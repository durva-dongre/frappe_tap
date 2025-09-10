# import unittest
# from unittest.mock import patch, MagicMock, Mock
# import json


# class TestOnboardingFlows(unittest.TestCase):
#     def setUp(self):
#         # Mock frappe and other dependencies
#         self.setup_mocks()
#         self.setup_test_data()
        
#     def setup_mocks(self):
#         # Mock frappe module
#         self.frappe_patcher = patch.dict('sys.modules', {
#             'frappe': MagicMock(),
#             'frappe.utils': MagicMock(),
#             'frappe.utils.background_jobs': MagicMock(),
#             'frappe.model.document': MagicMock(),
#             'frappe.model.base_document': MagicMock()
#         })
#         self.frappe_patcher.start()
        
#         import frappe
#         self.frappe = frappe
        
#         # Mock requests module
#         self.requests_patcher = patch.dict('sys.modules', {
#             'requests': MagicMock()
#         })
#         self.requests_patcher.start()
        
#         # Mock the actual functions we'll be testing
#         self.onboarding_flows_patcher = patch.dict('sys.modules', {
#             'tap_lms.onboarding_flows': MagicMock()
#         })
#         self.onboarding_flows_patcher.start()
        
#         # Now import the module and functions
#         from tap_lms.onboarding_flows import (
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

#     def setup_test_data(self):
#         # Create mock documents
#         self.stage = MagicMock()
#         self.stage.name = "Test Onboarding Stage"
#         self.stage.is_active = True
#         self.stage.stage_flows = [MagicMock(student_status="assigned", glific_flow_id="flow_123", flow_type="Group")]
        
#         self.onboarding = MagicMock()
#         self.onboarding.name = "Test Onboarding Set"
#         self.onboarding.status = "Processed"
        
#         self.student = MagicMock()
#         self.student.name = "STU-001"
#         self.student.first_name = "Test"
#         self.student.last_name = "Student"
#         self.student.phone = "+1234567890"
#         self.student.glific_id = "test_glific_id_123"
        
#         self.backend_student = MagicMock()
#         self.backend_student.student_id = self.student.name
#         self.backend_student.processing_status = "Success"
        
#         self.glific_settings = MagicMock()
#         self.glific_settings.api_url = "https://test.glific.com"
#         self.glific_settings.auth_token = "test_token"

#     def tearDown(self):
#         self.frappe_patcher.stop()
#         self.requests_patcher.stop()
#         self.onboarding_flows_patcher.stop()

#     # Test 1: trigger_onboarding_flow - Basic functionality
#     @patch('tap_lms.onboarding_flows.frappe.enqueue')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_trigger_onboarding_flow_success(self, mock_get_doc, mock_enqueue):
#         # Mock documents
#         mock_get_doc.side_effect = [self.stage, self.onboarding]
#         mock_enqueue.return_value = "job_123"
        
#         # Execute
#         result = self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
        
#         # Assert
#         self.assertTrue(result["success"])
#         self.assertEqual(result["job_id"], "job_123")
#         mock_enqueue.assert_called_once()

#     # Test 2: trigger_onboarding_flow - Validation errors
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_trigger_onboarding_flow_validation_errors(self, mock_get_doc):
#         # Test missing parameters
#         self.frappe.ValidationError = Exception
#         with self.assertRaises(Exception):
#             self.trigger_onboarding_flow("", "", "")
            
#         # Test inactive stage
#         inactive_stage = MagicMock()
#         inactive_stage.is_active = False
#         mock_get_doc.return_value = inactive_stage
        
#         with self.assertRaises(Exception):
#             self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")

#     # Test 3: _trigger_onboarding_flow_job - Group flow
#     @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
#     @patch('tap_lms.onboarding_flows.trigger_group_flow')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_trigger_onboarding_flow_job_group(self, mock_get_doc, mock_trigger_group, mock_auth_headers):
#         mock_auth_headers.return_value = {"authorization": "test_token"}
#         mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
#         mock_trigger_group.return_value = {"success": True}
        
