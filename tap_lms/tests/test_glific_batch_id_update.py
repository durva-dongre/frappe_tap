# test_glific_batch_id_update.py
# Complete test suite for glific_batch_id_update.py module

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
    mock_student.name = test_data["backend_student_name"]
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


@pytest.fixture
def mock_glific_contact_without_batch_id(test_data):
    """Fixture for Glific contact without batch_id field"""
    return {
        "data": {
            "contact": {
                "contact": {
                    "id": test_data["glific_id"],
                    "name": test_data["student_name"],
                    "phone": test_data["phone"],
                    "fields": json.dumps({
                        "student_id": {"value": test_data["student_id"], "type": "string"}
                    })
                }
            }
        }
    }


@pytest.fixture
def mock_glific_contact_with_batch_id(test_data):
    """Fixture for Glific contact with batch_id field"""
    return {
        "data": {
            "contact": {
                "contact": {
                    "id": test_data["glific_id"],
                    "name": test_data["student_name"],
                    "phone": test_data["phone"],
                    "fields": json.dumps({
                        "student_id": {"value": test_data["student_id"], "type": "string"},
                        "batch_id": {"value": "BATCH_2023_12", "type": "string"}
                    })
                }
            }
        }
    }


@pytest.fixture
def mock_glific_update_success(test_data):
    """Fixture for successful Glific update response"""
    return {
        "data": {
            "updateContact": {
                "contact": {
                    "id": test_data["glific_id"],
                    "name": test_data["student_name"],
                    "fields": json.dumps({
                        "student_id": {"value": test_data["student_id"], "type": "string"},
                        "batch_id": {"value": test_data["batch_id"], "type": "string"}
                    })
                }
            }
        }
    }


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
    
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    def test_returns_none_when_batch_is_empty_string(self, mock_exists, test_data):
        """Test returns None when batch is empty string"""
        mock_exists.return_value = True
        
        result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], "")
        
        # Empty string is falsy in the conditional check (if not batch_id_value)
        # So the function returns None for empty strings
        assert result is None or result == ""
    
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

class TestUpdateSpecificSetContactsValidation:
    """Test cases for input validation and error cases"""
    
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


