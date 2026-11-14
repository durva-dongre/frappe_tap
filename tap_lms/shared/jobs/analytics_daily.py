"""
shared/jobs/analytics_daily.py

Computes the prior day's metrics (IST calendar day) and writes one row to
the configured Google Sheet, via a Google Apps Script Web App endpoint
(Shared Settings.analytics_apps_script_url /
analytics_apps_script_shared_secret). Idempotent per analysis_date: finds
an existing row for the date first and updates it in place rather than
appending a duplicate, so a retried/re-run pipeline never double-writes a
day's row.

Column order and sourcing match the full accounting worked out for this
job -- see the design doc. Several columns are approximations (noted
inline) because this project's "no doctype changes except Shared Settings"
constraint rules out an event-sourced activity log; those columns are
computed from the best available proxy (usually Frappe's own `modified`
timestamp) rather than silently reported as exact.

auto_activated_enrollments is NOT a column at all -- there is no way to
reconstruct "how many auto-activations happened today" after the fact
without a new field or a log table, both out of scope here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import frappe
import requests

from shared.config.secrets_cache import (
    get_analytics_apps_script_url,
    get_analytics_apps_script_shared_secret,
    get_analytics_sheet_tab_name,
    get_worker_internal_api_timeout_seconds,
)
from shared.progress.rewards import (
    points_for_video,
    points_per_quiz_correct,
    points_for_submission_first_attempt,
    points_for_submission_review_valid,
    gems_for_submission_review_valid,
)
from shared.jobs._log import log_job_run

try:
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo("Asia/Kolkata")
except Exception:
    import pytz
    _IST = pytz.timezone("Asia/Kolkata")

_APPS_SCRIPT_TIMEOUT_SECONDS = 15

# Column order written to the sheet -- keep this in sync with
# compute_daily_analytics's returned dict keys.
_COLUMN_ORDER = [
    "analysis_date", "run_at",
    "new_students", "active_students_program", "active_students_event",
    "video_activity_count", "quiz_attempt_count",
    "submission_count_total", "submission_success_original",
    "submission_success_flagged", "submission_failed",
    "units_completed", "courses_completed",
    "points_awarded_total", "gems_awarded_total",
    "new_enrollments", "reactivated_enrollments", "new_event_enrollments",
    "events_closed", "avg_review_turnaround_minutes",
    "gallery_r2_promoted_today", "gallery_remaining_backlog", "gallery_d1_chunks_failed",
    "student_weekly_reset_ran", "event_daily_sweep_ran", "gallery_promotion_sweep_ran",
    "job_status", "notes",
]


def _resolve_analysis_date() -> date:
    """Yesterday's calendar date, in IST, regardless of server timezone
    config -- IST is hardcoded here deliberately rather than trusted from
    system settings."""
    now_ist = datetime.now(_IST)
    return (now_ist - timedelta(days=1)).date()


def _window_bounds(analysis_date: date) -> tuple[datetime, datetime]:
    """Returns (start, end) datetimes, in naive local time matching
    Frappe's own stored datetime convention, spanning the full IST
    calendar day of analysis_date."""
    start_ist = datetime.combine(analysis_date, datetime.min.time(), tzinfo=_IST)
    end_ist = start_ist + timedelta(days=1)
    return start_ist.replace(tzinfo=None), end_ist.replace(tzinfo=None)


def compute_daily_analytics(analysis_date: date, pipeline_context: dict | None = None) -> dict:
    """Computes every column for one day. pipeline_context, when supplied
    by nightly_pipeline.py, carries outcomes from the other nightly jobs
    (job-ran booleans, events_closed, gallery sweep numbers) that this
    function has no visibility into on its own."""
    ctx = pipeline_context or {}
    start, end = _window_bounds(analysis_date)

    data: dict = {
        "analysis_date": analysis_date.isoformat(),
        "run_at": frappe.utils.now_datetime().isoformat(),
    }

    data["new_students"] = _scalar(
        """SELECT COUNT(*) FROM "tabStudent" WHERE creation >= %(start)s AND creation < %(end)s""",
        start, end,
    )

    data["active_students_program"] = _scalar(
        """SELECT COUNT(DISTINCT student) FROM "tabProgramEnrollment"
           WHERE last_activity_at >= %(start)s AND last_activity_at < %(end)s""",
        start, end,
    )

    # Approximate: event-track activity has no centrally-stored timestamp
    # the way program-track last_activity_at is; proxied via Unit Progress
    # rows' own `modified` for unit_type='event' rows.
    data["active_students_event"] = _scalar(
        """SELECT COUNT(DISTINCT see.parent) FROM "tabStudent Event Enrollment" see
           JOIN "tabUnit Progress" up ON up.name = see.unit_progress
           WHERE up.unit_type = 'event' AND up.modified >= %(start)s AND up.modified < %(end)s""",
        start, end,
    )

    # Approximate: video_watched/quiz-graded flips have no dedicated
    # timestamp field; proxied via Unit Progress.modified.
    data["video_activity_count"] = _scalar(
        """SELECT COUNT(*) FROM "tabUnit Progress"
           WHERE video_watched = 1 AND modified >= %(start)s AND modified < %(end)s""",
        start, end,
    )
    data["quiz_attempt_count"] = _scalar(
        """SELECT COUNT(*) FROM "tabUnit Progress"
           WHERE quiz_json IS NOT NULL AND quiz_json::text LIKE '%%"graded": true%%'
             AND modified >= %(start)s AND modified < %(end)s""",
        start, end,
    )

    data["submission_count_total"] = _scalar(
        """SELECT COUNT(*) FROM "tabSubmission" WHERE created_at >= %(start)s AND created_at < %(end)s""",
        start, end,
    )
    data["submission_success_original"] = _scalar(
        """SELECT COUNT(*) FROM "tabSubmission"
           WHERE result_status = 'Success - Original' AND status = 'Completed'
             AND completed_at >= %(start)s AND completed_at < %(end)s""",
        start, end,
    )
    data["submission_success_flagged"] = _scalar(
        """SELECT COUNT(*) FROM "tabSubmission"
           WHERE result_status = 'Success - Flagged' AND status = 'Completed'
             AND completed_at >= %(start)s AND completed_at < %(end)s""",
        start, end,
    )
    data["submission_failed"] = _scalar(
        """SELECT COUNT(*) FROM "tabSubmission"
           WHERE result_status = 'Failed' AND status = 'Completed'
             AND completed_at >= %(start)s AND completed_at < %(end)s""",
        start, end,
    )

    # Exact -- completed_at is reliably set by recompute_unit_status(_by_name).
    data["units_completed"] = _scalar(
        """SELECT COUNT(*) FROM "tabUnit Progress" WHERE completed_at >= %(start)s AND completed_at < %(end)s""",
        start, end,
    )
    # Approximate -- no dedicated completed_at field on ProgramEnrollment.
    data["courses_completed"] = _scalar(
        """SELECT COUNT(*) FROM "tabProgramEnrollment"
           WHERE status = 'completed' AND modified >= %(start)s AND modified < %(end)s""",
        start, end,
    )

    # Reconstructed from reward-amount accessors x the day's counts -- no
    # event-sourced ledger exists.
    points_total = (
        data["video_activity_count"] * points_for_video()
        + data["quiz_attempt_count"] * points_per_quiz_correct()
        + data["submission_count_total"] * 0  # first-attempt bonus not separately counted here
        + data["submission_success_original"] * points_for_submission_review_valid()
    )
    data["points_awarded_total"] = points_total
    data["gems_awarded_total"] = data["submission_success_original"] * gems_for_submission_review_valid()

    # Exact -- `creation` on a reactivated row stays at its original value.
    data["new_enrollments"] = _scalar(
        """SELECT COUNT(*) FROM "tabProgramEnrollment" WHERE creation >= %(start)s AND creation < %(end)s""",
        start, end,
    )
    # Approximate -- modified bumps on any field change, not specifically status.
    data["reactivated_enrollments"] = _scalar(
        """SELECT COUNT(*) FROM "tabProgramEnrollment"
           WHERE status = 'active' AND modified >= %(start)s AND modified < %(end)s
             AND NOT (creation >= %(start)s AND creation < %(end)s)""",
        start, end,
    )
    # Exact -- enrolled_at is a real, dedicated field.
    data["new_event_enrollments"] = _scalar(
        """SELECT COUNT(*) FROM "tabStudent Event Enrollment"
           WHERE enrolled_at >= %(start)s AND enrolled_at < %(end)s""",
        start, end,
    )

    data["events_closed"] = ctx.get("events_closed", 0)

    turnaround = frappe.db.sql(
        """SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at)) / 60)
             FROM "tabSubmission" WHERE completed_at >= %(start)s AND completed_at < %(end)s""",
        {"start": start, "end": end},
    )
    data["avg_review_turnaround_minutes"] = round(turnaround[0][0], 1) if turnaround and turnaround[0][0] is not None else None

    data["gallery_r2_promoted_today"] = ctx.get("gallery_r2_promoted", 0)
    data["gallery_remaining_backlog"] = ctx.get("gallery_remaining_backlog", 0)
    data["gallery_d1_chunks_failed"] = ctx.get("gallery_d1_chunks_failed", 0)

    data["student_weekly_reset_ran"] = ctx.get("student_weekly_reset_ran", False)
    data["event_daily_sweep_ran"] = ctx.get("event_daily_sweep_ran", False)
    data["gallery_promotion_sweep_ran"] = ctx.get("gallery_promotion_sweep_ran", False)

    data["job_status"] = ctx.get("job_status", "success")
    data["notes"] = ctx.get("notes", "")

    return data


def _scalar(query: str, start, end) -> int:
    result = frappe.db.sql(query, {"start": start, "end": end})
    return int(result[0][0] or 0) if result else 0


def _sheet_row_for(data: dict) -> list:
    return [data.get(col) for col in _COLUMN_ORDER]


def _apps_script_call(action: str, payload: dict) -> dict:
    url = get_analytics_apps_script_url()
    secret = get_analytics_apps_script_shared_secret()
    body = {"secret": secret, "action": action, **payload}
    resp = requests.post(url, json=body, timeout=_APPS_SCRIPT_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json() or {}


def _find_existing_row_index(analysis_date: date) -> int | None:
    result = _apps_script_call("find", {
        "tab": get_analytics_sheet_tab_name(),
        "analysis_date": analysis_date.isoformat(),
    })
    if result.get("found"):
        return result.get("row")
    return None


def write_analytics_row(row_values: list, analysis_date: date) -> None:
    existing_row = _find_existing_row_index(analysis_date)
    tab = get_analytics_sheet_tab_name()
    if existing_row is not None:
        _apps_script_call("update", {"tab": tab, "row": existing_row, "row_values": row_values})
    else:
        _apps_script_call("append", {"tab": tab, "row_values": row_values})


def run(pipeline_context: dict | None = None) -> dict:
    started = frappe.utils.now_datetime()
    analysis_date = _resolve_analysis_date()

    try:
        data = compute_daily_analytics(analysis_date, pipeline_context)
        row_values = _sheet_row_for(data)

        sheet_write_failed = False
        try:
            write_analytics_row(row_values, analysis_date)
        except Exception as sheet_exc:
            sheet_write_failed = True
            data["job_status"] = "failed"
            data["notes"] = (data.get("notes") or "") + f"; sheet write failed: {sheet_exc}"
            frappe.logger().warning("analytics_daily: sheet write failed", exc_info=True)

        log_job_run(
            "analytics_daily", "rollup",
            "failed" if sheet_write_failed else "success",
            started, frappe.utils.now_datetime(), 1, data,
        )
        return data
    except Exception as exc:
        log_job_run(
            "analytics_daily", "rollup", "failed",
            started, frappe.utils.now_datetime(), 0, {"error": str(exc)},
        )
        return {"status": "failed", "error": str(exc)}