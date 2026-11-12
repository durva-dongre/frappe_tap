from __future__ import annotations

from tap_lms.tap_app.api import tap_app_method
from shared.enrollment.active_batch import get_active_program_enrollment
from shared.progress.activities import submit_video as _submit_video, submit_quiz as _submit_quiz
from shared.profile.sync import get_sync_payload, get_last_submission_payload


@tap_app_method
def submit_video(student_id: str, unit_id: str, watched, context: str = "program"):
    watched = bool(watched)
    pe = get_active_program_enrollment(student_id)
    result = _submit_video(pe, unit_id, watched, context)
    pe.save(ignore_permissions=True)
    return {
        "points_awarded": result["points_awarded"],
        "points_total": result["points_total"],
        "updated_at": int(pe.last_activity_at.timestamp()),
    }


@tap_app_method
def submit_quiz(student_id: str, unit_id: str, answers, context: str = "program"):
    pe = get_active_program_enrollment(student_id)
    result = _submit_quiz(pe, unit_id, answers, context)
    pe.save(ignore_permissions=True)
    return {
        "correct_count": result["correct_count"],
        "total_count": result["total_count"],
        "points_awarded": result["points_awarded"],
        "points_total": result["points_total"],
        "updated_at": int(pe.last_activity_at.timestamp()),
    }


@tap_app_method
def progress_sync(student_id: str, last_updated: int):
    return get_sync_payload(student_id, last_updated)


@tap_app_method
def last_submission(student_id: str, last_updated: int):
    return get_last_submission_payload(student_id, last_updated)