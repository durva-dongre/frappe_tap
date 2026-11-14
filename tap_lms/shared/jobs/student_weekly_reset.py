"""
shared/jobs/student_weekly_reset.py

Weekly reset of ProgramEnrollment.submission_this_week back to 0. Called
by nightly_pipeline.py only when the run date is a Sunday (IST) -- this
module itself has no day-of-week logic; it always resets on every call.
"""

from __future__ import annotations

import frappe

from shared.jobs._log import log_job_run


def reset_weekly_activity() -> int:
    """Resets ProgramEnrollment.submission_this_week to 0 for every
    enrollment that currently has a nonzero value. This job only ever
    zeroes the column; it does not care how it got incremented."""
    result = frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET submission_this_week = 0, modified = NOW()
         WHERE submission_this_week != 0
        RETURNING name
        """
    )
    frappe.db.commit()
    return len(result)


def run() -> dict:
    started = frappe.utils.now_datetime()
    try:
        count = reset_weekly_activity()
        log_job_run(
            "student_weekly_reset", "weekly_reset", "success",
            started, frappe.utils.now_datetime(), count,
        )
        return {"status": "success", "reset_count": count}
    except Exception as exc:
        log_job_run(
            "student_weekly_reset", "weekly_reset", "failed",
            started, frappe.utils.now_datetime(), 0, {"error": str(exc)},
        )
        return {"status": "failed", "reset_count": 0, "error": str(exc)}