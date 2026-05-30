import frappe
import unittest
from datetime import date, timedelta


class TestCitizenshipLearner(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self.student_name = self._make_student()

    def tearDown(self):
        frappe.db.rollback()

    def _make_student(self):
        if frappe.db.exists("Student", {"name1": "_Test Student CL"}):
            return frappe.db.get_value("Student", {"name1": "_Test Student CL"}, "name")
        doc = frappe.new_doc("Student")
        doc.name1 = "_Test Student CL"
        doc.phone = "9999999999"
        doc.insert(ignore_permissions=True)
        return doc.name

    def _make_learner(self):
        doc = frappe.new_doc("Citizenship Learner")
        doc.student = self.student_name
        doc.xp = 0
        doc.streak = 0
        doc.longest_streak = 0
        doc.insert(ignore_permissions=True)
        return doc

    def test_learner_creation(self):
        doc = self._make_learner()
        self.assertEqual(doc.xp, 0)
        self.assertEqual(doc.streak, 0)
        self.assertEqual(doc.longest_streak, 0)

    def test_add_activity_adds_xp(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10, video_index=1)
        self.assertEqual(doc.xp, 10)

    def test_add_activity_arbitrary_xp(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=25)
        self.assertEqual(doc.xp, 25)

    def test_add_activity_accumulates_xp(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10, video_index=1)
        doc.add_activity("_Test Course", xp=5)
        self.assertEqual(doc.xp, 15)

    def test_video_duplicate_blocked(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10, video_index=1)
        doc.add_activity("_Test Course", xp=10, video_index=1)
        self.assertEqual(doc.xp, 10)

    def test_video_sequential_allowed(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10, video_index=1)
        doc.add_activity("_Test Course", xp=10, video_index=2)
        self.assertEqual(doc.xp, 20)

    def test_no_video_index_always_adds_xp(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=3)
        doc.add_activity("_Test Course", xp=3)
        self.assertEqual(doc.xp, 6)

    def test_enrollment_created_on_first_activity(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10, video_index=1)
        self.assertEqual(len(doc.enrollments), 1)
        self.assertEqual(doc.enrollments[0].course, "_Test Course")

    def test_enrollment_reused_same_course_batch(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10, video_index=1)
        doc.add_activity("_Test Course", xp=3)
        self.assertEqual(len(doc.enrollments), 1)

    def test_separate_enrollments_different_courses(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course A", "_Test Batch", xp=10, video_index=1)
        doc.add_activity("_Test Course B", "_Test Batch", xp=10, video_index=1)
        self.assertEqual(len(doc.enrollments), 2)

    def test_videos_completed_updated(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10, video_index=3)
        self.assertEqual(doc.enrollments[0].videos_completed, 3)

    def test_streak_first_activity(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10)
        self.assertEqual(doc.streak, 1)

    def test_streak_same_day_no_increment(self):
        doc = self._make_learner()
        doc.add_activity("_Test Course", xp=10)
        doc.add_activity("_Test Course", xp=3)
        self.assertEqual(doc.streak, 1)

    def test_streak_consecutive_day_increments(self):
        doc = self._make_learner()
        doc.last_activity_date = (date.today() - timedelta(days=1)).isoformat()
        doc.streak = 3
        doc.longest_streak = 3
        doc.add_activity("_Test Course", xp=10)
        self.assertEqual(doc.streak, 4)

    def test_streak_resets_after_gap(self):
        doc = self._make_learner()
        doc.last_activity_date = (date.today() - timedelta(days=2)).isoformat()
        doc.streak = 5
        doc.add_activity("_Test Course", xp=10)
        self.assertEqual(doc.streak, 1)

    def test_longest_streak_updated(self):
        doc = self._make_learner()
        doc.last_activity_date = (date.today() - timedelta(days=1)).isoformat()
        doc.streak = 9
        doc.longest_streak = 9
        doc.add_activity("_Test Course", xp=10)
        self.assertEqual(doc.longest_streak, 10)

    def test_longest_streak_preserved_on_reset(self):
        doc = self._make_learner()
        doc.last_activity_date = (date.today() - timedelta(days=2)).isoformat()
        doc.streak = 5
        doc.longest_streak = 5
        doc.add_activity("_Test Course", xp=10)
        self.assertEqual(doc.streak, 1)
        self.assertEqual(doc.longest_streak, 5)

    def test_record_activity_api_returns_state(self):
        from tap_lms.tap_lms.doctype.citizenship_learner.citizenship_learner import record_activity
        result = record_activity(self.student_name, "_Test Course", xp=10, video_index=1)
        self.assertEqual(result["xp"], 10)
        self.assertEqual(result["streak"], 1)
        self.assertIn("longest_streak", result)
        self.assertIn("level", result)
        self.assertIn("last_activity_date", result)

    def test_record_activity_api_no_video_index(self):
        from tap_lms.tap_lms.doctype.citizenship_learner.citizenship_learner import record_activity
        result = record_activity(self.student_name, "_Test Course", xp=3)
        self.assertEqual(result["xp"], 3)

    def test_get_learner_state_api(self):
        from tap_lms.tap_lms.doctype.citizenship_learner.citizenship_learner import record_activity, get_learner_state
        record_activity(self.student_name, "_Test Course", xp=10, video_index=1)
        state = get_learner_state(self.student_name)
        self.assertEqual(state["xp"], 10)
        self.assertEqual(len(state["enrollments"]), 1)
        self.assertEqual(state["enrollments"][0]["videos_completed"], 1)

    def test_get_learner_creates_if_missing(self):
        from tap_lms.tap_lms.doctype.citizenship_learner.citizenship_learner import _get_learner
        learner = _get_learner(self.student_name)
        self.assertEqual(learner.student, self.student_name)
        self.assertEqual(learner.xp, 0)

    def test_get_learner_reuses_existing(self):
        from tap_lms.tap_lms.doctype.citizenship_learner.citizenship_learner import _get_learner
        first = _get_learner(self.student_name)
        second = _get_learner(self.student_name)
        self.assertEqual(first.name, second.name)