from __future__ import annotations

import frappe

from shared.errors import InvalidInput, NotFound, StudentNotFound
from shared.progress.unit_progress import find_unit_progress_row_by_name_global, infer_last_activity_type


def _get_student_doc(student_id: str):
    try:
        return frappe.get_doc("Student", student_id)
    except frappe.DoesNotExistError:
        raise StudentNotFound()


def enroll_student_in_event(student_id: str, event_id: str) -> dict:
    event = frappe.db.get_value(
        "Event Campaign", event_id,
        ["name", "status", "start_date", "end_date"], as_dict=True,
    )
    if not event:
        raise NotFound("event does not exist")
    if event.status not in ("Published", "On going"):
        raise InvalidInput("event is not currently open for enrollment")

    today = frappe.utils.getdate()
    if not (frappe.utils.getdate(event.start_date) <= today <= frappe.utils.getdate(event.end_date)):
        raise InvalidInput("event is not currently within its active window")

    student = _get_student_doc(student_id)
    rows = list(student.event_enrollments or [])

    this_event_row = None
    is_new_enrollment = False

    for row in rows:
        if row.event == event_id:
            this_event_row = row
        elif row.status == "active":
            row.status = "missed"

    if this_event_row is None:
        this_event_row = student.append("event_enrollments", {
            "event": event_id,
            "status": "active",
            "enrolled_at": frappe.utils.now_datetime(),
            "unit_progress": "",
        })
        is_new_enrollment = True
        already_enrolled = False
    elif this_event_row.status == "active":
        already_enrolled = True
    else:
        this_event_row.status = "active"
        this_event_row.enrolled_at = frappe.utils.now_datetime()
        already_enrolled = False
        is_new_enrollment = True

    student.save(ignore_permissions=True)

    if is_new_enrollment:
        frappe.db.sql(
            """UPDATE "tabEvent Campaign" SET enrolled_count = COALESCE(enrolled_count, 0) + 1 WHERE name = %s""",
            (event_id,),
        )
        frappe.db.commit()

    return {"enrolled": True, "already_enrolled": already_enrolled}


def is_enrolled(student_id: str, event_id: str) -> dict:
    """The sole source of event-track status and resume state
    (API_Reference.md §8.2). A student's event-track Unit Progress row is
    resolved globally, by the row's own name
    (find_unit_progress_row_by_name_global), rather than by first loading
    get_active_program_enrollment(student_id) and searching that doc's
    unit_progress table -- because a Unit Progress row is immutably tied
    to whichever ProgramEnrollment it was created under, not to whatever
    enrollment happens to be "active" right now. If the student's active
    enrollment has since changed (e.g. they started a new course-level
    enrollment after making progress on this event), a lookup scoped to
    "the active enrollment" would fail to find the row and would report
    the event's default starting unit instead of the student's real
    progress. shared/progress/activities.py's write path
    (_resolve_event_unit_progress_row) anchors event-context writes to
    this same global resolution, so the two stay in agreement: whatever
    row this function finds for a read is the same row a write for that
    event will update."""
    student = _get_student_doc(student_id)
    rows = [r for r in (student.event_enrollments or []) if r.event == event_id]
    if not rows:
        return {"enrolled": False, "last_activity_type": None, "current_event_learning_unit": None}

    rows.sort(key=lambda r: r.idx, reverse=True)
    row = rows[0]
    enrolled = row.status == "active"

    if not row.unit_progress:
        unit = frappe.db.get_value("Event Campaign", event_id, "learning_unit")
        return {"enrolled": enrolled, "last_activity_type": None, "current_event_learning_unit": unit}

    up_row = find_unit_progress_row_by_name_global(row.unit_progress)
    if not up_row:
        unit = frappe.db.get_value("Event Campaign", event_id, "learning_unit")
        return {"enrolled": enrolled, "last_activity_type": None, "current_event_learning_unit": unit}

    return {
        "enrolled": enrolled,
        "last_activity_type": infer_last_activity_type(up_row),
        "current_event_learning_unit": up_row["learning_unit"],
    }