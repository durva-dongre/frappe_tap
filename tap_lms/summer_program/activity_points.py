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

Test plan: see app/tap_lms/summer_program/tests/test_activity_points.py.
"""
import frappe

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

    Steps (per CR-002 v2 §"New module — activity_points.py"):
      1. Filter (handled by caller `handle_content_log`).
      2. Idempotency: skip if scl.points_awarded > 0.
      3. Resolve award: VideoClass.points → pts. Return on 0/null (E11).
      4. Resolve active PE for scl.student. Return if none.
      5. Atomic UPDATE bumping total_activity_points,
         weekly_activity_points, total_points, and setting
         weekly_video_done = 1.
      6. Write `scl.points_awarded` (audit-after-PE so retries are safe).
      7. Sync contact fields + log ProgramEventLog event.
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

    # ── 5. Atomic UPDATE on PE (P-002 / L-011) ──────────────
    # COALESCE-update is race-tolerant against T19's reset of
    # weekly_activity_points (E5) and against parallel quiz/submission writes.
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET total_activity_points  = COALESCE(total_activity_points, 0)  + %s,
               weekly_activity_points = COALESCE(weekly_activity_points, 0) + %s,
               total_points           = COALESCE(total_points, 0)           + %s,
               weekly_video_done      = 1
         WHERE name = %s
        """,
        (pts, pts, pts, pe.name),
    )

    # ── 6. Audit-field anchor (written AFTER PE update so retries skip) ──
    frappe.db.set_value(
        "StudentContentLog", scl.name, "points_awarded", pts,
        update_modified=False,
    )

    # ── 7a. Push contact fields ────────────────────────────
    # Reload the PE so the Glific sync reflects the post-UPDATE values
    # (the local doc instance from get_active_pe still has the pre-UPDATE
    # values for the bumped columns).
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
