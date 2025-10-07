
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
#             'frappe.utils.background_jobs': MagicMock(),
#             'tap_lms.glific_integration': MagicMock()
#         })
#         self.frappe_patcher.start()
        
#         # Import after patching
#         from tap_lms.tap_lms.page.onboarding_flow_trigger import onboarding_flow_trigger
        
#         # Store references to the actual functions
#         self.module = onboarding_flow_trigger
#         self.trigger_onboarding_flow = onboarding_flow_trigger.trigger_onboarding_flow
#         self._trigger_onboarding_flow_job = onboarding_flow_trigger._trigger_onboarding_flow_job
#         self.trigger_group_flow = onboarding_flow_trigger.trigger_group_flow
#         self.trigger_individual_flows = onboarding_flow_trigger.trigger_individual_flows
#         self.get_stage_flow_statuses = onboarding_flow_trigger.get_stage_flow_statuses
#         self.get_students_from_onboarding = onboarding_flow_trigger.get_students_from_onboarding
#         self.update_student_stage_progress = onboarding_flow_trigger.update_student_stage_progress
#         self.update_student_stage_progress_batch = onboarding_flow_trigger.update_student_stage_progress_batch
#         self.get_job_status = onboarding_flow_trigger.get_job_status
#         self.get_onboarding_progress_report = onboarding_flow_trigger.get_onboarding_progress_report
#         self.update_incomplete_stages = onboarding_flow_trigger.update_incomplete_stages
        
#     def tearDown(self):
#         """Clean up after each test."""
#         self.frappe_patcher.stop()

#     # ============= EXISTING WORKING TESTS =============
    
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
        
#         with patch.object(self.module, 'get_students_from_onboarding', return_value=[]):
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
        
#         with patch.object(self.module, 'get_students_from_onboarding', return_value=[mock_student]):
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
#         mock_student.name = "STUD_001"
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
#         mock_stage.name = "STAGE_001"
        
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
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     def test_trigger_onboarding_flow_job_exception_handling(self, mock_auth, mock_frappe):
#         """Test _trigger_onboarding_flow_job exception handling"""
#         mock_auth.return_value = {"authorization": "Bearer token"}
#         mock_frappe.get_doc.side_effect = Exception("Database error")
#         mock_frappe.log_error = MagicMock()
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "Group")
        
#         self.assertIn("error", result)
#         mock_frappe.log_error.assert_called_once()

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
#         mock_settings.api_url = "https://api.glific.com"
        
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_get_students.return_value = [MagicMock()]
#         mock_frappe.logger.return_value = MagicMock()
        
#         def mock_get_doc_side_effect(doctype, filters=None):
#             if doctype == "Glific Settings":
#                 return mock_settings
#             if doctype == "GlificContactGroup":
#                 mock_group = MagicMock()
#                 mock_group.group_id = "group_123"
#                 return mock_group
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
#         mock_onboarding.name = "TEST_ONBOARDING"
#         mock_stage = MagicMock()
#         mock_stage.name = "TEST_STAGE"
        
#         mock_student1 = MagicMock()
#         mock_student1.name = "STUD_001"
#         mock_student1.name1 = "Student One"
#         mock_student1.glific_id = "contact_001"
        
#         mock_student2 = MagicMock()
#         mock_student2.name = "STUD_002"
#         mock_student2.name1 = "Student Two"
#         mock_student2.glific_id = "contact_002"
        
#         mock_get_students.return_value = [mock_student1, mock_student2]
#         mock_start_flow.return_value = True
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.db.commit.return_value = None
        
#         result = self.trigger_individual_flows(
#             mock_onboarding, mock_stage, "Bearer token", 
#             self.mock_student_status, self.mock_flow_id
#         )
        
#         self.assertEqual(result["individual_count"], 2)
#         self.assertEqual(mock_update_progress.call_count, 2)
#         self.assertEqual(mock_start_flow.call_count, 2)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     def test_trigger_individual_flows_partial_success(self, mock_update_progress, mock_get_students, mock_start_flow, mock_frappe):
#         """Test trigger_individual_flows with partial success"""
#         mock_onboarding = MagicMock()
#         mock_onboarding.name = "TEST_ONBOARDING"
#         mock_stage = MagicMock()
#         mock_stage.name = "TEST_STAGE"
        
