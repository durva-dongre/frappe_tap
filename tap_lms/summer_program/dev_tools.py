"""
Summer Program — dev / test reset helpers.

Tools for re-running a student (or all students in a batch) through the SP
journey from state 0. Used during integration testing where the same dev
contacts need to be cycled through many times.

**USE FOR DEV/TEST ONLY.** Every function in this module DESTROYS journey
history (StudentQuizAttempt / StudentContentLog / StudentStageProgress /
StudentReflection / TransitionHistory / ProgramEventLog rows). A safety
guard refuses to run on sites whose name suggests a production environment
unless the caller explicitly opts in.

**Submission rows are deliberately PRESERVED across resets** so the team
can analyse AI-feedback quality and submission-pipeline behaviour across
many test cycles for the same student. If you need a truly clean slate
(e.g. to test the save_submission claim logic), delete the rows manually
via console.

Usage from `bench execute`:

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.list_pes_for_batch \\
        --kwargs '{"batch_name": "palv2-test-BT52231"}'

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.reset_pe_to_state_0 \\
        --kwargs '{"student_id": "STU-0001", "dry_run": true}'

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.reset_pe_to_state_0 \\
        --kwargs '{"student_id": "STU-0001"}'

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.reset_pes_for_batch \\
        --kwargs '{"batch_name": "palv2-test-BT52231"}'

Usage from `bench console`:

    >>> from tap_lms.summer_program.dev_tools import reset_pe_to_state_0
    >>> reset_pe_to_state_0("STU-0001", dry_run=True)
    >>> reset_pe_to_state_0("STU-0001")
"""
import frappe

from tap_lms.summer_program.constants import (
    STATE_NORMAL_CONTENT,
    LABEL_ENROLLED,
    PROGRAM_ACTIVE,
    PROGRAM_PAUSED,
    PATH_CORE,
    # Task #84: pull the canonical lists from constants instead of
    # hardcoding so the dev_tools validation stays in sync with the
    # enum source-of-truth used elsewhere (state machine, doctype
    # Select options, Glific field contracts).
    ALL_ARCHETYPES,
    ALL_ARMS,
)
# Hoisted at module level so tests can patch at the canonical location
# `tap_lms.summer_program.dev_tools.{maintain_collections,_enqueue_contact_field_sync}`
# without depending on Python's late-binding behaviour for inline imports.
from tap_lms.summer_program.collection_membership import maintain_collections
from tap_lms.summer_program.state_machine import _enqueue_contact_field_sync
# Task #82/#84: dev_tools reset must recompute current_expected_submission_type
# from the archetype's WeekRule, and update_student_state must do the same
# when week/path/archetype/arm change. The canonical helpers live in the
# enrollment API module; importing them here keeps a single source of truth.
from tap_lms.summer_program.program_enrollment_api import (
    _get_week1_submission_type,
    _get_expected_submission_type_for_week,
)


# ════════════════════════════════════════════════════════════
# Safety guard
# ════════════════════════════════════════════════════════════

_PRODUCTION_SITE_MARKERS = ("prod", "live", "production")


def _assert_dev_site(i_know_this_is_destructive=False):
    """Refuse to run on sites whose name suggests a production environment.

    The check is heuristic — it pattern-matches the site name against a
    small denylist (`prod`, `live`, `production`). False positives are
    unlocked by passing `i_know_this_is_destructive=True`, which is the
    operator's signed acknowledgement.

    Raises:
        frappe.PermissionError on a suspected-prod site without override.
    """
    if i_know_this_is_destructive:
        return

    site = (frappe.local.site or "").lower()
    for marker in _PRODUCTION_SITE_MARKERS:
        if marker in site:
            raise frappe.PermissionError(
                f"dev_tools refuses to run on site '{site}' (matched "
                f"production marker '{marker}'). If you really mean to "
                f"do this, pass i_know_this_is_destructive=True."
            )


# ════════════════════════════════════════════════════════════
# Listing helper
# ════════════════════════════════════════════════════════════

def list_pes_for_batch(batch_name):
    """Print all active/paused PEs for a batch with key state fields.

    Read-only — no safety guard needed.

    Returns the list of dicts so callers (or tests) can introspect.
    """
    frappe.db.rollback()  # PG txn hygiene

    rows = frappe.db.sql(
        """
        SELECT
            pe.name                   AS pe,
            pe.student,
            s.name1                   AS student_name,
            pe.resolved_flow_state,
            pe.current_week,
            pe.current_path,
            pe.journey_label,
            pe.submission_count,
            pe.current_escalation_step,
            pe.delivery_failure_count,
            pe.glific_id,
            pe.program_status
          FROM "tabProgramEnrollment" pe
          LEFT JOIN "tabStudent" s ON s.name = pe.student
         WHERE pe.batch = %s
           AND pe.program_status IN ('active', 'paused')
         ORDER BY pe.name
        """,
        (batch_name,),
        as_dict=True,
    )

    for r in rows:
        name = r.get("student_name") or "<no name>"
        print(
            f"{r['pe']}  {name:25}  "
            f"w{r['current_week']} {r['current_path'] or '-':8} "
            f"state={r['resolved_flow_state']:30} "
            f"step={r['current_escalation_step']} "
            f"subs={r['submission_count']} "
            f"status={r['program_status']}"
        )
    print(f"\n{len(rows)} PEs total in batch {batch_name}.")
    return rows


# ════════════════════════════════════════════════════════════
# Single-PE reset
# ════════════════════════════════════════════════════════════

