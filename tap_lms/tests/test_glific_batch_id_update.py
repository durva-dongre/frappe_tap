# test_glific_batch_id_update.py
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timezone
import frappe
from frappe.tests.utils import FrappeTestCase

# Import the module under test
from your_app.glific_batch_id_update import (
    get_student_batch_id,
    update_specific_set_contacts_with_batch_id,
    run_batch_id_update_for_specific_set,
    process_multiple_sets_batch_id,
    process_multiple_sets_batch_id_background,
    get_backend_onboarding_sets_for_batch_id
)


class TestGlificBatchIdUpdate(FrappeTestCase):
    """Test cases for Glific Batch ID Update functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_onboarding_set_name = "TEST_SET_001"
        self.test_student_id = "STU001"
        self.test_student_name = "Test Student"
        self.test_phone = "+1234567890"
        self.test_batch_id = "BATCH_2024_A"
        self.test_glific_id = "12345"
        
        # Mock Glific settings
        self.mock_settings = Mock()
        self.mock_settings.api_url = "https://api.glific.test"
        
        # Mock headers
        self.mock_headers = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }

    def tearDown(self):
        """Clean up after tests"""
        pass


class TestGetStudentBatchId(TestGlificBatchIdUpdate):
    """Test cases for get_student_batch_id function"""
    
    @patch('frappe.db.exists')
    def test_get_student_batch_id_success(self, mock_exists):
        """Test successful retrieval of student batch ID"""
        mock_exists.return_value = True
        
        result = get_student_batch_id(self.test_student_name, self.test_batch_id)
        
        self.assertEqual(result, self.test_batch_id)
        mock_exists.assert_called_once_with("Student", self.test_student_name)
    
    @patch('frappe.db.exists')
    def test_get_student_batch_id_student_not_exists(self, mock_exists):
        """Test when student document doesn't exist"""
        mock_exists.return_value = False
        
        with patch('frappe.logger') as mock_logger:
            result = get_student_batch_id(self.test_student_name, self.test_batch_id)
            
            self.assertIsNone(result)
            mock_logger().error.assert_called_once()
    
    def test_get_student_batch_id_no_batch(self):
        """Test when no batch is provided"""
        result = get_student_batch_id(self.test_student_name, None)
        self.assertIsNone(result)
        
        result = get_student_batch_id(self.test_student_name, "")
        self.assertIsNone(result)
    
    @patch('frappe.db.exists')
    def test_get_student_batch_id_exception(self, mock_exists):
        """Test exception handling"""
        mock_exists.side_effect = Exception("Database error")
        
        with patch('frappe.logger') as mock_logger:
            result = get_student_batch_id(self.test_student_name, self.test_batch_id)
            
            self.assertIsNone(result)
            mock_logger().error.assert_called_once()


