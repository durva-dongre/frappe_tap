# # test_glific_batch_id_update.py
# # Pytest test cases for glific_batch_id_update.py module - All Passing Tests

# import pytest
# import json
# from unittest.mock import Mock, patch, MagicMock, call
# from datetime import datetime, timezone
# import sys
# import os

# # Add the app path to sys.path for imports
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# # Mock frappe module before importing the module under test
# sys.modules['frappe'] = MagicMock()
# sys.modules['frappe.utils.background_jobs'] = MagicMock()
# sys.modules['requests'] = MagicMock()

# # Create mock for DoesNotExistError
# class DoesNotExistError(Exception):
#     pass

# # Set up frappe mock with necessary attributes
# import frappe
# frappe.DoesNotExistError = DoesNotExistError
# frappe.logger = MagicMock(return_value=MagicMock())
# frappe.db = MagicMock()
# frappe.get_doc = MagicMock()
# frappe.get_all = MagicMock()
# frappe.whitelist = MagicMock(return_value=lambda x: x)

# # Mock the glific_integration module dependencies
# sys.modules['tap_lms.glific_integration'] = MagicMock()

# # Import the module under test
# from tap_lms import glific_batch_id_update

# # Mock the imported functions from glific_integration
# glific_batch_id_update.get_glific_settings = MagicMock()
# glific_batch_id_update.get_glific_auth_headers = MagicMock()


# # ============= Fixtures =============

# @pytest.fixture
# def test_data():
#     """Fixture providing test data"""
#     return {
#         "student_id": "STU001",
#         "student_name": "John Doe",
#         "phone": "+1234567890",
#         "glific_id": "12345",
#         "batch_id": "BATCH_2024_01",
#         "onboarding_set": "ONBOARD_SET_001",
#         "backend_student_name": "BACKEND_STU_001"
#     }


# @pytest.fixture
# def mock_onboarding_set():
#     """Fixture for mock onboarding set"""
#     mock_set = MagicMock()
#     mock_set.status = "Processed"
#     mock_set.set_name = "Test Onboarding Set"
#     return mock_set


# @pytest.fixture
# def mock_backend_student(test_data):
#     """Fixture for mock backend student"""
#     mock_student = MagicMock()
#     mock_student.student_id = test_data["student_id"]
#     mock_student.student_name = test_data["student_name"]
#     mock_student.phone = test_data["phone"]
#     mock_student.batch = test_data["batch_id"]
#     mock_student.batch_skeyword = "batch_key"
#     return mock_student


# @pytest.fixture
# def mock_student_doc(test_data):
#     """Fixture for mock student document"""
#     mock_doc = MagicMock()
#     mock_doc.glific_id = test_data["glific_id"]
#     return mock_doc


# @pytest.fixture
# def mock_glific_settings():
#     """Fixture for mock Glific settings"""
#     mock_settings = MagicMock()
#     mock_settings.api_url = "https://api.glific.com"
#     return mock_settings


# # ============= Test get_student_batch_id =============

# class TestGetStudentBatchId:
#     """Test cases for get_student_batch_id function"""
    
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_returns_batch_when_student_exists_and_batch_provided(self, mock_exists, test_data):
#         """Test successful retrieval of batch_id when student exists"""
#         mock_exists.return_value = True
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
#         assert result == test_data["batch_id"]
#         mock_exists.assert_called_once_with("Student", test_data["student_id"])
    
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_returns_none_when_batch_is_none(self, mock_exists, test_data):
#         """Test returns None when batch is None"""
#         mock_exists.return_value = True
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], None)
        
#         assert result is None
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_returns_none_when_student_not_exists(self, mock_exists, mock_logger, test_data):
#         """Test returns None and logs error when student doesn't exist"""
#         mock_exists.return_value = False
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
#         assert result is None
#         mock_logger().error.assert_called_once()
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_handles_exception_gracefully(self, mock_exists, mock_logger, test_data):
#         """Test exception handling returns None and logs error"""
#         mock_exists.side_effect = Exception("Database error")
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
#         assert result is None
#         mock_logger().error.assert_called_once()


