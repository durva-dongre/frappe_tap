"""
ArchetypeConfig validators — CR-003 + task #14 (2026-05-13).

tap_lms/summer_program/validators.py

Two validation surfaces:

1. `validate_escalation_hours_fit_grace(config)` — per-config helper from
   CR-003. Returns `(ok, message)`. Stays as a building block consumed by
   the per-tuple validator below.

2. `validate_archetype_config(batch)` — task #14, the replacement for the
   retired `validate_ab_config`. Per-tuple completeness check that scales
   naturally with however many experiment_arms the team actually uses.
   See ADR-004 audit log (2026-05-13) for the supersession rationale.

The `preview_archetype_config_issues` whitelisted endpoint surfaces the
report shape to admins; the `validate_bpr` activation gate calls the
internal hard-fail wrapper before flipping a batch to active.
"""
import frappe

from tap_lms.summer_program.constants import (
    DEFAULT_GRACE_WINDOW_DAYS,
    PROGRAM_ACTIVE,
    PROGRAM_PAUSED,
)


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


# ════════════════════════════════════════════════════════════
# Task #14 (2026-05-13) — per-tuple completeness check
# ════════════════════════════════════════════════════════════
#
# ADR-004 supersession: the rigid "always 16" rule is retired. Instead,
# we compute which (archetype, in-use experiment_arm, path) tuples are
# actually present in the batch's PE roster and check that an active
# ArchetypeConfig exists for each, with the rules complete enough to
# drive the state machine through the program duration.
#
# Return shape is `{valid: bool, issues: [{severity, tuple, problem}]}`.
# Errors block batch activation; warnings surface in the admin UI but
# don't block. The hours-fit-grace rule (CR-003 §"Validation rule") is
# a warning under this scheme — the grace clock truncating later steps
# is operationally weird, but the batch can still run without dropping
# every student.


@frappe.whitelist(allow_guest=False)
def validate_archetype_config(batch_name):
    """Per-tuple completeness check for batch ArchetypeConfig rows.

    Whitelisted so admins can hit `/api/method/...validate_archetype_config`
    directly from the Batch UI's "Validate" button or ops scripts. The
    `preview_archetype_config_issues` wrapper below is an alias retained
    for backward compat with the doc's original naming.

    Per ADR-004 supersession (2026-05-13), the rigid 'always 16' rule is
    retired. This validator instead checks: for every
    (archetype, in-use experiment_arm, path) tuple actually present in
    the batch's PE roster, an active ArchetypeConfig must exist with
    non-empty active escalation steps and week rules covering the full
    program duration.

    Args:
        batch_name: the Batch document name.

    Returns:
        {
            "valid": bool,
            "issues": [
                {"severity": "error"|"warning",
                 "tuple": (archetype, arm, path),
                 "problem": str},
                ...
            ],
        }

    valid=False iff at least one error-severity issue is present. A
    batch with only warnings reports valid=True for the activation gate
    but the admin should still see and ideally fix them.
    """
    in_use = _compute_in_use_tuples(batch_name)

    issues = []
    try:
        batch = frappe.get_doc("Batch", batch_name)
    except frappe.DoesNotExistError:
        return {
            "valid": False,
            "issues": [{
                "severity": "error",
                "tuple": None,
                "problem": f"Batch {batch_name} not found",
            }],
        }

    for archetype, arm, path in sorted(in_use):
        issues.extend(_check_tuple(batch, archetype, arm, path))

    errors = [i for i in issues if i["severity"] == "error"]
    return {"valid": not errors, "issues": issues}


def _compute_in_use_tuples(batch_name):
    """Read PE roster, return set of (archetype, experiment_arm, path)
    tuples actually in use for this batch.

    PEs can switch between Core and Remedial during the program. To
    avoid a mid-program crash when a student crosses paths into a
    config that doesn't exist, we always require BOTH paths for every
    (archetype, arm) we see on the roster. This is cheap (max ~24
    tuples) and removes a class of activation-time bug.

    Postgres-specific: `= ANY(%s)` per L-005. Active+paused only — a
    PE in dropped/completed isn't going to consume a config anyway.
    """
    # Read PE columns directly, NOT a join to Student. The dispatcher reads
    # `pe.archetype` and `pe.experiment_arm` at runtime (see
    # pe_dispatcher.handle_escalation, save_submission, vocallabs, etc.); the
    # validator must agree with what the dispatcher will actually look for.
    # `Student.archetype` can diverge from `pe.archetype` because the PE field
    # is written once at enrollment and never re-synced — a Student.archetype
    # update post-enrollment would make the validator pass on Student's value
    # while the dispatcher fires on the stale PE value (H2 fix, 2026-05-13).
    rows = frappe.db.sql(
        """
        SELECT DISTINCT
            COALESCE(NULLIF(pe.archetype, ''), 'Submitter') AS archetype,
            COALESCE(NULLIF(pe.experiment_arm, ''), 'default') AS experiment_arm
          FROM "tabProgramEnrollment" pe
         WHERE pe.batch = %s
           AND pe.program_status = ANY(%s)
        """,
        (batch_name, [PROGRAM_ACTIVE, PROGRAM_PAUSED]),
        as_dict=True,
    )

    tuples = set()
    for r in rows:
        # Both paths because PEs may switch mid-program.
        tuples.add((r.archetype, r.experiment_arm, "Core"))
        tuples.add((r.archetype, r.experiment_arm, "Remedial"))
    return tuples


