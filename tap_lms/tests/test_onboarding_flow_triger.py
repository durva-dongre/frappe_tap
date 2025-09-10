import frappe
import unittest
from unittest.mock import patch, MagicMock, Mock
import json
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
        # Create test documents
        self.setup_test_data()
        
    def setup_test_data(self):
        # Create test OnboardingStage
        self.stage = frappe.get_doc({
            "doctype": "OnboardingStage",
            "stage_name": "Test Onboarding Stage",
            "is_active": 1
        }).insert()
        
        # Create test Backend Student Onboarding
        self.onboarding = frappe.get_doc({
            "doctype": "Backend Student Onboarding",
            "onboarding_name": "Test Onboarding Set",
            "status": "Processed"
        }).insert()
        
        # Create test Student
        self.student = frappe.get_doc({
            "doctype": "Student",
            "first_name": "Test",
            "last_name": "Student",
            "phone": "+1234567890",
            "glific_id": "test_glific_id_123"
        }).insert()
        
        # Create Backend Students link
        self.backend_student = frappe.get_doc({
            "doctype": "Backend Students",
            "parent": self.onboarding.name,
            "parenttype": "Backend Student Onboarding",
            "parentfield": "backend_students",
            "student_id": self.student.name,
            "processing_status": "Success"
        }).insert()
        
        # Create Glific Settings if not exists
        if not frappe.db.exists("Glific Settings", "Glific Settings"):
            self.glific_settings = frappe.get_doc({
                "doctype": "Glific Settings",
                "api_url": "https://test.glific.com",
                "auth_token": "test_token"
            }).insert()
        else:
            self.glific_settings = frappe.get_doc("Glific Settings", "Glific Settings")

    def tearDown(self):
        frappe.db.rollback()

    # Test 1: trigger_onboarding_flow - Basic functionality
    @patch('tap_lms.onboarding_flows.frappe.enqueue')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_success(self, mock_get_doc, mock_enqueue):
        # Mock documents
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.stage_flows = [MagicMock(student_status="assigned", glific_flow_id="flow_123", flow_type="Group")]
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
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
        with self.assertRaises(frappe.ValidationError):
            trigger_onboarding_flow("", "", "")
            
        # Test inactive stage
        mock_stage = MagicMock()
        mock_stage.is_active = False
        mock_get_doc.return_value = mock_stage
        
        with self.assertRaises(frappe.ValidationError):
            trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")

    # Test 3: _trigger_onboarding_flow_job - Group flow
    @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
    @patch('tap_lms.onboarding_flows.trigger_group_flow')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_job_group(self, mock_get_doc, mock_trigger_group, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "test_token"}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, self.glific_settings]
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
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, self.glific_settings]
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
        
        result = trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        self.assertEqual(result["individual_count"], 1)
        mock_update_progress.assert_called_once()

    # Test 7: get_stage_flow_statuses
    def test_get_stage_flow_statuses(self):
        # Test with stage flows
        self.stage.append("stage_flows", {
            "student_status": "assigned",
            "glific_flow_id": "flow_123",
            "flow_type": "Group"
        })
        self.stage.save()
        
        result = get_stage_flow_statuses(self.stage.name)
        self.assertEqual(result["statuses"], ["assigned"])

    # Test 8: get_students_from_onboarding
    def test_get_students_from_onboarding(self):
        result = get_students_from_onboarding(self.onboarding, self.stage.name, "assigned")
        self.assertEqual(len(result), 0)  # No stage progress records yet
        
        # Create stage progress record
        progress = frappe.get_doc({
            "doctype": "StudentStageProgress",
            "student": self.student.name,
            "stage_type": "OnboardingStage",
            "stage": self.stage.name,
            "status": "assigned"
        }).insert()
        
        result = get_students_from_onboarding(self.onboarding, self.stage.name, "assigned")
        self.assertEqual(len(result), 1)

    # Test 9: update_student_stage_progress
    def test_update_student_stage_progress(self):
        # Test creating new progress
        update_student_stage_progress(self.student, self.stage)
        
        progress = frappe.get_all("StudentStageProgress", filters={"student": self.student.name})
        self.assertEqual(len(progress), 1)
        
        # Test updating existing progress
        update_student_stage_progress(self.student, self.stage)
        progress = frappe.get_all("StudentStageProgress", filters={"student": self.student.name})
        self.assertEqual(len(progress), 1)  # Should not create duplicate

    # Test 10: update_student_stage_progress_batch
    def test_update_student_stage_progress_batch(self):
        students = [self.student]
        update_student_stage_progress_batch(students, self.stage)
        
        progress = frappe.get_all("StudentStageProgress", filters={"student": self.student.name})
        self.assertEqual(len(progress), 1)

    # Test 11: get_job_status
    @patch('tap_lms.onboarding_flows.frappe.utils.background_jobs.get_job_status')
    def test_get_job_status(self, mock_frappe_job_status):
        mock_frappe_job_status.return_value = "finished"
        
        result = get_job_status("test_job_id")
        self.assertEqual(result["status"], "complete")

    # Test 12: get_onboarding_progress_report
    def test_get_onboarding_progress_report(self):
        # Create stage progress
        progress = frappe.get_doc({
            "doctype": "StudentStageProgress",
            "student": self.student.name,
            "stage_type": "OnboardingStage",
            "stage": self.stage.name,
            "status": "assigned"
        }).insert()
        
        result = get_onboarding_progress_report(self.onboarding.name, self.stage.name, "assigned")
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["assigned"], 1)

    # Test 13: update_incomplete_stages
    @patch('tap_lms.onboarding_flows.now_datetime')
    @patch('tap_lms.onboarding_flows.add_to_date')
    def test_update_incomplete_stages(self, mock_add_to_date, mock_now_datetime):
        # Create old assigned record
        old_date = frappe.utils.now_datetime().replace(year=2020)
        progress = frappe.get_doc({
            "doctype": "StudentStageProgress",
            "student": self.student.name,
            "stage_type": "OnboardingStage",
            "stage": self.stage.name,
            "status": "assigned",
            "start_timestamp": old_date
        }).insert()
        
        mock_now_datetime.return_value = frappe.utils.now_datetime()
        mock_add_to_date.return_value = old_date.replace(day=old_date.day - 1)
        
        update_incomplete_stages()
        
        # Check if status was updated
        updated = frappe.get_doc("StudentStageProgress", progress.name)
        self.assertEqual(updated.status, "incomplete")

    # Test 14: Error handling in trigger_group_flow
    @patch('tap_lms.onboarding_flows.create_or_get_glific_group_for_batch')
    @patch('tap_lms.onboarding_flows.requests.post')
    def test_trigger_group_flow_error(self, mock_post, mock_create_group):
        mock_create_group.return_value = None
        
        with self.assertRaises(frappe.ValidationError):
            trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

    # Test 15: Edge case - No students found
    @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
    def test_trigger_individual_flows_no_students(self, mock_get_students):
        mock_get_students.return_value = []
        
        with self.assertRaises(frappe.ValidationError):
            trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

    # Test 16: Test with legacy flow configuration
    @patch('tap_lms.onboarding_flows.frappe.enqueue')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_trigger_onboarding_flow_legacy(self, mock_get_doc, mock_enqueue):
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.glific_flow_id = "legacy_flow_123"
        mock_stage.glific_flow_type = "Group"
        # Simulate no stage_flows attribute
        delattr(mock_stage, 'stage_flows')
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = "job_123"
        
        result = trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
        
        self.assertTrue(result["success"])

    # Test 17: Test authentication failure
    @patch('tap_lms.onboarding_flows.get_glific_auth_headers')
    @patch('tap_lms.onboarding_flows.frappe.get_doc')
    def test_authentication_failure(self, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, self.glific_settings]
        
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
        
        with self.assertRaises(frappe.ValidationError):
            trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

    # Test 19: Test student without glific_id
    @patch('tap_lms.onboarding_flows.get_students_from_onboarding')
    def test_student_without_glific_id(self, mock_get_students):
        # Create student without glific_id
        student_no_glific = frappe.get_doc({
            "doctype": "Student",
            "first_name": "No",
            "last_name": "Glific",
            "phone": "+0987654321"
        }).insert()
        
        mock_get_students.return_value = [student_no_glific]
        
        result = trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        self.assertEqual(result["error_count"], 1)


if __name__ == '__main__':
    unittest.main()