

# import unittest
# from unittest.mock import Mock, patch, MagicMock
# from datetime import datetime, timedelta

# # Conditional import guard
# try:
#     import frappe
#     from tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger import (
#         trigger_onboarding_flow,
#         _trigger_onboarding_flow_job,
#         trigger_group_flow,
#         trigger_individual_flows,
#         get_stage_flow_statuses,
#         get_students_from_onboarding,
#         update_student_stage_progress,
#         update_student_stage_progress_batch,
#         get_job_status,
#         get_onboarding_progress_report,
#         update_incomplete_stages
#     )
#     from tap_lms.glific_integration import get_glific_auth_headers, create_or_get_glific_group_for_batch, start_contact_flow
#     FRAPPE_AVAILABLE = True
# except ImportError:
#     FRAPPE_AVAILABLE = False
#     def trigger_onboarding_flow(*args, **kwargs): pass
#     def _trigger_onboarding_flow_job(*args, **kwargs): pass
#     def trigger_group_flow(*args, **kwargs): pass
#     def trigger_individual_flows(*args, **kwargs): pass
#     def get_stage_flow_statuses(*args, **kwargs): pass
#     def get_students_from_onboarding(*args, **kwargs): pass
#     def update_student_stage_progress(*args, **kwargs): pass
#     def update_student_stage_progress_batch(*args, **kwargs): pass
#     def get_job_status(*args, **kwargs): pass
#     def get_onboarding_progress_report(*args, **kwargs): pass
#     def update_incomplete_stages(*args, **kwargs): pass
#     def get_glific_auth_headers(*args, **kwargs): pass
#     def create_or_get_glific_group_for_batch(*args, **kwargs): pass
#     def start_contact_flow(*args, **kwargs): pass

# class TestOnboardingFlowFunctions(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests (run via 'bench --site <site> test')")

#     def setUp(self):
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"
#         self.mock_job_id = "test_job_123"
#         self.current_time = datetime(2025, 9, 11, 15, 15)  # 03:15 PM IST

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
#     def test_trigger_onboarding_flow_success(self, mock_enqueue, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status=self.mock_student_status, glific_flow_id=self.mock_flow_id)])
#         mock_onboarding = MagicMock(status="Processed")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         mock_enqueue.return_value = self.mock_job_id
#         result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         self.assertTrue(result["success"])
#         mock_enqueue.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_error_handling(self, mock_throw, mock_get_doc):
#         mock_get_doc.side_effect = Exception("DB Error")
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_empty(self, mock_get_doc):
#         mock_stage = MagicMock(stage_flows=[])
#         mock_get_doc.return_value = mock_stage
#         result = get_stage_flow_statuses(self.mock_onboarding_stage)
#         self.assertIn("statuses", result)
#         self.assertEqual(len(result["statuses"]), 0)

# class TestOnboardingFlowJobAndGroup(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     def setUp(self):
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
#     def test_trigger_group_flow_success(self, mock_create_group, mock_requests, mock_auth_headers, mock_get_doc):
#         mock_auth_headers.return_value = {"Authorization": "Bearer token"}
#         mock_onboarding = MagicMock(name=self.mock_onboarding_set)
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_response = MagicMock(status_code=200, json=lambda: {"data": {"startGroupFlow": {"success": True}}})
#         mock_requests.return_value = mock_response
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding') as mock_get_students:
#             mock_get_students.return_value = [MagicMock(name="STUD_001")]
#             with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch') as mock_update_batch:
#                 result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#                 self.assertIn("group_flow_result", result)
#                 self.assertEqual(result["group_count"], 1)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     def test_trigger_group_flow_network_error(self, mock_requests):
#         mock_requests.side_effect = ConnectionError("Network failure")
#         mock_onboarding = MagicMock(name=self.mock_onboarding_set)
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         with self.assertRaises(ConnectionError):
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     def test_trigger_onboarding_flow_job_group_error(self, mock_auth_headers, mock_get_doc):
#         mock_auth_headers.return_value = {}
#         mock_get_doc.side_effect = [MagicMock(), MagicMock(), MagicMock(api_url="https://api.glific.org")]
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow') as mock_group_flow:
#             mock_group_flow.return_value = {"error": "Auth failed"}
#             result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
#             self.assertIn("error", result)

