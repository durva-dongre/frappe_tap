import frappe

from tap_lms.tapvoice.constants import (
    DECISION_DEPLOY,
    DECISION_SKIP_BELOW_MINIMUM,
    DECISION_SKIP_BUDGET,
    DECISION_SKIP_NOTHING,
)
from tap_lms.tapvoice.lib import budget
from tap_lms.tapvoice.lib.eligibility import find_eligible

DEFAULT_MAX_SCAN = 5000


class Plan:
    def __init__(
        self,
        decision,
        reason,
        eligible_found,
        urgent_count,
        truncated_count,
        skipped_unsupported_language,
        unsupported_language_values,
        skipped_empty_text,
        skipped_recent_failure,
        skipped_flagged,
        deferred_over_budget,
        estimated_cost_usd,
        estimated_seconds,
        today_spend_usd,
        month_spend_usd,
        items,
    ):
        self.decision = decision
        self.reason = reason
        self.eligible_found = eligible_found
        self.urgent_count = urgent_count
        self.truncated_count = truncated_count
        self.skipped_unsupported_language = skipped_unsupported_language
        self.unsupported_language_values = unsupported_language_values
        self.skipped_empty_text = skipped_empty_text
        self.skipped_recent_failure = skipped_recent_failure
        self.skipped_flagged = skipped_flagged
        self.deferred_over_budget = deferred_over_budget
        self.estimated_cost_usd = estimated_cost_usd
        self.estimated_seconds = estimated_seconds
        self.today_spend_usd = today_spend_usd
        self.month_spend_usd = month_spend_usd
        self.items = items


def _is_urgent(age_hours, window_hours, run_interval_hours, urgent_margin_hours):
    return age_hours + run_interval_hours >= window_hours - urgent_margin_hours


def plan_batch(settings, force=False, max_scan=DEFAULT_MAX_SCAN, only_names=None):
    found = find_eligible(settings, max_scan, only_names=only_names)

    if not found.items:
        return Plan(
            decision=DECISION_SKIP_NOTHING,
            reason="no eligible submissions in window",
            eligible_found=0,
            urgent_count=0,
            truncated_count=0,
            skipped_unsupported_language=found.skipped_unsupported_language,
            unsupported_language_values=found.unsupported_language_values,
            skipped_empty_text=found.skipped_empty_text,
            skipped_recent_failure=found.skipped_recent_failure,
            skipped_flagged=found.skipped_flagged,
            deferred_over_budget=0,
            estimated_cost_usd=0,
            estimated_seconds=0,
            today_spend_usd=0,
            month_spend_usd=0,
            items=[],
        )

    urgent_count = sum(
        1
        for item in found.items
        if _is_urgent(
            item.age_hours,
            settings.window_hours,
            settings.run_interval_hours,
            settings.urgent_margin_hours,
        )
    )

    below_minimum = len(found.items) < settings.min_items_to_deploy
    allow_bypass = force and settings.allow_force_start
    if below_minimum and urgent_count == 0 and not allow_bypass:
        return Plan(
            decision=DECISION_SKIP_BELOW_MINIMUM,
            reason=f"{len(found.items)} eligible, minimum is {settings.min_items_to_deploy}",
            eligible_found=len(found.items),
            urgent_count=urgent_count,
            truncated_count=found.truncated_count,
            skipped_unsupported_language=found.skipped_unsupported_language,
            unsupported_language_values=found.unsupported_language_values,
            skipped_empty_text=found.skipped_empty_text,
            skipped_recent_failure=found.skipped_recent_failure,
            skipped_flagged=found.skipped_flagged,
            deferred_over_budget=0,
            estimated_cost_usd=0,
            estimated_seconds=0,
            today_spend_usd=0,
            month_spend_usd=0,
            items=[],
        )

    check = budget.fit_to_caps(settings, found.items)
    trimmed_items = found.items[: check.trimmed_count]
    deferred = len(found.items) - len(trimmed_items)

    if not check.fits:
        return Plan(
            decision=DECISION_SKIP_BUDGET,
            reason=check.reason,
            eligible_found=len(found.items),
            urgent_count=urgent_count,
            truncated_count=found.truncated_count,
            skipped_unsupported_language=found.skipped_unsupported_language,
            unsupported_language_values=found.unsupported_language_values,
            skipped_empty_text=found.skipped_empty_text,
            skipped_recent_failure=found.skipped_recent_failure,
            skipped_flagged=found.skipped_flagged,
            deferred_over_budget=deferred,
            estimated_cost_usd=0,
            estimated_seconds=0,
            today_spend_usd=check.today_spend_usd,
            month_spend_usd=check.month_spend_usd,
            items=[],
        )

    return Plan(
        decision=DECISION_DEPLOY,
        reason=None,
        eligible_found=len(found.items),
        urgent_count=urgent_count,
        truncated_count=found.truncated_count,
        skipped_unsupported_language=found.skipped_unsupported_language,
        unsupported_language_values=found.unsupported_language_values,
        skipped_empty_text=found.skipped_empty_text,
        skipped_recent_failure=found.skipped_recent_failure,
        skipped_flagged=found.skipped_flagged,
        deferred_over_budget=deferred,
        estimated_cost_usd=check.estimate.cost_usd,
        estimated_seconds=check.estimate.seconds,
        today_spend_usd=check.today_spend_usd,
        month_spend_usd=check.month_spend_usd,
        items=trimmed_items,
    )