def _check_tuple(batch, archetype, arm, path):
    """Run completeness checks for one (archetype, arm, path) tuple.

    Returns a list of issue dicts (possibly empty). Each issue carries
    severity ∈ {error, warning}, the tuple identity for admin display,
    and a human-readable problem string.

    The checks are ordered: existence first (without an ArchetypeConfig
    nothing else can be validated), then escalation_steps presence,
    then the grace-fit warning, then week_rules coverage, then the
    per-step escalation_type non-empty check. Each block returns its
    own short-circuit decision so a single tuple can surface multiple
    related issues if relevant.
    """
    issues = []

    # Check 1: ArchetypeConfig exists and is active.
    config_name = frappe.db.get_value(
        "ArchetypeConfig",
        {
            "batch": batch.name,
            "archetype": archetype,
            "experiment_arm": arm,
            "path": path,
            "is_active": 1,
        },
        "name",
    )

    if not config_name:
        issues.append({
            "severity": "error",
            "tuple": (archetype, arm, path),
            "problem": "No active ArchetypeConfig found",
        })
        return issues  # can't check sub-rules without a config

    config = frappe.get_doc("ArchetypeConfig", config_name)

    # Check 2: escalation_steps non-empty (at least one active row).
    active_steps = [s for s in (config.escalation_steps or []) if s.is_active]
    if not active_steps:
        issues.append({
            "severity": "error",
            "tuple": (archetype, arm, path),
            "problem": "escalation_steps is empty or all inactive",
        })

    # Check 3: hours_after_previous sum vs grace window (CR-003 rule;
    # downgraded to warning under the task-#14 scheme — the batch can
    # still run, but later steps will be truncated by grace expiry).
    if active_steps:
        ok, msg = validate_escalation_hours_fit_grace(config_name)
        if not ok:
            issues.append({
                "severity": "warning",
                "tuple": (archetype, arm, path),
                "problem": msg or "escalation steps sum exceeds grace window",
            })

    # Check 4: week_rules cover all weeks 1..total_weeks. WeekRule has no
    # `is_active` field in the current schema, so every row counts.
    total_weeks = batch.total_weeks or 0
    week_rules = config.week_rules or []
    covered_weeks = {wr.week for wr in week_rules if wr.week}
    if total_weeks:
        missing_weeks = set(range(1, total_weeks + 1)) - covered_weeks
        if missing_weeks:
            issues.append({
                "severity": "error",
                "tuple": (archetype, arm, path),
                "problem": f"week_rules missing weeks: {sorted(missing_weeks)}",
            })

    # Check 5: each active escalation step has a non-empty escalation_type.
    # The CR-003 dispatcher branches on this column; an empty value would
    # fall through to the default (`help_note_a`) silently and the admin
    # would never know the parent_call / voice_note routing they intended
    # never fires. One issue per tuple is enough for the report.
    for step in active_steps:
        if not (step.escalation_type or "").strip():
            issues.append({
                "severity": "error",
                "tuple": (archetype, arm, path),
                "problem": (
                    f"escalation step #{step.escalation_order} has empty "
                    f"escalation_type"
                ),
            })
            break

    return issues


@frappe.whitelist(allow_guest=False)
def preview_archetype_config_issues(batch_name):
    """Admin preview API: returns the same `{valid, issues}` shape as
    `validate_archetype_config` without raising. Admins click a button on
    the BPR form to inspect what the activation gate would say, fix any
    errors in the underlying ArchetypeConfig rows, and re-run.

    The activation gate (`_validate_archetype_config_before_activation`)
    is the hard-fail wrapper called from `batch_activation.activate_bpr`;
    this method is the soft-preview surface.
    """
    return validate_archetype_config(batch_name)


def _validate_archetype_config_before_activation(batch_name):
    """Hard-fail wrapper for batch activation.

    Called from `batch_activation.activate_bpr` BEFORE the BPR flips to
    BPR_ACTIVE. Throws `frappe.ValidationError` with a multi-line message
    listing every error-severity issue. Warnings are ignored at this gate
    — they surface through the preview API for the admin to see.
    """
    result = validate_archetype_config(batch_name)
    errors = [i for i in result["issues"] if i["severity"] == "error"]
    if not errors:
        return

    msg_lines = ["Cannot activate batch — fix these ArchetypeConfig issues first:"]
    for issue in errors:
        tup = issue.get("tuple")
        tup_str = f"{tup}" if tup else "(batch-level)"
        msg_lines.append(f"  - {tup_str}: {issue['problem']}")
    frappe.throw("\n".join(msg_lines), frappe.ValidationError)
