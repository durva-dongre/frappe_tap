# test_glific_batch_id_update.py
# Pytest test cases for glific_batch_id_update.py module - All Passing Tests

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

# Import the module under test
from tap_lms import glific_batch_id_update


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
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.get_student_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    def test_successfully_adds_batch_id_to_contact(self, mock_get_all, mock_get_doc, mock_exists,
                                                   mock_logger, mock_get_batch_id, mock_settings,
                                                   mock_headers, mock_requests, test_data,
                                                   mock_onboarding_set, mock_backend_student,
                                                   mock_student_doc, mock_glific_settings):
        """Test successful addition of batch_id to Glific contact"""
        # Setup mocks
        mock_get_doc.side_effect = [mock_onboarding_set, mock_backend_student, mock_student_doc]
        mock_exists.return_value = True
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        mock_get_batch_id.return_value = test_data["batch_id"]
        
        # Mock Glific API responses
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "phone": test_data["phone"],
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
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "fields": json.dumps({"batch_id": {"value": test_data["batch_id"]}})
                    }
                }
            }
        }
        
        mock_requests.side_effect = [fetch_response, update_response]
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
        assert result["updated"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == 0
        assert result["total_processed"] == 1
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.get_student_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    def test_updates_existing_batch_id_field(self, mock_get_all, mock_get_doc, mock_exists,
                                             mock_logger, mock_get_batch_id, mock_settings,
                                             mock_headers, mock_requests, test_data,
                                             mock_onboarding_set, mock_backend_student,
                                             mock_student_doc, mock_glific_settings):
        """Test updating existing batch_id field with new value"""
        new_batch = "NEW_BATCH_2024"
        mock_backend_student.batch = new_batch
        
        mock_get_doc.side_effect = [mock_onboarding_set, mock_backend_student, mock_student_doc]
        mock_exists.return_value = True
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": new_batch,
            "batch_skeyword": "batch_key"
        }]
        
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        mock_get_batch_id.return_value = new_batch
        
        # Contact already has batch_id
        existing_fields = {
            "batch_id": {
                "value": "OLD_BATCH_2023",
                "type": "string",
                "inserted_at": "2023-01-01T00:00:00Z"
            }
        }
        
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "phone": test_data["phone"],
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
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "fields": json.dumps({"batch_id": {"value": new_batch}})
                    }
                }
            }
        }
        
        mock_requests.side_effect = [fetch_response, update_response]
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
        assert result["updated"] == 1
        assert result["errors"] == 0


# ============= Test run_batch_id_update_for_specific_set =============

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
            Exception("Database connection error")
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
    
    @patch('tap_lms.glific_batch_id_update.enqueue')
    def test_enqueues_job_with_list_input(self, mock_enqueue):
        """Test background job enqueueing with list input"""
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
    
    @patch('tap_lms.glific_batch_id_update.enqueue')
    def test_enqueues_job_with_string_input(self, mock_enqueue):
        """Test background job enqueueing with comma-separated string input"""
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


# ============= Integration Tests =============

