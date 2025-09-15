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

import pytest
import json
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
import sys
import os

# Add the app path to sys.path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock frappe module before importing the module under test
sys.modules['frappe'] = MagicMock()
sys.modules['frappe.utils.background_jobs'] = MagicMock()
sys.modules['requests'] = MagicMock()

# Create mock for DoesNotExistError
class DoesNotExistError(Exception):
    pass

# Set up frappe mock with necessary attributes
import frappe
frappe.DoesNotExistError = DoesNotExistError
frappe.logger = MagicMock(return_value=MagicMock())
frappe.db = MagicMock()
frappe.get_doc = MagicMock()
frappe.get_all = MagicMock()
frappe.whitelist = MagicMock(return_value=lambda x: x)

# Mock the glific_integration module dependencies
sys.modules['tap_lms.glific_integration'] = MagicMock()

# Import the module under test
from tap_lms import glific_batch_id_update

# Mock the imported functions from glific_integration
glific_batch_id_update.get_glific_settings = MagicMock()
glific_batch_id_update.get_glific_auth_headers = MagicMock()


# ============= Fixtures =============

@pytest.fixture
def test_data():
    """Fixture providing test data"""
    return {
        "student_id": "STU001",
        "student_name": "John Doe",
        "phone": "+1234567890",
        "glific_id": "12345",
        "batch_id": "BATCH_2024_01",
        "onboarding_set": "ONBOARD_SET_001",
        "backend_student_name": "BACKEND_STU_001"
    }


@pytest.fixture
def mock_onboarding_set():
    """Fixture for mock onboarding set"""
    mock_set = MagicMock()
    mock_set.status = "Processed"
    mock_set.set_name = "Test Onboarding Set"
    return mock_set


@pytest.fixture
def mock_backend_student(test_data):
    """Fixture for mock backend student"""
    mock_student = MagicMock()
    mock_student.student_id = test_data["student_id"]
    mock_student.student_name = test_data["student_name"]
    mock_student.phone = test_data["phone"]
    mock_student.batch = test_data["batch_id"]
    mock_student.batch_skeyword = "batch_key"
    return mock_student


@pytest.fixture
def mock_student_doc(test_data):
    """Fixture for mock student document"""
    mock_doc = MagicMock()
    mock_doc.glific_id = test_data["glific_id"]
    return mock_doc


@pytest.fixture
def mock_glific_settings():
    """Fixture for mock Glific settings"""
    mock_settings = MagicMock()
    mock_settings.api_url = "https://api.glific.com"
    return mock_settings


# ============= Test get_student_batch_id =============

class TestGetStudentBatchId:
    """Test cases for get_student_batch_id function"""
    
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    def test_returns_batch_when_student_exists_and_batch_provided(self, mock_exists, test_data):
        """Test successful retrieval of batch_id when student exists"""
        mock_exists.return_value = True
        
        result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
        assert result == test_data["batch_id"]
        mock_exists.assert_called_once_with("Student", test_data["student_id"])
    
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    def test_returns_none_when_batch_is_none(self, mock_exists, test_data):
        """Test returns None when batch is None"""
        mock_exists.return_value = True
        
        result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], None)
        
        assert result is None
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    def test_returns_none_when_student_not_exists(self, mock_exists, mock_logger, test_data):
        """Test returns None and logs error when student doesn't exist"""
        mock_exists.return_value = False
        
        result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
        assert result is None
        mock_logger().error.assert_called_once()
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    def test_handles_exception_gracefully(self, mock_exists, mock_logger, test_data):
        """Test exception handling returns None and logs error"""
        mock_exists.side_effect = Exception("Database error")
        
        result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
        assert result is None
        mock_logger().error.assert_called_once()


# ============= Test update_specific_set_contacts_with_batch_id =============