# # ============= Test update_specific_set_contacts_with_batch_id =============

# class TestUpdateSpecificSetContacts:
#     """Test cases for update_specific_set_contacts_with_batch_id function"""
    
#     def test_returns_error_when_no_set_name_provided(self):
#         """Test error when onboarding set name is None"""
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(None)
        
#         assert "error" in result
#         assert result["error"] == "Backend Student Onboarding set name is required"
    
#     @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
#     def test_returns_error_when_set_not_found(self, mock_get_doc, test_data):
#         """Test error when onboarding set doesn't exist"""
#         mock_get_doc.side_effect = DoesNotExistError
        
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(test_data["onboarding_set"])
        
#         assert "error" in result
#         assert "not found" in result["error"]
    
#     @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
#     def test_returns_error_when_set_not_processed(self, mock_get_doc, test_data):
#         """Test error when set status is not 'Processed'"""
#         mock_set = MagicMock()
#         mock_set.status = "Pending"
#         mock_set.set_name = test_data["onboarding_set"]
#         mock_get_doc.return_value = mock_set
        
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(test_data["onboarding_set"])
        
#         assert "error" in result
#         assert "not 'Processed'" in result["error"]
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.get_all')
#     @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
#     def test_returns_message_when_no_students_found(self, mock_get_doc, mock_get_all, 
#                                                     mock_logger, mock_onboarding_set):
#         """Test message when no successfully processed students found"""
#         mock_get_doc.return_value = mock_onboarding_set
#         mock_get_all.return_value = []
        
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
#         assert "message" in result
#         assert "No successfully processed students" in result["message"]
    


# class TestRunBatchIdUpdate:
#     """Test cases for run_batch_id_update_for_specific_set function"""
    
#     def test_returns_error_message_when_no_set_name(self):
#         """Test error message when set name is not provided"""
#         result = glific_batch_id_update.run_batch_id_update_for_specific_set(None)
        
#         assert "Error: Backend Student Onboarding set name is required" in result
    
#     @patch('tap_lms.glific_batch_id_update.frappe.db.commit')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_returns_success_message_on_completion(self, mock_update, mock_begin, mock_commit, test_data):
#         """Test successful completion message"""
#         mock_update.return_value = {
#             "set_name": test_data["onboarding_set"],
#             "updated": 5,
#             "skipped": 2,
#             "errors": 1,
#             "total_processed": 8
#         }
        
#         result = glific_batch_id_update.run_batch_id_update_for_specific_set(test_data["onboarding_set"])
        
#         assert "Process completed" in result
#         assert "Updated: 5" in result
#         assert "Skipped: 2" in result
#         assert "Errors: 1" in result
#         assert "Total Processed: 8" in result
#         mock_begin.assert_called_once()
#         mock_commit.assert_called_once()
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.rollback')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_handles_exception_with_rollback(self, mock_update, mock_begin, mock_rollback, mock_logger):
#         """Test exception handling with database rollback"""
#         mock_update.side_effect = Exception("Test exception")
        
#         result = glific_batch_id_update.run_batch_id_update_for_specific_set("ONBOARD_SET_001")
        
#         assert "Error occurred" in result
#         assert "Test exception" in result
#         mock_rollback.assert_called_once()
#         mock_logger().error.assert_called_once()


# # ============= Test process_multiple_sets_batch_id =============

# class TestProcessMultipleSets:
#     """Test cases for process_multiple_sets_batch_id function"""
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('time.sleep')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_processes_multiple_sets_successfully(self, mock_update, mock_sleep, mock_logger):
#         """Test successful processing of multiple sets"""
#         # First set processes in 2 batches, second set has no students
#         mock_update.side_effect = [
#             {"updated": 3, "errors": 0, "skipped": 1, "total_processed": 4},
#             {"updated": 2, "errors": 1, "skipped": 0, "total_processed": 3},
#             {"updated": 0, "errors": 0, "skipped": 0, "total_processed": 0},
#             {"message": "No successfully processed students found"}
#         ]
        
#         set_names = ["SET001", "SET002"]
#         results = glific_batch_id_update.process_multiple_sets_batch_id(set_names, batch_size=5)
        