# Fields zeroed by the reset. Listed explicitly so adding a new PE column
# without thinking about reset behaviour is a visible omission (rather than
# silently retaining stale data).
_FIELDS_TO_ZERO = (
    # Counters
    "submission_count",
    "current_escalation_step",
    "last_escalation_step",
    "delivery_failure_count",
    # Grace
    "in_grace_window",
    # CR-002 v2 gamification — per-stream totals AND the rollup.
    # Task #85: total_points was previously missing here, so per-stream
    # totals got zeroed but total_points stayed at its old value, breaking
    # the invariant `total_activity + total_quiz + total_submission ==
    # total_points`. This was the exact pattern of ST00051295's drift in
    # the 2026-05-24 audit (total_points=1053, all per-stream=0). Zeroing
    # total_points alongside the streams keeps the invariant intact and
    # makes the Glific reconcile push a coherent state-0 bundle.
    "total_points",
    "total_activity_points",
    "weekly_activity_points",
    "total_quiz_points",
    "weekly_quiz_points",
    "bonus_quiz_points",
    "total_submission_points",
    "weekly_submission_points",
    "special_gems",
    "current_streak",
    # CR-002 v2 + CR-003 follow-up 2 sticky flags
    "weekly_video_done",
    "weekly_submission_done",
)

# Fields nulled by the reset (vs. zeroed).
_FIELDS_TO_NULL = (
    "next_action_at",
    "grace_window_start",
    "grace_window_end_at",
)

# Fields cleared to empty string.
# Task #85: current_escalation_type and pause_reason were previously
# missing. current_escalation_step zeros to 0 but the type string ('parent_call',
# 'help_note_b') stayed at its old value — Glific contact then ended up with
# step=0 + type='parent_call' (mismatch). pause_reason similarly carried over
# 'binge_limit' even though program_status was switched back to active.
_FIELDS_TO_CLEAR = (
    "next_action_type",
    "drop_reason",
    "current_escalation_type",
    "pause_reason",
)

# Historical/audit rows to delete when delete_history=True.
# Tuple shape: (doctype, FK field name ON that doctype, source-key — either
# 'student' to fill with pe.student, or 'pe_name' to fill with the PE name).
#
# FK names verified against the doctype JSONs (2026-05-16):
#   - StudentQuizAttempt.student / StudentContentLog.student are Link to Student
#   - ProgramEventLog.enrollment is the PE link (NOT 'program_enrollment')
#   - StudentStageProgress.student is a Link to Student. CRITICAL: this is
#     the doctype `get_next_content` reads to track current_content_index /
#     is_on_remedial / active_content_type / current_question_index — without
#     clearing it, the next-content API stays stuck on the old position even
#     after the PE row is reset.
#   - StudentReflection.student / TransitionHistory.student are Link to Student.
#
# Submission is DELIBERATELY OMITTED from this list (2026-05-18 product
# decision). The team analyses AI-feedback quality across many test cycles
# for the same student, so historical Submission rows must persist. Trade-
# offs accepted: (a) PE.submission_count is reset to 0 while old Submission
# rows persist — counter is intentionally inconsistent with row count, and
# (b) re-submitting the same week may hit save_submission's claim logic
# depending on uniqueness constraints. Both are dev-only nuisances; the
# benefit of feedback-quality analysis outweighs them.
_HISTORY_DOCTYPES = (
    ("StudentQuizAttempt",    "student",            "student"),
    ("StudentContentLog",     "student",            "student"),
    ("StudentStageProgress",  "student",            "student"),
    ("StudentReflection",     "student",            "student"),
    ("TransitionHistory",     "student",            "student"),
    ("ProgramEventLog",       "enrollment",         "pe_name"),
)


@frappe.whitelist(allow_guest=False)
def reset_pe_to_state_0(
    student_id,
    dry_run=False,
    delete_history=True,
    push_to_glific=True,
    verbose=True,
    i_know_this_is_destructive=False,
):
    """Reset a student's active ProgramEnrollment to its initial state.

    Resets:
      - PE state machine fields → state 0 (normal_content_delivery, week 1,
        Core path, enrolled label, active status)
      - All counters → 0
      - Grace window → cleared
      - CR-002 v2 gamification points (weekly + total) → 0
      - Sticky weekly flags → 0
      - Scheduler pointers (next_action_at, next_action_type) → cleared

    Optionally:
      - Deletes journey history when `delete_history=True` (default):
        StudentQuizAttempt, StudentContentLog, StudentStageProgress,
        StudentReflection, TransitionHistory, ProgramEventLog.
        NOTE: Submission rows are DELIBERATELY PRESERVED so the team can
        analyse AI-feedback quality across many reset cycles for the same
        student. See the comment on `_HISTORY_DOCTYPES` for the rationale.
      - Pushes fresh contact fields to Glific when `push_to_glific=True`
        (default), so Glific flows see the reset state immediately.
      - Calls `maintain_collections(pe, from_state, to_state=normal)` so the
        CR-005 Glific group membership is corrected (PE removed from any
        escalation/audit group, ensured in `main`).

    Does NOT touch:
      - Student.archetype / Student.experiment_arm / Student.glific_id
        (upstream-supplied data per CLAUDE.md)
      - BPR aggregate counters
      - Batch / ArchetypeConfig / WeekRule (configuration)

    Args:
        student_id: Student.name whose active/paused ProgramEnrollment is reset
        dry_run: if True, print intended changes without writing
        delete_history: if True, delete journey audit rows for this student
        push_to_glific: if True, enqueue a contact-field sync job
        verbose: if True, print before/after snapshot
        i_know_this_is_destructive: bypass the production-site safety guard

    Returns:
        dict with `before` and `after` snapshots, plus `history_deleted` counts.

    Raises:
        frappe.PermissionError if site name suggests production.
        frappe.DoesNotExistError if student_id is invalid.
        frappe.ValidationError if student has no active/paused PE.
    """
    dry_run = _coerce_bool(dry_run)
    delete_history = _coerce_bool(delete_history)
    push_to_glific = _coerce_bool(push_to_glific)
    verbose = _coerce_bool(verbose)
    i_know_this_is_destructive = _coerce_bool(i_know_this_is_destructive)

    _assert_dev_site(i_know_this_is_destructive=i_know_this_is_destructive)

    frappe.db.rollback()  # PG txn hygiene

    if not frappe.db.exists("Student", student_id):
        frappe.throw(f"Student not found: {student_id}", frappe.DoesNotExistError)

    pe = _get_active_pe_for_student(student_id)
    if not pe:
        frappe.throw(
            f"No active/paused ProgramEnrollment found for student {student_id}",
            frappe.ValidationError,
        )

    return _reset_pe_doc_to_state_0(
        pe,
        dry_run=dry_run,
        delete_history=delete_history,
        push_to_glific=push_to_glific,
        verbose=verbose,
    )


