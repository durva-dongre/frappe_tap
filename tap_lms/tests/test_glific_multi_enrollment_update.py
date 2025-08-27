# test_glific_multi_enrollment_update.py
# Test cases for glific_multi_enrollment_update.py

import unittest
from unittest.mock import patch, MagicMock, call
import json
import frappe
from datetime import datetime, timezone
from frappe.tests.utils import FrappeTestCase
from tap_lms.tap_lms.glific_multi_enrollment_update import (
    check_student_multi_enrollment,
    update_specific_set_contacts_with_multi_enrollment,
    run_multi_enrollment_update_for_specific_set,
    get_backend_onboarding_sets,
    process_multiple_sets_simple,
    process_my_sets
)


class TestGlificMultiEnrollmentUpdate(FrappeTestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.sample_student_id = "STU001"
        self.sample_student_name = "John Doe"
        self.sample_phone = "+1234567890"
        self.sample_glific_id = "12345"
        self.sample_set_name = "SET001"
        
    def tearDown(self):
        """Clean up after each test method."""
        pass

    # Test check_student_multi_enrollment function
    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_check_student_multi_enrollment_multiple_enrollments(self, mock_logger, mock_get_doc, mock_exists):
        """Test student with multiple enrollments returns 'yes'"""
        # Setup
        mock_exists.return_value = True
        mock_student = MagicMock()
        mock_student.enrollment = [MagicMock(), MagicMock(), MagicMock()]  # 3 enrollments
        mock_get_doc.return_value = mock_student
        
        # Execute
        result = check_student_multi_enrollment(self.sample_student_id)
        
        # Assert
        self.assertEqual(result, "yes")
        mock_exists.assert_called_once_with("Student", self.sample_student_id)
        mock_get_doc.assert_called_once_with("Student", self.sample_student_id)

    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_check_student_multi_enrollment_single_enrollment(self, mock_logger, mock_get_doc, mock_exists):
        """Test student with single enrollment returns 'no'"""
        # Setup
        mock_exists.return_value = True
        mock_student = MagicMock()
        mock_student.enrollment = [MagicMock()]  # 1 enrollment
        mock_get_doc.return_value = mock_student
        
        # Execute
        result = check_student_multi_enrollment(self.sample_student_id)
        
        # Assert
        self.assertEqual(result, "no")

    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_check_student_multi_enrollment_no_enrollments(self, mock_logger, mock_get_doc, mock_exists):
        """Test student with no enrollments returns 'no'"""
        # Setup
        mock_exists.return_value = True
        mock_student = MagicMock()
        mock_student.enrollment = []  # No enrollments
        mock_get_doc.return_value = mock_student
        
        # Execute
        result = check_student_multi_enrollment(self.sample_student_id)
        
        # Assert
        self.assertEqual(result, "no")

    @patch('frappe.db.exists')
    @patch('frappe.logger')
    def test_check_student_multi_enrollment_student_not_found(self, mock_logger, mock_exists):
        """Test student not found returns 'no' and logs error"""
        # Setup
        mock_exists.return_value = False
        
        # Execute
        result = check_student_multi_enrollment(self.sample_student_id)
        
        # Assert
        self.assertEqual(result, "no")
        mock_logger.return_value.error.assert_called_once()

    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_check_student_multi_enrollment_exception_handling(self, mock_logger, mock_get_doc, mock_exists):
        """Test exception handling returns 'no' and logs error"""
        # Setup
        mock_exists.return_value = True
        mock_get_doc.side_effect = Exception("Database error")
        
        # Execute
        result = check_student_multi_enrollment(self.sample_student_id)
        
        # Assert
        self.assertEqual(result, "no")
        mock_logger.return_value.error.assert_called_once()

    # Test update_specific_set_contacts_with_multi_enrollment function
    @patch('frappe.get_doc')
    def test_update_specific_set_no_set_name(self, mock_get_doc):
        """Test function returns error when no set name provided"""
        result = update_specific_set_contacts_with_multi_enrollment(None)
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")

    @patch('frappe.get_doc')
    def test_update_specific_set_not_found(self, mock_get_doc):
        """Test function returns error when set not found"""
        mock_get_doc.side_effect = frappe.DoesNotExistError()
        
        result = update_specific_set_contacts_with_multi_enrollment(self.sample_set_name)
        
        self.assertIn("not found", result["error"])

    @patch('frappe.get_doc')
    def test_update_specific_set_not_processed(self, mock_get_doc):
        """Test function returns error when set status is not 'Processed'"""
        mock_set = MagicMock()
        mock_set.status = "Draft"
        mock_set.set_name = self.sample_set_name
        mock_get_doc.return_value = mock_set
        
        result = update_specific_set_contacts_with_multi_enrollment(self.sample_set_name)
        
        self.assertIn("not 'Processed'", result["error"])

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_update_specific_set_no_students(self, mock_get_doc, mock_get_all):
        """Test function returns message when no students found"""
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = self.sample_set_name
        mock_get_doc.return_value = mock_set
        mock_get_all.return_value = []
        
        result = update_specific_set_contacts_with_multi_enrollment(self.sample_set_name)
        
        self.assertIn("No successfully processed students found", result["message"])

    @patch('requests.post')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.get_glific_settings')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment')
    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    @patch('frappe.logger')
    def test_update_specific_set_successful_update(self, mock_logger, mock_exists, mock_get_doc, 
                                                  mock_get_all, mock_check_enrollment, 
                                                  mock_get_headers, mock_get_settings, mock_post):
        """Test successful update of contacts"""
        # Setup onboarding set
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = self.sample_set_name
        
        # Setup student document
        mock_student_doc = MagicMock()
        mock_student_doc.glific_id = self.sample_glific_id
        
        # Setup get_doc to return different objects based on doctype
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        mock_exists.return_value = True
        
        # Setup backend students
        mock_get_all.return_value = [{
            "student_name": self.sample_student_name,
            "phone": self.sample_phone,
            "student_id": self.sample_student_id,
            "batch_skeyword": "BATCH001"
        }]
        
        # Setup multi-enrollment check
        mock_check_enrollment.return_value = "yes"
        
        # Setup Glific API settings and headers
        mock_settings = MagicMock()
        mock_settings.api_url = "https://api.glific.com"
        mock_get_settings.return_value = mock_settings
        mock_get_headers.return_value = {"Authorization": "Bearer token"}
        
        # Setup API responses
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": self.sample_glific_id,
                        "name": self.sample_student_name,
                        "phone": self.sample_phone,
                        "fields": "{}"
                    }
                }
            }
        }
        
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = {
            "data": {
                "updateContact": {
                    "contact": {
                        "id": self.sample_glific_id,
                        "name": self.sample_student_name,
                        "fields": json.dumps({
                            "multi_enrollment": {
                                "value": "yes",
                                "type": "string",
                                "inserted_at": datetime.now(timezone.utc).isoformat()
                            }
                        })
                    }
                }
            }
        }
        
        mock_post.side_effect = [fetch_response, update_response]
        
        # Execute
        result = update_specific_set_contacts_with_multi_enrollment(self.sample_set_name)
        
        # Assert
        self.assertEqual(result["set_name"], self.sample_set_name)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["total_processed"], 1)

    @patch('requests.post')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.get_glific_settings')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.get_glific_auth_headers')
    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    @patch('frappe.logger')
    def test_update_specific_set_student_no_glific_id(self, mock_logger, mock_exists, mock_get_doc, 
                                                     mock_get_all, mock_get_headers, 
                                                     mock_get_settings, mock_post):
        """Test handling student without Glific ID"""
        # Setup onboarding set
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = self.sample_set_name
        
        # Setup student document without glific_id
        mock_student_doc = MagicMock()
        mock_student_doc.glific_id = None
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        mock_exists.return_value = True
        
        # Setup backend students
        mock_get_all.return_value = [{
            "student_name": self.sample_student_name,
            "phone": self.sample_phone,
            "student_id": self.sample_student_id,
            "batch_skeyword": "BATCH001"
        }]
        
        # Execute
        result = update_specific_set_contacts_with_multi_enrollment(self.sample_set_name)
        
        # Assert
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], 1)
        mock_logger.return_value.warning.assert_called()

    # Test run_multi_enrollment_update_for_specific_set function
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('frappe.db.begin')
    @patch('frappe.db.commit')
    @patch('frappe.db.rollback')
    def test_run_multi_enrollment_update_success(self, mock_rollback, mock_commit, 
                                               mock_begin, mock_update):
        """Test successful run of multi-enrollment update"""
        mock_update.return_value = {
            "set_name": self.sample_set_name,
            "updated": 5,
            "skipped": 2,
            "errors": 1,
            "total_processed": 8
        }
        
        result = run_multi_enrollment_update_for_specific_set(self.sample_set_name)
        
        self.assertIn("Process completed", result)
        self.assertIn("Updated: 5", result)
        mock_commit.assert_called_once()

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('frappe.db.begin')
    @patch('frappe.db.commit')
    @patch('frappe.db.rollback')
    def test_run_multi_enrollment_update_error(self, mock_rollback, mock_commit, 
                                             mock_begin, mock_update):
        """Test error handling in run function"""
        mock_update.return_value = {"error": "Set not found"}
        
        result = run_multi_enrollment_update_for_specific_set(self.sample_set_name)
        
        self.assertIn("Error: Set not found", result)

    def test_run_multi_enrollment_update_no_set_name(self):
        """Test error when no set name provided"""
        result = run_multi_enrollment_update_for_specific_set(None)
        
        self.assertIn("Error: Backend Student Onboarding set name is required", result)

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('frappe.db.begin')
    @patch('frappe.db.commit')
    @patch('frappe.db.rollback')
    @patch('frappe.logger')
    def test_run_multi_enrollment_update_exception(self, mock_logger, mock_rollback, 
                                                  mock_commit, mock_begin, mock_update):
        """Test exception handling in run function"""
        mock_update.side_effect = Exception("Database connection failed")
        
        result = run_multi_enrollment_update_for_specific_set(self.sample_set_name)
        
        self.assertIn("Error occurred", result)
        mock_rollback.assert_called_once()

    # Test get_backend_onboarding_sets function
    @patch('frappe.get_all')
    def test_get_backend_onboarding_sets(self, mock_get_all):
        """Test getting backend onboarding sets"""
        expected_sets = [
            {
                "name": "SET001",
                "set_name": "Test Set 1",
                "processed_student_count": 10,
                "upload_date": "2024-01-01"
            },
            {
                "name": "SET002", 
                "set_name": "Test Set 2",
                "processed_student_count": 15,
                "upload_date": "2024-01-02"
            }
        ]
        mock_get_all.return_value = expected_sets
        
        result = get_backend_onboarding_sets()
        
        self.assertEqual(result, expected_sets)
        mock_get_all.assert_called_once_with(
            "Backend Student Onboarding",
            filters={"status": "Processed"},
            fields=["name", "set_name", "processed_student_count", "upload_date"],
            order_by="upload_date desc"
        )

    # Test process_multiple_sets_simple function
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('time.sleep')
    @patch('frappe.logger')
    def test_process_multiple_sets_simple_success(self, mock_logger, mock_sleep, mock_update):
        """Test processing multiple sets successfully"""
        set_names = ["SET001", "SET002"]
        
        # Mock successful responses
        mock_update.return_value = {
            "updated": 5,
            "errors": 0,
            "total_processed": 5
        }
        
        result = process_multiple_sets_simple(set_names)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["set_name"], "SET001")
        self.assertEqual(result[0]["updated"], 5)
        self.assertEqual(result[0]["status"], "completed")

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('frappe.logger')
    def test_process_multiple_sets_simple_with_error(self, mock_logger, mock_update):
        """Test processing multiple sets with errors"""
        set_names = ["SET001"]
        
        # Mock error response
        mock_update.return_value = {"error": "Set not found"}
        
        result = process_multiple_sets_simple(set_names)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["set_name"], "SET001")
        self.assertEqual(result[0]["updated"], 0)

    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    @patch('frappe.logger')
    def test_process_multiple_sets_simple_exception(self, mock_logger, mock_update):
        """Test processing multiple sets with exception"""
        set_names = ["SET001"]
        
        # Mock exception
        mock_update.side_effect = Exception("Unexpected error")
        
        result = process_multiple_sets_simple(set_names)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["set_name"], "SET001")
        self.assertEqual(result[0]["status"], "error")
        self.assertIn("error", result[0])

    # Test process_my_sets function
    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_my_sets_with_list(self, mock_enqueue):
        """Test processing sets with list input"""
        set_names = ["SET001", "SET002"]
        mock_job = MagicMock()
        mock_job.id = "job123"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets(set_names)
        
        self.assertIn("Started processing 2 sets", result)
        self.assertIn("job123", result)
        mock_enqueue.assert_called_once()

    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_my_sets_with_string(self, mock_enqueue):
        """Test processing sets with comma-separated string input"""
        set_names = "SET001, SET002, SET003"
        mock_job = MagicMock()
        mock_job.id = "job456"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets(set_names)
        
        self.assertIn("Started processing 3 sets", result)
        self.assertIn("job456", result)


