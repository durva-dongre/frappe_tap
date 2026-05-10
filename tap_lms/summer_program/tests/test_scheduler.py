"""
Tests for summer_program.scheduler

Regression coverage for the Postgres-compat fix in `_run_grace_notifications`
(was using DATEDIFF/CURDATE/`IN %s` which errors on PG — see lessons L-002, L-005).

The test exercises the corrected query path end-to-end against the test
PG-backed site: a Student with an EngagementState dated 8 days ago should
fall inside a 7-day grace window, and `_run_grace_notifications` should run
without raising. Glific is mocked so we don't actually hit the network.
"""
import frappe
from datetime import date, timedelta
from unittest.mock import patch
from frappe.tests.utils import FrappeTestCase


class TestRunGraceNotifications(FrappeTestCase):

    def setUp(self):
        # Seed a Student with a glific_id so the WHERE filter keeps it.
        self.student_name = frappe.get_doc({
            "doctype": "Student",
            "name1": "Grace Test Student",
            "phone": "+10000000001",
            "glific_id": "glific-grace-test-1",
        }).insert(ignore_permissions=True).name

        # Engagement state with last activity 8 days ago — inside a [7, 10) window.
        eight_days_ago = date.today() - timedelta(days=8)
        frappe.get_doc({
            "doctype": "EngagementState",
            "student": self.student_name,
            "last_activity_date": eight_days_ago,
        }).insert(ignore_permissions=True)

    def tearDown(self):
        # FrappeTestCase rolls back each test in a transaction, but be explicit
        # about cleanup for the Student/EngagementState pair to keep the row-set
        # tidy if a future test in the same class assumes a clean slate.
        for es in frappe.get_all(
            "EngagementState", filters={"student": self.student_name}, pluck="name"
        ):
            frappe.delete_doc("EngagementState", es, force=True)
        if frappe.db.exists("Student", self.student_name):
            frappe.delete_doc("Student", self.student_name, force=True)

    def test_grace_query_runs_on_postgres(self):
        """
        The corrected SQL (CURRENT_DATE - es.last_activity_date)::int with
        `= ANY(%s)` must execute on Postgres without exception, regardless of
        whether the BPR has flows or matching students.
        """
        from tap_lms.summer_program import scheduler

        # Build a tiny stand-in BPR-like object — _run_grace_notifications only
        # reads .name and .grace_notification_flow off the BPR.
        class _StubBPR:
            name = "BPR-TEST-GRACE"
            grace_notification_flow = 9999

        # Stub batch is unused inside the function body but keeps the signature happy.
        class _StubBatch:
            pass

        # Patch the helper that fetches student ids for the BPR — return our seeded student.
        # Patch start_contact_flow so we never hit Glific.
        with patch(
            "tap_lms.summer_program.scheduler._get_students_for_bpr",
            return_value=[self.student_name],
        ), patch(
            "tap_lms.summer_program.scheduler.start_contact_flow",
            return_value={"ok": True},
        ) as mock_flow:
            # Should run cleanly on PG (no DATEDIFF/CURDATE syntax error).
            scheduler._run_grace_notifications(_StubBPR(), _StubBatch(), grace_days=7)

            # Student is 8 days idle, falls in [7, 10) → flow should have been triggered once.
            self.assertEqual(mock_flow.call_count, 1)

    def test_grace_query_handles_empty_student_list(self):
        """
        Empty student-list short-circuits before SQL — guards against the
        old `IN ()` empty-tuple footgun documented in lesson L-005.
        """
        from tap_lms.summer_program import scheduler

        class _StubBPR:
            name = "BPR-TEST-GRACE-EMPTY"
            grace_notification_flow = 9999

        class _StubBatch:
            pass

        with patch(
            "tap_lms.summer_program.scheduler._get_students_for_bpr",
            return_value=[],
        ), patch(
            "tap_lms.summer_program.scheduler.start_contact_flow",
        ) as mock_flow:
            scheduler._run_grace_notifications(_StubBPR(), _StubBatch(), grace_days=7)
            mock_flow.assert_not_called()
