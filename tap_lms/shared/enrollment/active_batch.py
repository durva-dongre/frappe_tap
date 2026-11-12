from __future__ import annotations

import frappe

from shared.errors import StudentNotFound

PROGRAM_ENROLLMENT_TABLE = "tabProgramEnrollment"

_PRIORITY_STATUSES = ("active", "default")
_TERMINAL_STATUSES = ("dropped", "completed")


def get_active_program_enrollment_name(student_id: str, doctype_table: str = PROGRAM_ENROLLMENT_TABLE) -> str:
    rows = frappe.db.sql(
        f"""
        SELECT name, status
        FROM "{doctype_table}"
        WHERE student = %s
        ORDER BY modified DESC
        """,
        (student_id,),
        as_dict=True,
    )
    if not rows:
        raise StudentNotFound("No ProgramEnrollment found for this student")

    for wanted in _PRIORITY_STATUSES:
        for row in rows:
            if row.status == wanted:
                return row.name

    for row in rows:
        if row.status not in _TERMINAL_STATUSES:
            return row.name

    raise StudentNotFound("Student has no active enrollment")


def get_active_program_enrollment(student_id: str):
    name = get_active_program_enrollment_name(student_id)
    return frappe.get_doc("ProgramEnrollment", name)