class TestUpdateSpecificSetContacts:
    """Test cases for update_specific_set_contacts_with_batch_id function"""
    
    def test_returns_error_when_no_set_name_provided(self):
        """Test error when onboarding set name is None"""
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(None)
        
        assert "error" in result
        assert result["error"] == "Backend Student Onboarding set name is required"
    
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_returns_error_when_set_not_found(self, mock_get_doc, test_data):
        """Test error when onboarding set doesn't exist"""
        mock_get_doc.side_effect = DoesNotExistError
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(test_data["onboarding_set"])
        
        assert "error" in result
        assert "not found" in result["error"]
    
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_returns_error_when_set_not_processed(self, mock_get_doc, test_data):
        """Test error when set status is not 'Processed'"""
        mock_set = MagicMock()
        mock_set.status = "Pending"
        mock_set.set_name = test_data["onboarding_set"]
        mock_get_doc.return_value = mock_set
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(test_data["onboarding_set"])
        
        assert "error" in result
        assert "not 'Processed'" in result["error"]
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_returns_message_when_no_students_found(self, mock_get_doc, mock_get_all, 
                                                    mock_logger, mock_onboarding_set):
        """Test message when no successfully processed students found"""
        mock_get_doc.return_value = mock_onboarding_set
        mock_get_all.return_value = []
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
        assert "message" in result
        assert "No successfully processed students" in result["message"]
    


class TestRunBatchIdUpdate:
    """Test cases for run_batch_id_update_for_specific_set function"""
    
    def test_returns_error_message_when_no_set_name(self):
        """Test error message when set name is not provided"""
        result = glific_batch_id_update.run_batch_id_update_for_specific_set(None)
        
        assert "Error: Backend Student Onboarding set name is required" in result
    
    @patch('tap_lms.glific_batch_id_update.frappe.db.commit')
    @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_returns_success_message_on_completion(self, mock_update, mock_begin, mock_commit, test_data):
        """Test successful completion message"""
        mock_update.return_value = {
            "set_name": test_data["onboarding_set"],
            "updated": 5,
            "skipped": 2,
            "errors": 1,
            "total_processed": 8
        }
        
        result = glific_batch_id_update.run_batch_id_update_for_specific_set(test_data["onboarding_set"])
        
        assert "Process completed" in result
        assert "Updated: 5" in result
        assert "Skipped: 2" in result
        assert "Errors: 1" in result
        assert "Total Processed: 8" in result
        mock_begin.assert_called_once()
        mock_commit.assert_called_once()
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.rollback')
    @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_handles_exception_with_rollback(self, mock_update, mock_begin, mock_rollback, mock_logger):
        """Test exception handling with database rollback"""
        mock_update.side_effect = Exception("Test exception")
        
        result = glific_batch_id_update.run_batch_id_update_for_specific_set("ONBOARD_SET_001")
        
        assert "Error occurred" in result
        assert "Test exception" in result
        mock_rollback.assert_called_once()
        mock_logger().error.assert_called_once()


# ============= Test process_multiple_sets_batch_id =============

class TestProcessMultipleSets:
    """Test cases for process_multiple_sets_batch_id function"""
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('time.sleep')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_processes_multiple_sets_successfully(self, mock_update, mock_sleep, mock_logger):
        """Test successful processing of multiple sets"""
        # First set processes in 2 batches, second set has no students
        mock_update.side_effect = [
            {"updated": 3, "errors": 0, "skipped": 1, "total_processed": 4},
            {"updated": 2, "errors": 1, "skipped": 0, "total_processed": 3},
            {"updated": 0, "errors": 0, "skipped": 0, "total_processed": 0},
            {"message": "No successfully processed students found"}
        ]
        
        set_names = ["SET001", "SET002"]
        results = glific_batch_id_update.process_multiple_sets_batch_id(set_names, batch_size=5)
        
        assert len(results) == 2
        assert results[0]["set_name"] == "SET001"
        assert results[0]["updated"] == 5
        assert results[0]["errors"] == 1
        assert results[0]["skipped"] == 1
        assert results[0]["status"] == "completed"
        
        assert results[1]["set_name"] == "SET002"
        assert results[1]["status"] == "completed"
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_handles_errors_in_individual_sets(self, mock_update, mock_logger):
        """Test handling of errors in individual sets"""
        mock_update.side_effect = [
            {"updated": 5, "errors": 0, "skipped": 0, "total_processed": 5},
            {"updated": 0, "errors": 0, "skipped": 0, "total_processed": 0},
            {"error": "Database connection error"}
        ]
        
        set_names = ["SET001", "SET002"]
        results = glific_batch_id_update.process_multiple_sets_batch_id(set_names, batch_size=10)
        
        assert results[0]["status"] == "completed"
        assert results[0]["updated"] == 5
        
        assert results[1]["status"] == "error"
        assert "Database connection error" in results[1]["error"]
        assert results[1]["updated"] == 0


