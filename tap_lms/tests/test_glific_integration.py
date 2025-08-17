import pytest
import sys
import os
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
import json

# Add the parent directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # This goes from tests/ to tap_lms/
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def test_get_glific_settings_basic():
    """Test basic functionality of get_glific_settings"""
    
    # Mock frappe and other dependencies before importing
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        # Set up the mocks
        mock_frappe = sys.modules['frappe']
        
        # Configure frappe mocks
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_settings.access_token = "test_token"
        mock_frappe.get_single.return_value = mock_settings
        
        # Import function
        from glific_integration import get_glific_settings
        
        # Test that the function exists and is callable
        assert callable(get_glific_settings)
        
        # Call the function
        result = get_glific_settings()
        
        # Verify the result
        assert result == mock_settings
        assert result.api_url == "https://api.glific.com"
        
        # Verify frappe calls
        mock_frappe.get_single.assert_called_once_with("Glific Settings")


def test_get_glific_settings_exception():
    """Test get_glific_settings when exception occurs"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        
        # Configure frappe to raise exception
        mock_frappe.get_single.side_effect = Exception("Settings not found")
        
        try:
            from glific_integration import get_glific_settings
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        # Test that exception is raised
        with pytest.raises(Exception):
            get_glific_settings()


def test_get_glific_auth_headers_valid_token():
    """Test get_glific_auth_headers with valid token"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        
        # Configure mocks
        mock_settings = Mock()
        mock_settings.access_token = "valid_token"
        # Use a real datetime object, not a mock
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_settings.token_expiry_time = future_time
        mock_frappe.get_single.return_value = mock_settings
        
        try:
            from glific_integration import get_glific_auth_headers
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        # Call the function
        result = get_glific_auth_headers()
        
        # Verify the result
        expected = {
            "authorization": "valid_token",
            "Content-Type": "application/json"
        }
        assert result == expected


def test_get_glific_auth_headers_timezone_replacement():
    """Test get_glific_auth_headers with timezone-naive datetime"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        
        # Configure mocks
        mock_settings = Mock()
        mock_settings.access_token = "valid_token"
        # Timezone-naive datetime - use real datetime, not mock
        mock_settings.token_expiry_time = datetime(2025, 12, 31, 23, 59, 59)
        mock_frappe.get_single.return_value = mock_settings
        
        try:
            from glific_integration import get_glific_auth_headers
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        # Call the function
        result = get_glific_auth_headers()
        
        # Should add timezone and return valid token
        expected = {
            "authorization": "valid_token",
            "Content-Type": "application/json"
        }
        assert result == expected


# def test_get_glific_auth_headers_expired_token():
#     """Test get_glific_auth_headers when token is expired"""
    
#     with patch.dict('sys.modules', {
#         'frappe': Mock(),
#         'requests': Mock(),
#         'json': Mock(),
#         'dateutil': Mock(),
#         'dateutil.parser': Mock(),
#     }):
#         mock_frappe = sys.modules['frappe']
        
#         # Configure mocks
#         mock_settings = Mock()
#         mock_settings.access_token = "expired_token"
#         # Set expiry time in the past - use real datetime
#         past_time = datetime.now(timezone.utc) - timedelta(hours=1)
#         mock_settings.token_expiry_time = past_time
#         mock_frappe.get_single.return_value = mock_settings
        
#         try:
#             from glific_integration import get_glific_auth_headers
#         except ImportError as e:
#             pytest.skip("Could not import module: " + str(e))
        
#         # Check if refresh_access_token exists in the module first
#         import glific_integration
#         if hasattr(glific_integration, 'refresh_access_token'):
#             # Mock the refresh_access_token function
#             with patch('glific_integration.refresh_access_token') as mock_refresh:
#                 mock_refresh.return_value = True
                
#                 result = get_glific_auth_headers()
                
#                 # Should call refresh_access_token
#                 mock_refresh.assert_called_once()
#         else:
#             # Skip this test if refresh_access_token doesn't exist
#             pytest.skip("refresh_access_token function not found in module")


def test_create_contact_success():
    """Test create_contact function with successful response"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        # Configure frappe mocks
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_frappe.get_single.return_value = mock_settings
        mock_frappe.logger.return_value.info = Mock()
        
        # Configure requests mocks
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
        
        try:
            from glific_integration import create_contact
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        # Mock other functions that are called
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            # Call the function
            result = create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
            
            # Verify the result
            assert result is not None
            assert result["id"] == "123"
            assert result["name"] == "Test User"


