import frappe
from .learner import (
    _get_or_create_learner,
    _learner_xp_state,
    _update_streak,
    _queue_xp,
    _bulk_course_meta,
    _bulk_course_translations,
    MAX_XP_PER_CALL,
)


def _get_enrollment_row(learner_name: str, course: str):
    return frappe.db.get_value(
        "Citizenship Enrollment",
        {"parent": learner_name, "course": course},
        ["name", "videos_completed", "quizzes_completed", "status"],
        as_dict=True,
    )


def _parse_fields(fields_param):
    if not fields_param:
        return None
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


def _fetch_next_video(course_id: str, video_index: int, lang=None):
    course_doc = frappe.get_doc("Course Level", course_id)
    units = [row.learning_unit for row in (course_doc.learning_units or []) if row.learning_unit]

    video_counter = 0
    for unit_id in units:
        unit = frappe.get_doc("LearningUnit", unit_id)
        for item in (unit.content_items or []):
            ct = (getattr(item, "content_type", "") or "").lower()
            if ct != "videoclass":
                continue
            video_counter += 1
            if video_counter == video_index + 1:
                cid = item.content
                if not cid:
                    return None
                v = frappe.db.get_value(
                    "VideoClass",
                    cid,
                    ["name", "video_name", "video_youtube_url", "video_url",
                     "duration", "points", "subtitle_file"],
                    as_dict=True,
                )
                if not v:
                    return None
                trans_url = None
                trans_dl = None
                trans_title = None
                trans_sub = None
                if lang and lang.lower() not in ("en", "english"):
                    t = frappe.db.get_value(
                        "VideoTranslation",
                        {"parent": cid, "language": lang},
                        ["translated_name", "video_youtube_url", "video_url", "subtitle_file"],
                        as_dict=True,
                    )
                    if t:
                        trans_title = t.translated_name or None
                        trans_url = t.video_youtube_url or None
                        trans_dl = t.video_url or None
                        trans_sub = t.subtitle_file or None
                return {
                    "content_type": "video",
                    "content_id": cid,
                    "index": video_counter,
                    "title": trans_title or v.video_name,
                    "url": trans_url or v.video_youtube_url,
                    "download_url": trans_dl or v.video_url,
                    "subtitle_file": trans_sub or v.subtitle_file,
                    "duration": str(v.duration or ""),
                    "points": v.points or 10,
                }
    return None


def _fetch_next_quiz(course_id: str, quiz_index: int, lang=None):
    course_doc = frappe.get_doc("Course Level", course_id)
    units = [row.learning_unit for row in (course_doc.learning_units or []) if row.learning_unit]

    quiz_counter = 0
    for unit_id in units:
        unit = frappe.get_doc("LearningUnit", unit_id)
        for item in (unit.content_items or []):
            ct = (getattr(item, "content_type", "") or "").lower()
            if ct != "quiz":
                continue
            quiz_counter += 1
            if quiz_counter == quiz_index + 1:
                cid = item.content
                if not cid:
                    return None
                q = frappe.db.get_value(
                    "Quiz",
                    cid,
                    ["name", "quiz_name", "passing_score", "time_limit", "max_attempts"],
                    as_dict=True,
                )
                if not q:
                    return None
                trans_title = None
                if lang and lang.lower() not in ("en", "english"):
                    t = frappe.db.get_value(
                        "QuizTranslation",
                        {"parent": cid, "language": lang},
                        "translated_name",
                    )
                    trans_title = t or None
                return {
                    "content_type": "quiz",
                    "content_id": cid,
                    "index": quiz_counter,
                    "title": trans_title or q.quiz_name,
                    "passing_score": q.passing_score or 60,
                    "time_limit": str(q.time_limit) if q.time_limit else None,
                    "max_attempts": q.max_attempts,
                }
    return None