# ============= Test process_multiple_sets_batch_id_background =============

class TestProcessMultipleSetsBackground:
    """Test cases for process_multiple_sets_batch_id_background function"""
    
    @patch('frappe.utils.background_jobs.enqueue')
    def test_enqueues_job_with_list_input(self, mock_enqueue):
        """Test background job enqueueing with list input"""
        # Re-import to get the enqueue function
        from frappe.utils.background_jobs import enqueue
        glific_batch_id_update.enqueue = enqueue
        
        mock_job = MagicMock()
        mock_job.id = "JOB123"
        mock_enqueue.return_value = mock_job
        
        set_names = ["SET001", "SET002", "SET003"]
        result = glific_batch_id_update.process_multiple_sets_batch_id_background(set_names)
        
        assert "Started processing 3 sets" in result
        assert "JOB123" in result
        
        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        assert call_args[1]['set_names'] == set_names
        assert call_args[1]['batch_size'] == 50
        assert call_args[1]['queue'] == 'long'
        assert call_args[1]['timeout'] == 7200
    
    @patch('frappe.utils.background_jobs.enqueue')
    def test_enqueues_job_with_string_input(self, mock_enqueue):
        """Test background job enqueueing with comma-separated string input"""
        # Re-import to get the enqueue function
        from frappe.utils.background_jobs import enqueue
        glific_batch_id_update.enqueue = enqueue
        
        mock_job = MagicMock()
        mock_job.id = "JOB456"
        mock_enqueue.return_value = mock_job
        
        set_names_str = "SET001, SET002, SET003"
        result = glific_batch_id_update.process_multiple_sets_batch_id_background(set_names_str)
        
        assert "Started processing 3 sets" in result
        assert "JOB456" in result
        
        call_args = mock_enqueue.call_args
        expected_list = ["SET001", "SET002", "SET003"]
        assert call_args[1]['set_names'] == expected_list


# ============= Test get_backend_onboarding_sets_for_batch_id =============

class TestGetBackendOnboardingSets:
    """Test cases for get_backend_onboarding_sets_for_batch_id function"""
    
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    def test_returns_processed_onboarding_sets(self, mock_get_all):
        """Test fetching processed backend onboarding sets"""
        mock_sets = [
            {
                "name": "SET001",
                "set_name": "January Batch",
                "processed_student_count": 100,
                "upload_date": "2024-01-15"
            },
            {
                "name": "SET002",
                "set_name": "February Batch",
                "processed_student_count": 150,
                "upload_date": "2024-02-20"
            }
        ]
        mock_get_all.return_value = mock_sets
        
        result = glific_batch_id_update.get_backend_onboarding_sets_for_batch_id()
        
        assert len(result) == 2
        assert result[0]["set_name"] == "January Batch"
        assert result[0]["processed_student_count"] == 100
        assert result[1]["set_name"] == "February Batch"
        assert result[1]["processed_student_count"] == 150
        
        mock_get_all.assert_called_once_with(
            "Backend Student Onboarding",
            filters={"status": "Processed"},
            fields=["name", "set_name", "processed_student_count", "upload_date"],
            order_by="upload_date desc"
        )



