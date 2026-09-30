import frappe

from tap_lms.tapvoice.lib import languages
from tap_lms.tapvoice.lib.text import prepare as prepare_text

FAILED_STATUS = "Failed"
PERMANENT_FAILURE_REASONS = frozenset(
    {
        "silent",
        "too_short",
        "too_long",
        "pace_short",
        "pace_long",
        "too_few_tokens",
        "bad_codes",
        "truncated",
        "prompt_too_long",
        "empty",
        "non_finite",
        "text_too_long",
        "empty_text",
    }
)


def _excluded_ids(recent_run_count):
    if not recent_run_count:
        return set()
    runs = frappe.get_all(
        "Tap Voice Run",
        filters={"status": ["not in", ["Draft", "Skipped"]]},
        fields=["failed_items"],
        order_by="created_at desc",
        limit_page_length=recent_run_count,
    )
    excluded = set()
    for run in runs:
        if not run.failed_items:
            continue
        mapping = frappe.parse_json(run.failed_items)
        for item_id, reason in mapping.items():
            if reason in PERMANENT_FAILURE_REASONS:
                excluded.add(item_id)
    return excluded


def find_eligible(settings, max_scan):
    basis_field = settings.window_basis or "creation"
    window_start = frappe.utils.add_to_date(
        frappe.utils.now_datetime(), hours=-int(settings.window_hours)
    )
    excluded = _excluded_ids(settings.skip_recent_failures_runs)

    filters = [
        [basis_field, ">=", window_start],
        ["audio_feedback_url", "in", ["", None]],
    ]
    if not settings.skip_flagged:
        pass
    else:
        filters.append(["result_status", "!=", "Success - Flagged"])

    rows = frappe.get_all(
        "Submission",
        filters=filters,
        fields=[
            "name",
            "status",
            basis_field,
            "overall_feedback_translated",
            "translation_language",
            "audio_feedback_url",
        ],
        order_by=f"{basis_field} asc",
        limit_page_length=max_scan,
    )

    items = []
    truncated_count = 0
    skipped_unsupported_language = 0
    unsupported_language_values = {}
    skipped_empty_text = 0
    skipped_recent_failure = 0
    skipped_flagged = 0

    for row in rows:
        if row.status == FAILED_STATUS:
            continue
        if row.name in excluded:
            skipped_recent_failure += 1
            continue
        feedback = (row.overall_feedback_translated or "").strip()
        if not feedback:
            skipped_empty_text += 1
            continue
        language = languages.normalize(row.translation_language)
        if language is None:
            skipped_unsupported_language += 1
            raw_value = row.translation_language or ""
            unsupported_language_values[raw_value] = unsupported_language_values.get(raw_value, 0) + 1
            continue

        max_chars = settings.max_chars_per_text
        policy = settings.over_length_policy
        prepared, was_truncated = prepare_text(feedback, language, max_chars, policy)
        if not prepared:
            skipped_empty_text += 1
            continue
        if was_truncated:
            truncated_count += 1

        basis_value = row.get(basis_field)
        age_hours = (
            frappe.utils.time_diff_in_hours(frappe.utils.now_datetime(), basis_value)
            if basis_value
            else 0
        )

        items.append(
            {
                "id": row.name,
                "text": prepared,
                "language": language,
                "age_hours": age_hours,
            }
        )

    return {
        "items": items,
        "truncated_count": truncated_count,
        "skipped_unsupported_language": skipped_unsupported_language,
        "unsupported_language_values": unsupported_language_values,
        "skipped_empty_text": skipped_empty_text,
        "skipped_recent_failure": skipped_recent_failure,
        "skipped_flagged": skipped_flagged,
    }