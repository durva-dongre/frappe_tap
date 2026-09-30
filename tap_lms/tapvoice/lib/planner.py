from dataclasses import dataclass, field
from typing import Dict, List

from tap_lms.tapvoice.constants import (
    DECISION_DEPLOY,
    DECISION_SKIP_BELOW_MINIMUM,
    DECISION_SKIP_BUDGET,
    DECISION_SKIP_NOTHING,
)
from tap_lms.tapvoice.lib import budget as budget_lib
from tap_lms.tapvoice.lib import eligibility as eligibility_lib


@dataclass
class PlanResult:
    decision: str
    reason: str
    items: List[eligibility_lib.EligibleItem] = field(default_factory=list)
    eligible_found: int = 0
    urgent_count: int = 0
    truncated_count: int = 0
    skipped_unsupported_language: int = 0
    unsupported_language_values: Dict[str, int] = field(default_factory=dict)
    skipped_empty_text: int = 0
    skipped_over_length: int = 0
    skipped_recent_failure: int = 0
    skipped_flagged: int = 0
    deferred_over_budget: int = 0
    estimated_cost_usd: float = 0.0
    estimated_seconds: float = 0.0
    today_spend_usd: float = 0.0
    month_spend_usd: float = 0.0


def _urgent_first(items):
    return sorted(items, key=lambda item: not item.urgent)


def plan_batch(settings, force=False, max_scan=20000, hourly_rate=None):
    elig = eligibility_lib.find_eligible(settings, max_scan)

    base = PlanResult(
        decision=DECISION_SKIP_NOTHING,
        reason="",
        eligible_found=len(elig.items),
        urgent_count=elig.urgent_count,
        truncated_count=sum(1 for i in elig.items if i.truncated),
        skipped_unsupported_language=elig.skipped_unsupported_language,
        unsupported_language_values=dict(elig.unsupported_language_values),
        skipped_empty_text=elig.skipped_empty_text,
        skipped_over_length=elig.skipped_over_length,
        skipped_recent_failure=elig.skipped_recent_failure,
        skipped_flagged=elig.skipped_flagged,
    )

    if not elig.items:
        base.reason = "no eligible submissions found"
        return base

    ordered_items = _urgent_first(elig.items)

    worth_it = len(ordered_items) >= settings.min_items_to_deploy or elig.urgent_count > 0
    if not worth_it and not (force and settings.allow_force_start):
        base.decision = DECISION_SKIP_BELOW_MINIMUM
        base.reason = (
            f"{len(ordered_items)} eligible, below minimum {settings.min_items_to_deploy}, "
            f"oldest age {eligibility_lib.oldest_age_hours(elig):.1f}h"
        )
        base.items = ordered_items
        return base

    check = budget_lib.fit_to_caps(settings, ordered_items, hourly_rate)
    base.estimated_cost_usd = check.estimate.cost_usd
    base.estimated_seconds = check.estimate.seconds
    base.today_spend_usd = check.today_spend_usd
    base.month_spend_usd = check.month_spend_usd

    if not check.fits or check.trimmed_count == 0:
        base.decision = DECISION_SKIP_BUDGET
        base.reason = (
            f"budget exhausted: today ${check.today_spend_usd:.2f}, "
            f"month ${check.month_spend_usd:.2f}"
        )
        base.items = ordered_items
        return base

    trimmed_items = ordered_items[: check.trimmed_count]
    base.deferred_over_budget = len(ordered_items) - len(trimmed_items)
    base.items = trimmed_items
    base.decision = DECISION_DEPLOY
    base.reason = f"deploying {len(trimmed_items)} items, est cost ${check.estimate.cost_usd:.4f}"
    return base