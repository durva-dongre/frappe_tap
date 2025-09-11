# import unittest
# from unittest.mock import Mock, patch, MagicMock
# from datetime import datetime, timedelta
# import time
# import os

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
#         self.current_time = datetime(2025, 9, 11, 12, 50)  # 12:50 PM IST, September 11, 2025

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
#         self.assertEqual(result["job_id"], self.mock_job_id)
#         mock_enqueue.assert_called_once()
#         mock_throw.assert_not_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_invalid_stage(self, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=False)
#         mock_get_doc.return_value = mock_stage
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("Selected Onboarding Stage is not active"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_success(self, mock_get_doc):
#         mock_stage = MagicMock(stage_flows=[MagicMock(student_status="not_started"), MagicMock(student_status="completed")])
#         mock_get_doc.return_value = mock_stage
#         result = get_stage_flow_statuses(self.mock_onboarding_stage)
#         self.assertIn("statuses", result)
#         self.assertEqual(len(result["statuses"]), 2)

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

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_trigger_onboarding_flow_job_success(self, mock_get_doc, mock_auth_headers):
#         mock_auth_headers.return_value = {"Authorization": "Bearer token"}
#         mock_get_doc.return_value = MagicMock()
#         result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
#         self.assertIn("success", result)
#         self.assertTrue(result["success"])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_trigger_group_flow_success(self, mock_get_doc, mock_requests):
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_response = MagicMock(status_code=200, json=lambda: {"data": {"startGroupFlow": {"success": True}}})
#         mock_requests.return_value = mock_response
#         result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertIn("group_flow_result", result)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_trigger_group_flow_failure(self, mock_get_doc, mock_requests):
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_response = MagicMock(status_code=500, text="Server Error")
#         mock_requests.return_value = mock_response
#         with self.assertRaises(Exception):
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

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
#     def test_get_students_from_onboarding_success(self, mock_get_all):
#         mock_get_all.return_value = [{"student_id": "STUD_001"}]
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, self.mock_student_status)
#         self.assertEqual(len(result), 1)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_get_students_from_onboarding_empty(self, mock_get_all):
#         mock_get_all.return_value = []
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), None, None)
#         self.assertEqual(result, [])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
#     def test_update_student_stage_progress_new(self, mock_new_doc, mock_get_all):
#         mock_get_all.return_value = []
#         mock_progress = MagicMock()
#         mock_new_doc.return_value = mock_progress
#         update_student_stage_progress(MagicMock(), MagicMock())
#         mock_new_doc.assert_called_once_with("StudentStageProgress")
#         mock_progress.insert.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_update_student_stage_progress_existing(self, mock_get_doc, mock_get_all):
#         mock_get_all.return_value = [{"name": "progress_1"}]
#         mock_progress = MagicMock(status="not_started")
#         mock_get_doc.return_value = mock_progress
#         update_student_stage_progress(MagicMock(), MagicMock())
#         self.assertEqual(mock_progress.status, "assigned")
#         mock_progress.save.assert_called_once()

# class TestOnboardingJobReportAndScheduled(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
#     def test_get_job_status_success(self, mock_get_job_status):
#         mock_get_job_status.return_value = "finished"
#         result = get_job_status("test_job")
#         self.assertEqual(result["status"], "complete")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_get_onboarding_progress_report_empty(self, mock_get_all):
#         mock_get_all.return_value = []
#         result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage)
#         self.assertIn("summary", result)
#         self.assertEqual(result["summary"], {})

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
#     def test_update_incomplete_stages_success(self, mock_now_datetime, mock_get_doc, mock_get_all):
#         mock_now_datetime.return_value = self.current_time
#         mock_get_all.return_value = [{"name": "progress_1", "status": "assigned", "start_timestamp": self.current_time - timedelta(days=5)}]
#         mock_progress = MagicMock()
#         mock_get_doc.return_value = mock_progress
#         update_incomplete_stages()
#         self.assertEqual(mock_progress.status, "incomplete")
#         mock_progress.save.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_update_incomplete_stages_no_records(self, mock_get_all):
#         mock_get_all.return_value = []
#         update_incomplete_stages()  # Should handle gracefully

# class TestOnboardingFlowRunner:
#     @staticmethod
#     def run_all_tests(verbosity=2):
#         test_suite = unittest.TestSuite()
#         test_classes = [
#             TestOnboardingFlowFunctions,
#             TestOnboardingFlowJobAndGroup,
#             TestOnboardingIndividualAndStudents,
#             TestOnboardingJobReportAndScheduled
#         ]
#         for test_class in test_classes:
#             tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
#             test_suite.addTests(tests)
#         runner = unittest.TextTestRunner(verbosity=verbosity, stream=sys.stdout, buffer=True)
#         result = runner.run(test_suite)
#         print(f"\n{'='*60}\nTEST SUMMARY\n{'='*60}")
#         print(f"Tests run: {result.testsRun}")
#         print(f"Failures: {len(result.failures)}")
#         print(f"Errors: {len(result.errors)}")
#         print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
#         success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100) if result.testsRun > 0 else 0
#         print(f"Success Rate: {success_rate:.1f}%")
#         return result.wasSuccessful()

# if __name__ == '__main__':
#     success = TestOnboardingFlowRunner.run_all_tests()
#     sys.exit(0 if success else 1)

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import time
import os

# Conditional import guard
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
    FRAPPE_AVAILABLE = True