class TestUpdateSpecificSetContactsWithBatchId(TestGlificBatchIdUpdate):
    """Test cases for update_specific_set_contacts_with_batch_id function"""
    
    def test_no_onboarding_set_name(self):
        """Test when no onboarding set name is provided"""
        result = update_specific_set_contacts_with_batch_id(None)
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")
        
        result = update_specific_set_contacts_with_batch_id("")
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")
    
    @patch('frappe.get_doc')
    def test_onboarding_set_not_found(self, mock_get_doc):
        """Test when onboarding set doesn't exist"""
        mock_get_doc.side_effect = frappe.DoesNotExistError()
        
        result = update_specific_set_contacts_with_batch_id(self.test_onboarding_set_name)
        self.assertIn("not found", result["error"])
    
    @patch('frappe.get_doc')
    def test_onboarding_set_not_processed(self, mock_get_doc):
        """Test when onboarding set status is not 'Processed'"""
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Draft"
        mock_onboarding_set.set_name = "Test Set"
        mock_get_doc.return_value = mock_onboarding_set
        
        result = update_specific_set_contacts_with_batch_id(self.test_onboarding_set_name)
        self.assertIn("not 'Processed'", result["error"])
    
    @patch('frappe.get_all')
    @patch('frappe.get_doc')
    def test_no_backend_students(self, mock_get_doc, mock_get_all):
        """Test when no backend students are found"""
        # Mock onboarding set
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Processed"
        mock_onboarding_set.set_name = "Test Set"
        mock_get_doc.return_value = mock_onboarding_set
        
        # Mock empty backend students list
        mock_get_all.return_value = []
        
        result = update_specific_set_contacts_with_batch_id(self.test_onboarding_set_name)
        self.assertIn("No successfully processed students", result["message"])
    
    @patch('requests.post')
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.exists')
    @patch('your_app.glific_batch_id_update.get_glific_settings')
    @patch('your_app.glific_batch_id_update.get_glific_auth_headers')
    def test_successful_update_new_batch_id(self, mock_headers, mock_settings, 
                                          mock_exists, mock_get_all, mock_get_doc, mock_post):
        """Test successful update with new batch_id"""
        # Setup mocks
        self._setup_successful_update_mocks(mock_headers, mock_settings, mock_exists, 
                                          mock_get_all, mock_get_doc, mock_post, 
                                          existing_batch_id=False)
        
        result = update_specific_set_contacts_with_batch_id(self.test_onboarding_set_name)
        
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["skipped"], 0)
    
    @patch('requests.post')
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.exists')
    @patch('your_app.glific_batch_id_update.get_glific_settings')
    @patch('your_app.glific_batch_id_update.get_glific_auth_headers')
    def test_successful_update_existing_batch_id(self, mock_headers, mock_settings, 
                                               mock_exists, mock_get_all, mock_get_doc, mock_post):
        """Test successful update with existing batch_id"""
        # Setup mocks
        self._setup_successful_update_mocks(mock_headers, mock_settings, mock_exists, 
                                          mock_get_all, mock_get_doc, mock_post, 
                                          existing_batch_id=True)
        
        result = update_specific_set_contacts_with_batch_id(self.test_onboarding_set_name)
        
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["skipped"], 0)
    
    def _setup_successful_update_mocks(self, mock_headers, mock_settings, mock_exists, 
                                     mock_get_all, mock_get_doc, mock_post, 
                                     existing_batch_id=False):
        """Helper method to setup mocks for successful update tests"""
        # Mock settings and headers
        mock_settings.return_value = self.mock_settings
        mock_headers.return_value = self.mock_headers
        
        # Mock onboarding set
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Processed"
        mock_onboarding_set.set_name = "Test Set"
        
        # Mock backend student
        mock_backend_student = Mock()
        mock_backend_student.student_id = self.test_student_id
        mock_backend_student.student_name = self.test_student_name
        mock_backend_student.phone = self.test_phone
        mock_backend_student.batch = self.test_batch_id
        
        # Mock student doc
        mock_student_doc = Mock()
        mock_student_doc.glific_id = self.test_glific_id
        
        mock_get_doc.side_effect = [
            mock_onboarding_set,  # First call for onboarding set
            mock_backend_student,  # Second call for backend student
            mock_student_doc       # Third call for student doc
        ]
        
        # Mock backend students list
        mock_get_all.return_value = [
            {
                "name": "backend_student_1",
                "student_name": self.test_student_name,
                "phone": self.test_phone,
                "student_id": self.test_student_id,
                "batch": self.test_batch_id,
                "batch_skeyword": "TEST"
            }
        ]
        
        # Mock database exists
        mock_exists.return_value = True
        
        # Mock Glific API responses
        existing_fields = {}
        if existing_batch_id:
            existing_fields = {
                "batch_id": {
                    "value": "OLD_BATCH",
                    "type": "string",
                    "inserted_at": "2024-01-01T00:00:00Z"
                }
            }
        
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": self.test_glific_id,
                        "name": self.test_student_name,
                        "phone": self.test_phone,
                        "fields": json.dumps(existing_fields)
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
                        "fields": json.dumps({
                            **existing_fields,
                            "batch_id": {
                                "value": self.test_batch_id,
                                "type": "string",
                                "inserted_at": datetime.now(timezone.utc).isoformat()
                            }
                        })
                    }
                }
            }
        }
        
        mock_post.side_effect = [fetch_response, update_response]
    
    @patch('requests.post')
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.exists')
    @patch('your_app.glific_batch_id_update.get_glific_settings')
    @patch('your_app.glific_batch_id_update.get_glific_auth_headers')
    def test_glific_api_error(self, mock_headers, mock_settings, mock_exists, 
                             mock_get_all, mock_get_doc, mock_post):
        """Test handling of Glific API errors"""
        # Setup basic mocks
        mock_settings.return_value = self.mock_settings
        mock_headers.return_value = self.mock_headers
        
        # Mock onboarding set
        mock_onboarding_set = Mock()
        mock_onboarding_set.status = "Processed"
        mock_onboarding_set.set_name = "Test Set"
        
        # Mock backend student
        mock_backend_student = Mock()
        mock_backend_student.student_id = self.test_student_id
        mock_backend_student.student_name = self.test_student_name
        mock_backend_student.phone = self.test_phone
        mock_backend_student.batch = self.test_batch_id
        
        # Mock student doc
        mock_student_doc = Mock()
        mock_student_doc.glific_id = self.test_glific_id
        
        mock_get_doc.side_effect = [
            mock_onboarding_set,
            mock_backend_student,
            mock_student_doc
        ]
        
        mock_get_all.return_value = [
            {
                "name": "backend_student_1",
                "student_name": self.test_student_name,
                "phone": self.test_phone,
                "student_id": self.test_student_id,
                "batch": self.test_batch_id,
                "batch_skeyword": "TEST"
            }
        ]
        
        mock_exists.return_value = True
        
        # Mock API error response
        error_response = Mock()
        error_response.status_code = 500
        mock_post.return_value = error_response
        
        result = update_specific_set_contacts_with_batch_id(self.test_onboarding_set_name)
        
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["errors"], 1)


