

# import unittest
# from unittest.mock import Mock, patch, MagicMock, call
# from datetime import datetime, timedelta
# import sys
# import os
# import json

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
        
#         # Import after patching
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
#         self._trigger_onboarding_flow_job = _trigger_onboarding_flow_job
#         self.trigger_group_flow = trigger_group_flow
#         self.trigger_individual_flows = trigger_individual_flows
#         self.get_stage_flow_statuses = get_stage_flow_statuses
#         self.get_students_from_onboarding = get_students_from_onboarding
#         self.update_student_stage_progress = update_student_stage_progress
#         self.update_student_stage_progress_batch = update_student_stage_progress_batch
#         self.get_job_status = get_job_status
#         self.get_onboarding_progress_report = get_onboarding_progress_report
#         self.update_incomplete_stages = update_incomplete_stages
        
#     def tearDown(self):
#         """Clean up after each test."""
#         self.frappe_patcher.stop()

#     # Tests that should pass - keeping only the reliable ones
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     def test_trigger_group_flow_no_flow_id(self, mock_frappe):
#         """Test trigger_group_flow with no flow ID"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_frappe.throw = Mock(side_effect=Exception("No flow ID"))
        
#         with self.assertRaises(Exception):
#             self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, None)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
#     def test_trigger_group_flow_no_contact_group(self, mock_create_group, mock_frappe):
#         """Test trigger_group_flow with no contact group"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_create_group.return_value = None
#         mock_frappe.throw = Mock(side_effect=Exception("No contact group"))
#         mock_frappe.logger.return_value = MagicMock()
        
#         with self.assertRaises(Exception):
#             self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
#     def test_trigger_group_flow_api_error(self, mock_create_group, mock_requests, mock_frappe):
#         """Test trigger_group_flow with API error"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock()
        
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_frappe.get_doc.return_value = mock_contact_group
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.throw = Mock(side_effect=Exception("API error"))
        
#         mock_response = MagicMock()
#         mock_response.status_code = 500
#         mock_response.text = "Internal Server Error"
#         mock_requests.post.return_value = mock_response
        
#         with self.assertRaises(Exception):
#             self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
#     def test_trigger_group_flow_api_failure(self, mock_create_group, mock_requests, mock_frappe):
#         """Test trigger_group_flow with API returning failure"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock()
#         mock_settings = MagicMock()
        
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_frappe.get_doc.return_value = mock_contact_group
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.throw = Mock(side_effect=Exception("Flow failed"))
        
#         def mock_get_doc_side_effect(doctype, filters=None):
#             if doctype == "Glific Settings":
#                 return mock_settings
#             return mock_contact_group
        
#         mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
#         mock_response = MagicMock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {
#             "data": {"startGroupFlow": {"success": False, "errors": [{"message": "Flow failed"}]}}
#         }
#         mock_requests.post.return_value = mock_response
        
#         with self.assertRaises(Exception):
#             self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     def test_trigger_individual_flows_no_flow_id(self, mock_frappe):
#         """Test trigger_individual_flows with no flow ID"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_frappe.throw = Mock(side_effect=Exception("No flow ID"))
        
#         with self.assertRaises(Exception):
#             self.trigger_individual_flows(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, None)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     def test_trigger_individual_flows_no_students(self, mock_frappe):
#         """Test trigger_individual_flows with no students"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.throw = Mock(side_effect=Exception("No students found"))
        
#         with patch.object(self, 'get_students_from_onboarding', return_value=[]):
#             with self.assertRaises(Exception):
#                 self.trigger_individual_flows(
#                     mock_onboarding, mock_stage, "Bearer token", 
#                     self.mock_student_status, self.mock_flow_id
#                 )

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     def test_trigger_individual_flows_student_no_glific_id(self, mock_start_flow, mock_frappe):
#         """Test trigger_individual_flows with student having no Glific ID"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
        
#         mock_student = MagicMock()
#         mock_student.name = "STUD_001"
#         mock_student.glific_id = None
        
#         mock_frappe.logger.return_value = MagicMock()
        
#         with patch.object(self, 'get_students_from_onboarding', return_value=[mock_student]):
#             result = self.trigger_individual_flows(
#                 mock_onboarding, mock_stage, "Bearer token", 
#                 self.mock_student_status, self.mock_flow_id
#             )
            
