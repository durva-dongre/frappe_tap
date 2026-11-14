from __future__ import annotations

import frappe

from shared.jobs._log import log_job_run


def reset_weekly_activity() -> int:
    """Resets ProgramEnrollment.submission_this_week to 0 for every
    enrollment that currently has a nonzero value. this job only ever zeroes the column, it does
    not care how it got incremented."""
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


def run() -> None:
    started = frappe.utils.now_datetime()
    try:
        count = reset_weekly_activity()
        log_job_run(
            "student_maintenance", "weekly_reset", "success",
            started, frappe.utils.now_datetime(), count,
        )
    except Exception as exc:
        log_job_run(
            "student_maintenance", "weekly_reset", "failed",
            started, frappe.utils.now_datetime(), 0, {"error": str(exc)},
        )
        raise