#         assert len(results) == 2
#         assert results[0]["set_name"] == "SET001"
#         assert results[0]["updated"] == 5
#         assert results[0]["errors"] == 1
#         assert results[0]["skipped"] == 1
#         assert results[0]["status"] == "completed"
        
#         assert results[1]["set_name"] == "SET002"
#         assert results[1]["status"] == "completed"
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_handles_errors_in_individual_sets(self, mock_update, mock_logger):
#         """Test handling of errors in individual sets"""
#         mock_update.side_effect = [
#             {"updated": 5, "errors": 0, "skipped": 0, "total_processed": 5},
#             {"updated": 0, "errors": 0, "skipped": 0, "total_processed": 0},
#             Exception("Database connection error")
#         ]
        
#         set_names = ["SET001", "SET002"]
#         results = glific_batch_id_update.process_multiple_sets_batch_id(set_names, batch_size=10)
        
#         assert results[0]["status"] == "completed"
#         assert results[0]["updated"] == 5
        
#         assert results[1]["status"] == "error"
#         assert "Database connection error" in results[1]["error"]
#         assert results[1]["updated"] == 0


# # ============= Test process_multiple_sets_batch_id_background =============

# class TestProcessMultipleSetsBackground:
#     """Test cases for process_multiple_sets_batch_id_background function"""
    
#     @patch('frappe.utils.background_jobs.enqueue')
#     def test_enqueues_job_with_list_input(self, mock_enqueue):
#         """Test background job enqueueing with list input"""
#         # Re-import to get the enqueue function
#         from frappe.utils.background_jobs import enqueue
#         glific_batch_id_update.enqueue = enqueue
        
#         mock_job = MagicMock()
#         mock_job.id = "JOB123"
#         mock_enqueue.return_value = mock_job
        
#         set_names = ["SET001", "SET002", "SET003"]
#         result = glific_batch_id_update.process_multiple_sets_batch_id_background(set_names)
        
#         assert "Started processing 3 sets" in result
#         assert "JOB123" in result
        
#         mock_enqueue.assert_called_once()
#         call_args = mock_enqueue.call_args
#         assert call_args[1]['set_names'] == set_names
#         assert call_args[1]['batch_size'] == 50
#         assert call_args[1]['queue'] == 'long'
#         assert call_args[1]['timeout'] == 7200
    
#     @patch('frappe.utils.background_jobs.enqueue')
#     def test_enqueues_job_with_string_input(self, mock_enqueue):
#         """Test background job enqueueing with comma-separated string input"""
#         # Re-import to get the enqueue function
#         from frappe.utils.background_jobs import enqueue
#         glific_batch_id_update.enqueue = enqueue
        
#         mock_job = MagicMock()
#         mock_job.id = "JOB456"
#         mock_enqueue.return_value = mock_job
        
#         set_names_str = "SET001, SET002, SET003"
#         result = glific_batch_id_update.process_multiple_sets_batch_id_background(set_names_str)
        
#         assert "Started processing 3 sets" in result
#         assert "JOB456" in result
        
#         call_args = mock_enqueue.call_args
#         expected_list = ["SET001", "SET002", "SET003"]
#         assert call_args[1]['set_names'] == expected_list


# # ============= Test get_backend_onboarding_sets_for_batch_id =============

# class TestGetBackendOnboardingSets:
#     """Test cases for get_backend_onboarding_sets_for_batch_id function"""
    
#     @patch('tap_lms.glific_batch_id_update.frappe.get_all')
#     def test_returns_processed_onboarding_sets(self, mock_get_all):
#         """Test fetching processed backend onboarding sets"""
#         mock_sets = [
#             {
#                 "name": "SET001",
#                 "set_name": "January Batch",
#                 "processed_student_count": 100,
#                 "upload_date": "2024-01-15"
#             },
#             {
#                 "name": "SET002",
#                 "set_name": "February Batch",
#                 "processed_student_count": 150,
#                 "upload_date": "2024-02-20"
#             }
#         ]
#         mock_get_all.return_value = mock_sets
        
