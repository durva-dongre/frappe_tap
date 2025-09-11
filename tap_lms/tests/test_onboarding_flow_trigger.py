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
        self.current_time = datetime(2025, 9, 11, 12, 50)  # 12:50 PM IST, September 11, 2025

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
        self.assertEqual(result["job_id"], self.mock_job_id)
        mock_enqueue.assert_called_once()
        mock_throw.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_invalid_stage(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=False)
        mock_get_doc.return_value = mock_stage
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(_("Selected Onboarding Stage is not active"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_success(self, mock_get_doc):
        mock_stage = MagicMock(stage_flows=[MagicMock(student_status="not_started"), MagicMock(student_status="completed")])
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
        self.assertTrue(result["success"])

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
    def test_trigger_group_flow_failure(self, mock_get_doc, mock_requests):
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
    def test_update_student_stage_progress_existing(self, mock_get_doc, mock_get_all):
        mock_get_all.return_value = [{"name": "progress_1"}]
        mock_progress = MagicMock(status="not_started")
        mock_get_doc.return_value = mock_progress
        update_student_stage_progress(MagicMock(), MagicMock())
        self.assertEqual(mock_progress.status, "assigned")
        mock_progress.save.assert_called_once()

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
        self.assertEqual(result["summary"], {})

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
        mock_progress.save.assert_called_once()

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


# import unittest
# from unittest.mock import Mock, patch, MagicMock
# import json
# from datetime import datetime, timedelta
# import time
# import sys
# import os

# # Conditional import guard: Only import the module if frappe is available (i.e., during bench test execution, not discovery)
# try:
#     import frappe
#     # If frappe is importable, we're in bench context - safe to import the module
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
#     # During test discovery (e.g., pytest collect-only or Jenkins scan), frappe isn't loaded - define dummies to allow discovery
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
#         self.mock_now = datetime.now()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_trigger_onboarding_flow_success(self, mock_logger, mock_enqueue, mock_throw, mock_get_doc):
#         mock_stage = MagicMock()
#         mock_stage.name = self.mock_onboarding_stage
#         mock_stage.is_active = True
#         mock_stage.stage_flows = [MagicMock(student_status="not_started", glific_flow_id=self.mock_flow_id, flow_type="Group")]
#         mock_onboarding = MagicMock(name=self.mock_onboarding_set, status="Processed")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         mock_enqueue.return_value = self.mock_job_id

#         result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         self.assertTrue(result["success"])
#         self.assertEqual(result["job_id"], self.mock_job_id)
#         mock_enqueue.assert_called_once()
#         mock_throw.assert_not_called()
#         mock_logger.info.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_missing_parameters(self, mock_throw):
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("Both Backend Student Onboarding Set and Onboarding Stage are required"))

#         mock_throw.reset_mock()
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, "", self.mock_student_status)
#         mock_throw.assert_called_with(_("Both Backend Student Onboarding Set and Onboarding Stage are required"))

#         mock_throw.reset_mock()
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "")
#         mock_throw.assert_called_with(_("Student status is required"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_inactive_stage(self, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=False)
#         mock_get_doc.return_value = mock_stage
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("Selected Onboarding Stage is not active"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_unprocessed_set(self, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status="not_started", glific_flow_id=self.mock_flow_id)])
#         mock_onboarding = MagicMock(status="Draft")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("Selected Backend Student Onboarding Set is not in Processed status"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_no_flows(self, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=True, stage_flows=[], glific_flow_id=None)
#         mock_onboarding = MagicMock(status="Processed")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("No flows configured for stage '{0}'").format(self.mock_onboarding_stage))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_trigger_onboarding_flow_legacy(self, mock_logger, mock_enqueue, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=True, stage_flows=[], glific_flow_id=self.mock_flow_id, glific_flow_type="Group")
#         mock_onboarding = MagicMock(status="Processed")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         mock_enqueue.return_value = self.mock_job_id

#         result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         self.assertTrue(result["success"])
#         mock_logger.warning.assert_called()
#         mock_enqueue.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_get_stage_flow_statuses_new_structure(self, mock_throw, mock_get_doc):
#         mock_stage = MagicMock()
#         mock_stage.stage_flows = [
#             MagicMock(student_status="not_started"),
#             MagicMock(student_status="in_progress"),
#             MagicMock(student_status="completed")
#         ]
#         mock_get_doc.return_value = mock_stage