def test_create_contact_api_error():
    """Test create_contact when API returns error"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        # Configure mocks
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_frappe.logger.return_value.error = Mock()
        
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.json.return_value = {
            "errors": [{"message": "Phone number already exists"}]
        }
        mock_requests.post.return_value = mock_response
        
        try:
            from glific_integration import create_contact
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            result = create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
            
            assert result is None


def test_update_contact_fields_success():
    """Test update_contact_fields function with success"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        # Configure mocks
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_frappe.logger.return_value.info = Mock()
        mock_frappe.logger.return_value.error = Mock()
        
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
        
        try:
            from glific_integration import update_contact_fields
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            result = update_contact_fields("123", {"new_field": "new_value"})
            
            assert result is True


def test_update_contact_fields_json_decode_error():
    """Test update_contact_fields JSON decode error"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        # Configure mocks
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_frappe.logger.return_value.error = Mock()
        mock_frappe.logger.return_value.info = Mock()
        
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
                        "fields": "not valid json"  # This will fail json.loads()
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
        
        try:
            from glific_integration import update_contact_fields
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
             patch('json.loads') as mock_json_loads:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            # Make json.loads raise an exception
            mock_json_loads.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            
            result = update_contact_fields("123", {"new_field": "new_value"})
            
            # Should succeed despite JSON error (sets existing_fields = {} and continues)
            assert result is True


def test_update_contact_fields_general_exception():
    """Test update_contact_fields when exception occurs during the try block"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        mock_frappe.logger.return_value.error = Mock()
        
        try:
            from glific_integration import update_contact_fields
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        # Set up basic mocks that work (these are called before the try block)
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        
        # Mock the requests.post to raise a RequestException (which should be caught)
        mock_requests.post.side_effect = Exception("Network error")
        mock_requests.exceptions = Mock()
        mock_requests.exceptions.RequestException = Exception
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            result = update_contact_fields("123", {"new_field": "new_value"})
            
            # The function should catch the exception and return False
            assert result is False


def test_get_contact_by_phone_success():
    """Test get_contact_by_phone function with success"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        
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
        
        try:
            from glific_integration import get_contact_by_phone
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            result = get_contact_by_phone("1234567890")
            
            assert result is not None
            assert result["id"] == "123"


def test_optin_contact_success():
    """Test optin_contact function with success"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        
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
        
        try:
            from glific_integration import optin_contact
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            result = optin_contact("1234567890", "Test User")
            
            assert result is True


def test_check_glific_group_exists_found():
    """Test check_glific_group_exists when group exists"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        
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
        
        try:
            from glific_integration import check_glific_group_exists
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            result = check_glific_group_exists("Test Group")
            
            assert result is not None
            assert result["id"] == "group123"


def test_add_contact_to_group_success():
    """Test add_contact_to_group function with success"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_requests = sys.modules['requests']
        
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        
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
        
        try:
            from glific_integration import add_contact_to_group
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            result = add_contact_to_group("contact123", "group123")
            
            assert result is True


def test_add_contact_to_group_invalid_params():
    """Test add_contact_to_group with invalid parameters"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        try:
            from glific_integration import add_contact_to_group
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))
        
        # Test with None contact_id
        result = add_contact_to_group(None, "group123")
        assert result is False
        
        # Test with None group_id
        result = add_contact_to_group("contact123", None)
        assert result is False


def test_import_statements_coverage():
    """Test to cover import statements in the module"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        try:
            # This import covers the import statements in the file
            import glific_integration
            assert hasattr(glific_integration, 'get_glific_settings')
            assert callable(glific_integration.get_glific_settings)
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))


def test_function_signatures():
    """Test function signatures exist"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'datetime': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        try:
            from glific_integration import (
                get_glific_settings,
                get_glific_auth_headers,
                create_contact,
                update_contact_fields,
                get_contact_by_phone,
                optin_contact,
                check_glific_group_exists,
                add_contact_to_group
            )
            
            # Verify all functions exist and are callable
            functions = [
                get_glific_settings,
                get_glific_auth_headers,
                create_contact,
                update_contact_fields,
                get_contact_by_phone,
                optin_contact,
                check_glific_group_exists,
                add_contact_to_group
            ]
            
            for func in functions:
                assert callable(func)
                
        except ImportError as e:
            pytest.skip("Could not import module: " + str(e))


# if __name__ == "__main__":
#     pytest.main([__file__, "-v"])
