from __future__ import annotations

import frappe

from shared.errors import StudentNotFound


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


def get_profile_scope(student_id: str) -> dict:
    student = frappe.db.get_value(
        "Student", student_id,
        ["grade", "state_id", "district_id", "school_id"], as_dict=True,
    )
    if not student:
        raise StudentNotFound(f"Student {student_id} not found")
    return {
        "state_id": student.state_id,
        "district_id": student.district_id,
        "school_id": student.school_id,
        "grade": student.grade,
    }