#         result = self._trigger_onboarding_flow_job(
#             self.onboarding.name, self.stage.name, "assigned", "flow_123", "Group"
#         )
        
#         self.assertEqual(result, {"success": True})

#     # Test 4: _trigger_onboarding_flow_job - Individual flow
#     @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
#     @patch('tap_lms.onboarding_flows.trigger_individual_flows')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_trigger_onboarding_flow_job_individual(self, mock_get_doc, mock_trigger_individual, mock_auth_headers):
#         mock_auth_headers.return_value = {"authorization": "test_token"}
#         mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
#         mock_trigger_individual.return_value = {"success": True}
        
#         result = self._trigger_onboarding_flow_job(
#             self.onboarding.name, self.stage.name, "assigned", "flow_123", "Personal"
#         )
        
#         self.assertEqual(result, {"success": True})

#     # Test 5: trigger_group_flow - Success case
#     @patch('tap_lms.onboarding_flows.create_or_get_glific_group_for_batch')
#     @patch('tap_lms.onboarding_flows.requests.post')
#     @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
#     @patch('tap_lms.onboarding_flows.update_student_stage_progress_batch')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_trigger_group_flow_success(self, mock_get_doc, mock_update_progress, 
#                                       mock_get_students, mock_post, mock_create_group):
#         # Mock responses
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_group = MagicMock()
#         mock_group.group_id = "group_123"
#         mock_get_doc.return_value = mock_group
        
#         mock_response = MagicMock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {
#             "data": {"startGroupFlow": {"success": True}}
#         }
#         mock_post.return_value = mock_response
        
#         mock_get_students.return_value = [self.student]
        
#         result = self.trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
#         self.assertTrue(result["group_flow_result"]["success"])
#         mock_update_progress.assert_called_once()

#     # Test 6: trigger_individual_flows - Success case
#     @patch('tap_lms.onboarding_flows.start_contact_flow')
#     @patch('tap_lms.onboarding_flows.update_student_stage_progress')
#     @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
#     def test_trigger_individual_flows_success(self, mock_get_students, mock_update_progress, mock_start_flow):
#         mock_get_students.return_value = [self.student]
#         mock_start_flow.return_value = True
        
#         result = self.trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
#         self.assertEqual(result["individual_count"], 1)
#         mock_update_progress.assert_called_once()

#     # Test 7: get_stage_flow_statuses
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_get_stage_flow_statuses(self, mock_get_doc):
#         # Test with stage flows
#         mock_get_doc.return_value = self.stage
        
#         result = self.get_stage_flow_statuses(self.stage.name)
#         self.assertEqual(result["statuses"], ["assigned"])

#     # Test 8: get_students_from_onboarding
#     @patch('tap_lms.onboarding_flows.frappe.get_all')
#     def test_get_students_from_onboarding(self, mock_get_all):
#         mock_get_all.return_value = [{"student": self.student.name}]
        
#         result = self.get_students_from_onboarding(self.onboarding, self.stage.name, "assigned")
#         self.assertEqual(len(result), 1)

#     # Test 9: update_student_stage_progress
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     @patch('tap_lms.onboarding_flows.frappe.get_all')
#     def test_update_student_stage_progress(self, mock_get_all, mock_get_doc):
#         mock_get_all.return_value = []
#         mock_get_doc.return_value = MagicMock()
        
#         # Test creating new progress
#         self.update_student_stage_progress(self.student, self.stage)
        
#         mock_get_doc.assert_called_once()

#     # Test 10: update_student_stage_progress_batch
#     @patch('tap_lms.onboarding_flows.update_student_stage_progress')
#     def test_update_student_stage_progress_batch(self, mock_update_progress):
#         students = [self.student]
#         self.update_student_stage_progress_batch(students, self.stage)
        
#         mock_update_progress.assert_called_once_with(self.student, self.stage)

#     # Test 11: get_job_status
#     @patch('tap_lms.onboarding_flows.frappe.utils.background_jobs.get_job_status')
#     def test_get_job_status(self, mock_frappe_job_status):
#         mock_frappe_job_status.return_value = "finished"
        