def _reset_pe_doc_to_state_0(
    pe,
    dry_run=False,
    delete_history=True,
    push_to_glific=True,
    verbose=True,
):
    """Reset an already-resolved PE doc. Keep public API resolution separate."""
    pe_name = pe.name
    student_id = pe.student

    # ── Snapshot history counts ──────────────────────────
    history_counts = {}
    for dt, field, key_source in _HISTORY_DOCTYPES:
        key = student_id if key_source == "student" else pe_name
        try:
            history_counts[dt] = frappe.db.count(dt, {field: key})
        except Exception as e:
            history_counts[dt] = f"<error: {e}>"

    before = _snapshot(pe)
    before["history_rows"] = history_counts

    if verbose:
        print(f"\nPE {pe_name} (student={student_id}) BEFORE:")
        for k, v in before.items():
            print(f"  {k:30} = {v}")

    if dry_run:
        if verbose:
            print("\nDRY RUN — nothing written.")
        return {"before": before, "after": None, "history_deleted": {}}

    from_state = pe.resolved_flow_state
    history_deleted = {}

    # ── 1. Delete journey history (if requested) ─────────
    if delete_history:
        for dt, field, key_source in _HISTORY_DOCTYPES:
            key = student_id if key_source == "student" else pe_name
            try:
                frappe.db.sql(
                    f'DELETE FROM "tab{dt}" WHERE "{field}" = %s',
                    (key,),
                )
                history_deleted[dt] = history_counts.get(dt, 0)
                if verbose:
                    print(f"  deleted {history_deleted[dt]} rows from {dt}")
            except Exception as e:
                history_deleted[dt] = f"<error: {e}>"
                if verbose:
                    print(f"  could not delete from {dt}: {e}")

    # ── 2. Reset PE state-machine fields ─────────────────
    pe.resolved_flow_state = STATE_NORMAL_CONTENT
    pe.journey_label = LABEL_ENROLLED
    pe.program_status = PROGRAM_ACTIVE
    pe.current_week = 1
    pe.current_path = PATH_CORE
    if hasattr(pe, "current_tier"):
        pe.current_tier = "Basic"  # week-1 default per TIER_BY_WEEK

    for f in _FIELDS_TO_ZERO:
        if hasattr(pe, f):
            setattr(pe, f, 0)
    for f in _FIELDS_TO_NULL:
        if hasattr(pe, f):
            setattr(pe, f, None)
    for f in _FIELDS_TO_CLEAR:
        if hasattr(pe, f):
            setattr(pe, f, "")

    # Task #82 (bug fix): recompute current_expected_submission_type so it
    # matches the archetype's week-1 WeekRule, not whatever stale value the
    # PE carried from a later week. Mirrors the normal enrollment flow at
    # program_enrollment_api._process_pe_chunk:268. Without this, Glific
    # flows fail validation (expecting word_text_voice when the week-1
    # rule actually expects image, etc.).
    if hasattr(pe, "current_expected_submission_type"):
        try:
            batch_doc = frappe.get_doc("Batch", pe.batch)
            expected = _get_week1_submission_type(
                batch_doc, pe.archetype, pe.experiment_arm,
            )
            pe.current_expected_submission_type = expected or ""
            if verbose:
                print(
                    f"  recomputed current_expected_submission_type for "
                    f"archetype={pe.archetype}, arm={pe.experiment_arm}, "
                    f"path=Core, week=1 → {expected!r}"
                )
        except Exception as e:
            # Don't fail the reset if the lookup goes sideways — leave the
            # field empty and let the operator notice via the reconcile diff.
            if verbose:
                print(
                    f"  could not recompute current_expected_submission_type: "
                    f"{e}. Setting to empty string."
                )
            pe.current_expected_submission_type = ""

    pe.save(ignore_permissions=True)

    # ── 3. CR-005: fix Glific group membership ───────────
    maintain_collections(pe, from_state=from_state, to_state=STATE_NORMAL_CONTENT)

    # ── 4. Push fresh contact fields to Glific ───────────
    # Task #83: synchronous reconcile (was: async _enqueue_contact_field_sync).
    # Matches update_student_state + reset_and_update_student behavior so the
    # test team gets immediate visibility into what landed on Glific. Returns
    # a diff so the operator can audit any drift inline.
    reconcile_result = None
    if push_to_glific and pe.glific_id:
        try:
            reconcile_result = reconcile_pe_to_glific(
                pe.name, dry_run=False, verbose=verbose,
            )
        except Exception as e:
            if verbose:
                print(f"  reconcile_pe_to_glific failed: {e}")

    # Skip commit under the test runner — FrappeTestCase relies on
    # transaction rollback for test isolation, and an explicit commit
    # here would leak this PE's reset state into the next test case.
    # In real bench/console usage, the commit is required so workers
    # see the saved state.
    if not getattr(frappe.flags, "in_test", False):
        frappe.db.commit()

    after = _snapshot(pe)
    if verbose:
        print(f"\nPE {pe_name} AFTER:")
        for k, v in after.items():
            print(f"  {k:30} = {v}")
        print(
            f"\nCR-005 group-write jobs enqueued "
            f"(from={from_state} → {STATE_NORMAL_CONTENT}). "
            f"Background workers will sync to Glific within seconds."
        )

    return {
        "before": before,
        "after": after,
        "history_deleted": history_deleted,
        # Task #83: synchronous reconcile result, so callers see the diff
        # that was pushed to Glific (or None if push was skipped).
        "reconcile": reconcile_result,
    }