#         mock_student1 = MagicMock()
#         mock_student1.name = "STUD_001"
#         mock_student1.name1 = "Student One"
#         mock_student1.glific_id = "contact_001"
        
#         mock_student2 = MagicMock()
#         mock_student2.name = "STUD_002"
#         mock_student2.name1 = "Student Two"
#         mock_student2.glific_id = None  # No glific ID
        
#         mock_student3 = MagicMock()
#         mock_student3.name = "STUD_003"
#         mock_student3.name1 = "Student Three"
#         mock_student3.glific_id = "contact_003"
        
#         mock_get_students.return_value = [mock_student1, mock_student2, mock_student3]
#         # First call succeeds, second call fails
#         mock_start_flow.side_effect = [True, Exception("Flow failed")]
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.db.commit.return_value = None
        
#         result = self.trigger_individual_flows(
#             mock_onboarding, mock_stage, "Bearer token", 
#             self.mock_student_status, self.mock_flow_id
#         )
        
#         self.assertEqual(result["individual_count"], 1)  # Only STUD_001 succeeded
#         self.assertEqual(mock_update_progress.call_count, 1)  # Only called for successful student
#         self.assertEqual(mock_start_flow.call_count, 2)  # Called for students with glific_id

#     # ============= ADDITIONAL TESTS TO INCREASE COVERAGE =============
    
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow')
#     def test_trigger_onboarding_flow_job_group_flow(self, mock_trigger_group, mock_auth, mock_frappe):
#         """Test _trigger_onboarding_flow_job triggering group flow"""
#         mock_auth.return_value = {"authorization": "Bearer token"}
#         mock_stage = MagicMock()
#         mock_onboarding = MagicMock()
#         mock_settings = MagicMock()
        
#         mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding, mock_settings]
#         mock_trigger_group.return_value = {"success": True, "group_count": 5}
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "Group")
        
#         self.assertEqual(result, {"success": True, "group_count": 5})
#         mock_trigger_group.assert_called_once_with(mock_onboarding, mock_stage, "Bearer token", "status", "flow")
    
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_individual_flows')
#     def test_trigger_onboarding_flow_job_individual_flow(self, mock_trigger_individual, mock_auth, mock_frappe):
#         """Test _trigger_onboarding_flow_job triggering individual flows"""
#         mock_auth.return_value = {"authorization": "Bearer token"}
#         mock_stage = MagicMock()
#         mock_onboarding = MagicMock()
#         mock_settings = MagicMock()
        
#         mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding, mock_settings]
#         mock_trigger_individual.return_value = {"success": True, "individual_count": 10}
#         mock_frappe.logger.return_value = MagicMock()
        
#         result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "Individual")
        
#         self.assertEqual(result, {"success": True, "individual_count": 10})
#         mock_trigger_individual.assert_called_once_with(mock_onboarding, mock_stage, "Bearer token", "status", "flow")
    
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
#     def test_trigger_group_flow_exception_handling(self, mock_traceback, mock_frappe):
#         """Test trigger_group_flow general exception handling"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
        
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.log_error = MagicMock()
#         mock_frappe.throw = Mock(side_effect=Exception("General error"))
#         mock_traceback.format_exc.return_value = "Mock traceback"
        
#         with self.assertRaises(Exception):
#             self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", "status", "flow")
        
#         mock_frappe.log_error.assert_called_once()
    
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
#     def test_trigger_individual_flows_exception_handling(self, mock_traceback, mock_frappe):
#         """Test trigger_individual_flows general exception handling"""
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
        
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.log_error = MagicMock()
#         mock_frappe.throw = Mock(side_effect=Exception("General error"))
#         mock_traceback.format_exc.return_value = "Mock traceback"
        
#         with self.assertRaises(Exception):
#             self.trigger_individual_flows(mock_onboarding, mock_stage, "Bearer token", "status", "flow")
        
#         mock_frappe.log_error.assert_called_once()
    
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     def test_trigger_individual_flows_all_students_have_glific_id(self, mock_start_flow, mock_frappe):
#         """Test trigger_individual_flows where all students have glific_id and succeed"""
#         mock_onboarding = MagicMock()
#         mock_onboarding.name = "TEST_ONBOARDING"
#         mock_stage = MagicMock()
#         mock_stage.name = "TEST_STAGE"
        
