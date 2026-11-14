"""
shared/jobs/nightly_pipeline.py

Single cron entrypoint for every nightly job. Order matters: the three
sub-jobs run first so their outcomes can be folded into the analytics
sheet row, which is written last (before the final retention cleanup).

1. event_daily_sweep.run() -- every night, unconditional.
2. student_weekly_reset.run() -- only on Sunday (IST).
3. rebuild_events_index() -- only if step 1 actually closed something.
4. gallery_promotion_sweep.run() -- every night, unconditional, independent
   of the above.
5. analytics_daily.run(pipeline_context) -- folds in the outcomes of 1-4.
6. Shared Logs retention cleanup -- runs last, after every other job has
   already written tonight's own log row, so tonight's rows are never at
   risk of being swept up by the cleanup itself.
7. Final orchestrator-level log_job_run summarizing overall status.
"""

from __future__ import annotations

import frappe

from shared.jobs._log import log_job_run
from shared.jobs import event_daily_sweep, student_weekly_reset, gallery_promotion_sweep, analytics_daily
from shared.config.secrets_cache import get_shared_logs_retention_days

try:
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo("Asia/Kolkata")
except Exception:
    import pytz
    _IST = pytz.timezone("Asia/Kolkata")


def _is_sunday_ist() -> bool:
    from datetime import datetime
    return datetime.now(_IST).weekday() == 6  # Monday=0 ... Sunday=6


def _cleanup_shared_logs() -> int:
    retention_days = get_shared_logs_retention_days()
    result = frappe.db.sql(
        """
        DELETE FROM "tabShared Logs"
         WHERE log_date < CURRENT_DATE - (%(days)s || ' days')::interval
        RETURNING name
        """,
        {"days": retention_days},
    )
    frappe.db.commit()
    return len(result)


def run() -> dict:
    started = frappe.utils.now_datetime()
    notes: list[str] = []

    # ── 1. Event daily sweep (unconditional) ─────────────────────────────
    event_result = event_daily_sweep.run()
    event_daily_sweep_ran = event_result.get("status") == "success"
    events_closed = event_result.get("events_closed", 0)
    if not event_daily_sweep_ran:
        notes.append(f"event_daily_sweep failed: {event_result.get('error')}")

    # ── 2. Student weekly reset (Sunday only) ────────────────────────────
    student_weekly_reset_ran = False
    if _is_sunday_ist():
        reset_result = student_weekly_reset.run()
        student_weekly_reset_ran = reset_result.get("status") == "success"
        if not student_weekly_reset_ran:
            notes.append(f"student_weekly_reset failed: {reset_result.get('error')}")

    # ── 3. Rebuild events index, only if step 1 closed anything ─────────
    if events_closed > 0:
        try:
            from shared.export.event_exporter import rebuild_events_index
            rebuild_events_index()
        except Exception as exc:
            notes.append(f"rebuild_events_index failed: {exc}")
            frappe.logger().warning("nightly_pipeline: rebuild_events_index failed", exc_info=True)

    # ── 4. Gallery promotion sweep (unconditional) ───────────────────────
    gallery_result = gallery_promotion_sweep.run()
    gallery_promotion_sweep_ran = gallery_result.get("status") == "success"
    if not gallery_promotion_sweep_ran:
        notes.append(f"gallery_promotion_sweep failed: {gallery_result.get('error')}")

    # ── 5. Analytics rollup, folding in the above outcomes ───────────────
    pipeline_context = {
        "events_closed": events_closed,
        "gallery_r2_promoted": gallery_result.get("r2_promoted", 0),
        "gallery_remaining_backlog": gallery_result.get("remaining_backlog_estimate", 0),
        "gallery_d1_chunks_failed": gallery_result.get("d1_chunks_failed", 0),
        "student_weekly_reset_ran": student_weekly_reset_ran,
        "event_daily_sweep_ran": event_daily_sweep_ran,
        "gallery_promotion_sweep_ran": gallery_promotion_sweep_ran,
        "job_status": "degraded" if notes else "success",
        "notes": "; ".join(notes),
    }
    analytics_result = analytics_daily.run(pipeline_context)

    # ── 6. Shared Logs retention cleanup (last, after tonight's own rows) ─
    try:
        purged = _cleanup_shared_logs()
    except Exception as exc:
        purged = 0
        notes.append(f"shared_logs cleanup failed: {exc}")
        frappe.logger().warning("nightly_pipeline: shared_logs cleanup failed", exc_info=True)

    overall_status = "degraded" if notes else "success"

    # ── 7. Orchestrator-level summary log row ────────────────────────────
    log_job_run(
        "nightly_pipeline", "orchestrator", overall_status,
        started, frappe.utils.now_datetime(), 1,
        {
            "event_daily_sweep_ran": event_daily_sweep_ran,
            "student_weekly_reset_ran": student_weekly_reset_ran,
            "gallery_promotion_sweep_ran": gallery_promotion_sweep_ran,
            "shared_logs_purged": purged,
            "notes": notes,
        },
    )

    return {
        "status": overall_status,
        "event_daily_sweep": event_result,
        "student_weekly_reset_ran": student_weekly_reset_ran,
        "gallery_promotion_sweep": gallery_result,
        "analytics": analytics_result,
        "shared_logs_purged": purged,
        "notes": notes,
    }