@frappe.whitelist(allow_guest=True)
def update_content_progress(
    student_id=None,
    course=None,
    video_index=None,
    quiz_index=None,
    xp=None,
    lang=None,
    fetch_next=None,
    fields=None,
):
    fd = frappe.form_dict
    student_id  = student_id  or fd.get("student_id")
    course      = course      or fd.get("course")
    video_index = video_index if video_index is not None else fd.get("video_index")
    quiz_index  = quiz_index  if quiz_index  is not None else fd.get("quiz_index")
    xp          = xp          if xp          is not None else fd.get("xp")
    lang        = lang        or fd.get("lang")
    fetch_next  = fetch_next  if fetch_next  is not None else fd.get("fetch_next")
    fields      = fields      or fd.get("fields")

    if not student_id or not course:
        frappe.throw("student_id and course are required", frappe.ValidationError)

    has_video = video_index is not None
    has_quiz  = quiz_index  is not None

    if not has_video and not has_quiz:
        frappe.throw("At least one of video_index or quiz_index is required", frappe.ValidationError)

    video_index = int(video_index) if has_video else None
    quiz_index  = int(quiz_index)  if has_quiz  else None
    xp          = min(int(xp or 10), MAX_XP_PER_CALL)

    fetch_next_flag = str(fetch_next).lower() in ("true", "1", "yes") if fetch_next is not None else False
    optional        = _parse_fields(fields)
    include_daily   = optional is None or "xp_daily" in optional

    learner_name = _get_or_create_learner(student_id)
    enrollment   = _get_enrollment_row(learner_name, course)

    if not enrollment:
        frappe.throw("Not enrolled in this course", frappe.ValidationError)

    current_videos = enrollment.videos_completed or 0
    current_quizzes = enrollment.quizzes_completed or 0

    video_already_done  = has_video and video_index <= current_videos
    quiz_already_done   = has_quiz  and quiz_index  <= current_quizzes

    new_videos  = video_index if (has_video  and not video_already_done)  else current_videos
    new_quizzes = quiz_index  if (has_quiz   and not quiz_already_done)   else current_quizzes

    needs_update = (has_video and not video_already_done) or (has_quiz and not quiz_already_done)

    if needs_update:
        frappe.db.sql(
            """
            UPDATE "tabCitizenship Enrollment"
               SET videos_completed  = %s,
                   quizzes_completed = %s,
                   modified          = NOW()
             WHERE name = %s
            """,
            (new_videos, new_quizzes, enrollment.name),
        )
        frappe.db.commit()
        _update_streak(learner_name)
        _queue_xp(student_id, xp)

    result = {
        "updated":                needs_update,
        "video_updated":          has_video  and not video_already_done,
        "quiz_updated":           has_quiz   and not quiz_already_done,
        "video_already_completed": video_already_done if has_video else None,
        "quiz_already_completed":  quiz_already_done  if has_quiz  else None,
        "videos_completed":       new_videos,
        "quizzes_completed":      new_quizzes,
        **_learner_xp_state(student_id, include_daily=include_daily),
    }

    if fetch_next_flag:
        next_data = {}
        if has_video:
            nv = _fetch_next_video(course, new_videos, lang)
            if nv:
                next_data["next_video"] = nv
        if has_quiz:
            nq = _fetch_next_quiz(course, new_quizzes, lang)
            if nq:
                next_data["next_quiz"] = nq
        result["next"] = next_data

    return result


@frappe.whitelist(allow_guest=True)
def get_course_progress(student_id=None, course=None, lang=None, fields=None):
    fd = frappe.form_dict
    student_id = student_id or fd.get("student_id")
    course     = course     or fd.get("course")
    lang       = lang       or fd.get("lang")
    fields     = fields     or fd.get("fields")

    if not student_id or not course:
        frappe.throw("student_id and course are required", frappe.ValidationError)

    optional = _parse_fields(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    learner_name = _get_or_create_learner(student_id)
    enrollment   = _get_enrollment_row(learner_name, course)

    result = {
        "course":             course,
        "videos_completed":   enrollment.videos_completed  if enrollment else 0,
        "quizzes_completed":  enrollment.quizzes_completed if enrollment else 0,
        "status":             enrollment.status            if enrollment else None,
    }

    if _want("xp") or _want("xp_daily"):
        result.update(_learner_xp_state(student_id, include_daily=_want("xp_daily")))

    if _want("course_meta"):
        course_meta  = _bulk_course_meta([course])
        course_trans = _bulk_course_translations([course], lang)
        meta = course_meta.get(course)
        eng_name = (meta.name1 if meta else None) or course
        result["course_title"] = course_trans.get(course) or eng_name
        result["eng_name"]     = eng_name

    return result


@frappe.whitelist(allow_guest=True)
def get_video_progress(student_id=None, course=None, lang=None):
    return get_course_progress(
        student_id=student_id,
        course=course,
        lang=lang,
        fields="xp,course_meta",
    )


@frappe.whitelist(allow_guest=True)
def get_quiz_progress(student_id=None, course=None, lang=None):
    return get_course_progress(
        student_id=student_id,
        course=course,
        lang=lang,
        fields="xp,course_meta",
    )


@frappe.whitelist(allow_guest=True)
def update_video_progress(student_id=None, course=None, video_index=None, xp=None, lang=None):
    return update_content_progress(
        student_id=student_id,
        course=course,
        video_index=video_index,
        xp=xp,
        lang=lang,
    )


@frappe.whitelist(allow_guest=True)
def update_quiz_progress(student_id=None, course=None, quiz_index=None, xp=None, lang=None):
    return update_content_progress(
        student_id=student_id,
        course=course,
        quiz_index=quiz_index,
        xp=xp,
        lang=lang,
    )


@frappe.whitelist(allow_guest=True)
def get_student_state(student_id=None):
    from .learner import _get_or_create_learner, _learner_xp_state
    student_id = student_id or frappe.form_dict.get("student_id")
    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)
    _get_or_create_learner(student_id)
    return _learner_xp_state(student_id)


@frappe.whitelist(allow_guest=True)
def get_streak(student_id=None):
    from .learner import _learner_xp_state
    student_id = student_id or frappe.form_dict.get("student_id")
    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)
    return _learner_xp_state(student_id)


@frappe.whitelist(allow_guest=True)
def update_streak(student_id=None):
    from .learner import _get_or_create_learner, _update_streak, _learner_xp_state
    student_id = student_id or frappe.form_dict.get("student_id")
    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)
    learner_name = _get_or_create_learner(student_id)
    _update_streak(learner_name)
    return _learner_xp_state(student_id)


@frappe.whitelist(allow_guest=True)
def get_content_progress(student_id=None, course=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    course     = course     or frappe.form_dict.get("course")
    if not student_id or not course:
        frappe.throw("student_id and course are required", frappe.ValidationError)
    return get_course_progress(student_id=student_id, course=course, fields="xp")