import frappe
from .learner import (
    _learner_xp_state,
    _update_streak,
    _queue_xp,
    _parse_optional,
)
from .achievements import (
    _award_achievement_row,
    _parse_achievements_payload,
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


def _ensure_enrollment(learner_id: str, course: str):
    existing = _get_enrollment_row(learner_id, course)
    if existing:
        return existing

    frappe.db.sql(
        """
        INSERT INTO "tabCitizenship Enrollment"
            (name, parent, parenttype, parentfield,
             course, enrolled_on, status,
             videos_completed, quizzes_completed,
             creation, modified, modified_by, owner)
        VALUES
            (%s, %s, 'Citizenship Learner', 'enrollments',
             %s, CURRENT_DATE, 'active',
             0, 0,
             NOW(), NOW(), 'Administrator', 'Administrator')
        ON CONFLICT (parent, course) DO NOTHING
        """,
        (frappe.generate_hash(length=10), learner_id, course),
    )
    frappe.db.commit()

    return _get_enrollment_row(learner_id, course)


@frappe.whitelist(allow_guest=True)
def update_content_progress(
    learner_id=None, course=None, video_index=None,
    quiz_index=None, xp=None, fetch_next=False, fields=None,
    achievements=None,
):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")
    video_index = video_index if video_index is not None else fd.get("video_index")
    quiz_index = quiz_index if quiz_index is not None else fd.get("quiz_index")
    xp = xp if xp is not None else fd.get("xp")
    fetch_next = fetch_next if fetch_next is not False else fd.get("fetch_next", False)
    fields = fields or fd.get("fields")
    achievements = achievements if achievements is not None else fd.get("achievements")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    has_video = video_index is not None
    has_quiz = quiz_index is not None
    if not has_video and not has_quiz:
        frappe.throw("At least one of video_index or quiz_index is required", frappe.ValidationError)

    video_count = int(video_index) if has_video else None
    quiz_count = int(quiz_index) if has_quiz else None
    xp = int(xp or 10)
    fetch_next_flag = str(fetch_next).lower() in ("true", "1", "yes") if fetch_next else False

    if xp <= 0:
        frappe.throw("xp must be positive", frappe.ValidationError)

    optional = _parse_optional(fields)
    include_daily = optional is None or "xp_daily" in optional

    parsed_achievements = _parse_achievements_payload(achievements)

    enrollment = _ensure_enrollment(learner_id, course)
    if not enrollment:
        frappe.throw("Could not create or find enrollment for this learner and course", frappe.ValidationError)

    current_videos = enrollment.videos_completed or 0
    current_quizzes = enrollment.quizzes_completed or 0

    new_videos = max(current_videos, video_count) if has_video else current_videos
    new_quizzes = max(current_quizzes, quiz_count) if has_quiz else current_quizzes

    video_advanced = has_video and new_videos > current_videos
    quiz_advanced = has_quiz and new_quizzes > current_quizzes
    progress_moved = video_advanced or quiz_advanced

    if progress_moved:
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

    awarded_achievements = []
    for achievement, level in parsed_achievements:
        awarded_achievements.append(_award_achievement_row(learner_id, achievement, level))
    if awarded_achievements:
        frappe.db.commit()

    result = {
        "updated": progress_moved,
        "video_updated": video_advanced,
        "quiz_updated": quiz_advanced,
        "videos_completed": new_videos,
        "quizzes_completed": new_quizzes,
        **_learner_xp_state(learner_id, include_daily=include_daily),
    }

    if awarded_achievements:
        result["achievements_awarded"] = awarded_achievements

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