# ════════════════════════════════════════════════════════════
# Bulk reset
# ════════════════════════════════════════════════════════════

def reset_pes_for_batch(
    batch_name,
    dry_run=False,
    delete_history=True,
    push_to_glific=True,
    i_know_this_is_destructive=False,
):
    """Reset every active/paused PE in a batch to state 0.

    Calls `reset_pe_to_state_0` per PE with `verbose=False` to keep output
    sane on a batch of 9+ students. Prints a one-line summary per PE and
    a totals line.

    Returns the per-PE result dicts keyed by PE name.
    """
    dry_run = _coerce_bool(dry_run)
    delete_history = _coerce_bool(delete_history)
    push_to_glific = _coerce_bool(push_to_glific)
    i_know_this_is_destructive = _coerce_bool(i_know_this_is_destructive)

    _assert_dev_site(i_know_this_is_destructive=i_know_this_is_destructive)

    frappe.db.rollback()

    rows = frappe.db.sql(
        """
            SELECT name, student FROM "tabProgramEnrollment"
             WHERE batch = %s AND program_status IN ('active', 'paused')
             ORDER BY name
        """,
        (batch_name,),
        as_dict=True,
    )

    if not rows:
        print(f"No active/paused PEs in batch {batch_name}.")
        return {}

    if dry_run:
        print(f"DRY RUN — would reset {len(rows)} PEs in batch {batch_name}:")
        for row in rows:
            print(f"  {row.name}  student={row.student}")
        return {}

    print(f"Resetting {len(rows)} PEs in batch {batch_name}…")
    results = {}
    for row in rows:
        pe_name = row.name
        try:
            pe = frappe.get_doc("ProgramEnrollment", pe_name)
            result = _reset_pe_doc_to_state_0(
                pe,
                dry_run=False,
                delete_history=delete_history,
                push_to_glific=push_to_glific,
                verbose=False,
            )
            results[pe_name] = result
            print(f"  {pe_name}  reset OK")
        except Exception as e:
            results[pe_name] = {"error": str(e)}
            print(f"  {pe_name}  FAILED: {e}")

    ok = sum(1 for r in results.values() if "error" not in r)
    print(f"\nDone — {ok}/{len(rows)} succeeded.")
    return results


# ════════════════════════════════════════════════════════════
# Student state mutation — archetype / experiment_arm / PE state
# ════════════════════════════════════════════════════════════
#
# For testing only. Lets operators update a student's archetype /
# experiment_arm (Student fields) and optionally key PE-state fields
# (program_status, current_week, current_path) in one call, then
# reconciles to Glific so contact fields land.
#
# Why this exists:
#   - Student.archetype + Student.experiment_arm are upstream-supplied
#     (CLAUDE.md). Operationally we still need to flip them during testing.
#   - Three places hold the same data: Student, ProgramEnrollment
#     (denormalized at enrollment), Glific contact fields. All three must
#     agree or the dispatcher/state-machine + Glific flows disagree on
#     what archetype the student "is".


# Task #84: source these from constants so the validation can never drift
# out of sync with the canonical enum. Previous hardcoded list had 'lurker'
# (invalid — never in ALL_ARCHETYPES) and was missing 'irregular_submitter'
# (canonical) — operators trying to flip to irregular_submitter got a
# confusing validation error.
_VALID_ARCHETYPES = tuple(ALL_ARCHETYPES)
_VALID_ARMS = tuple(ALL_ARMS)
_VALID_PROGRAM_STATUSES = ("active", "paused", "completed", "dropped")
_VALID_PATHS = ("Core", "Remedial")


