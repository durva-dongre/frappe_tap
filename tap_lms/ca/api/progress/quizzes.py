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


@frappe.whitelist(allow_guest=True)
def update_quiz_progress(student_id=None, course=None, quiz_index=None, xp=None, lang=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    course = course or frappe.form_dict.get("course")
    quiz_index = quiz_index if quiz_index is not None else frappe.form_dict.get("quiz_index")
    xp = xp if xp is not None else frappe.form_dict.get("xp")
    lang = lang or frappe.form_dict.get("lang")

    if not student_id or not course or quiz_index is None:
        frappe.throw("student_id, course, and quiz_index are required", frappe.ValidationError)

    quiz_index = int(quiz_index)
    xp = min(int(xp or 15), MAX_XP_PER_CALL)

    learner_name = _get_or_create_learner(student_id)
    enrollment = _get_enrollment_row(learner_name, course)

    if not enrollment:
        frappe.throw("Not enrolled in this course", frappe.ValidationError)

    current = enrollment.quizzes_completed or 0
    already_done = quiz_index <= current

    if not already_done:
        frappe.db.sql(
            """
            UPDATE "tabCitizenship Enrollment"
               SET quizzes_completed = %s,
                   modified          = NOW()
             WHERE name = %s
            """,
            (quiz_index, enrollment.name),
        )
        frappe.db.commit()
        _update_streak(learner_name)
        _queue_xp(student_id, xp)

    return {
        "updated": not already_done,
        "already_completed": already_done,
        "quizzes_completed": quiz_index if not already_done else current,
        **_learner_xp_state(student_id),
    }


@frappe.whitelist(allow_guest=True)
def get_quiz_progress(student_id=None, course=None, lang=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    course = course or frappe.form_dict.get("course")
    lang = lang or frappe.form_dict.get("lang")

    if not student_id or not course:
        frappe.throw("student_id and course are required", frappe.ValidationError)

    learner_name = _get_or_create_learner(student_id)
    enrollment = _get_enrollment_row(learner_name, course)

    course_meta = _bulk_course_meta([course])
    course_trans = _bulk_course_translations([course], lang)
    meta = course_meta.get(course)
    eng_name = (meta.name1 if meta else None) or course
    title = course_trans.get(course) or eng_name

    return {
        "course": course,
        "course_title": title,
        "eng_name": eng_name,
        "videos_completed": enrollment.videos_completed if enrollment else 0,
        "quizzes_completed": enrollment.quizzes_completed if enrollment else 0,
        "status": enrollment.status if enrollment else None,
        **_learner_xp_state(student_id),
    }