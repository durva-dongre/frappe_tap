import frappe
from frappe.model.document import Document
from datetime import date, datetime


class CitizenshipLearner(Document):

    def add_activity(self, course: str, xp: int, video_index: int = None):
        enrollment = self._get_or_create_enrollment(course)
        if video_index is not None:
            if video_index <= (enrollment.videos_completed or 0):
                return
            enrollment.videos_completed = video_index
        self.xp = (self.xp or 0) + xp
        self._update_streak()
        self.save(ignore_permissions=True)

    def _get_or_create_enrollment(self, course: str):
        for row in self.enrollments:
            if row.course == course:
                return row
        return self.append("enrollments", {
            "course": course,
            "enrolled_on": date.today().isoformat(),
            "status": "active",
            "videos_completed": 0,
            "quizzes_completed": 0,
        })

    def _update_streak(self):
        today = date.today()
        if not self.last_activity_date:
            self.streak = 1
            self.last_activity_date = today.isoformat()
            self.longest_streak = max(self.longest_streak or 0, self.streak)
            return
        last = self.last_activity_date
        if isinstance(last, str):
            last = datetime.strptime(last, "%Y-%m-%d").date()
        delta = (today - last).days
        if delta == 0:
            return
        self.streak = (self.streak or 0) + 1 if delta == 1 else 1
        self.last_activity_date = today.isoformat()
        self.longest_streak = max(self.longest_streak or 0, self.streak)


@frappe.whitelist()
def record_activity(student: str, course: str, xp: int, video_index: int = None):
    learner = _get_learner(student)
    learner.add_activity(
        course=course,
        xp=int(xp),
        video_index=int(video_index) if video_index is not None else None,
    )
    return {
        "xp": learner.xp,
        "streak": learner.streak,
        "longest_streak": learner.longest_streak,
        "level": learner.level,
        "last_activity_date": str(learner.last_activity_date),
    }


@frappe.whitelist()
def get_learner_state(student: str):
    learner = _get_learner(student)
    return {
        "name": learner.name,
        "xp": learner.xp,
        "streak": learner.streak,
        "longest_streak": learner.longest_streak,
        "level": learner.level,
        "last_activity_date": str(learner.last_activity_date) if learner.last_activity_date else None,
        "enrollments": [
            {
                "course": row.course,
                "status": row.status,
                "videos_completed": row.videos_completed,
                "quizzes_completed": row.quizzes_completed,
                "enrolled_on": str(row.enrolled_on),
            }
            for row in learner.enrollments
        ],
    }


def _get_learner(student: str) -> "CitizenshipLearner":
    name = frappe.db.get_value("Citizenship Learner", {"student": student}, "name")
    if name:
        return frappe.get_doc("Citizenship Learner", name)
    doc = frappe.new_doc("Citizenship Learner")
    doc.student = student
    doc.xp = 0
    doc.streak = 0
    doc.longest_streak = 0
    doc.insert(ignore_permissions=True)
    return doc