@frappe.whitelist(allow_guest=False)
def update_student_state(
    student_id,
    archetype=None,
    experiment_arm=None,
    program_status=None,
    current_week=None,
    current_path=None,
    push_to_glific=True,
    dry_run=False,
    i_know_this_is_destructive=False,
):
    """Update a student's archetype / experiment_arm + optional PE state.

    Writes to:
      - Student.archetype, Student.experiment_arm
      - ProgramEnrollment.archetype, .experiment_arm (denormalized copies)
      - Optional: ProgramEnrollment.program_status, .current_week, .current_path

    After Frappe writes complete, calls reconcile_pe_to_glific to push the
    canonical state to Glific contact fields (synchronous).

    Args (all positional-or-keyword via Frappe whitelist):
        student_id: Student.name (required)
        archetype: one of fence_sitter / dormant / lurker / submitter (or None to skip)
        experiment_arm: one of default / arm_a / arm_b (or None)
        program_status: one of active / paused / completed / dropped (or None)
        current_week: int (or None)
        current_path: one of Core / Remedial (or None)
        push_to_glific: bool, default True
        dry_run: bool, default False — compute the change set without writing
        i_know_this_is_destructive: bypass production-site safety guard

    Returns:
        {
            "student_id": ..., "pe_name": ...,
            "before": {<snapshot>},
            "after": {<snapshot>},
            "applied": {<field: new_value>},
            "reconcile": <reconcile result dict>,
            "dry_run": <bool>,
        }

    Raises:
        frappe.PermissionError on suspected production site without override.
        frappe.ValidationError on invalid enum value or missing student/PE.
    """
    dry_run = _coerce_bool(dry_run)
    push_to_glific = _coerce_bool(push_to_glific)
    i_know_this_is_destructive = _coerce_bool(i_know_this_is_destructive)

    _assert_dev_site(i_know_this_is_destructive=i_know_this_is_destructive)
    frappe.db.rollback()  # PG txn hygiene

    if not frappe.db.exists("Student", student_id):
        frappe.throw(
            f"Student not found: {student_id}", frappe.ValidationError
        )

    # ── Validate enum inputs ────────────────────────────────
    if archetype is not None and archetype not in _VALID_ARCHETYPES:
        frappe.throw(
            f"Invalid archetype {archetype!r}; must be one of {_VALID_ARCHETYPES}",
            frappe.ValidationError,
        )
    if experiment_arm is not None and experiment_arm not in _VALID_ARMS:
        frappe.throw(
            f"Invalid experiment_arm {experiment_arm!r}; must be one of {_VALID_ARMS}",
            frappe.ValidationError,
        )
    if program_status is not None and program_status not in _VALID_PROGRAM_STATUSES:
        frappe.throw(
            f"Invalid program_status {program_status!r}; must be one of {_VALID_PROGRAM_STATUSES}",
            frappe.ValidationError,
        )
    if current_path is not None and current_path not in _VALID_PATHS:
        frappe.throw(
            f"Invalid current_path {current_path!r}; must be one of {_VALID_PATHS}",
            frappe.ValidationError,
        )
    if current_week is not None:
        try:
            current_week = int(current_week)
        except (TypeError, ValueError):
            frappe.throw(
                f"current_week must be an integer; got {current_week!r}",
                frappe.ValidationError,
            )

    # ── Snapshot before ─────────────────────────────────────
    student = frappe.get_doc("Student", student_id)
    pe = _get_active_pe_for_student(student_id)
    pe_name = pe.name if pe else None

    before = {
        "student.archetype": student.archetype,
        "student.experiment_arm": student.experiment_arm,
        "pe.archetype": pe.archetype if pe else None,
        "pe.experiment_arm": pe.experiment_arm if pe else None,
        "pe.program_status": pe.program_status if pe else None,
        "pe.current_week": pe.current_week if pe else None,
        "pe.current_path": pe.current_path if pe else None,
        # Task #84: surface this in the snapshot so callers can verify the
        # recompute happened (or didn't, if no week/path/archetype/arm change).
        "pe.current_expected_submission_type": (
            pe.current_expected_submission_type if pe else None
        ),
    }

    # ── Compute applied diff (only fields the caller passed) ────
    applied = {}
    student_updates = {}
    pe_updates = {}

    if archetype is not None:
        if student.archetype != archetype:
            student_updates["archetype"] = archetype
            applied["student.archetype"] = archetype
        if pe and pe.archetype != archetype:
            pe_updates["archetype"] = archetype
            applied["pe.archetype"] = archetype
    if experiment_arm is not None:
        if student.experiment_arm != experiment_arm:
            student_updates["experiment_arm"] = experiment_arm
            applied["student.experiment_arm"] = experiment_arm
        if pe and pe.experiment_arm != experiment_arm:
            pe_updates["experiment_arm"] = experiment_arm
            applied["pe.experiment_arm"] = experiment_arm
    if pe and program_status is not None and pe.program_status != program_status:
        pe_updates["program_status"] = program_status
        applied["pe.program_status"] = program_status
    if pe and current_week is not None and pe.current_week != current_week:
        pe_updates["current_week"] = current_week
        applied["pe.current_week"] = current_week
    if pe and current_path is not None and pe.current_path != current_path:
        pe_updates["current_path"] = current_path
        applied["pe.current_path"] = current_path

    # Task #84: if ANY of (current_week, current_path, archetype, experiment_arm)
    # changed, recompute current_expected_submission_type from the WeekRule
    # for the NEW combination. Without this, the field stays at whatever
    # value it had pre-update — e.g., caller fast-forwards to week=2 but
    # current_expected_submission_type is still week-1's value. Glific flows
    # would then prompt for the wrong submission type and validation fails.
    # Uses the same _get_expected_submission_type_for_week helper as the
    # enrollment flow + the reset, so all three paths agree on the rule.
    if pe and any(k in pe_updates for k in (
        "current_week", "current_path", "archetype", "experiment_arm",
    )):
        # Resolve the post-update values (use update if present, else current PE value).
        final_week = pe_updates.get("current_week", pe.current_week or 1)
        final_path = pe_updates.get("current_path", pe.current_path or PATH_CORE)
        final_archetype = pe_updates.get("archetype", pe.archetype)
        final_arm = pe_updates.get("experiment_arm", pe.experiment_arm)
        try:
            batch_doc = frappe.get_doc("Batch", pe.batch)
            new_expected = _get_expected_submission_type_for_week(
                batch_doc, final_archetype, final_arm, final_path, final_week,
            )
            new_value = new_expected or ""
            if pe.current_expected_submission_type != new_value:
                pe_updates["current_expected_submission_type"] = new_value
                applied["pe.current_expected_submission_type"] = new_value
        except Exception as e:
            # Don't fail the whole update if the lookup errors — fall back
            # to empty string so the operator notices via the reconcile diff
            # rather than seeing a stale value persist.
            pe_updates["current_expected_submission_type"] = ""
            applied["pe.current_expected_submission_type"] = (
                f"<recompute failed: {e}> — cleared to empty"
            )

    if dry_run:
        return {
            "student_id": student_id,
            "pe_name": pe_name,
            "before": before,
            "after": None,
            "applied": applied,
            "reconcile": None,
            "dry_run": True,
        }

    # ── Write ────────────────────────────────────────────────
    if student_updates:
        frappe.db.set_value("Student", student_id, student_updates)
    if pe and pe_updates:
        frappe.db.set_value("ProgramEnrollment", pe.name, pe_updates)
    frappe.db.commit()

    # ── Snapshot after ──────────────────────────────────────
    student.reload()
    if pe:
        pe.reload()
    after = {
        "student.archetype": student.archetype,
        "student.experiment_arm": student.experiment_arm,
        "pe.archetype": pe.archetype if pe else None,
        "pe.experiment_arm": pe.experiment_arm if pe else None,
        "pe.program_status": pe.program_status if pe else None,
        "pe.current_week": pe.current_week if pe else None,
        "pe.current_path": pe.current_path if pe else None,
        "pe.current_expected_submission_type": (
            pe.current_expected_submission_type if pe else None
        ),
    }

    # ── Push to Glific via reconciler ───────────────────────
    reconcile_result = None
    if push_to_glific and pe and pe.glific_id:
        reconcile_result = reconcile_pe_to_glific(
            pe.name, dry_run=False, verbose=False
        )

    return {
        "student_id": student_id,
        "pe_name": pe_name,
        "before": before,
        "after": after,
        "applied": applied,
        "reconcile": reconcile_result,
        "dry_run": False,
    }


