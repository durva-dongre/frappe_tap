import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json

# Add the parent directory to Python path
# We're in /tap_lms/tests/ and need to import from /tap_lms/
current_dir = os.path.dirname(os.path.abspath(__file__))  # tests directory
parent_dir = os.path.dirname(current_dir)  # tap_lms directory
sys.path.insert(0, parent_dir)

# Import the module we're testing
import glific_integration

@pytest.fixture
def mock_frappe():
    """Mock frappe module with common methods"""
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_frappe.get_single.return_value = Mock()
        mock_frappe.get_doc.return_value = Mock()
        mock_frappe.get_all.return_value = []
        mock_frappe.new_doc.return_value = Mock()
        mock_frappe.db = Mock()
        mock_frappe.logger.return_value = Mock()
        mock_frappe.throw = Mock(side_effect=Exception("Frappe throw"))
        mock_frappe.utils = Mock()
        mock_frappe.utils.now_datetime.return_value = datetime.now()
        yield mock_frappe

class TestGlificSettings:
    """Test cases for get_glific_settings function"""
    
    def test_get_glific_settings_success(self, mock_frappe):
        """Test get_glific_settings function returns settings"""
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_settings.access_token = "test_token"
        mock_frappe.get_single.return_value = mock_settings
        
        result = glific_integration.get_glific_settings()
        
        mock_frappe.get_single.assert_called_once_with("Glific Settings")
        assert result == mock_settings
        assert result.api_url == "https://api.glific.com"

    def test_get_glific_settings_exception(self, mock_frappe):
        """Test get_glific_settings when exception occurs"""
        mock_frappe.get_single.side_effect = Exception("Settings not found")
        
        with pytest.raises(Exception):
            glific_integration.get_glific_settings()

class TestGlificAuthHeaders:
    """Test cases for get_glific_auth_headers function"""
    
    def test_get_glific_auth_headers_valid_token(self, mock_frappe):
        """Test get_glific_auth_headers with valid token"""
        mock_settings = Mock()
        mock_settings.access_token = "valid_token"
        mock_settings.token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_frappe.get_single.return_value = mock_settings

        result = glific_integration.get_glific_auth_headers()

        assert result == {
            "authorization": "valid_token",
            "Content-Type": "application/json"
        }

    def test_get_glific_auth_headers_timezone_replacement(self, mock_frappe):
        """Test get_glific_auth_headers with timezone-naive datetime"""
        mock_settings = Mock()
        mock_settings.access_token = "valid_token"
        # Timezone-naive datetime
        mock_settings.token_expiry_time = datetime(2025, 12, 31, 23, 59, 59)
        mock_frappe.get_single.return_value = mock_settings

        result = glific_integration.get_glific_auth_headers()

        assert result == {
            "authorization": "valid_token",
            "Content-Type": "application/json"
        }

    def test_get_glific_auth_headers_expired_token(self, mock_frappe):
        """Test get_glific_auth_headers when token is expired"""
        mock_settings = Mock()
        mock_settings.access_token = "expired_token"
        # Set expiry time in the past
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_settings.token_expiry_time = past_time
        mock_frappe.get_single.return_value = mock_settings

        with patch('glific_integration.refresh_access_token') as mock_refresh:
            mock_refresh.return_value = True
            
            result = glific_integration.get_glific_auth_headers()
            
            mock_refresh.assert_called_once()

    def test_get_glific_auth_headers_no_token(self, mock_frappe):
        """Test get_glific_auth_headers when no token exists"""
        mock_settings = Mock()
        mock_settings.access_token = None
        mock_frappe.get_single.return_value = mock_settings

        with patch('glific_integration.refresh_access_token') as mock_refresh:
            mock_refresh.return_value = True
            
            result = glific_integration.get_glific_auth_headers()
            
            mock_refresh.assert_called_once()

