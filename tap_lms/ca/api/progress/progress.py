import frappe
import json
from datetime import date, datetime

MAX_XP_PER_CALL = 25
XP_QUEUE_KEY = "ca:xp_queue"


def _today():
    return date.today()


def _parse_date(d):
    if not d:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _get_learner_name(student_id: str):
    return frappe.db.get_value("Citizenship Learner", {"student": student_id}, "name")


def _learner_state_from_row(row):
    return {
        "xp": row.xp or 0,
        "weekly_xp": row.weekly_xp or 0,
        "streak": row.streak or 0,
        "longest_streak": row.longest_streak or 0,
        "level": row.level or 1,
        "last_activity_date": str(row.last_activity_date) if row.last_activity_date else None,
    }


def _learner_state(student_id: str):
    row = frappe.db.get_value(
        "Citizenship Learner",
        {"student": student_id},
        ["xp", "weekly_xp", "streak", "longest_streak", "level", "last_activity_date"],
        as_dict=True,
    )
    if not row:
        return {}
    return _learner_state_from_row(row)


def _ensure_learner(student_id: str):
    name = _get_learner_name(student_id)
    if name:
        return name
    try:
        doc = frappe.new_doc("Citizenship Learner")
        doc.student = student_id
        doc.xp = 0
        doc.xp_d0 = 0
        doc.xp_d1 = 0
        doc.xp_d2 = 0
        doc.xp_d3 = 0
        doc.xp_d4 = 0
        doc.xp_d5 = 0
        doc.xp_d6 = 0
        doc.weekly_xp = 0
        doc.streak = 0
        doc.longest_streak = 0
        doc.level = 1
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except frappe.exceptions.DuplicateEntryError:
        frappe.db.rollback()
        return _get_learner_name(student_id)


def _get_enrollment(learner_name, course):
    return frappe.db.get_value(
        "Citizenship Enrollment",
        {"parent": learner_name, "course": course},
        ["name", "videos_completed", "quizzes_completed", "status"],
        as_dict=True,
    )


@frappe.whitelist(allow_guest=True)
def get_student_state(student_id=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)
    _ensure_learner(student_id)
    return _learner_state(student_id)


@frappe.whitelist(allow_guest=True)
def get_streak(student_id=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)
    return _learner_state(student_id)


@frappe.whitelist(allow_guest=True)
def update_streak(student_id=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)

    _ensure_learner(student_id)
    today = _today()
    name = _get_learner_name(student_id)

    last_date_raw = frappe.db.get_value("Citizenship Learner", name, "last_activity_date")
    last_date = _parse_date(last_date_raw)

    if last_date == today:
        return _learner_state(student_id)

    if last_date and (today - last_date).days == 1:
        frappe.db.sql(
            """
            UPDATE "tabCitizenship Learner"
               SET streak             = streak + 1,
                   longest_streak     = GREATEST(longest_streak, streak + 1),
                   last_activity_date = %s
             WHERE name = %s
            """,
            (today.isoformat(), name),
        )
    else:
        frappe.db.sql(
            """
            UPDATE "tabCitizenship Learner"
               SET streak             = 1,
                   longest_streak     = GREATEST(longest_streak, 1),
                   last_activity_date = %s
             WHERE name = %s
            """,
            (today.isoformat(), name),
        )

    frappe.db.commit()
    return _learner_state(student_id)


@frappe.whitelist(allow_guest=True)
def get_content_progress(student_id=None, course=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    course = course or frappe.form_dict.get("course")
    if not student_id or not course:
        frappe.throw("student_id and course are required", frappe.ValidationError)
    name = _ensure_learner(student_id)
    enrollment = _get_enrollment(name, course)
    return {
        "course": course,
        "videos_completed": enrollment.videos_completed if enrollment else 0,
        "quizzes_completed": enrollment.quizzes_completed if enrollment else 0,
        **_learner_state(student_id),
    }