# ════════════════════════════════════════════════════════════
# Combined: reset PE + update Student identity in one call
# ════════════════════════════════════════════════════════════


@frappe.whitelist(allow_guest=False)
def reset_and_update_student(
    student_id,
    archetype=None,
    experiment_arm=None,
    program_status=None,
    current_week=None,
    current_path=None,
    delete_history=True,
    dry_run=False,
    i_know_this_is_destructive=False,
):
    """One-shot: reset_pe_to_state_0 + update_student_state, single Glific push.

    Atomic-ish wrapper around the two existing endpoints. Use when a test
    cycle needs to restart a student from week 1 AND change their archetype
    or experiment_arm at the same time.

    Sequence:
      1. reset_pe_to_state_0(push_to_glific=False) — clears PE state-machine
         fields, counters, history; maintains Glific group memberships;
         skips contact-field push (we'll do one combined push at the end).
      2. update_student_state(push_to_glific=True) — writes new Student
         archetype/arm + optional PE state fields, then reconciles ALL
         fields to Glific in a single round-trip.

    Args mirror the two underlying functions:
        student_id: required
        archetype, experiment_arm: optional new identity (None to skip)
        program_status, current_week, current_path: optional PE-state overrides
            applied AFTER the reset (e.g., if you want the resulting PE
            to be `paused` instead of `active`, or already at week 2)
        delete_history: passed to reset_pe_to_state_0
        dry_run: bool
        i_know_this_is_destructive: production-site safety override

    Returns:
        {
            "student_id": ..., "pe_name": ...,
            "phase1_reset": <result of reset_pe_to_state_0>,
            "phase2_update": <result of update_student_state>,
            "dry_run": <bool>,
        }

    Raises:
        Same as the two underlying functions.
    """
    dry_run = _coerce_bool(dry_run)
    delete_history = _coerce_bool(delete_history)
    i_know_this_is_destructive = _coerce_bool(i_know_this_is_destructive)

    _assert_dev_site(i_know_this_is_destructive=i_know_this_is_destructive)
    frappe.db.rollback()

    # ── Phase 1: reset PE to state 0 ────────────────────────
    # push_to_glific=False — defer Glific push to phase 2 so the team only
    # pays one Glific round-trip per call.
    phase1 = reset_pe_to_state_0(
        student_id,
        dry_run=dry_run,
        delete_history=delete_history,
        push_to_glific=False,
        verbose=False,
        i_know_this_is_destructive=True,  # outer guard already passed
    )

    # ── Phase 2: update Student identity + optional PE state ────
    # push_to_glific=True — reconciles the FULL 28-field bundle to Glific
    # in one shot, picking up both the reset-cleared values AND the new
    # archetype/arm.
    phase2 = update_student_state(
        student_id,
        archetype=archetype,
        experiment_arm=experiment_arm,
        program_status=program_status,
        current_week=current_week,
        current_path=current_path,
        push_to_glific=True,
        dry_run=dry_run,
        i_know_this_is_destructive=True,  # outer guard already passed
    )

    pe_name = phase2.get("pe_name") or (phase1 or {}).get("pe_name")

    return {
        "student_id": student_id,
        "pe_name": pe_name,
        "phase1_reset": phase1,
        "phase2_update": phase2,
        "dry_run": dry_run,
    }


