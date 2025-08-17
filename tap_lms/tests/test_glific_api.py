import pytest
import sys
import os
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
import json

# Add the path where the actual glific_integration.py is located
sys.path.insert(0, '/home/frappe/frappe-bench/apps/tap_lms/tap_lms')

@pytest.fixture
def mock_frappe():
    """Mock frappe module with common methods"""
    mock_frappe = Mock()
    mock_frappe.get_single.return_value = Mock()
    mock_frappe.get_doc.return_value = Mock()
    mock_frappe.get_all.return_value = []
    mock_frappe.new_doc.return_value = Mock()
    mock_frappe.db = Mock()
    mock_frappe.logger.return_value = Mock()
    mock_frappe.throw = Mock(side_effect=Exception("Frappe throw"))
    mock_frappe.utils = Mock()
    mock_frappe.utils.now_datetime.return_value = datetime.now()
    return mock_frappe

def test_import_works():
    """Test that we can import the actual glific_integration module"""
    with patch.dict('sys.modules', {'frappe': Mock(), 'requests': Mock(), 'dateutil': Mock(), 'dateutil.parser': Mock()}):
        import glific_integration
        # Check if we have the actual functions (not test functions)
        assert hasattr(glific_integration, 'get_glific_settings')
        assert hasattr(glific_integration, 'get_glific_auth_headers')
        assert hasattr(glific_integration, 'create_contact')
        assert hasattr(glific_integration, 'update_contact_fields')
        print("✅ Successfully imported glific_integration with actual functions")

def test_get_glific_settings(mock_frappe):
    """Test get_glific_settings function"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'requests': Mock(), 'dateutil': Mock(), 'dateutil.parser': Mock()}):
        import glific_integration
        
        mock_settings = Mock()
        mock_frappe.get_single.return_value = mock_settings
        
        result = glific_integration.get_glific_settings()
        
        mock_frappe.get_single.assert_called_once_with("Glific Settings")
        assert result == mock_settings

def test_get_glific_auth_headers_timezone_replacement(mock_frappe):
    """Test get_glific_auth_headers with timezone-naive datetime that needs timezone replacement"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'requests': Mock(), 'dateutil': Mock(), 'dateutil.parser': Mock()}):
        import glific_integration
        
        mock_settings = Mock()
        mock_settings.access_token = "valid_token"
        mock_settings.token_expiry_time = datetime(2025, 12, 31, 23, 59, 59)  # timezone-naive
        mock_frappe.get_single.return_value = mock_settings

        result = glific_integration.get_glific_auth_headers()

        assert result == {
            "authorization": "valid_token",
            "Content-Type": "application/json"
        }

def test_create_contact_success(mock_frappe):
    """Test create_contact function with successful response"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'dateutil': Mock(), 'dateutil.parser': Mock()}), \
         patch('requests.post') as mock_post:
        
        import glific_integration
        
        # Mock the internal functions
        with patch.object(glific_integration, 'get_glific_settings') as mock_get_settings, \
             patch.object(glific_integration, 'get_glific_auth_headers') as mock_get_headers:
            
            mock_settings = Mock()
            mock_settings.api_url = "https://api.glific.com"
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "success"
            mock_response.json.return_value = {
                "data": {
                    "createContact": {
                        "contact": {
                            "id": "123",
                            "name": "Test User",
                            "phone": "1234567890"
                        }
                    }
                }
            }
            mock_post.return_value = mock_response
            
            mock_frappe.logger.return_value.info = Mock()
            
            result = glific_integration.create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
            
            assert result is not None
            assert result["id"] == "123"
            assert result["name"] == "Test User"

def test_update_contact_fields_json_decode_error(mock_frappe):
    """Test update_contact_fields with JSON decode error"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'dateutil': Mock(), 'dateutil.parser': Mock()}), \
         patch('requests.post') as mock_post:
        
        import glific_integration
        
        with patch.object(glific_integration, 'get_glific_settings') as mock_get_settings, \
             patch.object(glific_integration, 'get_glific_auth_headers') as mock_get_headers:

            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}

            # Mock fetch response with invalid JSON that will cause decode error
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.raise_for_status = Mock()
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "123",
                            "name": "Test User",
                            "fields": "not valid json"  # This will cause JSONDecodeError
                        }
                    }
                }
            }

            # Mock successful update response
            update_response = Mock()
            update_response.status_code = 200
            update_response.raise_for_status = Mock()
            update_response.json.return_value = {
                "data": {
                    "updateContact": {
                        "contact": {"id": "123", "name": "Test User"}
                    }
                }
            }

            mock_post.side_effect = [fetch_response, update_response]

            mock_frappe.logger.return_value.error = Mock()
            mock_frappe.logger.return_value.info = Mock()

            result = glific_integration.update_contact_fields("123", {"new_field": "new_value"})
            assert result is True

def test_update_contact_fields_general_exception(mock_frappe):
    """Test update_contact_fields when general exception occurs"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'dateutil': Mock(), 'dateutil.parser': Mock()}), \
         patch('requests.post') as mock_post:
        
        import glific_integration
        
        mock_frappe.logger.return_value.error = Mock()
        mock_post.side_effect = Exception("General error")
        
        result = glific_integration.update_contact_fields("123", {"new_field": "new_value"})
        assert result is False

def test_create_contact_unexpected_response_structure(mock_frappe):
    """Test create_contact when response structure is unexpected"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'dateutil': Mock(), 'dateutil.parser': Mock()}), \
         patch('requests.post') as mock_post:
        
        import glific_integration

        with patch.object(glific_integration, 'get_glific_settings') as mock_get_settings, \
             patch.object(glific_integration, 'get_glific_auth_headers') as mock_get_headers:

            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "createContact": {}  # Missing contact field
                }
            }
            mock_response.text = '{"data": {"createContact": {}}}'
            mock_post.return_value = mock_response
            
            mock_frappe.logger.return_value.info = Mock()
            mock_frappe.logger.return_value.error = Mock()
            
            result = glific_integration.create_contact("Test Name", "919876543210", "Test School", "Test Model", "1", "batch1")
            
            assert result is None

def test_create_contact_bad_status_code(mock_frappe):
    """Test create_contact when API returns bad status code"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'dateutil': Mock(), 'dateutil.parser': Mock()}), \
         patch('requests.post') as mock_post:
        
        import glific_integration

        with patch.object(glific_integration, 'get_glific_settings') as mock_get_settings, \
             patch.object(glific_integration, 'get_glific_auth_headers') as mock_get_headers:

            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response
            
            mock_frappe.logger.return_value.info = Mock()
            mock_frappe.logger.return_value.error = Mock()
            
            result = glific_integration.create_contact("Test Name", "919876543210", "Test School", "Test Model", "1", "batch1")
            
            assert result is None

def test_add_student_to_glific_for_onboarding_invalid_phone(mock_frappe):
    """Test add_student_to_glific_for_onboarding with invalid phone"""
    with patch.dict('sys.modules', {'frappe': mock_frappe, 'dateutil': Mock(), 'dateutil.parser': Mock()}):
        import glific_integration
        
        mock_frappe.logger.return_value.warning = Mock()
        
        result = glific_integration.add_student_to_glific_for_onboarding(
            "Test Student", "invalid_phone", "Test School", "Test Batch", 
            "group123", "1", "Level 1", "Math", "Grade 5"
        )
        
        assert result is None