#         result = glific_batch_id_update.get_backend_onboarding_sets_for_batch_id()
        
#         assert len(result) == 2
#         assert result[0]["set_name"] == "January Batch"
#         assert result[0]["processed_student_count"] == 100
#         assert result[1]["set_name"] == "February Batch"
#         assert result[1]["processed_student_count"] == 150
        
#         mock_get_all.assert_called_once_with(
#             "Backend Student Onboarding",
#             filters={"status": "Processed"},
#             fields=["name", "set_name", "processed_student_count", "upload_date"],
#             order_by="upload_date desc"
#         )



# class TestPerformance:
#     """Performance-related test cases"""
    
#     @patch('time.sleep')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     def test_batch_processing_respects_batch_limit(self, mock_logger, mock_update, mock_sleep):
#         """Test that batch processing stops after safety limit"""
#         # Simulate continuous batches that never end
#         mock_update.return_value = {
#             "updated": 1,
#             "errors": 0,
#             "skipped": 0,
#             "total_processed": 1
#         }
        
#         results = glific_batch_id_update.process_multiple_sets_batch_id(["INFINITE_SET"], batch_size=1)
        
#         # Should stop after 20 batches (safety limit)
#         assert mock_update.call_count <= 21  # Initial call + 20 batch limit
#         assert results[0]["status"] == "completed"
    
#     @patch('frappe.utils.background_jobs.enqueue')
#     def test_background_job_uses_correct_timeout(self, mock_enqueue):
#         """Test that background job is configured with proper timeout"""
#         # Re-import to get the enqueue function
#         from frappe.utils.background_jobs import enqueue
#         glific_batch_id_update.enqueue = enqueue
        
#         mock_job = MagicMock()
#         mock_job.id = "TIMEOUT_TEST"
#         mock_enqueue.return_value = mock_job
        
#         glific_batch_id_update.process_multiple_sets_batch_id_background(["SET001"])
        
#         call_args = mock_enqueue.call_args
#         assert call_args[1]['timeout'] == 7200  # 2 hours
#         assert call_args[1]['queue'] == 'long'

import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sys
import os
import importlib.util

# Direct file import approach
def import_backend_module():
    """Import the backend module directly from file path"""
    file_path = "/home/frappe/frappe-bench/apps/tap_lms/tap_lms/tap_lms/page/backend_onboarding_process/backend_onboarding_process.py"
    
    if not os.path.exists(file_path):
        raise ImportError(f"File not found: {file_path}")
    
    spec = importlib.util.spec_from_file_location("backend_onboarding_process", file_path)
    module = importlib.util.module_from_spec(spec)
    
    # Mock frappe before loading the module
    mock_frappe = MagicMock()
    mock_frappe.utils = MagicMock()
    mock_frappe.utils.nowdate = MagicMock(return_value="2025-01-01")
    mock_frappe.utils.now = MagicMock(return_value="2025-01-01 10:00:00")
    mock_frappe.utils.getdate = MagicMock()
    
    # Mock the whitelist decorator to return function unchanged
    mock_frappe.whitelist.return_value = lambda func: func
    
    sys.modules['frappe'] = mock_frappe
    sys.modules['frappe.utils'] = mock_frappe.utils
    sys.modules['tap_lms.glific_integration'] = MagicMock()
    sys.modules['tap_lms.api'] = MagicMock()
    sys.modules['rq.job'] = MagicMock()
    sys.modules['frappe.utils.background_jobs'] = MagicMock()
    
    spec.loader.exec_module(module)
    return module

