"""
ArchetypeConfig validators — CR-003.

tap_lms/summer_program/validators.py

Standalone validation helpers that can be called from controllers, the
`validate_ab_config` API (task #14, pending), bench scripts, and ad-hoc
audits. These do NOT have side effects — they read configuration and
return (ok, message) tuples.

Per L-027 (MVP discipline): only the helper that CR-003 actually consumes
is implemented here. The full `validate_ab_config` API surface lives in
task #14 and will pull this helper in alongside other rule checks.
"""
import frappe

from tap_lms.summer_program.constants import DEFAULT_GRACE_WINDOW_DAYS


def validate_escalation_hours_fit_grace(archetype_config_name):
    """CR-003 §"Validation rule":

    The sum of `escalation_steps.hours_after_previous` for an
    ArchetypeConfig must not exceed the cohort's grace window
    (`Batch.grace_window_days * 24` hours). If it does, the later
    escalation steps would never fire because the grace clock expires
    first — admins must reconfigure either the steps or the cohort grace.

    Args:
        archetype_config_name: ArchetypeConfig document name.

    Returns:
        (True, None) if config is valid.
        (False, error_message) if the sum exceeds the cohort window.

    Notes:
        - Only `is_active` escalation steps count toward the sum, matching
          the runtime semantics in `_get_escalation_steps`.
        - If the ArchetypeConfig isn't linked to a Batch, or the batch has
          no `grace_window_days`, we fall back to
          `DEFAULT_GRACE_WINDOW_DAYS` (14) and surface that in the error
          for the admin's benefit.
        - Returning a tuple (rather than throwing) keeps the helper usable
          from both validation hooks (which can throw on False) and
          standalone audit scripts (which want to collect failures).
    """
    try:
        config = frappe.get_doc("ArchetypeConfig", archetype_config_name)
    except frappe.DoesNotExistError:
        return False, f"ArchetypeConfig {archetype_config_name} not found"

    if not config.escalation_steps:
        # No steps at all is acceptable — the cohort just has no nudges.
        return True, None

    sum_hours = 0
    for step in config.escalation_steps:
        if not step.is_active:
            continue
        sum_hours += step.hours_after_previous or 0

    # Resolve grace window from the batch this config attaches to.
    grace_days = None
    if config.batch:
        grace_days = frappe.db.get_value("Batch", config.batch, "grace_window_days")
    if not grace_days:
        grace_days = DEFAULT_GRACE_WINDOW_DAYS

    grace_hours = int(grace_days) * 24

    if sum_hours > grace_hours:
        return False, (
            f"ArchetypeConfig {archetype_config_name}: sum of escalation "
            f"hours_after_previous ({sum_hours}h) exceeds the cohort's "
            f"grace window ({grace_days}d = {grace_hours}h). "
            f"Later escalation steps would never fire because the grace "
            f"clock would expire first. Either trim the steps or extend "
            f"Batch.grace_window_days."
        )

    return True, None
