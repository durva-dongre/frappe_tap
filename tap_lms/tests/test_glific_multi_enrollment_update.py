import unittest
import frappe
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timezone

# Proper Frappe test imports
from frappe.tests.utils import FrappeTestCase


class TestCheckStudentMultiEnrollment(FrappeTestCase):
    """Test cases for check_student_multi_enrollment function"""
    
    def setUp(self):
        """Setup test data"""
        super().setUp()
        
    def tearDown(self):
        """Cleanup test data"""
        super().tearDown()
    
    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    def test_student_with_multiple_enrollments(self, mock_get_doc, mock_exists):
        """Test student with multiple enrollments returns 'yes'"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
        
        mock_exists.return_value = True
        mock_student = Mock()
        mock_student.enrollment = [{'enrollment_id': 1}, {'enrollment_id': 2}]
        mock_get_doc.return_value = mock_student
        
        result = check_student_multi_enrollment("STUDENT001")
        
        self.assertEqual(result, "yes")
        mock_exists.assert_called_once_with("Student", "STUDENT001")
        mock_get_doc.assert_called_once_with("Student", "STUDENT001")
    
    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    def test_student_with_single_enrollment(self, mock_get_doc, mock_exists):
        """Test student with single enrollment returns 'no'"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
        
        mock_exists.return_value = True
        mock_student = Mock()
        mock_student.enrollment = [{'enrollment_id': 1}]
        mock_get_doc.return_value = mock_student
        
        result = check_student_multi_enrollment("STUDENT001")
        
        self.assertEqual(result, "no")
    
    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    def test_student_with_no_enrollments(self, mock_get_doc, mock_exists):
        """Test student with no enrollments returns 'no'"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
        
        mock_exists.return_value = True
        mock_student = Mock()
        mock_student.enrollment = []
        mock_get_doc.return_value = mock_student
        
        result = check_student_multi_enrollment("STUDENT001")
        
        self.assertEqual(result, "no")
    
    @patch('frappe.db.exists')
    def test_student_not_found(self, mock_exists):
        """Test when student document doesn't exist"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
        
        mock_exists.return_value = False
        
        result = check_student_multi_enrollment("NONEXISTENT")
        
        self.assertEqual(result, "no")
    
    @patch('frappe.db.exists')
    @patch('frappe.get_doc')
    def test_exception_handling(self, mock_get_doc, mock_exists):
        """Test exception handling returns 'no'"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import check_student_multi_enrollment
        
        mock_exists.return_value = True
        mock_get_doc.side_effect = Exception("Database error")
        
        result = check_student_multi_enrollment("STUDENT001")
        
        self.assertEqual(result, "no")


class TestUpdateSpecificSetContactsWithMultiEnrollment(FrappeTestCase):
    """Test cases for update_specific_set_contacts_with_multi_enrollment function"""
    
    def setUp(self):
        """Setup test data"""
        super().setUp()
        
    def tearDown(self):
        """Cleanup test data"""
        super().tearDown()
    
    def test_invalid_onboarding_set_name(self):
        """Test with invalid onboarding set name"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        result = update_specific_set_contacts_with_multi_enrollment("")
        
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")
    
    @patch('frappe.get_doc')
    def test_onboarding_set_not_found(self, mock_get_doc):
        """Test when onboarding set doesn't exist"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        mock_get_doc.side_effect = frappe.DoesNotExistError()
        
        result = update_specific_set_contacts_with_multi_enrollment("INVALID_SET")
        
        self.assertIn("not found", result["error"])
    
    @patch('frappe.get_doc')
    def test_onboarding_set_not_processed(self, mock_get_doc):
        """Test when onboarding set status is not 'Processed'"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        mock_set = Mock()
        mock_set.status = "Draft"
        mock_set.set_name = "TEST_SET"
        mock_get_doc.return_value = mock_set
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertIn("status is 'Draft', not 'Processed'", result["error"])
    
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    def test_no_students_found(self, mock_get_all, mock_get_doc):
        """Test when no successfully processed students found"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        mock_set = Mock()
        mock_set.status = "Processed"
        mock_set.set_name = "TEST_SET"
        mock_get_doc.return_value = mock_set
        mock_get_all.return_value = []
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertIn("No successfully processed students found", result["message"])
    
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.exists')
    @patch('requests.post')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_settings')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment')
    def test_successful_contact_update(self, mock_check_enrollment, mock_headers, mock_settings,
                                     mock_requests, mock_db_exists, mock_get_all, mock_get_doc):
        """Test successful contact update"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        # Setup mocks
        mock_set = Mock()
        mock_set.status = "Processed"
        mock_set.set_name = "TEST_SET"
        mock_get_doc.side_effect = [
            mock_set,  # First call for onboarding set
            Mock(glific_id="123")  # Second call for student doc
        ]
        
        mock_get_all.return_value = [{
            "student_name": "John Doe",
            "phone": "1234567890",
            "student_id": "STUDENT001",
            "batch_skeyword": "batch1"
        }]
        
        mock_db_exists.return_value = True
        mock_check_enrollment.return_value = "yes"
        
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
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["total_processed"], 1)
    
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.exists')
    def test_student_without_glific_id(self, mock_db_exists, mock_get_all, mock_get_doc):
        """Test handling student without Glific ID"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        mock_set = Mock()
        mock_set.status = "Processed"
        mock_set.set_name = "TEST_SET"
        mock_get_doc.side_effect = [
            mock_set,  # First call for onboarding set
            Mock(glific_id=None)  # Second call for student doc
        ]
        
        mock_get_all.return_value = [{
            "student_name": "John Doe",
            "phone": "1234567890",
            "student_id": "STUDENT001",
            "batch_skeyword": "batch1"
        }]
        
        mock_db_exists.return_value = True
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["updated"], 0)


class TestRunMultiEnrollmentUpdateForSpecificSet(FrappeTestCase):
    """Test cases for run_multi_enrollment_update_for_specific_set function"""
    
    def setUp(self):
        """Setup test data"""
        super().setUp()
        
    def tearDown(self):
        """Cleanup test data"""
        super().tearDown()
    
    def test_missing_onboarding_set_name(self):
        """Test with missing onboarding set name"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        result = run_multi_enrollment_update_for_specific_set("")
        
        self.assertIn("Backend Student Onboarding set name is required", result)
    
    @patch('frappe.db.begin')
    @patch('frappe.db.commit')
    @patch('frappe.db.rollback')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_successful_execution(self, mock_update, mock_rollback, mock_commit, mock_begin):
        """Test successful execution"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        mock_update.return_value = {
            "set_name": "TEST_SET",
            "updated": 5,
            "skipped": 0,
            "errors": 0,
            "total_processed": 5
        }
        
        result = run_multi_enrollment_update_for_specific_set("TEST_SET")
        
        self.assertIn("Process completed", result)
        self.assertIn("Updated: 5", result)
        mock_begin.assert_called_once()
        mock_commit.assert_called_once()
        mock_rollback.assert_not_called()
    
    @patch('frappe.db.begin')
    @patch('frappe.db.commit')
    @patch('frappe.db.rollback')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_exception_handling(self, mock_update, mock_rollback, mock_commit, mock_begin):
        """Test exception handling with rollback"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import run_multi_enrollment_update_for_specific_set
        
        mock_update.side_effect = Exception("Database error")
        
        result = run_multi_enrollment_update_for_specific_set("TEST_SET")
        
        self.assertIn("Error occurred", result)
        mock_begin.assert_called_once()
        mock_rollback.assert_called_once()
        mock_commit.assert_not_called()