class TestUpdateSpecificSetContactsHappyPath:
    """Test cases for successful update scenarios"""
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_successfully_adds_batch_id_to_new_contact(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc, 
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings,
        mock_glific_contact_without_batch_id, mock_glific_update_success
    ):
        """Test successfully adding batch_id to contact that doesn't have one"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Mock Glific fetch and update responses
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = mock_glific_contact_without_batch_id
        
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = mock_glific_update_success
        
        mock_post.side_effect = [fetch_response, update_response]
        
        # Setup get_doc to return different mocks based on doctype
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions
        assert result["updated"] == 1
        assert result["errors"] == 0
        assert result["skipped"] == 0
        assert result["total_processed"] == 1
        assert mock_post.call_count == 2  # Fetch + Update
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_successfully_updates_batch_id_with_different_value(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings,
        mock_glific_contact_with_batch_id, mock_glific_update_success
    ):
        """Test successfully updating batch_id when value changes"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Mock Glific fetch response (contact WITH old batch_id)
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = mock_glific_contact_with_batch_id
        
        # Mock Glific update response
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = mock_glific_update_success
        
        mock_post.side_effect = [fetch_response, update_response]
        
        # Setup get_doc
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions
        assert result["updated"] == 1
        assert result["errors"] == 0
        assert result["skipped"] == 0
        assert mock_post.call_count == 2
        
        # Verify logging shows old → new value
        log_calls = [str(call) for call in mock_logger().info.call_args_list]
        assert any("BATCH_2023_12" in str(call) and "BATCH_2024_01" in str(call) for call in log_calls)
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_refreshes_batch_id_with_same_value(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_student_doc, mock_glific_settings
    ):
        """Test refreshing batch_id when value is already correct"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Mock Glific fetch response (contact WITH same batch_id)
        contact_with_same_batch = {
            "data": {
                "contact": {
                    "contact": {
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "phone": test_data["phone"],
                        "fields": json.dumps({
                            "batch_id": {"value": test_data["batch_id"], "type": "string"}
                        })
                    }
                }
            }
        }
        
        # FIXED: Proper update response structure
        update_response_data = {
            "data": {
                "updateContact": {
                    "contact": {
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "fields": json.dumps({
                            "batch_id": {"value": test_data["batch_id"], "type": "string"}
                        })
                    }
                }
            }
        }
        
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = contact_with_same_batch
        
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = update_response_data  # FIXED: Use correct structure
        
        mock_post.side_effect = [fetch_response, update_response]
        
        # Setup get_doc
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions
        assert result["updated"] == 1
        assert result["errors"] == 0
        
        # Verify logging shows refresh message
        log_calls = [str(call) for call in mock_logger().info.call_args_list]
        assert any("Refreshed" in str(call) or "unchanged" in str(call) for call in log_calls)
    
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_skips_student_without_glific_id(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, test_data, mock_onboarding_set,
        mock_backend_student
    ):
        """Test skipping student that has no glific_id"""
        # Setup mocks
        mock_exists.return_value = True
        
        # Student doc has no glific_id
        mock_student_no_glific = MagicMock()
        mock_student_no_glific.glific_id = None
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_no_glific
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions
        assert result["errors"] == 1
        assert result["updated"] == 0
        assert result["total_processed"] == 1
        mock_logger().warning.assert_called()
    
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_skips_student_without_batch_id(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        test_data, mock_onboarding_set, mock_student_doc
    ):
        """Test skipping student that has no batch_id value"""
        # Setup mocks
        mock_exists.return_value = True
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        # FIXED: batch should be None or empty string
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": None,  # No batch_id
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions
        assert result["skipped"] == 1
        assert result["updated"] == 0
        assert result["total_processed"] == 1
        mock_logger().warning.assert_called()


class TestUpdateSpecificSetContactsErrorHandling:
    """Test cases for error handling scenarios"""
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_handles_glific_fetch_failure(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings
    ):
        """Test handling when Glific contact fetch fails"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Glific returns 500 error
        fetch_response = MagicMock()
        fetch_response.status_code = 500
        mock_post.return_value = fetch_response
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions
        assert result["errors"] == 1
        assert result["updated"] == 0
        mock_logger().error.assert_called()
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_handles_glific_api_errors_in_response(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings
    ):
        """Test handling Glific API errors in successful HTTP response"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # 200 response but with errors in JSON
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "errors": [{"message": "Invalid contact ID"}]
        }
        mock_post.return_value = fetch_response
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions
        assert result["errors"] == 1
        assert result["updated"] == 0
        mock_logger().error.assert_called()
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_handles_malformed_json_in_contact_fields(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings,
        mock_glific_update_success
    ):
        """Test handling when contact fields contain invalid JSON"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Glific returns fields that can't be parsed
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "phone": test_data["phone"],
                        "fields": "invalid json {{"
                    }
                }
            }
        }
        
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = mock_glific_update_success
        
        mock_post.side_effect = [fetch_response, update_response]
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Should handle gracefully and treat as empty fields
        assert result["updated"] == 1  # Still succeeds
        mock_logger().error.assert_called()  # Logs the JSON parse error
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_continues_processing_after_single_student_error(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_glific_settings, mock_glific_update_success
    ):
        """Test that one student error doesn't stop batch processing"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Three students: first succeeds, second fails, third succeeds
        student_doc1 = MagicMock()
        student_doc1.glific_id = "GID001"
        
        student_doc2 = MagicMock()
        student_doc2.glific_id = None  # This will cause error
        
        student_doc3 = MagicMock()
        student_doc3.glific_id = "GID003"
        
        doc_counter = [0]
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                doc_counter[0] += 1
                if doc_counter[0] == 1:
                    return student_doc1
                elif doc_counter[0] == 2:
                    return student_doc2
                else:
                    return student_doc3
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [
            {"name": "STU001", "student_id": "STU001", "student_name": "Student 1", "batch": "BATCH_1", "phone": "+1", "batch_skeyword": "key"},
            {"name": "STU002", "student_id": "STU002", "student_name": "Student 2", "batch": "BATCH_2", "phone": "+2", "batch_skeyword": "key"},
            {"name": "STU003", "student_id": "STU003", "student_name": "Student 3", "batch": "BATCH_3", "phone": "+3", "batch_skeyword": "key"}
        ]
        
        # Mock responses for student 1 and 3 (student 2 will fail before reaching here)
        success_fetch = MagicMock()
        success_fetch.status_code = 200
        success_fetch.json.return_value = {
            "data": {"contact": {"contact": {"id": "GID001", "name": "Student 1", "phone": "+1", "fields": "{}"}}}
        }
        
        success_update = MagicMock()
        success_update.status_code = 200
        success_update.json.return_value = mock_glific_update_success
        
        mock_post.side_effect = [success_fetch, success_update, success_fetch, success_update]
        
        # Execute
        result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Assertions - should process all 3 students despite middle one failing
        assert result["total_processed"] == 3
        assert result["updated"] == 2  # Student 1 and 3
        assert result["errors"] == 1  # Student 2


class TestGlificAPIInteraction:
    """Tests for Glific API interaction details"""
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_sends_correct_graphql_query_for_fetch(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings,
        mock_glific_contact_without_batch_id, mock_glific_update_success
    ):
        """Verify correct GraphQL query structure for fetching contact"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = mock_glific_contact_without_batch_id
        
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = mock_glific_update_success
        
        mock_post.side_effect = [fetch_response, update_response]
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Get the first call (fetch)
        fetch_call = mock_post.call_args_list[0]
        fetch_payload = fetch_call[1]['json']
        
        # Verify GraphQL query structure
        assert 'query' in fetch_payload
        assert 'contact($id: ID!)' in fetch_payload['query']
        assert 'contact {' in fetch_payload['query']
        assert 'id' in fetch_payload['query']
        assert 'name' in fetch_payload['query']
        assert 'phone' in fetch_payload['query']
        assert 'fields' in fetch_payload['query']
        assert 'variables' in fetch_payload
        assert fetch_payload['variables']['id'] == test_data["glific_id"]
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_sends_correct_graphql_mutation_for_update(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings,
        mock_glific_contact_without_batch_id, mock_glific_update_success
    ):
        """Verify correct GraphQL mutation structure for updating contact"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = mock_glific_contact_without_batch_id
        
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = mock_glific_update_success
        
        mock_post.side_effect = [fetch_response, update_response]
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Get the second call (update)
        update_call = mock_post.call_args_list[1]
        update_payload = update_call[1]['json']
        
        # Verify GraphQL mutation structure
        assert 'query' in update_payload
        assert 'mutation updateContact' in update_payload['query']
        assert 'updateContact(id: $id, input: $input)' in update_payload['query']
        assert 'variables' in update_payload
        assert update_payload['variables']['id'] == test_data["glific_id"]
        assert 'input' in update_payload['variables']
        assert 'fields' in update_payload['variables']['input']
        
        # Verify fields JSON is properly formatted
        fields_json = update_payload['variables']['input']['fields']
        fields_dict = json.loads(fields_json)
        assert 'batch_id' in fields_dict
        assert fields_dict['batch_id']['value'] == test_data["batch_id"]
    
    @patch('requests.post')
    @patch('tap_lms.glific_batch_id_update.get_glific_auth_headers')
    @patch('tap_lms.glific_batch_id_update.get_glific_settings')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_preserves_existing_fields_when_updating(
        self, mock_logger, mock_exists, mock_get_all, mock_get_doc,
        mock_settings, mock_headers, mock_post, test_data, mock_onboarding_set,
        mock_backend_student, mock_student_doc, mock_glific_settings,
        mock_glific_update_success
    ):
        """Test that other fields are preserved when adding batch_id"""
        # Setup mocks
        mock_exists.return_value = True
        mock_settings.return_value = mock_glific_settings
        mock_headers.return_value = {"Authorization": "Bearer token"}
        
        # Contact with existing fields
        contact_with_fields = {
            "data": {
                "contact": {
                    "contact": {
                        "id": test_data["glific_id"],
                        "name": test_data["student_name"],
                        "phone": test_data["phone"],
                        "fields": json.dumps({
                            "student_id": {"value": test_data["student_id"], "type": "string"},
                            "email": {"value": "test@example.com", "type": "string"}
                        })
                    }
                }
            }
        }
        
        fetch_response = MagicMock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = contact_with_fields
        
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = mock_glific_update_success
        
        mock_post.side_effect = [fetch_response, update_response]
        
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_onboarding_set
            elif doctype == "Student":
                return mock_student_doc
            return MagicMock()
        
        mock_get_doc.side_effect = get_doc_side_effect
        
        mock_get_all.return_value = [{
            "name": test_data["backend_student_name"],
            "student_name": test_data["student_name"],
            "phone": test_data["phone"],
            "student_id": test_data["student_id"],
            "batch": test_data["batch_id"],
            "batch_skeyword": "batch_key"
        }]
        
        # Execute
        glific_batch_id_update.update_specific_set_contacts_with_batch_id(
            test_data["onboarding_set"], batch_size=50
        )
        
        # Verify existing fields are preserved
        update_call = mock_post.call_args_list[1]
        update_payload = update_call[1]['json']
        fields_json = update_payload['variables']['input']['fields']
        fields_dict = json.loads(fields_json)
        
        assert 'student_id' in fields_dict
        assert 'email' in fields_dict
        assert 'batch_id' in fields_dict
        assert fields_dict['student_id']['value'] == test_data["student_id"]
        assert fields_dict['email']['value'] == "test@example.com"


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
    
    @patch('tap_lms.glific_batch_id_update.frappe.db.commit')
    @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_returns_error_from_update_function(self, mock_update, mock_begin, mock_commit, test_data):
        """Test returns error message from update function"""
        mock_update.return_value = {
            "error": "Set not found"
        }
        
        result = glific_batch_id_update.run_batch_id_update_for_specific_set(test_data["onboarding_set"])
        
        assert "Error: Set not found" in result
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
    
    @patch('tap_lms.glific_batch_id_update.frappe.db.commit')
    @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_respects_batch_size_parameter(self, mock_update, mock_begin, mock_commit, test_data):
        """Test that batch_size parameter is passed correctly"""
        mock_update.return_value = {
            "set_name": test_data["onboarding_set"],
            "updated": 5,
            "skipped": 0,
            "errors": 0,
            "total_processed": 5
        }
        
        glific_batch_id_update.run_batch_id_update_for_specific_set(
            test_data["onboarding_set"], 
            batch_size=25
        )
        
        mock_update.assert_called_once_with(test_data["onboarding_set"], 25)


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
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('time.sleep')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_stops_at_batch_limit(self, mock_update, mock_sleep, mock_logger):
        """Test that processing stops after safety limit"""
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
        
        # Verify warning was logged
        warning_calls = [str(call) for call in mock_logger().warning.call_args_list]
        assert any("batch limit" in str(call).lower() for call in warning_calls)
    
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    @patch('time.sleep')
    @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
    def test_respects_sleep_between_batches(self, mock_update, mock_sleep, mock_logger):
        """Test that sleep is called between batches"""
        mock_update.side_effect = [
            {"updated": 10, "errors": 0, "skipped": 0, "total_processed": 10},
            {"updated": 5, "errors": 0, "skipped": 0, "total_processed": 5},
            {"updated": 0, "errors": 0, "skipped": 0, "total_processed": 0}
        ]
        
        glific_batch_id_update.process_multiple_sets_batch_id(["SET001"], batch_size=10)
        
        # Sleep should be called between batches (2 times for 3 batches)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1)


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
    
    @patch('tap_lms.glific_batch_id_update.enqueue')
    def test_handles_empty_string_input(self, mock_enqueue):
        """Test handling of empty or whitespace-only strings"""
        mock_job = MagicMock()
        mock_job.id = "JOB789"
        mock_enqueue.return_value = mock_job
        
        set_names_str = "  ,  ,  "
        result = glific_batch_id_update.process_multiple_sets_batch_id_background(set_names_str)
        
        call_args = mock_enqueue.call_args
        # Should result in empty strings after stripping
        assert len(call_args[1]['set_names']) == 3


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
    
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    def test_returns_empty_list_when_no_sets(self, mock_get_all):
        """Test returns empty list when no processed sets exist"""
        mock_get_all.return_value = []
        
        result = glific_batch_id_update.get_backend_onboarding_sets_for_batch_id()
        
        assert result == []
        assert isinstance(result, list)


# ============= Performance and Edge Case Tests =============

class TestPerformanceAndEdgeCases:
    """Performance-related and edge case test scenarios"""
    
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
    
    @patch('tap_lms.glific_batch_id_update.frappe.get_all')
    @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
    @patch('tap_lms.glific_batch_id_update.frappe.logger')
    def test_respects_batch_size_limit_on_query(self, mock_logger, mock_get_doc, mock_get_all):
        """Test that only batch_size students are fetched per call"""
        mock_onboarding_set = MagicMock()
        mock_onboarding_set.status = "Processed"
        mock_onboarding_set.set_name = "Test Set"
        mock_get_doc.return_value = mock_onboarding_set
        
        # Simulate 100 students available, but only batch_size should be fetched
        mock_get_all.return_value = []  # Will result in "no students" message
        
        glific_batch_id_update.update_specific_set_contacts_with_batch_id("SET001", batch_size=10)
        
        # Verify that get_all was called with limit=batch_size
        call_args = mock_get_all.call_args
        assert call_args[1]['limit'] == 10