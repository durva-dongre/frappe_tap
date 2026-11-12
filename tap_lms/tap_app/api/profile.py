from __future__ import annotations

from tap_lms.tap_app.api import tap_app_method
from shared.profile import student as student_profile
from shared.enrollment.active_batch import get_active_program_enrollment


@tap_app_method
def get_profile(student_id: str):
    fields = student_profile.get_profile_fields(student_id)
    pe = get_active_program_enrollment(student_id)
    return {
        "student_id": student_id,
        "name1": fields["name1"],
        "gender": fields["gender"],
        "language": fields["language_code"],
        "grade": fields["grade"],
        "course_id": pe.course_level,
        "state_id": fields["state_id"],
        "district_id": fields["district_id"],
        "school_id": fields["school_id"],
        "state_name": fields["state_name"],
        "district_name": fields["district_name"],
        "school_name": fields["school_name"],
    }


@tap_app_method
def get_profile_scope(student_id: str):
    return student_profile.get_profile_scope(student_id)