class TestGetBackendOnboardingSets(FrappeTestCase):
    """Test cases for get_backend_onboarding_sets function"""
    
    def setUp(self):
        """Setup test data"""
        super().setUp()
        
    def tearDown(self):
        """Cleanup test data"""
        super().tearDown()
    
    @patch('frappe.get_all')
    def test_get_processed_sets(self, mock_get_all):
        """Test getting processed onboarding sets"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import get_backend_onboarding_sets
        
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
        
        result = get_backend_onboarding_sets()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "SET001")
        mock_get_all.assert_called_once_with(
            "Backend Student Onboarding",
            filters={"status": "Processed"},
            fields=["name", "set_name", "processed_student_count", "upload_date"],
            order_by="upload_date desc"
        )


class TestProcessMySets(FrappeTestCase):
    """Test cases for process_my_sets function"""
    
    def setUp(self):
        """Setup test data"""
        super().setUp()
        
    def tearDown(self):
        """Cleanup test data"""
        super().tearDown()
    
    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_sets_with_list(self, mock_enqueue):
        """Test processing sets with list input"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import process_my_sets
        
        mock_job = Mock()
        mock_job.id = "job123"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets(["SET001", "SET002"])
        
        self.assertIn("Started processing 2 sets", result)
        self.assertIn("Job ID: job123", result)
        mock_enqueue.assert_called_once()
    
    @patch('frappe.utils.background_jobs.enqueue')
    def test_process_sets_with_string(self, mock_enqueue):
        """Test processing sets with comma-separated string"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import process_my_sets
        
        mock_job = Mock()
        mock_job.id = "job456"
        mock_enqueue.return_value = mock_job
        
        result = process_my_sets("SET001, SET002, SET003")
        
        self.assertIn("Started processing 3 sets", result)
        self.assertIn("Job ID: job456", result)


class TestIntegrationScenarios(FrappeTestCase):
    """Integration test scenarios"""
    
    def setUp(self):
        """Setup test data"""
        super().setUp()
        
    def tearDown(self):
        """Cleanup test data"""
        super().tearDown()
    
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.exists')
    @patch('requests.post')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_settings')
    @patch('tap_lms.tap_lms.glific_integration.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment')
    def test_glific_api_error_handling(self, mock_check_enrollment, mock_headers, mock_settings,
                                     mock_requests, mock_db_exists, mock_get_all, mock_get_doc):
        """Test Glific API error handling"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import update_specific_set_contacts_with_multi_enrollment
        
        # Setup mocks
        mock_set = Mock()
        mock_set.status = "Processed"
        mock_set.set_name = "TEST_SET"
        mock_get_doc.side_effect = [
            mock_set,
            Mock(glific_id="123")
        ]
        
        mock_get_all.return_value = [{
            "student_name": "John Doe",
            "phone": "1234567890", 
            "student_id": "STUDENT001",
            "batch_skeyword": "batch1"
        }]
        
        mock_db_exists.return_value = True
        mock_check_enrollment.return_value = "yes"
        
        mock_settings.return_value = Mock(api_url="https://api.glific.com")
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Mock API error response
        mock_error_response = Mock()
        mock_error_response.status_code = 500
        mock_requests.return_value = mock_error_response
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["updated"], 0)


