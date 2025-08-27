

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import json
from datetime import datetime, timezone
import sys
import os

# For Frappe testing environment - this is the key fix
import frappe

# Import the functions to test - use absolute imports that work in Frappe
from tap_lms.glific_multi_enrollment_update import (
    check_student_multi_enrollment,
    update_specific_set_contacts_with_multi_enrollment,
    run_multi_enrollment_update_for_specific_set,
    get_backend_onboarding_sets,
    process_multiple_sets_simple,
    process_my_sets
)

from tap_lms.glific_integration import get_glific_settings, get_glific_auth_headers


class TestGlificMultiEnrollmentUpdate(unittest.TestCase):
    
    def setUp(self):
        """Set up test data"""
        self.test_student_id = "STU-001"
        self.test_student_name = "Test Student"
        self.test_phone = "1234567890"
        self.test_glific_id = "12345"
        self.test_set_name = "TEST-SET-001"
        
        # Mock Glific settings
        self.mock_settings = Mock()
        self.mock_settings.api_url = "https://test.glific.com"
        
        # Mock student document with enrollments
        self.mock_student_doc = Mock()
        self.mock_student_doc.enrollment = [Mock(), Mock()]  # Two enrollments
        self.mock_student_doc.glific_id = self.test_glific_id

    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    def test_check_student_multi_enrollment_multiple_enrollments(self, mock_get_doc, mock_exists):
        """Test student with multiple enrollments returns 'yes'"""
        mock_exists.return_value = True
        mock_get_doc.return_value = self.mock_student_doc
        
        result = check_student_multi_enrollment(self.test_student_id)
        
        self.assertEqual(result, "yes")
        mock_exists.assert_called_once_with("Student", self.test_student_id)
        mock_get_doc.assert_called_once_with("Student", self.test_student_id)

    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    def test_check_student_multi_enrollment_single_enrollment(self, mock_get_doc, mock_exists):
        """Test student with single enrollment returns 'no'"""
        mock_exists.return_value = True
        mock_student_single = Mock()
        mock_student_single.enrollment = [Mock()]  # Single enrollment
        mock_get_doc.return_value = mock_student_single
        
        result = check_student_multi_enrollment(self.test_student_id)
        
        self.assertEqual(result, "no")

    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    def test_check_student_multi_enrollment_no_enrollments(self, mock_get_doc, mock_exists):
        """Test student with no enrollments returns 'no'"""
        mock_exists.return_value = True
        mock_student_none = Mock()
        mock_student_none.enrollment = []  # No enrollments
        mock_get_doc.return_value = mock_student_none
        
        result = check_student_multi_enrollment(self.test_student_id)
        
        self.assertEqual(result, "no")

    @patch('frappe.db.exists')
    @patch('frappe.logger')
    def test_check_student_multi_enrollment_student_not_exists(self, mock_logger, mock_exists):
        """Test non-existent student returns 'no' and logs error"""
        mock_exists.return_value = False
        
        result = check_student_multi_enrollment(self.test_student_id)
        
        self.assertEqual(result, "no")
        mock_logger().error.assert_called()

    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_check_student_multi_enrollment_exception_handling(self, mock_logger, mock_get_doc, mock_exists):
        """Test exception handling returns 'no' and logs error"""
        mock_exists.return_value = True
        mock_get_doc.side_effect = Exception("Database error")
        
        result = check_student_multi_enrollment(self.test_student_id)
        
        self.assertEqual(result, "no")
        mock_logger().error.assert_called()

    def test_update_specific_set_contacts_missing_set_name(self):
        """Test function with missing set name parameter"""
        result = update_specific_set_contacts_with_multi_enrollment(None)
        
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")

    @patch('frappe.get_doc')
    def test_update_specific_set_contacts_set_not_found(self, mock_get_doc):
        """Test function with non-existent onboarding set"""
        mock_get_doc.side_effect = frappe.DoesNotExistError()
        
        result = update_specific_set_contacts_with_multi_enrollment(self.test_set_name)
        
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    @patch('frappe.get_doc')
    def test_update_specific_set_contacts_set_not_processed(self, mock_get_doc):
        """Test function with non-processed onboarding set"""
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Draft"
        mock_onboarding_set.set_name = self.test_set_name
        mock_get_doc.return_value = mock_onboarding_set
        
        result = update_specific_set_contacts_with_multi_enrollment(self.test_set_name)
        
        self.assertIn("error", result)
        self.assertIn("not 'Processed'", result["error"])

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_update_specific_set_contacts_no_students(self, mock_get_doc, mock_get_all):
        """Test function with no successfully processed students"""
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Processed"
        mock_onboarding_set.set_name = self.test_set_name
        mock_get_doc.return_value = mock_onboarding_set
        mock_get_all.return_value = []
        
        result = update_specific_set_contacts_with_multi_enrollment(self.test_set_name)
        
        self.assertIn("message", result)
        self.assertIn("No successfully processed students", result["message"])

    @patch('requests.post')
    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_settings')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment')
    def test_update_specific_set_contacts_successful_update(self, mock_check_enrollment, 
                                                          mock_auth_headers, mock_settings,
                                                          mock_exists, mock_get_doc, 
                                                          mock_get_all, mock_requests_post):
        """Test successful contact update"""
        # Setup mocks
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Processed"
        mock_onboarding_set.set_name = self.test_set_name
        
        mock_backend_student = {
            'student_id': self.test_student_id,
            'student_name': self.test_student_name,
            'phone': self.test_phone,
            'batch_skeyword': 'TEST'
        }
        
        mock_get_doc.side_effect = [mock_onboarding_set, self.mock_student_doc]
        mock_get_all.return_value = [mock_backend_student]
        mock_exists.return_value = True
        mock_settings.return_value = self.mock_settings
        mock_auth_headers.return_value = {"Authorization": "Bearer test-token"}
        mock_check_enrollment.return_value = "yes"
        
        # Mock Glific API responses
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": self.test_glific_id,
                        "name": self.test_student_name,
                        "phone": self.test_phone,
                        "fields": "{}"
                    }
                }
            }
        }
        
        update_response = Mock()
        update_response.status_code = 200
        update_response.json.return_value = {
            "data": {
                "updateContact": {
                    "contact": {
                        "id": self.test_glific_id,
                        "name": self.test_student_name,
                        "fields": '{"multi_enrollment": {"value": "yes", "type": "string"}}'
                    }
                }
            }
        }
        
        mock_requests_post.side_effect = [fetch_response, update_response]
        
        # Execute test
        result = update_specific_set_contacts_with_multi_enrollment(self.test_set_name)
        
        # Assertions
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["total_processed"], 1)

    @patch('requests.post')
    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_settings')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_auth_headers')
    def test_update_specific_set_contacts_glific_api_error(self, mock_auth_headers, mock_settings,
                                                         mock_exists, mock_get_doc, 
                                                         mock_get_all, mock_requests_post):
        """Test handling of Glific API errors"""
        # Setup mocks similar to successful test
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Processed"
        mock_onboarding_set.set_name = self.test_set_name
        
        mock_backend_student = {
            'student_id': self.test_student_id,
            'student_name': self.test_student_name,
            'phone': self.test_phone,
            'batch_skeyword': 'TEST'
        }
        
        mock_get_doc.side_effect = [mock_onboarding_set, self.mock_student_doc]
        mock_get_all.return_value = [mock_backend_student]
        mock_exists.return_value = True
        mock_settings.return_value = self.mock_settings
        mock_auth_headers.return_value = {"Authorization": "Bearer test-token"}
        
        # Mock API error response
        error_response = Mock()
        error_response.status_code = 500
        mock_requests_post.return_value = error_response
        
        # Execute test
        result = update_specific_set_contacts_with_multi_enrollment(self.test_set_name)
        
        # Assertions
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["total_processed"], 1)

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('frappe.db.begin')
    @patch('frappe.db.commit')
    def test_run_multi_enrollment_update_for_specific_set_success(self, mock_commit, mock_begin, mock_update):
        """Test successful whitelist function execution"""
        mock_update.return_value = {
            "set_name": self.test_set_name,
            "updated": 5,
            "skipped": 0,
            "errors": 0,
            "total_processed": 5
        }
        
        result = run_multi_enrollment_update_for_specific_set(self.test_set_name)
        
        self.assertIn("Process completed", result)
        self.assertIn("Updated: 5", result)
        mock_begin.assert_called_once()
        mock_commit.assert_called_once()

    def test_run_multi_enrollment_update_for_specific_set_missing_name(self):
        """Test whitelist function with missing set name"""
        result = run_multi_enrollment_update_for_specific_set(None)
        
        self.assertIn("Error: Backend Student Onboarding set name is required", result)

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('frappe.db.begin')
    @patch('frappe.db.rollback')
    def test_run_multi_enrollment_update_for_specific_set_exception(self, mock_rollback, mock_begin, mock_update):
        """Test whitelist function exception handling"""
        mock_update.side_effect = Exception("Test error")
        
        result = run_multi_enrollment_update_for_specific_set(self.test_set_name)
        
        self.assertIn("Error occurred", result)
        mock_begin.assert_called_once()
        mock_rollback.assert_called_once()

    @patch('frappe.get_all')
    def test_get_backend_onboarding_sets(self, mock_get_all):
        """Test getting list of processed onboarding sets"""
        mock_sets = [
            {
                "name": "SET-001",
                "set_name": "Test Set 1",
                "processed_student_count": 10,
                "upload_date": "2024-01-01"
            },
            {
                "name": "SET-002",
                "set_name": "Test Set 2",
                "processed_student_count": 15,
                "upload_date": "2024-01-02"
            }
        ]
        mock_get_all.return_value = mock_sets
        
        result = get_backend_onboarding_sets()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "SET-001")
        mock_get_all.assert_called_once_with(
            "Backend Student Onboarding",
            filters={"status": "Processed"},
            fields=["name", "set_name", "processed_student_count", "upload_date"],
            order_by="upload_date desc"
        )

    @patch('time.sleep')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_process_multiple_sets_simple_success(self, mock_update, mock_sleep):
        """Test processing multiple sets successfully"""
        set_names = ["SET-001", "SET-002"]
        
        # Mock successful results
        mock_update.side_effect = [
            {"updated": 5, "errors": 0, "total_processed": 5},
            {"updated": 3, "errors": 1, "total_processed": 4}
        ]
        
        results = process_multiple_sets_simple(set_names, batch_size=10)
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["updated"], 5)
        self.assertEqual(results[1]["updated"], 3)
        self.assertEqual(results[0]["status"], "completed")

    @patch('time.sleep')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_process_multiple_sets_simple_with_error(self, mock_update, mock_sleep):
        """Test processing multiple sets with error"""
        set_names = ["SET-001"]
        
        # Mock error result
        mock_update.return_value = {"error": "Set not found"}
        
        results = process_multiple_sets_simple(set_names, batch_size=10)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["updated"], 0)
        self.assertEqual(results[0]["errors"], 0)
        self.assertEqual(results[0]["status"], "completed")

    @patch('time.sleep')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_process_multiple_sets_simple_exception(self, mock_update, mock_sleep):
        """Test processing multiple sets with exception"""
        set_names = ["SET-001"]
        
        # Mock exception
        mock_update.side_effect = Exception("Test exception")
        
        results = process_multiple_sets_simple(set_names, batch_size=10)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "error")
        self.assertIn("error", results[0])

    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_my_sets_with_list(self, mock_enqueue):
        """Test processing sets with list input"""
        set_names = ["SET-001", "SET-002"]
        mock_job = Mock()
        mock_job.id = "job-123"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets(set_names)
        
        self.assertIn("Started processing 2 sets", result)
        self.assertIn("Job ID: job-123", result)
        mock_enqueue.assert_called_once()

    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_my_sets_with_string(self, mock_enqueue):
        """Test processing sets with comma-separated string input"""
        set_names = "SET-001, SET-002, SET-003"
        mock_job = Mock()
        mock_job.id = "job-456"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets(set_names)
        
        self.assertIn("Started processing 3 sets", result)
        mock_enqueue.assert_called_once()

    def test_json_field_parsing_in_contact_update(self):
        """Test JSON field parsing and updating logic"""
        # Test existing fields parsing
        existing_fields_json = '{"name": {"value": "John", "type": "string"}, "age": {"value": "25", "type": "number"}}'
        existing_fields = json.loads(existing_fields_json)
        
        # Add multi_enrollment field
        existing_fields["multi_enrollment"] = {
            "value": "yes",
            "type": "string",
            "inserted_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Verify structure
        self.assertIn("multi_enrollment", existing_fields)
        self.assertEqual(existing_fields["multi_enrollment"]["value"], "yes")
        self.assertEqual(existing_fields["multi_enrollment"]["type"], "string")
        self.assertIn("inserted_at", existing_fields["multi_enrollment"])


# Additional utility functions for testing
def create_mock_student_doc(student_id, glific_id, enrollment_count=1):
    """Helper function to create mock student documents"""
    mock_student = Mock()
    mock_student.name = student_id
    mock_student.glific_id = glific_id
    mock_student.enrollment = [Mock() for _ in range(enrollment_count)]
    return mock_student

def create_mock_glific_response(contact_id, name, phone, fields=None):
    """Helper function to create mock Glific API responses"""
    if fields is None:
        fields = "{}"
    
    return {
        "data": {
            "contact": {
                "contact": {
                    "id": contact_id,
                    "name": name,
                    "phone": phone,
                    "fields": fields
                }
            }
        }
    }

def create_mock_backend_student(student_id, student_name, phone, batch_skeyword="TEST"):
    """Helper function to create mock backend student data"""
    return {
        'student_id': student_id,
        'student_name': student_name,
        'phone': phone,
        'batch_skeyword': batch_skeyword
    }


# Test data constants
TEST_CONSTANTS = {
    'STUDENT_ID': 'STU-001',
    'STUDENT_NAME': 'Test Student',
    'PHONE': '1234567890',
    'GLIFIC_ID': '12345',
    'SET_NAME': 'TEST-SET-001',
    'API_URL': 'https://test.glific.com'
}