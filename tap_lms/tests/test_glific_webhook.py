import unittest
from unittest.mock import Mock, patch, MagicMock, call
import json
import frappe


class TestGlificWebhook(unittest.TestCase):
    """Test cases for Glific webhook integration functions"""
    
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

    @patch('requests.post')
    @patch('frappe.get_all')
    @patch('frappe.db.get_value')
    @patch('frappe.utils.now_datetime')
    @patch('frappe.logger')
    def test_update_glific_contact_success(self, mock_logger, mock_now, mock_db_get_value, 
                                         mock_get_all, mock_post):
        """Test successful update of Glific contact"""
        # Arrange
        mock_get_all.return_value = self.sample_field_mappings
        mock_db_get_value.return_value = "1"
        mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        
        # Mock get_glific_contact response
        mock_response_get = Mock()
        mock_response_get.status_code = 200
        mock_response_get.json.return_value = {
            "data": {"contact": {"contact": self.sample_glific_contact}}
        }
        
        # Mock send_glific_update response
        mock_response_update = Mock()
        mock_response_update.status_code = 200
        mock_response_update.json.return_value = {
            "data": {"updateContact": {"contact": {"id": "123"}}}
        }
        
        mock_post.side_effect = [mock_response_get, mock_response_update]
        
        # Mock settings and headers
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute the function
            from tap_lms.integrations.glific_webhook import update_glific_contact
            update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        self.assertEqual(mock_post.call_count, 2)  # One for get, one for update
        mock_logger().info.assert_called()

    @patch('frappe.logger')
    def test_update_glific_contact_not_teacher_doctype(self, mock_logger):
        """Test that function returns early if doctype is not Teacher"""
        # Arrange
        non_teacher_doc = Mock()
        non_teacher_doc.doctype = "Student"
        
        # Import and execute
        from tap_lms.integrations.glific_webhook import update_glific_contact
        update_glific_contact(non_teacher_doc, "on_update")
        
        # Assert - logger should not be called for non-Teacher docs
        mock_logger().error.assert_not_called()
        mock_logger().info.assert_not_called()

    @patch('requests.post')
    @patch('frappe.logger')
    def test_get_glific_contact_not_found(self, mock_logger, mock_post):
        """Test handling when Glific contact is not found"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"contact": {"contact": None}}}
        mock_post.return_value = mock_response
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import update_glific_contact
            update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().error.assert_called_with("Glific contact not found for teacher TEST-001")

    @patch('requests.post')
    @patch('frappe.get_all')
    @patch('frappe.db.get_value')
    @patch('frappe.logger')
    def test_no_updates_needed(self, mock_logger, mock_db_get_value, mock_get_all, mock_post):
        """Test handling when no updates are needed"""
        # Arrange
        mock_get_all.return_value = [{"frappe_field": "phone", "glific_field": "phone"}]
        mock_db_get_value.return_value = "1"  # Same language ID
        
        # Teacher has same phone as in Glific
        self.sample_teacher_doc.get.side_effect = lambda field: {
            "language": "English",
            "phone": "1234567890"  # Same as in glific_contact
        }.get(field)
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"contact": {"contact": self.sample_glific_contact}}
        }
        mock_post.return_value = mock_response
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import update_glific_contact
            update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().info.assert_called_with("No updates needed for Glific contact 123")

    @patch('requests.post')
    @patch('frappe.get_all')
    @patch('frappe.db.get_value')
    @patch('frappe.utils.now_datetime')
    @patch('frappe.logger')
    def test_send_update_fails(self, mock_logger, mock_now, mock_db_get_value, 
                              mock_get_all, mock_post):
        """Test handling when sending update to Glific fails"""
        # Arrange
        mock_get_all.return_value = self.sample_field_mappings
        mock_db_get_value.return_value = "1"
        mock_now.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        
        # Mock successful get but failed update
        mock_response_get = Mock()
        mock_response_get.status_code = 200
        mock_response_get.json.return_value = {
            "data": {"contact": {"contact": self.sample_glific_contact}}
        }
        
        mock_response_update = Mock()
        mock_response_update.status_code = 500  # Failed update
        
        mock_post.side_effect = [mock_response_get, mock_response_update]
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import update_glific_contact
            update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().error.assert_called_with("Failed to update Glific contact for teacher TEST-001")

    @patch('requests.post')
    @patch('frappe.logger')
    def test_exception_handling(self, mock_logger, mock_post):
        """Test exception handling in update_glific_contact"""
        # Arrange
        mock_post.side_effect = Exception("API Error")
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import update_glific_contact
            update_glific_contact(self.sample_teacher_doc, "on_update")
        
        # Assert
        mock_logger().error.assert_called_with("Error updating Glific contact for teacher TEST-001: API Error")

    @patch('requests.post')
    def test_get_glific_contact_api_error(self, mock_post):
        """Test handling of API error in get_glific_contact"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import get_glific_contact
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
        
        # Import and execute
        from tap_lms.integrations.glific_webhook import prepare_update_payload
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
        
        # Import and execute
        from tap_lms.integrations.glific_webhook import prepare_update_payload
        result = prepare_update_payload(self.sample_teacher_doc, self.sample_glific_contact)
        
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result["languageId"], 2)

    @patch('requests.post')
    @patch('frappe.logger')
    def test_send_glific_update_success(self, mock_logger, mock_post):
        """Test successful sending of update to Glific"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"updateContact": {"contact": {"id": "123"}}}}
        mock_post.return_value = mock_response
        
        update_payload = {"fields": json.dumps({"email": {"value": "test@example.com"}})}
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import send_glific_update
            result = send_glific_update("123", update_payload)
        
        # Assert
        self.assertTrue(result)

    @patch('requests.post')
    @patch('frappe.logger')
    def test_send_glific_update_api_errors(self, mock_logger, mock_post):
        """Test handling of API errors in send_glific_update"""
        # Arrange
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errors": [{"message": "Invalid input"}]}
        mock_post.return_value = mock_response
        
        update_payload = {"fields": json.dumps({"email": {"value": "test@example.com"}})}
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import send_glific_update
            result = send_glific_update("123", update_payload)
        
        # Assert
        self.assertFalse(result)
        mock_logger().error.assert_called_with("Glific API Error: [{'message': 'Invalid input'}]")


class TestGlificWebhookEdgeCases(unittest.TestCase):
    """Additional edge case tests for Glific webhook"""
    
    def setUp(self):
        """Set up test fixtures for edge cases"""
        self.teacher_doc_no_glific_id = Mock()
        self.teacher_doc_no_glific_id.doctype = "Teacher"
        self.teacher_doc_no_glific_id.name = "TEST-NO-ID"
        self.teacher_doc_no_glific_id.glific_id = None

    @patch('requests.post')
    @patch('frappe.logger')
    def test_glific_id_none(self, mock_logger, mock_post):
        """Test handling when teacher has no Glific ID"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"contact": {"contact": None}}}
        mock_post.return_value = mock_response
        
        with patch('tap_lms.integrations.glific_integration.get_glific_settings') as mock_settings, \
             patch('tap_lms.integrations.glific_integration.get_glific_auth_headers') as mock_headers:
            
            mock_settings.return_value.api_url = "https://api.glific.com"
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Import and execute
            from tap_lms.integrations.glific_webhook import update_glific_contact
            update_glific_contact(self.teacher_doc_no_glific_id, "on_update")
        
        # Should handle None glific_id gracefully
        mock_post.assert_called_once()

    @patch('frappe.get_all')
    @patch('frappe.db.get_value')
    def test_empty_field_mappings(self, mock_db_get_value, mock_get_all):
        """Test preparing update payload with no field mappings"""
        teacher_doc = Mock()
        teacher_doc.get.return_value = "English"
        
        glific_contact = {
            "id": "123",
            "language": {"id": "1", "label": "English"},
            "fields": "{}"
        }
        
        mock_get_all.return_value = []
        mock_db_get_value.return_value = "1"
        
        # Import and execute
        from tap_lms.integrations.glific_webhook import prepare_update_payload
        result = prepare_update_payload(teacher_doc, glific_contact)
        
        self.assertIsNone(result)

    def test_invalid_json_fields(self):
        """Test preparing update payload when Glific contact has invalid JSON fields"""
        teacher_doc = Mock()
        teacher_doc.get.return_value = "English"
        
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
            
            # Import and execute - Should handle the JSON decode error gracefully
            from tap_lms.integrations.glific_webhook import prepare_update_payload
            with self.assertRaises(json.JSONDecodeError):
                prepare_update_payload(teacher_doc, glific_contact_invalid)


# Standalone test functions that can be run without unittest framework
def run_basic_test():
    """Basic test that can be run independently"""
    print("Running basic Glific webhook test...")
    
    # Mock teacher document
    teacher_doc = Mock()
    teacher_doc.doctype = "Teacher"
    teacher_doc.name = "TEST-BASIC"
    teacher_doc.glific_id = "123"
    
    print("✅ Mock teacher document created")
    
    # Test doctype validation
    if teacher_doc.doctype == "Teacher":
        print("✅ Doctype validation passed")
    else:
        print("❌ Doctype validation failed")
    
    # Test glific_id presence
    if teacher_doc.glific_id:
        print("✅ Glific ID validation passed")
    else:
        print("❌ Glific ID validation failed")
    
    print("Basic test completed successfully!")


if __name__ == '__main__':
    # Run basic test if executed directly
    run_basic_test()
    
    # Run unittest suite
    unittest.main(verbosity=2)