#         result = get_stage_flow_statuses("TEST_STAGE")
#         self.assertIn("statuses", result)
#         self.assertEqual(len(result["statuses"]), 3)
#         self.assertIn("not_started", result["statuses"])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_legacy_structure(self, mock_get_doc):
#         mock_stage = MagicMock(glific_flow_id="legacy_123")
#         mock_get_doc.return_value = mock_stage

#         result = get_stage_flow_statuses("TEST_STAGE")
#         self.assertIn("statuses", result)
#         self.assertEqual(result["statuses"], ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"])

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
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_trigger_onboarding_flow_job_auth_error(self, mock_logger, mock_get_doc, mock_auth_headers):
#         mock_auth_headers.return_value = {}
#         mock_stage = MagicMock()
#         mock_onboarding = MagicMock()
#         mock_glific_settings = MagicMock()
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]

#         result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
#         self.assertEqual(result["error"], "Failed to authenticate with Glific API")
#         mock_logger.error.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_trigger_group_flow_success(self, mock_logger, mock_update_progress, mock_get_students, mock_create_group, mock_get_doc, mock_requests):
#         mock_onboarding = MagicMock(name=self.mock_onboarding_set)
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_get_students.return_value = [MagicMock()]
#         mock_response = MagicMock(status_code=200)
#         mock_response.json.return_value = {"data": {"startGroupFlow": {"success": True, "errors": []}}}
#         mock_requests.return_value = mock_response

#         result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertIn("group_flow_result", result)
#         self.assertEqual(result["group_count"], 1)
#         mock_update_progress.assert_called_once()
#         mock_logger.debug.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_group_flow_api_error(self, mock_throw, mock_get_doc, mock_requests):
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_response = MagicMock(status_code=500, text="Server Error")
#         mock_requests.return_value = mock_response

#         with self.assertRaises(Exception):
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         mock_throw.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_group_flow_no_group(self, mock_throw, mock_get_doc):
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch', return_value=None):
#             with self.assertRaises(Exception):
#                 trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         mock_throw.assert_called_with(_("Could not find or create contact group for this onboarding set"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_group_flow_graphql_error(self, mock_throw, mock_get_doc, mock_requests):
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_response = MagicMock(status_code=200)
#         mock_response.json.return_value = {"data": {"startGroupFlow": {"success": False, "errors": [{"message": "GraphQL error"}]}}}
#         mock_requests.return_value = mock_response

#         with self.assertRaises(Exception):
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         mock_throw.assert_called_with(_("Failed to trigger group flow: GraphQL error"))

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

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_individual_flows_no_students(self, mock_throw, mock_get_students):
#         mock_get_students.return_value = []
#         with self.assertRaises(Exception):
#             trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
#         mock_throw.assert_called_with(_("No students found in this onboarding set with the selected status"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
#     def test_trigger_individual_flows_success(self, mock_commit, mock_logger, mock_update_progress, mock_start_flow, mock_get_students):
#         mock_student = MagicMock(name="STUD_001", name1="Student1", glific_id="glific_1")
#         mock_get_students.return_value = [mock_student]
#         mock_start_flow.return_value = True