# ════════════════════════════════════════════════════════════
# Glific reconciliation (task #51, 2026-05-21)
# ════════════════════════════════════════════════════════════
#
# When Frappe PE state and Glific contact fields drift apart (failed sync
# job, manual data edit, parallel writer bypassing the state machine), these
# helpers rebuild the canonical 28-field bundle from PE state and push it
# synchronously to Glific. Frappe PE is the source of truth.
#
# Use cases:
#   - Post-incident cleanup after _enqueue_contact_field_sync DLQ'd (task #5).
#   - After dev_tools.reset_pe_to_state_0 if Glific has stale weekly_* values
#     the async sync hasn't drained yet.
#   - Pre-launch audit to confirm every cohort PE matches Glific.
#
# These DO NOT mutate Frappe PE state. Strictly one-way Frappe → Glific.


def reconcile_pe_to_glific(pe_name, dry_run=False, verbose=True):
    """Re-push the canonical 28-field bundle for one PE to its Glific contact.

    Synchronous (does NOT go through frappe.enqueue). Returns a dict with the
    fields that differed pre-push, so the operator can audit.

    Args:
        pe_name: ProgramEnrollment doc name.
        dry_run: If True, compute the diff but do NOT push to Glific.
        verbose: Print field-by-field diff.

    Returns: {
        "pe": <pe_name>, "glific_id": <id>,
        "diff": [{"field": ..., "frappe": ..., "glific": ...}, ...],
        "pushed": <bool>,
    }
    """
    import json
    import requests
    from tap_lms.summer_program.utils import get_student_display_name
    from tap_lms.glific_integration import (
        update_contact_fields,
        get_glific_settings,
        get_glific_auth_headers,
    )
    from tap_lms.summer_program.constants import (
        CF_STUDENT_ID, CF_BATCH_ID, CF_ARCHETYPE, CF_LANGUAGE_ID,
        CF_EXPERIMENT_ARM, CF_COURSE_LEVEL, CF_STUDENT_NAME,
        CF_RESOLVED_FLOW_STATE, CF_CURRENT_WEEK, CF_CURRENT_PATH,
        CF_CURRENT_TIER, CF_PROGRAM_STATUS, CF_TOTAL_POINTS,
        CF_CURRENT_STREAK, CF_GRACE_WINDOW_END, CF_EXPECTED_SUBMISSION,
        CF_LAST_ESCALATION_STEP, CF_SUBMISSION_COUNT,
        CF_TOTAL_ACTIVITY_POINTS, CF_WEEKLY_ACTIVITY_POINTS,
        CF_TOTAL_QUIZ_POINTS, CF_WEEKLY_QUIZ_POINTS,
        CF_TOTAL_SUBMISSION_POINTS, CF_WEEKLY_SUBMISSION_POINTS,
        CF_SPECIAL_GEMS, CF_WEEKLY_SUBMISSION_DONE,
        CF_ESCALATION_ORDER, CF_ESCALATION_TYPE,
    )

    dry_run = _coerce_bool(dry_run)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)
    if not pe.glific_id:
        if verbose:
            print(f"PE {pe_name}: no glific_id — skip")
        return {"pe": pe_name, "glific_id": None, "diff": [], "pushed": False}

    student = frappe.get_doc("Student", pe.student)
    batch = frappe.get_doc("Batch", pe.batch)

    # Mirror _process_pe_chunk's enrollment-time bundle so the reconciler
    # stays in sync with the canonical writer. If a field is added to that
    # writer, mirror it here too.
    glific_language_id = ""
    if student.language:
        glific_language_id = str(
            frappe.db.get_value("TAP Language", student.language, "glific_language_id") or ""
        )

    expected = {
        CF_STUDENT_ID: pe.student,
        CF_BATCH_ID: batch.batch_id or batch.name,
        CF_ARCHETYPE: pe.archetype or "",
        CF_LANGUAGE_ID: glific_language_id,
        CF_EXPERIMENT_ARM: pe.experiment_arm or "",
        CF_COURSE_LEVEL: pe.course_level or "",
        CF_STUDENT_NAME: get_student_display_name(student),
        CF_RESOLVED_FLOW_STATE: pe.resolved_flow_state or "",
        CF_CURRENT_WEEK: str(pe.current_week or 1),
        CF_CURRENT_PATH: pe.current_path or "Core",
        CF_CURRENT_TIER: pe.current_tier or "Basic",
        CF_PROGRAM_STATUS: pe.program_status or "active",
        CF_TOTAL_POINTS: str(pe.total_points or 0),
        CF_CURRENT_STREAK: str(pe.current_streak or 0),
        CF_GRACE_WINDOW_END: str(pe.grace_window_end_at or ""),
        CF_EXPECTED_SUBMISSION: pe.current_expected_submission_type or "",
        CF_LAST_ESCALATION_STEP: str(pe.current_escalation_step or 0),
        CF_SUBMISSION_COUNT: str(pe.submission_count or 0),
        CF_TOTAL_ACTIVITY_POINTS: str(pe.total_activity_points or 0),
        CF_WEEKLY_ACTIVITY_POINTS: str(pe.weekly_activity_points or 0),
        CF_TOTAL_QUIZ_POINTS: str(pe.total_quiz_points or 0),
        CF_WEEKLY_QUIZ_POINTS: str(pe.weekly_quiz_points or 0),
        CF_TOTAL_SUBMISSION_POINTS: str(pe.total_submission_points or 0),
        CF_WEEKLY_SUBMISSION_POINTS: str(pe.weekly_submission_points or 0),
        CF_SPECIAL_GEMS: str(pe.special_gems or 0),
        CF_WEEKLY_SUBMISSION_DONE: str(int(pe.weekly_submission_done or 0)),
        CF_ESCALATION_ORDER: str(pe.current_escalation_step or 0),
        CF_ESCALATION_TYPE: getattr(pe, "current_escalation_type", "") or "",
    }

    # Fetch Glific contact to diff
    settings = get_glific_settings()
    payload = {
        "query": "query contact($id: ID!) { contact(id: $id) { contact { id fields } } }",
        "variables": {"id": str(pe.glific_id)},
    }
    r = requests.post(f"{settings.api_url}/api", json=payload,
                      headers=get_glific_auth_headers(), timeout=15).json()
    contact = (r.get("data") or {}).get("contact", {}).get("contact") or {}
    raw_fields = contact.get("fields")
    glific_fields = json.loads(raw_fields) if isinstance(raw_fields, str) else (raw_fields or {})

    diff = []
    for k, v_expected in expected.items():
        raw = glific_fields.get(k)
        v_glific = raw.get("value") if isinstance(raw, dict) else raw
        if str(v_glific or "") != str(v_expected or ""):
            diff.append({"field": k, "frappe": v_expected, "glific": v_glific})

    if verbose:
        print(f"PE {pe_name} → Glific {pe.glific_id}")
        if not diff:
            print(f"  ✓ no mismatches")
        else:
            print(f"  ✗ {len(diff)} mismatches:")
            for d in diff:
                print(f"    {d['field']:30s} frappe={d['frappe']!r:25s} glific={d['glific']!r}")

    if not diff:
        return {"pe": pe_name, "glific_id": pe.glific_id, "diff": [], "pushed": False}

    if dry_run:
        if verbose:
            print(f"  DRY RUN — would push {len(diff)} fields")
        return {"pe": pe_name, "glific_id": pe.glific_id, "diff": diff, "pushed": False}

    # Push only the fields that differ, to minimize payload churn.
    fields_to_push = {d["field"]: d["frappe"] for d in diff}

    # Also push the CORE Glific language if the language_id field is in the diff
    # (single round-trip via the language_id kwarg).
    core_lang = glific_language_id if any(d["field"] == CF_LANGUAGE_ID for d in diff) else None
    ok = update_contact_fields(
        contact_id=pe.glific_id,
        fields_to_update=fields_to_push,
        language_id=core_lang,
    )
    if verbose:
        print(f"  pushed: {ok}")
    return {"pe": pe_name, "glific_id": pe.glific_id, "diff": diff, "pushed": bool(ok)}


