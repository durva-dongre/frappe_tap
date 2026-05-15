"""
Summer Program — dev / test reset helpers.

Tools for re-running a student (or all students in a batch) through the SP
journey from state 0. Used during integration testing where the same dev
contacts need to be cycled through many times.

**USE FOR DEV/TEST ONLY.** Every function in this module DESTROYS journey
history (Submission / StudentQuizAttempt / StudentContentLog /
ProgramEventLog rows). A safety guard refuses to run on sites whose name
suggests a production environment unless the caller explicitly opts in.

Usage from `bench execute`:

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.list_pes_for_batch \\
        --kwargs '{"batch_name": "palv2-test-BT52231"}'

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.reset_pe_to_state_0 \\
        --kwargs '{"pe_name": "h2i6sbirph", "dry_run": true}'

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.reset_pe_to_state_0 \\
        --kwargs '{"pe_name": "h2i6sbirph"}'

    bench --site tap_lms.dev execute \\
        tap_lms.summer_program.dev_tools.reset_pes_for_batch \\
        --kwargs '{"batch_name": "palv2-test-BT52231"}'

Usage from `bench console`:

    >>> from tap_lms.summer_program.dev_tools import reset_pe_to_state_0
    >>> reset_pe_to_state_0("h2i6sbirph", dry_run=True)
    >>> reset_pe_to_state_0("h2i6sbirph")
"""
import frappe

from tap_lms.summer_program.constants import (
    STATE_NORMAL_CONTENT,
    LABEL_ENROLLED,
    PROGRAM_ACTIVE,
    PATH_CORE,
)
# Hoisted at module level so tests can patch at the canonical location
# `tap_lms.summer_program.dev_tools.{maintain_collections,_enqueue_contact_field_sync}`
# without depending on Python's late-binding behaviour for inline imports.
from tap_lms.summer_program.collection_membership import maintain_collections
from tap_lms.summer_program.state_machine import _enqueue_contact_field_sync


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
    # CR-002 v2 gamification
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
_FIELDS_TO_CLEAR = (
    "next_action_type",
    "drop_reason",
)

# Historical/audit rows to delete when delete_history=True.
# Tuple shape: (doctype, FK field name ON that doctype, source-key — either
# 'student' to fill with pe.student, or 'pe_name' to fill with the PE name).
# FK names verified against the doctype JSONs (2026-05-16):
#   - Submission.program_enrollment is a Link to ProgramEnrollment
#   - StudentQuizAttempt.student / StudentContentLog.student are Link to Student
#   - ProgramEventLog.enrollment is the PE link (NOT 'program_enrollment')
_HISTORY_DOCTYPES = (
    ("Submission",         "program_enrollment", "pe_name"),
    ("StudentQuizAttempt", "student",            "student"),
    ("StudentContentLog",  "student",            "student"),
    ("ProgramEventLog",    "enrollment",         "pe_name"),
)


def reset_pe_to_state_0(
    pe_name,
    dry_run=False,
    delete_history=True,
    push_to_glific=True,
    verbose=True,
    i_know_this_is_destructive=False,
):
    """Reset a single ProgramEnrollment to its initial post-enrollment state.

    Resets:
      - PE state machine fields → state 0 (normal_content_delivery, week 1,
        Core path, enrolled label, active status)
      - All counters → 0
      - Grace window → cleared
      - CR-002 v2 gamification points (weekly + total) → 0
      - Sticky weekly flags → 0
      - Scheduler pointers (next_action_at, next_action_type) → cleared

    Optionally:
      - Deletes journey history (Submission/StudentQuizAttempt/StudentContentLog/
        ProgramEventLog rows) when `delete_history=True` (default).
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
        pe_name: ProgramEnrollment.name (e.g. 'h2i6sbirph')
        dry_run: if True, print intended changes without writing
        delete_history: if True, delete journey audit rows for this student
        push_to_glific: if True, enqueue a contact-field sync job
        verbose: if True, print before/after snapshot
        i_know_this_is_destructive: bypass the production-site safety guard

    Returns:
        dict with `before` and `after` snapshots, plus `history_deleted` counts.

    Raises:
        frappe.PermissionError if site name suggests production.
        frappe.DoesNotExistError if pe_name is invalid.
    """
    _assert_dev_site(i_know_this_is_destructive=i_know_this_is_destructive)

    frappe.db.rollback()  # PG txn hygiene

    pe = frappe.get_doc("ProgramEnrollment", pe_name)
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

    pe.save(ignore_permissions=True)

    # ── 3. CR-005: fix Glific group membership ───────────
    maintain_collections(pe, from_state=from_state, to_state=STATE_NORMAL_CONTENT)

    # ── 4. Push fresh contact fields to Glific ───────────
    if push_to_glific and pe.glific_id:
        try:
            _enqueue_contact_field_sync(pe)
            if verbose:
                print(f"  enqueued Glific contact-field sync (glific_id={pe.glific_id})")
        except Exception as e:
            if verbose:
                print(f"  could not enqueue Glific sync: {e}")

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
    _assert_dev_site(i_know_this_is_destructive=i_know_this_is_destructive)

    frappe.db.rollback()

    pe_names = [
        r[0] for r in frappe.db.sql(
            """
            SELECT name FROM "tabProgramEnrollment"
             WHERE batch = %s AND program_status IN ('active', 'paused')
             ORDER BY name
            """,
            (batch_name,),
        )
    ]

    if not pe_names:
        print(f"No active/paused PEs in batch {batch_name}.")
        return {}

    if dry_run:
        print(f"DRY RUN — would reset {len(pe_names)} PEs in batch {batch_name}:")
        for n in pe_names:
            print(f"  {n}")
        return {}

    print(f"Resetting {len(pe_names)} PEs in batch {batch_name}…")
    results = {}
    for pe_name in pe_names:
        try:
            result = reset_pe_to_state_0(
                pe_name,
                dry_run=False,
                delete_history=delete_history,
                push_to_glific=push_to_glific,
                verbose=False,
                # Already passed the gate at function entry.
                i_know_this_is_destructive=i_know_this_is_destructive,
            )
            results[pe_name] = result
            print(f"  {pe_name}  reset OK")
        except Exception as e:
            results[pe_name] = {"error": str(e)}
            print(f"  {pe_name}  FAILED: {e}")

    ok = sum(1 for r in results.values() if "error" not in r)
    print(f"\nDone — {ok}/{len(pe_names)} succeeded.")
    return results


# ════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════

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
