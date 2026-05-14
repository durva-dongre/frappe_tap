"""
Activity-points handler (CR-002 v2).
tap_lms/summer_program/activity_points.py

Awards `VideoClass.points` to a ProgramEnrollment whenever a StudentContentLog
row is inserted that records a VideoClass completion. Wired via
`doc_events["StudentContentLog"]["after_insert"]` in hooks.py.

Design notes:

  - Per-row idempotency: `scl.points_awarded > 0` is the write-once anchor
    (P-005). Re-saves of the same SCL row are no-ops.
  - Race-tolerant counter bump: COALESCE-update SQL (P-002 / L-011) so the
    handler is immune to T19's weekly reset of `weekly_activity_points` and
    parallel writes from quiz/submission handlers.
  - First-video-of-week flag: `weekly_video_done = 1` is set idempotently
    (writing 1 to 1 is harmless). This flag is the gating signal for T19's
    streak/gem penalty branch.
  - Edge E11 (CR-002 v2): if `VideoClass.points` is 0 or null, the handler
    returns at the award-resolve step — NO PE update and NO `weekly_video_done`
    flag flip. Trade-off documented in the CR: zero-point pedagogical videos
    do not count toward "assigned this week" gating.
  - Glific sync: re-uses `_enqueue_contact_field_sync` (the same retry+DLQ
    machinery that protects every other PE→Glific write — pattern P-007).

CR-003 follow-up (2026-05-13) — grace clock arming:
  - The same UPDATE that flips `weekly_video_done` 0→1 also arms the
    per-week grace clock (`grace_window_start`, `grace_window_end_at`,
    `in_grace_window`) via atomic Postgres `CASE WHEN` clauses. Postgres
    evaluates `CASE WHEN weekly_video_done = 0 ...` against the OLD row
    state within a single UPDATE statement (standard SQL behaviour), so
    the arm only fires when this is genuinely the week's first VideoClass.
    A `grace_window_entered` ProgramEventLog row is written before the
    UPDATE, gated on the pre-UPDATE Python read of `pe.weekly_video_done`.
  - Re-arming on the next week is automatic: T19's weekly reset sets
    `weekly_video_done = 0`, so the next VideoClass completion re-trips
    the CASE WHEN and writes a fresh `grace_window_end_at`.

Test plan: see app/tap_lms/summer_program/tests/test_activity_points.py
and app/tap_lms/summer_program/tests/test_grace_logic.py.
"""
import frappe

from tap_lms.summer_program.constants import DEFAULT_GRACE_WINDOW_DAYS
from tap_lms.summer_program.state_machine import (
    _enqueue_contact_field_sync,
    get_active_pe,
)
from tap_lms.summer_program.event_log import log_event


# ════════════════════════════════════════════════════════════
# DocType-event entry point
# ════════════════════════════════════════════════════════════

def handle_content_log(doc, method=None):
    """`after_insert` hook for StudentContentLog.

    Filters to VideoClass completions only; everything else returns
    immediately. Idempotent via `doc.points_awarded > 0`.
    """
    # Filter at entry — only VideoClass completions trigger an award.
    if (doc.content_type or "") != "VideoClass":
        return
    if (doc.action or "") != "completed":
        return

    award_activity_points(doc)


# ════════════════════════════════════════════════════════════
# Core award logic
# ════════════════════════════════════════════════════════════

