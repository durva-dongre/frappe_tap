"""
shared/profile/student.py  

get_profile_scope now runs its resolved assignment_id through the shared
normalize_assignment_id_for_scope() before returning it, instead of returning
the raw UnitContentItem.content value. This is the read-side fix: a client that
never passes its own assignment_id falls back to this profile-derived value,
and the Worker's gallery query binds it as-is into WHERE assignment_id = ?1 --
so it must be byte-identical to whatever normalize_assignment_id_for_scope
produced on the write side (the nightly sweep), or a space-containing
assignment_id never matches any row even though matching rows exist.
"""

from __future__ import annotations

import frappe

from shared.errors import StudentNotFound
from shared.submission.object_naming import normalize_assignment_id_for_scope


def get_profile_fields(student_id: str) -> dict:
    student = frappe.db.get_value(
        "Student",
        student_id,
        ["name1", "gender", "grade", "language", "state_id", "district_id", "school_id"],
        as_dict=True,
    )
    if not student:
        raise StudentNotFound(f"Student {student_id} not found")

    state_name = frappe.db.get_value("State", student.state_id, "state_name") if student.state_id else None
    district_name = frappe.db.get_value("District", student.district_id, "district_name") if student.district_id else None
    school_name = frappe.db.get_value("School", student.school_id, "name1") if student.school_id else None

    language_code = student.language
    if student.language:
        try:
            resolved_code = frappe.db.get_value("TAP Language", student.language, "language_code")
            if resolved_code:
                language_code = resolved_code
        except Exception:
            pass

    return {
        "student_id": student_id,
        "name1": student.name1,
        "gender": student.gender,
        "grade": student.grade,
        "language_code": language_code,
        "state_id": student.state_id,
        "district_id": student.district_id,
        "school_id": student.school_id,
        "state_name": state_name,
        "district_name": district_name,
        "school_name": school_name,
    }


def _resolve_assignment_id_for_unit(learning_unit: str) -> str | None:
    """Reverse lookup of lifecycle.resolve_learning_unit_for_assignment: given a
    unit, find the Assignment content item it owns, if any. Returns None if the
    unit has no assignment content item configured."""
    if not learning_unit:
        return None
    row = frappe.db.sql(
        """
        SELECT uci.content
          FROM "tabUnitContentItem" uci
         WHERE uci.parent = %s
           AND uci.content_type = 'Assignment'
           AND uci.content IS NOT NULL AND uci.content != ''
         LIMIT 1
        """,
        (learning_unit,),
    )
    if row and row[0][0]:
        return row[0][0]
    return None


def get_profile_scope(student_id: str) -> dict:
    """Returns the student's gallery-scoping fields, read by the Worker's
    storage/profileScope.ts. assignment_id is normalized the same way the sweep
    normalizes it on write (see module docstring) before being returned, so a
    space-containing assignment_id never silently fails to match in the
    gallery's D1 query."""
    student = frappe.db.get_value(
        "Student", student_id,
        ["grade", "state_id", "district_id", "school_id"], as_dict=True,
    )
    if not student:
        raise StudentNotFound(f"Student {student_id} not found")

    assignment_id = None
    try:
        from shared.enrollment.active_batch import get_active_program_enrollment
        from shared.enrollment.unit_rotation import next_unit_for
        from shared.progress.unit_progress import resolve_current_unit_for_track

        pe = get_active_program_enrollment(student_id)
        current_unit = resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for)
        assignment_id = _resolve_assignment_id_for_unit(current_unit)
    except StudentNotFound:
        pass

    return {
        "state_id": student.state_id,
        "district_id": student.district_id,
        "school_id": student.school_id,
        "grade": student.grade,
        "assignment_id": normalize_assignment_id_for_scope(assignment_id),
    }