#         students = []
#         for i in range(5):
#             student = MagicMock()
#             student.name = f"STUD_{i:03d}"
#             student.name1 = f"Student {i}"
#             student.glific_id = f"contact_{i:03d}"
#             students.append(student)
        
#         mock_frappe.logger.return_value = MagicMock()
#         mock_frappe.db.commit.return_value = None
#         mock_start_flow.return_value = True
        
#         with patch.object(self.module, 'get_students_from_onboarding', return_value=students):
#             with patch.object(self.module, 'update_student_stage_progress'):
#                 result = self.trigger_individual_flows(
#                     mock_onboarding, mock_stage, "Bearer token", 
#                     self.mock_student_status, self.mock_flow_id
#                 )
                
#                 self.assertEqual(result["individual_count"], 5)
#                 self.assertEqual(result["error_count"], 0)
#                 self.assertEqual(mock_start_flow.call_count, 5)

# if __name__ == '__main__':
#     unittest.main()

import unittest
from unittest.mock import Mock, patch, MagicMock, call, PropertyMock
from datetime import datetime, timedelta
import sys
import os
import json

# Mock frappe and its submodules before importing the module to test
sys.modules['frappe'] = MagicMock()
sys.modules['frappe.utils'] = MagicMock()
sys.modules['frappe.utils.background_jobs'] = MagicMock()
sys.modules['tap_lms'] = MagicMock()
sys.modules['tap_lms.glific_integration'] = MagicMock()

# Now import the module to test
from tap_lms.tap_lms.page.onboarding_flow_trigger import onboarding_flow_trigger

