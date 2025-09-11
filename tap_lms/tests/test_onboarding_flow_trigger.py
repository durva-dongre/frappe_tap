

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

    # Tests for trigger_group_flow
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

    # Tests for update_incomplete_stages
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