class TestPerformance:
    """Performance-related test cases"""
    
    @patch('time.sleep')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_batch_processing_respects_batch_limit(self, mock_logger, mock_update, mock_sleep):
        """Test that batch processing stops after safety limit"""
        # Simulate continuous batches that never end
        mock_update.return_value = {
            "updated": 1,
            "errors": 0,
            "skipped": 0,
            "total_processed": 1
        }
        
        results = glific_batch_id_update.process_multiple_sets_batch_id(["INFINITE_SET"], batch_size=1)
        
        # Should stop after 20 batches (safety limit)
        assert mock_update.call_count <= 21  # Initial call + 20 batch limit
        assert results[0]["status"] == "completed"
    
    @patch('frappe.utils.background_jobs.enqueue')
    def test_background_job_uses_correct_timeout(self, mock_enqueue):
        """Test that background job is configured with proper timeout"""
        # Re-import to get the enqueue function
        from frappe.utils.background_jobs import enqueue
        glific_batch_id_update.enqueue = enqueue
        
        mock_job = MagicMock()
        mock_job.id = "TIMEOUT_TEST"
        mock_enqueue.return_value = mock_job
        
        glific_batch_id_update.process_multiple_sets_batch_id_background(["SET001"])
        
        call_args = mock_enqueue.call_args
        assert call_args[1]['timeout'] == 7200  # 2 hours
        assert call_args[1]['queue'] == 'long'

# Additional test cases to increase coverage from 46% to 50%+
# Fixed version with proper mocking


# ============= Test update_specific_set_contacts_with_batch_id (Extended Coverage) =============

