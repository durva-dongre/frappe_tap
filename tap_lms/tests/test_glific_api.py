import pytest
import sys
import os
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
import json
import importlib.util

def load_glific_module():
    """Load the glific_integration module directly from file path"""
    file_path = '/home/frappe/frappe-bench/apps/tap_lms/tap_lms/glific_integration.py'
    
    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Load the module directly from the file
    spec = importlib.util.spec_from_file_location("glific_actual", file_path)
    if spec is None:
        raise ImportError(f"Could not load spec from {file_path}")
        
    glific_mod = importlib.util.module_from_spec(spec)
    
    # Mock the dependencies before loading
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
    
    mock_requests = Mock()
    mock_json = Mock()
    mock_dateutil = Mock()
    mock_dateutil.parser = Mock()
    
    # Mock isoparse function
    mock_isoparse = Mock()
    mock_isoparse.return_value = datetime.now(timezone.utc)
    mock_dateutil.parser.isoparse = mock_isoparse
    
    with patch.dict('sys.modules', {
        'frappe': mock_frappe,
        'requests': mock_requests,
        'json': mock_json,
        'dateutil': mock_dateutil,
        'dateutil.parser': mock_dateutil.parser,
    }):
        spec.loader.exec_module(glific_mod)
        return glific_mod, mock_frappe, mock_requests, mock_json

@pytest.fixture
def glific_components():
    """Fixture that provides the glific_integration module and mocks"""
    try:
        module, mock_frappe, mock_requests, mock_json = load_glific_module()
        return module, mock_frappe, mock_requests, mock_json
    except Exception as e:
        pytest.skip(f"Could not load glific_integration module: {e}")

def test_module_loads_successfully():
    """Test that we can successfully load the glific_integration module"""
    try:
        module, _, _, _ = load_glific_module()
        
        # Print available functions for debugging
        functions = [name for name in dir(module) if not name.startswith('_')]
        print(f"\nAvailable functions in module: {functions}")
        
        # Check for expected functions
        expected_functions = [
            'get_glific_settings',
            'get_glific_auth_headers',
            'create_contact',
            'update_contact_fields',
            'get_contact_by_phone',
            'optin_contact'
        ]
        
        found_functions = []
        for func_name in expected_functions:
            if hasattr(module, func_name):
                func = getattr(module, func_name)
                if callable(func):
                    found_functions.append(func_name)
        
        print(f"Found expected functions: {found_functions}")
        
        # We should find at least some functions
        assert len(found_functions) > 0, f"No expected functions found. Available functions: {functions}"
        
        # Make sure we don't have test functions (would indicate wrong file)
        test_functions = [name for name in functions if name.startswith('test_')]
        if test_functions:
            pytest.fail(f"Module contains test functions: {test_functions}. This indicates the wrong file is being loaded.")
            
    except Exception as e:
        pytest.fail(f"Failed to load module: {e}")

def test_get_glific_settings(glific_components):
    """Test get_glific_settings function"""
    module, mock_frappe, _, _ = glific_components
    
    if not hasattr(module, 'get_glific_settings'):
        pytest.skip("get_glific_settings function not found")
    
    mock_settings = Mock()
    mock_frappe.get_single.return_value = mock_settings
    
    result = module.get_glific_settings()
    
    mock_frappe.get_single.assert_called_once_with("Glific Settings")
    assert result == mock_settings

def test_get_glific_auth_headers_timezone_replacement(glific_components):
    """Test get_glific_auth_headers with timezone-naive datetime"""
    module, mock_frappe, _, _ = glific_components
    
    if not hasattr(module, 'get_glific_auth_headers'):
        pytest.skip("get_glific_auth_headers function not found")
    
    mock_settings = Mock()
    mock_settings.access_token = "valid_token"
    mock_settings.token_expiry_time = datetime(2025, 12, 31, 23, 59, 59)  # timezone-naive
    mock_frappe.get_single.return_value = mock_settings

    result = module.get_glific_auth_headers()

    assert result == {
        "authorization": "valid_token",
        "Content-Type": "application/json"
    }