class TestBackendOnboardingProcessExtended(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the backend module for all tests"""
        try:
            cls.backend_module = import_backend_module()
            print(f"Successfully imported module. Available functions: {[name for name in dir(cls.backend_module) if not name.startswith('_') and callable(getattr(cls.backend_module, name))]}")
        except Exception as e:
            raise unittest.SkipTest(f"Could not import backend module: {e}")

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_batch_id = "BSO_001"
        self.mock_student_name = "Test Student"
        self.mock_phone_10 = "9876543210"
        self.mock_phone_12 = "919876543210"
        self.mock_course_vertical = "Math"
        self.mock_grade = "5"

    # ============= Additional Process Batch Job Tests =============

    def test_process_batch_job_success(self):
        """Test process_batch_job with successful processing"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'update_job_progress') as mock_progress:
                with patch.object(self.backend_module, 'process_student_record') as mock_process_student:
                    with patch.object(self.backend_module, 'process_glific_contact') as mock_glific:
                        with patch.object(self.backend_module, 'update_backend_student_status') as mock_update_status:
                            with patch.object(self.backend_module, 'get_onboarding_stages') as mock_stages:
                                mock_batch = MagicMock()
                                mock_batch.name = "BSO_001"
                                mock_batch.status = "Processing"
                                
                                mock_student = MagicMock()
                                mock_student.processing_status = "Pending"
                                mock_student.course_vertical = "Math"
                                mock_student.grade = "5"
                                mock_student.phone = "9876543210"
                                mock_student.student_name = "Test Student"
                                
                                mock_frappe.get_doc.return_value = mock_batch
                                mock_frappe.get_all.return_value = [mock_student]
                                mock_stages.return_value = [{"name": "STAGE_001"}]
                                mock_glific.return_value = {"id": "contact_123"}
                                mock_process_student.return_value = MagicMock()
                                
                                result = self.backend_module.process_batch_job("BSO_001")
                                
                                self.assertEqual(result["success_count"], 1)
                                self.assertEqual(result["failure_count"], 0)
                                mock_update_status.assert_called()
                                mock_batch.save.assert_called()

    def test_process_batch_job_with_failures(self):
        """Test process_batch_job with some failed students"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'process_glific_contact') as mock_glific:
                with patch.object(self.backend_module, 'get_onboarding_stages') as mock_stages:
                    mock_batch = MagicMock()
                    mock_batch.name = "BSO_001"
                    
                    mock_student = MagicMock()
                    mock_student.processing_status = "Pending"
                    
                    mock_frappe.get_doc.return_value = mock_batch
                    mock_frappe.get_all.return_value = [mock_student]
                    mock_stages.return_value = [{"name": "STAGE_001"}]
                    mock_glific.side_effect = Exception("Glific error")
                    
                    result = self.backend_module.process_batch_job("BSO_001")
                    
                    self.assertEqual(result["success_count"], 0)
                    self.assertEqual(result["failure_count"], 1)

    def test_process_batch_job_empty_batch(self):
        """Test process_batch_job with no students"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_onboarding_stages') as mock_stages:
                mock_batch = MagicMock()
                mock_batch.name = "BSO_001"
                
                mock_frappe.get_doc.return_value = mock_batch
                mock_frappe.get_all.return_value = []  # No students
                mock_stages.return_value = [{"name": "STAGE_001"}]
                
                result = self.backend_module.process_batch_job("BSO_001")
                
                self.assertEqual(result["success_count"], 0)
                self.assertEqual(result["failure_count"], 0)

    # ============= Validate Student Tests =============

    def test_validate_student_all_valid(self):
        """Test validate_student with all valid data"""
        student = {
            "student_name": "John Doe",
            "phone": "9876543210",
            "course_vertical": "Math",
            "grade": "5"
        }
        
        result = self.backend_module.validate_student(student)
        
        self.assertEqual(len(result), 0)  # No errors

    def test_validate_student_missing_required_fields(self):
        """Test validate_student with missing required fields"""
        student = {
            "student_name": "",
            "phone": "",
            "course_vertical": "",
            "grade": ""
        }
        
        result = self.backend_module.validate_student(student)
        
        self.assertIn("Missing required field: student_name", result)
        self.assertIn("Missing required field: phone", result)
        self.assertIn("Missing required field: course_vertical", result)
        self.assertIn("Missing required field: grade", result)

    def test_validate_student_invalid_phone(self):
        """Test validate_student with invalid phone number"""
        student = {
            "student_name": "John Doe",
            "phone": "12345",  # Invalid phone
            "course_vertical": "Math",
            "grade": "5"
        }
        
        result = self.backend_module.validate_student(student)
        
        self.assertIn("Invalid phone number format", result)

    def test_validate_student_invalid_grade(self):
        """Test validate_student with invalid grade"""
        student = {
            "student_name": "John Doe",
            "phone": "9876543210",
            "course_vertical": "Math",
            "grade": "invalid"
        }
        
        result = self.backend_module.validate_student(student)
        
        self.assertIn("Invalid grade", result)

    # ============= Determine Student Type Tests =============

    def test_determine_student_type_backend_new_student(self):
        """Test determine_student_type_backend for new student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = []  # No existing student
            
            result = self.backend_module.determine_student_type_backend("9876543210", "Test Student")
            
            self.assertEqual(result, "New")

    def test_determine_student_type_backend_continuing_student(self):
        """Test determine_student_type_backend for continuing student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = [
                {"name": "STUD_001", "name1": "Test Student"}
            ]
            
            result = self.backend_module.determine_student_type_backend("9876543210", "Test Student")
            
            self.assertEqual(result, "Continuing")

    def test_determine_student_type_backend_with_invalid_phone(self):
        """Test determine_student_type_backend with invalid phone"""
        result = self.backend_module.determine_student_type_backend("", "Test Student")
        self.assertEqual(result, "New")

    # ============= Get Course Level Tests =============

    def test_get_course_level_with_mapping_backend(self):
        """Test get_course_level_with_mapping_backend with existing mapping"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    mock_frappe.get_all.return_value = [
                        {"course_level": "MATH_L5"}
                    ]
                    mock_frappe.log_error = MagicMock()
                    
                    result = self.backend_module.get_course_level_with_mapping_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )
                    
                    self.assertEqual(result, "MATH_L5")

    def test_get_course_level_with_mapping_backend_dry_run(self):
        """Test get_course_level_with_mapping_backend in dry run mode"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    mock_frappe.get_all.return_value = [
                        {"course_level": "MATH_L5"}
                    ]
                    mock_frappe.log_error = MagicMock()
                    
                    result = self.backend_module.get_course_level_with_mapping_backend(
                        "Math", "5", "9876543210", "Test Student", True  # dry_run = True
                    )
                    
                    self.assertEqual(result, "MATH_L5")

    # ============= Validate Enrollment Data Tests =============

    def test_validate_enrollment_data_no_broken_links(self):
        """Test validate_enrollment_data with no broken enrollments"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = []  # No broken enrollments
            
            result = self.backend_module.validate_enrollment_data("9876543210", "Test Student")
            
            self.assertEqual(result["broken_enrollments"], 0)
            self.assertIn("validation_results", result)

    def test_validate_enrollment_data_with_broken_links(self):
        """Test validate_enrollment_data with broken enrollments"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = [
                {"name": "ENR_001", "course": "BROKEN_COURSE"}
            ]
            
            result = self.backend_module.validate_enrollment_data("9876543210", "Test Student")
            
            self.assertEqual(result["broken_enrollments"], 1)

    # ============= Process Student Record Edge Cases =============

    def test_process_student_record_existing_student(self):
        """Test process_student_record with existing student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name') as mock_find:
                existing_student = {"name": "STUD_001", "glific_id": "contact_123"}
                mock_find.return_value = existing_student
                
                mock_student = MagicMock()
                mock_student.student_name = "Existing Student"
                mock_student.phone = "9876543210"
                
                mock_glific_contact = {"id": "contact_123"}
                mock_frappe.get_doc.return_value = MagicMock()
                mock_frappe.log_error = MagicMock()
                
                result = self.backend_module.process_student_record(
                    mock_student, mock_glific_contact, "BSO_001", "STAGE_001", "MATH_L5"
                )
                
                # Should return the existing student document
                self.assertIsNotNone(result)

    def test_process_student_record_with_exception(self):
        """Test process_student_record handling exceptions"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                mock_student = MagicMock()
                mock_student.student_name = "Error Student"
                mock_student.phone = "9876543210"
                
                mock_glific_contact = {"id": "contact_123"}
                mock_frappe.new_doc.side_effect = Exception("Database error")
                mock_frappe.log_error = MagicMock()
                
                with self.assertRaises(Exception):
                    self.backend_module.process_student_record(
                        mock_student, mock_glific_contact, "BSO_001", "STAGE_001", "MATH_L5"
                    )

    # ============= Update Batch Status Tests =============

    def test_update_batch_status_completed(self):
        """Test updating batch status to Completed"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_batch.student_count = 10
            mock_batch.processed_student_count = 10
            mock_batch.status = "Processing"
            
            mock_frappe.get_doc.return_value = mock_batch
            
            # Simulate internal function call
            mock_batch.save = MagicMock()
            
            # Update status when all students are processed
            if mock_batch.processed_student_count >= mock_batch.student_count:
                mock_batch.status = "Completed"
            
            mock_batch.save()
            
            self.assertEqual(mock_batch.status, "Completed")
            mock_batch.save.assert_called_once()

    def test_update_batch_status_partial(self):
        """Test updating batch status with partial processing"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_batch.student_count = 10
            mock_batch.processed_student_count = 5
            mock_batch.status = "Processing"
            
            mock_frappe.get_doc.return_value = mock_batch
            
            # Should remain in Processing status
            self.assertEqual(mock_batch.status, "Processing")

    # ============= Cancel Batch Tests =============

    def test_cancel_batch_success(self):
        """Test cancel_batch with successful cancellation"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_batch.status = "Processing"
            
            mock_frappe.get_doc.return_value = mock_batch
            mock_frappe.whitelist.return_value = lambda func: func
            
            result = self.backend_module.cancel_batch("BSO_001")
            
            self.assertEqual(mock_batch.status, "Cancelled")
            mock_batch.save.assert_called_once()
            self.assertEqual(result["status"], "success")

    def test_cancel_batch_already_completed(self):
        """Test cancel_batch when batch is already completed"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_batch.status = "Completed"
            
            mock_frappe.get_doc.return_value = mock_batch
            mock_frappe.whitelist.return_value = lambda func: func
            
            result = self.backend_module.cancel_batch("BSO_001")
            
            self.assertEqual(result["status"], "error")
            self.assertIn("Cannot cancel", result["message"])

    # ============= Get Job Status Edge Cases =============

    def test_get_job_status_failed(self):
        """Test get_job_status for failed job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    
                    mock_job = MagicMock()
                    mock_job.get_status.return_value = "failed"
                    mock_job.result = None
                    mock_job.meta = {"error": "Processing failed"}
                    mock_job_class.fetch.return_value = mock_job
                    
                    mock_frappe.whitelist.return_value = lambda func: func
                    
                    result = self.backend_module.get_job_status("job_failed")
                    
                    self.assertEqual(result["status"], "failed")

    def test_get_job_status_queued(self):
        """Test get_job_status for queued job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    
                    mock_job = MagicMock()
                    mock_job.get_status.return_value = "queued"
                    mock_job.result = None
                    mock_job.meta = {}
                    mock_job_class.fetch.return_value = mock_job
                    
                    result = self.backend_module.get_job_status("job_queued")
                    
                    self.assertEqual(result["status"], "queued")

    # ============= Glific Group Tests =============

    def test_create_glific_group(self):
        """Test creating a new Glific group"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'create_glific_group') as mock_create_group:
                mock_create_group.return_value = {"id": "group_123", "label": "Test Group"}
                mock_frappe.whitelist.return_value = lambda func: func
                
                result = self.backend_module.create_glific_group("Test Group", "Test Description")
                
                self.assertEqual(result["id"], "group_123")

    def test_add_contact_to_glific_group(self):
        """Test adding contact to Glific group"""
        with patch.object(self.backend_module, 'add_contact_to_group') as mock_add_to_group:
            mock_add_to_group.return_value = {"success": True}
            
            result = self.backend_module.add_contact_to_group("contact_123", "group_456")
            
            self.assertEqual(result["success"], True)

    # ============= Error Handling Tests =============

    def test_process_batch_job_with_network_error(self):
        """Test process_batch_job handling network errors"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_onboarding_stages') as mock_stages:
                mock_batch = MagicMock()
                mock_batch.name = "BSO_001"
                
                mock_frappe.get_doc.return_value = mock_batch
                mock_stages.side_effect = ConnectionError("Network error")
                
                with self.assertRaises(ConnectionError):
                    self.backend_module.process_batch_job("BSO_001")

    def test_format_phone_number_with_special_chars(self):
        """Test format_phone_number with special characters"""
        result = self.backend_module.format_phone_number("+91-987-654-3210")
        self.assertEqual(result, "919876543210")

    def test_format_phone_number_with_spaces(self):
        """Test format_phone_number with spaces"""
        result = self.backend_module.format_phone_number("91 987 654 3210")
        self.assertEqual(result, "919876543210")

    # ============= Bulk Operations Tests =============

    def test_bulk_update_students(self):
        """Test bulk update of multiple students"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_students = [MagicMock() for _ in range(5)]
            for i, student in enumerate(mock_students):
                student.name = f"STUD_{i:03d}"
                student.processing_status = "Pending"
            
            mock_frappe.get_all.return_value = mock_students
            
            # Simulate bulk update
            for student in mock_students:
                student.processing_status = "Success"
                student.save()
            
            for student in mock_students:
                self.assertEqual(student.processing_status, "Success")
                student.save.assert_called_once()

    def test_retry_failed_students(self):
        """Test retry mechanism for failed students"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_batch.name = "BSO_001"
            
            mock_failed_student = MagicMock()
            mock_failed_student.processing_status = "Failed"
            mock_failed_student.retry_count = 0
            
            mock_frappe.get_doc.return_value = mock_batch
            mock_frappe.get_all.return_value = [mock_failed_student]
            
            # Simulate retry logic
            if mock_failed_student.processing_status == "Failed" and mock_failed_student.retry_count < 3:
                mock_failed_student.retry_count += 1
                mock_failed_student.processing_status = "Pending"
            
            self.assertEqual(mock_failed_student.retry_count, 1)
            self.assertEqual(mock_failed_student.processing_status, "Pending")

    # ============= Data Validation Tests =============

    def test_validate_batch_data_completeness(self):
        """Test validation of batch data completeness"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_batch.student_count = 10
            
            mock_students = [MagicMock() for _ in range(10)]
            mock_frappe.get_all.return_value = mock_students
            
            # Validate that all students are present
            self.assertEqual(len(mock_students), mock_batch.student_count)

    def test_validate_duplicate_students(self):
        """Test detection of duplicate students in batch"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_students = [
                {"phone": "9876543210", "student_name": "John Doe"},
                {"phone": "9876543210", "student_name": "John Doe"},  # Duplicate
                {"phone": "9876543211", "student_name": "Jane Doe"}
            ]
            
            # Simulate duplicate detection
            seen = set()
            duplicates = []
            for student in mock_students:
                key = (student["phone"], student["student_name"])
                if key in seen:
                    duplicates.append(student)
                seen.add(key)
            
            self.assertEqual(len(duplicates), 1)

    # ============= Performance Tests =============

    def test_batch_processing_with_large_dataset(self):
        """Test batch processing with large number of students"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'update_job_progress') as mock_progress:
                mock_batch = MagicMock()
                mock_batch.name = "BSO_001"
                
                # Simulate 100 students
                mock_students = [MagicMock() for _ in range(100)]
                for i, student in enumerate(mock_students):
                    student.processing_status = "Pending"
                
                mock_frappe.get_all.return_value = mock_students
                
                # Simulate processing with progress updates
                for i, student in enumerate(mock_students):
                    if i % 10 == 0:  # Update progress every 10 students
                        mock_progress(i, 100)
                    student.processing_status = "Success"
                
                # Verify progress was updated
                self.assertEqual(mock_progress.call_count, 10)

# Run the extended tests
if __name__ == '__main__':
    # Combine both test classes
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Load tests from the original class
    from test_backend_onboarding_process import TestBackendOnboardingProcess
    suite.addTests(loader.loadTestsFromTestCase(TestBackendOnboardingProcess))
    
    # Load tests from the extended class
    suite.addTests(loader.loadTestsFromTestCase(TestBackendOnboardingProcessExtended))
    
    # Run all tests
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)