class TestUpdateSpecificSetContactsExtended:
    """Extended test cases for better coverage of update_specific_set_contacts_with_batch_id"""
    
    @patch('tap_lms.glific_batch_id_update.update_glific_contact_field')
    @patch('tap_lms.glific_batch_id_update.get_student_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_successful_batch_update_with_students(self, mock_get_doc, mock_get_all,
                                                   mock_get_batch, mock_update_glific,
                                                   mock_onboarding_set, test_data):
        """Test successful processing of students with batch updates"""
        # Setup mocks
        mock_onboarding_set.status = "Processed"
        
        # First call returns onboarding set, subsequent calls return backend students and students
        backend_student1 = MagicMock()
        backend_student1.student_id = "STU_001"
        backend_student1.phone = "+1234567891"
        backend_student1.batch = "BATCH_2024"
        
        backend_student2 = MagicMock()
        backend_student2.student_id = "STU_002"
        backend_student2.phone = "+1234567892"
        backend_student2.batch = "BATCH_2024"
        
        student_doc1 = MagicMock()
        student_doc1.glific_id = "GLIFIC_001"
        
        student_doc2 = MagicMock()
        student_doc2.glific_id = "GLIFIC_002"
        
        mock_get_doc.side_effect = [
            mock_onboarding_set,  # Initial check
            backend_student1,      # First backend student
            student_doc1,         # First student doc
            backend_student2,      # Second backend student
            student_doc2,         # Second student doc
        ]
        
        mock_get_all.return_value = [
            {"name": "BACKEND_STU_001"},
            {"name": "BACKEND_STU_002"}
        ]
        
        mock_get_batch.return_value = "BATCH_2024"
        mock_update_glific.return_value = True
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001", batch_size=2)
        
        assert result["updated"] == 2
        assert result["errors"] == 0
        assert result["total_processed"] == 2
        assert mock_update_glific.call_count == 2

    @patch('tap_lms.glific_batch_id_update.update_glific_contact_field')
    @patch('tap_lms.glific_batch_id_update.get_student_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_handles_missing_glific_id(self, mock_get_doc, mock_get_all,
                                       mock_get_batch, mock_update_glific,
                                       mock_onboarding_set):
        """Test handling of students without glific_id"""
        mock_onboarding_set.status = "Processed"
        
        backend_student = MagicMock()
        backend_student.student_id = "STU_001"
        backend_student.phone = "+1234567890"
        backend_student.batch = "BATCH_2024"
        
        student_doc = MagicMock()
        student_doc.glific_id = None  # No glific_id
        
        mock_get_doc.side_effect = [
            mock_onboarding_set,  # Initial check
            backend_student,      # Backend student
            student_doc,         # Student doc without glific_id
        ]
        
        mock_get_all.return_value = [{"name": "BACKEND_STU_001"}]
        mock_get_batch.return_value = "BATCH_2024"
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
        assert result["skipped"] == 1
        assert result["updated"] == 0
        mock_update_glific.assert_not_called()

    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.update_glific_contact_field')
    @patch('tap_lms.glific_batch_id_update.get_student_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_handles_update_glific_failure(self, mock_get_doc, mock_get_all,
                                           mock_get_batch, mock_update_glific, mock_logger,
                                           mock_onboarding_set):
        """Test handling when update_glific_contact_field fails"""
        mock_onboarding_set.status = "Processed"
        
        backend_student = MagicMock()
        backend_student.student_id = "STU_001"
        backend_student.phone = "+1234567890"
        backend_student.batch = "BATCH_2024"
        
        student_doc = MagicMock()
        student_doc.glific_id = "GLIFIC_001"
        
        mock_get_doc.side_effect = [
            mock_onboarding_set,  # Initial check
            backend_student,      # Backend student
            student_doc,         # Student doc
        ]
        
        mock_get_all.return_value = [{"name": "BACKEND_STU_001"}]
        mock_get_batch.return_value = "BATCH_2024"
        mock_update_glific.return_value = False  # Update fails
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
        assert result["errors"] == 1
        assert result["updated"] == 0
        mock_logger().error.assert_called()

    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_handles_student_not_found_exception(self, mock_get_doc, mock_get_all, 
                                                 mock_logger, mock_onboarding_set):
        """Test handling when Student document doesn't exist"""
        mock_onboarding_set.status = "Processed"
        
        backend_student = MagicMock()
        backend_student.student_id = "STU_001"
        backend_student.phone = "+1234567890"
        backend_student.batch = "BATCH_2024"
        
        mock_get_doc.side_effect = [
            mock_onboarding_set,  # Initial check
            backend_student,      # Backend student
            frappe.DoesNotExistError("Student not found")  # Student doc throws error
        ]
        
        mock_get_all.return_value = [{"name": "BACKEND_STU_001"}]
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
        assert result["errors"] == 1
        assert result["updated"] == 0
        mock_logger().error.assert_called()


# ============= Test update_glific_contact_field =============