except ImportError:
    FRAPPE_AVAILABLE = False
    def trigger_onboarding_flow(*args, **kwargs): pass
    def _trigger_onboarding_flow_job(*args, **kwargs): pass
    def trigger_group_flow(*args, **kwargs): pass
    def trigger_individual_flows(*args, **kwargs): pass
    def get_stage_flow_statuses(*args, **kwargs): pass
    def get_students_from_onboarding(*args, **kwargs): pass
    def update_student_stage_progress(*args, **kwargs): pass
    def update_student_stage_progress_batch(*args, **kwargs): pass
    def get_job_status(*args, **kwargs): pass
    def get_onboarding_progress_report(*args, **kwargs): pass
    def update_incomplete_stages(*args, **kwargs): pass

class TestOnboardingFlowFunctions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests (run via 'bench --site <site> test')")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "test_job_123"
        self.current_time = datetime(2025, 9, 11, 13, 16)  # 01:16 PM IST, September 11, 2025

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
    def test_trigger_onboarding_flow_missing_params(self, mock_throw, mock_get_doc):
        with self.assertRaises(Exception):
            trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(_("Both Backend Student Onboarding Set and Onboarding Stage are required"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_success(self, mock_get_doc):
        mock_stage = MagicMock(stage_flows=[MagicMock(student_status="not_started"), MagicMock(student_status="in_progress")])
        mock_get_doc.return_value = mock_stage
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        self.assertIn("statuses", result)
        self.assertEqual(len(result["statuses"]), 2)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_empty(self, mock_get_doc):
        mock_stage = MagicMock(stage_flows=[])
        mock_get_doc.return_value = mock_stage
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        self.assertIn("statuses", result)
        self.assertEqual(len(result["statuses"]), 0)

class TestOnboardingFlowJobAndGroup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_job_success(self, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {"Authorization": "Bearer token"}
        mock_get_doc.return_value = MagicMock()
        result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
        self.assertIn("success", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_group_flow_success(self, mock_get_doc, mock_requests):
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_response = MagicMock(status_code=200, json=lambda: {"data": {"startGroupFlow": {"success": True}}})
        mock_requests.return_value = mock_response
        result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertIn("group_flow_result", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_group_flow_api_error(self, mock_get_doc, mock_requests):
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_response = MagicMock(status_code=500, text="Server Error")
        mock_requests.return_value = mock_response
        with self.assertRaises(Exception):
            trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

class TestOnboardingIndividualAndStudents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_students_from_onboarding_success(self, mock_get_all):
        mock_get_all.return_value = [{"student_id": "STUD_001"}]
        result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, self.mock_student_status)
        self.assertEqual(len(result), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_students_from_onboarding_empty(self, mock_get_all):
        mock_get_all.return_value = []
        result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), None, None)
        self.assertEqual(result, [])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    def test_trigger_individual_flows_success(self, mock_update_progress, mock_start_flow, mock_get_all):
        mock_student = MagicMock(name="STUD_001", glific_id="glific_1")
        mock_get_all.return_value = [{"student_id": "STUD_001"}]
        mock_start_flow.return_value = True
        result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertGreaterEqual(result["individual_count"], 1)
        mock_update_progress.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
    def test_update_student_stage_progress_new(self, mock_new_doc, mock_get_all):
        mock_get_all.return_value = []
        mock_progress = MagicMock()
        mock_new_doc.return_value = mock_progress
        update_student_stage_progress(MagicMock(), MagicMock())
        mock_new_doc.assert_called_once_with("StudentStageProgress")
        mock_progress.insert.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_student_stage_progress_batch_success(self, mock_get_doc, mock_get_all):
        mock_students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        mock_get_all.return_value = []
        mock_progress = MagicMock()
        mock_get_doc.return_value = mock_progress
        update_student_stage_progress_batch(mock_students, MagicMock())
        self.assertEqual(mock_progress.status, "assigned")

class TestOnboardingJobReportAndScheduled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_success(self, mock_get_job_status):
        mock_get_job_status.return_value = "finished"
        result = get_job_status("test_job")
        self.assertEqual(result["status"], "complete")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_onboarding_progress_report_empty(self, mock_get_all):
        mock_get_all.return_value = []
        result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage)
        self.assertIn("summary", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
    def test_update_incomplete_stages_success(self, mock_now_datetime, mock_get_doc, mock_get_all):
        mock_now_datetime.return_value = self.current_time
        mock_get_all.return_value = [{"name": "progress_1", "status": "assigned", "start_timestamp": self.current_time - timedelta(days=5)}]
        mock_progress = MagicMock()
        mock_get_doc.return_value = mock_progress
        update_incomplete_stages()
        self.assertEqual(mock_progress.status, "incomplete")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_update_incomplete_stages_no_records(self, mock_get_all):
        mock_get_all.return_value = []
        update_incomplete_stages()  # Should handle gracefully

class TestOnboardingFlowRunner:
    @staticmethod
    def run_all_tests(verbosity=2):
        test_suite = unittest.TestSuite()
        test_classes = [
            TestOnboardingFlowFunctions,
            TestOnboardingFlowJobAndGroup,
            TestOnboardingIndividualAndStudents,
            TestOnboardingJobReportAndScheduled
        ]
        for test_class in test_classes:
            tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
            test_suite.addTests(tests)
        runner = unittest.TextTestRunner(verbosity=verbosity, stream=sys.stdout, buffer=True)
        result = runner.run(test_suite)
        print(f"\n{'='*60}\nTEST SUMMARY\n{'='*60}")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100) if result.testsRun > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        return result.wasSuccessful()

if __name__ == '__main__':
    success = TestOnboardingFlowRunner.run_all_tests()
    sys.exit(0 if success else 1)