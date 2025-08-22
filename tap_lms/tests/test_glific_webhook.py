import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import frappe
from your_module import update_glific_contact, get_glific_contact, prepare_update_payload, send_glific_update


class TestGlificIntegration(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.sample_teacher_doc = Mock()
        self.sample_teacher_doc.doctype = "Teacher"
        self.sample_teacher_doc.name = "TEST-001"
        self.sample_teacher_doc.glific_id = "123"
        self.sample_teacher_doc.language = "English"
        self.sample_teacher_doc.get.side_effect = lambda field: {
            "language": "English",
            "phone": "1234567890",
            "email": "test@example.com",
            "name": "John Doe"
        }.get(field)
        
        self.sample_glific_contact = {
            "id": "123",
            "name": "John Doe",
            "language": {"id": "1", "label": "English"},
            "fields": json.dumps({
                "phone": {"value": "1234567890", "type": "string"},
                "email": {"value": "old@example.com", "type": "string"}
            })
        }
        
        self.sample_field_mappings = [
            {"frappe_field": "phone", "glific_field": "phone"},
            {"frappe_field": "email", "glific_field": "email"}
        ]

    @patch('your_module.send_glific_update')
    @patch('your_module.prepare_update_payload')
    @patch('your_module.get_glific_contact')
    @patch('frappe.logger')
    def test_update_glific_contact_success(self, mock_logger, mock_get_contact, 
                                         mock_prepare_payload, mock_send_update):
        """Test successful update of Glific contact"""
        # Arrange
        mock_get_contact.return_value = self.sample_glific_contact
        mock_prepare_payload.return_value = {"fields": json.dumps({"email": {"value": "test@example.com"}})}
        mock_send_update.return_value = True
        
        # Act
        update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_get_contact.assert_called_once_with("123")
        mock_prepare_payload.assert_called_once_with(self.sample_teacher_doc, self.sample_glific_contact)
        mock_send_update.assert_called_once()
        mock_logger().info.assert_called_with("Successfully updated Glific contact for teacher TEST-001")

    @patch('your_module.get_glific_contact')
    @patch('frappe.logger')
    def test_update_glific_contact_not_teacher_doctype(self, mock_logger, mock_get_contact):
        """Test that function returns early if doctype is not Teacher"""
        # Arrange
        non_teacher_doc = Mock()
        non_teacher_doc.doctype = "Student"
        
        # Act
        update_glific_contact(non_teacher_doc, "on_update")
        
        # Assert
        mock_get_contact.assert_not_called()
        mock_logger.assert_not_called()

    @patch('your_module.get_glific_contact')
    @patch('frappe.logger')
    def test_update_glific_contact_no_glific_contact_found(self, mock_logger, mock_get_contact):
        """Test handling when Glific contact is not found"""
        # Arrange
        mock_get_contact.return_value = None
        
        # Act
        update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().error.assert_called_with("Glific contact not found for teacher TEST-001")

    @patch('your_module.prepare_update_payload')
    @patch('your_module.get_glific_contact')
    @patch('frappe.logger')
    def test_update_glific_contact_no_updates_needed(self, mock_logger, mock_get_contact, mock_prepare_payload):
        """Test handling when no updates are needed"""
        # Arrange
        mock_get_contact.return_value = self.sample_glific_contact
        mock_prepare_payload.return_value = None
        
        # Act
        update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().info.assert_called_with("No updates needed for Glific contact 123")

    @patch('your_module.send_glific_update')
    @patch('your_module.prepare_update_payload')
    @patch('your_module.get_glific_contact')
    @patch('frappe.logger')
    def test_update_glific_contact_send_update_fails(self, mock_logger, mock_get_contact, 
                                                   mock_prepare_payload, mock_send_update):
        """Test handling when sending update to Glific fails"""
        # Arrange
        mock_get_contact.return_value = self.sample_glific_contact
        mock_prepare_payload.return_value = {"fields": json.dumps({"email": {"value": "test@example.com"}})}
        mock_send_update.return_value = False
        
        # Act
        update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().error.assert_called_with("Failed to update Glific contact for teacher TEST-001")

    @patch('your_module.get_glific_contact')
    @patch('frappe.logger')
    def test_update_glific_contact_exception_handling(self, mock_logger, mock_get_contact):
        """Test exception handling in update_glific_contact"""
        # Arrange
        mock_get_contact.side_effect = Exception("API Error")
        
        # Act
        update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().error.assert_called_with("Error updating Glific contact for teacher TEST-001: API Error")

    @patch('requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_get_glific_contact_success(self, mock_settings, mock_headers, mock_post):
        """Test successful retrieval of Glific contact"""
        # Arrange
        mock_settings.return_value.api_url = "https://api.glific.com"
        mock_headers.return_value = {"Authorization": "Bearer token"}
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"contact": {"contact": self.sample_glific_contact}}}
        mock_post.return_value = mock_response
        
        # Act
        result = get_glific_contact("123")
        
        # Assert
        self.assertEqual(result, self.sample_glific_contact)
        mock_post.assert_called_once()

    @patch('requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_get_glific_contact_api_error(self, mock_settings, mock_headers, mock_post):
        """Test handling of API error in get_glific_contact"""
        # Arrange
        mock_settings.return_value.api_url = "https://api.glific.com"
        mock_headers.return_value = {"Authorization": "Bearer token"}
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        # Act
        result = get_glific_contact("123")
        
        # Assert
        self.assertIsNone(result)

    @patch('frappe.utils.now_datetime')
    @patch('frappe.db.get_value')
    @patch('frappe.get_all')
    def test_prepare_update_payload_with_field_updates(self, mock_get_all, mock_db_get_value, mock_now):
        """Test preparing update payload with field changes"""
        # Arrange
        mock_get_all.return_value = self.sample_field_mappings
        mock_db_get_value.return_value = "1"
        mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        
        # Act
        result = prepare_update_payload(self.sample_teacher_doc, self.sample_glific_contact)
        
        # Assert
        self.assertIsNotNone(result)
        self.assertIn("fields", result)
        fields = json.loads(result["fields"])
        self.assertEqual(fields["email"]["value"], "test@example.com")

    @patch('frappe.db.get_value')
    @patch('frappe.get_all')
    def test_prepare_update_payload_with_language_change(self, mock_get_all, mock_db_get_value):
        """Test preparing update payload with language change"""
        # Arrange
        mock_get_all.return_value = []
        mock_db_get_value.return_value = "2"  # Different language ID
        
        # Act
        result = prepare_update_payload(self.sample_teacher_doc, self.sample_glific_contact)
        
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result["languageId"], 2)

    @patch('frappe.db.get_value')
    @patch('frappe.get_all')
    def test_prepare_update_payload_no_changes(self, mock_get_all, mock_db_get_value):
        """Test preparing update payload when no changes are needed"""
        # Arrange
        mock_get_all.return_value = [{"frappe_field": "phone", "glific_field": "phone"}]
        mock_db_get_value.return_value = "1"  # Same language ID
        
        # Modify teacher doc to have same phone as in Glific
        self.sample_teacher_doc.get.side_effect = lambda field: {
            "language": "English",
            "phone": "1234567890"  # Same as in glific_contact
        }.get(field)
        
        # Act
        result = prepare_update_payload(self.sample_teacher_doc, self.sample_glific_contact)
        
        # Assert
        self.assertIsNone(result)

    @patch('frappe.utils.now_datetime')
    @patch('frappe.db.get_value')
    @patch('frappe.get_all')
    def test_prepare_update_payload_new_field(self, mock_get_all, mock_db_get_value, mock_now):
        """Test preparing update payload with new field addition"""
        # Arrange
        mock_get_all.return_value = [{"frappe_field": "address", "glific_field": "address"}]
        mock_db_get_value.return_value = "1"
        mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        
        self.sample_teacher_doc.get.side_effect = lambda field: {
            "language": "English",
            "address": "123 Main St"
        }.get(field)
        
        # Act
        result = prepare_update_payload(self.sample_teacher_doc, self.sample_glific_contact)
        
        # Assert
        self.assertIsNotNone(result)
        fields = json.loads(result["fields"])
        self.assertIn("address", fields)
        self.assertEqual(fields["address"]["value"], "123 Main St")

    @patch('requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    @patch('frappe.logger')
    def test_send_glific_update_success(self, mock_logger, mock_settings, mock_headers, mock_post):
        """Test successful sending of update to Glific"""
        # Arrange
        mock_settings.return_value.api_url = "https://api.glific.com"
        mock_headers.return_value = {"Authorization": "Bearer token"}
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"updateContact": {"contact": {"id": "123"}}}}
        mock_post.return_value = mock_response
        
        update_payload = {"fields": json.dumps({"email": {"value": "test@example.com"}})}
        
        # Act
        result = send_glific_update("123", update_payload)
        
        # Assert
        self.assertTrue(result)

    @patch('requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    @patch('frappe.logger')
    def test_send_glific_update_api_errors(self, mock_logger, mock_settings, mock_headers, mock_post):
        """Test handling of API errors in send_glific_update"""
        # Arrange
        mock_settings.return_value.api_url = "https://api.glific.com"
        mock_headers.return_value = {"Authorization": "Bearer token"}
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errors": [{"message": "Invalid input"}]}
        mock_post.return_value = mock_response
        
        update_payload = {"fields": json.dumps({"email": {"value": "test@example.com"}})}
        
        # Act
        result = send_glific_update("123", update_payload)
        
        # Assert
        self.assertFalse(result)
        mock_logger().error.assert_called_with("Glific API Error: [{'message': 'Invalid input'}]")

    @patch('requests.post')
    @patch('your_module.get_glific_auth_headers')
    @patch('your_module.get_glific_settings')
    def test_send_glific_update_http_error(self, mock_settings, mock_headers, mock_post):
        """Test handling of HTTP errors in send_glific_update"""
        # Arrange
        mock_settings.return_value.api_url = "https://api.glific.com"
        mock_headers.return_value = {"Authorization": "Bearer token"}
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        update_payload = {"fields": json.dumps({"email": {"value": "test@example.com"}})}
        
        # Act
        result = send_glific_update("123", update_payload)
        
        # Assert
        self.assertFalse(result)

    def test_prepare_update_payload_empty_glific_fields(self):
        """Test preparing update payload when Glific contact has no fields"""
        # Arrange
        glific_contact_no_fields = {
            "id": "123",
            "name": "John Doe",
            "language": {"id": "1", "label": "English"},
            "fields": "{}"
        }
        
        with patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.get_value') as mock_db_get_value, \
             patch('frappe.utils.now_datetime') as mock_now:
            
            mock_get_all.return_value = [{"frappe_field": "phone", "glific_field": "phone"}]
            mock_db_get_value.return_value = "1"
            mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
            
            # Act
            result = prepare_update_payload(self.sample_teacher_doc, glific_contact_no_fields)
            
            # Assert
            self.assertIsNotNone(result)
            fields = json.loads(result["fields"])
            self.assertIn("phone", fields)

    def test_prepare_update_payload_invalid_json_fields(self):
        """Test preparing update payload when Glific contact has invalid JSON fields"""
        # Arrange
        glific_contact_invalid = {
            "id": "123",
            "name": "John Doe",
            "language": {"id": "1", "label": "English"},
            "fields": "invalid_json"
        }
        
        with patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.get_value') as mock_db_get_value:
            
            mock_get_all.return_value = []
            mock_db_get_value.return_value = "1"
            
            # Act & Assert - Should handle the JSON decode error gracefully
            with self.assertRaises(json.JSONDecodeError):
                prepare_update_payload(self.sample_teacher_doc, glific_contact_invalid)


class TestGlificIntegrationEdgeCases(unittest.TestCase):
    """Additional edge case tests"""
    
    def test_glific_id_none(self):
        """Test handling when teacher has no Glific ID"""
        teacher_doc = Mock()
        teacher_doc.doctype = "Teacher"
        teacher_doc.glific_id = None
        
        with patch('your_module.get_glific_contact') as mock_get_contact:
            mock_get_contact.return_value = None
            
            # This should handle None glific_id gracefully
            update_glific_contact(teacher_doc, "on_update")
            mock_get_contact.assert_called_once_with(None)

    def test_empty_field_mappings(self):
        """Test preparing update payload with no field mappings"""
        teacher_doc = Mock()
        teacher_doc.get.return_value = "English"
        
        glific_contact = {
            "id": "123",
            "language": {"id": "1", "label": "English"},
            "fields": "{}"
        }
        
        with patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.get_value') as mock_db_get_value:
            
            mock_get_all.return_value = []
            mock_db_get_value.return_value = "1"
            
            result = prepare_update_payload(teacher_doc, glific_contact)
            self.assertIsNone(result)


if __name__ == '__main__':
    # Run specific test classes or all tests
    unittest.main(verbosity=2)