class TestUpdateGlificContactField:
    """Test cases for update_glific_contact_field function"""
    
    @patch('tap_lms.glific_batch_id_update.requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    def test_successful_glific_update(self, mock_settings, mock_headers, mock_post, mock_glific_settings):
        """Test successful update of Glific contact field"""
        # Import requests mock properly
        import requests
        glific_batch_id_update.requests = requests
        
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token123"}
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "updateContactFields": {
                    "contact": {
                        "id": "12345",
                        "fields": {"batch_id": {"value": "BATCH_2024"}}
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        
        result = glific_batch_id_update.update_glific_contact_field("12345", "BATCH_2024")
        
        assert result is True
        mock_post.assert_called_once()
        
        # Verify the GraphQL mutation structure
        call_args = mock_post.call_args
        payload = json.loads(call_args[1]['data'])
        assert "updateContactFields" in payload['query']
        assert payload['variables']['contactId'] == "12345"
        assert payload['variables']['fieldName'] == "batch_id"
        assert payload['variables']['fieldValue'] == "BATCH_2024"

    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    def test_glific_update_with_error_response(self, mock_settings, mock_headers, mock_post, 
                                               mock_logger, mock_glific_settings):
        """Test handling of error in Glific API response"""
        import requests
        glific_batch_id_update.requests = requests
        
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token123"}
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": [{"message": "Contact not found"}]
        }
        mock_post.return_value = mock_response
        
        result = glific_batch_id_update.update_glific_contact_field("99999", "BATCH_2024")
        
        assert result is False
        mock_logger().error.assert_called()

    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    def test_glific_update_with_http_error(self, mock_settings, mock_headers, mock_post, 
                                           mock_logger, mock_glific_settings):
        """Test handling of HTTP error from Glific API"""
        import requests
        glific_batch_id_update.requests = requests
        
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token123"}
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        result = glific_batch_id_update.update_glific_contact_field("12345", "BATCH_2024")
        
        assert result is False
        mock_logger().error.assert_called()

    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    def test_glific_update_with_request_exception(self, mock_settings, mock_headers, mock_post, 
                                                  mock_logger, mock_glific_settings):
        """Test handling of request exception"""
        import requests
        glific_batch_id_update.requests = requests
        
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token123"}
        mock_post.side_effect = Exception("Connection timeout")
        
        result = glific_batch_id_update.update_glific_contact_field("12345", "BATCH_2024")
        
        assert result is False
        mock_logger().error.assert_called()


# ============= Test Edge Cases for process_multiple_sets_batch_id =============

class TestProcessMultipleSetsEdgeCases:
    """Edge case tests for process_multiple_sets_batch_id"""
    
    def test_handles_empty_set_list(self):
        """Test handling of empty set list"""
        results = glific_batch_id_update.process_multiple_sets_batch_id([])
        
        assert results == []
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_handles_none_set_name_in_list(self, mock_update, mock_logger):
        """Test handling when None is in the set list"""
        mock_update.return_value = {
            "updated": 5, 
            "errors": 0, 
            "skipped": 0, 
            "total_processed": 5,
            "set_name": "SET001"
        }
        
        set_names = [None, "SET001", None, "SET002"]
        results = glific_batch_id_update.process_multiple_sets_batch_id(set_names)
        
        # Should process non-None values
        valid_results = [r for r in results if r.get("set_name")]
        assert len(valid_results) >= 1
    
    @patch('time.sleep')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_continues_processing_after_set_error(self, mock_update, mock_logger, mock_sleep):
        """Test that processing continues after a set encounters an error"""
        # First set succeeds
        # Second set has an error
        # Third set succeeds
        
        def update_side_effect(set_name, batch_size=50):
            if set_name == "SET001":
                return {
                    "updated": 5,
                    "errors": 0,
                    "skipped": 0,
                    "total_processed": 5,
                    "set_name": "SET001"
                }
            elif set_name == "SET002":
                return {"error": "Database connection lost"}
            elif set_name == "SET003":
                return {
                    "updated": 3,
                    "errors": 0,
                    "skipped": 0,
                    "total_processed": 3,
                    "set_name": "SET003"
                }
            return {"total_processed": 0}
        
        mock_update.side_effect = update_side_effect
        
        set_names = ["SET001", "SET002", "SET003"]
        results = glific_batch_id_update.process_multiple_sets_batch_id(set_names, batch_size=10)
        
        assert len(results) == 3
        assert results[0]["status"] == "completed"
        assert results[0]["updated"] == 5
        assert results[1]["status"] == "error"
        assert "Database connection lost" in results[1]["error"]
        assert results[2]["status"] == "completed"
        assert results[2]["updated"] == 3


# ============= Test process_multiple_sets_batch_id_background Edge Cases =============

class TestProcessMultipleSetsBackgroundEdgeCases:
    """Edge case tests for background processing"""
    
    @patch('frappe.utils.background_jobs.enqueue')
    def test_handles_empty_string_input(self, mock_enqueue):
        """Test handling of empty string input"""
        from frappe.utils.background_jobs import enqueue
        glific_batch_id_update.enqueue = enqueue
        
        mock_job = MagicMock()
        mock_job.id = "EMPTY_JOB"
        mock_enqueue.return_value = mock_job
        
        result = glific_batch_id_update.process_multiple_sets_batch_id_background("")
        
        assert "Started processing" in result
    
    @patch('frappe.utils.background_jobs.enqueue')
    def test_handles_whitespace_only_input(self, mock_enqueue):
        """Test handling of whitespace-only string input"""
        from frappe.utils.background_jobs import enqueue
        glific_batch_id_update.enqueue = enqueue
        
        mock_job = MagicMock()
        mock_job.id = "WHITESPACE_JOB"
        mock_enqueue.return_value = mock_job
        
        result = glific_batch_id_update.process_multiple_sets_batch_id_background("   ,  ,   ")
        
        # Should handle whitespace gracefully
        assert "Started processing" in result
        
        call_args = mock_enqueue.call_args
        set_names = call_args[1]['set_names']
        # Filter out empty strings
        valid_names = [name for name in set_names if name and name.strip()]
        assert len(valid_names) == 0 or all(name.strip() for name in valid_names)
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('frappe.utils.background_jobs.enqueue')
    def test_handles_enqueue_failure(self, mock_enqueue, mock_logger):
        """Test handling when enqueue fails"""
        from frappe.utils.background_jobs import enqueue
        glific_batch_id_update.enqueue = enqueue
        
        mock_enqueue.side_effect = Exception("Queue is full")
        
        # Should raise the exception
        with pytest.raises(Exception) as exc_info:
            glific_batch_id_update.process_multiple_sets_batch_id_background(["SET001"])
        
        assert "Queue is full" in str(exc_info.value)


# ============= Integration-style Tests =============

class TestIntegrationScenarios:
    """Integration-style tests combining multiple components"""
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.update_glific_contact_field')
    @patch('tap_lms.glific_batch_id_update.get_student_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    def test_mixed_success_and_failure_scenario(self, mock_get_doc, mock_get_all,
                                                mock_get_batch, mock_update_glific,
                                                mock_logger, mock_onboarding_set):
        """Test realistic scenario with mix of success, skip, and error cases"""
        mock_onboarding_set.status = "Processed"
        
        # Setup 5 students
        backend_students = []
        student_docs = []
        
        for i in range(1, 6):
            backend = MagicMock()
            backend.student_id = f"STU_00{i}"
            backend.phone = f"+123456789{i}"
            backend.batch = "BATCH_2024"
            backend_students.append(backend)
            
            student = MagicMock()
            if i == 3:  # Third student has no glific_id
                student.glific_id = None
            elif i == 5:  # Fifth student will cause exception
                student = None
            else:
                student.glific_id = f"GLIFIC_00{i}"
            student_docs.append(student)
        
        # Build side_effect list
        side_effects = [mock_onboarding_set]  # Initial check
        for i in range(5):
            side_effects.append(backend_students[i])
            if i == 4:  # Fifth student throws exception
                side_effects.append(Exception("Database error"))
            else:
                side_effects.append(student_docs[i])
        
        mock_get_doc.side_effect = side_effects
        
        mock_get_all.return_value = [
            {"name": "BACKEND_STU_001"},
            {"name": "BACKEND_STU_002"},
            {"name": "BACKEND_STU_003"},
            {"name": "BACKEND_STU_004"},
            {"name": "BACKEND_STU_005"}
        ]
        
        mock_get_batch.return_value = "BATCH_2024"
        
        # First two succeed, fourth fails
        mock_update_glific.side_effect = [True, True, False]
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001", batch_size=10)
        
        assert result["updated"] == 2
        assert result["skipped"] == 1
        assert result["errors"] == 2
        assert result["total_processed"] == 5