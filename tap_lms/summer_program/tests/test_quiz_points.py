"""
Tests for CR-002 v2 quiz-points handler.

Per-question independent award model:
  correct → QuizQuestion.points
  wrong   → QuizQuestion.failed_points

Cumulative-vs-weekly split (E4): cumulative uses delta vs previous-latest
attempt for same (student, quiz); weekly always adds new attempt's full
earned (effort, not latest).

Idempotency: attempt.points_earned > 0 is the write-once anchor (P-005).

Tests in this file:
  1. test_quiz_attempt_awards_per_question_correct
  2. test_quiz_attempt_awards_per_question_wrong_failed_points
  3. test_quiz_idempotent_via_points_earned
  4. test_quiz_retake_higher_score_delta_to_total
  5. test_quiz_retake_lower_score_negative_delta_to_total
  6. test_quiz_zero_earned_no_pe_update
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime
from unittest.mock import patch

from tap_lms.summer_program.constants import (
    LABEL_CONTENT_DELIVERED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    STATE_NORMAL_CONTENT,
)
from tap_lms.summer_program.quiz_points import (
    compute_quiz_points,
    handle_attempt_update,
)


# ════════════════════════════════════════════════════════════
# Test fixtures
# ════════════════════════════════════════════════════════════

def _ensure_batch():
    name = frappe.get_value("Batch", {"name1": "QuizPointsTestBatch"}, "name")
    if name:
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = "QuizPointsTestBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = "QPT01"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = 14
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix):
    name = frappe.get_value("Student", {"phone": f"+9999200{suffix}"}, "name")
    if name:
        return name
    s = frappe.new_doc("Student")
    s.name1 = f"QuizPointsTestStudent{suffix}"
    s.phone = f"+9999200{suffix}"
    s.glific_id = f"glific-qzpts-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(batch_name, student_name, suffix):
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-QZPTS-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-qzpts-{suffix}"
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = STATE_NORMAL_CONTENT
    pe.journey_label = LABEL_CONTENT_DELIVERED
    pe.current_path = PATH_CORE
    pe.current_week = 1
    pe.total_points = 0
    pe.total_quiz_points = 0
    pe.weekly_quiz_points = 0
    pe.insert(ignore_permissions=True)
    return pe.name


def _make_quiz_question(suffix, points, failed_points):
    """Insert a QuizQuestion row."""
    q = frappe.new_doc("QuizQuestion")
    q.question_text = f"Quiz question {suffix}?"
    q.points = points
    # `failed_points` is added by T-CR002v2-01; default 0 if absent.
    setattr(q, "failed_points", failed_points)
    q.insert(ignore_permissions=True)
    return q.name


def _make_quiz():
    quiz = frappe.new_doc("Quiz")
    quiz.quiz_name = f"QuizPointsTestQuiz-{frappe.utils.random_string(6)}"
    quiz.insert(ignore_permissions=True)
    return quiz.name


def _make_attempt(student, quiz, answers, completed=True):
    """Insert a StudentQuizAttempt with the provided answers.

    answers: list of dicts with keys (question, is_correct).
    """
    attempt = frappe.new_doc("StudentQuizAttempt")
    attempt.student = student
    attempt.quiz = quiz
    attempt.status = "Completed" if completed else "InProgress"
    attempt.total_questions = len(answers)
    attempt.attempt_number = 1
    attempt.started_at = now_datetime()
    if completed:
        attempt.completed_at = now_datetime()
    for i, a in enumerate(answers):
        attempt.append("answers", {
            "question_index": i,
            "question": a["question"],
            "is_correct": 1 if a["is_correct"] else 0,
        })
    attempt.insert(ignore_permissions=True)
    return attempt


# ════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════

class TestQuizPoints(FrappeTestCase):
    """CR-002 v2 §Test Plan — quiz-points handler regression coverage."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    @patch("tap_lms.summer_program.quiz_points._enqueue_contact_field_sync")
    def test_quiz_attempt_awards_per_question_correct(self, mock_sync):
        """Two correct answers (points=8, points=10) → earned = 18."""
        student = _ensure_student("01")
        pe_name = _make_pe(self.batch_name, student, "01")
        quiz = _make_quiz()
        q1 = _make_quiz_question("01a", 8, 2)
        q2 = _make_quiz_question("01b", 10, 3)
        attempt = _make_attempt(student, quiz, [
            {"question": q1, "is_correct": True},
            {"question": q2, "is_correct": True},
        ])

        handle_attempt_update(attempt)

        attempt.reload()
        self.assertEqual(attempt.points_earned, 18)

        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        self.assertEqual(pe.total_quiz_points, 18)
        self.assertEqual(pe.weekly_quiz_points, 18)
        self.assertEqual(pe.total_points, 18)

    @patch("tap_lms.summer_program.quiz_points._enqueue_contact_field_sync")
    def test_quiz_attempt_awards_per_question_wrong_failed_points(self, mock_sync):
        """Two wrong answers (failed_points=2, failed_points=3) → earned = 5.
        Verifies per-question independence of attempt-level pass/fail."""
        student = _ensure_student("02")
        pe_name = _make_pe(self.batch_name, student, "02")
        quiz = _make_quiz()
        q1 = _make_quiz_question("02a", 8, 2)
        q2 = _make_quiz_question("02b", 10, 3)
        attempt = _make_attempt(student, quiz, [
            {"question": q1, "is_correct": False},
            {"question": q2, "is_correct": False},
        ])
        # Even though attempt-level "passed" is false, partial credit applies.
        attempt.passed = 0
        attempt.save(ignore_permissions=True)

        handle_attempt_update(attempt)

        attempt.reload()
        self.assertEqual(attempt.points_earned, 5,
                         "Wrong answers award failed_points (2+3=5)")

        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        self.assertEqual(pe.total_quiz_points, 5)
        self.assertEqual(pe.weekly_quiz_points, 5)
        self.assertEqual(pe.total_points, 5)

    @patch("tap_lms.summer_program.quiz_points._enqueue_contact_field_sync")
    def test_quiz_idempotent_via_points_earned(self, mock_sync):
        """Re-running the handler on a completed attempt is a no-op:
        sees points_earned > 0 and returns. PE counters do not double-bump."""
        student = _ensure_student("03")
        pe_name = _make_pe(self.batch_name, student, "03")
        quiz = _make_quiz()
        q1 = _make_quiz_question("03", 10, 0)
        attempt = _make_attempt(student, quiz, [
            {"question": q1, "is_correct": True},
        ])

        handle_attempt_update(attempt)
        attempt.reload()
        self.assertEqual(attempt.points_earned, 10)

        # Second call should be a no-op.
        handle_attempt_update(attempt)
        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        self.assertEqual(pe.total_quiz_points, 10,
                         "Re-running handler must not double-bump")
        self.assertEqual(pe.weekly_quiz_points, 10)
        self.assertEqual(pe.total_points, 10)

    @patch("tap_lms.summer_program.quiz_points._enqueue_contact_field_sync")
    def test_quiz_retake_higher_score_delta_to_total(self, mock_sync):
        """Attempt 1 earns 5, attempt 2 earns 8 in same week:
        cumulative += delta = +3, weekly += full new earned = +8 (so total
        weekly is 5 + 8 = 13). Latest-score for cumulative."""
        student = _ensure_student("04")
        pe_name = _make_pe(self.batch_name, student, "04")
        quiz = _make_quiz()
        q1 = _make_quiz_question("04a", 5, 0)
        q2 = _make_quiz_question("04b", 8, 0)

        # Attempt 1: one correct → 5 earned.
        attempt1 = _make_attempt(student, quiz, [
            {"question": q1, "is_correct": True},
        ])
        handle_attempt_update(attempt1)
        # Allow some sequencing on completed_at — set attempt2's later.

        # Attempt 2: one correct different question → 8 earned.
        attempt2 = _make_attempt(student, quiz, [
            {"question": q2, "is_correct": True},
        ])
        # Force chronological order on completed_at so delta query picks attempt1
        # as the prior-latest.
        frappe.db.set_value(
            "StudentQuizAttempt", attempt1.name,
            "completed_at", "2026-05-12 09:00:00",
            update_modified=False,
        )
        frappe.db.set_value(
            "StudentQuizAttempt", attempt2.name,
            "completed_at", "2026-05-12 10:00:00",
            update_modified=False,
        )
        # Re-fetch attempt2 to get fresh state for the handler call.
        attempt2.reload()
        attempt2.points_earned = 0  # ensure the idempotency anchor is not yet set
        attempt2.save(ignore_permissions=True)

        handle_attempt_update(attempt2)

        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        # Cumulative: 5 + delta(8-5) = 5 + 3 = 8
        self.assertEqual(pe.total_quiz_points, 8,
                         "Cumulative gets delta (5 → 8 = +3)")
        self.assertEqual(pe.total_points, 8)
        # Weekly: 5 + 8 = 13 (effort, not latest)
        self.assertEqual(pe.weekly_quiz_points, 13,
                         "Weekly always adds full new earned (5 + 8 = 13)")

    @patch("tap_lms.summer_program.quiz_points._enqueue_contact_field_sync")
    def test_quiz_retake_lower_score_negative_delta_to_total(self, mock_sync):
        """Attempt 1 earns 8, attempt 2 earns 5 in same week:
        cumulative += delta = -3 (5 + -3 = 2 net), weekly += 5 (effort)."""
        student = _ensure_student("05")
        pe_name = _make_pe(self.batch_name, student, "05")
        quiz = _make_quiz()
        q1 = _make_quiz_question("05a", 8, 0)
        q2 = _make_quiz_question("05b", 5, 0)

        attempt1 = _make_attempt(student, quiz, [
            {"question": q1, "is_correct": True},
        ])
        handle_attempt_update(attempt1)

        attempt2 = _make_attempt(student, quiz, [
            {"question": q2, "is_correct": True},
        ])
        frappe.db.set_value(
            "StudentQuizAttempt", attempt1.name,
            "completed_at", "2026-05-12 09:00:00",
            update_modified=False,
        )
        frappe.db.set_value(
            "StudentQuizAttempt", attempt2.name,
            "completed_at", "2026-05-12 10:00:00",
            update_modified=False,
        )
        attempt2.reload()
        attempt2.points_earned = 0
        attempt2.save(ignore_permissions=True)

        handle_attempt_update(attempt2)

        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        # Cumulative: 8 + delta(5-8) = 8 + -3 = 5
        self.assertEqual(pe.total_quiz_points, 5,
                         "Cumulative gets negative delta (8 → 5 = -3)")
        self.assertEqual(pe.total_points, 5)
        # Weekly: 8 + 5 = 13
        self.assertEqual(pe.weekly_quiz_points, 13,
                         "Weekly always adds full new earned (8 + 5 = 13)")

    @patch("tap_lms.summer_program.quiz_points._enqueue_contact_field_sync")
    def test_quiz_zero_earned_no_pe_update(self, mock_sync):
        """E10: question correct but points=0; all answers wrong but
        failed_points=0. Earned = 0. points_earned written, no PE update."""
        student = _ensure_student("06")
        pe_name = _make_pe(self.batch_name, student, "06")
        quiz = _make_quiz()
        q1 = _make_quiz_question("06", 0, 0)
        attempt = _make_attempt(student, quiz, [
            {"question": q1, "is_correct": True},
        ])

        handle_attempt_update(attempt)

        attempt.reload()
        self.assertEqual(attempt.points_earned, 0,
                         "Zero-earned still writes points_earned so re-runs skip")
        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        self.assertEqual(pe.total_quiz_points, 0)
        self.assertEqual(pe.weekly_quiz_points, 0)
        self.assertEqual(pe.total_points, 0)

    def test_compute_quiz_points_correct_only(self):
        """Pure unit test on the compute helper — no DB write needed."""
        # Use a fake attempt-like object with answers child rows.
        class FakeAns:
            def __init__(self, question, is_correct):
                self.question = question
                self.is_correct = is_correct

        class FakeAttempt:
            def __init__(self, answers):
                self.answers = answers

        quiz = _make_quiz()
        q1 = _make_quiz_question("compute01", 10, 2)
        q2 = _make_quiz_question("compute02", 5, 1)

        attempt = FakeAttempt([
            FakeAns(q1, 1),  # correct → 10
            FakeAns(q2, 0),  # wrong → 1
        ])
        self.assertEqual(compute_quiz_points(attempt), 11)