# class TestOnboardingIndividualAndStudents(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     def setUp(self):
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_get_students_from_onboarding_no_match(self, mock_get_all):
#         mock_get_all.return_value = []
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, "completed")
#         self.assertEqual(len(result), 0)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     def test_trigger_individual_flows_failure(self, mock_update_progress, mock_start_flow, mock_get_all):
#         mock_students = [MagicMock(name="STUD_001", glific_id="glific_1")]
#         mock_get_all.return_value = [{"student_id": s.name, "glific_id": s.glific_id} for s in mock_students]
#         mock_start_flow.return_value = False
#         result = trigger_individual_flows(MagicMock(name=self.mock_onboarding_set), MagicMock(name=self.mock_onboarding_stage), "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertEqual(result["individual_count"], 0)
#         self.assertEqual(mock_start_flow.call_count, 1)

# class TestOnboardingJobReportAndScheduled(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
#     def test_get_job_status_pending(self, mock_get_job_status):
#         mock_get_job_status.return_value = "pending"
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.Job.fetch') as mock_fetch:
#             mock_fetch.side_effect = Exception("Job not found")
#             result = get_job_status(self.mock_job_id)
#             self.assertEqual(result["status"], "pending")
#             self.assertNotIn("results", result)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_onboarding_progress_report_empty(self, mock_get_doc, mock_get_all):
#         mock_get_all.return_value = []
#         result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage)
#         self.assertIn("summary", result)
#         self.assertEqual(len(result["details"]), 0)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_update_incomplete_stages_no_change(self, mock_get_doc, mock_get_all, mock_now_datetime):
#         mock_now_datetime.return_value = self.current_time
#         mock_get_all.return_value = [{"name": "progress_1", "status": "completed", "start_timestamp": self.current_time}]
#         mock_progress = MagicMock()
#         mock_get_doc.return_value = mock_progress
#         update_incomplete_stages()
#         self.assertEqual(mock_progress.status, "completed")
#         self.assertEqual(mock_progress.save.call_count, 0)

# if __name__ == '__main__':
#     unittest.main()


import unittest
from unittest.mock import patch, MagicMock
import frappe
import json
from datetime import datetime, timedelta
from tap_lms.tap_lms import (
    _trigger_onboarding_flow_job,
    trigger_group_flow,
    trigger_individual_flows,
    get_stage_flow_statuses,
    get_students_from_onboarding,
    update_student_stage_progress,
    update_student_stage_progress_batch,
    get_job_status,
    get_onboarding_progress_report,
    update_incomplete_stages
)