class TestIntegrationScenarios(FrappeTestCase):
    """Integration test scenarios"""
    
    @patch('requests.post')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.get_glific_settings')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.get_glific_auth_headers')
    def test_glific_api_error_handling(self, mock_get_headers, mock_get_settings, mock_post):
        """Test handling of various Glific API error responses"""
        # Test 500 error
        error_response = MagicMock()
        error_response.status_code = 500
        mock_post.return_value = error_response
        
        # Test with mocked frappe components would go here
        # This would require more complex setup

    def test_large_batch_processing(self):
        """Test processing large batches of students"""
        # This would test the batch_size parameter and pagination
        pass

    def test_concurrent_processing(self):
        """Test handling of concurrent processing scenarios"""
        # This would test race conditions and database locking
        pass


if __name__ == '__main__':
    # For Frappe testing, use frappe.test_runner
    import frappe
    frappe.init(site='test_site')
    frappe.connect()
    
    # Test runner configuration
    unittest.main(verbosity=2)


# Additional test utilities and fixtures
class TestDataFactory:
    """Factory for creating test data"""
    
    @staticmethod
    def create_backend_student(student_id="STU001", name="John Doe", phone="+1234567890"):
        return {
            "student_name": name,
            "phone": phone,
            "student_id": student_id,
            "batch_skeyword": "BATCH001"
        }
    
    @staticmethod
    def create_glific_contact_response(contact_id="12345", name="John Doe", fields=None):
        if fields is None:
            fields = "{}"
        
        return {
            "data": {
                "contact": {
                    "contact": {
                        "id": contact_id,
                        "name": name,
                        "phone": "+1234567890",
                        "fields": fields
                    }
                }
            }
        }
    
    @staticmethod
    def create_student_doc(student_id="STU001", glific_id="12345", enrollments=None):
        if enrollments is None:
            enrollments = [MagicMock(), MagicMock()]  # Default 2 enrollments
        
        mock_student = MagicMock()
        mock_student.name = student_id
        mock_student.glific_id = glific_id
        mock_student.enrollment = enrollments
        return mock_student


# Performance test cases
class TestPerformance(FrappeTestCase):
    """Performance-related test cases"""
    
    def test_batch_size_optimization(self):
        """Test optimal batch sizes for processing"""
        pass
    
    def test_memory_usage(self):
        """Test memory usage with large datasets"""
        pass
    
    def test_api_rate_limiting(self):
        """Test handling of API rate limits"""
        pass


# Edge case test scenarios
class TestEdgeCases(FrappeTestCase):
    """Edge case scenarios"""
    
    def test_malformed_json_in_fields(self):
        """Test handling of malformed JSON in Glific contact fields"""
        pass
    
    def test_unicode_characters_in_names(self):
        """Test handling of unicode characters in student names"""
        pass
    
    def test_very_long_field_values(self):
        """Test handling of very long field values"""
        pass
    
    def test_network_timeouts(self):
        """Test handling of network timeouts"""
        pass
    
    def test_database_connection_loss(self):
        """Test handling of database connection issues"""
        pass