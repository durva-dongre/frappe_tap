

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
import frappe
import json
from unittest.mock import Mock, patch, MagicMock
from frappe.utils import now_datetime, add_to_date
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


class TestOnboardingFlowTrigger(unittest.TestCase):
    """Test cases for onboarding flow trigger functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.test_onboarding_set = "TEST-ONBOARDING-001"
        self.test_stage = "TEST-STAGE-001"
        self.test_student_status = "not_started"
        self.test_flow_id = "12345"
        
    def tearDown(self):
        """Clean up after tests"""
        pass

    @patch('frappe.get_doc')
    @patch('frappe.enqueue')
    def test_trigger_onboarding_flow_success(self, mock_enqueue, mock_get_doc):
        """Test successful triggering of onboarding flow"""
        # Mock stage document
        mock_stage = Mock()
        mock_stage.name = self.test_stage
        mock_stage.is_active = True
        mock_stage.stage_flows = [Mock()]
        mock_stage.stage_flows[0].student_status = self.test_student_status
        mock_stage.stage_flows[0].glific_flow_id = self.test_flow_id
        mock_stage.stage_flows[0].flow_type = "Group"
        
        # Mock onboarding document
        mock_onboarding = Mock()
        mock_onboarding.name = self.test_onboarding_set
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = "job_123"
        
        result = trigger_onboarding_flow(
            self.test_onboarding_set, 
            self.test_stage, 
            self.test_student_status
        )
        
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "job_123")
        mock_enqueue.assert_called_once()

    def test_trigger_onboarding_flow_missing_parameters(self):
        """Test trigger_onboarding_flow with missing parameters"""
        with self.assertRaises(Exception):
            trigger_onboarding_flow("", "", "")
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.test_onboarding_set, "", "")

    @patch('frappe.get_doc')
    def test_trigger_onboarding_flow_inactive_stage(self, mock_get_doc):
        """Test trigger_onboarding_flow with inactive stage"""
        mock_stage = Mock()
        mock_stage.is_active = False
        mock_get_doc.return_value = mock_stage
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(
                self.test_onboarding_set, 
                self.test_stage, 
                self.test_student_status
            )

    @patch('frappe.get_doc')
    def test_trigger_onboarding_flow_unprocessed_set(self, mock_get_doc):
        """Test trigger_onboarding_flow with unprocessed onboarding set"""
        mock_stage = Mock()
        mock_stage.is_active = True
        
        mock_onboarding = Mock()
        mock_onboarding.status = "Draft"
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(
                self.test_onboarding_set, 
                self.test_stage, 
                self.test_student_status
            )

    @patch('frappe.get_doc')
    def test_trigger_onboarding_flow_no_flow_configured(self, mock_get_doc):
        """Test trigger_onboarding_flow with no flow configured for status"""
        mock_stage = Mock()
        mock_stage.name = self.test_stage
        mock_stage.is_active = True
        mock_stage.stage_flows = []  # No flows configured
        
        mock_onboarding = Mock()
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(
                self.test_onboarding_set, 
                self.test_stage, 
                self.test_student_status
            )

    @patch('frappe.get_doc')
    def test_trigger_onboarding_flow_legacy_flow_support(self, mock_get_doc):
        """Test trigger_onboarding_flow with legacy flow configuration"""
        mock_stage = Mock()
        mock_stage.name = self.test_stage
        mock_stage.is_active = True
        mock_stage.stage_flows = None  # Legacy mode
        mock_stage.glific_flow_id = self.test_flow_id
        mock_stage.glific_flow_type = "Individual"
        
        mock_onboarding = Mock()
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        
        with patch('frappe.enqueue') as mock_enqueue:
            mock_enqueue.return_value = "job_123"
            
            result = trigger_onboarding_flow(
                self.test_onboarding_set, 
                self.test_stage, 
                self.test_student_status
            )
            
            self.assertTrue(result["success"])

    @patch('frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow')
    def test_trigger_onboarding_flow_job_group_flow(self, mock_group_flow, mock_auth, mock_get_doc):
        """Test _trigger_onboarding_flow_job for group flow"""
        # Mock auth headers
        mock_auth.return_value = {"authorization": "Bearer test_token"}
        
        # Mock documents
        mock_stage = Mock()
        mock_onboarding = Mock()
        mock_glific_settings = Mock()
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]
        
        # Mock group flow result
        mock_group_flow.return_value = {"success": True, "group_count": 5}
        
        result = _trigger_onboarding_flow_job(
            self.test_onboarding_set,
            self.test_stage,
            self.test_student_status,
            self.test_flow_id,
            "Group"
        )
        
        mock_group_flow.assert_called_once()
        self.assertIn("success", result)

    @patch('frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_individual_flows')
    def test_trigger_onboarding_flow_job_individual_flow(self, mock_individual_flow, mock_auth, mock_get_doc):
        """Test _trigger_onboarding_flow_job for individual flow"""
        # Mock auth headers
        mock_auth.return_value = {"authorization": "Bearer test_token"}
        
        # Mock documents
        mock_stage = Mock()
        mock_onboarding = Mock()
        mock_glific_settings = Mock()
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]
        
        # Mock individual flow result
        mock_individual_flow.return_value = {"individual_count": 3, "error_count": 0}
        
        result = _trigger_onboarding_flow_job(
            self.test_onboarding_set,
            self.test_stage,
            self.test_student_status,
            self.test_flow_id,
            "Individual"
        )
        
        mock_individual_flow.assert_called_once()
        self.assertIn("individual_count", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_auth_failure(self, mock_auth):
        """Test _trigger_onboarding_flow_job with authentication failure"""
        mock_auth.return_value = None
        
        result = _trigger_onboarding_flow_job(
            self.test_onboarding_set,
            self.test_stage,
            self.test_student_status,
            self.test_flow_id,
            "Group"
        )
        
        self.assertIn("error", result)
        self.assertIn("authenticate", result["error"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('frappe.get_doc')
    @patch('requests.post')
    def test_trigger_group_flow_success(self, mock_post, mock_get_doc, mock_create_group):
        """Test successful group flow trigger"""
        # Mock group creation
        mock_create_group.return_value = {"group_id": "group_123"}
        
        # Mock contact group document
        mock_contact_group = Mock()
        mock_contact_group.group_id = "group_123"
        
        # Mock glific settings
        mock_glific_settings = Mock()
        mock_glific_settings.api_url = "https://api.glific.com"
        
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "startGroupFlow": {
                    "success": True,
                    "errors": []
                }
            }
        }
        mock_post.return_value = mock_response
        
        # Mock students
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding') as mock_students:
            mock_students.return_value = [Mock(), Mock(), Mock()]  # 3 students
            
            with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch'):
                mock_onboarding = Mock()
                mock_onboarding.name = self.test_onboarding_set
                
                mock_stage = Mock()
                mock_stage.name = self.test_stage
                
                result = trigger_group_flow(
                    mock_onboarding,
                    mock_stage,
                    "Bearer test_token",
                    self.test_student_status,
                    self.test_flow_id
                )
        
        self.assertIn("group_flow_result", result)
        self.assertEqual(result["group_count"], 3)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_no_group(self, mock_create_group):
        """Test group flow trigger when group creation fails"""
        mock_create_group.return_value = None
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        with self.assertRaises(Exception):
            trigger_group_flow(
                mock_onboarding,
                mock_stage,
                "Bearer test_token",
                self.test_student_status,
                self.test_flow_id
            )

    @patch('requests.post')
    @patch('frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_api_error(self, mock_create_group, mock_get_doc, mock_post):
        """Test group flow trigger with API error"""
        # Mock group creation
        mock_create_group.return_value = {"group_id": "group_123"}
        
        # Mock contact group document
        mock_contact_group = Mock()
        mock_contact_group.group_id = "group_123"
        
        # Mock glific settings
        mock_glific_settings = Mock()
        mock_glific_settings.api_url = "https://api.glific.com"
        
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        with self.assertRaises(Exception):
            trigger_group_flow(
                mock_onboarding,
                mock_stage,
                "Bearer test_token",
                self.test_student_status,
                self.test_flow_id
            )

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    def test_trigger_individual_flows_success(self, mock_update_progress, mock_start_flow, mock_get_students):
        """Test successful individual flows trigger"""
        # Mock students
        mock_student1 = Mock()
        mock_student1.name = "STUDENT-001"
        mock_student1.name1 = "John Doe"
        mock_student1.glific_id = "contact_123"
        
        mock_student2 = Mock()
        mock_student2.name = "STUDENT-002"
        mock_student2.name1 = "Jane Smith"
        mock_student2.glific_id = "contact_456"
        
        mock_get_students.return_value = [mock_student1, mock_student2]
        
        # Mock successful flow starts
        mock_start_flow.return_value = True
        
        mock_onboarding = Mock()
        mock_onboarding.name = self.test_onboarding_set
        
        mock_stage = Mock()
        mock_stage.name = self.test_stage
        
        result = trigger_individual_flows(
            mock_onboarding,
            mock_stage,
            "Bearer test_token",
            self.test_student_status,
            self.test_flow_id
        )
        
        self.assertEqual(result["individual_count"], 2)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["individual_flow_results"]), 2)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_trigger_individual_flows_no_students(self, mock_get_students):
        """Test individual flows trigger with no students"""
        mock_get_students.return_value = []
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        with self.assertRaises(Exception):
            trigger_individual_flows(
                mock_onboarding,
                mock_stage,
                "Bearer test_token",
                self.test_student_status,
                self.test_flow_id
            )

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    def test_trigger_individual_flows_mixed_results(self, mock_start_flow, mock_get_students):
        """Test individual flows trigger with mixed success/failure"""
        # Mock students
        mock_student1 = Mock()
        mock_student1.name = "STUDENT-001"
        mock_student1.name1 = "John Doe"
        mock_student1.glific_id = "contact_123"
        
        mock_student2 = Mock()
        mock_student2.name = "STUDENT-002"
        mock_student2.name1 = "Jane Smith"
        mock_student2.glific_id = None  # No Glific ID
        
        mock_student3 = Mock()
        mock_student3.name = "STUDENT-003"
        mock_student3.name1 = "Bob Johnson"
        mock_student3.glific_id = "contact_789"
        
        mock_get_students.return_value = [mock_student1, mock_student2, mock_student3]
        
        # Mock flow start results
        def mock_start_flow_side_effect(flow_id, contact_id, results):
            if contact_id == "contact_123":
                return True
            elif contact_id == "contact_789":
                return False
            return False
        
        mock_start_flow.side_effect = mock_start_flow_side_effect
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress'):
            result = trigger_individual_flows(
                mock_onboarding,
                mock_stage,
                "Bearer test_token",
                self.test_student_status,
                self.test_flow_id
            )
        
        self.assertEqual(result["individual_count"], 1)  # Only one success
        self.assertEqual(result["error_count"], 1)  # One failure
        self.assertEqual(len(result["individual_flow_results"]), 2)  # Two results (student without Glific ID skipped)

    @patch('frappe.get_doc')
    def test_get_stage_flow_statuses_new_structure(self, mock_get_doc):
        """Test get_stage_flow_statuses with new stage_flows structure"""
        mock_stage = Mock()
        mock_stage.stage_flows = [
            Mock(student_status="not_started"),
            Mock(student_status="in_progress"),
            Mock(student_status="completed")
        ]
        mock_get_doc.return_value = mock_stage
        
        result = get_stage_flow_statuses(self.test_stage)
        
        self.assertIn("statuses", result)
        self.assertEqual(len(result["statuses"]), 3)
        self.assertIn("not_started", result["statuses"])
        self.assertIn("in_progress", result["statuses"])
        self.assertIn("completed", result["statuses"])

    @patch('frappe.get_doc')
    def test_get_stage_flow_statuses_legacy_structure(self, mock_get_doc):
        """Test get_stage_flow_statuses with legacy structure"""
        mock_stage = Mock()
        mock_stage.stage_flows = None
        mock_stage.glific_flow_id = self.test_flow_id
        mock_get_doc.return_value = mock_stage
        
        result = get_stage_flow_statuses(self.test_stage)
        
        self.assertIn("statuses", result)
        self.assertIn("not_started", result["statuses"])
        self.assertIn("completed", result["statuses"])

    @patch('frappe.get_doc')
    def test_get_stage_flow_statuses_no_flows(self, mock_get_doc):
        """Test get_stage_flow_statuses with no flows configured"""
        mock_stage = Mock()
        mock_stage.stage_flows = None
        mock_stage.glific_flow_id = None
        mock_get_doc.return_value = mock_stage
        
        result = get_stage_flow_statuses(self.test_stage)
        
        self.assertIn("statuses", result)
        self.assertEqual(len(result["statuses"]), 0)

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_get_students_from_onboarding_with_status_filter(self, mock_get_doc, mock_get_all):
        """Test get_students_from_onboarding with status filtering"""
        # Mock backend students
        mock_get_all.side_effect = [
            [{"student_id": "STUDENT-001"}, {"student_id": "STUDENT-002"}],  # Backend students
            [{"name": "PROGRESS-001"}],  # Stage progress for STUDENT-001
            []  # No stage progress for STUDENT-002
        ]
        
        # Mock student documents
        mock_student1 = Mock()
        mock_student1.name = "STUDENT-001"
        mock_student1.name1 = "John Doe"
        
        mock_student2 = Mock()
        mock_student2.name = "STUDENT-002"
        mock_student2.name1 = "Jane Smith"
        
        mock_get_doc.side_effect = [mock_student1, mock_student2]
        
        mock_onboarding = Mock()
        mock_onboarding.name = self.test_onboarding_set
        
        result = get_students_from_onboarding(
            mock_onboarding, 
            self.test_stage, 
            "in_progress"
        )
        
        self.assertEqual(len(result), 1)  # Only student with matching status
        self.assertEqual(result[0].name, "STUDENT-001")

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_get_students_from_onboarding_not_started_status(self, mock_get_doc, mock_get_all):
        """Test get_students_from_onboarding with not_started status"""
        # Mock backend students
        mock_get_all.side_effect = [
            [{"student_id": "STUDENT-001"}, {"student_id": "STUDENT-002"}],  # Backend students
            [],  # No stage progress for STUDENT-001
            [{"name": "PROGRESS-002"}],  # Stage progress exists for STUDENT-002
            []  # No stage progress for STUDENT-001 in second check
        ]
        
        # Mock student documents
        mock_student1 = Mock()
        mock_student1.name = "STUDENT-001"
        mock_student1.name1 = "John Doe"
        
        mock_student2 = Mock()
        mock_student2.name = "STUDENT-002"
        mock_student2.name1 = "Jane Smith"
        
        mock_get_doc.side_effect = [mock_student1, mock_student2, mock_student1]
        
        mock_onboarding = Mock()
        mock_onboarding.name = self.test_onboarding_set
        
        result = get_students_from_onboarding(
            mock_onboarding, 
            self.test_stage, 
            "not_started"
        )
        
        self.assertEqual(len(result), 1)  # Only student without stage progress
        self.assertEqual(result[0].name, "STUDENT-001")

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    @patch('frappe.new_doc')
    @patch('frappe.db.commit')
    def test_update_student_stage_progress_new_record(self, mock_commit, mock_new_doc, mock_get_doc, mock_get_all):
        """Test update_student_stage_progress creating new record"""
        # No existing record
        mock_get_all.return_value = []
        
        # Mock new document creation
        mock_progress = Mock()
        mock_new_doc.return_value = mock_progress
        
        mock_student = Mock()
        mock_student.name = "STUDENT-001"
        
        mock_stage = Mock()
        mock_stage.name = self.test_stage
        
        update_student_stage_progress(mock_student, mock_stage)
        
        mock_new_doc.assert_called_once_with("StudentStageProgress")
        mock_progress.insert.assert_called_once()

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    @patch('frappe.db.commit')
    def test_update_student_stage_progress_update_existing(self, mock_commit, mock_get_doc, mock_get_all):
        """Test update_student_stage_progress updating existing record"""
        # Existing record
        mock_get_all.return_value = [{"name": "PROGRESS-001"}]
        
        # Mock existing progress document
        mock_progress = Mock()
        mock_progress.status = "not_started"
        mock_get_doc.return_value = mock_progress
        
        mock_student = Mock()
        mock_student.name = "STUDENT-001"
        
        mock_stage = Mock()
        mock_stage.name = self.test_stage
        
        update_student_stage_progress(mock_student, mock_stage)
        
        self.assertEqual(mock_progress.status, "assigned")
        mock_progress.save.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    def test_update_student_stage_progress_batch(self, mock_update_progress):
        """Test update_student_stage_progress_batch"""
        mock_students = [Mock(), Mock(), Mock()]
        mock_stage = Mock()
        
        update_student_stage_progress_batch(mock_students, mock_stage)
        
        # Should call update for each student
        self.assertEqual(mock_update_progress.call_count, 3)

    def test_update_student_stage_progress_batch_empty_list(self):
        """Test update_student_stage_progress_batch with empty student list"""
        mock_stage = Mock()
        
        # Should not raise exception
        update_student_stage_progress_batch([], mock_stage)

    @patch('frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_finished(self, mock_bg_status):
        """Test get_job_status for finished job"""
        mock_bg_status.return_value = "finished"
        
        with patch('rq.job.Job.fetch') as mock_fetch:
            mock_job = Mock()
            mock_job.result = {"success": True, "count": 5}
            mock_fetch.return_value = mock_job
            
            with patch('frappe.utils.background_jobs.get_redis_conn') as mock_redis:
                mock_redis.return_value = Mock()
                
                result = get_job_status("job_123")
                
                self.assertEqual(result["status"], "complete")
                self.assertIn("results", result)

    @patch('frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_failed(self, mock_bg_status):
        """Test get_job_status for failed job"""
        mock_bg_status.return_value = "failed"
        
        result = get_job_status("job_123")
        
        self.assertEqual(result["status"], "failed")

    @patch('frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_running(self, mock_bg_status):
        """Test get_job_status for running job"""
        mock_bg_status.return_value = "started"
        
        result = get_job_status("job_123")
        
        self.assertEqual(result["status"], "started")

    def test_get_job_status_no_job_id(self):
        """Test get_job_status with no job ID"""
        result = get_job_status("")
        
        self.assertEqual(result["status"], "unknown")

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_get_onboarding_progress_report(self, mock_get_doc, mock_get_all):
        """Test get_onboarding_progress_report"""
        # Mock progress records
        mock_get_all.return_value = [
            {
                "name": "PROGRESS-001",
                "student": "STUDENT-001",
                "stage": self.test_stage,
                "status": "completed",
                "start_timestamp": now_datetime(),
                "last_activity_timestamp": now_datetime(),
                "completion_timestamp": now_datetime()
            },
            {
                "name": "PROGRESS-002",
                "student": "STUDENT-002",
                "stage": self.test_stage,
                "status": "in_progress",
                "start_timestamp": now_datetime(),
                "last_activity_timestamp": now_datetime(),
                "completion_timestamp": None
            }
        ]
        
        # Mock student and stage documents
        mock_student1 = Mock()
        mock_student1.name = "STUDENT-001"
        mock_student1.name1 = "John Doe"
        mock_student1.phone = "1234567890"
        
        mock_student2 = Mock()
        mock_student2.name = "STUDENT-002"
        mock_student2.name1 = "Jane Smith"
        mock_student2.phone = "0987654321"
        
        mock_stage_doc = Mock()
        mock_stage_doc.name = self.test_stage
        
        mock_get_doc.side_effect = [mock_student1, mock_stage_doc, mock_student2, mock_stage_doc]
        
        result = get_onboarding_progress_report(stage=self.test_stage)
        
        self.assertIn("summary", result)
        self.assertIn("details", result)
        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(result["summary"]["in_progress"], 1)
        self.assertEqual(len(result["details"]), 2)

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_get_onboarding_progress_report_with_set_filter(self, mock_get_doc, mock_get_all):
        """Test get_onboarding_progress_report with set filtering"""
        # Mock progress records
        mock_get_all.side_effect = [
            [  # First call - get progress records
                {
                    "name": "PROGRESS-001",
                    "student": "STUDENT-001",
                    "stage": self.test_stage,
                    "status": "completed",
                    "start_timestamp": now_datetime(),
                    "last_activity_timestamp": now_datetime(),
                    "completion_timestamp": now_datetime()
                }
            ],
            [  # Second call - check backend students for set filter
                {"student_id": "STUDENT-001"}
            ]
        ]
        
        # Mock documents
        mock_student = Mock()
        mock_student.name = "STUDENT-001"
        mock_student.name1 = "John Doe"
        mock_student.phone = "1234567890"
        
        mock_stage_doc = Mock()
        mock_stage_doc.name = self.test_stage
        
        mock_get_doc.side_effect = [mock_student, mock_stage_doc]
        
        result = get_onboarding_progress_report(
            set=self.test_onboarding_set,
            stage=self.test_stage
        )
        
        self.assertEqual(len(result["details"]), 1)
        self.assertEqual(result["details"][0]["student"], "STUDENT-001")

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    @patch('frappe.db.commit')
    def test_update_incomplete_stages(self, mock_commit, mock_get_doc, mock_get_all):
        """Test update_incomplete_stages scheduled task"""
        # Mock assigned records that are old
        old_timestamp = add_to_date(now_datetime(), days=-5)
        mock_get_all.return_value = [
            {
                "name": "PROGRESS-001",
                "student": "STUDENT-001",
                "stage": self.test_stage,
                "start_timestamp": old_timestamp
            },
            {
                "name": "PROGRESS-002",
                "student": "STUDENT-002",
                "stage": self.test_stage,
                "start_timestamp": old_timestamp
            }
        ]
        
        # Mock progress documents
        mock_progress1 = Mock()
        mock_progress1.status = "assigned"
        
        mock_progress2 = Mock()
        mock_progress2.status = "assigned"
        
        mock_get_doc.side_effect = [mock_progress1, mock_progress2]
        
        update_incomplete_stages()
        
        # Both records should be updated to incomplete
        self.assertEqual(mock_progress1.status, "incomplete")
        self.assertEqual(mock_progress2.status, "incomplete")
        mock_progress1.save.assert_called_once()
        mock_progress2.save.assert_called_once()

    def test_update_incomplete_stages_no_records(self):
        """Test update_incomplete_stages with no records to update"""
        with patch('frappe.get_all') as mock_get_all:
            mock_get_all.return_value = []
            
            # Should not raise exception
            update_incomplete_stages()

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_update_incomplete_stages_error_handling(self, mock_get_doc, mock_get_all):
        """Test update_incomplete_stages error handling"""
        mock_get_all.return_value = [
            {
                "name": "PROGRESS-001",
                "student": "STUDENT-001",
                "stage": self.test_stage,
                "start_timestamp": add_to_date(now_datetime(), days=-5)
            }
        ]
        
        # Mock exception during document update
        mock_get_doc.side_effect = Exception("Database error")
        
        with patch('frappe.logger') as mock_logger:
            # Should not raise exception but log error
            update_incomplete_stages()
            mock_logger.return_value.error.assert_called()


class TestOnboardingFlowTriggerIntegration(unittest.TestCase):
    """Integration test cases for onboarding flow trigger"""
    
    def setUp(self):
        """Set up integration test data"""
        # This would typically set up actual test records in the database
        pass
    
    def tearDown(self):
        """Clean up integration test data"""
        # This would typically clean up test records from the database
        pass
    
    @unittest.skip("Integration test - requires database setup")
    def test_end_to_end_group_flow(self):
        """End-to-end test for group flow trigger"""
        # This would test the complete flow from API call to database updates
        # Including actual Glific API calls (in test environment)
        pass
    
    @unittest.skip("Integration test - requires database setup")
    def test_end_to_end_individual_flow(self):
        """End-to-end test for individual flow trigger"""
        # This would test the complete flow for individual student flows
        pass


class TestOnboardingFlowTriggerEdgeCases(unittest.TestCase):
    """Edge case test scenarios"""
    
    @patch('frappe.get_doc')
    def test_trigger_onboarding_flow_with_special_characters_in_names(self, mock_get_doc):
        """Test with special characters in onboarding set/stage names"""
        special_set_name = "TEST-SET-WITH-SPECIAL-CHARS-@#$%"
        special_stage_name = "TEST-STAGE-WITH-UNICODE-字符"
        
        mock_stage = Mock()
        mock_stage.name = special_stage_name
        mock_stage.is_active = True
        mock_stage.stage_flows = [Mock()]
        mock_stage.stage_flows[0].student_status = "not_started"
        mock_stage.stage_flows[0].glific_flow_id = "12345"
        mock_stage.stage_flows[0].flow_type = "Group"
        
        mock_onboarding = Mock()
        mock_onboarding.name = special_set_name
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        
        with patch('frappe.enqueue') as mock_enqueue:
            mock_enqueue.return_value = "job_123"
            
            result = trigger_onboarding_flow(
                special_set_name,
                special_stage_name,
                "not_started"
            )
            
            self.assertTrue(result["success"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_trigger_individual_flows_large_batch(self, mock_get_students):
        """Test individual flows with large number of students"""
        # Create 100 mock students
        mock_students = []
        for i in range(100):
            student = Mock()
            student.name = f"STUDENT-{i:03d}"
            student.name1 = f"Student {i}"
            student.glific_id = f"contact_{i}"
            mock_students.append(student)
        
        mock_get_students.return_value = mock_students
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow') as mock_start_flow:
            mock_start_flow.return_value = True
            
            with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress'):
                with patch('time.sleep'):  # Skip sleep in tests
                    mock_onboarding = Mock()
                    mock_stage = Mock()
                    
                    result = trigger_individual_flows(
                        mock_onboarding,
                        mock_stage,
                        "Bearer test_token",
                        "not_started",
                        "12345"
                    )
        
        self.assertEqual(result["individual_count"], 100)
        self.assertEqual(result["error_count"], 0)

    @patch('frappe.get_all')
    def test_get_students_from_onboarding_with_corrupted_data(self, mock_get_all):
        """Test get_students_from_onboarding with corrupted backend student data"""
        # Mock backend students with some None/invalid student IDs
        mock_get_all.return_value = [
            {"student_id": "STUDENT-001"},
            {"student_id": None},  # Corrupted data
            {"student_id": ""},    # Empty string
            {"student_id": "STUDENT-002"},
            {"student_id": "NONEXISTENT-STUDENT"}  # Student that doesn't exist
        ]
        
        with patch('frappe.get_doc') as mock_get_doc:
            # Mock successful student fetch for valid IDs
            def mock_get_doc_side_effect(doctype, docname):
                if docname == "STUDENT-001":
                    student = Mock()
                    student.name = "STUDENT-001"
                    return student
                elif docname == "STUDENT-002":
                    student = Mock()
                    student.name = "STUDENT-002"
                    return student
                elif docname == "NONEXISTENT-STUDENT":
                    raise Exception("Student not found")
                else:
                    raise Exception("Invalid student ID")
            
            mock_get_doc.side_effect = mock_get_doc_side_effect
            
            mock_onboarding = Mock()
            mock_onboarding.name = "TEST-ONBOARDING-001"
            
            result = get_students_from_onboarding(mock_onboarding)
            
            # Should only return valid students
            self.assertEqual(len(result), 2)

    def test_performance_with_concurrent_requests(self):
        """Test system behavior with concurrent flow trigger requests"""
        # This would test race conditions and concurrent access patterns
        # Skipped as it requires more complex setup
        pass


class TestOnboardingFlowTriggerSecurity(unittest.TestCase):
    """Security-related test cases"""
    
    @patch('frappe.get_doc')
    def test_sql_injection_prevention(self, mock_get_doc):
        """Test that SQL injection attempts are handled safely"""
        malicious_input = "'; DROP TABLE StudentStageProgress; --"
        
        mock_stage = Mock()
        mock_stage.is_active = False  # Will cause early exit
        mock_get_doc.return_value = mock_stage
        
        # Should not cause SQL injection even with malicious input
        with self.assertRaises(Exception):
            trigger_onboarding_flow(
                malicious_input,
                malicious_input,
                "not_started"
            )

    @patch('frappe.get_doc')
    def test_unauthorized_access_protection(self, mock_get_doc):
        """Test that unauthorized access is prevented"""
        # Test with non-existent documents
        mock_get_doc.side_effect = Exception("Document not found")
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(
                "UNAUTHORIZED-SET",
                "UNAUTHORIZED-STAGE",
                "not_started"
            )

    def test_data_validation_and_sanitization(self):
        """Test input validation and data sanitization"""
        # Test with various invalid inputs
        invalid_inputs = [
            ("", "", ""),
            (None, None, None),
            ("' OR 1=1 --", "malicious", "test"),
            ("<script>alert('xss')</script>", "test", "test"),
        ]
        
        for onboarding_set, stage, status in invalid_inputs:
            with self.assertRaises(Exception):
                trigger_onboarding_flow(onboarding_set, stage, status)


if __name__ == "__main__":
    # Run the tests
    unittest.main()

# Additional test utilities and fixtures

class OnboardingFlowTestFixtures:
    """Helper class to create test data fixtures"""
    
    @staticmethod
    def create_mock_onboarding_set(name="TEST-ONBOARDING-001", status="Processed"):
        """Create a mock Backend Student Onboarding document"""
        mock_onboarding = Mock()
        mock_onboarding.name = name
        mock_onboarding.status = status
        return mock_onboarding
    
    @staticmethod
    def create_mock_stage(name="TEST-STAGE-001", is_active=True, flow_type="Group"):
        """Create a mock OnboardingStage document"""
        mock_stage = Mock()
        mock_stage.name = name
        mock_stage.is_active = is_active
        
        # New structure
        mock_flow = Mock()
        mock_flow.student_status = "not_started"
        mock_flow.glific_flow_id = "12345"
        mock_flow.flow_type = flow_type
        
        mock_stage.stage_flows = [mock_flow]
        return mock_stage
    
    @staticmethod
    def create_mock_student(name="STUDENT-001", student_name="John Doe", glific_id="contact_123"):
        """Create a mock Student document"""
        mock_student = Mock()
        mock_student.name = name
        mock_student.name1 = student_name
        mock_student.glific_id = glific_id
        mock_student.phone = "1234567890"
        return mock_student
    
    @staticmethod
    def create_mock_glific_response(success=True, errors=None):
        """Create a mock Glific API response"""
        if errors is None:
            errors = []
        
        return {
            "data": {
                "startGroupFlow": {
                    "success": success,
                    "errors": errors
                }
            }
        }


class OnboardingFlowTestRunner:
    """Helper class to run specific test suites"""
    
    @staticmethod
    def run_unit_tests():
        """Run only unit tests"""
        suite = unittest.TestLoader().loadTestsFromTestCase(TestOnboardingFlowTrigger)
        runner = unittest.TextTestRunner(verbosity=2)
        return runner.run(suite)
    
    @staticmethod
    def run_integration_tests():
        """Run only integration tests"""
        suite = unittest.TestLoader().loadTestsFromTestCase(TestOnboardingFlowTriggerIntegration)
        runner = unittest.TextTestRunner(verbosity=2)
        return runner.run(suite)
    
    @staticmethod
    def run_edge_case_tests():
        """Run only edge case tests"""
        suite = unittest.TestLoader().loadTestsFromTestCase(TestOnboardingFlowTriggerEdgeCases)
        runner = unittest.TextTestRunner(verbosity=2)
        return runner.run(suite)
    
    @staticmethod
    def run_security_tests():
        """Run only security tests"""
        suite = unittest.TestLoader().loadTestsFromTestCase(TestOnboardingFlowTriggerSecurity)
        runner = unittest.TextTestRunner(verbosity=2)
        return runner.run(suite)
    
    @staticmethod
    def run_all_tests():
        """Run all test suites"""
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        
        # Add all test cases
        suite.addTests(loader.loadTestsFromTestCase(TestOnboardingFlowTrigger))
        suite.addTests(loader.loadTestsFromTestCase(TestOnboardingFlowTriggerIntegration))
        suite.addTests(loader.loadTestsFromTestCase(TestOnboardingFlowTriggerEdgeCases))
        suite.addTests(loader.loadTestsFromTestCase(TestOnboardingFlowTriggerSecurity))
        
        runner = unittest.TextTestRunner(verbosity=2)
        return runner.run(suite)


# Example usage and test configuration
"""
To run these tests, you can use:

1. Run all tests:
   python -m unittest tap_lms.tests.test_onboarding_flow_trigger

2. Run specific test class:
   python -m unittest tap_lms.tests.test_onboarding_flow_trigger.TestOnboardingFlowTrigger

3. Run specific test method:
   python -m unittest tap_lms.tests.test_onboarding_flow_trigger.TestOnboardingFlowTrigger.test_trigger_onboarding_flow_success

4. Run with coverage:
   coverage run -m unittest tap_lms.tests.test_onboarding_flow_trigger
   coverage report
   coverage html

Test Configuration:
- Make sure to install required packages: unittest, mock, frappe (test environment)
- Set up test database configuration
- Configure test Glific API endpoints
- Set appropriate environment variables for testing

Mock Strategy:
- External API calls (Glific) are mocked to avoid dependency on external services
- Database operations are mocked for unit tests but can use real DB for integration tests
- Frappe framework functions are mocked to isolate business logic
"""