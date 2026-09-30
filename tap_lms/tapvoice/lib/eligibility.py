from dataclasses import dataclass, field
from typing import Dict, List

import frappe

from tap_lms.tapvoice.constants import PERMANENT_FAILURE_REASONS, RUN_DOCTYPE
from tap_lms.tapvoice.lib.languages import normalize as normalize_language
from tap_lms.tapvoice.lib.text import prepare as prepare_text

SUBMISSION_DOCTYPE = "Submission"

FETCH_FIELDS = (
    "name",
    "status",
    "overall_feedback_translated",
    "translation_language",
    "audio_feedback_url",
    "result_status",
    "is_plagiarized",
    "is_ai_generated",
    "creation",
    "completed_at",
    "modified",
)

BASIS_COLUMNS = {
    "creation": "creation",
    "completed_at": "completed_at",
    "modified": "modified",
}


@dataclass(frozen=True)
class EligibleItem:
    id: str
    language: str
    text: str
    truncated: bool
    fingerprint: str
    age_hours: float
    urgent: bool


@dataclass
class EligibilityResult:
    items: List[EligibleItem] = field(default_factory=list)
    urgent_count: int = 0
    skipped_unsupported_language: int = 0
    unsupported_language_values: Dict[str, int] = field(default_factory=dict)
    skipped_empty_text: int = 0
    skipped_over_length: int = 0
    skipped_recent_failure: int = 0
    skipped_flagged: int = 0
    scanned: int = 0


def _excluded_ids(skip_recent_failures_runs):
    if skip_recent_failures_runs <= 0:
        return set()
    runs = frappe.get_all(
        RUN_DOCTYPE,
        filters={"failed_items": ["is", "set"]},
        fields=["name", "failed_items"],
        order_by="creation desc",
        limit_page_length=skip_recent_failures_runs,
    )
    excluded = set()
    for run in runs:
        try:
            mapping = frappe.parse_json(run.failed_items) or {}
        except Exception:
            continue
        for item_id, reason in mapping.items():
            if reason in PERMANENT_FAILURE_REASONS:
                excluded.add(item_id)
    return excluded


def _is_flagged(row):
    if row.result_status == "Success - Flagged":
        return True
    if row.is_plagiarized:
        return True
    if row.is_ai_generated:
        return True
    return False


def _window_start(window_hours):
    return frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-window_hours)


def find_eligible(settings, max_scan):
    basis_column = BASIS_COLUMNS.get(settings.window_basis, "creation")
    window_start = _window_start(settings.window_hours)
    excluded = _excluded_ids(settings.skip_recent_failures_runs)
    max_chars = settings.max_text_chars()
    policy = settings.over_length_policy

    filters = [
        [basis_column, ">=", window_start],
        ["audio_feedback_url", "in", ["", None]],
    ]

    rows = frappe.get_all(
        SUBMISSION_DOCTYPE,
        filters=filters,
        fields=list(FETCH_FIELDS),
        order_by=f"{basis_column} asc",
        limit_page_length=max_scan,
    )

    result = EligibilityResult()
    now = frappe.utils.now_datetime()
    for row in rows:
        result.scanned += 1
        if row.status == "Failed":
            continue
        feedback = (row.overall_feedback_translated or "").strip()
        if not feedback:
            result.skipped_empty_text += 1
            continue
        if row.name in excluded:
            result.skipped_recent_failure += 1
            continue
        if settings.skip_flagged and _is_flagged(row):
            result.skipped_flagged += 1
            continue

        prepared = prepare_text(feedback, row.translation_language, max_chars, policy)
        if prepared is None:
            if normalize_language(row.translation_language) is None:
                result.skipped_unsupported_language += 1
                key = str(row.translation_language or "")
                result.unsupported_language_values[key] = (
                    result.unsupported_language_values.get(key, 0) + 1
                )
            elif len(feedback) > max_chars and policy == "skip":
                result.skipped_over_length += 1
            else:
                result.skipped_empty_text += 1
            continue

        basis_value = row.get(basis_column) or row.creation
        age_hours = (
            frappe.utils.time_diff_in_hours(now, basis_value) if basis_value else 0.0
        )
        urgent_threshold = settings.window_hours - settings.run_interval_hours - settings.urgent_margin_hours
        urgent = age_hours >= max(0, urgent_threshold)
        if urgent:
            result.urgent_count += 1

        result.items.append(
            EligibleItem(
                id=row.name,
                language=prepared.language,
                text=prepared.text,
                truncated=prepared.truncated,
                fingerprint=prepared.fingerprint,
                age_hours=age_hours,
                urgent=urgent,
            )
        )

    return result


def oldest_age_hours(result):
    if not result.items:
        return 0.0
    return max(item.age_hours for item in result.items)