import frappe

from tap_lms.tapvoice.lib import budget
from tap_lms.tapvoice.lib.eligibility import find_eligible

DECISION_DEPLOY = "Deploy"
DECISION_SKIP_NOTHING = "Skip: nothing to convert"
DECISION_SKIP_MINIMUM = "Skip: below minimum"
DECISION_SKIP_BUDGET = "Skip: budget"


def _is_urgent(age_hours, window_hours, run_interval_hours, urgent_margin_hours):
    return age_hours + run_interval_hours >= window_hours - urgent_margin_hours


def plan_batch(settings, force=False):
    found = find_eligible(settings)

    if not found["items"]:
        return {
            "decision": DECISION_SKIP_NOTHING,
            "reason": "no eligible submissions in window",
            "eligible_found": 0,
            "urgent_count": 0,
            "truncated_count": 0,
            "estimated_cost_usd": 0,
            "manifest": [],
        }

    urgent_count = sum(
        1
        for item in found["items"]
        if _is_urgent(
            item["age_hours"],
            settings.window_hours,
            settings.run_interval_hours,
            settings.urgent_margin_hours,
        )
    )

    below_minimum = len(found["items"]) < settings.min_items_to_deploy
    allow_bypass = force and settings.allow_force_start
    if below_minimum and urgent_count == 0 and not allow_bypass:
        return {
            "decision": DECISION_SKIP_MINIMUM,
            "reason": f"{len(found['items'])} eligible, minimum is {settings.min_items_to_deploy}",
            "eligible_found": len(found["items"]),
            "urgent_count": urgent_count,
            "truncated_count": found["truncated_count"],
            "estimated_cost_usd": 0,
            "manifest": [],
        }

    trimmed = budget.fit_to_budget(settings, found["items"])
    if not trimmed["items"]:
        return {
            "decision": DECISION_SKIP_BUDGET,
            "reason": trimmed["reason"],
            "eligible_found": len(found["items"]),
            "urgent_count": urgent_count,
            "truncated_count": found["truncated_count"],
            "estimated_cost_usd": 0,
            "manifest": [],
        }

    return {
        "decision": DECISION_DEPLOY,
        "reason": None,
        "eligible_found": len(found["items"]),
        "urgent_count": urgent_count,
        "truncated_count": found["truncated_count"],
        "estimated_cost_usd": trimmed["estimated_cost_usd"],
        "manifest": trimmed["items"],
    }