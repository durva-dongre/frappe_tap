from __future__ import annotations

import frappe

from shared.jobs._log import log_job_run


def reset_weekly_activity() -> int:
    result = frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET activity_this_week = 0, modified = NOW()
         WHERE activity_this_week != 0
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