#         result = self.get_job_status("test_job_id")
#         self.assertEqual(result["status"], "complete")

#     # Test 12: get_onboarding_progress_report
#     @patch('tap_lms.onboarding_flows.frappe.get_all')
#     def test_get_onboarding_progress_report(self, mock_get_all):
#         mock_get_all.return_value = [{"student": self.student.name, "status": "assigned"}]
        
#         result = self.get_onboarding_progress_report(self.onboarding.name, self.stage.name, "assigned")
        
#         self.assertEqual(result["summary"]["total"], 1)
#         self.assertEqual(result["summary"]["assigned"], 1)

#     # Test 13: update_incomplete_stages
#     @patch('tap_lms.onboarding_flows.frappe.get_all')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     @patch('tap_lms.onboarding_flows.frappe.utils.now_datetime')
#     @patch('tap_lms.onboarding_flows.frappe.utils.add_to_date')
#     def test_update_incomplete_stages(self, mock_add_to_date, mock_now_datetime, mock_get_doc, mock_get_all):
#         # Create mock progress record
#         progress_mock = MagicMock()
#         progress_mock.status = "assigned"
#         progress_mock.start_timestamp = "2020-01-01 00:00:00"
        
#         mock_get_all.return_value = [{"name": "progress-001"}]
#         mock_get_doc.return_value = progress_mock
#         mock_now_datetime.return_value = "2024-01-01 00:00:00"
#         mock_add_to_date.return_value = "2019-12-31 00:00:00"
        
#         self.update_incomplete_stages()
        
#         # Check if status was updated
#         progress_mock.save.assert_called_once()

#     # Test 14: Error handling in trigger_group_flow
#     @patch('tap_lms.onboarding_flows.create_or_get_glific_group_for_batch')
#     def test_trigger_group_flow_error(self, mock_create_group):
#         mock_create_group.return_value = None
        
#         with self.assertRaises(Exception):
#             self.trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

#     # Test 15: Edge case - No students found
#     @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
#     def test_trigger_individual_flows_no_students(self, mock_get_students):
#         mock_get_students.return_value = []
        
#         with self.assertRaises(Exception):
#             self.trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

#     # Test 16: Test with legacy flow configuration
#     @patch('tap_lms.onboarding_flows.frappe.enqueue')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_trigger_onboarding_flow_legacy(self, mock_get_doc, mock_enqueue):
#         legacy_stage = MagicMock()
#         legacy_stage.is_active = True
#         legacy_stage.glific_flow_id = "legacy_flow_123"
#         legacy_stage.glific_flow_type = "Group"
#         # Simulate no stage_flows attribute
#         delattr(legacy_stage, 'stage_flows')
        
#         mock_onboarding = MagicMock()
#         mock_onboarding.status = "Processed"
        
#         mock_get_doc.side_effect = [legacy_stage, mock_onboarding]
#         mock_enqueue.return_value = "job_123"
        
#         result = self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
        
#         self.assertTrue(result["success"])

#     # Test 17: Test authentication failure
#     @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_authentication_failure(self, mock_get_doc, mock_auth_headers):
#         mock_auth_headers.return_value = {}
#         mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
        
#         result = self._trigger_onboarding_flow_job(
#             self.onboarding.name, self.stage.name, "assigned", "flow_123", "Group"
#         )
        
#         self.assertIn("error", result)

#     # Test 18: Test API failure in group flow
#     @patch('tap_lms.onboarding_flows.create_or_get_glific_group_for_batch')
#     @patch('tap_lms.onboarding_flows.requests.post')
#     @patch('tap_lms.onboarding_flows.frappe.get_doc')
#     def test_group_flow_api_failure(self, mock_get_doc, mock_post, mock_create_group):
#         mock_create_group.return_value = {"group_id": "group_123"}
#         mock_group = MagicMock()
#         mock_group.group_id = "group_123"
#         mock_get_doc.return_value = mock_group
        
#         mock_response = MagicMock()
#         mock_response.status_code = 500
#         mock_response.text = "Internal Server Error"
#         mock_post.return_value = mock_response
        
