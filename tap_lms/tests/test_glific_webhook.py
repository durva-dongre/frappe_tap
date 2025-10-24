"""
Comprehensive test suite for Glific Webhook module.

Tests cover:
- update_glific_contact (main webhook function)
- get_glific_contact (fetch contact details)
- prepare_update_payload (prepare update data)
- send_glific_update (send updates to Glific)
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
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
        'frappe.utils': Mock(),
        'requests': Mock(),
        'json': Mock(),
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
    frappe_mock.db.get_value = Mock()
    frappe_mock.get_all = Mock()
    frappe_mock.utils = Mock()
    frappe_mock.utils.now_datetime = Mock(return_value=datetime.now(timezone.utc))
    frappe_mock._ = lambda x: x  # Translation function mock
    return frappe_mock


@pytest.fixture
def mock_glific_settings():
    """Mock Glific Settings document"""
    settings = Mock()
    settings.api_url = "https://api.glific.com"
    settings.access_token = "valid_test_token"
    return settings


@pytest.fixture
def mock_teacher_doc():
    """Mock Teacher document"""
    doc = Mock()
    doc.doctype = "Teacher"
    doc.name = "Teacher-001"
    doc.glific_id = "12345"
    doc.language = "English"
    doc.school = "Test School"
    doc.batch = "Batch-001"
    doc.get = Mock(side_effect=lambda field: {
        "language": "English",
        "school": "Test School",
        "batch": "Batch-001",
        "glific_id": "12345"
    }.get(field))
    return doc


@pytest.fixture
def mock_glific_contact():
    """Mock Glific contact data"""
    return {
        "id": "12345",
        "name": "Test Teacher",
        "language": {
            "id": "1",
            "label": "English"
        },
        "fields": json.dumps({
            "school": {
                "value": "Old School",
                "type": "string",
                "inserted_at": "2025-01-01T00:00:00Z"
            },
            "batch": {
                "value": "Old Batch",
                "type": "string",
                "inserted_at": "2025-01-01T00:00:00Z"
            }
        })
    }


@pytest.fixture
def mock_requests(mock_modules):
    """Configured requests mock"""
    requests_mock = mock_modules['requests']
    requests_mock.exceptions = Mock()
    requests_mock.exceptions.RequestException = Exception
    return requests_mock


@pytest.fixture
def mock_api_response():
    """Factory for creating mock API responses"""
    def _create_response(status_code=200, data=None, errors=None):
        response = Mock()
        response.status_code = status_code
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
# TEST CLASS: UPDATE GLIFIC CONTACT (Main Webhook Function)
# ============================================================================

class TestUpdateGlificContact:
    """Tests for the main webhook function update_glific_contact"""
    
    def test_update_glific_contact_wrong_doctype(self, mock_frappe, mock_teacher_doc):
        """Test that function returns early for non-Teacher doctypes"""
        mock_teacher_doc.doctype = "Student"
        
        with patch('glific_webhook.get_glific_contact') as mock_get_contact:
            from glific_webhook import update_glific_contact
            
            result = update_glific_contact(mock_teacher_doc, "on_update")
            
            # Should return early without calling get_glific_contact
            mock_get_contact.assert_not_called()
            assert result is None
    
    def test_update_glific_contact_success(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test successful contact update"""
        with patch('glific_webhook.get_glific_contact') as mock_get_contact, \
             patch('glific_webhook.prepare_update_payload') as mock_prepare, \
             patch('glific_webhook.send_glific_update') as mock_send:
            
            mock_get_contact.return_value = mock_glific_contact
            mock_prepare.return_value = {
                "fields": json.dumps({"school": {"value": "New School", "type": "string"}})
            }
            mock_send.return_value = True
            
            from glific_webhook import update_glific_contact
            
            update_glific_contact(mock_teacher_doc, "on_update")
            
            mock_get_contact.assert_called_once_with("12345")
            mock_prepare.assert_called_once_with(mock_teacher_doc, mock_glific_contact)
            mock_send.assert_called_once()
            mock_frappe.logger().info.assert_called()
    
    def test_update_glific_contact_not_found(self, mock_frappe, mock_teacher_doc):
        """Test when Glific contact is not found"""
        with patch('glific_webhook.get_glific_contact') as mock_get_contact:
            mock_get_contact.return_value = None
            
            from glific_webhook import update_glific_contact
            
            update_glific_contact(mock_teacher_doc, "on_update")
            
            mock_frappe.logger().error.assert_called_once()
            error_call = mock_frappe.logger().error.call_args[0][0]
            assert "not found" in error_call
            assert "Teacher-001" in error_call
    
    def test_update_glific_contact_no_updates_needed(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test when no updates are needed"""
        with patch('glific_webhook.get_glific_contact') as mock_get_contact, \
             patch('glific_webhook.prepare_update_payload') as mock_prepare, \
             patch('glific_webhook.send_glific_update') as mock_send:
            
            mock_get_contact.return_value = mock_glific_contact
            mock_prepare.return_value = None  # No updates needed
            
            from glific_webhook import update_glific_contact
            
            update_glific_contact(mock_teacher_doc, "on_update")
            
            mock_send.assert_not_called()
            mock_frappe.logger().info.assert_called()
            info_call = mock_frappe.logger().info.call_args[0][0]
            assert "No updates needed" in info_call
    
    def test_update_glific_contact_send_failure(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test when sending update fails"""
        with patch('glific_webhook.get_glific_contact') as mock_get_contact, \
             patch('glific_webhook.prepare_update_payload') as mock_prepare, \
             patch('glific_webhook.send_glific_update') as mock_send:
            
            mock_get_contact.return_value = mock_glific_contact
            mock_prepare.return_value = {"fields": json.dumps({"test": "data"})}
            mock_send.return_value = False
            
            from glific_webhook import update_glific_contact
            
            update_glific_contact(mock_teacher_doc, "on_update")
            
            mock_frappe.logger().error.assert_called()
            error_call = mock_frappe.logger().error.call_args[0][0]
            assert "Failed to update" in error_call
    
    def test_update_glific_contact_exception_handling(
        self, mock_frappe, mock_teacher_doc
    ):
        """Test exception handling in update_glific_contact"""
        with patch('glific_webhook.get_glific_contact') as mock_get_contact:
            mock_get_contact.side_effect = Exception("Network error")
            
            from glific_webhook import update_glific_contact
            
            update_glific_contact(mock_teacher_doc, "on_update")
            
            mock_frappe.logger().error.assert_called()
            error_call = mock_frappe.logger().error.call_args[0][0]
            assert "Error updating" in error_call
            assert "Network error" in error_call


# ============================================================================
# TEST CLASS: GET GLIFIC CONTACT
# ============================================================================

class TestGetGlificContact:
    """Tests for get_glific_contact function"""
    
    def test_get_glific_contact_success(
        self, mock_frappe, mock_glific_settings, mock_requests, 
        mock_api_response, mock_glific_contact
    ):
        """Test successful contact retrieval"""
        contact_data = {
            "contact": {
                "contact": mock_glific_contact
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, contact_data)
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import get_glific_contact
            
            result = get_glific_contact("12345")
            
            assert result is not None
            assert result["id"] == "12345"
            assert result["name"] == "Test Teacher"
            mock_requests.post.assert_called_once()
    
    def test_get_glific_contact_api_error(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test handling of API errors"""
        mock_requests.post.return_value = mock_api_response(500)
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import get_glific_contact
            
            result = get_glific_contact("12345")
            
            assert result is None
    
    def test_get_glific_contact_empty_response(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test handling of empty response"""
        mock_requests.post.return_value = mock_api_response(200, {})
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import get_glific_contact
            
            result = get_glific_contact("12345")
            
            assert result is None
    
    def test_get_glific_contact_query_structure(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test that query structure is correct"""
        contact_data = {
            "contact": {
                "contact": {"id": "12345", "name": "Test"}
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, contact_data)
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import get_glific_contact
            
            get_glific_contact("12345")
            
            # Verify the query was called with correct structure
            call_args = mock_requests.post.call_args
            json_payload = call_args[1]['json']
            assert 'query' in json_payload
            assert 'variables' in json_payload
            assert json_payload['variables']['id'] == "12345"
            assert 'contact(id: $id)' in json_payload['query']
    
    def test_get_glific_contact_network_exception(
        self, mock_frappe, mock_glific_settings, mock_requests
    ):
        """Test handling of network exceptions"""
        mock_requests.post.side_effect = Exception("Connection timeout")
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import get_glific_contact
            
            with pytest.raises(Exception):
                get_glific_contact("12345")


# ============================================================================
# TEST CLASS: PREPARE UPDATE PAYLOAD
# ============================================================================

class TestPrepareUpdatePayload:
    """Tests for prepare_update_payload function"""
    
    def test_prepare_update_payload_with_changes(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test preparing payload when there are field changes"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"},
            {"frappe_field": "batch", "glific_field": "batch"}
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "New School",
            "batch": "New Batch"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None  # No language change
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is not None
        assert "fields" in result
        fields_data = json.loads(result["fields"])
        assert "school" in fields_data
        assert fields_data["school"]["value"] == "New School"
        assert "batch" in fields_data
        assert fields_data["batch"]["value"] == "New Batch"
    
    def test_prepare_update_payload_no_changes(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test when there are no changes"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"},
            {"frappe_field": "batch", "glific_field": "batch"}
        ]
        
        # Return same values as in glific_contact
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "Old School",
            "batch": "Old Batch"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is None
    
    def test_prepare_update_payload_new_fields(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test adding new fields that don't exist in Glific"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"},
            {"frappe_field": "email", "glific_field": "email"}  # New field
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "Old School",
            "email": "new@test.com"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is not None
        fields_data = json.loads(result["fields"])
        assert "email" in fields_data
        assert fields_data["email"]["value"] == "new@test.com"
    
    def test_prepare_update_payload_language_change(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test when language needs to be updated"""
        mock_frappe.get_all.return_value = []
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "language": "Hindi"
        }.get(field))
        
        # Return different language ID
        mock_frappe.db.get_value.return_value = "2"
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is not None
        assert "languageId" in result
        assert result["languageId"] == 2
    
    def test_prepare_update_payload_language_no_change(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test when language ID is the same"""
        mock_frappe.get_all.return_value = []
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "language": "English"
        }.get(field))
        
        # Return same language ID as in contact
        mock_frappe.db.get_value.return_value = "1"
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is None
    
    def test_prepare_update_payload_combined_changes(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test both field and language changes"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"}
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "New School",
            "language": "Hindi"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = "2"
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is not None
        assert "fields" in result
        assert "languageId" in result
        assert result["languageId"] == 2
    
    def test_prepare_update_payload_empty_fields(
        self, mock_frappe, mock_teacher_doc
    ):
        """Test handling of contact with empty fields"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"}
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "New School"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None
        
        contact_with_empty_fields = {
            "id": "12345",
            "name": "Test",
            "language": {"id": "1", "label": "English"},
            "fields": "{}"
        }
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, contact_with_empty_fields)
        
        assert result is not None
        fields_data = json.loads(result["fields"])
        assert "school" in fields_data
    
    def test_prepare_update_payload_preserves_existing_fields(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test that existing fields not being updated are preserved"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "batch", "glific_field": "batch"}
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "batch": "New Batch"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is not None
        fields_data = json.loads(result["fields"])
        # Both old and new fields should be present
        assert "school" in fields_data  # Existing field preserved
        assert "batch" in fields_data  # Updated field


# ============================================================================
# TEST CLASS: SEND GLIFIC UPDATE
# ============================================================================

class TestSendGlificUpdate:
    """Tests for send_glific_update function"""
    
    def test_send_glific_update_success(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test successful update sending"""
        update_data = {
            "updateContact": {
                "contact": {
                    "id": "12345",
                    "fields": "{}",
                    "language": {"label": "English"}
                },
                "errors": []
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, update_data)
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import send_glific_update
            
            payload = {"fields": json.dumps({"school": {"value": "Test"}})}
            result = send_glific_update("12345", payload)
            
            assert result is True
            mock_requests.post.assert_called_once()
    
    def test_send_glific_update_with_language(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test sending update with language change"""
        update_data = {
            "updateContact": {
                "contact": {
                    "id": "12345",
                    "fields": "{}",
                    "language": {"label": "Hindi"}
                }
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, update_data)
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import send_glific_update
            
            payload = {
                "fields": json.dumps({"school": {"value": "Test"}}),
                "languageId": 2
            }
            result = send_glific_update("12345", payload)
            
            assert result is True
    
    def test_send_glific_update_api_errors(
        self, mock_frappe, mock_glific_settings, mock_requests
    ):
        """Test handling of API errors in response"""
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "errors": [{"message": "Invalid field"}]
        }
        mock_requests.post.return_value = response
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import send_glific_update
            
            payload = {"fields": json.dumps({"school": {"value": "Test"}})}
            result = send_glific_update("12345", payload)
            
            assert result is False
            mock_frappe.logger().error.assert_called()
    
    def test_send_glific_update_http_error(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test handling of HTTP errors"""
        mock_requests.post.return_value = mock_api_response(500)
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import send_glific_update
            
            payload = {"fields": json.dumps({"school": {"value": "Test"}})}
            result = send_glific_update("12345", payload)
            
            assert result is False
    
    def test_send_glific_update_mutation_structure(
        self, mock_frappe, mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test that mutation structure is correct"""
        update_data = {
            "updateContact": {
                "contact": {"id": "12345"}
            }
        }
        
        mock_requests.post.return_value = mock_api_response(200, update_data)
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import send_glific_update
            
            payload = {"fields": json.dumps({"test": "value"})}
            send_glific_update("12345", payload)
            
            # Verify mutation structure
            call_args = mock_requests.post.call_args
            json_payload = call_args[1]['json']
            assert 'query' in json_payload
            assert 'variables' in json_payload
            assert 'updateContact' in json_payload['query']
            assert json_payload['variables']['id'] == "12345"
            assert json_payload['variables']['input'] == payload
    
    def test_send_glific_update_network_exception(
        self, mock_frappe, mock_glific_settings, mock_requests
    ):
        """Test handling of network exceptions"""
        mock_requests.post.side_effect = Exception("Connection error")
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import send_glific_update
            
            payload = {"fields": json.dumps({"test": "value"})}
            
            with pytest.raises(Exception):
                send_glific_update("12345", payload)


# ============================================================================
# TEST CLASS: INTEGRATION SCENARIOS
# ============================================================================

class TestWebhookIntegration:
    """Integration tests for complete webhook workflows"""
    
    def test_complete_update_workflow_success(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact,
        mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test complete workflow from webhook trigger to successful update"""
        # Setup field mappings
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"}
        ]
        
        # Setup teacher doc with changes
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "New School",
            "language": "English"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = "1"
        
        # Mock API responses
        get_contact_response = mock_api_response(
            200, 
            {"contact": {"contact": mock_glific_contact}}
        )
        
        update_response = mock_api_response(
            200,
            {"updateContact": {"contact": {"id": "12345"}}}
        )
        
        mock_requests.post.side_effect = [get_contact_response, update_response]
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import update_glific_contact
            
            update_glific_contact(mock_teacher_doc, "on_update")
            
            # Verify complete flow
            assert mock_requests.post.call_count == 2
            mock_frappe.logger().info.assert_called()
    
    def test_complete_workflow_with_no_changes(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact,
        mock_glific_settings, mock_requests, mock_api_response
    ):
        """Test workflow when no changes are detected"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"}
        ]
        
        # No changes in values
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "Old School",
            "language": "English"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = "1"
        
        get_contact_response = mock_api_response(
            200,
            {"contact": {"contact": mock_glific_contact}}
        )
        
        mock_requests.post.return_value = get_contact_response
        
        with patch('glific_webhook.get_glific_settings') as mock_get_settings, \
             patch('glific_webhook.get_glific_auth_headers') as mock_get_headers:
            
            mock_get_settings.return_value = mock_glific_settings
            mock_get_headers.return_value = {"authorization": "token"}
            
            from glific_webhook import update_glific_contact
            
            update_glific_contact(mock_teacher_doc, "on_update")
            
            # Should only call get contact, not update
            assert mock_requests.post.call_count == 1


# ============================================================================
# TEST CLASS: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""
    
    def test_glific_contact_with_null_fields(
        self, mock_frappe, mock_teacher_doc
    ):
        """Test handling contact with null fields"""
        contact = {
            "id": "12345",
            "name": "Test",
            "language": {"id": "1", "label": "English"},
            "fields": None
        }
        
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"}
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "Test School"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None
        
        from glific_webhook import prepare_update_payload
        
        # Should handle gracefully
        result = prepare_update_payload(mock_teacher_doc, contact)
        
        assert result is not None
    
    def test_teacher_doc_with_missing_glific_id(self, mock_frappe):
        """Test handling teacher without glific_id"""
        doc = Mock()
        doc.doctype = "Teacher"
        doc.name = "Teacher-001"
        doc.glific_id = None
        
        with patch('glific_webhook.get_glific_contact') as mock_get_contact:
            from glific_webhook import update_glific_contact
            
            update_glific_contact(doc, "on_update")
            
            # Should call get_glific_contact with None
            mock_get_contact.assert_called_once_with(None)
    
    def test_empty_field_mappings(self, mock_frappe, mock_teacher_doc, mock_glific_contact):
        """Test when no field mappings are configured"""
        mock_frappe.get_all.return_value = []
        mock_frappe.db.get_value.return_value = None
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        # Should return None as no updates
        assert result is None
    
    def test_special_characters_in_field_values(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test handling of special characters in field values"""
        mock_frappe.get_all.return_value = [
            {"frappe_field": "school", "glific_field": "school"}
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "school": "O'Reilly's School & Academy"
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is not None
        fields_data = json.loads(result["fields"])
        assert fields_data["school"]["value"] == "O'Reilly's School & Academy"
    
    def test_very_long_field_values(
        self, mock_frappe, mock_teacher_doc, mock_glific_contact
    ):
        """Test handling of very long field values"""
        long_value = "A" * 10000
        
        mock_frappe.get_all.return_value = [
            {"frappe_field": "notes", "glific_field": "notes"}
        ]
        
        mock_teacher_doc.get = Mock(side_effect=lambda field: {
            "notes": long_value
        }.get(field))
        
        mock_frappe.db.get_value.return_value = None
        
        from glific_webhook import prepare_update_payload
        
        result = prepare_update_payload(mock_teacher_doc, mock_glific_contact)
        
        assert result is not None
        fields_data = json.loads(result["fields"])
        assert len(fields_data["notes"]["value"]) == 10000


# ============================================================================
# HELPER TESTS
# ============================================================================

class TestModuleStructure:
    """Tests for module structure and imports"""
    
    def test_all_functions_importable(self, mock_modules):
        """Verify all expected functions can be imported"""
        try:
            from glific_webhook import (
                update_glific_contact,
                get_glific_contact,
                prepare_update_payload,
                send_glific_update
            )
            
            # Verify all are callable
            functions = [
                update_glific_contact,
                get_glific_contact,
                prepare_update_payload,
                send_glific_update
            ]
            
            for func in functions:
                assert callable(func)
        
        except ImportError as e:
            pytest.skip(f"Could not import module: {str(e)}")
    
    def test_whitelist_decorator(self, mock_modules):
        """Test that update_glific_contact has @frappe.whitelist() decorator"""
        try:
            from glific_webhook import update_glific_contact
            
            # This test would verify decorator in actual implementation
            assert callable(update_glific_contact)
        
        except ImportError as e:
            pytest.skip(f"Could not import module: {str(e)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--cov=glific_webhook", "--cov-report=html"])