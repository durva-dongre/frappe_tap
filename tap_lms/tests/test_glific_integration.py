import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json

# Add the parent directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

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

# CORRECTED TEST FUNCTIONS:

def test_get_glific_auth_headers_timezone_replacement(mock_frappe):
    """Test get_glific_auth_headers with timezone-naive datetime that needs timezone replacement"""

    try:
        from glific_integration import get_glific_auth_headers
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")

    # Import the real timezone and datetime classes
    from datetime import timezone as real_timezone, datetime as real_datetime
    
    # Mock settings with timezone-naive datetime (this should trigger line 19)
    mock_settings = Mock()
    mock_settings.access_token = "valid_token"

    # Create a timezone-naive datetime using the real datetime class
    naive_datetime = real_datetime(2025, 12, 31, 23, 59, 59)  # No timezone info
    mock_settings.token_expiry_time = naive_datetime

    mock_frappe.get_single.return_value = mock_settings

    # Mock datetime.now to return a consistent time that is less than token expiry
    with patch('glific_integration.datetime') as mock_datetime, \
         patch('glific_integration.timezone', real_timezone):
        
        current_time = real_datetime(2025, 12, 31, 22, 0, 0, tzinfo=real_timezone.utc)
        mock_datetime.now.return_value = current_time
        
        # Keep the real datetime class for isinstance checks
        mock_datetime.datetime = real_datetime
        
        result = get_glific_auth_headers()

        # Verify the token_expiry_time was updated with timezone info
        assert mock_settings.token_expiry_time.tzinfo is not None
        assert result == {
            "authorization": "valid_token",
            "Content-Type": "application/json"
        }

def test_update_contact_fields_general_exception(mock_frappe):
    """Test update_contact_fields when general exception occurs"""
    
    try:
        from glific_integration import update_contact_fields
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")

    # Mock logger first
    mock_frappe.logger.return_value.error = Mock()

    with patch('glific_integration.get_glific_settings') as mock_get_settings:
        # Mock exception in get_glific_settings
        mock_get_settings.side_effect = Exception("General error")
        
        result = update_contact_fields("123", {"new_field": "new_value"})
        
        assert result is False
        # The function should call logger().error, so check if logger was called
        mock_frappe.logger.return_value.error.assert_called()

def test_update_contact_fields_json_decode_error_complete(mock_frappe):
    """Test update_contact_fields JSON decode error - covers lines 180-182"""

    try:
        from glific_integration import update_contact_fields
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")

    with patch('glific_integration.requests') as mock_requests, \
         patch('glific_integration.get_glific_settings') as mock_get_settings, \
         patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
         patch('glific_integration.datetime') as mock_datetime:

        mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
        mock_get_headers.return_value = {"authorization": "token"}
        mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T00:00:00Z"

        # Mock fetch response with fields that will cause JSON decode error when parsed
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": "123",
                        "name": "Test User",
                        "fields": "invalid json string"  # This will cause JSONDecodeError when json.loads is called
                    }
                }
            }
        }

        # Mock update response - successful update
        update_response = Mock()
        update_response.status_code = 200
        update_response.text = "success"
        update_response.raise_for_status = Mock()
        update_response.json.return_value = {
            "data": {
                "updateContact": {
                    "contact": {"id": "123", "name": "Test User"}
                }
            }
        }

        mock_requests.post.side_effect = [fetch_response, update_response]
        mock_requests.exceptions = Mock()
        mock_requests.exceptions.RequestException = Exception

        # Mock logger
        mock_frappe.logger.return_value.error = Mock()
        mock_frappe.logger.return_value.info = Mock()

        result = update_contact_fields("123", {"new_field": "new_value"})

        # The function should handle the JSON decode error gracefully and still succeed
        # When json.loads fails on line 180-182, it sets existing_fields = {} and continues
        assert result is True

# Add some basic working tests to ensure the file runs properly:

def test_get_glific_settings(mock_frappe):
    """Test get_glific_settings function"""
    
    try:
        from glific_integration import get_glific_settings
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")
    
    # Mock settings object
    mock_settings = Mock()
    mock_frappe.get_single.return_value = mock_settings
    
    result = get_glific_settings()
    
    mock_frappe.get_single.assert_called_once_with("Glific Settings")
    assert result == mock_settings

def test_get_glific_auth_headers_valid_token(mock_frappe):
    """Test get_glific_auth_headers with valid non-expired token"""
    
    try:
        from glific_integration import get_glific_auth_headers
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")
    
    with patch('glific_integration.datetime') as mock_datetime:
        # Mock settings with valid token
        mock_settings = Mock()
        mock_settings.access_token = "valid_token"
        mock_settings.token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_frappe.get_single.return_value = mock_settings
        
        # Mock datetime.now to return a consistent time
        mock_datetime.now.return_value = datetime.now(timezone.utc)
        mock_datetime.datetime = datetime  # For isinstance checks
        
        result = get_glific_auth_headers()
        
        expected = {
            "authorization": "valid_token",
            "Content-Type": "application/json"
        }
        assert result == expected

def test_create_contact_success(mock_frappe):
    """Test create_contact function with successful response"""
    
    try:
        from glific_integration import create_contact
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")
    
    with patch('glific_integration.requests') as mock_requests, \
         patch('glific_integration.get_glific_settings') as mock_get_settings, \
         patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
         patch('glific_integration.datetime') as mock_datetime:
        
        # Mock dependencies
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_get_settings.return_value = mock_settings
        mock_get_headers.return_value = {"authorization": "token"}
        mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T00:00:00Z"
        
        # Mock successful response
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
        
        # Mock logger
        mock_frappe.logger.return_value.info = Mock()
        
        result = create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
        
        # Verify result
        assert result is not None
        assert result["id"] == "123"
        assert result["name"] == "Test User"
        
        # Verify API call
        mock_requests.post.assert_called_once()

def test_update_contact_fields_success(mock_frappe):
    """Test update_contact_fields function with success"""
    
    try:
        from glific_integration import update_contact_fields
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")
    
    with patch('glific_integration.requests') as mock_requests, \
         patch('glific_integration.get_glific_settings') as mock_get_settings, \
         patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
         patch('glific_integration.datetime') as mock_datetime:
        
        # Mock dependencies
        mock_settings = Mock()
        mock_settings.api_url = "https://api.glific.com"
        mock_get_settings.return_value = mock_settings
        mock_get_headers.return_value = {"authorization": "token"}
        
        # Mock datetime for timestamp
        mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T00:00:00Z"
        
        # Mock fetch response (get current contact)
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
        
        # Create a proper RequestException for the except clause
        mock_requests.exceptions = Mock()
        mock_requests.exceptions.RequestException = Exception
        
        # Mock logger
        mock_frappe.logger.return_value.info = Mock()
        
        result = update_contact_fields("123", {"new_field": "new_value"})
        
        assert result is True
        assert mock_requests.post.call_count == 2