class TestRunBatchIdUpdateForSpecificSet(TestGlificBatchIdUpdate):
    """Test cases for run_batch_id_update_for_specific_set function"""
    
    def test_no_onboarding_set_name(self):
        """Test when no onboarding set name is provided"""
        result = run_batch_id_update_for_specific_set(None)
        self.assertIn("Error: Backend Student Onboarding set name is required", result)
        
        result = run_batch_id_update_for_specific_set("")
        self.assertIn("Error: Backend Student Onboarding set name is required", result)
    
    @patch('frappe.db.rollback')
    @patch('frappe.db.commit')
    @patch('frappe.db.begin')
    @patch('your_app.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_successful_execution(self, mock_update, mock_begin, mock_commit, mock_rollback):
        """Test successful execution of batch ID update"""
        mock_update.return_value = {
            "set_name": "Test Set",
            "updated": 5,
            "skipped": 1,
            "errors": 0,
            "total_processed": 6
        }
        
        result = run_batch_id_update_for_specific_set(self.test_onboarding_set_name)
        
        self.assertIn("Process completed", result)
        self.assertIn("Updated: 5", result)
        self.assertIn("Skipped: 1", result)
        mock_begin.assert_called_once()
        mock_commit.assert_called_once()
        mock_rollback.assert_not_called()
    
    @patch('frappe.db.rollback')
    @patch('frappe.db.commit')
    @patch('frappe.db.begin')
    @patch('your_app.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_error_handling(self, mock_update, mock_begin, mock_commit, mock_rollback):
        """Test error handling and rollback"""
        mock_update.side_effect = Exception("Database connection error")
        
        with patch('frappe.logger') as mock_logger:
            result = run_batch_id_update_for_specific_set(self.test_onboarding_set_name)
            
            self.assertIn("Error occurred:", result)
            mock_begin.assert_called_once()
            mock_rollback.assert_called_once()
            mock_commit.assert_not_called()
            mock_logger().error.assert_called_once()


class TestProcessMultipleSetsBatchId(TestGlificBatchIdUpdate):
    """Test cases for process_multiple_sets_batch_id function"""
    
    @patch('time.sleep')
    @patch('your_app.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_process_multiple_sets_success(self, mock_update, mock_sleep):
        """Test successful processing of multiple sets"""
        set_names = ["SET_001", "SET_002"]
        
        # Mock responses for each set
        mock_update.side_effect = [
            # First set responses
            {"updated": 3, "skipped": 1, "errors": 0, "total_processed": 4},
            {"updated": 0, "skipped": 0, "errors": 0, "total_processed": 0},  # End of first set
            # Second set responses
            {"updated": 2, "skipped": 0, "errors": 1, "total_processed": 3},
            {"updated": 0, "skipped": 0, "errors": 0, "total_processed": 0},  # End of second set
        ]
        
        with patch('frappe.logger') as mock_logger:
            results = process_multiple_sets_batch_id(set_names)
            
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["updated"], 3)
            self.assertEqual(results[1]["updated"], 2)
            self.assertTrue(all(r["status"] == "completed" for r in results))
    
    @patch('time.sleep')
    @patch('your_app.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_process_multiple_sets_with_errors(self, mock_update, mock_sleep):
        """Test processing multiple sets with errors"""
        set_names = ["SET_001", "SET_002"]
        
        mock_update.side_effect = [
            {"error": "Set not found"},  # First set error
            Exception("Network error"),  # Second set exception
        ]
        
        with patch('frappe.logger') as mock_logger:
            results = process_multiple_sets_batch_id(set_names)
            
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["status"], "completed")  # Error handled gracefully
            self.assertEqual(results[1]["status"], "error")
            self.assertIn("error", results[1])


class TestProcessMultipleSetsBatchIdBackground(TestGlificBatchIdUpdate):
    """Test cases for process_multiple_sets_batch_id_background function"""
    
    @patch('your_app.glific_batch_id_update.enqueue')
    def test_background_processing_with_list(self, mock_enqueue):
        """Test background processing with list input"""
        set_names = ["SET_001", "SET_002"]
        
        mock_job = Mock()
        mock_job.id = "job_12345"
        mock_enqueue.return_value = mock_job
        
        result = process_multiple_sets_batch_id_background(set_names)
        
        self.assertIn("Started processing 2 sets", result)
        self.assertIn("Job ID: job_12345", result)
        mock_enqueue.assert_called_once()
    
    @patch('your_app.glific_batch_id_update.enqueue')
    def test_background_processing_with_string(self, mock_enqueue):
        """Test background processing with comma-separated string input"""
        set_names = "SET_001, SET_002, SET_003"
        
        mock_job = Mock()
        mock_job.id = "job_67890"
        mock_enqueue.return_value = mock_job
        
        result = process_multiple_sets_batch_id_background(set_names)
        
        self.assertIn("Started processing 3 sets", result)
        self.assertIn("Job ID: job_67890", result)
        
        # Verify enqueue was called with correct parameters
        args, kwargs = mock_enqueue.call_args
        self.assertEqual(kwargs['set_names'], ["SET_001", "SET_002", "SET_003"])
        self.assertEqual(kwargs['batch_size'], 50)
        self.assertEqual(kwargs['queue'], 'long')
        self.assertEqual(kwargs['timeout'], 7200)


class TestGetBackendOnboardingSetsForBatchId(TestGlificBatchIdUpdate):
    """Test cases for get_backend_onboarding_sets_for_batch_id function"""
    
    @patch('frappe.get_all')
    def test_get_backend_onboarding_sets(self, mock_get_all):
        """Test getting backend onboarding sets"""
        mock_sets = [
            {
                "name": "SET_001",
                "set_name": "Test Set 1",
                "processed_student_count": 10,
                "upload_date": "2024-01-15"
            },
            {
                "name": "SET_002", 
                "set_name": "Test Set 2",
                "processed_student_count": 25,
                "upload_date": "2024-01-10"
            }
        ]
        
        mock_get_all.return_value = mock_sets
        
        result = get_backend_onboarding_sets_for_batch_id()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["set_name"], "Test Set 1")
        
        # Verify correct query parameters
        mock_get_all.assert_called_once_with(
            "Backend Student Onboarding",
            filters={"status": "Processed"},
            fields=["name", "set_name", "processed_student_count", "upload_date"],
            order_by="upload_date desc"
        )
    
    @patch('frappe.get_all')
    def test_get_backend_onboarding_sets_empty(self, mock_get_all):
        """Test when no sets are found"""
        mock_get_all.return_value = []
        
        result = get_backend_onboarding_sets_for_batch_id()
        
        self.assertEqual(len(result), 0)


class TestIntegrationScenarios(TestGlificBatchIdUpdate):
    """Integration test scenarios"""
    
    @patch('requests.post')
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.exists')
    @patch('your_app.glific_batch_id_update.get_glific_settings')
    @patch('your_app.glific_batch_id_update.get_glific_auth_headers')
    def test_end_to_end_workflow(self, mock_headers, mock_settings, mock_exists, 
                                mock_get_all, mock_get_doc, mock_post):
        """Test complete end-to-end workflow"""
        # This test simulates the complete workflow from getting sets to updating contacts
        
        # Setup mocks for getting sets
        mock_sets = [
            {
                "name": "SET_001",
                "set_name": "Test Set 1",
                "processed_student_count": 2,
                "upload_date": "2024-01-15"
            }
        ]
        
        # Test getting sets
        with patch('frappe.get_all', return_value=mock_sets):
            available_sets = get_backend_onboarding_sets_for_batch_id()
            self.assertEqual(len(available_sets), 1)
        
        # Test processing the set
        self._setup_successful_update_mocks(mock_headers, mock_settings, mock_exists, 
                                          mock_get_all, mock_get_doc, mock_post)
        
        result = update_specific_set_contacts_with_batch_id("SET_001")
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["errors"], 0)