def award_activity_points(scl):
    """Award VideoClass.points to the student's active PE.

    Steps (per CR-002 v2 §"New module — activity_points.py" + CR-003
    follow-up 2026-05-13):
      1. Filter (handled by caller `handle_content_log`).
      2. Idempotency: skip if scl.points_awarded > 0.
      3. Resolve award: VideoClass.points → pts. Return on 0/null (E11).
      4. Resolve active PE for scl.student. Return if none.
      5a. If this is the week's first VideoClass (pre-UPDATE
          `pe.weekly_video_done == 0`), log a `grace_window_entered`
          ProgramEventLog row BEFORE the UPDATE so the audit trail captures
          the arm intent even if the UPDATE races. Resolve
          `Batch.grace_window_days` once so the CASE WHEN can use it.
      5b. Atomic UPDATE bumping total_activity_points,
          weekly_activity_points, total_points, setting weekly_video_done = 1,
          AND arming the grace clock via CASE WHEN clauses that fire iff
          weekly_video_done = 0 at UPDATE time. Postgres evaluates CASE
          against OLD row values within the same UPDATE, so the arm only
          fires for the genuine 0→1 flip.
      6. Write `scl.points_awarded` (audit-after-PE so retries are safe).
      7. Sync contact fields + log activity_points_awarded ProgramEventLog
         event.
    """
    # ── 2. Idempotency anchor (P-005) ───────────────────────
    if (scl.points_awarded or 0) > 0:
        return

    # ── 3. Resolve award ────────────────────────────────────
    if not scl.content_id:
        return

    pts = _resolve_video_points(scl.content_id)
    if not pts:
        # E11: zero-point video → no award, no `weekly_video_done` flip.
        return

    # ── 4. Resolve active PE ────────────────────────────────
    pe = get_active_pe(scl.student)
    if not pe:
        return

    # ── 5a. First-VideoClass-of-week detection (CR-003 follow-up) ──
    # Pre-UPDATE Python read; the SQL CASE WHEN in step 5b is the source
    # of truth for the atomic arm, but the Python read is a cheap and
    # consistent gate for the event-log row. If the read here is racing a
    # concurrent first-VideoClass write, both paths converge on the same
    # arm semantics — the CASE WHEN preserves the existing clock and the
    # event log may have one extra row that says "grace_window_entered"
    # with no actual arm; that's harmless and observable.
    is_first_video_of_week = not bool(pe.weekly_video_done)
    grace_window_days = _resolve_grace_window_days(pe)

    if is_first_video_of_week:
        # Log BEFORE the UPDATE so the audit row exists even if the SQL
        # raises after the log write. `grace_window_entered` is one of the
        # accepted event_type values on ProgramEventLog.
        from frappe.utils import now_datetime, add_to_date
        log_event(
            pe, "grace_window_entered",
            trigger_source="activity_points",
            details={
                "video": scl.content_id,
                "grace_days": grace_window_days,
                # Expected end timestamp the CASE WHEN should write — useful
                # for reconstructing the timeline from logs alone if the
                # PE row's grace_window_end_at gets clobbered downstream.
                "grace_window_end_at_expected": str(
                    add_to_date(now_datetime(), days=grace_window_days)
                ),
            },
        )

    # ── 5b. Atomic UPDATE on PE (P-002 / L-011 + CR-003 grace arm) ──
    # COALESCE-update is race-tolerant against T19's reset of
    # weekly_activity_points (E5) and against parallel quiz/submission writes.
    #
    # The CASE WHEN clauses fire IFF weekly_video_done = 0 at UPDATE time.
    # Postgres reads OLD row values in CASE WHEN within the same UPDATE
    # (standard SQL behaviour), so the arm only happens when this is
    # genuinely the week's first VideoClass. Second-video-same-week is a
    # no-op for the grace fields (existing values preserved).
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET total_activity_points  = COALESCE(total_activity_points, 0)  + %s,
               weekly_activity_points = COALESCE(weekly_activity_points, 0) + %s,
               total_points           = COALESCE(total_points, 0)           + %s,
               weekly_video_done      = 1,
               grace_window_start     = CASE WHEN weekly_video_done = 0
                                             THEN NOW()
                                             ELSE grace_window_start END,
               grace_window_end_at    = CASE WHEN weekly_video_done = 0
                                             THEN NOW() + (%s || ' days')::interval
                                             ELSE grace_window_end_at END,
               in_grace_window        = CASE WHEN weekly_video_done = 0
                                             THEN 1
                                             ELSE in_grace_window END
         WHERE name = %s
        """,
        (pts, pts, pts, grace_window_days, pe.name),
    )

    # ── 6. Audit-field anchor (written AFTER PE update so retries skip) ──
    frappe.db.set_value(
        "StudentContentLog", scl.name, "points_awarded", pts,
        update_modified=False,
    )

    # ── 7a. Push contact fields ────────────────────────────
    # Reload the PE so the Glific sync reflects the post-UPDATE values
    # (the local doc instance from get_active_pe still has the pre-UPDATE
    # values for the bumped columns + freshly armed grace fields).
    pe.reload()
    if pe.glific_id:
        _enqueue_contact_field_sync(pe)

    # ── 7b. ProgramEventLog ────────────────────────────────
    log_event(
        pe, "activity_points_awarded",
        new_value=str(pts),
        trigger_source="content_log",
        details={
            "scl": scl.name,
            "video": scl.content_id,
            "points": pts,
        },
    )


# ════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════

def _resolve_video_points(video_id):
    """Return VideoClass.points for the given id, or 0 if missing/zero.

    Reads via `frappe.db.get_value` (single SELECT, no full doc hydration)
    because the handler runs on every video completion across the cohort —
    keep it cheap.
    """
    try:
        pts = frappe.db.get_value("VideoClass", video_id, "points")
    except Exception:
        # Defensive: a VideoClass row missing should not crash the SCL insert.
        # Log and skip; the SCL is still recorded.
        frappe.log_error(
            f"activity_points: VideoClass {video_id} lookup failed",
            "SP Activity Points",
        )
        return 0
    return int(pts or 0)


def _resolve_grace_window_days(pe):
    """Return Batch.grace_window_days for the PE, falling back to
    DEFAULT_GRACE_WINDOW_DAYS if unset.

    Mirrors `state_machine._batch_grace_window_days` but is duplicated here
    to keep activity_points self-contained — the CASE WHEN UPDATE needs the
    integer value bound as a parameter, so we resolve it before the SQL call.
    """
    if not pe.batch:
        return DEFAULT_GRACE_WINDOW_DAYS
    try:
        days = frappe.db.get_value("Batch", pe.batch, "grace_window_days")
    except Exception:
        days = None
    if not days:
        frappe.log_error(
            f"activity_points: Batch {pe.batch} has no grace_window_days; "
            f"falling back to default ({DEFAULT_GRACE_WINDOW_DAYS}d) for PE {pe.name}",
            "SP Activity Points Grace Config",
        )
        return DEFAULT_GRACE_WINDOW_DAYS
    return int(days)