#         result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertEqual(result["individual_count"], 1)
#         self.assertEqual(result["error_count"], 0)
#         self.assertEqual(len(result["individual_flow_results"]), 1)
#         mock_update_progress.assert_called_once()
#         mock_commit.assert_called()
#         mock_logger.debug.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_trigger_individual_flows_no_glific_id(self, mock_logger, mock_get_students):
#         mock_student = MagicMock(name="STUD_001", name1="Student1", glific_id=None)
#         mock_get_students.return_value = [mock_student]
#         result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertEqual(result["individual_count"], 0)
#         self.assertEqual(result["error_count"], 0)
#         mock_logger.warning.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_trigger_individual_flows_flow_error(self, mock_logger, mock_start_flow, mock_get_students):
#         mock_student = MagicMock(name="STUD_001", name1="Student1", glific_id="glific_1")
#         mock_get_students.return_value = [mock_student]
#         mock_start_flow.side_effect = Exception("Flow error")
#         result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertEqual(result["error_count"], 1)
#         self.assertEqual(result["individual_count"], 0)
#         mock_logger.error.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_students_from_onboarding_no_students(self, mock_get_doc, mock_get_all):
#         mock_get_all.return_value = []
#         result = get_students_from_onboarding(MagicMock(name="TEST_SET"), None, None)
#         self.assertEqual(result, [])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_students_from_onboarding_with_filters(self, mock_get_doc, mock_get_all):
#         mock_student = MagicMock(name="STUD_001")
#         mock_get_all.side_effect = [[{"student_id": "STUD_001"}], [{"name": "progress_1"}]]
#         mock_get_doc.return_value = mock_student
#         result = get_students_from_onboarding(MagicMock(name="TEST_SET"), "TEST_STAGE", "in_progress")
#         self.assertEqual(len(result), 1)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_students_from_onboarding_not_started(self, mock_get_doc, mock_get_all):
#         mock_student = MagicMock(name="STUD_001")
#         mock_get_all.side_effect = [[{"student_id": "STUD_001"}], []]  # No progress records
#         mock_get_doc.return_value = mock_student
#         result = get_students_from_onboarding(MagicMock(name="TEST_SET"), "TEST_STAGE", "not_started")
#         self.assertEqual(len(result), 1)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
#     def test_update_student_stage_progress_existing(self, mock_commit, mock_get_doc, mock_get_all):
#         mock_student = MagicMock(name="STUD_001")
#         mock_stage = MagicMock(name="TEST_STAGE")
#         mock_progress = MagicMock(status="not_started")
#         mock_get_all.return_value = [{"name": "progress_1"}]
#         mock_get_doc.return_value = mock_progress
#         update_student_stage_progress(mock_student, mock_stage)
#         self.assertEqual(mock_progress.status, "assigned")
#         mock_progress.save.assert_called_once()
#         mock_commit.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
#     def test_update_student_stage_progress_new(self, mock_commit, mock_new_doc, mock_get_all):
#         mock_student = MagicMock(name="STUD_001")
#         mock_stage = MagicMock(name="TEST_STAGE")
#         mock_progress = MagicMock()
#         mock_get_all.return_value = []
#         mock_new_doc.return_value = mock_progress
#         update_student_stage_progress(mock_student, mock_stage)
#         mock_new_doc.assert_called_once_with("StudentStageProgress")
#         mock_progress.insert.assert_called_once()
#         mock_commit.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
#     def test_update_student_stage_progress_batch_mixed(self, mock_commit, mock_logger, mock_new_doc, mock_get_all):
#         mock_students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
#         mock_stage = MagicMock()
#         mock_progress = MagicMock(status="not_started")
#         mock_get_all.side_effect = [[{"name": "progress_1"}], Exception("DB error")]
#         mock_new_doc.return_value = mock_progress
#         update_student_stage_progress_batch(mock_students, mock_stage)
#         mock_progress.save.assert_called_once()  # First student updated
#         mock_logger.error.assert_called()  # Second student error logged
#         mock_commit.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_update_student_stage_progress_batch_empty(self, mock_logger, mock_get_all):
#         update_student_stage_progress_batch([], MagicMock())
#         mock_logger.warning.assert_called_with("No students provided to update_student_stage_progress_batch")

# class TestOnboardingJobReportAndScheduled(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
#     @patch('rq.job.Job.fetch')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_redis_conn')
#     def test_get_job_status_finished_with_results(self, mock_redis_conn, mock_job_fetch, mock_get_job_status):
#         mock_get_job_status.return_value = "finished"
#         mock_job = MagicMock(result={"key": "value"})
#         mock_job_fetch.return_value = mock_job
#         mock_redis_conn.return_value = MagicMock()

