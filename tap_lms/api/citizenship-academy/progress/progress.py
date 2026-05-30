import frappe
from datetime import date, datetime


def _get_learner(student_id: str):
    name = frappe.db.get_value("Citizenship Learner", {"student": student_id}, "name")
    if name:
        return frappe.get_doc("Citizenship Learner", name)
    doc = frappe.new_doc("Citizenship Learner")
    doc.student = student_id
    doc.xp = 0
    doc.streak = 0
    doc.longest_streak = 0
    doc.insert(ignore_permissions=True)
    return doc


def _update_streak(learner):
    today = date.today()
    if not learner.last_activity_date:
        learner.streak = 1
        learner.last_activity_date = today.isoformat()
        learner.longest_streak = max(learner.longest_streak or 0, 1)
        return
    last = learner.last_activity_date
    if isinstance(last, str):
        last = datetime.strptime(last, "%Y-%m-%d").date()
    delta = (today - last).days
    if delta == 0:
        return
    learner.streak = (learner.streak or 0) + 1 if delta == 1 else 1
    learner.last_activity_date = today.isoformat()
    learner.longest_streak = max(learner.longest_streak or 0, learner.streak)


def _learner_state(learner):
    return {
        "xp": learner.xp,
        "streak": learner.streak,
        "longest_streak": learner.longest_streak,
        "level": learner.level,
        "last_activity_date": str(learner.last_activity_date) if learner.last_activity_date else None,
    }


@frappe.whitelist(allow_guest=True)
def update_xp(student_id: str, xp: int):
    learner = _get_learner(student_id)
    learner.xp = (learner.xp or 0) + int(xp)
    _update_streak(learner)
    learner.save(ignore_permissions=True)
    return _learner_state(learner)


@frappe.whitelist(allow_guest=True)
def get_streak(student_id: str):
    learner = _get_learner(student_id)
    return {
        "streak": learner.streak,
        "longest_streak": learner.longest_streak,
        "last_activity_date": str(learner.last_activity_date) if learner.last_activity_date else None,
    }


@frappe.whitelist(allow_guest=True)
def get_enrollments(student_id: str):
    learner = _get_learner(student_id)
    return {
        "student_id": student_id,
        "enrollments": [
            {
                "course": row.course,
                "status": row.status,
                "videos_completed": row.videos_completed or 0,
                "quizzes_completed": row.quizzes_completed or 0,
                "enrolled_on": str(row.enrolled_on) if row.enrolled_on else None,
            }
            for row in learner.enrollments
        ],
    }


@frappe.whitelist(allow_guest=True)
def enroll_course(student_id: str, course: str):
    if not frappe.db.exists("Course Level", course):
        frappe.throw("Course not found")
    learner = _get_learner(student_id)
    for row in learner.enrollments:
        if row.course == course:
            return {"enrolled": False, "reason": "already_enrolled", "course": course}
    learner.append("enrollments", {
        "course": course,
        "enrolled_on": date.today().isoformat(),
        "status": "active",
        "videos_completed": 0,
        "quizzes_completed": 0,
    })
    learner.save(ignore_permissions=True)
    return {"enrolled": True, "course": course}


@frappe.whitelist(allow_guest=True)
def update_video(student_id: str, course: str, video_index: int, xp: int = 0):
    learner = _get_learner(student_id)
    enrollment = None
    for row in learner.enrollments:
        if row.course == course:
            enrollment = row
            break
    if not enrollment:
        frappe.throw("Not enrolled in this course")
    video_index = int(video_index)
    if video_index <= (enrollment.videos_completed or 0):
        return {"updated": False, "reason": "already_completed", **_learner_state(learner)}
    enrollment.videos_completed = video_index
    if int(xp) > 0:
        learner.xp = (learner.xp or 0) + int(xp)
        _update_streak(learner)
    learner.save(ignore_permissions=True)
    return {"updated": True, "videos_completed": enrollment.videos_completed, **_learner_state(learner)}


@frappe.whitelist(allow_guest=True)
def update_quiz(student_id: str, course: str, xp: int = 0):
    learner = _get_learner(student_id)
    enrollment = None
    for row in learner.enrollments:
        if row.course == course:
            enrollment = row
            break
    if not enrollment:
        frappe.throw("Not enrolled in this course")
    enrollment.quizzes_completed = (enrollment.quizzes_completed or 0) + 1
    if int(xp) > 0:
        learner.xp = (learner.xp or 0) + int(xp)
        _update_streak(learner)
    learner.save(ignore_permissions=True)
    return {"updated": True, "quizzes_completed": enrollment.quizzes_completed, **_learner_state(learner)}