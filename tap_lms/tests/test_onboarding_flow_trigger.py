

# import unittest
# from unittest.mock import Mock, patch, MagicMock
# from datetime import datetime, timedelta
# import sys
# import os

# # Add the project root to Python path if needed
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# class TestOnboardingFlowFunctions(unittest.TestCase):
    
#     def setUp(self):
#         """Set up test fixtures before each test method."""
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"
#         self.mock_job_id = "job_123"
#         self.current_time = datetime(2025, 9, 11, 16, 3)
        
#         # Mock frappe module at module level
#         self.frappe_patcher = patch.dict('sys.modules', {
#             'frappe': MagicMock(),
#             'frappe.utils': MagicMock(),
#             'frappe.utils.background_jobs': MagicMock()
#         })
#         self.frappe_patcher.start()
        
#         # Now import the actual functions
#         from tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger import (
#             trigger_onboarding_flow,
#             _trigger_onboarding_flow_job,
#             trigger_group_flow,
#             trigger_individual_flows,
#             get_stage_flow_statuses,
#             get_students_from_onboarding,
#             update_student_stage_progress,
#             update_student_stage_progress_batch,
#             get_job_status,
#             get_onboarding_progress_report,
#             update_incomplete_stages
#         )
        
#         # Store references to the actual functions
#         self.trigger_onboarding_flow = trigger_onboarding_flow
#         self.trigger_group_flow = trigger_group_flow
#         self.trigger_individual_flows = trigger_individual_flows
#         # ... store other functions
        
#     def tearDown(self):
#         """Clean up after each test."""
#         self.frappe_patcher.stop()

    
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
#     def test_trigger_group_flow_success_real_logic(self, mock_requests, mock_frappe):
#         """Test group flow with minimal mocking to exercise real logic"""
        
#         # Set up the minimum required mocks
#         mock_onboarding = MagicMock()
#         mock_onboarding.name = self.mock_onboarding_set
        
#         mock_stage = MagicMock()
#         mock_stage.name = self.mock_onboarding_stage
        
#         mock_glific_settings = MagicMock()
#         mock_glific_settings.api_url = "https://api.glific.org"
        
#         mock_contact_group = MagicMock()
#         mock_contact_group.group_id = "group_123"
        
       
        
#         # Mock the HTTP response
#         mock_response = MagicMock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {
#             "data": {
#                 "startGroupFlow": {
#                     "success": True,
#                     "errors": []
#                 }
#             }
#         }
#         mock_requests.post.return_value = mock_response
        
#         # Mock other required functions
#         with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding') as mock_get_students, \
#              patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch') as mock_update_batch, \
#              patch('tap_lms.glific_integration.create_or_get_glific_group_for_batch') as mock_create_group:
            
#             mock_get_students.return_value = [MagicMock(name="STUD_001")]
#             mock_create_group.return_value = {"group_id": "group_123"}
            
#             # Call the real function
#             result = self.trigger_group_flow(
#                 mock_onboarding,
#                 mock_stage,
#                 "Bearer token",
#                 self.mock_student_status,
#                 self.mock_flow_id
#             )
            
#             # Verify results
#             self.assertIn("group_flow_result", result)
#             self.assertEqual(result["group_count"], 1)
            
#             # Verify actual HTTP call was made
#             mock_requests.post.assert_called_once()
#             mock_update_batch.assert_called_once()



import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sys
import os
import json