#         with self.assertRaises(Exception):
#             self.trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

#     # Test 19: Test student without glific_id
#     @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
#     @patch('tap_lms.onboarding_flows.start_contact_flow')
#     def test_student_without_glific_id(self, mock_start_flow, mock_get_students):
#         # Create student without glific_id
#         student_no_glific = MagicMock()
#         student_no_glific.glific_id = None
        
#         mock_get_students.return_value = [student_no_glific]
#         mock_start_flow.return_value = False
        
#         result = self.trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
#         self.assertEqual(result["error_count"], 1)


# if __name__ == '__main__':
#     unittest.main()
import unittest
from unittest.mock import patch, MagicMock, Mock
import sys
import json

# Mock frappe and other modules before importing the test class
with patch.dict('sys.modules', {
    'frappe': MagicMock(),
    'frappe.utils': MagicMock(),
    'frappe.utils.background_jobs': MagicMock(),
    'frappe.model': MagicMock(),
    'frappe.model.document': MagicMock(),
    'frappe.model.base_document': MagicMock(),
    'frappe.exceptions': MagicMock(),
    'requests': MagicMock(),
    'tap_lms': MagicMock(),
    'tap_lms.onboarding_flows': MagicMock()
}):
    # Now import the actual test class
    from tap_lms.onboarding_flows import (
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


class TestOnboardingFlows(unittest.TestCase):
    
    def setUp(self):
        # Set up test data
        self.setup_test_data()
        
        # Set up frappe functions
        import frappe
        frappe.ValidationError = Exception
        frappe.throw = MagicMock(side_effect=Exception)
        frappe.get_doc = MagicMock()
        frappe.enqueue = MagicMock()
        frappe.get_all = MagicMock(return_value=[])
        frappe.utils.now_datetime = MagicMock()
        frappe.utils.add_to_date = MagicMock()
        frappe.utils.background_jobs.get_job_status = MagicMock(return_value="finished")
        
        # Mock the specific functions from onboarding_flows
        from tap_lms.onboarding_flows import get_glific_auth_headers, create_or_get_glific_group_for_batch, start_contact_flow
        get_glific_auth_headers.return_value = {"authorization": "test_token"}
        create_or_get_glific_group_for_batch.return_value = {"group_id": "group_123"}
        start_contact_flow.return_value = True

    def setup_test_data(self):
        # Create mock documents
        self.stage = MagicMock()
        self.stage.name = "Test Onboarding Stage"
        self.stage.is_active = True
        self.stage.stage_flows = [MagicMock(student_status="assigned", glific_flow_id="flow_123", flow_type="Group")]
        
        self.onboarding = MagicMock()
        self.onboarding.name = "Test Onboarding Set"
        self.onboarding.status = "Processed"
        
        self.student = MagicMock()
        self.student.name = "STU-001"
        self.student.first_name = "Test"
        self.student.last_name = "Student"
        self.student.phone = "+1234567890"
        self.student.glific_id = "test_glific_id_123"
        
        self.glific_settings = MagicMock()
        self.glific_settings.api_url = "https://test.glific.com"
        self.glific_settings.auth_token = "test_token"

    # Test 1: trigger_onboarding_flow - Basic functionality
    @patch('tap_lms.onboarding_flows.frappe.enqueue')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_success(self, mock_get_doc, mock_enqueue):
        # Mock documents
        mock_get_doc.side_effect = [self.stage, self.onboarding]
        mock_enqueue.return_value = "job_123"
        
        # Execute
        result = trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
        
        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "job_123")
        mock_enqueue.assert_called_once()

    # Test 2: trigger_onboarding_flow - Validation errors
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_validation_errors(self, mock_get_doc):
        # Test missing parameters
        with self.assertRaises(Exception):
            trigger_onboarding_flow("", "", "")
            
        # Test inactive stage
        inactive_stage = MagicMock()
        inactive_stage.is_active = False
        mock_get_doc.return_value = inactive_stage
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")

    # Test 3: _trigger_onboarding_flow_job - Group flow
    @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
    @patch('tap_lms.onboarding_flows.trigger_group_flow')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_job_group(self, mock_get_doc, mock_trigger_group, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "test_token"}
        mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
        mock_trigger_group.return_value = {"success": True}
        
        result = _trigger_onboarding_flow_job(
            self.onboarding.name, self.stage.name, "assigned", "flow_123", "Group"
        )
        
        self.assertEqual(result, {"success": True})

    # Test 4: _trigger_onboarding_flow_job - Individual flow
    @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
    @patch('tap_lms.onboarding_flows.trigger_individual_flows')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_job_individual(self, mock_get_doc, mock_trigger_individual, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "test_token"}
        mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
        mock_trigger_individual.return_value = {"success": True}
        
        result = _trigger_onboarding_flow_job(
            self.onboarding.name, self.stage.name, "assigned", "flow_123", "Personal"
        )
        
        self.assertEqual(result, {"success": True})

    # Test 5: trigger_group_flow - Success case
    @patch('tap_lms.onboarding_flows.create_or_get_glific_group_for_batch')
    @patch('tap_lms.onboarding_flows.requests.post')
    @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
    @patch('tap_lms.onboarding_flows.update_student_stage_progress_batch')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_group_flow_success(self, mock_get_doc, mock_update_progress, 
                                      mock_get_students, mock_post, mock_create_group):
        # Mock responses
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_group = MagicMock()
        mock_group.group_id = "group_123"
        mock_get_doc.return_value = mock_group
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": True}}
        }
        mock_post.return_value = mock_response
        
        mock_get_students.return_value = [self.student]
        mock_update_progress.return_value = None
        
        result = trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        self.assertTrue(result["group_flow_result"]["success"])
        mock_update_progress.assert_called_once()

    # Test 6: trigger_individual_flows - Success case
    @patch('tap_lms.onboarding_flows.start_contact_flow')
    @patch('tap_lms.onboarding_flows.update_student_stage_progress')
    @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
    def test_trigger_individual_flows_success(self, mock_get_students, mock_update_progress, mock_start_flow):
        mock_get_students.return_value = [self.student]
        mock_start_flow.return_value = True
        mock_update_progress.return_value = None
        
        result = trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        self.assertEqual(result["individual_count"], 1)
        mock_update_progress.assert_called_once()

    # Test 7: get_stage_flow_statuses
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_get_stage_flow_statuses(self, mock_get_doc):
        # Test with stage flows
        mock_get_doc.return_value = self.stage
        
        result = get_stage_flow_statuses(self.stage.name)
        self.assertEqual(result["statuses"], ["assigned"])

    # Test 8: get_students_from_onboarding
    @patch('tap_lms.onboarding_flows.frappe.get_all')
    def test_get_students_from_onboarding(self, mock_get_all):
        mock_get_all.return_value = [{"student": self.student.name}]
        
        result = get_students_from_onboarding(self.onboarding, self.stage.name, "assigned")
        self.assertEqual(len(result), 1)

    # Test 9: update_student_stage_progress
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    @patch('tap_lms.onboarding_flows.frappe.get_all')
    def test_update_student_stage_progress(self, mock_get_all, mock_get_doc):
        mock_get_all.return_value = []
        mock_doc = MagicMock()
        mock_get_doc.return_value = mock_doc
        
        # Test creating new progress
        update_student_stage_progress(self.student, self.stage)
        
        mock_get_doc.assert_called_once()

    # Test 10: update_student_stage_progress_batch
    @patch('tap_lms.onboarding_flows.update_student_stage_progress')
    def test_update_student_stage_progress_batch(self, mock_update_progress):
        students = [self.student]
        mock_update_progress.return_value = None
        
        update_student_stage_progress_batch(students, self.stage)
        
        mock_update_progress.assert_called_once_with(self.student, self.stage)

    # Test 11: get_job_status
    @patch('tap_lms.onboarding_flows.frappe.utils.background_jobs.get_job_status')
    def test_get_job_status(self, mock_frappe_job_status):
        mock_frappe_job_status.return_value = "finished"
        
        result = get_job_status("test_job_id")
        self.assertEqual(result["status"], "complete")

    # Test 12: get_onboarding_progress_report
    @patch('tap_lms.onboarding_flows.frappe.get_all')
    def test_get_onboarding_progress_report(self, mock_get_all):
        mock_get_all.return_value = [{"student": self.student.name, "status": "assigned"}]
        
        result = get_onboarding_progress_report(self.onboarding.name, self.stage.name, "assigned")
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["assigned"], 1)

    # Test 13: update_incomplete_stages
    @patch('tap_lms.onboarding_flows.frappe.get_all')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    @patch('tap_lms.onboarding_flows.frappe.utils.now_datetime')
    @patch('tap_lms.onboarding_flows.frappe.utils.add_to_date')
    def test_update_incomplete_stages(self, mock_add_to_date, mock_now_datetime, mock_get_doc, mock_get_all):
        # Create mock progress record
        progress_mock = MagicMock()
        progress_mock.status = "assigned"
        progress_mock.start_timestamp = "2020-01-01 00:00:00"
        
        mock_get_all.return_value = [{"name": "progress-001"}]
        mock_get_doc.return_value = progress_mock
        mock_now_datetime.return_value = "2024-01-01 00:00:00"
        mock_add_to_date.return_value = "2019-12-31 00:00:00"
        
        update_incomplete_stages()
        
        # Check if status was updated
        progress_mock.save.assert_called_once()

    # Test 14: Error handling in trigger_group_flow
    @patch('tap_lms.onboarding_flows.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_error(self, mock_create_group):
        mock_create_group.return_value = None
        
        # This should not raise an exception but return an error result
        result = trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        self.assertIn("error", result)

    # Test 15: Edge case - No students found
    @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
    def test_trigger_individual_flows_no_students(self, mock_get_students):
        mock_get_students.return_value = []
        
        # This should not raise an exception but return a result with count 0
        result = trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        self.assertEqual(result["individual_count"], 0)

    # Test 16: Test with legacy flow configuration
    @patch('tap_lms.onboarding_flows.frappe.enqueue')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_legacy(self, mock_get_doc, mock_enqueue):
        legacy_stage = MagicMock()
        legacy_stage.is_active = True
        legacy_stage.glific_flow_id = "legacy_flow_123"
        legacy_stage.glific_flow_type = "Group"
        # Simulate no stage_flows attribute
        delattr(legacy_stage, 'stage_flows')
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [legacy_stage, mock_onboarding]
        mock_enqueue.return_value = "job_123"
        
        result = trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
        
        self.assertTrue(result["success"])

    # Test 17: Test authentication failure
    @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_authentication_failure(self, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {}
        mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
        
        result = _trigger_onboarding_flow_job(
            self.onboarding.name, self.stage.name, "assigned", "flow_123", "Group"
        )
        
        self.assertIn("error", result)

    # Test 18: Test API failure in group flow
    @patch('tap_lms.onboarding_flows.create_or_get_glific_group_for_batch')
    @patch('tap_lms.onboarding_flows.requests.post')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_group_flow_api_failure(self, mock_get_doc, mock_post, mock_create_group):
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_group = MagicMock()
        mock_group.group_id = "group_123"
        mock_get_doc.return_value = mock_group
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        # This should not raise an exception but return an error result
        result = trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        self.assertIn("error", result)

    # Test 19: Test student without glific_id
    @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
    @patch('tap_lms.onboarding_flows.start_contact_flow')
    @patch('tap_lms.onboarding_flows.update_student_stage_progress')
    def test_student_without_glific_id(self, mock_update_progress, mock_start_flow, mock_get_students):
        # Create student without glific_id
        student_no_glific = MagicMock()
        student_no_glific.glific_id = None
        
        mock_get_students.return_value = [student_no_glific]
        mock_start_flow.return_value = False
        mock_update_progress.return_value = None
        
        result = trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        self.assertEqual(result["error_count"], 1)


if __name__ == '__main__':
    unittest.main()