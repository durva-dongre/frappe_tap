

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
#         self.current_time = datetime(2025, 9, 11, 15, 5)  # 03:05 PM IST

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
#     def test_trigger_onboarding_flow_missing_params(self, mock_throw, mock_get_doc):
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("Both Backend Student Onboarding Set and Onboarding Stage are required"))

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
#     def test_trigger_onboarding_flow_unprocessed(self, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=True)
#         mock_onboarding = MagicMock(status="Pending")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("Selected Backend Student Onboarding Set is not in Processed status"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_success(self, mock_get_doc):
#         mock_stage = MagicMock(stage_flows=[MagicMock(student_status="not_started"), MagicMock(student_status="in_progress")])
#         mock_get_doc.return_value = mock_stage
#         result = get_stage_flow_statuses(self.mock_onboarding_stage)
#         self.assertIn("statuses", result)
#         self.assertEqual(len(result["statuses"]), 2)

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

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     def test_trigger_group_flow_api_error(self, mock_requests, mock_auth_headers, mock_get_doc):
#         mock_auth_headers.return_value = {"Authorization": "Bearer token"}
#         mock_onboarding = MagicMock(name=self.mock_onboarding_set)
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_response = MagicMock(status_code=500, text="Server Error")
#         mock_requests.return_value = mock_response
#         with self.assertRaises(Exception):
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     def test_trigger_onboarding_flow_job_group_success(self, mock_auth_headers, mock_get_doc):
#         mock_auth_headers.return_value = {"Authorization": "Bearer token"}
#         mock_stage = MagicMock()
#         mock_onboarding = MagicMock()
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow') as mock_group_flow:
#             mock_group_flow.return_value = {"success": True}
#             result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
#             self.assertTrue(result["success"])

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
#         mock_get_all.return_value = [{"student_id": "STUD_001", "glific_id": "glific_1"}]
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, self.mock_student_status)
#         self.assertEqual(len(result), 1)
#         self.assertEqual(result[0].name, "STUD_001")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     def test_trigger_individual_flows_success(self, mock_update_progress, mock_start_flow, mock_get_all):
#         mock_students = [MagicMock(name="STUD_001", glific_id="glific_1"), MagicMock(name="STUD_002", glific_id="glific_2")]
#         mock_get_all.return_value = [{"student_id": s.name, "glific_id": s.glific_id} for s in mock_students]
#         mock_start_flow.return_value = True
#         result = trigger_individual_flows(MagicMock(name=self.mock_onboarding_set), MagicMock(name=self.mock_onboarding_stage), "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertEqual(result["individual_count"], 2)
#         self.assertEqual(mock_start_flow.call_count, 2)
#         mock_update_progress.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
#     def test_update_student_stage_progress_new(self, mock_new_doc, mock_get_all):
#         mock_get_all.return_value = []
#         mock_progress = MagicMock()
#         mock_new_doc.return_value = mock_progress
#         update_student_stage_progress(MagicMock(name="STUD_001"), MagicMock(name=self.mock_onboarding_stage))
#         mock_new_doc.assert_called_once_with("StudentStageProgress")
#         mock_progress.insert.assert_called_once()