class TestIntegration:
    """Integration tests for complete workflows"""
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    def test_complete_batch_id_update_workflow(self, mock_get_all, mock_get_doc, mock_exists,
                                               mock_logger, mock_settings, mock_headers,
                                               mock_requests):
        """Test complete batch_id update workflow with multiple students"""
        # Setup mock onboarding set
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = "Integration Test Set"
        
        # Create test students with different scenarios
        students_data = [
            {"id": "STU001", "name": "Student 1", "batch": "BATCH_A", "glific": "1001"},
            {"id": "STU002", "name": "Student 2", "batch": "BATCH_B", "glific": "1002"},
            {"id": "STU003", "name": "Student 3", "batch": None, "glific": "1003"},  # No batch
            {"id": "STU004", "name": "Student 4", "batch": "BATCH_A", "glific": None},  # No glific_id
        ]
        
        mock_get_all.return_value = [
            {
                "name": f"BACKEND_{s['id']}",
                "student_name": s['name'],
                "phone": f"+123456789{i}",
                "student_id": s['id'],
                "batch": s['batch'],
                "batch_skeyword": "key"
            }
            for i, s in enumerate(students_data)
        ]
        
        # Setup get_doc returns
        get_doc_returns = [mock_set]
        for s in students_data:
            backend_student = MagicMock()
            backend_student.student_id = s['id']
            backend_student.student_name = s['name']
            backend_student.batch = s['batch']
            get_doc_returns.append(backend_student)
            
            student_doc = MagicMock()
            student_doc.glific_id = s['glific']
            get_doc_returns.append(student_doc)
        
        mock_get_doc.side_effect = get_doc_returns
        mock_exists.return_value = True
        
        # Mock Glific settings
        mock_settings_obj = MagicMock()
        mock_settings_obj.api_url = "https://api.glific.com"
        mock_settings.return_value = mock_settings_obj
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Mock API responses
        api_responses = []
        for s in students_data:
            if s['glific']:
                # Fetch response
                fetch_resp = Mock()
                fetch_resp.status_code = 200
                fetch_resp.json.return_value = {
                    "data": {
                        "contact": {
                            "contact": {
                                "id": s['glific'],
                                "name": s['name'],
                                "fields": "{}"
                            }
                        }
                    }
                }
                api_responses.append(fetch_resp)
                
                # Update response (only if batch exists)
                if s['batch']:
                    update_resp = Mock()
                    update_resp.status_code = 200
                    update_resp.json.return_value = {
                        "data": {
                            "updateContact": {
                                "contact": {
                                    "id": s['glific'],
                                    "name": s['name'],
                                    "fields": json.dumps({"batch_id": {"value": s['batch']}})
                                }
                            }
                        }
                    }
                    api_responses.append(update_resp)
        
        mock_requests.side_effect = api_responses
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("Integration Test Set")
        
        # Verify results
        assert result["set_name"] == "Integration Test Set"
        assert result["updated"] == 2  # STU001 and STU002
        assert result["skipped"] == 1  # STU003 (no batch)
        assert result["errors"] == 1  # STU004 (no glific_id)
        assert result["total_processed"] == 4


# ============= Performance Tests =============

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
    
    @patch('tap_lms.glific_batch_id_update.enqueue')
    def test_background_job_uses_correct_timeout(self, mock_enqueue):
        """Test that background job is configured with proper timeout"""
        mock_job = MagicMock()
        mock_job.id = "TIMEOUT_TEST"
        mock_enqueue.return_value = mock_job
        
        glific_batch_id_update.process_multiple_sets_batch_id_background(["SET001"])
        
        call_args = mock_enqueue.call_args
        assert call_args[1]['timeout'] == 7200  # 2 hours
        assert call_args[1]['queue'] == 'long'


# ============= Edge Case Tests =============

class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    def test_handles_student_without_glific_id(self, mock_get_all, mock_get_doc,
                                               mock_exists, mock_logger):
        """Test handling of student without Glific ID"""
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = "Test Set"
        
        mock_backend_student = MagicMock()
        mock_backend_student.student_id = "STU001"
        mock_backend_student.batch = "BATCH_001"
        
        mock_student_doc = MagicMock()
        mock_student_doc.glific_id = None  # No Glific ID
        
        mock_get_doc.side_effect = [mock_set, mock_backend_student, mock_student_doc]
        mock_exists.return_value = True
        
        mock_get_all.return_value = [{
            "name": "BACKEND_STU_001",
            "student_name": "Test Student",
            "phone": "+1234567890",
            "student_id": "STU001",
            "batch": "BATCH_001",
            "batch_skeyword": "key"
        }]
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("Test Set")
        
        assert result["errors"] == 1
        assert result["updated"] == 0
        mock_logger().warning.assert_called_once()
    
    @patch('tap_lms.glific_batch_id_update.get_student_batch_id')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    def test_skips_student_without_batch(self, mock_get_all, mock_get_doc,
                                         mock_exists, mock_logger, mock_get_batch_id):
        """Test skipping of student without batch"""
        mock_set = MagicMock()
        mock_set.status = "Processed"
        mock_set.set_name = "Test Set"
        
        mock_backend_student = MagicMock()
        mock_backend_student.student_id = "STU001"
        mock_backend_student.batch = None  # No batch
        
        mock_student_doc = MagicMock()
        mock_student_doc.glific_id = "12345"
        
        mock_get_doc.side_effect = [mock_set, mock_backend_student, mock_student_doc]
        mock_exists.return_value = True
        mock_get_batch_id.return_value = None  # No batch_id
        
        mock_get_all.return_value = [{
            "name": "BACKEND_STU_001",
            "student_name": "Test Student",
            "phone": "+1234567890",
            "student_id": "STU001",
            "batch": None,
            "batch_skeyword": "key"
        }]
        
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("Test Set")
        
        assert result["skipped"] == 1
        assert result["updated"] == 0
        mock_logger().warning.assert_called()


# ============= Run Tests =============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])