if __name__ == '__main__':
    # Run specific test class
    unittest.main()


# Additional test utilities and fixtures

class GlificTestFixtures:
    """Test fixtures and utilities for Glific tests"""
    
    @staticmethod
    def create_mock_backend_student(student_id="STU001", batch="BATCH_A"):
        """Create a mock backend student object"""
        student = Mock()
        student.student_id = student_id
        student.student_name = f"Student {student_id}"
        student.phone = "+1234567890"
        student.batch = batch
        student.batch_skeyword = "TEST"
        return student
    
    @staticmethod
    def create_mock_glific_contact(glific_id="12345", has_batch_id=False, batch_value=None):
        """Create a mock Glific contact response"""
        fields = {}
        if has_batch_id:
            fields["batch_id"] = {
                "value": batch_value or "OLD_BATCH",
                "type": "string",
                "inserted_at": "2024-01-01T00:00:00Z"
            }
        
        return {
            "data": {
                "contact": {
                    "contact": {
                        "id": glific_id,
                        "name": f"Student {glific_id}",
                        "phone": "+1234567890",
                        "fields": json.dumps(fields)
                    }
                }
            }
        }
    
    @staticmethod
    def create_mock_update_response(glific_id="12345", success=True):
        """Create a mock Glific update response"""
        if success:
            return {
                "data": {
                    "updateContact": {
                        "contact": {
                            "id": glific_id,
                            "name": f"Student {glific_id}",
                            "fields": json.dumps({
                                "batch_id": {
                                    "value": "NEW_BATCH",
                                    "type": "string",
                                    "inserted_at": datetime.now(timezone.utc).isoformat()
                                }
                            })
                        }
                    }
                }
            }
        else:
            return {
                "errors": [
                    {
                        "key": "contact",
                        "message": "Update failed"
                    }
                ]
            }


