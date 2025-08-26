# test_glific_multi_enrollment_update.py
# Test cases for glific_multi_enrollment_update.py

import frappe
import unittest
from unittest.mock import patch, MagicMock, call
import json
from datetime import datetime, timezone
from frappe.tests.utils import FrappeTestCase


class TestGlificMultiEnrollmentUpdate(FrappeTestCase):
    
    def setUp(self):
        """Set up test data"""
        self.test_student_id = "STU-001"
        self.test_student_name = "Test Student"
        self.test_phone = "+1234567890"
        self.test_glific_id = "12345"
        self.test_set_name = "TEST-SET-001"
        
        # Create test Backend Student Onboarding
        self.test_onboarding_set = frappe.get_doc({
            "doctype": "Backend Student Onboarding",
            "name": self.test_set_name,
            "set_name": "Test Set 001",
            "status": "Processed",
            "processed_student_count": 2
        })
        
        # Create test Student document
        self.test_student = frappe.get_doc({
            "doctype": "Student",
            "name": self.test_student_id,
            "student_name": self.test_student_name,
            "glific_id": self.test_glific_id,
            "enrollment": [
                {"program": "Program 1", "batch": "Batch 1"},
                {"program": "Program 2", "batch": "Batch 2"}
            ]
        })
        
        # Create test Backend Students
        self.test_backend_students = [
            {
                "student_name": "Test Student 1",
                "phone": "+1234567890",
                "student_id": "STU-001",
                "batch_skeyword": "BATCH1",
                "parent": self.test_set_name,
                "processing_status": "Success"
            },
            {
                "student_name": "Test Student 2", 
                "phone": "+1234567891",
                "student_id": "STU-002",
                "batch_skeyword": "BATCH2",
                "parent": self.test_set_name,
                "processing_status": "Success"
            }
        ]

    def tearDown(self):
        """Clean up test data"""
        pass

    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    def test_check_student_multi_enrollment_with_multiple_enrollments(self, mock_exists, mock_get_doc):
        """Test check_student_multi_enrollment returns 'yes' for student with multiple enrollments"""
        from glific_multi_enrollment_update import check_student_multi_enrollment
        
        # Mock student exists
        mock_exists.return_value = True
        
        # Mock student document with multiple enrollments
        mock_student = MagicMock()
        mock_student.enrollment = [
            {"program": "Program 1"},
            {"program": "Program 2"}
        ]
        mock_get_doc.return_value = mock_student
        
        result = check_student_multi_enrollment("STU-001")
        
        self.assertEqual(result, "yes")
        mock_exists.assert_called_once_with("Student", "STU-001")
        mock_get_doc.assert_called_once_with("Student", "STU-001")

    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    def test_check_student_multi_enrollment_with_single_enrollment(self, mock_exists, mock_get_doc):
        """Test check_student_multi_enrollment returns 'no' for student with single enrollment"""
        from glific_multi_enrollment_update import check_student_multi_enrollment
        
        # Mock student exists
        mock_exists.return_value = True
        
        # Mock student document with single enrollment
        mock_student = MagicMock()
        mock_student.enrollment = [{"program": "Program 1"}]
        mock_get_doc.return_value = mock_student
        
        result = check_student_multi_enrollment("STU-001")
        
        self.assertEqual(result, "no")

    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    def test_check_student_multi_enrollment_no_enrollments(self, mock_exists, mock_get_doc):
        """Test check_student_multi_enrollment returns 'no' for student with no enrollments"""
        from glific_multi_enrollment_update import check_student_multi_enrollment
        
        # Mock student exists
        mock_exists.return_value = True
        
        # Mock student document with no enrollments
        mock_student = MagicMock()
        mock_student.enrollment = []
        mock_get_doc.return_value = mock_student
        
        result = check_student_multi_enrollment("STU-001")
        
        self.assertEqual(result, "no")

    @patch('frappe.db.exists')
    def test_check_student_multi_enrollment_student_not_exists(self, mock_exists):
        """Test check_student_multi_enrollment returns 'no' when student doesn't exist"""
        from glific_multi_enrollment_update import check_student_multi_enrollment
        
        # Mock student doesn't exist
        mock_exists.return_value = False
        
        result = check_student_multi_enrollment("NONEXISTENT")
        
        self.assertEqual(result, "no")

    @patch('frappe.logger')
    @patch('frappe.get_doc')
    @patch('frappe.db.exists')
    def test_check_student_multi_enrollment_exception(self, mock_exists, mock_get_doc, mock_logger):
        """Test check_student_multi_enrollment handles exceptions gracefully"""
        from glific_multi_enrollment_update import check_student_multi_enrollment
        
        # Mock student exists
        mock_exists.return_value = True
        
        # Mock exception when getting document
        mock_get_doc.side_effect = Exception("Database error")
        
        result = check_student_multi_enrollment("STU-001")
        
        self.assertEqual(result, "no")
        mock_logger().error.assert_called()

    def test_update_specific_set_contacts_no_set_name(self):
        """Test update function returns error when no set name provided"""
        from glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        result = update_specific_set_contacts_with_multi_enrollment("")
        
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")

    @patch('frappe.get_doc')
    def test_update_specific_set_contacts_set_not_found(self, mock_get_doc):
        """Test update function returns error when set doesn't exist"""
        from glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        # Mock DoesNotExistError
        mock_get_doc.side_effect = frappe.DoesNotExistError()
        
        result = update_specific_set_contacts_with_multi_enrollment("NONEXISTENT")
        
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    @patch('frappe.get_doc')
    def test_update_specific_set_contacts_set_not_processed(self, mock_get_doc):
        """Test update function returns error when set status is not 'Processed'"""
        from glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        # Mock onboarding set with non-processed status
        mock_set = MagicMock()
        mock_set.status = "Draft"
        mock_set.set_name = "Test Set"
        mock_get_doc.return_value = mock_set
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST-SET")
        
        self.assertIn("error", result)
        self.assertIn("not 'Processed'", result["error"])

    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_update_specific_set_contacts_no_students(self, mock_get_doc, mock_get_all):
        """Test update function returns message when no students found"""
        from glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        # Mock processed onboarding set
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = "Test Set"
        mock_get_doc.return_value = mock_set
        
        # Mock no backend students found
        mock_get_all.return_value = []
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST-SET")
        
        self.assertIn("message", result)
        self.assertIn("No successfully processed students", result["message"])

    @patch('requests.post')
    @patch('glific_multi_enrollment_update.get_glific_auth_headers')
    @patch('glific_multi_enrollment_update.get_glific_settings')
    @patch('glific_multi_enrollment_update.check_student_multi_enrollment')
    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    def test_update_specific_set_contacts_successful_update(self, mock_get_all, mock_get_doc, 
                                                           mock_db_exists, mock_check_multi, 
                                                           mock_settings, mock_headers, mock_post):
        """Test successful update of contact with multi_enrollment field"""
        from glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        # Mock onboarding set
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = "Test Set"
        mock_get_doc_calls = [mock_set]
        
        # Mock student document
        mock_student = MagicMock()
        mock_student.glific_id = "12345"
        mock_get_doc_calls.append(mock_student)
        
        mock_get_doc.side_effect = mock_get_doc_calls
        
        # Mock backend students
        mock_get_all.return_value = [{
            "student_name": "Test Student",
            "phone": "+1234567890", 
            "student_id": "STU-001",
            "batch_skeyword": "BATCH1"
        }]
        
        # Mock student exists
        mock_db_exists.return_value = True
        
        # Mock multi enrollment check
        mock_check_multi.return_value = "yes"
        
        # Mock Glific settings
        mock_settings_obj = MagicMock()
        mock_settings_obj.api_url = "https://test.glific.com"
        mock_settings.return_value = mock_settings_obj
        
        # Mock auth headers
        mock_headers.return_value = {"Authorization": "Bearer test_token"}
        
        # Mock Glific API responses
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": "12345",
                        "name": "Test Student",
                        "phone": "+1234567890",
                        "fields": json.dumps({
                            "existing_field": {"value": "test", "type": "string"}
                        })
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
                        "id": "12345",
                        "name": "Test Student",
                        "fields": json.dumps({
                            "existing_field": {"value": "test", "type": "string"},
                            "multi_enrollment": {"value": "yes", "type": "string"}
                        })
                    },
                    "errors": []
                }
            }
        }
        
        mock_post.side_effect = [fetch_response, update_response]
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST-SET")
        
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["total_processed"], 1)

    @patch('frappe.db.rollback')
    @patch('frappe.db.commit') 
    @patch('frappe.db.begin')
    @patch('glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_run_multi_enrollment_update_for_specific_set_success(self, mock_update, mock_begin, 
                                                                mock_commit, mock_rollback):
        """Test whitelist function successful execution"""
        from glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        # Mock successful update
        mock_update.return_value = {
            "set_name": "Test Set",
            "updated": 5,
            "skipped": 0, 
            "errors": 0,
            "total_processed": 5
        }
        
        result = run_multi_enrollment_update_for_specific_set("TEST-SET")
        
        self.assertIn("Process completed", result)
        self.assertIn("Updated: 5", result)
        mock_begin.assert_called_once()
        mock_commit.assert_called_once()
        mock_rollback.assert_not_called()

    def test_run_multi_enrollment_update_no_set_name(self):
        """Test whitelist function returns error when no set name provided"""
        from glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        result = run_multi_enrollment_update_for_specific_set("")
        
        self.assertIn("Error: Backend Student Onboarding set name is required", result)

    @patch('frappe.db.rollback')
    @patch('frappe.db.commit')
    @patch('frappe.db.begin')
    @patch('glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_run_multi_enrollment_update_exception_handling(self, mock_update, mock_begin, 
                                                           mock_commit, mock_rollback):
        """Test whitelist function handles exceptions properly"""
        from glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        # Mock exception
        mock_update.side_effect = Exception("Database connection failed")
        
        result = run_multi_enrollment_update_for_specific_set("TEST-SET")
        
        self.assertIn("Error occurred:", result)
        mock_begin.assert_called_once()
        mock_rollback.assert_called_once()
        mock_commit.assert_not_called()

    @patch('frappe.get_all')
    def test_get_backend_onboarding_sets(self, mock_get_all):
        """Test getting list of processed Backend Student Onboarding sets"""
        from glific_multi_enrollment_update import get_backend_onboarding_sets
        
        # Mock return data
        mock_get_all.return_value = [
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
    @patch('glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_process_multiple_sets_simple_success(self, mock_update, mock_sleep):
        """Test processing multiple sets successfully"""
        from glific_multi_enrollment_update import process_multiple_sets_simple
        
        # Mock successful updates
        mock_update.side_effect = [
            {"updated": 5, "errors": 0, "total_processed": 5},
            {"updated": 3, "errors": 1, "total_processed": 4}
        ]
        
        result = process_multiple_sets_simple(["SET-001", "SET-002"])
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["updated"], 5)
        self.assertEqual(result[1]["updated"], 3)
        self.assertEqual(result[0]["status"], "completed")

    @patch('glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_process_multiple_sets_simple_with_error(self, mock_update):
        """Test processing multiple sets with error handling"""
        from glific_multi_enrollment_update import process_multiple_sets_simple
        
        # Mock error response
        mock_update.return_value = {"error": "Set not found"}
        
        result = process_multiple_sets_simple(["INVALID-SET"])
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "completed")

    @patch('glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_process_multiple_sets_simple_exception(self, mock_update):
        """Test processing multiple sets with exception"""
        from glific_multi_enrollment_update import process_multiple_sets_simple
        
        # Mock exception
        mock_update.side_effect = Exception("Unexpected error")
        
        result = process_multiple_sets_simple(["SET-001"])
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "error")
        self.assertIn("error", result[0])

    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_my_sets_with_list(self, mock_enqueue):
        """Test process_my_sets with list input"""
        from glific_multi_enrollment_update import process_my_sets
        
        # Mock job
        mock_job = MagicMock()
        mock_job.id = "job_123"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets(["SET-001", "SET-002"])
        
        self.assertIn("Started processing 2 sets", result)
        self.assertIn("job_123", result)
        mock_enqueue.assert_called_once()

    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_my_sets_with_string(self, mock_enqueue):
        """Test process_my_sets with comma-separated string input"""
        from glific_multi_enrollment_update import process_my_sets
        
        # Mock job
        mock_job = MagicMock()
        mock_job.id = "job_456"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets("SET-001, SET-002, SET-003")
        
        self.assertIn("Started processing 3 sets", result)
        mock_enqueue.assert_called_once()
        
        # Check that the function was called with correct parameters
        call_args = mock_enqueue.call_args
        self.assertEqual(len(call_args[1]["set_names"]), 3)


class TestGlificMultiEnrollmentIntegration(FrappeTestCase):
    """Integration tests that test the full workflow"""
    
    def setUp(self):
        """Set up integration test data"""
        # This would require actual test data in the database
        pass
    
    @unittest.skip("Integration test - requires full test environment")
    def test_full_workflow_integration(self):
        """Test the complete workflow from start to finish"""
        # This test would:
        # 1. Create actual test Backend Student Onboarding set
        # 2. Create test Student records with different enrollment scenarios
        # 3. Mock Glific API calls
        # 4. Run the update process
        # 5. Verify the results
        pass


if __name__ == '__main__':
    # Run specific test
    unittest.main()

# Additional test runner for Frappe
def run_tests():
    """Helper function to run tests in Frappe context"""
    import unittest
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestGlificMultiEnrollmentUpdate)
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)