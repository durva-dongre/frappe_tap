

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json

# Fix 1: test_get_glific_auth_headers_timezone_replacement
# The issue is with timezone mocking. Here's the corrected version:

def test_get_glific_auth_headers_timezone_replacement(mock_frappe):
    """Test get_glific_auth_headers with timezone-naive datetime that needs timezone replacement"""

    try:
        from glific_integration import get_glific_auth_headers
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")

    # Import the real timezone and datetime classes
    from datetime import timezone as real_timezone, datetime as real_datetime
    
    with patch('glific_integration.datetime') as mock_datetime:
        
        # Mock settings with timezone-naive datetime (this should trigger line 19)
        mock_settings = Mock()
        mock_settings.access_token = "valid_token"

        # Create a timezone-naive datetime using the real datetime class
        naive_datetime = real_datetime(2025, 12, 31, 23, 59, 59)  # No timezone info
        mock_settings.token_expiry_time = naive_datetime

        mock_frappe.get_single.return_value = mock_settings

        # Mock datetime.now to return a consistent time that is less than token expiry
        current_time = real_datetime(2025, 12, 31, 22, 0, 0, tzinfo=real_timezone.utc)
        mock_datetime.now.return_value = current_time
        
        # Keep the real datetime class for isinstance checks
        mock_datetime.datetime = real_datetime
        
        # Don't patch timezone - use the real one
        with patch('glific_integration.timezone', real_timezone):
            result = get_glific_auth_headers()

            # Verify the token_expiry_time was updated with timezone info
            assert mock_settings.token_expiry_time.tzinfo is not None
            assert result == {
                "authorization": "valid_token",
                "Content-Type": "application/json"
            }

# Fix 2: test_update_contact_fields_general_exception
# The issue is that we're mocking get_glific_settings to raise an exception, 
# but we also need to handle the logger mock properly

def test_update_contact_fields_general_exception(mock_frappe):
    """Test update_contact_fields when general exception occurs"""
    
    try:
        from glific_integration import update_contact_fields
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")

    # Mock logger first
    mock_logger = Mock()
    mock_frappe.logger.return_value.error = Mock()

    with patch('glific_integration.get_glific_settings') as mock_get_settings:
        # Mock exception in get_glific_settings
        mock_get_settings.side_effect = Exception("General error")
        
        result = update_contact_fields("123", {"new_field": "new_value"})
        
        assert result is False
        # The function should call logger().error, so check if logger was called
        mock_frappe.logger.return_value.error.assert_called()

# Fix 3: test_update_contact_fields_json_decode_error_complete
# The issue is the assertion. Looking at your code, when JSON decode fails,
# it sets existing_fields = {} and continues, which should result in success.
# But the test might be failing because of how we're simulating the JSON decode error.

def test_update_contact_fields_json_decode_error_complete(mock_frappe):
    """Test update_contact_fields JSON decode error - covers lines 180-182"""

    try:
        from glific_integration import update_contact_fields
    except ImportError as e:
        pytest.skip(f"Could not import module: {e}")

    with patch('glific_integration.requests') as mock_requests, \
         patch('glific_integration.get_glific_settings') as mock_get_settings, \
         patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
         patch('glific_integration.datetime') as mock_datetime, \
         patch('glific_integration.json') as mock_json:

        mock_get_settings.return_value = Mock(api_url="https://api.glific.com")
        mock_get_headers.return_value = {"authorization": "token"}
        mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T00:00:00Z"

        # Mock fetch response with fields that will cause JSON decode error
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": "123",
                        "name": "Test User",
                        "fields": "invalid json string"  # This will cause JSONDecodeError
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

        # Mock json.loads to raise JSONDecodeError specifically for the fields parsing
        import json as real_json
        def json_loads_side_effect(s):
            if s == "invalid json string":
                raise real_json.JSONDecodeError("Expecting value", "invalid json string", 0)
            return real_json.loads(s)
        
        mock_json.loads.side_effect = json_loads_side_effect
        mock_json.dumps.return_value = '{"new_field": {"value": "new_value", "type": "string", "inserted_at": "2025-01-01T00:00:00Z"}}'

        # Mock logger
        mock_frappe.logger.return_value.error = Mock()
        mock_frappe.logger.return_value.info = Mock()

        result = update_contact_fields("123", {"new_field": "new_value"})

        # The function should handle the JSON decode error gracefully and still succeed
        assert result is True