class TestEdgeCases(FrappeTestCase):
    """Test edge cases and boundary conditions"""
    
    def setUp(self):
        """Setup test data"""
        super().setUp()
        
    def tearDown(self):
        """Cleanup test data"""
        super().tearDown()
    
    def test_empty_set_names_list(self):
        """Test with empty set names list"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import process_my_sets
        
        with patch('frappe.utils.background_jobs.enqueue') as mock_enqueue:
            mock_job = Mock()
            mock_job.id = "job123"
            mock_enqueue.return_value = mock_job
            
            result = process_my_sets([])
            self.assertIn("Started processing 0 sets", result)
    
    def test_whitespace_in_set_names(self):
        """Test with whitespace in set names"""
        from tap_lms.tap_lms.glific_multi_enrollment_update import process_my_sets
        
        with patch('frappe.utils.background_jobs.enqueue') as mock_enqueue:
            mock_job = Mock()
            mock_job.id = "job123"
            mock_enqueue.return_value = mock_job
            
            result = process_my_sets(" SET001 , SET002 , SET003 ")
            
            # Verify that whitespace is stripped
            call_args = mock_enqueue.call_args
            set_names = call_args[1]['set_names']  # keyword argument
            self.assertEqual(set_names, ["SET001", "SET002", "SET003"])


# Test runner compatible with Frappe
def run_tests():
    """Run all tests"""
    import unittest
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    test_classes = [
        TestCheckStudentMultiEnrollment,
        TestUpdateSpecificSetContactsWithMultiEnrollment,
        TestRunMultiEnrollmentUpdateForSpecificSet,
        TestGetBackendOnboardingSets,
        TestProcessMySets,
        TestIntegrationScenarios,
        TestEdgeCases
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    run_tests()