# class TestOnboardingJobReportAndScheduled(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
#     def test_get_job_status_success(self, mock_get_job_status):
#         mock_get_job_status.return_value = "finished"
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.Job.fetch') as mock_fetch:
#             mock_job = MagicMock(result={"success": True})
#             mock_fetch.return_value = mock_job
#             result = get_job_status(self.mock_job_id)
#             self.assertEqual(result["status"], "complete")
#             self.assertEqual(result["results"], {"success": True})

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_onboarding_progress_report_success(self, mock_get_doc, mock_get_all):
#         mock_get_all.return_value = [{"name": "PROG_001", "student": "STUD_001", "stage": self.mock_onboarding_stage, "status": "assigned",
#                                     "start_timestamp": self.current_time, "last_activity_timestamp": self.current_time}]
#         mock_student = MagicMock(name="STUD_001", name1="Student One", phone="1234567890")
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         mock_get_doc.side_effect = [mock_student, mock_stage]
#         result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage)
#         self.assertIn("summary", result)
#         self.assertGreater(len(result["details"]), 0)
#         self.assertEqual(result["details"][0]["status"], "assigned")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_update_incomplete_stages_success(self, mock_get_doc, mock_get_all, mock_now_datetime):
#         mock_now_datetime.return_value = self.current_time
#         mock_get_all.return_value = [{"name": "progress_1", "status": "assigned", "start_timestamp": self.current_time - timedelta(days=5)}]
#         mock_progress = MagicMock()
#         mock_get_doc.return_value = mock_progress
#         update_incomplete_stages()
#         self.assertEqual(mock_progress.status, "incomplete")
#         mock_progress.save.assert_called_once()
#         self.assertEqual(frappe.db.commit.call_count, 1)

# if __name__ == '__main__':
#     unittest.main()



