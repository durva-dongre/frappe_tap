from __future__ import annotations

import frappe

from shared.errors import StudentNotFound

PROGRAM_ENROLLMENT_TABLE = "tabProgramEnrollment"

_PRIORITY_STATUSES = ("active", "default")
_TERMINAL_STATUSES = ("dropped", "completed")
# Terminal statuses that are still safe to resolve for READ paths (sync,
# profile, last_submission). A student whose only enrollment is completed
# must still be able to see their final state (points, last unit, last
# submission) -- raising StudentNotFound here was breaking /progress/sync,
# /auth/redeem, /auth/select_profile, get_profile, and get_profile_scope
# the moment a student's only ProgramEnrollment became "completed".
#
# "dropped" is deliberately excluded from this fallback: a dropped
# enrollment is not a finished, readable state the way "completed" is --
# it's an abandoned one, and the existing StudentNotFound behavior for it
# is correct and unchanged.
#
# Write paths (submit_artwork, submit_video_watched, submit_quiz) must NOT
# rely on this fallback to silently resume writing against a finished
# course -- see shared/submission/lifecycle.py and
# tap_lms/tap_app/api/progress.py, which explicitly check
# pe.status == "completed" and reject with InvalidInput before any write
# happens. This function only widens what can be READ; it does not by
# itself re-open writing.
_READABLE_TERMINAL_STATUSES = ("completed",)


def get_active_program_enrollment_name(student_id: str, doctype_table: str = PROGRAM_ENROLLMENT_TABLE) -> str:
    """Resolves the one ProgramEnrollment name a caller should read or
    write against for this student.

    Resolution order:
      1. "active", then "default" -- the normal, in-progress case.
      2. Any row not in a terminal status (paused, no_activity, manual).
      3. A "completed" row, as a READ-ONLY fallback (see
         _READABLE_TERMINAL_STATUSES above) -- so a student whose only
         enrollment has finished can still have their final state read.
      4. Otherwise (every row is "dropped", or there are no rows at all),
         raise StudentNotFound -- unchanged from before.

    NOTE: a student can have multiple ProgramEnrollment rows across
    different course levels, and in principle more than one could be
    "active" simultaneously. Where more than one candidate exists at the
    same priority tier, this function returns the one with the latest
    `modified` (rows are queried `ORDER BY modified DESC`), since that is
    the most recently touched enrollment. Callers working with a student
    enrolled in multiple course levels at once should not assume this
    picks a specific course level; it picks the most recently active one.
    """
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

    for row in rows:
        if row.status in _READABLE_TERMINAL_STATUSES:
            return row.name

    raise StudentNotFound("Student has no active enrollment")


def get_active_program_enrollment(student_id: str):
    name = get_active_program_enrollment_name(student_id)
    return frappe.get_doc("ProgramEnrollment", name)