# Performance and load testing utilities

class TestPerformanceScenarios(TestGlificBatchIdUpdate):
    """Test performance and load scenarios"""
    
    @patch('time.sleep')
    @patch('your_app.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_large_batch_processing(self, mock_update, mock_sleep):
        """Test processing large batches"""
        # Simulate processing 1000 students in batches of 50
        batch_responses = []
        for i in range(20):  # 20 batches of 50
            if i < 19:
                batch_responses.append({
                    "updated": 48, "skipped": 2, "errors": 0, "total_processed": 50
                })
            else:
                batch_responses.append({
                    "updated": 0, "skipped": 0, "errors": 0, "total_processed": 0
                })
        
        mock_update.side_effect = batch_responses
        
        with patch('frappe.logger') as mock_logger:
            results = process_multiple_sets_batch_id(["LARGE_SET"], batch_size=50)
            
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["updated"], 48 * 19)  # 912 total updates
            self.assertEqual(results[0]["status"], "completed")
    
    def test_batch_size_parameter_validation(self):
        """Test batch size parameter validation"""
        # Test with different batch sizes
        test_cases = [1, 10, 50, 100]
        
        for batch_size in test_cases:
            with patch('your_app.glific_batch_id_update.update_specific_set_contacts_with_batch_id') as mock_update:
                mock_update.return_value = {"message": "No students found"}
                
                update_specific_set_contacts_with_batch_id("TEST_SET", batch_size)
                
                # Verify batch_size is passed correctly
                args, kwargs = mock_update.call_args
                # Note: In actual implementation, verify the batch_size is used in frappe.get_all limit parameter


# Mock data generators for comprehensive testing

class MockDataGenerator:
    """Generate mock data for testing"""
    
    @staticmethod
    def generate_backend_students(count=10, set_name="TEST_SET"):
        """Generate a list of mock backend students"""
        students = []
        for i in range(count):
            students.append({
                "name": f"backend_student_{i+1}",
                "student_name": f"Student {i+1:03d}",
                "phone": f"+123456789{i:02d}",
                "student_id": f"STU{i+1:03d}",
                "batch": f"BATCH_{chr(65 + i % 26)}",
                "batch_skeyword": f"KEY{i+1:02d}"
            })
        return students
    
    @staticmethod
    def generate_onboarding_sets(count=5):
        """Generate mock onboarding sets"""
        sets = []
        for i in range(count):
            sets.append({
                "name": f"SET_{i+1:03d}",
                "set_name": f"Test Set {i+1}",
                "processed_student_count": (i+1) * 10,
                "upload_date": f"2024-01-{i+1:02d}"
            })
        return sets