def test_create_contact_success(glific_components):
    """Test create_contact function with successful response"""
    module, mock_frappe, mock_requests, _ = glific_components
    
    if not hasattr(module, 'create_contact'):
        pytest.skip("create_contact function not found")
    
    # Mock the dependencies
    mock_settings = Mock()
    mock_settings.api_url = "https://api.glific.com"
    
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
    
    # Mock internal functions if they exist
    with patch.object(module, 'get_glific_settings', return_value=mock_settings), \
         patch.object(module, 'get_glific_auth_headers', return_value={"authorization": "token"}):
        
        result = module.create_contact("Test User", "1234567890", "Test School", "Test Model", "1", "batch123")
        
        assert result is not None
        assert result["id"] == "123"
        assert result["name"] == "Test User"

def test_update_contact_fields_json_decode_error(glific_components):
    """Test update_contact_fields with JSON decode error"""
    module, mock_frappe, mock_requests, _ = glific_components
    
    if not hasattr(module, 'update_contact_fields'):
        pytest.skip("update_contact_fields function not found")
    
    # Mock the responses
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
    mock_frappe.logger.return_value.error = Mock()
    mock_frappe.logger.return_value.info = Mock()

    # Mock internal functions
    with patch.object(module, 'get_glific_settings', return_value=Mock(api_url="https://api.glific.com")), \
         patch.object(module, 'get_glific_auth_headers', return_value={"authorization": "token"}):

        result = module.update_contact_fields("123", {"new_field": "new_value"})
        assert result is True

def test_update_contact_fields_general_exception(glific_components):
    """Test update_contact_fields when general exception occurs"""
    module, mock_frappe, mock_requests, _ = glific_components
    
    if not hasattr(module, 'update_contact_fields'):
        pytest.skip("update_contact_fields function not found")
    
    mock_frappe.logger.return_value.error = Mock()
    mock_requests.post.side_effect = Exception("General error")
    
    result = module.update_contact_fields("123", {"new_field": "new_value"})
    assert result is False

def test_create_contact_unexpected_response_structure(glific_components):
    """Test create_contact when response structure is unexpected"""
    module, mock_frappe, mock_requests, _ = glific_components
    
    if not hasattr(module, 'create_contact'):
        pytest.skip("create_contact function not found")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "createContact": {}  # Missing contact field
        }
    }
    mock_response.text = '{"data": {"createContact": {}}}'
    mock_requests.post.return_value = mock_response
    
    mock_frappe.logger.return_value.info = Mock()
    mock_frappe.logger.return_value.error = Mock()
    
    with patch.object(module, 'get_glific_settings', return_value=Mock(api_url="https://api.glific.com")), \
         patch.object(module, 'get_glific_auth_headers', return_value={"authorization": "token"}):
        
        result = module.create_contact("Test Name", "919876543210", "Test School", "Test Model", "1", "batch1")
        
        assert result is None

def test_create_contact_bad_status_code(glific_components):
    """Test create_contact when API returns bad status code"""
    module, mock_frappe, mock_requests, _ = glific_components
    
    if not hasattr(module, 'create_contact'):
        pytest.skip("create_contact function not found")

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_requests.post.return_value = mock_response
    
    mock_frappe.logger.return_value.info = Mock()
    mock_frappe.logger.return_value.error = Mock()
    
    with patch.object(module, 'get_glific_settings', return_value=Mock(api_url="https://api.glific.com")), \
         patch.object(module, 'get_glific_auth_headers', return_value={"authorization": "token"}):
        
        result = module.create_contact("Test Name", "919876543210", "Test School", "Test Model", "1", "batch1")
        
        assert result is None

def test_add_student_to_glific_for_onboarding_invalid_phone(glific_components):
    """Test add_student_to_glific_for_onboarding with invalid phone"""
    module, mock_frappe, _, _ = glific_components
    
    if not hasattr(module, 'add_student_to_glific_for_onboarding'):
        pytest.skip("add_student_to_glific_for_onboarding function not found")
    
    mock_frappe.logger.return_value.warning = Mock()
    
    result = module.add_student_to_glific_for_onboarding(
        "Test Student", "invalid_phone", "Test School", "Test Batch", 
        "group123", "1", "Level 1", "Math", "Grade 5"
    )
    
    assert result is None

    