def reconcile_batch_to_glific(batch_name, dry_run=False, verbose=True):
    """Reconcile every active/paused PE in a batch to Glific.

    Loops PEs and calls reconcile_pe_to_glific per row. Prints a one-line
    summary per PE plus totals at the end.

    Returns: {pe_name: <per-pe result dict>, ...}
    """
    dry_run = _coerce_bool(dry_run)

    rows = frappe.db.sql(
        """
            SELECT name, student FROM "tabProgramEnrollment"
             WHERE batch = %s AND program_status IN ('active', 'paused')
             ORDER BY name
        """,
        (batch_name,),
        as_dict=True,
    )
    if not rows:
        print(f"No active/paused PEs in batch {batch_name}.")
        return {}

    print(f"Reconciling {len(rows)} PEs in batch {batch_name} "
          f"({'DRY RUN' if dry_run else 'LIVE'})…")
    results = {}
    total_mismatches = 0
    total_pushed = 0
    for row in rows:
        try:
            result = reconcile_pe_to_glific(row.name, dry_run=dry_run, verbose=False)
            results[row.name] = result
            n = len(result["diff"])
            total_mismatches += n
            if result.get("pushed"):
                total_pushed += 1
            print(f"  {row.name}  student={row.student}  mismatches={n}  "
                  f"{'pushed' if result.get('pushed') else 'no-push'}")
        except Exception as e:
            results[row.name] = {"error": str(e)}
            print(f"  {row.name}  student={row.student}  FAILED: {e}")

    print(f"\nDone — total mismatches across {len(rows)} PEs: {total_mismatches}; "
          f"PEs pushed: {total_pushed}.")
    return results


# ════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════

def _get_active_pe_for_student(student_id):
    """Return the most recently modified active/paused PE for a student."""
    pe_name = frappe.db.get_value(
        "ProgramEnrollment",
        {
            "student": student_id,
            "program_status": ["in", [PROGRAM_ACTIVE, PROGRAM_PAUSED]],
        },
        "name",
        order_by="modified desc",
    )
    if pe_name:
        return frappe.get_doc("ProgramEnrollment", pe_name)
    return None


def _coerce_bool(value):
    """Coerce API form-string booleans while preserving existing bool callers."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _snapshot(pe):
    """Return the small subset of PE fields we care about for before/after."""
    return {
        "resolved_flow_state":      pe.resolved_flow_state,
        "journey_label":            pe.journey_label,
        "program_status":           pe.program_status,
        "current_week":             pe.current_week,
        "current_path":             pe.current_path,
        "submission_count":         pe.submission_count,
        "current_escalation_step":  pe.current_escalation_step,
        "delivery_failure_count":   pe.delivery_failure_count,
        "in_grace_window":          pe.in_grace_window,
        "next_action_at":           pe.next_action_at,
        "next_action_type":         pe.next_action_type,
    }