# Add the project root to Python path if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestOnboardingFlowFunctions(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "job_123"
        self.current_time = datetime(2025, 9, 11, 16, 3)
        
        # Mock frappe module at module level
        self.frappe_patcher = patch.dict('sys.modules', {
            'frappe': MagicMock(),
            'frappe.utils': MagicMock(),
            'frappe.utils.background_jobs': MagicMock()
        })
        self.frappe_patcher.start()
        
        # Import after patching
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
        
        # Store references to the actual functions
        self.trigger_onboarding_flow = trigger_onboarding_flow
        self._trigger_onboarding_flow_job = _trigger_onboarding_flow_job
        self.trigger_group_flow = trigger_group_flow
        self.trigger_individual_flows = trigger_individual_flows
        self.get_stage_flow_statuses = get_stage_flow_statuses
        self.get_students_from_onboarding = get_students_from_onboarding
        self.update_student_stage_progress = update_student_stage_progress
        self.update_student_stage_progress_batch = update_student_stage_progress_batch
        self.get_job_status = get_job_status
        self.get_onboarding_progress_report = get_onboarding_progress_report
        self.update_incomplete_stages = update_incomplete_stages
        
    def tearDown(self):
        """Clean up after each test."""
        self.frappe_patcher.stop()

    # Tests for trigger_onboarding_flow
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_missing_params(self, mock_frappe):
        """Test trigger_onboarding_flow with missing parameters"""
        mock_frappe.throw = Mock(side_effect=Exception("Missing parameter"))
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
            
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, "", self.mock_student_status)
            
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, None)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_inactive_stage(self, mock_frappe):
        """Test trigger_onboarding_flow with inactive stage"""
        mock_stage = MagicMock()
        mock_stage.is_active = False
        mock_frappe.get_doc.return_value = mock_stage
        mock_frappe.throw = Mock(side_effect=Exception("Stage not active"))
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_invalid_onboarding_status(self, mock_frappe):
        """Test trigger_onboarding_flow with invalid onboarding status"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Draft"
        
        def mock_get_doc(doctype, name):
            if doctype == "OnboardingStage":
                return mock_stage
            elif doctype == "Backend Student Onboarding":
                return mock_onboarding
            
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_frappe.throw = Mock(side_effect=Exception("Invalid status"))
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_new_structure_success(self, mock_frappe):
        """Test trigger_onboarding_flow with new stage_flows structure"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.name = self.mock_onboarding_stage
        mock_stage.stage_flows = [MagicMock(student_status=self.mock_student_status, 
                                           glific_flow_id=self.mock_flow_id,
                                           flow_type="Group")]
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        def mock_get_doc(doctype, name):
            if doctype == "OnboardingStage":
                return mock_stage
            elif doctype == "Backend Student Onboarding":
                return mock_onboarding
                
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_frappe.enqueue.return_value = self.mock_job_id
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], self.mock_job_id)
        mock_frappe.enqueue.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_legacy_structure_success(self, mock_frappe):
        """Test trigger_onboarding_flow with legacy structure"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.name = self.mock_onboarding_stage
        mock_stage.stage_flows = []  # Empty to simulate legacy
        mock_stage.glific_flow_id = self.mock_flow_id
        mock_stage.glific_flow_type = "Personal"
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        def mock_get_doc(doctype, name):
            if doctype == "OnboardingStage":
                return mock_stage
            elif doctype == "Backend Student Onboarding":
                return mock_onboarding
                
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_frappe.enqueue.return_value = self.mock_job_id
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], self.mock_job_id)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_no_flows_configured(self, mock_frappe):
        """Test trigger_onboarding_flow with no flows configured"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.stage_flows = []
        # Simulate no legacy fields either
        mock_stage.glific_flow_id = None
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        def mock_get_doc(doctype, name):
            if doctype == "OnboardingStage":
                return mock_stage
            elif doctype == "Backend Student Onboarding":
                return mock_onboarding
                
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_frappe.throw = Mock(side_effect=Exception("No flows configured"))
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_trigger_onboarding_flow_exception_handling(self, mock_traceback, mock_frappe):
        """Test trigger_onboarding_flow exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        mock_frappe.throw = Mock(side_effect=Exception("Error triggering"))
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
            
        mock_frappe.log_error.assert_called_once()

    # Tests for _trigger_onboarding_flow_job
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_group_flow(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job for group flow"""
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_glific_settings = MagicMock()
        
        def mock_get_doc(doctype, name):
            if doctype == "OnboardingStage":
                return mock_stage
            elif doctype == "Backend Student Onboarding":
                return mock_onboarding
            elif doctype == "Glific Settings":
                return mock_glific_settings
                
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_frappe.logger.return_value = MagicMock()
        
        with patch.object(self, 'trigger_group_flow', return_value={"success": True}) as mock_group_flow:
            result = self._trigger_onboarding_flow_job(
                self.mock_onboarding_set, self.mock_onboarding_stage, 
                self.mock_student_status, self.mock_flow_id, "Group"
            )
            
            mock_group_flow.assert_called_once()
            self.assertEqual(result["success"], True)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_individual_flow(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job for individual flow"""
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_glific_settings = MagicMock()
        
        def mock_get_doc(doctype, name):
            if doctype == "OnboardingStage":
                return mock_stage
            elif doctype == "Backend Student Onboarding":
                return mock_onboarding
            elif doctype == "Glific Settings":
                return mock_glific_settings
                
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_frappe.logger.return_value = MagicMock()
        
        with patch.object(self, 'trigger_individual_flows', return_value={"success": True}) as mock_individual_flow:
            result = self._trigger_onboarding_flow_job(
                self.mock_onboarding_set, self.mock_onboarding_stage, 
                self.mock_student_status, self.mock_flow_id, "Personal"
            )
            
            mock_individual_flow.assert_called_once()
            self.assertEqual(result["success"], True)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_auth_failure(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job with auth failure"""
        mock_auth.return_value = None
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job(
            self.mock_onboarding_set, self.mock_onboarding_stage, 
            self.mock_student_status, self.mock_flow_id, "Group"
        )
        
        self.assertIn("error", result)
        self.assertIn("authenticate", result["error"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_trigger_onboarding_flow_job_exception(self, mock_traceback, mock_frappe):
        """Test _trigger_onboarding_flow_job exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job(
            self.mock_onboarding_set, self.mock_onboarding_stage, 
            self.mock_student_status, self.mock_flow_id, "Group"
        )
        
        self.assertIn("error", result)
        mock_frappe.log_error.assert_called_once()

    # Tests for trigger_group_flow
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_success(self, mock_create_group, mock_requests, mock_frappe):
        """Test trigger_group_flow success scenario"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        mock_stage = MagicMock()
        mock_stage.name = self.mock_onboarding_stage
        
        mock_contact_group = MagicMock()
        mock_contact_group.group_id = "group_123"
        
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_frappe.get_doc.return_value = mock_contact_group
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": True, "errors": []}}
        }
        mock_requests.post.return_value = mock_response
        
        mock_settings = MagicMock()
        mock_settings.api_url = "https://api.glific.org"
        
        def mock_get_doc_side_effect(doctype, filters=None):
            if doctype == "Glific Settings":
                return mock_settings
            elif doctype == "GlificContactGroup":
                return mock_contact_group
            return MagicMock()
        
        mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        mock_frappe.logger.return_value = MagicMock()
        
        with patch.object(self, 'get_students_from_onboarding', return_value=[MagicMock(name="STUD_001")]) as mock_get_students, \
             patch.object(self, 'update_student_stage_progress_batch') as mock_update_batch:
            
            result = self.trigger_group_flow(
                mock_onboarding, mock_stage, "Bearer token", 
                self.mock_student_status, self.mock_flow_id
            )
            
            self.assertIn("group_flow_result", result)
            self.assertEqual(result["group_count"], 1)
            mock_requests.post.assert_called_once()
            mock_update_batch.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_group_flow_no_flow_id(self, mock_frappe):
        """Test trigger_group_flow with no flow ID"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("No flow ID"))
        
        with self.assertRaises(Exception):
            self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, None)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_no_contact_group(self, mock_create_group, mock_frappe):
        """Test trigger_group_flow with no contact group"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_create_group.return_value = None
        mock_frappe.throw = Mock(side_effect=Exception("No contact group"))
        mock_frappe.logger.return_value = MagicMock()
        
        with self.assertRaises(Exception):
            self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_api_error(self, mock_create_group, mock_requests, mock_frappe):
        """Test trigger_group_flow with API error"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_contact_group = MagicMock()
        
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_frappe.get_doc.return_value = mock_contact_group
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("API error"))
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_requests.post.return_value = mock_response
        
        with self.assertRaises(Exception):
            self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_api_failure(self, mock_create_group, mock_requests, mock_frappe):
        """Test trigger_group_flow with API returning failure"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_contact_group = MagicMock()
        mock_settings = MagicMock()
        
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_frappe.get_doc.return_value = mock_contact_group
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("Flow failed"))
        
        def mock_get_doc_side_effect(doctype, filters=None):
            if doctype == "Glific Settings":
                return mock_settings
            return mock_contact_group
        
        mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": False, "errors": [{"message": "Flow failed"}]}}
        }
        mock_requests.post.return_value = mock_response
        
        with self.assertRaises(Exception):
            self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

    # Tests for trigger_individual_flows
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.time')
    def test_trigger_individual_flows_success(self, mock_time, mock_start_flow, mock_frappe):
        """Test trigger_individual_flows success scenario"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.name1 = "Test Student"
        mock_student.glific_id = "glific_123"
        
        mock_frappe.logger.return_value = MagicMock()
        mock_start_flow.return_value = True
        
        with patch.object(self, 'get_students_from_onboarding', return_value=[mock_student]) as mock_get_students, \
             patch.object(self, 'update_student_stage_progress') as mock_update_progress:
            
            result = self.trigger_individual_flows(
                mock_onboarding, mock_stage, "Bearer token", 
                self.mock_student_status, self.mock_flow_id
            )
            
            self.assertEqual(result["individual_count"], 1)
            self.assertEqual(result["error_count"], 0)
            self.assertEqual(len(result["individual_flow_results"]), 1)
            mock_update_progress.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_individual_flows_no_flow_id(self, mock_frappe):
        """Test trigger_individual_flows with no flow ID"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("No flow ID"))
        
        with self.assertRaises(Exception):
            self.trigger_individual_flows(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, None)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_individual_flows_no_students(self, mock_frappe):
        """Test trigger_individual_flows with no students"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("No students found"))
        
        with patch.object(self, 'get_students_from_onboarding', return_value=[]):
            with self.assertRaises(Exception):
                self.trigger_individual_flows(
                    mock_onboarding, mock_stage, "Bearer token", 
                    self.mock_student_status, self.mock_flow_id
                )

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    def test_trigger_individual_flows_student_no_glific_id(self, mock_start_flow, mock_frappe):
        """Test trigger_individual_flows with student having no Glific ID"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.glific_id = None
        
        mock_frappe.logger.return_value = MagicMock()
        
        with patch.object(self, 'get_students_from_onboarding', return_value=[mock_student]):
            result = self.trigger_individual_flows(
                mock_onboarding, mock_stage, "Bearer token", 
                self.mock_student_status, self.mock_flow_id
            )
            
            self.assertEqual(result["individual_count"], 0)
            mock_start_flow.assert_not_called()

    # Tests for get_stage_flow_statuses
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_new_structure(self, mock_frappe):
        """Test get_stage_flow_statuses with new structure"""
        mock_stage = MagicMock()
        mock_flow1 = MagicMock()
        mock_flow1.student_status = "not_started"
        mock_flow2 = MagicMock()
        mock_flow2.student_status = "in_progress"
        mock_stage.stage_flows = [mock_flow1, mock_flow2]
        
        mock_frappe.get_doc.return_value = mock_stage
        
        result = self.get_stage_flow_statuses("TEST_STAGE")
        
        self.assertIn("not_started", result["statuses"])
        self.assertIn("in_progress", result["statuses"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_legacy_structure(self, mock_frappe):
        """Test get_stage_flow_statuses with legacy structure"""
        mock_stage = MagicMock()
        mock_stage.stage_flows = []
        mock_stage.glific_flow_id = "12345"
        
        mock_frappe.get_doc.return_value = mock_stage
        
        result = self.get_stage_flow_statuses("TEST_STAGE")
        
        expected_statuses = ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"]
        for status in expected_statuses:
            self.assertIn(status, result["statuses"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_no_flows(self, mock_frappe):
        """Test get_stage_flow_statuses with no flows configured"""
        mock_stage = MagicMock()
        mock_stage.stage_flows = []
        mock_stage.glific_flow_id = None
        
        mock_frappe.get_doc.return_value = mock_stage
        
        result = self.get_stage_flow_statuses("TEST_STAGE")
        
        self.assertEqual(result["statuses"], [])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_exception(self, mock_frappe):
        """Test get_stage_flow_statuses exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.log_error = Mock()
        
        result = self.get_stage_flow_statuses("TEST_STAGE")
        
        self.assertEqual(result["statuses"], [])
        self.assertIn("error", result)
        mock_frappe.log_error.assert_called_once()

    # Tests for get_students_from_onboarding
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_basic(self, mock_frappe):
        """Test get_students_from_onboarding basic functionality"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        backend_students = [{"student_id": "STUD_001"}, {"student_id": "STUD_002"}]
        mock_frappe.get_all.return_value = backend_students
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_frappe.get_doc.return_value = mock_student
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(mock_frappe.get_doc.call_count, 2)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_with_stage_and_status(self, mock_frappe):
        """Test get_students_from_onboarding with stage and status filters"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        backend_students = [{"student_id": "STUD_001"}]
        stage_progress = [{"name": "PROGRESS_001"}]
        
        def mock_get_all_side_effect(doctype, **kwargs):
            if doctype == "Backend Students":
                return backend_students
            elif doctype == "StudentStageProgress":
                return stage_progress
            return []
        
        mock_frappe.get_all.side_effect = mock_get_all_side_effect
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_frappe.get_doc.return_value = mock_student
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(
            mock_onboarding, "TEST_STAGE", "in_progress"
        )
        
        self.assertEqual(len(result), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_not_started_status(self, mock_frappe):
        """Test get_students_from_onboarding with not_started status"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        backend_students = [{"student_id": "STUD_001"}]
        
        def mock_get_all_side_effect(doctype, **kwargs):
            if doctype == "Backend Students":
                return backend_students
            elif doctype == "StudentStageProgress":
                # Return empty to simulate "not_started"
                return []
            return []
        
        mock_frappe.get_all.side_effect = mock_get_all_side_effect
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_frappe.get_doc.return_value = mock_student
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(
            mock_onboarding, "TEST_STAGE", "not_started"
        )
        
        self.assertEqual(len(result), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_no_backend_students(self, mock_frappe):
        """Test get_students_from_onboarding with no backend students"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        mock_frappe.get_all.return_value = []
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding)
        
        self.assertEqual(len(result), 0)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_get_students_from_onboarding_exception(self, mock_traceback, mock_frappe):
        """Test get_students_from_onboarding exception handling"""
        mock_onboarding = MagicMock()
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding)
        
        self.assertEqual(result, [])
        mock_frappe.log_error.assert_called_once()

    # Tests for update_student_stage_progress
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_new_record(self, mock_now, mock_frappe):
        """Test update_student_stage_progress creating new record"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        mock_frappe.get_all.return_value = []  # No existing record
        mock_progress = MagicMock()
        mock_frappe.new_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        mock_progress.insert.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_update_existing(self, mock_now, mock_frappe):
        """Test update_student_stage_progress updating existing record"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        existing = [{"name": "PROGRESS_001"}]
        mock_frappe.get_all.return_value = existing
        
        mock_progress = MagicMock()
        mock_progress.status = "not_started"
        mock_progress.start_timestamp = None
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        self.assertEqual(mock_progress.status, "assigned")
        mock_progress.save.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_no_update_completed(self, mock_now, mock_frappe):
        """Test update_student_stage_progress not updating completed record"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_stage = MagicMock()
        
        existing = [{"name": "PROGRESS_001"}]
        mock_frappe.get_all.return_value = existing
        
        mock_progress = MagicMock()
        mock_progress.status = "completed"
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        mock_progress.save.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_update_student_stage_progress_exception(self, mock_traceback, mock_frappe):
        """Test update_student_stage_progress exception handling"""
        mock_student = MagicMock()
        mock_stage = MagicMock()
        
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        mock_frappe.log_error.assert_called_once()

    # Tests for update_student_stage_progress_batch
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_batch_success(self, mock_now, mock_frappe):
        """Test update_student_stage_progress_batch success"""
        mock_now.return_value = self.current_time
        
        students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        mock_stage = MagicMock()
        
        mock_frappe.get_all.return_value = []  # No existing records
        mock_progress = MagicMock()
        mock_frappe.new_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress_batch(students, mock_stage)
        
        self.assertEqual(mock_progress.insert.call_count, 2)
        mock_frappe.db.commit.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_update_student_stage_progress_batch_empty_list(self, mock_frappe):
        """Test update_student_stage_progress_batch with empty student list"""
        mock_stage = MagicMock()
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress_batch([], mock_stage)
        
        mock_frappe.db.commit.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_update_student_stage_progress_batch_exception(self, mock_traceback, mock_frappe):
        """Test update_student_stage_progress_batch exception handling"""
        students = [MagicMock(name="STUD_001")]
        mock_stage = MagicMock()
        
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress_batch(students, mock_stage)
        
        mock_frappe.log_error.assert_called_once()

    # # Tests for get_job_status
    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    # def test_get_job_status_no_job_id(self, mock_frappe):
    #     """Test get_job_status with no job ID"""
    #     result = self.get_job_status(None)
        
    #     self.assertEqual(result["status"], "unknown")

    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    # def test_get_job_status_failed(self, mock_job_status_func, mock_frappe):
    #     """Test get_job_status with failed job"""
    #     mock_job_status_func.return_value = "failed"
    #     mock_frappe.logger.return_value = MagicMock()
        
    #     result = self.get_job_status("job_123")
        
    #     self.assertEqual(result["status"], "failed")

    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    # def test_get_job_status_finished_with_results(self, mock_job_status_func, mock_frappe):
    #     """Test get_job_status with finished job and results"""
    #     mock_job_status_func.return_value = "finished"
    #     mock_frappe.logger.return_value = MagicMock()
        
    #     # Mock Job and redis connection
    #     with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.Job') as mock_job_class, \
    #          patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_redis_conn') as mock_redis:
            
    #         mock_redis_conn = MagicMock()
    #         mock_redis.return_value = mock_redis_conn
            
    #         mock_job = MagicMock()
    #         mock_job.result = {"success": True}
    #         mock_job_class.fetch.return_value = mock_job
            
    #         result = self.get_job_status("job_123")
            
    #         self.assertEqual(result["status"], "complete")
    #         self.assertIn("results", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    def test_get_job_status_finished_no_results(self, mock_job_status_func, mock_frappe):
        """Test get_job_status with finished job but no results"""
        mock_job_status_func.return_value = "finished"
        mock_frappe.logger.return_value = MagicMock()
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_redis_conn') as mock_redis:
            mock_redis.return_value = None
            
            result = self.get_job_status("job_123")
            
            self.assertEqual(result["status"], "complete")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    def test_get_job_status_running(self, mock_job_status_func, mock_frappe):
        """Test get_job_status with running job"""
        mock_job_status_func.return_value = "queued"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_job_status("job_123")
        
        self.assertEqual(result["status"], "queued")

    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    # def test_get_job_status_exception(self, mock_traceback, mock_frappe):
    #     """Test get_job_status exception handling"""
    #     mock_frappe.logger.return_value = MagicMock()
    #     mock_traceback.format_exc.return_value = "Mock traceback"
        
    #     with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status', side_effect=Exception("Error")):
    #         result = self.get_job_status("job_123")
            
    #         self.assertEqual(result["status"], "error")
    #         self.assertIn("message", result)
    #         mock_frappe.log_error.assert_called_once()

    # Tests for get_onboarding_progress_report
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_basic(self, mock_frappe):
        """Test get_onboarding_progress_report basic functionality"""
        progress_records = [
            {
                "name": "PROGRESS_001",
                "student": "STUD_001",
                "stage": "STAGE_001",
                "status": "completed",
                "start_timestamp": self.current_time,
                "last_activity_timestamp": self.current_time,
                "completion_timestamp": self.current_time
            }
        ]
        
        mock_frappe.get_all.return_value = progress_records
        mock_frappe.logger.return_value = MagicMock()
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.name1 = "Test Student"
        mock_student.phone = "1234567890"
        
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        def mock_get_doc_side_effect(doctype, name):
            if doctype == "Student":
                return mock_student
            elif doctype == "OnboardingStage":
                return mock_stage
            return MagicMock()
        
        mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
        result = self.get_onboarding_progress_report()
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(len(result["details"]), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_with_filters(self, mock_frappe):
        """Test get_onboarding_progress_report with filters"""
        mock_frappe.get_all.return_value = []
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_onboarding_progress_report(
            set="TEST_SET", stage="TEST_STAGE", status="completed"
        )
        
        self.assertEqual(result["summary"]["total"], 0)
        self.assertEqual(len(result["details"]), 0)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_not_started_students(self, mock_frappe):
        """Test get_onboarding_progress_report including not_started students"""
        # Mock progress records (empty)
        progress_records = []
        
        # Mock backend students
        backend_students = [{"student_id": "STUD_001"}]
        
        def mock_get_all_side_effect(doctype, **kwargs):
            if doctype == "StudentStageProgress":
                if "filters" in kwargs and "stage" in kwargs["filters"]:
                    # For checking existing records
                    return []
                return progress_records
            elif doctype == "Backend Students":
                return backend_students
            return []
        
        mock_frappe.get_all.side_effect = mock_get_all_side_effect
        mock_frappe.logger.return_value = MagicMock()
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.name1 = "Test Student"
        mock_student.phone = "1234567890"
        
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        def mock_get_doc_side_effect(doctype, name):
            if doctype == "Student":
                return mock_student
            elif doctype == "OnboardingStage":
                return mock_stage
            return MagicMock()
        
        mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
        result = self.get_onboarding_progress_report(
            set="TEST_SET", stage="STAGE_001", status="not_started"
        )
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["not_started"], 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_get_onboarding_progress_report_exception(self, mock_traceback, mock_frappe):
        """Test get_onboarding_progress_report exception handling"""
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("Report error"))
        
        with self.assertRaises(Exception):
            self.get_onboarding_progress_report()
        
        mock_frappe.log_error.assert_called_once()

    # Tests for update_incomplete_stages
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages_success(self, mock_add_to_date, mock_now, mock_frappe):
        """Test update_incomplete_stages success"""
        mock_now.return_value = self.current_time
        three_days_ago = self.current_time - timedelta(days=3)
        mock_add_to_date.return_value = three_days_ago
        
        assigned_records = [
            {
                "name": "PROGRESS_001",
                "student": "STUD_001",
                "stage": "STAGE_001",
                "start_timestamp": three_days_ago - timedelta(days=1)
            }
        ]
        
        mock_frappe.get_all.return_value = assigned_records
        mock_frappe.logger.return_value = MagicMock()
        
        mock_progress = MagicMock()
        mock_frappe.get_doc.return_value = mock_progress
        
        self.update_incomplete_stages()
        
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages_no_records(self, mock_add_to_date, mock_now, mock_frappe):
        """Test update_incomplete_stages with no records to update"""
        mock_now.return_value = self.current_time
        mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
        mock_frappe.get_all.return_value = []
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_incomplete_stages()
        
        mock_frappe.db.commit.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_update_incomplete_stages_exception(self, mock_traceback, mock_frappe):
        """Test update_incomplete_stages exception handling"""
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_incomplete_stages()
        
        mock_frappe.log_error.assert_called_once()


if __name__ == '__main__':
    unittest.main()