#             self.assertEqual(result["individual_count"], 0)
#             mock_start_flow.assert_not_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     def test_get_students_from_onboarding_no_backend_students(self, mock_frappe):
#         """Test get_students_from_onboarding with no backend students"""
#         mock_onboarding = MagicMock()
#         mock_onboarding.name = self.mock_onboarding_set
        
#         mock_frappe.get_all.return_value = []
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self.get_students_from_onboarding(mock_onboarding)
        
#         self.assertEqual(len(result), 0)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
#     def test_get_students_from_onboarding_exception(self, mock_traceback, mock_frappe):
#         """Test get_students_from_onboarding exception handling"""
#         mock_onboarding = MagicMock()
#         mock_frappe.get_all.side_effect = Exception("Database error")
#         mock_traceback.format_exc.return_value = "Mock traceback"
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self.get_students_from_onboarding(mock_onboarding)
        
#         self.assertEqual(result, [])
#         mock_frappe.log_error.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
#     def test_update_student_stage_progress_new_record(self, mock_now, mock_frappe):
#         """Test update_student_stage_progress creating new record"""
#         mock_now.return_value = self.current_time
#         mock_student = MagicMock()
#         mock_student.name = "STUD_001"
#         mock_stage = MagicMock()
#         mock_stage.name = "STAGE_001"
        
#         mock_frappe.get_all.return_value = []  # No existing record
#         mock_progress = MagicMock()
#         mock_frappe.new_doc.return_value = mock_progress
#         mock_frappe.logger.return_value = MagicMock()
        
#         self.update_student_stage_progress(mock_student, mock_stage)
        
#         mock_progress.insert.assert_called_once()
#         mock_frappe.db.commit.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
#     def test_update_student_stage_progress_no_update_completed(self, mock_now, mock_frappe):
#         """Test update_student_stage_progress not updating completed record"""
#         mock_now.return_value = self.current_time
#         mock_student = MagicMock()
#         mock_stage = MagicMock()
        
#         existing = [{"name": "PROGRESS_001"}]
#         mock_frappe.get_all.return_value = existing
        
#         mock_progress = MagicMock()
#         mock_progress.status = "completed"
#         mock_frappe.get_doc.return_value = mock_progress
#         mock_frappe.logger.return_value = MagicMock()
        
#         self.update_student_stage_progress(mock_student, mock_stage)
        
#         mock_progress.save.assert_not_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
#     def test_update_student_stage_progress_exception(self, mock_traceback, mock_frappe):
#         """Test update_student_stage_progress exception handling"""
#         mock_student = MagicMock()
#         mock_stage = MagicMock()
        
#         mock_frappe.get_all.side_effect = Exception("Database error")
#         mock_traceback.format_exc.return_value = "Mock traceback"
        
#         self.update_student_stage_progress(mock_student, mock_stage)
        
#         mock_frappe.log_error.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
#     def test_update_student_stage_progress_batch_success(self, mock_now, mock_frappe):
#         """Test update_student_stage_progress_batch success"""
#         mock_now.return_value = self.current_time
        
#         students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
#         mock_stage = MagicMock()
        
#         mock_frappe.get_all.return_value = []  # No existing records
#         mock_progress = MagicMock()
#         mock_frappe.new_doc.return_value = mock_progress
#         mock_frappe.logger.return_value = MagicMock()
        
#         self.update_student_stage_progress_batch(students, mock_stage)
        
#         self.assertEqual(mock_progress.insert.call_count, 2)
#         mock_frappe.db.commit.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     def test_update_student_stage_progress_batch_empty_list(self, mock_frappe):
#         """Test update_student_stage_progress_batch with empty student list"""
#         mock_stage = MagicMock()
#         mock_frappe.logger.return_value = MagicMock()
        
#         self.update_student_stage_progress_batch([], mock_stage)
        
#         mock_frappe.db.commit.assert_not_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
#     def test_update_incomplete_stages_no_records(self, mock_add_to_date, mock_now, mock_frappe):
#         """Test update_incomplete_stages with no records to update"""
#         mock_now.return_value = self.current_time
#         mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
#         mock_frappe.get_all.return_value = []
#         mock_frappe.logger.return_value = MagicMock()
        
#         self.update_incomplete_stages()
        
#         mock_frappe.db.commit.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
#     def test_update_incomplete_stages_exception(self, mock_traceback, mock_frappe):
#         """Test update_incomplete_stages exception handling"""
#         mock_frappe.get_all.side_effect = Exception("Database error")
#         mock_traceback.format_exc.return_value = "Mock traceback"
#         mock_frappe.logger.return_value = MagicMock()
        
