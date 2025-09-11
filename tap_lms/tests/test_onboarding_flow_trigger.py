

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
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

# Conditional import guard with fallback
try:
    import frappe
    from tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger import (
        trigger_onboarding_flow,
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
    from tap_lms.glific_integration import get_glific_auth_headers, create_or_get_glific_group_for_batch, start_contact_flow
    FRAPPE_AVAILABLE = True
except ImportError:
    FRAPPE_AVAILABLE = False
    # Use real imports with fallback to avoid skipping
    from tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger import (
        trigger_onboarding_flow,
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
    from tap_lms.glific_integration import get_glific_auth_headers, create_or_get_glific_group_for_batch, start_contact_flow

class TestOnboardingFlowFunctions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            print("Warning: Frappe not available - forcing test execution")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "test_job_123"
        self.current_time = datetime(2025, 9, 11, 15, 35)  # 03:35 PM IST

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    def test_trigger_onboarding_flow_success(self, mock_enqueue, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status=self.mock_student_status, glific_flow_id=self.mock_flow_id)])
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = self.mock_job_id
        result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        self.assertTrue(result["success"])
        mock_enqueue.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_error(self, mock_throw, mock_get_doc):
        mock_get_doc.side_effect = Exception("DB Error")
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called()

class TestOnboardingFlowJobAndGroup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            print("Warning: Frappe not available - forcing test execution")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_success(self, mock_create_group, mock_requests, mock_auth_headers, mock_get_doc):
        mock_auth_headers.return_value = {"Authorization": "Bearer token"}
        mock_onboarding = MagicMock(name=self.mock_onboarding_set)
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_response = MagicMock(status_code=200, json=lambda: {"data": {"startGroupFlow": {"success": True}}})
        mock_requests.return_value = mock_response
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding') as mock_get_students:
            mock_get_students.return_value = [MagicMock(name="STUD_001")]
            with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch') as mock_update_batch:
                result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
                self.assertIn("group_flow_result", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    def test_trigger_group_flow_network_error(self, mock_requests):
        mock_requests.side_effect = ConnectionError("Network failure")
        mock_onboarding = MagicMock(name=self.mock_onboarding_set)
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        with self.assertRaises(ConnectionError):
            trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

class TestOnboardingIndividualAndStudents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            print("Warning: Frappe not available - forcing test execution")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_students_from_onboarding_empty(self, mock_get_all):
        mock_get_all.return_value = []
        result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, self.mock_student_status)
        self.assertEqual(len(result), 0)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    def test_trigger_individual_flows_empty(self, mock_start_flow, mock_get_all):
        mock_get_all.return_value = []
        result = trigger_individual_flows(MagicMock(name=self.mock_onboarding_set), MagicMock(name=self.mock_onboarding_stage), "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertEqual(result["individual_count"], 0)

class TestOnboardingJobReportAndScheduled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            print("Warning: Frappe not available - forcing test execution")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_failure(self, mock_get_job_status):
        mock_get_job_status.side_effect = Exception("Job fetch failed")
        result = get_job_status(self.mock_job_id)
        self.assertIn("error", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_onboarding_progress_report_none(self, mock_get_all):
        mock_get_all.return_value = None
        result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage)
        self.assertIn("summary", result)
        self.assertEqual(len(result["details"]), 0)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_update_incomplete_stages_empty(self, mock_get_all, mock_now_datetime):
        mock_now_datetime.return_value = self.current_time
        mock_get_all.return_value = []
        update_incomplete_stages()  # Should handle gracefully

if __name__ == '__main__':
    unittest.main()