import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

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
    from tap_lms.glific_integration import (
        get_glific_auth_headers,
        create_or_get_glific_group_for_batch,
        start_contact_flow
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
    def get_glific_auth_headers(*args, **kwargs): pass
    def create_or_get_glific_group_for_batch(*args, **kwargs): pass
    def start_contact_flow(*args, **kwargs): pass

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
        self.mock_job_id = "job_123"
        self.current_time = datetime(2025, 9, 11, 16, 3)  # 04:03 PM IST

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_onboarding_flow_success(self, mock_logger, mock_enqueue, mock_throw, mock_get_doc):
        """Test successful triggering of onboarding flow"""
        mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status=self.mock_student_status, glific_flow_id=self.mock_flow_id, flow_type="Group")])
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = self.mock_job_id
        result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        self.assertEqual(result, {"success": True, "job_id": self.mock_job_id})
        mock_enqueue.assert_called_once()
        mock_logger.info.assert_called()
        mock_throw.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_missing_inputs(self, mock_throw, mock_get_doc):
        """Test trigger_onboarding_flow with missing inputs"""
        with self.assertRaises(Exception):
            trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with("Both Backend Student Onboarding Set and Onboarding Stage are required")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_inactive_stage(self, mock_throw, mock_get_doc):
        """Test trigger_onboarding_flow with inactive stage"""
        mock_stage = MagicMock(is_active=False)
        mock_get_doc.return_value = mock_stage
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with("Selected Onboarding Stage is not active")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_no_flow_id(self, mock_throw, mock_get_doc):
        """Test trigger_onboarding_flow with no flow ID"""
        mock_stage = MagicMock(is_active=True, stage_flows=[])
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with("No flows configured for stage 'TEST_STAGE_001'")

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
        self.current_time = datetime(2025, 9, 11, 16, 3)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.glific_integration.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.glific_integration.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
    def test_trigger_group_flow_success(self, mock_update_batch, mock_get_students, mock_create_group, mock_requests, mock_auth_headers, mock_get_doc):
        """Test successful group flow trigger"""
        mock_auth_headers.return_value = {"authorization": "Bearer token"}
        mock_onboarding = MagicMock(name=self.mock_onboarding_set)
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings, mock_contact_group]
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_requests.return_value = MagicMock(status_code=200, json=lambda: {"data": {"startGroupFlow": {"success": True, "errors": []}}})
        mock_get_students.return_value = [MagicMock(name="STUD_001")]
        result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertIn("group_flow_result", result)
        self.assertEqual(result["group_count"], 1)
        mock_requests.assert_called_once()
        mock_update_batch.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.glific_integration.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_job_auth_failure(self, mock_throw, mock_auth_headers, mock_get_doc):
        """Test _trigger_onboarding_flow_job with authentication failure"""
        mock_auth_headers.return_value = {}
        mock_get_doc.side_effect = [MagicMock(), MagicMock(), MagicMock(api_url="https://api.glific.org")]
        result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
        self.assertEqual(result, {"error": "Failed to authenticate with Glific API"})
        mock_throw.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.glific_integration.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.glific_integration.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_group_flow_api_failure(self, mock_throw, mock_create_group, mock_requests, mock_auth_headers, mock_get_doc):
        """Test trigger_group_flow with Glific API failure"""
        mock_auth_headers.return_value = {"authorization": "Bearer token"}
        mock_onboarding = MagicMock(name=self.mock_onboarding_set)
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings, mock_contact_group]
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_requests.return_value = MagicMock(status_code=500, text="Server error")
        with self.assertRaises(Exception):
            trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        mock_throw.assert_called_with("Failed to communicate with Glific API: 500 - Server error")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.glific_integration.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_onboarding_flow_job_success(self, mock_logger, mock_group_flow, mock_auth_headers, mock_get_doc):
        """Test _trigger_onboarding_flow_job with successful group flow"""
        mock_auth_headers.return_value = {"authorization": "Bearer token"}
        mock_onboarding = MagicMock(name=self.mock_onboarding_set)
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]
        mock_group_flow.return_value = {"group_flow_result": {"success": True}, "group_count": 1}
        result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
        self.assertIn("group_flow_result", result)
        self.assertEqual(result["group_count"], 1)
        mock_logger.info.assert_called()

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
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding_with_status(self, mock_get_doc, mock_get_all):
        """Test get_students_from_onboarding with status filter"""
        mock_student = MagicMock(name="STUD_001", name1="Test Student", glific_id="glific_123")
        mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), mock_student]
        mock_get_all.side_effect = [
            [{"student_id": "STUD_001", "processing_status": "Success"}],  # Backend Students
            [{"name": "progress_1"}]  # StudentStageProgress
        ]
        result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, self.mock_student_status)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "STUD_001")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding_not_started(self, mock_get_doc, mock_get_all):
        """Test get_students_from_onboarding for not_started status"""
        mock_student = MagicMock(name="STUD_001", name1="Test Student", glific_id="glific_123")
        mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), mock_student]
        mock_get_all.side_effect = [
            [{"student_id": "STUD_001", "processing_status": "Success"}],  # Backend Students
            []  # No StudentStageProgress
        ]
        result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, "not_started")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "STUD_001")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.glific_integration.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    def test_trigger_individual_flows_success(self, mock_update_progress, mock_start_flow, mock_get_doc, mock_get_all):
        """Test successful individual flows trigger"""
        mock_student = MagicMock(name="STUD_001", glific_id="glific_123", name1="Test Student")
        mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), MagicMock(name=self.mock_onboarding_stage), MagicMock(api_url="https://api.glific.org"), mock_student]
        mock_get_all.return_value = [{"student_id": "STUD_001", "glific_id": "glific_123"}]
        mock_start_flow.return_value = True
        result = trigger_individual_flows(
            MagicMock(name=self.mock_onboarding_set),
            MagicMock(name=self.mock_onboarding_stage),
            "Bearer token",
            self.mock_student_status,
            self.mock_flow_id
        )
        self.assertEqual(result["individual_count"], 1)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["individual_flow_results"]), 1)
        self.assertTrue(result["individual_flow_results"][0]["success"])
        mock_update_progress.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.glific_integration.start_contact_flow')
    def test_trigger_individual_flows_no_glific_id(self, mock_start_flow, mock_get_doc, mock_get_all):
        """Test trigger_individual_flows with student missing Glific ID"""
        mock_student = MagicMock(name="STUD_001", glific_id=None, name1="Test Student")
        mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), MagicMock(name=self.mock_onboarding_stage), MagicMock(api_url="https://api.glific.org"), mock_student]
        mock_get_all.return_value = [{"student_id": "STUD_001", "glific_id": None}]
        result = trigger_individual_flows(
            MagicMock(name=self.mock_onboarding_set),
            MagicMock(name=self.mock_onboarding_stage),
            "Bearer token",
            self.mock_student_status,
            self.mock_flow_id
        )
        self.assertEqual(result["individual_count"], 0)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["individual_flow_results"]), 1)
        self.assertFalse(result["individual_flow_results"][0]["success"])
        mock_start_flow.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.glific_integration.start_contact_flow')
    def test_trigger_individual_flows_failure(self, mock_start_flow, mock_get_doc, mock_get_all):
        """Test trigger_individual_flows with start_contact_flow failure"""
        mock_student = MagicMock(name="STUD_001", glific_id="glific_123", name1="Test Student")
        mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), MagicMock(name=self.mock_onboarding_stage), MagicMock(api_url="https://api.glific.org"), mock_student]
        mock_get_all.return_value = [{"student_id": "STUD_001", "glific_id": "glific_123"}]
        mock_start_flow.return_value = False
        result = trigger_individual_flows(
            MagicMock(name=self.mock_onboarding_set),
            MagicMock(name=self.mock_onboarding_stage),
            "Bearer token",
            self.mock_student_status,
            self.mock_flow_id
        )
        self.assertEqual(result["individual_count"], 0)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(len(result["individual_flow_results"]), 1)
        self.assertFalse(result["individual_flow_results"][0]["success"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_student_stage_progress_new(self, mock_get_doc):
        """Test creating new StudentStageProgress"""
        mock_progress = MagicMock()
        mock_get_doc.side_effect = [MagicMock(), mock_progress]
        mock_get_doc.return_value = None  # No existing record
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc') as mock_new_doc:
            mock_new_doc.return_value = MagicMock()
            update_student_stage_progress(MagicMock(name="STUD_001"), MagicMock(name=self.mock_onboarding_stage))
            mock_new_doc.assert_called_with("StudentStageProgress")
            mock_new_doc.return_value.insert.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_student_stage_progress_existing(self, mock_get_doc):
        """Test updating existing StudentStageProgress"""
        mock_progress = MagicMock(status="not_started")
        mock_get_doc.return_value = mock_progress
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all') as mock_get_all:
            mock_get_all.return_value = [{"name": "progress_1"}]
            update_student_stage_progress(MagicMock(name="STUD_001"), MagicMock(name=self.mock_onboarding_stage))
            self.assertEqual(mock_progress.status, "assigned")
            mock_progress.save.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_student_stage_progress_error(self, mock_get_doc):
        """Test update_student_stage_progress with error"""
        mock_get_doc.side_effect = Exception("DB Error")
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error') as mock_log_error:
            update_student_stage_progress(MagicMock(name="STUD_001"), MagicMock(name=self.mock_onboarding_stage))
            mock_log_error.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_student_stage_progress_batch_success(self, mock_get_doc):
        """Test batch update of StudentStageProgress"""
        mock_students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        mock_progress1 = MagicMock(status="not_started")
        mock_progress2 = MagicMock(status="not_started")
        mock_get_doc.side_effect = [mock_progress1, mock_progress2]
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all') as mock_get_all:
            mock_get_all.return_value = [{"name": "progress_1"}, {"name": "progress_2"}]
            update_student_stage_progress_batch(mock_students, MagicMock(name=self.mock_onboarding_stage))
            self.assertEqual(mock_progress1.status, "assigned")
            self.assertEqual(mock_progress2.status, "assigned")
            mock_progress1.save.assert_called()
            mock_progress2.save.assert_called()

class TestOnboardingProgressAndScheduled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_job_id = "job_123"
        self.current_time = datetime(2025, 9, 11, 16, 3)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_new_structure(self, mock_get_doc):
        """Test get_stage_flow_statuses with new stage_flows structure"""
        mock_stage = MagicMock(stage_flows=[MagicMock(student_status="not_started"), MagicMock(student_status="assigned")])
        mock_get_doc.return_value = mock_stage
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        self.assertEqual(result, {"statuses": ["not_started", "assigned"]})

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_legacy(self, mock_get_doc):
        """Test get_stage_flow_statuses with legacy structure"""
        mock_stage = MagicMock(stage_flows=[], glific_flow_id="123")
        mock_get_doc.return_value = mock_stage
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        self.assertEqual(result["statuses"], ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_redis_conn')
    def test_get_job_status_finished(self, mock_get_redis_conn, mock_get_job_status):
        """Test get_job_status with finished job"""
        mock_get_job_status.return_value = "finished"
        mock_redis_conn = MagicMock()
        mock_get_redis_conn.return_value = mock_redis_conn
        mock_job = MagicMock(result={"status": "complete", "results": {"data": "test"}})
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.Job.fetch') as mock_fetch:
            mock_fetch.return_value = mock_job
            result = get_job_status(self.mock_job_id)
            self.assertEqual(result, {"status": "complete", "results": {"data": "test"}})

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_onboarding_progress_report_with_data(self, mock_get_doc, mock_get_all):
        """Test generating onboarding progress report with data"""
        mock_student = MagicMock(name="STUD_001", name1="Test Student", phone="1234567890")
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        mock_get_doc.side_effect = [mock_student, mock_stage]
        mock_get_all.side_effect = [
            [{"name": "progress_1", "student": "STUD_001", "stage": self.mock_onboarding_stage, "status": "assigned"}],  # StudentStageProgress
            [{"student_id": "STUD_001"}]  # Backend Students
        ]
        result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage, status="assigned")
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["assigned"], 1)
        self.assertEqual(len(result["details"]), 1)
        self.assertEqual(result["details"][0]["student_name"], "Test Student")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_incomplete_stages_with_update(self, mock_get_doc, mock_get_all, mock_now_datetime):
        """Test updating incomplete stages for overdue assigned records"""
        three_days_ago = self.current_time - timedelta(days=3)
        mock_now_datetime.return_value = self.current_time
        mock_get_all.return_value = [
            {"name": "progress_1", "student": "STUD_001", "stage": self.mock_onboarding_stage, "start_timestamp": three_days_ago, "status": "assigned"}
        ]
        mock_progress = MagicMock(status="assigned")
        mock_get_doc.return_value = mock_progress
        update_incomplete_stages()
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_incomplete_stages_no_change(self, mock_get_doc, mock_get_all, mock_now_datetime):
        """Test update_incomplete_stages with no status change"""
        mock_now_datetime.return_value = self.current_time
        mock_get_all.return_value = [
            {"name": "progress_1", "student": "STUD_001", "stage": self.mock_onboarding_stage, "start_timestamp": self.current_time, "status": "completed"}
        ]
        mock_progress = MagicMock(status="completed")
        mock_get_doc.return_value = mock_progress
        update_incomplete_stages()
        self.assertEqual(mock_progress.status, "completed")
        mock_progress.save.assert_not_called()

if __name__ == '__main__':
    unittest.main()


    


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
#     from tap_lms.glific_integration import (
#         get_glific_auth_headers,
#         create_or_get_glific_group_for_batch,
#         start_contact_flow
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
#         self.mock_job_id = "job_123"
#         self.current_time = datetime(2025, 9, 11, 15, 54)  # 03:54 PM IST

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
#     def test_trigger_onboarding_flow_success(self, mock_logger, mock_enqueue, mock_throw, mock_get_doc):
#         """Test successful triggering of onboarding flow"""
#         mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status=self.mock_student_status, glific_flow_id=self.mock_flow_id, flow_type="Group")])
#         mock_onboarding = MagicMock(status="Processed")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         mock_enqueue.return_value = self.mock_job_id
#         result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         self.assertEqual(result, {"success": True, "job_id": self.mock_job_id})
#         mock_enqueue.assert_called_once()
#         mock_logger.info.assert_called()
#         mock_throw.assert_not_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_missing_inputs(self, mock_throw, mock_get_doc):
#         """Test trigger_onboarding_flow with missing inputs"""
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with("Both Backend Student Onboarding Set and Onboarding Stage are required")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_inactive_stage(self, mock_throw, mock_get_doc):
#         """Test trigger_onboarding_flow with inactive stage"""
#         mock_stage = MagicMock(is_active=False)
#         mock_get_doc.return_value = mock_stage
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with("Selected Onboarding Stage is not active")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_no_flow_id(self, mock_throw, mock_get_doc):
#         """Test trigger_onboarding_flow with no flow ID"""
#         mock_stage = MagicMock(is_active=True, stage_flows=[])
#         mock_onboarding = MagicMock(status="Processed")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with("No flows configured for stage 'TEST_STAGE_001'")

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
#         self.current_time = datetime(2025, 9, 11, 15, 54)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.glific_integration.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.glific_integration.create_or_get_glific_group_for_batch')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
#     def test_trigger_group_flow_success(self, mock_update_batch, mock_get_students, mock_create_group, mock_requests, mock_auth_headers, mock_get_doc):
#         """Test successful group flow trigger"""
#         mock_auth_headers.return_value = {"authorization": "Bearer token"}
#         mock_onboarding = MagicMock(name=self.mock_onboarding_set)
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings, mock_contact_group]
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_requests.return_value = MagicMock(status_code=200, json=lambda: {"data": {"startGroupFlow": {"success": True, "errors": []}}})
#         mock_get_students.return_value = [MagicMock(name="STUD_001")]
#         result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertIn("group_flow_result", result)
#         self.assertEqual(result["group_count"], 1)
#         mock_requests.assert_called_once()
#         mock_update_batch.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.glific_integration.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_job_auth_failure(self, mock_throw, mock_auth_headers, mock_get_doc):
#         """Test _trigger_onboarding_flow_job with authentication failure"""
#         mock_auth_headers.return_value = {}
#         mock_get_doc.side_effect = [MagicMock(), MagicMock(), MagicMock(api_url="https://api.glific.org")]
#         result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
#         self.assertEqual(result, {"error": "Failed to authenticate with Glific API"})
#         mock_throw.assert_not_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.glific_integration.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.glific_integration.create_or_get_glific_group_for_batch')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_group_flow_api_failure(self, mock_throw, mock_create_group, mock_requests, mock_auth_headers, mock_get_doc):
#         """Test trigger_group_flow with Glific API failure"""
#         mock_auth_headers.return_value = {"authorization": "Bearer token"}
#         mock_onboarding = MagicMock(name=self.mock_onboarding_set)
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings, mock_contact_group]
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_requests.return_value = MagicMock(status_code=500, text="Server error")
#         with self.assertRaises(Exception):
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         mock_throw.assert_called_with("Failed to communicate with Glific API: 500 - Server error")

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
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_students_from_onboarding_with_status(self, mock_get_doc, mock_get_all):
#         """Test get_students_from_onboarding with status filter"""
#         mock_student = MagicMock(name="STUD_001", name1="Test Student", glific_id="glific_123")
#         mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), mock_student]
#         mock_get_all.side_effect = [
#             [{"student_id": "STUD_001"}],  # Backend Students
#             [{"name": "progress_1"}]  # StudentStageProgress
#         ]
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, self.mock_student_status)
#         self.assertEqual(len(result), 1)
#         self.assertEqual(result[0].name, "STUD_001")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_students_from_onboarding_not_started(self, mock_get_doc, mock_get_all):
#         """Test get_students_from_onboarding for not_started status"""
#         mock_student = MagicMock(name="STUD_001", name1="Test Student", glific_id="glific_123")
#         mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), mock_student]
#         mock_get_all.side_effect = [
#             [{"student_id": "STUD_001"}],  # Backend Students
#             []  # No StudentStageProgress
#         ]
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, "not_started")
#         self.assertEqual(len(result), 1)
#         self.assertEqual(result[0].name, "STUD_001")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.glific_integration.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     def test_trigger_individual_flows_success(self, mock_update_progress, mock_start_flow, mock_get_doc, mock_get_all):
#         """Test successful individual flows trigger"""
#         mock_student = MagicMock(name="STUD_001", glific_id="glific_123", name1="Test Student")
#         mock_get_doc.side_effect = [MagicMock(name=self.mock_onboarding_set), MagicMock(name=self.mock_onboarding_stage), MagicMock(api_url="https://api.glific.org"), mock_student]
#         mock_get_all.return_value = [{"student_id": "STUD_001"}]
#         mock_start_flow.return_value = True
#         result = trigger_individual_flows(
#             MagicMock(name=self.mock_onboarding_set),
#             MagicMock(name=self.mock_onboarding_stage),
#             "Bearer token",
#             self.mock_student_status,
#             self.mock_flow_id
#         )
#         self.assertEqual(result["individual_count"], 1)
#         self.assertEqual(result["error_count"], 0)
#         self.assertEqual(len(result["individual_flow_results"]), 1)
#         self.assertTrue(result["individual_flow_results"][0]["success"])
#         mock_update_progress.assert_called_once()