class TestOnboardingFlowFunctions(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "job_123"
        self.current_time = datetime(2025, 9, 11, 16, 3)
        
    # ============= TEST trigger_onboarding_flow =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_success_with_child_table(self, mock_frappe, mock_traceback):
        """Test trigger_onboarding_flow with new child table structure"""
        # Setup mocks
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.name = "STAGE_001"
        mock_flow = MagicMock()
        mock_flow.student_status = "not_started"
        mock_flow.glific_flow_id = "flow_123"
        mock_flow.flow_type = "Group"
        mock_stage.stage_flows = [mock_flow]
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_frappe.enqueue.return_value = "job_123"
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.whitelist = MagicMock()
        
        # Decorate the function
        trigger_onboarding_flow_decorated = mock_frappe.whitelist(onboarding_flow_trigger.trigger_onboarding_flow)
        
        # Call the function
        result = onboarding_flow_trigger.trigger_onboarding_flow("ONBOARD_001", "STAGE_001", "not_started")
        
        # Assertions
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "job_123")
        mock_frappe.enqueue.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_validation_errors(self, mock_frappe, mock_traceback):
        """Test trigger_onboarding_flow with validation errors"""
        mock_frappe.throw = Mock(side_effect=Exception("Validation error"))
        mock_frappe._ = lambda x: x
        
        # Test missing onboarding_set
        with self.assertRaises(Exception):
            onboarding_flow_trigger.trigger_onboarding_flow(None, "STAGE_001", "not_started")
        
        # Test missing onboarding_stage
        with self.assertRaises(Exception):
            onboarding_flow_trigger.trigger_onboarding_flow("ONBOARD_001", None, "not_started")
        
        # Test missing student_status
        with self.assertRaises(Exception):
            onboarding_flow_trigger.trigger_onboarding_flow("ONBOARD_001", "STAGE_001", None)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_inactive_stage(self, mock_frappe, mock_traceback):
        """Test trigger_onboarding_flow with inactive stage"""
        mock_stage = MagicMock()
        mock_stage.is_active = False
        
        mock_frappe.get_doc.return_value = mock_stage
        mock_frappe.throw = Mock(side_effect=Exception("Stage not active"))
        mock_frappe._ = lambda x: x
        
        with self.assertRaises(Exception):
            onboarding_flow_trigger.trigger_onboarding_flow("ONBOARD_001", "STAGE_001", "not_started")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_legacy_structure(self, mock_frappe, mock_traceback):
        """Test trigger_onboarding_flow with legacy structure"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.name = "STAGE_001"
        mock_stage.stage_flows = []
        mock_stage.glific_flow_id = "legacy_flow_123"
        mock_stage.glific_flow_type = "Individual"
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_frappe.enqueue.return_value = "job_456"
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.logger.return_value.warning = MagicMock()
        
        result = onboarding_flow_trigger.trigger_onboarding_flow("ONBOARD_001", "STAGE_001", "not_started")
        
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "job_456")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_exception_handling(self, mock_frappe, mock_traceback):
        """Test trigger_onboarding_flow exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.log_error = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("Error"))
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe._ = lambda x: x
        mock_traceback.format_exc.return_value = "Mock traceback"
        
        with self.assertRaises(Exception):
            onboarding_flow_trigger.trigger_onboarding_flow("ONBOARD_001", "STAGE_001", "not_started")
        
        mock_frappe.log_error.assert_called_once()
    
    # ============= TEST _trigger_onboarding_flow_job =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_job_group_flow(self, mock_frappe, mock_auth, mock_trigger_group, mock_traceback):
        """Test _trigger_onboarding_flow_job with group flow"""
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_settings = MagicMock()
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding, mock_settings]
        mock_frappe.logger.return_value.info = MagicMock()
        mock_trigger_group.return_value = {"success": True}
        
        result = onboarding_flow_trigger._trigger_onboarding_flow_job(
            "set", "stage", "status", "flow", "Group"
        )
        
        self.assertEqual(result["success"], True)
        mock_trigger_group.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_individual_flows')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_job_individual_flow(self, mock_frappe, mock_auth, mock_trigger_individual, mock_traceback):
        """Test _trigger_onboarding_flow_job with individual flow"""
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_settings = MagicMock()
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding, mock_settings]
        mock_frappe.logger.return_value.info = MagicMock()
        mock_trigger_individual.return_value = {"success": True}
        
        result = onboarding_flow_trigger._trigger_onboarding_flow_job(
            "set", "stage", "status", "flow", "Individual"
        )
        
        self.assertEqual(result["success"], True)
        mock_trigger_individual.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_job_no_auth(self, mock_frappe, mock_auth, mock_traceback):
        """Test _trigger_onboarding_flow_job with no auth"""
        mock_auth.return_value = None
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.logger.return_value.error = MagicMock()
        
        result = onboarding_flow_trigger._trigger_onboarding_flow_job(
            "set", "stage", "status", "flow", "Group"
        )
        
        self.assertIn("error", result)
    
    # ============= TEST trigger_group_flow =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.json')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_group_flow_success(self, mock_frappe, mock_json, mock_create_group, mock_requests, 
                                       mock_get_students, mock_update_batch, mock_traceback):
        """Test successful group flow trigger"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        mock_stage = MagicMock()
        mock_stage.name = "TEST_STAGE"
        
        mock_create_group.return_value = {"group_id": "group_123"}
        
        mock_contact_group = MagicMock()
        mock_contact_group.group_id = "group_123"
        
        mock_settings = MagicMock()
        mock_settings.api_url = "https://api.glific.com"
        
        mock_frappe.get_doc.side_effect = [mock_contact_group, mock_settings]
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.logger.return_value.debug = MagicMock()
        mock_frappe._ = lambda x: x
        
        mock_json.dumps.return_value = "{}"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": True}}
        }
        mock_requests.post.return_value = mock_response
        
        mock_students = [MagicMock(), MagicMock()]
        mock_get_students.return_value = mock_students
        
        result = onboarding_flow_trigger.trigger_group_flow(
            mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
        )
        
        self.assertEqual(result["group_count"], 2)
        mock_update_batch.assert_called_once_with(mock_students, mock_stage)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_group_flow_no_flow_id(self, mock_frappe, mock_traceback):
        """Test trigger_group_flow with no flow ID"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("No flow ID"))
        mock_frappe._ = lambda x: x
        
        with self.assertRaises(Exception):
            onboarding_flow_trigger.trigger_group_flow(
                mock_onboarding, mock_stage, "Bearer token", "not_started", None
            )
    
    # ============= TEST trigger_individual_flows =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.time')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_individual_flows_success(self, mock_frappe, mock_get_students, mock_start_flow, 
                                             mock_update, mock_traceback, mock_time):
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
        mock_start_flow.return_value = True
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.logger.return_value.debug = MagicMock()
        mock_frappe.db.commit = MagicMock()
        mock_time.sleep = MagicMock()
        
        result = onboarding_flow_trigger.trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
        )
        
        self.assertEqual(result["individual_count"], 2)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(mock_update.call_count, 2)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_individual_flows_no_students(self, mock_frappe, mock_get_students, mock_traceback):
        """Test trigger_individual_flows with no students"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        
        mock_get_students.return_value = []
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.logger.return_value.warning = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("No students"))
        mock_frappe._ = lambda x: x
        
        with self.assertRaises(Exception):
            onboarding_flow_trigger.trigger_individual_flows(
                mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
            )
    
    # ============= TEST get_stage_flow_statuses =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_with_flows(self, mock_frappe):
        """Test get_stage_flow_statuses with configured flows"""
        mock_stage = MagicMock()
        mock_flow1 = MagicMock()
        mock_flow1.student_status = "not_started"
        mock_flow2 = MagicMock()
        mock_flow2.student_status = "completed"
        mock_stage.stage_flows = [mock_flow1, mock_flow2]
        
        mock_frappe.get_doc.return_value = mock_stage
        mock_frappe.whitelist = MagicMock()
        
        result = onboarding_flow_trigger.get_stage_flow_statuses("STAGE_001")
        
        self.assertIn("statuses", result)
        self.assertIn("not_started", result["statuses"])
        self.assertIn("completed", result["statuses"])
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_exception(self, mock_frappe):
        """Test get_stage_flow_statuses exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.log_error = MagicMock()
        
        result = onboarding_flow_trigger.get_stage_flow_statuses("STAGE_001")
        
        self.assertIn("error", result)
        self.assertEqual(result["statuses"], [])
    
    # ============= TEST get_students_from_onboarding =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_with_filters(self, mock_frappe, mock_traceback):
        """Test get_students_from_onboarding with stage and status filters"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        
        mock_frappe.get_all.side_effect = [
            [{"student_id": "STUD_001"}],  # Backend students
            [{"name": "PROGRESS_001"}]  # Stage progress
        ]
        mock_frappe.get_doc.return_value = mock_student
        mock_frappe.logger.return_value.debug = MagicMock()
        
        result = onboarding_flow_trigger.get_students_from_onboarding(
            mock_onboarding, "STAGE_001", "completed"
        )
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "STUD_001")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_not_started(self, mock_frappe, mock_traceback):
        """Test get_students_from_onboarding with not_started status"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        
        mock_frappe.get_all.side_effect = [
            [{"student_id": "STUD_001"}],  # Backend students
            [],  # No stage progress for initial check
            [{"student_id": "STUD_001"}],  # Backend students for not_started check
            []  # No stage progress (confirms not_started)
        ]
        mock_frappe.get_doc.side_effect = [mock_student, mock_student]
        mock_frappe.logger.return_value.debug = MagicMock()
        mock_frappe.logger.return_value.error = MagicMock()
        
        result = onboarding_flow_trigger.get_students_from_onboarding(
            mock_onboarding, "STAGE_001", "not_started"
        )
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "STUD_001")
    
    # ============= TEST update_student_stage_progress =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_update_student_stage_progress_new_record(self, mock_frappe, mock_now, mock_traceback):
        """Test update_student_stage_progress creating new record"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        mock_frappe.get_all.return_value = []  # No existing record
        mock_progress = MagicMock()
        mock_frappe.new_doc.return_value = mock_progress
        mock_frappe.logger.return_value.debug = MagicMock()
        mock_frappe.db.commit = MagicMock()
        
        onboarding_flow_trigger.update_student_stage_progress(mock_student, mock_stage)
        
        mock_progress.insert.assert_called_once()
        self.assertEqual(mock_progress.status, "assigned")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_update_student_stage_progress_update_existing(self, mock_frappe, mock_now, mock_traceback):
        """Test update_student_stage_progress updating existing record"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_stage = MagicMock()
        
        mock_frappe.get_all.return_value = [{"name": "PROGRESS_001"}]
        mock_progress = MagicMock()
        mock_progress.status = "incomplete"
        mock_progress.start_timestamp = None
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value.debug = MagicMock()
        mock_frappe.db.commit = MagicMock()
        
        onboarding_flow_trigger.update_student_stage_progress(mock_student, mock_stage)
        
        self.assertEqual(mock_progress.status, "assigned")
        self.assertEqual(mock_progress.start_timestamp, self.current_time)
        mock_progress.save.assert_called_once()
    
    # ============= TEST update_student_stage_progress_batch =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_update_student_stage_progress_batch(self, mock_frappe, mock_now):
        """Test update_student_stage_progress_batch"""
        mock_now.return_value = self.current_time
        
        students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        mock_frappe.get_all.return_value = []  # No existing records
        mock_progress = MagicMock()
        mock_frappe.new_doc.return_value = mock_progress
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.logger.return_value.error = MagicMock()
        mock_frappe.db.commit = MagicMock()
        
        onboarding_flow_trigger.update_student_stage_progress_batch(students, mock_stage)
        
        self.assertEqual(mock_progress.insert.call_count, 2)
        mock_frappe.db.commit.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_update_student_stage_progress_batch_empty(self, mock_frappe):
        """Test update_student_stage_progress_batch with empty list"""
        mock_frappe.logger.return_value.warning = MagicMock()
        
        onboarding_flow_trigger.update_student_stage_progress_batch([], MagicMock())
        
        mock_frappe.logger.return_value.warning.assert_called_once()
    
    # ============= TEST get_job_status =============
    
    def test_get_job_status_no_job_id(self):
        """Test get_job_status with no job ID"""
        result = onboarding_flow_trigger.get_job_status(None)
        self.assertEqual(result, {"status": "unknown"})
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_failed(self, mock_get_status, mock_frappe, mock_traceback):
        """Test get_job_status for failed job"""
        mock_get_status.return_value = "failed"
        mock_frappe.logger.return_value.debug = MagicMock()
        mock_frappe.whitelist = MagicMock()
        
        result = onboarding_flow_trigger.get_job_status("job_123")
        self.assertEqual(result, {"status": "failed"})
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_running(self, mock_get_status, mock_frappe, mock_traceback):
        """Test get_job_status for running job"""
        mock_get_status.return_value = "started"
        mock_frappe.logger.return_value.debug = MagicMock()
        
        result = onboarding_flow_trigger.get_job_status("job_123")
        self.assertEqual(result, {"status": "started"})
    
    # ============= TEST get_onboarding_progress_report =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_basic(self, mock_frappe, mock_traceback):
        """Test get_onboarding_progress_report basic functionality"""
        progress_records = [
            {
                "name": "PROG_001",
                "student": "STUD_001",
                "stage": "STAGE_001",
                "status": "completed",
                "start_timestamp": self.current_time,
                "last_activity_timestamp": self.current_time,
                "completion_timestamp": self.current_time
            }
        ]
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.name1 = "Student One"
        mock_student.phone = "1234567890"
        
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        mock_frappe.get_all.return_value = progress_records
        mock_frappe.get_doc.side_effect = [mock_student, mock_stage]
        mock_frappe.logger.return_value.debug = MagicMock()
        mock_frappe.whitelist = MagicMock()
        
        result = onboarding_flow_trigger.get_onboarding_progress_report()
        
        self.assertIn("summary", result)
        self.assertIn("details", result)
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["completed"], 1)
    
    # ============= TEST update_incomplete_stages =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_update_incomplete_stages_with_records(self, mock_frappe, mock_now, mock_add_to_date, mock_traceback):
        """Test update_incomplete_stages with records to update"""
        current_time = self.current_time
        three_days_ago = current_time - timedelta(days=3)
        
        mock_now.return_value = current_time
        mock_add_to_date.return_value = three_days_ago
        
        assigned_records = [
            {"name": "PROG_001", "student": "STUD_001", "stage": "STAGE_001", 
             "start_timestamp": three_days_ago - timedelta(days=1)}
        ]
        
        mock_frappe.get_all.return_value = assigned_records
        mock_progress = MagicMock()
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value.info = MagicMock()
        mock_frappe.db.commit = MagicMock()
        
        onboarding_flow_trigger.update_incomplete_stages()
        
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

if __name__ == '__main__':
    unittest.main()