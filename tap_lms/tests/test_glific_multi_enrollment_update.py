# test_glific_multi_enrollment_update.py
# Working test file for Frappe environment

import unittest
import frappe
from unittest.mock import patch, Mock
import json
from datetime import datetime, timezone


class TestGlificMultiEnrollmentUpdate(unittest.TestCase):
    """Test cases for Glific multi-enrollment update functionality"""

    @classmethod
    def setUpClass(cls):
        """Set up test class"""
        # Ensure Frappe is connected
        if not frappe.db:
            frappe.connect()
        frappe.set_user("Administrator")

    def setUp(self):
        """Set up each test"""
        frappe.db.begin()

    def tearDown(self):
        """Clean up after each test"""
        frappe.db.rollback()

    def test_check_student_multi_enrollment_with_multiple(self):
        """Test student with multiple enrollments returns 'yes'"""
        with patch('frappe.db.exists') as mock_exists, \
             patch('frappe.get_doc') as mock_get_doc:
            
            # Setup mocks
            mock_exists.return_value = True
            mock_student = Mock()
            mock_student.enrollment = [{'enrollment_id': 1}, {'enrollment_id': 2}]
            mock_get_doc.return_value = mock_student
            
            # Import function inside test to avoid import errors
            from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
            
            result = check_student_multi_enrollment("STUDENT001")
            self.assertEqual(result, "yes")
            mock_exists.assert_called_once_with("Student", "STUDENT001")
            mock_get_doc.assert_called_once_with("Student", "STUDENT001")

    def test_check_student_multi_enrollment_with_single(self):
        """Test student with single enrollment returns 'no'"""
        with patch('frappe.db.exists') as mock_exists, \
             patch('frappe.get_doc') as mock_get_doc:
            
            # Setup mocks
            mock_exists.return_value = True
            mock_student = Mock()
            mock_student.enrollment = [{'enrollment_id': 1}]
            mock_get_doc.return_value = mock_student
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
            
            result = check_student_multi_enrollment("STUDENT001")
            self.assertEqual(result, "no")

    def test_check_student_multi_enrollment_with_empty(self):
        """Test student with no enrollments returns 'no'"""
        with patch('frappe.db.exists') as mock_exists, \
             patch('frappe.get_doc') as mock_get_doc:
            
            # Setup mocks
            mock_exists.return_value = True
            mock_student = Mock()
            mock_student.enrollment = []
            mock_get_doc.return_value = mock_student
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
            
            result = check_student_multi_enrollment("STUDENT001")
            self.assertEqual(result, "no")

    def test_check_student_multi_enrollment_not_found(self):
        """Test when student document doesn't exist"""
        with patch('frappe.db.exists') as mock_exists:
            mock_exists.return_value = False
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
            
            result = check_student_multi_enrollment("NONEXISTENT")
            self.assertEqual(result, "no")

    def test_check_student_multi_enrollment_exception(self):
        """Test exception handling returns 'no'"""
        with patch('frappe.db.exists') as mock_exists, \
             patch('frappe.get_doc') as mock_get_doc:
            
            mock_exists.return_value = True
            mock_get_doc.side_effect = Exception("Database error")
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
            
            result = check_student_multi_enrollment("STUDENT001")
            self.assertEqual(result, "no")

    def test_update_contacts_empty_set_name(self):
        """Test with empty onboarding set name"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        result = update_specific_set_contacts_with_multi_enrollment("")
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")

    def test_update_contacts_set_not_found(self):
        """Test when onboarding set doesn't exist"""
        with patch('frappe.get_doc') as mock_get_doc:
            mock_get_doc.side_effect = frappe.DoesNotExistError()
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
            
            result = update_specific_set_contacts_with_multi_enrollment("INVALID_SET")
            self.assertIn("not found", result["error"])

    def test_update_contacts_set_not_processed(self):
        """Test when onboarding set status is not 'Processed'"""
        with patch('frappe.get_doc') as mock_get_doc:
            mock_set = Mock()
            mock_set.status = "Draft"
            mock_set.set_name = "TEST_SET"
            mock_get_doc.return_value = mock_set
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            self.assertIn("status is 'Draft', not 'Processed'", result["error"])

    def test_update_contacts_no_students(self):
        """Test when no successfully processed students found"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all:
            
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "TEST_SET"
            mock_get_doc.return_value = mock_set
            mock_get_all.return_value = []
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            self.assertIn("No successfully processed students found", result["message"])

    def test_update_contacts_student_without_glific_id(self):
        """Test handling student without Glific ID"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists') as mock_exists:
            
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "TEST_SET"
            
            mock_student = Mock()
            mock_student.glific_id = None
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{
                "student_name": "John Doe",
                "phone": "1234567890",
                "student_id": "STUDENT001",
                "batch_skeyword": "batch1"
            }]
            mock_exists.return_value = True
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["updated"], 0)

    @patch('requests.post')
    def test_update_contacts_successful(self, mock_requests):
        """Test successful contact update"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists') as mock_exists, \
             patch('tap_lms.tap_lms.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.tap_lms.glific_integration.get_glific_auth_headers') as mock_headers, \
             patch('tap_lms.tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "TEST_SET"
            
            mock_student = Mock()
            mock_student.glific_id = "123"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{
                "student_name": "John Doe",
                "phone": "1234567890",
                "student_id": "STUDENT001",
                "batch_skeyword": "batch1"
            }]
            mock_exists.return_value = True
            mock_check.return_value = "yes"
            
            mock_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock Glific API responses
            mock_fetch_response = Mock()
            mock_fetch_response.status_code = 200
            mock_fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "123",
                            "name": "John Doe",
                            "phone": "1234567890",
                            "fields": "{}"
                        }
                    }
                }
            }
            
            mock_update_response = Mock()
            mock_update_response.status_code = 200
            mock_update_response.json.return_value = {
                "data": {
                    "updateContact": {
                        "contact": {
                            "id": "123",
                            "name": "John Doe",
                            "fields": '{"multi_enrollment": {"value": "yes", "type": "string"}}'
                        }
                    }
                }
            }
            
            mock_requests.side_effect = [mock_fetch_response, mock_update_response]
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            self.assertEqual(result["updated"], 1)
            self.assertEqual(result["errors"], 0)
            self.assertEqual(result["total_processed"], 1)

    @patch('requests.post')
    def test_update_contacts_api_error(self, mock_requests):
        """Test Glific API error handling"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists') as mock_exists, \
             patch('tap_lms.tap_lms.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.tap_lms.glific_integration.get_glific_auth_headers') as mock_headers, \
             patch('tap_lms.tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "TEST_SET"
            
            mock_student = Mock()
            mock_student.glific_id = "123"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{
                "student_name": "John Doe",
                "phone": "1234567890",
                "student_id": "STUDENT001",
                "batch_skeyword": "batch1"
            }]
            mock_exists.return_value = True
            mock_check.return_value = "yes"
            
            mock_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock API error response
            mock_error_response = Mock()
            mock_error_response.status_code = 500
            mock_requests.return_value = mock_error_response
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["updated"], 0)

    def test_run_update_missing_set_name(self):
        """Test whitelist function with missing set name"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        result = run_multi_enrollment_update_for_specific_set("")
        self.assertIn("Backend Student Onboarding set name is required", result)

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_run_update_successful(self, mock_update):
        """Test successful execution of whitelist function"""
        mock_update.return_value = {
            "set_name": "TEST_SET",
            "updated": 5,
            "skipped": 0,
            "errors": 0,
            "total_processed": 5
        }
        
        from tap_lms.tap_lms.glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        result = run_multi_enrollment_update_for_specific_set("TEST_SET")
        
        self.assertIn("Process completed", result)
        self.assertIn("Updated: 5", result)

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_run_update_with_error(self, mock_update):
        """Test whitelist function with error"""
        mock_update.return_value = {"error": "Set not found"}
        
        from tap_lms.tap_lms.glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        result = run_multi_enrollment_update_for_specific_set("INVALID_SET")
        
        self.assertIn("Error: Set not found", result)

    @patch('frappe.get_all')
    def test_get_backend_onboarding_sets(self, mock_get_all):
        """Test getting backend onboarding sets"""
        mock_get_all.return_value = [
            {
                "name": "SET001",
                "set_name": "Test Set 1",
                "processed_student_count": 10,
                "upload_date": "2023-01-01"
            },
            {
                "name": "SET002",
                "set_name": "Test Set 2",
                "processed_student_count": 15,
                "upload_date": "2023-01-02"
            }
        ]
        
        from tap_lms.tap_lms.glific_multi_enrollment_update import get_backend_onboarding_sets
        
        result = get_backend_onboarding_sets()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "SET001")
        mock_get_all.assert_called_once_with(
            "Backend Student Onboarding",
            filters={"status": "Processed"},
            fields=["name", "set_name", "processed_student_count", "upload_date"],
            order_by="upload_date desc"
        )

    def test_process_my_sets_empty_list(self):
        """Test processing empty set list"""
        # Mock the enqueue function to avoid background job issues
        with patch('frappe.utils.background_jobs.enqueue') as mock_enqueue:
            mock_job = Mock()
            mock_job.id = "job123"
            mock_enqueue.return_value = mock_job
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import process_my_sets
            
            result = process_my_sets([])
            
            self.assertIn("Started processing 0 sets", result)

    def test_process_my_sets_with_string(self):
        """Test processing sets with comma-separated string"""
        with patch('frappe.utils.background_jobs.enqueue') as mock_enqueue:
            mock_job = Mock()
            mock_job.id = "job456"
            mock_enqueue.return_value = mock_job
            
            from tap_lms.tap_lms.glific_multi_enrollment_update import process_my_sets
            
            result = process_my_sets("SET001, SET002, SET003")
            
            self.assertIn("Started processing 3 sets", result)
            self.assertIn("Job ID: job456", result)
            
            # Verify whitespace was stripped
            call_args = mock_enqueue.call_args
            set_names = call_args[1]['set_names']
            self.assertEqual(set_names, ["SET001", "SET002", "SET003"])


def run_tests():
    """Function to run all tests"""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    run_tests()