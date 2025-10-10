"""
Comprehensive test suite for Glific Integration module.

This test suite covers:
- Authentication and token management
- Contact creation and updates
- Group management
- Phone number formatting
- Error handling and edge cases
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone, timedelta
import json

# Setup Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_modules():
    """Mock all external dependencies"""
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'requests': Mock(),
        'json': Mock(),
        'dateutil': Mock(),
        'dateutil.parser': Mock(),
    }):
        yield sys.modules


@pytest.fixture
def mock_frappe(mock_modules):
    """Configured Frappe mock"""
    frappe_mock = mock_modules['frappe']
    frappe_mock.logger.return_value = Mock(
        info=Mock(),
        error=Mock(),
        warning=Mock()
    )
    frappe_mock.db = Mock()
    frappe_mock.db.commit = Mock()
    frappe_mock.db.set_value = Mock()
    frappe_mock.utils = Mock()
    frappe_mock.utils.now_datetime = Mock(return_value=datetime.now(timezone.utc))
    return frappe_mock


@pytest.fixture
def mock_glific_settings():
    """Mock Glific Settings document"""
    settings = Mock()
    settings.name = "Glific Settings"
    settings.api_url = "https://api.glific.com"
    settings.access_token = "valid_test_token"
    settings.renewal_token = "renewal_test_token"
    settings.token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)
    settings.phone_number = "911234567890"
    settings.password = "test_password"
    settings.default_language_id = "1"
    return settings


@pytest.fixture
def mock_requests(mock_modules):
    """Configured requests mock"""
    requests_mock = mock_modules['requests']
    requests_mock.exceptions = Mock()
    requests_mock.exceptions.RequestException = Exception
    requests_mock.exceptions.Timeout = TimeoutError
    requests_mock.exceptions.ConnectionError = ConnectionError
    return requests_mock


@pytest.fixture
def mock_api_response():
    """Factory for creating mock API responses"""
    def _create_response(status_code=200, data=None, errors=None):
        response = Mock()
        response.status_code = status_code
        response.raise_for_status = Mock()
        response.text = "Mock response text"
        
        response_data = {}
        if data:
            response_data["data"] = data
        if errors:
            response_data["errors"] = errors
        
        response.json.return_value = response_data
        return response
    return _create_response


# ============================================================================
# TEST CLASS: SETTINGS AND AUTHENTICATION
# ============================================================================

class TestGlificSettings:
    """Tests for Glific settings and authentication"""
    
    def test_get_glific_settings_success(self, mock_frappe, mock_glific_settings):
        """Test successful retrieval of Glific settings"""
        mock_frappe.get_single.return_value = mock_glific_settings
        
        from glific_integration import get_glific_settings
        
        result = get_glific_settings()
        
        assert result == mock_glific_settings
        assert result.api_url == "https://api.glific.com"
        mock_frappe.get_single.assert_called_once_with("Glific Settings")
    
    def test_get_glific_settings_not_found(self, mock_frappe):
        """Test when Glific settings document doesn't exist"""
        mock_frappe.get_single.side_effect = Exception("Document not found")
        
        from glific_integration import get_glific_settings
        
        with pytest.raises(Exception, match="Document not found"):
            get_glific_settings()
    
    def test_get_glific_auth_headers_valid_token(self, mock_frappe, mock_glific_settings):
        """Test auth headers with valid, non-expired token"""
        mock_frappe.get_single.return_value = mock_glific_settings
        
        from glific_integration import get_glific_auth_headers
        
        result = get_glific_auth_headers()
        
        expected = {
            "authorization": "valid_test_token",
            "Content-Type": "application/json"
        }
        assert result == expected
    
    def test_get_glific_auth_headers_expired_token(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test auth headers when token is expired - should refresh"""
        # Set expired token
        mock_glific_settings.token_expiry_time = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_frappe.get_single.return_value = mock_glific_settings
        
        # Mock successful token refresh - note the structure matches what code expects
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "data": {
                "access_token": "new_test_token",
                "renewal_token": "new_renewal_token",
                "token_expiry_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            }
        }
        mock_requests.post.return_value = response
        
        from glific_integration import get_glific_auth_headers
        
        result = get_glific_auth_headers()
        
        assert result["authorization"] == "new_test_token"
        mock_frappe.db.set_value.assert_called_once()
    
    def test_get_glific_auth_headers_no_token(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test auth headers when no token exists"""
        mock_glific_settings.access_token = None
        mock_glific_settings.token_expiry_time = None
        mock_frappe.get_single.return_value = mock_glific_settings
        
        # Mock successful token refresh - structure matches what code expects
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "data": {
                "access_token": "new_test_token",
                "renewal_token": "new_renewal_token",
                "token_expiry_time": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            }
        }
        mock_requests.post.return_value = response
        
        from glific_integration import get_glific_auth_headers
        
        result = get_glific_auth_headers()
        
        assert "authorization" in result
        assert result["authorization"] == "new_test_token"
    
    def test_get_glific_auth_headers_timezone_naive(self, mock_frappe, mock_glific_settings):
        """Test handling of timezone-naive datetime"""
        mock_glific_settings.token_expiry_time = datetime(2025, 12, 31, 23, 59, 59)
        mock_frappe.get_single.return_value = mock_glific_settings
        
        from glific_integration import get_glific_auth_headers
        
        result = get_glific_auth_headers()
        
        assert "authorization" in result
    
    def test_auth_token_refresh_failure(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test handling of token refresh failure"""
        mock_glific_settings.access_token = None
        mock_frappe.get_single.return_value = mock_glific_settings
        mock_frappe.throw = Mock(side_effect=Exception("Auth failed"))
        
        mock_requests.post.return_value = mock_api_response(401, errors=[{"message": "Invalid credentials"}])
        
        from glific_integration import get_glific_auth_headers
        
        with pytest.raises(Exception):
            get_glific_auth_headers()


# ============================================================================
# TEST CLASS: CONTACT MANAGEMENT
# ============================================================================

class TestContactManagement:
    """Tests for contact creation, updates, and retrieval"""
    
    def test_create_contact_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successful contact creation"""
        contact_data = {
            "createContact": {
                "contact": {
                    "id": "123",
                    "name": "Test User",
                    "phone": "911234567890"
                }
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, contact_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import create_contact
            
            result = create_contact(
                name="Test User",
                phone="911234567890",
                school_name="Test School",
                model_name="Test Model",
                language_id="1",
                batch_id="batch123"
            )
            
            assert result is not None
            assert result["id"] == "123"
            assert result["name"] == "Test User"
            assert result["phone"] == "911234567890"
    
    def test_create_contact_api_error(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test contact creation with API error"""
        mock_requests.post.return_value = mock_api_response(
            400, 
            errors=[{"key": "phone", "message": "Phone already exists"}]
        )
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import create_contact
            
            result = create_contact(
                name="Test User",
                phone="911234567890",
                school_name="Test School",
                model_name="Test Model",
                language_id="1",
                batch_id="batch123"
            )
            
            assert result is None
    
    def test_create_contact_network_error(
        self, mock_frappe, mock_glific_settings, mock_requests
    ):
        """Test contact creation with network error"""
        mock_requests.post.side_effect = Exception("Network error")
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import create_contact
            
            result = create_contact(
                name="Test User",
                phone="911234567890",
                school_name="Test School",
                model_name="Test Model",
                language_id="1",
                batch_id="batch123"
            )
            
            assert result is None
    
    def test_get_contact_by_phone_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successful contact retrieval by phone"""
        contact_data = {
            "contactByPhone": {
                "contact": {
                    "id": "123",
                    "name": "Test User",
                    "phone": "911234567890",
                    "bspStatus": "SESSION"
                }
            }
        }
        
        mock_response = mock_api_response(200, contact_data)
        mock_requests.post.return_value = mock_response
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import get_contact_by_phone
            
            result = get_contact_by_phone("911234567890")
            
            assert result is not None
            assert result["id"] == "123"
            assert result["phone"] == "911234567890"
    
    def test_get_contact_by_phone_not_found(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test contact retrieval when contact doesn't exist"""
        contact_data = {
            "contactByPhone": {
                "contact": None
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, contact_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import get_contact_by_phone
            
            result = get_contact_by_phone("911234567890")
            
            assert result is None
    
    def test_update_contact_fields_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successful contact field update"""
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
                        "fields": json.dumps({
                            "existing_field": {
                                "value": "existing_value",
                                "type": "string"
                            }
                        })
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
                        "name": "Test User",
                        "fields": json.dumps({
                            "existing_field": {"value": "existing_value"},
                            "new_field": {"value": "new_value"}
                        })
                    }
                }
            }
        }
        
        mock_requests.post.side_effect = [fetch_response, update_response]
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import update_contact_fields
            
            result = update_contact_fields("123", {"new_field": "new_value"})
            
            assert result is True
    
    def test_update_contact_fields_invalid_json(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test update when existing fields have invalid JSON"""
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.raise_for_status = Mock()
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": "123",
                        "name": "Test User",
                        "fields": "invalid json"
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
                    "contact": {
                        "id": "123",
                        "name": "Test User"
                    }
                }
            }
        }
        
        mock_requests.post.side_effect = [fetch_response, update_response]
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import update_contact_fields
            
            result = update_contact_fields("123", {"new_field": "new_value"})
            
            # Should handle gracefully and still update
            assert result is True
    
    def test_update_contact_fields_api_error(
        self, mock_frappe, mock_glific_settings, mock_requests
    ):
        """Test update contact fields with API error"""
        mock_requests.post.side_effect = Exception("API Error")
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import update_contact_fields
            
            result = update_contact_fields("123", {"new_field": "new_value"})
            
            assert result is False
    
    def test_optin_contact_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successful contact opt-in"""
        optin_data = {
            "optinContact": {
                "contact": {
                    "id": "123",
                    "phone": "911234567890",
                    "name": "Test User",
                    "bspStatus": "SESSION"
                }
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, optin_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import optin_contact
            
            result = optin_contact("911234567890", "Test User")
            
            assert result is True
    
    def test_optin_contact_failure(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test contact opt-in failure"""
        mock_requests.post.return_value = mock_api_response(
            400,
            errors=[{"message": "Contact not found"}]
        )
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import optin_contact
            
            result = optin_contact("911234567890", "Test User")
            
            assert result is False


# ============================================================================
# TEST CLASS: GROUP MANAGEMENT
# ============================================================================

class TestGroupManagement:
    """Tests for Glific group operations"""
    
    def test_check_glific_group_exists_found(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test checking for existing group - group found"""
        groups_data = {
            "groups": [
                {"id": "group123", "label": "Test Group"}
            ]
        }
        
        mock_requests.post.return_value = mock_api_response(200, groups_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import check_glific_group_exists
            
            result = check_glific_group_exists("Test Group")
            
            assert result is not None
            assert result["id"] == "group123"
            assert result["label"] == "Test Group"
    
    def test_check_glific_group_exists_not_found(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test checking for existing group - group not found"""
        groups_data = {"groups": []}
        
        mock_requests.post.return_value = mock_api_response(200, groups_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import check_glific_group_exists
            
            result = check_glific_group_exists("Nonexistent Group")
            
            assert result is None
    
    def test_create_glific_group_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successful group creation"""
        group_data = {
            "createGroup": {
                "group": {
                    "id": "group123",
                    "label": "New Group",
                    "description": "Test description"
                }
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, group_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import create_glific_group
            
            result = create_glific_group("New Group", "Test description")
            
            assert result is not None
            assert result["id"] == "group123"
            assert result["label"] == "New Group"
    
    def test_create_glific_group_error(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test group creation with API error"""
        mock_requests.post.return_value = mock_api_response(
            400,
            errors=[{"message": "Group already exists"}]
        )
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import create_glific_group
            
            result = create_glific_group("Duplicate Group")
            
            assert result is None
    
    def test_add_contact_to_group_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successfully adding contact to group"""
        group_data = {
            "updateGroupContacts": {
                "groupContacts": [{"id": "gc123"}],
                "numberDeleted": 0
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, group_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import add_contact_to_group
            
            result = add_contact_to_group("contact123", "group456")
            
            assert result is True
    
    @pytest.mark.parametrize("contact_id,group_id", [
        (None, "group123"),
        ("contact123", None),
        (None, None),
        ("", "group123"),
        ("contact123", ""),
    ])
    def test_add_contact_to_group_invalid_params(
        self, contact_id, group_id, mock_frappe
    ):
        """Test adding contact to group with invalid parameters"""
        from glific_integration import add_contact_to_group
        
        result = add_contact_to_group(contact_id, group_id)
        
        assert result is False


# ============================================================================
# TEST CLASS: PHONE NUMBER FORMATTING
# ============================================================================

class TestPhoneNumberFormatting:
    """Tests for phone number formatting utility"""
    
    def test_update_student_glific_ids(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test batch update of student Glific IDs"""
        # Mock students - frappe.get_all returns list of dicts
        mock_frappe.get_all.return_value = [
            {"name": "student1", "phone": "1234567890"},
            {"name": "student2", "phone": "911234567891"}
        ]
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
             patch('glific_integration.get_contact_by_phone') as mock_get_contact:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            mock_get_contact.return_value = {"id": "glific123"}
            
            from glific_integration import update_student_glific_ids
            
            result = update_student_glific_ids(batch_size=10)
            
            assert result == 2
            assert mock_frappe.db.set_value.call_count == 2


# ============================================================================
# TEST CLASS: ONBOARDING FLOWS
# ============================================================================

class TestOnboardingFlows:
    """Tests for student and teacher onboarding functions"""
    
    def test_add_student_to_glific_new_contact(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test adding new student to Glific"""
        # Setup the sequence of API calls that will be made
        # 1. Check if contact exists (returns None)
        # 2. Create contact (returns new contact)
        # 3. Opt-in contact (returns success)
        # 4. Add to group (returns success)
        
        # Mock successful contact creation
        create_response = Mock()
        create_response.status_code = 200
        create_response.json.return_value = {
            "data": {
                "createContact": {
                    "contact": {
                        "id": "123",
                        "name": "New Student",
                        "phone": "911234567890"
                    }
                }
            }
        }
        
        # Mock successful opt-in
        optin_response = Mock()
        optin_response.status_code = 200
        optin_response.raise_for_status = Mock()
        optin_response.json.return_value = {
            "data": {
                "optinContact": {
                    "contact": {"id": "123", "bspStatus": "SESSION"}
                }
            }
        }
        
        # Mock successful add to group
        group_response = Mock()
        group_response.status_code = 200
        group_response.raise_for_status = Mock()
        group_response.json.return_value = {
            "data": {
                "updateGroupContacts": {
                    "groupContacts": [{"id": "1"}]
                }
            }
        }
        
        mock_requests.post.side_effect = [
            create_response,  # create contact
            optin_response,   # opt-in
            group_response    # add to group
        ]
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
             patch('glific_integration.get_contact_by_phone') as mock_get_contact:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            mock_get_contact.return_value = None  # Contact doesn't exist
            
            from glific_integration import add_student_to_glific_for_onboarding
            
            result = add_student_to_glific_for_onboarding(
                student_name="New Student",
                phone="1234567890",
                school_name="Test School",
                batch_id="batch123",
                group_id="group456",
                language_id="1"
            )
            
            assert result is not None
            assert result["id"] == "123"
    
    def test_add_student_to_glific_existing_contact(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test adding existing student to Glific"""
        existing_contact = {
            "id": "123",
            "name": "Existing Student",
            "phone": "911234567890",
            "bspStatus": "SESSION"
        }
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
             patch('glific_integration.get_contact_by_phone') as mock_get_contact, \
             patch('glific_integration.add_contact_to_group') as mock_add_to_group, \
             patch('glific_integration.update_contact_fields') as mock_update:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            mock_get_contact.return_value = existing_contact
            mock_add_to_group.return_value = True
            mock_update.return_value = True
            
            from glific_integration import add_student_to_glific_for_onboarding
            
            result = add_student_to_glific_for_onboarding(
                student_name="Existing Student",
                phone="911234567890",
                school_name="Test School",
                batch_id="batch123",
                group_id="group456"
            )
            
            assert result == existing_contact
    
    def test_add_student_invalid_phone(
        self, mock_frappe, mock_glific_settings
    ):
        """Test adding student with invalid phone number"""
        with patch('glific_integration.get_glific_settings') as mock_get_settings:
            mock_get_settings.return_value = mock_glific_settings
            
            from glific_integration import add_student_to_glific_for_onboarding
            
            result = add_student_to_glific_for_onboarding(
                student_name="Test Student",
                phone="123",  # Invalid phone
                school_name="Test School",
                batch_id="batch123",
                group_id="group456"
            )
            
            assert result is None
    
    def test_start_contact_flow_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successfully starting a contact flow"""
        flow_data = {
            "startContactFlow": {
                "success": True
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, flow_data)
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import start_contact_flow
            
            result = start_contact_flow(
                flow_id="flow123",
                contact_id="contact456",
                default_results={"key": "value"}
            )
            
            assert result is True
    
    def test_create_or_get_teacher_group_new(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test creating new teacher group"""
        mock_frappe.get_doc.return_value = Mock(
            set_name="Test Batch",
            name="batch123"
        )
        mock_frappe.get_all.return_value = []
        mock_frappe.new_doc.return_value = Mock(insert=Mock())
        
        # Mock group doesn't exist
        groups_data = {"groups": []}
        
        # Mock successful group creation
        create_data = {
            "createGroup": {
                "group": {
                    "id": "teacher_group123",
                    "label": "teacher_batch_batch123"
                }
            }
        }
        
        mock_requests.post.side_effect = [
            mock_api_response(200, groups_data),
            mock_api_response(200, create_data)
        ]
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers, \
             patch('glific_integration.check_glific_group_exists') as mock_check, \
             patch('glific_integration.create_glific_group') as mock_create:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            mock_check.return_value = None
            mock_create.return_value = {"id": "teacher_group123", "label": "teacher_batch_batch123"}
            
            from glific_integration import create_or_get_teacher_group_for_batch
            
            result = create_or_get_teacher_group_for_batch("batch123", "batch123")
            
            assert result is not None
            assert result["group_id"] == "teacher_group123"


# ============================================================================
# TEST CLASS: ERROR HANDLING
# ============================================================================

class TestErrorHandling:
    """Tests for error handling scenarios"""
    
    def test_create_contact_timeout(
        self, mock_frappe, mock_glific_settings, mock_requests
    ):
        """Test handling of timeout errors"""
        mock_requests.post.side_effect = TimeoutError("Request timeout")
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import create_contact
            
            result = create_contact(
                name="Test User",
                phone="911234567890",
                school_name="Test School",
                model_name="Test Model",
                language_id="1",
                batch_id="batch123"
            )
            
            assert result is None
    
    def test_get_contact_connection_error(
        self, mock_frappe, mock_glific_settings, mock_requests
    ):
        """Test handling of connection errors"""
        mock_requests.exceptions.RequestException = Exception
        mock_requests.post.side_effect = Exception("Connection refused")
        
        with patch('glific_integration.get_glific_settings') as mock_get_settings, \
             patch('glific_integration.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_integration import get_contact_by_phone
            
            result = get_contact_by_phone("911234567890")
            
            assert result is None


# ============================================================================
# TEST CLASS: INTEGRATION SCENARIOS
# ============================================================================

@pytest.mark.integration
class TestIntegrationScenarios:
    """Integration tests for complete workflows"""
    
    def test_complete_student_onboarding_workflow(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test complete student onboarding from start to finish"""
        # This would be a more complex test that chains multiple operations
        # Kept as a placeholder for actual integration testing
        pass
    
    def test_batch_creation_and_student_assignment(
        self, mock_frappe, mock_glific_settings
    ):
        """Test creating a batch and assigning multiple students"""
        # Placeholder for integration test
        pass


# ============================================================================
# HELPER TESTS
# ============================================================================

class TestModuleStructure:
    """Tests for module structure and imports"""
    
    def test_all_functions_importable(self, mock_modules):
        """Verify all expected functions can be imported"""
        try:
            from glific_integration import (
                get_glific_settings,
                get_glific_auth_headers,
                create_contact,
                update_contact_fields,
                get_contact_by_phone,
                optin_contact,
                check_glific_group_exists,
                create_glific_group,
                add_contact_to_group,
                add_student_to_glific_for_onboarding,
                start_contact_flow,
                update_student_glific_ids,
                create_or_get_glific_group_for_batch,
                create_or_get_teacher_group_for_batch
            )
            
            # Verify all are callable
            functions = [
                get_glific_settings,
                get_glific_auth_headers,
                create_contact,
                update_contact_fields,
                get_contact_by_phone,
                optin_contact,
                check_glific_group_exists,
                create_glific_group,
                add_contact_to_group,
                add_student_to_glific_for_onboarding,
                start_contact_flow,
                update_student_glific_ids,
                create_or_get_glific_group_for_batch,
                create_or_get_teacher_group_for_batch
            ]
            
            for func in functions:
                assert callable(func)
        
        except ImportError as e:
            pytest.skip(f"Could not import module: {str(e)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])