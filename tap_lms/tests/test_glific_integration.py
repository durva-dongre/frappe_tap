import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone, timedelta
import json
import requests

# Import your module here - adjust the import path as needed
# from your_module import (
#     get_glific_settings, get_glific_auth_headers, create_contact,
#     update_contact_fields, get_contact_by_phone, optin_contact,
#     check_glific_group_exists, create_glific_group, add_contact_to_group,
#     add_student_to_glific_for_onboarding, create_or_get_glific_group_for_batch,
#     create_or_get_teacher_group_for_batch
# )


class TestGlificIntegration(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_settings = Mock()
        self.mock_settings.api_url = "https://api.example.com"
        self.mock_settings.phone_number = "1234567890"
        self.mock_settings.password = "test_password"
        self.mock_settings.access_token = "test_token"
        self.mock_settings.renewal_token = "renewal_token"
        self.mock_settings.token_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)
        self.mock_settings.name = "test_settings"
        self.mock_settings.default_language_id = "1"

    @patch('your_module.frappe')
    def test_get_glific_settings(self, mock_frappe):
        """Test getting Glific settings."""
        from your_module import get_glific_settings
        
        mock_frappe.get_single.return_value = self.mock_settings
        
        result = get_glific_settings()
        
        mock_frappe.get_single.assert_called_once_with("Glific Settings")
        self.assertEqual(result, self.mock_settings)

    @patch('your_module.requests.post')
    @patch('your_module.frappe')
    def test_get_glific_auth_headers_with_valid_token(self, mock_frappe, mock_post):
        """Test getting auth headers when token is valid."""
        from your_module import get_glific_auth_headers
        
        mock_frappe.get_single.return_value = self.mock_settings
        
        result = get_glific_auth_headers()
        
        expected_headers = {
            "authorization": "test_token",
            "Content-Type": "application/json"
        }
        self.assertEqual(result, expected_headers)
        mock_post.assert_not_called()

    @patch('your_module.requests.post')
    @patch('your_module.frappe')
    def test_get_glific_auth_headers_token_expired(self, mock_frappe, mock_post):
        """Test getting auth headers when token is expired."""
        from your_module import get_glific_auth_headers
        
        # Set expired token
        self.mock_settings.token_expiry_time = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_frappe.get_single.return_value = self.mock_settings
        
        # Mock successful authentication response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "access_token": "new_token",
                "renewal_token": "new_renewal",
                "token_expiry_time": "2024-12-31T23:59:59Z"
            }
        }
        mock_post.return_value = mock_response
        
        result = get_glific_auth_headers()
        
        expected_headers = {
            "authorization": "new_token",
            "Content-Type": "application/json"
        }
        self.assertEqual(result, expected_headers)
        mock_post.assert_called_once()

    @patch('your_module.requests.post')
    @patch('your_module.frappe')
    def test_get_glific_auth_headers_authentication_failed(self, mock_frappe, mock_post):
        """Test authentication failure scenario."""
        from your_module import get_glific_auth_headers
        
        self.mock_settings.access_token = None
        mock_frappe.get_single.return_value = self.mock_settings
        
        # Mock failed authentication response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response
        
        with self.assertRaises(Exception):
            get_glific_auth_headers()

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    @patch('your_module.frappe')
    def test_create_contact_success(self, mock_frappe, mock_settings, mock_auth, mock_post):
        """Test successful contact creation."""
        from your_module import create_contact
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
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
                        "phone": "919876543210"
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        
        result = create_contact("Test User", "919876543210", "Test School", "Test Model", "1", "batch123")
        
        self.assertEqual(result["id"], "123")
        self.assertEqual(result["name"], "Test User")
        mock_post.assert_called_once()

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    @patch('your_module.frappe')
    def test_create_contact_with_errors(self, mock_frappe, mock_settings, mock_auth, mock_post):
        """Test contact creation with API errors."""
        from your_module import create_contact
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "error"
        mock_response.json.return_value = {
            "errors": [{"message": "Contact creation failed"}]
        }
        mock_post.return_value = mock_response
        
        result = create_contact("Test User", "919876543210", "Test School", "Test Model", "1", "batch123")
        
        self.assertIsNone(result)

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_get_contact_by_phone_success(self, mock_settings, mock_auth, mock_post):
        """Test successful contact retrieval by phone."""
        from your_module import get_contact_by_phone
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "contactByPhone": {
                    "contact": {
                        "id": "123",
                        "name": "Test User",
                        "phone": "919876543210",
                        "bspStatus": "SESSION"
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        mock_response.raise_for_status = Mock()
        
        result = get_contact_by_phone("919876543210")
        
        self.assertEqual(result["id"], "123")
        self.assertEqual(result["bspStatus"], "SESSION")

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_get_contact_by_phone_not_found(self, mock_settings, mock_auth, mock_post):
        """Test contact not found scenario."""
        from your_module import get_contact_by_phone
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "contactByPhone": {
                    "contact": None
                }
            }
        }
        mock_post.return_value = mock_response
        mock_response.raise_for_status = Mock()
        
        result = get_contact_by_phone("919876543210")
        
        self.assertIsNone(result)

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_optin_contact_success(self, mock_settings, mock_auth, mock_post):
        """Test successful contact opt-in."""
        from your_module import optin_contact
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "optinContact": {
                    "contact": {
                        "id": "123",
                        "phone": "919876543210",
                        "bspStatus": "SESSION"
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        mock_response.raise_for_status = Mock()
        
        result = optin_contact("919876543210", "Test User")
        
        self.assertTrue(result)

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_update_contact_fields_success(self, mock_settings, mock_auth, mock_post):
        """Test successful contact field update."""
        from your_module import update_contact_fields
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        # Mock fetch contact response
        fetch_response = Mock()
        fetch_response.status_code = 200
        fetch_response.json.return_value = {
            "data": {
                "contact": {
                    "contact": {
                        "id": "123",
                        "name": "Test User",
                        "fields": '{"existing_field": {"value": "existing_value", "type": "string"}}'
                    }
                }
            }
        }
        
        # Mock update contact response
        update_response = Mock()
        update_response.status_code = 200
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
        
        mock_post.side_effect = [fetch_response, update_response]
        fetch_response.raise_for_status = Mock()
        update_response.raise_for_status = Mock()
        
        fields_to_update = {"new_field": "new_value"}
        result = update_contact_fields("123", fields_to_update)
        
        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_check_glific_group_exists_found(self, mock_settings, mock_auth, mock_post):
        """Test checking if group exists - found."""
        from your_module import check_glific_group_exists
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "groups": [
                    {"id": "456", "label": "Test Group"}
                ]
            }
        }
        mock_post.return_value = mock_response
        mock_response.raise_for_status = Mock()
        
        result = check_glific_group_exists("Test Group")
        
        self.assertEqual(result["id"], "456")
        self.assertEqual(result["label"], "Test Group")

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_create_glific_group_success(self, mock_settings, mock_auth, mock_post):
        """Test successful group creation."""
        from your_module import create_glific_group
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "createGroup": {
                    "group": {
                        "id": "789",
                        "label": "New Group",
                        "description": "Test Description"
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        mock_response.raise_for_status = Mock()
        
        result = create_glific_group("New Group", "Test Description")
        
        self.assertEqual(result["id"], "789")
        self.assertEqual(result["label"], "New Group")

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_add_contact_to_group_success(self, mock_settings, mock_auth, mock_post):
        """Test successfully adding contact to group."""
        from your_module import add_contact_to_group
        
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "updateGroupContacts": {
                    "groupContacts": [{"id": "contact_group_123"}]
                }
            }
        }
        mock_post.return_value = mock_response
        mock_response.raise_for_status = Mock()
        
        result = add_contact_to_group("123", "456")
        
        self.assertTrue(result)

    @patch('your_module.get_contact_by_phone')
    @patch('your_module.optin_contact')
    @patch('your_module.add_contact_to_group')
    @patch('your_module.update_contact_fields')
    @patch('your_module.frappe')
    def test_add_student_to_glific_existing_contact(self, mock_frappe, mock_update, mock_add_group, mock_optin, mock_get_contact):
        """Test adding student when contact already exists."""
        from your_module import add_student_to_glific_for_onboarding
        
        # Mock existing contact
        existing_contact = {
            "id": "123",
            "name": "Test Student",
            "phone": "919876543210",
            "bspStatus": "SESSION"
        }
        mock_get_contact.return_value = existing_contact
        mock_add_group.return_value = True
        mock_update.return_value = True
        
        result = add_student_to_glific_for_onboarding(
            "Test Student", "9876543210", "Test School", "batch123", "group456", "1"
        )
        
        self.assertEqual(result, existing_contact)
        mock_get_contact.assert_called_once_with("919876543210")
        mock_add_group.assert_called_once_with("123", "group456")
        mock_optin.assert_not_called()  # Contact already opted in

    @patch('your_module.get_contact_by_phone')
    @patch('your_module.optin_contact')
    @patch('your_module.add_contact_to_group')
    @patch('your_module.update_contact_fields')
    @patch('your_module.frappe')
    def test_add_student_to_glific_existing_contact_needs_optin(self, mock_frappe, mock_update, mock_add_group, mock_optin, mock_get_contact):
        """Test adding student when contact exists but needs opt-in."""
        from your_module import add_student_to_glific_for_onboarding
        
        # Mock existing contact that needs opt-in
        existing_contact = {
            "id": "123",
            "name": "Test Student",
            "phone": "919876543210",
            "bspStatus": "NONE"
        }
        mock_get_contact.return_value = existing_contact
        mock_optin.return_value = True
        mock_add_group.return_value = True
        mock_update.return_value = True
        
        result = add_student_to_glific_for_onboarding(
            "Test Student", "9876543210", "Test School", "batch123", "group456", "1"
        )
        
        self.assertEqual(result, existing_contact)
        mock_optin.assert_called_once_with("919876543210", "Test Student")

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    @patch('your_module.get_contact_by_phone')
    @patch('your_module.optin_contact')
    @patch('your_module.add_contact_to_group')
    @patch('your_module.frappe')
    def test_add_student_to_glific_create_new_contact(self, mock_frappe, mock_add_group, mock_optin, mock_get_contact, mock_settings, mock_auth, mock_post):
        """Test creating new contact for student."""
        from your_module import add_student_to_glific_for_onboarding
        
        mock_get_contact.return_value = None  # No existing contact
        mock_settings.return_value = self.mock_settings
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        # Mock successful contact creation
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "createContact": {
                    "contact": {
                        "id": "new123",
                        "name": "New Student",
                        "phone": "919876543210"
                    }
                }
            }
        }
        mock_post.return_value = mock_response
        
        mock_optin.return_value = True
        mock_add_group.return_value = True
        
        result = add_student_to_glific_for_onboarding(
            "New Student", "9876543210", "Test School", "batch123", "group456", "1"
        )
        
        self.assertEqual(result["id"], "new123")
        mock_optin.assert_called_once_with("919876543210", "New Student")
        mock_add_group.assert_called_once_with("new123", "group456")

    def test_add_student_invalid_phone(self):
        """Test adding student with invalid phone number."""
        from your_module import add_student_to_glific_for_onboarding
        
        result = add_student_to_glific_for_onboarding(
            "Test Student", "invalid", "Test School", "batch123", "group456", "1"
        )
        
        self.assertIsNone(result)

    @patch('your_module.check_glific_group_exists')
    @patch('your_module.create_glific_group')
    @patch('your_module.frappe')
    def test_create_or_get_glific_group_for_batch_existing_mapping(self, mock_frappe, mock_create_group, mock_check_group):
        """Test getting existing group mapping for batch."""
        from your_module import create_or_get_glific_group_for_batch
        
        # Mock existing mapping
        mock_frappe.get_all.return_value = [{
            "name": "mapping1",
            "group_id": "existing_group_123",
            "label": "Set: Test Batch"
        }]
        
        result = create_or_get_glific_group_for_batch("batch_set_id")
        
        self.assertEqual(result["group_id"], "existing_group_123")
        self.assertEqual(result["label"], "Set: Test Batch")
        mock_check_group.assert_not_called()
        mock_create_group.assert_not_called()

    @patch('your_module.check_glific_group_exists')
    @patch('your_module.create_glific_group')
    @patch('your_module.frappe')
    def test_create_or_get_glific_group_for_batch_create_new(self, mock_frappe, mock_create_group, mock_check_group):
        """Test creating new group for batch."""
        from your_module import create_or_get_glific_group_for_batch
        
        # Mock no existing mapping
        mock_frappe.get_all.return_value = []
        
        # Mock batch document
        mock_set = Mock()
        mock_set.set_name = "Test Batch"
        mock_frappe.get_doc.return_value = mock_set
        
        # Mock no existing group in Glific
        mock_check_group.return_value = None
        
        # Mock successful group creation
        mock_create_group.return_value = {
            "id": "new_group_456",
            "label": "Set: Test Batch"
        }
        
        # Mock new document creation
        mock_doc = Mock()
        mock_frappe.new_doc.return_value = mock_doc
        
        result = create_or_get_glific_group_for_batch("batch_set_id")
        
        self.assertEqual(result["group_id"], "new_group_456")
        self.assertEqual(result["label"], "Set: Test Batch")
        mock_create_group.assert_called_once()
        mock_doc.insert.assert_called_once()

    @patch('your_module.check_glific_group_exists')
    @patch('your_module.create_glific_group')
    @patch('your_module.frappe')
    def test_create_or_get_teacher_group_for_batch_invalid_data(self, mock_frappe, mock_create_group, mock_check_group):
        """Test teacher group creation with invalid batch data."""
        from your_module import create_or_get_teacher_group_for_batch
        
        # Test with no active batch
        result = create_or_get_teacher_group_for_batch("batch_name", "no_active_batch_id")
        self.assertIsNone(result)
        
        # Test with None batch_id
        result = create_or_get_teacher_group_for_batch("batch_name", None)
        self.assertIsNone(result)
        
        # Test with empty batch_name
        result = create_or_get_teacher_group_for_batch("", "valid_batch_id")
        self.assertIsNone(result)

    def test_phone_number_formatting_in_add_student(self):
        """Test phone number formatting logic."""
        from your_module import add_student_to_glific_for_onboarding
        
        # Test with 10-digit number
        with patch('your_module.get_contact_by_phone') as mock_get:
            mock_get.return_value = {"id": "123", "bspStatus": "SESSION"}
            add_student_to_glific_for_onboarding("Test", "9876543210", "School", "batch", "group", "1")
            mock_get.assert_called_with("919876543210")
        
        # Test with already formatted 12-digit number
        with patch('your_module.get_contact_by_phone') as mock_get:
            mock_get.return_value = {"id": "123", "bspStatus": "SESSION"}
            add_student_to_glific_for_onboarding("Test", "919876543210", "School", "batch", "group", "1")
            mock_get.assert_called_with("919876543210")


class TestGlificIntegrationEdgeCases(unittest.TestCase):
    """Test edge cases and error scenarios."""
    
    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_network_timeout_handling(self, mock_settings, mock_auth, mock_post):
        """Test network timeout handling."""
        from your_module import get_contact_by_phone
        
        mock_settings.return_value = Mock(api_url="https://api.example.com")
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        # Mock network timeout
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = get_contact_by_phone("919876543210")
        
        self.assertIsNone(result)

    @patch('your_module.requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_malformed_json_response(self, mock_settings, mock_auth, mock_post):
        """Test handling of malformed JSON responses."""
        from your_module import get_contact_by_phone
        
        mock_settings.return_value = Mock(api_url="https://api.example.com")
        mock_auth.return_value = {"authorization": "token", "Content-Type": "application/json"}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_post.return_value = mock_response
        
        result = get_contact_by_phone("919876543210")
        
        self.assertIsNone(result)

    @patch('your_module.frappe')
    def test_database_error_handling(self, mock_frappe):
        """Test database error handling."""
        from your_module import get_glific_settings
        
        # Mock database error
        mock_frappe.get_single.side_effect = Exception("Database connection failed")
        
        with self.assertRaises(Exception):
            get_glific_settings()