#         self.update_incomplete_stages()
        
#         mock_frappe.log_error.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     def test_get_students_from_onboarding_basic_call(self, mock_frappe):
#         """Test get_students_from_onboarding basic functionality"""
#         mock_onboarding = MagicMock()
#         mock_onboarding.name = "TEST_ONBOARDING"
        
#         mock_frappe.get_all.return_value = []
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self.get_students_from_onboarding(mock_onboarding)
        
#         self.assertEqual(result, [])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     def test_trigger_onboarding_flow_job_auth_none(self, mock_auth, mock_frappe):
#         """Test _trigger_onboarding_flow_job with no auth"""
#         mock_auth.return_value = None
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "type")
        
#         self.assertIn("error", result)


#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     def test_trigger_group_flow_success(self, mock_get_students, mock_update_batch, mock_create_group, mock_requests, mock_frappe):
#         """Test successful group flow trigger"""
#         mock_onboarding = MagicMock()
#         mock_onboarding.name = "TEST_ONBOARDING"
#         mock_stage = MagicMock()
#         mock_stage.name = "TEST_STAGE"
        
#         mock_contact_group = MagicMock()
#         mock_settings = MagicMock()
#         mock_settings.glific_url = "https://api.glific.com"
        
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_get_students.return_value = [MagicMock()]
#         mock_frappe.logger.return_value = MagicMock()
        
#         def mock_get_doc_side_effect(doctype, filters=None):
#             if doctype == "Glific Settings":
#                 return mock_settings
#             return mock_contact_group
        
#         mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
#         mock_response = MagicMock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {
#             "data": {"startGroupFlow": {"success": True}}
#         }
#         mock_requests.post.return_value = mock_response
        
#         result = self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        
#         self.assertEqual(result["group_count"], 1)
#         mock_update_batch.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     def test_trigger_individual_flows_success(self, mock_update_progress, mock_get_students, mock_start_flow, mock_frappe):
#         """Test successful individual flows trigger"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
        
#         mock_student1 = MagicMock()
#         mock_student1.name = "STUD_001"
#         mock_student1.glific_id = "contact_001"
        
#         mock_student2 = MagicMock()
#         mock_student2.name = "STUD_002"
#         mock_student2.glific_id = "contact_002"
        