class TestCreateContact:
    """Test cases for create_contact function"""
    
    def test_create_contact_success(self, mock_frappe):
        """Test create_contact function with successful response"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
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
            mock_requests.post.return_value = mock_response
            
            mock_frappe.logger.return_value.info = Mock()
            
            result = glific_integration.create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
            
            assert result is not None
            assert result["id"] == "123"
            assert result["name"] == "Test User"

    def test_create_contact_api_error(self, mock_frappe):
        """Test create_contact when API returns error"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_response.json.return_value = {
                "errors": [{"message": "Phone number already exists"}]
            }
            mock_requests.post.return_value = mock_response
            
            mock_frappe.logger.return_value.error = Mock()
            
            result = glific_integration.create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
            
            assert result is None

    def test_create_contact_request_exception(self, mock_frappe):
        """Test create_contact when request raises exception"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_requests.post.side_effect = Exception("Connection error")
            mock_frappe.logger.return_value.error = Mock()
            
            result = glific_integration.create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
            
            assert result is None

class TestUpdateContactFields:
    """Test cases for update_contact_fields function"""
    
    def test_update_contact_fields_success(self, mock_frappe):
        """Test update_contact_fields function with success"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_settings = Mock()
            mock_settings.api_url = "https://api.glific.com"
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            # Mock fetch response
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.raise_for_status = Mock()
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "123",
                            "name": "Test User",
                            "fields": '{"existing_field": {"value": "existing_value"}}'
                        }
                    }
                }
            }
            
            # Mock update response
            update_response = Mock()
            update_response.status_code = 200
            update_response.text = "success"
            update_response.raise_for_status = Mock()
            update_response.json.return_value = {
                "data": {
                    "updateContact": {
                        "contact": {
                            "id": "123",
                            "name": "Test User"
                        }
                    }
                }
            }
            
            mock_requests.post.side_effect = [fetch_response, update_response]
            mock_requests.exceptions = Mock()
            mock_requests.exceptions.RequestException = Exception
            
            mock_frappe.logger.return_value.info = Mock()
            
            result = glific_integration.update_contact_fields("123", {"new_field": "new_value"})
            
            assert result is True

    def test_update_contact_fields_json_decode_error(self, mock_frappe):
        """Test update_contact_fields JSON decode error"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:

            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}

            # Mock fetch response with invalid JSON
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.raise_for_status = Mock()
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "123",
                            "name": "Test User",
                            "fields": "not valid json"
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

            mock_requests.post.side_effect = [fetch_response, update_response]
            mock_requests.exceptions.RequestException = Exception

            mock_frappe.logger.return_value.error = Mock()
            mock_frappe.logger.return_value.info = Mock()

            result = glific_integration.update_contact_fields("123", {"new_field": "new_value"})

            assert result is True

    def test_update_contact_fields_general_exception(self, mock_frappe):
        """Test update_contact_fields when general exception occurs"""
        mock_frappe.logger.return_value.error = Mock()

        with patch('glific_integration.requests.post') as mock_post:
            mock_post.side_effect = Exception("General error")
            
            result = glific_integration.update_contact_fields("123", {"new_field": "new_value"})
            
            assert result is False

class TestGetContactByPhone:
    """Test cases for get_contact_by_phone function"""
    
    def test_get_contact_by_phone_success(self, mock_frappe):
        """Test get_contact_by_phone function with success"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "contactByPhone": {
                        "contact": {
                            "id": "123",
                            "name": "Test User",
                            "phone": "1234567890"
                        }
                    }
                }
            }
            mock_requests.post.return_value = mock_response
            
            result = glific_integration.get_contact_by_phone("1234567890")
            
            assert result is not None
            assert result["id"] == "123"

    def test_get_contact_by_phone_not_found(self, mock_frappe):
        """Test get_contact_by_phone when contact not found"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "contactByPhone": {
                        "contact": None
                    }
                }
            }
            mock_requests.post.return_value = mock_response
            
            result = glific_integration.get_contact_by_phone("1234567890")
            
            assert result is None

class TestOptinContact:
    """Test cases for optin_contact function"""
    
    def test_optin_contact_success(self, mock_frappe):
        """Test optin_contact function with success"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "optinContact": {
                        "contact": {
                            "id": "123",
                            "phone": "1234567890",
                            "name": "Test User"
                        }
                    }
                }
            }
            mock_requests.post.return_value = mock_response
            
            result = glific_integration.optin_contact("1234567890", "Test User")
            
            assert result is True

    def test_optin_contact_failure(self, mock_frappe):
        """Test optin_contact function with failure"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_requests.post.return_value = mock_response
            mock_frappe.logger.return_value.error = Mock()
            
            result = glific_integration.optin_contact("1234567890", "Test User")
            
            assert result is False

class TestGlificGroup:
    """Test cases for group-related functions"""
    
    def test_check_glific_group_exists_found(self, mock_frappe):
        """Test check_glific_group_exists when group exists"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "groups": [
                        {"id": "group123", "label": "Test Group"}
                    ]
                }
            }
            mock_requests.post.return_value = mock_response
            
            result = glific_integration.check_glific_group_exists("Test Group")
            
            assert result is not None
            assert result["id"] == "group123"

    def test_check_glific_group_exists_not_found(self, mock_frappe):
        """Test check_glific_group_exists when group doesn't exist"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "groups": []
                }
            }
            mock_requests.post.return_value = mock_response
            
            result = glific_integration.check_glific_group_exists("Non-existent Group")
            
            assert result is None

    def test_add_contact_to_group_success(self, mock_frappe):
        """Test add_contact_to_group function with success"""
        with patch('glific_integration.requests') as mock_requests, \
             patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
            mock_get_headers.return_value = {"authorization": "token"}
            
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "updateGroupContacts": {
                        "groupContacts": [{"id": "contact123"}],
                        "numberDeleted": 0
                    }
                }
            }
            mock_requests.post.return_value = mock_response
            
            result = glific_integration.add_contact_to_group("contact123", "group123")
            
            assert result is True

    def test_add_contact_to_group_invalid_params(self, mock_frappe):
        """Test add_contact_to_group with invalid parameters"""
        # Test with None contact_id
        result = glific_integration.add_contact_to_group(None, "group123")
        assert result is False
        
        # Test with None group_id
        result = glific_integration.add_contact_to_group("contact123", None)
        assert result is False

if __name__ == "__main__":
    pytest.main([__file__, "-v"])