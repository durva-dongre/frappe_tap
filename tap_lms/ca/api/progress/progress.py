import frappe
from .learner import (
    _learner_xp_state,
    _update_streak,
    _queue_xp,
    _parse_optional,
    MAX_XP_PER_CALL,
)


def _get_enrollment_row(learner_id: str, course: str):
    rows = frappe.db.sql(
        """
        SELECT name, videos_completed, quizzes_completed, status, enrolled_on
        FROM "tabCitizenship Enrollment"
        WHERE parent=%s AND course=%s
        LIMIT 1
        """,
        (learner_id, course),
        as_dict=True,
    )
    return rows[0] if rows else None


@frappe.whitelist(allow_guest=True)
def update_content_progress(
    learner_id=None, course=None, video_index=None,
    quiz_index=None, xp=None, fetch_next=False, fields=None,
):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")
    video_index = video_index if video_index is not None else fd.get("video_index")
    quiz_index = quiz_index if quiz_index is not None else fd.get("quiz_index")
    xp = xp if xp is not None else fd.get("xp")
    fetch_next = fetch_next if fetch_next is not False else fd.get("fetch_next", False)
    fields = fields or fd.get("fields")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    has_video = video_index is not None
    has_quiz = quiz_index is not None
    if not has_video and not has_quiz:
        frappe.throw("At least one of video_index or quiz_index is required", frappe.ValidationError)

    video_index = int(video_index) if has_video else None
    quiz_index = int(quiz_index) if has_quiz else None
    xp = min(int(xp or 10), MAX_XP_PER_CALL)
    fetch_next_flag = str(fetch_next).lower() in ("true", "1", "yes") if fetch_next else False

    optional = _parse_optional(fields)
    include_daily = optional is None or "xp_daily" in optional

    enrollment = _get_enrollment_row(learner_id, course)
    if not enrollment:
        frappe.throw("Not enrolled in this course", frappe.ValidationError)

    current_videos = enrollment.videos_completed or 0
    current_quizzes = enrollment.quizzes_completed or 0

    video_already_done = has_video and video_index <= current_videos
    quiz_already_done = has_quiz and quiz_index <= current_quizzes

    new_videos = video_index if (has_video and not video_already_done) else current_videos
    new_quizzes = quiz_index if (has_quiz and not quiz_already_done) else current_quizzes
    needs_update = (has_video and not video_already_done) or (has_quiz and not quiz_already_done)

    if needs_update:
        frappe.db.sql(
            """
            UPDATE "tabCitizenship Enrollment"
               SET videos_completed  = GREATEST(videos_completed, %s),
                   quizzes_completed = GREATEST(quizzes_completed, %s),
                   modified          = NOW()
             WHERE name = %s
            """,
            (new_videos, new_quizzes, enrollment.name),
        )
        frappe.db.commit()
        _update_streak(learner_id)
        _queue_xp(learner_id, xp)

    result = {
        "updated": needs_update,
        "video_updated": has_video and not video_already_done,
        "quiz_updated": has_quiz and not quiz_already_done,
        "videos_completed": new_videos,
        "quizzes_completed": new_quizzes,
        **_learner_xp_state(learner_id, include_daily=include_daily),
    }

    if fetch_next_flag:
        result["next_video_index"] = new_videos + 1 if has_video else None
        result["next_quiz_index"] = new_quizzes + 1 if has_quiz else None

    return result


@frappe.whitelist(allow_guest=True)
def get_course_progress(learner_id=None, course=None, fields=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")
    fields = fields or fd.get("fields")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    optional = _parse_optional(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    enrollment = _get_enrollment_row(learner_id, course)
    result = {
        "course": course,
        "videos_completed": enrollment.videos_completed if enrollment else 0,
        "quizzes_completed": enrollment.quizzes_completed if enrollment else 0,
        "status": enrollment.status if enrollment else None,
        "enrolled_on": str(enrollment.enrolled_on) if enrollment and enrollment.enrolled_on else None,
    }

    if _want("xp") or _want("xp_daily"):
        result.update(_learner_xp_state(learner_id, include_daily=_want("xp_daily")))

    return result


@frappe.whitelist(allow_guest=True)
def refresh_content_progress(learner_id=None, course=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    enrollment = _get_enrollment_row(learner_id, course)
    if not enrollment:
        return {"enrolled": False, "course": course}

    vd = enrollment.videos_completed or 0
    qd = enrollment.quizzes_completed or 0
    return {
        "enrolled": True,
        "course": course,
        "videos_completed": vd,
        "quizzes_completed": qd,
        "next_video_index": vd + 1,
        "next_quiz_index": qd + 1,
    }