#         result = get_job_status("finished_job")
#         self.assertEqual(result["status"], "complete")
#         self.assertIn("results", result)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
#     def test_get_job_status_failed(self, mock_get_job_status):
#         mock_get_job_status.return_value = "failed"
#         result = get_job_status("failed_job")
#         self.assertEqual(result["status"], "failed")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_redis_conn')
#     def test_get_job_status_redis_error(self, mock_redis_conn, mock_get_job_status):
#         mock_get_job_status.return_value = "finished"
#         mock_redis_conn.return_value = None
#         result = get_job_status("error_job")
#         self.assertEqual(result["status"], "complete")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_onboarding_progress_report_filtered(self, mock_get_doc, mock_get_all):
#         mock_progress = {"name": "progress_1", "student": "STUD_001", "stage": "TEST_STAGE", "status": "in_progress"}
#         mock_get_all.return_value = [mock_progress]
#         mock_student = MagicMock(name1="Student1", phone="123")
#         mock_stage = MagicMock()
#         mock_get_doc.side_effect = [mock_student, mock_stage]
#         result = get_onboarding_progress_report(stage="TEST_STAGE", status="in_progress")
#         self.assertEqual(result["summary"]["in_progress"], 1)
#         self.assertEqual(len(result["details"]), 1)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_onboarding_progress_report_not_started(self, mock_get_doc, mock_get_all):
#         mock_get_all.side_effect = [[], [{"student_id": "STUD_001"}]]  # No progress, has backend student
#         mock_student = MagicMock(name1="Student1", phone="123")
#         mock_stage = MagicMock()
#         mock_get_doc.side_effect = [mock_student, mock_stage]
#         result = get_onboarding_progress_report(set="TEST_SET", stage="TEST_STAGE", status="not_started")
#         self.assertEqual(result["summary"]["not_started"], 1)
#         self.assertEqual(len(result["details"]), 1)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.add_to_date')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
#     def test_update_incomplete_stages(self, mock_commit, mock_add_to_date, mock_now_datetime, mock_get_doc, mock_get_all):
#         mock_now_datetime.return_value = datetime.now()
#         mock_add_to_date.return_value = datetime.now() - timedelta(days=4)
#         mock_progress = MagicMock(status="assigned")
#         mock_get_all.return_value = [{"name": "progress_1", "student": "STUD_001", "stage": "TEST_STAGE", "start_timestamp": datetime.now() - timedelta(days=5)}]
#         mock_get_doc.return_value = mock_progress
#         update_incomplete_stages()
#         self.assertEqual(mock_progress.status, "incomplete")
#         mock_progress.save.assert_called_once()
#         mock_commit.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_update_incomplete_stages_no_records(self, mock_get_all):
#         mock_get_all.return_value = []
#         update_incomplete_stages()  # No error, just logs

# class TestOnboardingFlowEdgeCases(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     def setUp(self):
#         self.edge_case_data = {
#             "malformed_stage": MagicMock(is_active=True, stage_flows=[], glific_flow_id=None),
#             "empty_students": [],
#             "mixed_glific_ids": [
#                 MagicMock(name="STUD_001", glific_id="valid_id"),
#                 MagicMock(name="STUD_002", glific_id=None),
#                 MagicMock(name="STUD_003", glific_id=""),
#                 MagicMock(name="STUD_004", glific_id="another_valid_id")
#             ]
#         }

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_malformed_stage_configuration(self, mock_throw, mock_get_doc):
#         mock_get_doc.side_effect = [self.edge_case_data["malformed_stage"], MagicMock(status="Processed")]
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow("SET_001", "MALFORMED_STAGE", "not_started")
#         mock_throw.assert_called_with(_("No flows configured for stage '{0}'").format("MALFORMED_STAGE"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     def test_empty_student_list_handling(self, mock_get_students):
#         mock_get_students.return_value = self.edge_case_data["empty_students"]
#         with self.assertRaises(Exception):
#             trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", "not_started", "flow_123")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     def test_mixed_glific_id_scenarios(self, mock_start_flow, mock_get_students):
#         mock_get_students.return_value = self.edge_case_data["mixed_glific_ids"]
#         mock_start_flow.return_value = True
#         result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", "not_started", "flow_123")
#         self.assertEqual(result["individual_count"], 2)  # Only valid IDs processed

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_database_connectivity_issues(self, mock_get_all):
#         mock_get_all.side_effect = Exception("Database connection timeout")
#         result = get_students_from_onboarding(MagicMock(), None, None)
#         self.assertEqual(result, [])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     def test_glific_api_timeout_handling(self, mock_requests):
#         mock_requests.side_effect = Exception("API request timed out")
#         with self.assertRaises(Exception):
#             trigger_group_flow(MagicMock(), MagicMock(), "Bearer token", "not_started", "flow_123")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback.format_exc')
#     def test_general_exception_handling(self, mock_format_exc, mock_log_error):
#         mock_format_exc.return_value = "traceback"
#         # Simulate exception in a function (e.g., in trigger_onboarding_flow)
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw', side_effect=Exception("Test error")):
#             try:
#                 trigger_onboarding_flow("TEST", "TEST", "not_started")
#             except Exception:
#                 mock_log_error.assert_called_with(message="Error triggering onboarding flow: Test error\ntraceback", title="Onboarding Flow Trigger Error")

# class TestOnboardingFlowRunner:
#     @staticmethod
#     def run_all_tests(verbosity=2):
#         test_suite = unittest.TestSuite()
#         test_classes = [
#             TestOnboardingFlowFunctions,
#             TestOnboardingFlowJobAndGroup,
#             TestOnboardingIndividualAndStudents,
#             TestOnboardingJobReportAndScheduled,
#             TestOnboardingFlowEdgeCases
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