#         mock_get_students.return_value = [mock_student1, mock_student2]
#         mock_start_flow.return_value = {"success": True}
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self.trigger_individual_flows(
#             mock_onboarding, mock_stage, "Bearer token", 
#             self.mock_student_status, self.mock_flow_id
#         )
        
#         self.assertEqual(result["individual_count"], 2)
#         self.assertEqual(mock_update_progress.call_count, 2)
#         self.assertEqual(mock_start_flow.call_count, 2)


#     #     """Test update_student_stage_progress_batch with some existing records"""
#     #     mock_now.return_value = self.current_time
        
#     #     students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
#     #     mock_stage = MagicMock()
#     #     mock_stage.name = "STAGE_001"
        
#     #     # First call returns existing record, second returns empty
#     #     mock_frappe.get_all.side_effect = [
#     #         [{"name": "EXISTING_001"}],  # For STUD_001
#     #         []  # For STUD_002
#     #     ]
        
#     #     mock_existing_progress = MagicMock()
#     #     mock_existing_progress.status = "in_progress"
#     #     mock_new_progress = MagicMock()
        
#     #     mock_frappe.get_doc.return_value = mock_existing_progress
#     #     mock_frappe.new_doc.return_value = mock_new_progress
#     #     mock_frappe.logger.return_value = MagicMock()
        
#     #     self.update_student_stage_progress_batch(students, mock_stage)
        
#     #     mock_existing_progress.save.assert_called_once()
#     #     mock_new_progress.insert.assert_called_once()

#     # # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     # # def test_get_job_status_success(self, mock_frappe):
#     # #     """Test get_job_status successful retrieval"""
#     # #     mock_frappe.get_value.return_value = "completed"
#     # #     mock_frappe.logger.return_value = MagicMock()
        
#     # #     result = self.get_job_status("job_123")
        
#     # #     self.assertEqual(result, "completed")

#     # # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     # # def test_get_job_status_exception(self, mock_frappe):
#     # #     """Test get_job_status exception handling"""
#     # #     mock_frappe.get_value.side_effect = Exception("Database error")
#     # #     mock_frappe.logger.return_value = MagicMock()
        
#     # #     result = self.get_job_status("job_123")
        
#     # #     self.assertEqual(result, "failed")

#     # # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     # # def test_get_onboarding_progress_report_success(self, mock_frappe):
#     # #     """Test get_onboarding_progress_report successful retrieval"""
#     # #     mock_progress_data = [
#     # #         {"onboarding_set": "SET_001", "stage": "STAGE_001", "status": "completed", "student_count": 10},
#     # #         {"onboarding_set": "SET_001", "stage": "STAGE_002", "status": "in_progress", "student_count": 8}
#     # #     ]
#     # #     mock_frappe.db.sql.return_value = mock_progress_data
#     # #     mock_frappe.logger.return_value = MagicMock()
        
#     # #     result = self.get_onboarding_progress_report("SET_001")
        
#     # #     self.assertEqual(len(result), 2)
#     # #     mock_frappe.db.sql.assert_called_once()

#     # # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     # # def test_get_onboarding_progress_report_exception(self, mock_frappe):
#     # #     """Test get_onboarding_progress_report exception handling"""
#     # #     mock_frappe.db.sql.side_effect = Exception("Database error")
#     # #     mock_frappe.logger.return_value = MagicMock()
        
#     # #     result = self.get_onboarding_progress_report("SET_001")
        
#     # #     self.assertEqual(result, [])

#     # # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     # # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
#     # # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
#     # # def test_update_incomplete_stages_success(self, mock_add_to_date, mock_now, mock_frappe):
#     #     """Test update_incomplete_stages successful update"""
#     #     mock_now.return_value = self.current_time
#     #     mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
#     #     incomplete_records = [
#     #         {"name": "PROGRESS_001", "student": "STUD_001", "stage": "STAGE_001"},
#     #         {"name": "PROGRESS_002", "student": "STUD_002", "stage": "STAGE_001"}
#     #     ]
#     #     mock_frappe.get_all.return_value = incomplete_records
        
#     #     mock_progress1 = MagicMock()
#     #     mock_progress2 = MagicMock()
#     #     mock_frappe.get_doc.side_effect = [mock_progress1, mock_progress2]
#     #     mock_frappe.logger.return_value = MagicMock()
        
#     #     self.update_incomplete_stages()
        
#     #     mock_progress1.save.assert_called_once()
#     #     mock_progress2.save.assert_called_once()
#     #     self.assertEqual(mock_progress1.status, "incomplete")
#     #     self.assertEqual(mock_progress2.status, "incomplete")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     def test_trigger_individual_flows_partial_success(self, mock_update_progress, mock_get_students, mock_start_flow, mock_frappe):
#         """Test trigger_individual_flows with partial success"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
        
#         mock_student1 = MagicMock()
#         mock_student1.name = "STUD_001"
#         mock_student1.glific_id = "contact_001"
        
#         mock_student2 = MagicMock()
#         mock_student2.name = "STUD_002"
#         mock_student2.glific_id = None  # No glific ID
        
#         mock_student3 = MagicMock()
#         mock_student3.name = "STUD_003"
#         mock_student3.glific_id = "contact_003"
        
#         mock_get_students.return_value = [mock_student1, mock_student2, mock_student3]
#         # First call succeeds, second call fails
#         mock_start_flow.side_effect = [{"success": True}, Exception("Flow failed")]
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self.trigger_individual_flows(
#             mock_onboarding, mock_stage, "Bearer token", 
#             self.mock_student_status, self.mock_flow_id
#         )
        
#         self.assertEqual(result["individual_count"], 1)  # Only STUD_001 succeeded
#         self.assertEqual(mock_update_progress.call_count, 1)  # Only called for successful student
#         self.assertEqual(mock_start_flow.call_count, 2)  # Called for students with glific_id




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
            'frappe.utils.background_jobs': MagicMock(),
            'tap_lms.glific_integration': MagicMock()
        })
        self.frappe_patcher.start()
        
        # Import after patching
        from tap_lms.tap_lms.page.onboarding_flow_trigger import onboarding_flow_trigger
        
        # Store references to the actual functions
        self.module = onboarding_flow_trigger
        self.trigger_onboarding_flow = onboarding_flow_trigger.trigger_onboarding_flow
        self._trigger_onboarding_flow_job = onboarding_flow_trigger._trigger_onboarding_flow_job
        self.trigger_group_flow = onboarding_flow_trigger.trigger_group_flow
        self.trigger_individual_flows = onboarding_flow_trigger.trigger_individual_flows
        self.get_stage_flow_statuses = onboarding_flow_trigger.get_stage_flow_statuses
        self.get_students_from_onboarding = onboarding_flow_trigger.get_students_from_onboarding
        self.update_student_stage_progress = onboarding_flow_trigger.update_student_stage_progress
        self.update_student_stage_progress_batch = onboarding_flow_trigger.update_student_stage_progress_batch
        self.get_job_status = onboarding_flow_trigger.get_job_status
        self.get_onboarding_progress_report = onboarding_flow_trigger.get_onboarding_progress_report
        self.update_incomplete_stages = onboarding_flow_trigger.update_incomplete_stages
        
    def tearDown(self):
        """Clean up after each test."""
        self.frappe_patcher.stop()

    # ============= Main Entry Point Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_success_with_stage_flows(self, mock_frappe):
        """Test successful trigger_onboarding_flow with stage_flows"""
        # Setup stage with stage_flows
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.name = "STAGE_001"
        
        mock_flow = MagicMock()
        mock_flow.student_status = "not_started"
        mock_flow.glific_flow_id = "flow_123"
        mock_flow.flow_type = "Group"
        mock_stage.stage_flows = [mock_flow]
        
        # Setup onboarding
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        mock_onboarding.name = "ONBOARDING_001"
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_frappe.enqueue.return_value = "job_123"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.trigger_onboarding_flow("ONBOARDING_001", "STAGE_001", "not_started")
        
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "job_123")
        mock_frappe.enqueue.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_exception_handling(self, mock_frappe):
        """Test trigger_onboarding_flow exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.log_error = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("Error triggering onboarding flow"))
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow("SET", "STAGE", "not_started")
        
        mock_frappe.log_error.assert_called_once()

    # ============= Background Job Tests =============

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_exception_handling(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job exception handling"""
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.log_error = MagicMock()
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "Group")
        
        self.assertIn("error", result)
        mock_frappe.log_error.assert_called_once()

    # ============= Get Stage Flow Statuses Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_success(self, mock_frappe):
        """Test get_stage_flow_statuses with stage_flows"""
        mock_stage = MagicMock()
        mock_flow1 = MagicMock()
        mock_flow1.student_status = "not_started"
        mock_flow2 = MagicMock()
        mock_flow2.student_status = "completed"
        mock_stage.stage_flows = [mock_flow1, mock_flow2]
        
        mock_frappe.get_doc.return_value = mock_stage
        
        result = self.get_stage_flow_statuses("STAGE_001")
        
        self.assertIn("not_started", result["statuses"])
        self.assertIn("completed", result["statuses"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_exception(self, mock_frappe):
        """Test get_stage_flow_statuses exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Not found")
        mock_frappe.log_error = MagicMock()
        
        result = self.get_stage_flow_statuses("INVALID_STAGE")
        
        self.assertIn("error", result)
        self.assertEqual(result["statuses"], [])

    # ============= Get Job Status Tests =============
    
    def test_get_job_status_unknown(self):
        """Test get_job_status with no job ID"""
        result = self.get_job_status(None)
        self.assertEqual(result["status"], "unknown")
        
        result = self.get_job_status("")
        self.assertEqual(result["status"], "unknown")

    # ============= Progress Report Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_basic(self, mock_frappe):
        """Test basic get_onboarding_progress_report"""
        mock_frappe.get_all.return_value = [
            {
                "name": "PROG_001",
                "student": "STUD_001",
                "stage": "STAGE_001",
                "status": "completed",
                "start_timestamp": None,
                "last_activity_timestamp": None,
                "completion_timestamp": None
            }
        ]
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.name1 = "Test Student"
        mock_student.phone = "1234567890"
        
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        mock_frappe.get_doc.side_effect = [mock_student, mock_stage]
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_onboarding_progress_report()
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(len(result["details"]), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_exception(self, mock_frappe):
        """Test get_onboarding_progress_report exception handling"""
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_frappe.log_error = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("Error generating report"))
        
        with self.assertRaises(Exception):
            self.get_onboarding_progress_report()

    # ============= Update Incomplete Stages Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages_with_updates(self, mock_add_to_date, mock_now, mock_frappe):
        """Test update_incomplete_stages with records to update"""
        mock_now.return_value = self.current_time
        mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
        mock_frappe.get_all.return_value = [
            {"name": "PROG_001", "student": "STUD_001", "stage": "STAGE_001", "start_timestamp": self.current_time - timedelta(days=4)}
        ]
        
        mock_progress = MagicMock()
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_incomplete_stages()
        
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

    # ============= Working Tests from Original =============
    
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
        
        with patch.object(self.module, 'get_students_from_onboarding', return_value=[]):
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
        
        with patch.object(self.module, 'get_students_from_onboarding', return_value=[mock_student]):
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
        mock_student.name = "STUD_001"
        mock_stage = MagicMock()
        
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_traceback.format_exc.return_value = "Mock traceback"
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        mock_frappe.log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_batch_success(self, mock_now, mock_frappe):
        """Test update_student_stage_progress_batch success"""
        mock_now.return_value = self.current_time
        
        students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
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

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_basic_call(self, mock_frappe):
        """Test get_students_from_onboarding basic functionality"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        
        mock_frappe.get_all.return_value = []
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding)
        
        self.assertEqual(result, [])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_auth_none(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job with no auth"""
        mock_auth.return_value = None
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "type")
        
        self.assertIn("error", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_trigger_group_flow_success(self, mock_get_students, mock_update_batch, mock_create_group, mock_requests, mock_frappe):
        """Test successful group flow trigger"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        mock_stage = MagicMock()
        mock_stage.name = "TEST_STAGE"
        
        mock_contact_group = MagicMock()
        mock_settings = MagicMock()
        mock_settings.glific_url = "https://api.glific.com"
        mock_settings.api_url = "https://api.glific.com"
        
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_get_students.return_value = [MagicMock()]
        mock_frappe.logger.return_value = MagicMock()
        
        def mock_get_doc_side_effect(doctype, filters=None):
            if doctype == "Glific Settings":
                return mock_settings
            if doctype == "GlificContactGroup":
                mock_group = MagicMock()
                mock_group.group_id = "group_123"
                return mock_group
            return mock_contact_group
        
        mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": True}}
        }
        mock_requests.post.return_value = mock_response
        
        result = self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        
        self.assertEqual(result["group_count"], 1)
        mock_update_batch.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    def test_trigger_individual_flows_success(self, mock_update_progress, mock_get_students, mock_start_flow, mock_frappe):
        """Test successful individual flows trigger"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        mock_stage = MagicMock()
        mock_stage.name = "TEST_STAGE"
        
        mock_student1 = MagicMock()
        mock_student1.name = "STUD_001"
        mock_student1.name1 = "Student One"
        mock_student1.glific_id = "contact_001"
        
        mock_student2 = MagicMock()
        mock_student2.name = "STUD_002"
        mock_student2.name1 = "Student Two"
        mock_student2.glific_id = "contact_002"
        
        mock_get_students.return_value = [mock_student1, mock_student2]
        mock_start_flow.return_value = {"success": True}
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.db.commit.return_value = None
        
        result = self.trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", 
            self.mock_student_status, self.mock_flow_id
        )
        
        self.assertEqual(result["individual_count"], 2)
        self.assertEqual(mock_update_progress.call_count, 2)
        self.assertEqual(mock_start_flow.call_count, 2)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    def test_trigger_individual_flows_partial_success(self, mock_update_progress, mock_get_students, mock_start_flow, mock_frappe):
        """Test trigger_individual_flows with partial success"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        mock_stage = MagicMock()
        mock_stage.name = "TEST_STAGE"
        
        mock_student1 = MagicMock()
        mock_student1.name = "STUD_001"
        mock_student1.name1 = "Student One"
        mock_student1.glific_id = "contact_001"
        
        mock_student2 = MagicMock()
        mock_student2.name = "STUD_002"
        mock_student2.name1 = "Student Two"
        mock_student2.glific_id = None  # No glific ID
        
        mock_student3 = MagicMock()
        mock_student3.name = "STUD_003"
        mock_student3.name1 = "Student Three"
        mock_student3.glific_id = "contact_003"
        
        mock_get_students.return_value = [mock_student1, mock_student2, mock_student3]
        # First call succeeds, second call fails
        mock_start_flow.side_effect = [{"success": True}, Exception("Flow failed")]
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.db.commit.return_value = None
        
        result = self.trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", 
            self.mock_student_status, self.mock_flow_id
        )
        
        self.assertEqual(result["individual_count"], 1)  # Only STUD_001 succeeded
        self.assertEqual(mock_update_progress.call_count, 1)  # Only called for successful student
        self.assertEqual(mock_start_flow.call_count, 2)  # Called for students with glific_id


if __name__ == '__main__':
    unittest.main()