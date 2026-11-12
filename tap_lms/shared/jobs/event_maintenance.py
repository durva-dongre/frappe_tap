"""
shared/jobs/event_maintenance.py

Daily sweep: closes out Event Campaigns whose end_date has passed, and
resolves every still-'active' Student Event Enrollment row against one of
those now-closed events to either 'completed' (if its Unit Progress row
shows unit_status == 'Completed') or 'missed' (otherwise).

Scheduled daily (hooks.py) -- events have day-granularity end_date, so a
once-a-day sweep is sufficient; no need for hourly.

Deliberately does NOT call rebuild_events_index() / export_event_to_r2()
directly -- those live in shared/export/event_exporter.py and are invoked
from their own doc_events hook, kept decoupled so a failure in the export
path never blocks the enrollment-status sweep, which is the part that
actually matters for student state correctness.
"""

from __future__ import annotations

import frappe

from shared.jobs._log import log_job_run


def expire_overdue_events() -> int:
    """
    1. Event Campaign rows with status in ('Published', 'On going') and
       end_date < today -> status = 'Completed' (doctype has no 'Expired'
       option; 'Completed' is the correct terminal state once the window
       has closed, regardless of how many students actually finished).
    2. For every Student Event Enrollment row still 'active' against one of
       the events just closed: resolve to 'completed' or 'missed' by
       checking whether that student's corresponding Unit Progress row
       (found via the enrollment's own `unit_progress` pointer field) shows
       unit_status == 'Completed'.
    Returns the number of Event Campaign rows transitioned (the headline
    count for the Shared Logs row).
    """
    closed_events = frappe.db.sql(
        """
        UPDATE "tabEvent Campaign"
           SET status = 'Completed', modified = NOW()
         WHERE status IN ('Published', 'On going')
           AND end_date < CURRENT_DATE
        RETURNING name
        """,
    )
    frappe.db.commit()
    closed_names = [row[0] for row in closed_events]
    if not closed_names:
        return 0

    # Student Event Enrollment is a child table (parenttype='Student'),
    # so resolve rows by parent/field directly rather than frappe.get_all
    # on a non-doctype table.
    rows = frappe.db.sql(
        """
        SELECT see.name, see.parent AS student_id, see.unit_progress
          FROM "tabStudent Event Enrollment" see
         WHERE see.event IN %(events)s
           AND see.status = 'active'
        """,
        {"events": tuple(closed_names)},
        as_dict=True,
    )

    for row in rows:
        new_status = "missed"
        if row.unit_progress:
            # unit_progress stores the Unit Progress child row's own `name`,
            # inside the student's active ProgramEnrollment.unit_progress
            # table (see shared/progress/unit_progress.py for that shape).
            up_status = frappe.db.sql(
                """
                SELECT up.unit_status
                  FROM "tabUnit Progress" up
                 WHERE up.name = %(row_name)s
                """,
                {"row_name": row.unit_progress},
            )
            if up_status and up_status[0][0] == "Completed":
                new_status = "completed"
        frappe.db.sql(
            """
            UPDATE "tabStudent Event Enrollment"
               SET status = %(status)s, modified = NOW()
             WHERE name = %(name)s
            """,
            {"status": new_status, "name": row.name},
        )
    frappe.db.commit()
    return len(closed_names)


def run() -> None:
    started = frappe.utils.now_datetime()
    try:
        count = expire_overdue_events()
        log_job_run(
            "event_maintenance", "scheduled", "success",
            started, frappe.utils.now_datetime(), count,
        )
    except Exception as exc:
        log_job_run(
            "event_maintenance", "scheduled", "failed",
            started, frappe.utils.now_datetime(), 0, {"error": str(exc)},
        )
        raise