class TestOnboardingFlow(unittest.TestCase):
    def setUp(self):
        # Mock Frappe functions to avoid real database calls
        self.mock_get_doc = patch('frappe.get_doc').start()
        self.mock_get_all = patch('frappe.get_all').start()
        self.mock_enqueue = patch('frappe.enqueue').start()
        self.mock_logger = patch('frappe.logger').start()
        self.mock_throw = patch('frappe.throw').start()
        self.mock_db_commit = patch('frappe.db.commit').start()
        self.mock_new_doc = patch('frappe.new_doc').start()
        self.mock_requests_post = patch('requests.post').start()
        self.mock_get_redis_conn = patch('frappe.utils.background_jobs.get_redis_conn').start()
        self.mock_job_fetch = patch('rq.job.Job.fetch').start()

        # Setup common mock objects
        self.mock_onboarding = MagicMock(
            name="test_onboarding",
            status="Processed"
        )
        self.mock_stage = MagicMock(
            name="test_stage",
            is_active=True,
            stage_flows=[
                {"student_status": "not_started", "glific_flow_id": "123", "flow_type": "Group"},
                {"student_status": "assigned", "glific_flow_id": "124", "flow_type": "Individual"}
            ]
        )
        self.mock_glific_settings = MagicMock(api_url="https://glific.test/api")
        self.mock_student = MagicMock(
            name="student_1",
            name1="Test Student",
            glific_id="glific_123",
            phone="1234567890"
        )

        # Default return values for get_doc
        self.mock_get_doc.side_effect = lambda doctype, name: {
            "Backend Student Onboarding": self.mock_onboarding,
            "OnboardingStage": self.mock_stage,
            "Glific Settings": self.mock_glific_settings,
            "Student": self.mock_student
        }.get(doctype, MagicMock())

    def tearDown(self):
        patch.stopall()

    
    def test_trigger_group_flow_success(self):
        """Test successful group flow trigger"""
        mock_contact_group = MagicMock(group_id="group_123")
        self.mock_get_doc.return_value = mock_contact_group
        self.mock_requests_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "data": {
                    "startGroupFlow": {
                        "success": True,
                        "errors": []
                    }
                }
            }
        )
        self.mock_get_all.return_value = [
            {"student_id": "student_1"}
        ]
        result = trigger_group_flow(
            self.mock_onboarding,
            self.mock_stage,
            "mock_token",
            "not_started",
            "123"
        )
        self.assertIn("group_flow_result", result)
        self.assertEqual(result["group_count"], 1)
        self.mock_requests_post.assert_called_once()

    def test_trigger_individual_flows_success(self):
        """Test successful individual flows trigger"""
        self.mock_get_all.return_value = [
            {"student_id": "student_1"}
        ]
        with patch('tap_lms.tap_lms.start_contact_flow', return_value=True):
            result = trigger_individual_flows(
                self.mock_onboarding,
                self.mock_stage,
                "mock_token",
                "not_started",
                "124"
            )
            self.assertEqual(result["individual_count"], 1)
            self.assertEqual(result["error_count"], 0)
            self.assertEqual(len(result["individual_flow_results"]), 1)
            self.assertTrue(result["individual_flow_results"][0]["success"])

    def test_get_stage_flow_statuses_new_structure(self):
        """Test get_stage_flow_statuses with new stage_flows structure"""
        result = get_stage_flow_statuses("test_stage")
        self.assertEqual(result, {"statuses": ["not_started", "assigned"]})

    def test_get_stage_flow_statuses_legacy(self):
        """Test get_stage_flow_statuses with legacy structure"""
        self.mock_stage.stage_flows = []
        self.mock_stage.glific_flow_id = "123"
        result = get_stage_flow_statuses("test_stage")
        self.assertEqual(result["statuses"], [
            "not_started", "assigned", "in_progress",
            "completed", "incomplete", "skipped"
        ])

    def test_get_students_from_onboarding_with_status(self):
        """Test get_students_from_onboarding with status filter"""
        self.mock_get_all.side_effect = [
            [{"student_id": "student_1"}],  # Backend Students
            [{"name": "progress_1"}]  # StudentStageProgress
        ]
        result = get_students_from_onboarding(self.mock_onboarding, "test_stage", "not_started")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "student_1")

    def test_get_students_from_onboarding_not_started(self):
        """Test get_students_from_onboarding for not_started status"""
        self.mock_get_all.side_effect = [
            [{"student_id": "student_1"}],  # Backend Students
            []  # No StudentStageProgress
        ]
        result = get_students_from_onboarding(self.mock_onboarding, "test_stage", "not_started")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "student_1")

    def test_update_student_stage_progress_new(self):
        """Test creating new StudentStageProgress"""
        self.mock_get_all.return_value = []
        mock_progress = MagicMock()
        self.mock_new_doc.return_value = mock_progress
        update_student_stage_progress(self.mock_student, self.mock_stage)
        self.mock_new_doc.assert_called_with("StudentStageProgress")
        mock_progress.insert.assert_called_once()

    def test_update_student_stage_progress_existing(self):
        """Test updating existing StudentStageProgress"""
        self.mock_get_all.return_value = [{"name": "progress_1"}]
        mock_progress = MagicMock(status="not_started")
        self.mock_get_doc.return_value = mock_progress
        update_student_stage_progress(self.mock_student, self.mock_stage)
        self.assertEqual(mock_progress.status, "assigned")
        mock_progress.save.assert_called_once()

    def test_get_onboarding_progress_report(self):
        """Test generating onboarding progress report"""
        self.mock_get_all.side_effect = [
            [{"name": "progress_1", "student": "student_1", "stage": "test_stage", "status": "assigned"}],  # StudentStageProgress
            [{"student_id": "student_1"}]  # Backend Students
        ]
        result = get_onboarding_progress_report(set="test_onboarding", stage="test_stage", status="assigned")
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["assigned"], 1)
        self.assertEqual(len(result["details"]), 1)

    def test_update_incomplete_stages(self):
        """Test updating incomplete stages"""
        three_days_ago = datetime.now() - timedelta(days=3)
        self.mock_get_all.return_value = [
            {"name": "progress_1", "student": "student_1", "stage": "test_stage", "start_timestamp": three_days_ago}
        ]
        mock_progress = MagicMock(status="assigned")
        self.mock_get_doc.return_value = mock_progress
        update_incomplete_stages()
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()

if __name__ == '__main__':
    unittest.main()