# class TestOnboardingProgressAndScheduled(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     def setUp(self):
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_job_id = "job_123"
#         self.current_time = datetime(2025, 9, 11, 15, 54)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_new_structure(self, mock_get_doc):
#         """Test get_stage_flow_statuses with new stage_flows structure"""
#         mock_stage = MagicMock(stage_flows=[MagicMock(student_status="not_started"), MagicMock(student_status="assigned")])
#         mock_get_doc.return_value = mock_stage
#         result = get_stage_flow_statuses(self.mock_onboarding_stage)
#         self.assertEqual(result, {"statuses": ["not_started", "assigned"]})

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_legacy(self, mock_get_doc):
#         """Test get_stage_flow_statuses with legacy structure"""
#         mock_stage = MagicMock(stage_flows=[], glific_flow_id="123")
#         mock_get_doc.return_value = mock_stage
#         result = get_stage_flow_statuses(self.mock_onboarding_stage)
#         self.assertEqual(result["statuses"], ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_onboarding_progress_report_with_data(self, mock_get_doc, mock_get_all):
#         """Test generating onboarding progress report with data"""
#         mock_student = MagicMock(name="STUD_001", name1="Test Student", phone="1234567890")
#         mock_stage = MagicMock(name=self.mock_onboarding_stage)
#         mock_get_doc.side_effect = [mock_student, mock_stage]
#         mock_get_all.side_effect = [
#             [{"name": "progress_1", "student": "STUD_001", "stage": self.mock_onboarding_stage, "status": "assigned"}],  # StudentStageProgress
#             [{"student_id": "STUD_001"}]  # Backend Students
#         ]
#         result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage, status="assigned")
#         self.assertEqual(result["summary"]["total"], 1)
#         self.assertEqual(result["summary"]["assigned"], 1)
#         self.assertEqual(len(result["details"]), 1)
#         self.assertEqual(result["details"][0]["student_name"], "Test Student")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_update_incomplete_stages_with_update(self, mock_get_doc, mock_get_all, mock_now_datetime):
#         """Test updating incomplete stages for overdue assigned records"""
#         three_days_ago = self.current_time - timedelta(days=3)
#         mock_now_datetime.return_value = self.current_time
#         mock_get_all.return_value = [
#             {"name": "progress_1", "student": "STUD_001", "stage": self.mock_onboarding_stage, "start_timestamp": three_days_ago}
#         ]
#         mock_progress = MagicMock(status="assigned")
#         mock_get_doc.return_value = mock_progress
#         update_incomplete_stages()
#         self.assertEqual(mock_progress.status, "incomplete")
#         mock_progress.save.assert_called_once()

# if __name__ == '__main__':
#     unittest.main()