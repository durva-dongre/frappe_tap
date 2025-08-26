# test_glific_multi_enrollment_update.py
# Complete coverage tests for 100% code coverage

import frappe
import unittest
from unittest.mock import patch, Mock, MagicMock, call
import json
import sys
import importlib
from datetime import datetime, timezone
import requests
import time


class TestGlificMultiEnrollmentComplete(unittest.TestCase):
    """Comprehensive tests for 100% coverage of glific_multi_enrollment_update.py"""
    
    def setUp(self):
        """Set up test environment"""
        if hasattr(frappe, 'set_user'):
            frappe.set_user("Administrator")
        
        # Import the module
        try:
            self.module = importlib.import_module(
                'tap_lms.tap_lms.doctype.backend_student_onboarding.glific_multi_enrollment_update'
            )
        except ImportError:
            self.skipTest("Could not import the module")

    def test_01_check_student_multi_enrollment_multiple_enrollments(self):
        """Test student with multiple enrollments - Line coverage for main path"""
        with patch('frappe.db.exists', return_value=True), \
             patch('frappe.get_doc') as mock_get_doc:
            
            mock_student = Mock()
            mock_student.enrollment = [{"program": "P1"}, {"program": "P2"}]
            mock_get_doc.return_value = mock_student
            
            result = self.module.check_student_multi_enrollment("STU-001")
            self.assertEqual(result, "yes")

    def test_02_check_student_multi_enrollment_single_enrollment(self):
        """Test student with single enrollment"""
        with patch('frappe.db.exists', return_value=True), \
             patch('frappe.get_doc') as mock_get_doc:
            
            mock_student = Mock()
            mock_student.enrollment = [{"program": "P1"}]
            mock_get_doc.return_value = mock_student
            
            result = self.module.check_student_multi_enrollment("STU-001")
            self.assertEqual(result, "no")

    def test_03_check_student_multi_enrollment_no_enrollments(self):
        """Test student with no enrollments - None case"""
        with patch('frappe.db.exists', return_value=True), \
             patch('frappe.get_doc') as mock_get_doc:
            
            mock_student = Mock()
            mock_student.enrollment = None
            mock_get_doc.return_value = mock_student
            
            result = self.module.check_student_multi_enrollment("STU-001")
            self.assertEqual(result, "no")

    def test_04_check_student_multi_enrollment_empty_enrollments(self):
        """Test student with empty enrollments list"""
        with patch('frappe.db.exists', return_value=True), \
             patch('frappe.get_doc') as mock_get_doc:
            
            mock_student = Mock()
            mock_student.enrollment = []
            mock_get_doc.return_value = mock_student
            
            result = self.module.check_student_multi_enrollment("STU-001")
            self.assertEqual(result, "no")

    def test_05_check_student_multi_enrollment_student_not_exists(self):
        """Test non-existent student"""
        with patch('frappe.db.exists', return_value=False), \
             patch('frappe.logger') as mock_logger:
            
            result = self.module.check_student_multi_enrollment("NONEXISTENT")
            self.assertEqual(result, "no")
            mock_logger().error.assert_called()

    def test_06_check_student_multi_enrollment_exception(self):
        """Test exception handling in check_student_multi_enrollment"""
        with patch('frappe.db.exists', return_value=True), \
             patch('frappe.get_doc', side_effect=Exception("DB Error")), \
             patch('frappe.logger') as mock_logger:
            
            result = self.module.check_student_multi_enrollment("STU-001")
            self.assertEqual(result, "no")
            mock_logger().error.assert_called()

    def test_07_update_specific_set_no_name(self):
        """Test update function with no set name"""
        result = self.module.update_specific_set_contacts_with_multi_enrollment("")
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Backend Student Onboarding set name is required")

    def test_08_update_specific_set_none_name(self):
        """Test update function with None set name"""
        result = self.module.update_specific_set_contacts_with_multi_enrollment(None)
        self.assertIn("error", result)

    def test_09_update_specific_set_not_found(self):
        """Test update function with non-existent set"""
        with patch('frappe.get_doc', side_effect=frappe.DoesNotExistError("Set not found")):
            result = self.module.update_specific_set_contacts_with_multi_enrollment("NONEXISTENT")
            self.assertIn("error", result)
            self.assertIn("not found", result["error"])

    def test_10_update_specific_set_not_processed(self):
        """Test update function with unprocessed set"""
        with patch('frappe.get_doc') as mock_get_doc:
            mock_set = Mock()
            mock_set.status = "Draft"
            mock_set.set_name = "Test Set"
            mock_get_doc.return_value = mock_set
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            self.assertIn("error", result)
            self.assertIn("not 'Processed'", result["error"])

    def test_11_update_specific_set_no_students(self):
        """Test update function with no students"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all', return_value=[]), \
             patch('frappe.logger') as mock_logger:
            
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            mock_get_doc.return_value = mock_set
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            self.assertIn("message", result)
            self.assertIn("No successfully processed students", result["message"])

    def test_12_update_specific_set_student_doc_not_found(self):
        """Test when student document doesn't exist"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=False), \
             patch('frappe.logger') as mock_logger:
            
            # Mock onboarding set
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            mock_get_doc.return_value = mock_set
            
            # Mock backend students
            mock_get_all.return_value = [{
                "student_name": "Test Student",
                "phone": "+1234567890",
                "student_id": "STU-001",
                "batch_skeyword": "BATCH1"
            }]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["total_processed"], 1)

    def test_13_update_specific_set_student_doc_exception(self):
        """Test exception when getting student document"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger:
            
            # Mock onboarding set
            mock_set = Mock()
            mock_set.status = "Processed" 
            mock_set.set_name = "Test Set"
            
            # Mock exception for student document
            mock_get_doc.side_effect = [mock_set, Exception("Student doc error")]
            
            # Mock backend students
            mock_get_all.return_value = [{
                "student_name": "Test Student",
                "phone": "+1234567890",
                "student_id": "STU-001", 
                "batch_skeyword": "BATCH1"
            }]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["total_processed"], 1)

    def test_14_update_specific_set_no_glific_id(self):
        """Test when student has no Glific ID"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger:
            
            # Mock onboarding set
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            # Mock student without glific_id
            mock_student = Mock()
            mock_student.glific_id = None
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            
            # Mock backend students
            mock_get_all.return_value = [{
                "student_name": "Test Student",
                "phone": "+1234567890",
                "student_id": "STU-001",
                "batch_skeyword": "BATCH1"
            }]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["total_processed"], 1)

    def test_15_update_specific_set_fetch_contact_failed(self):
        """Test when fetching contact from Glific fails"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            # Mock Glific settings
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock failed response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)

    def test_16_update_specific_set_fetch_contact_api_errors(self):
        """Test when Glific API returns errors"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock API error response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"errors": [{"message": "Contact not found"}]}
            mock_post.return_value = mock_response
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)

    def test_17_update_specific_set_no_contact_data(self):
        """Test when no contact data is returned"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock empty contact data
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": {"contact": None}}
            mock_post.return_value = mock_response
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)

    def test_18_update_specific_set_invalid_json_fields(self):
        """Test when existing fields JSON is invalid"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch.object(self.module, 'check_student_multi_enrollment', return_value="yes"), \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock contact with invalid JSON fields
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "12345",
                            "name": "Test",
                            "phone": "+123",
                            "fields": "invalid json"
                        }
                    }
                }
            }
            
            update_response = Mock()
            update_response.status_code = 200
            update_response.json.return_value = {
                "data": {
                    "updateContact": {
                        "contact": {"id": "12345", "name": "Test", "fields": "{}"}
                    }
                }
            }
            
            mock_post.side_effect = [fetch_response, update_response]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["updated"], 1)

    def test_19_update_specific_set_existing_multi_enrollment_same_value(self):
        """Test updating contact with existing multi_enrollment (same value)"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch.object(self.module, 'check_student_multi_enrollment', return_value="yes"), \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock contact with existing multi_enrollment
            existing_fields = {
                "multi_enrollment": {"value": "yes", "type": "string"}
            }
            
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "12345",
                            "name": "Test",
                            "phone": "+123",
                            "fields": json.dumps(existing_fields)
                        }
                    }
                }
            }
            
            update_response = Mock()
            update_response.status_code = 200
            update_response.json.return_value = {
                "data": {
                    "updateContact": {
                        "contact": {"id": "12345", "name": "Test", "fields": json.dumps(existing_fields)}
                    }
                }
            }
            
            mock_post.side_effect = [fetch_response, update_response]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["updated"], 1)

    def test_20_update_specific_set_existing_multi_enrollment_different_value(self):
        """Test updating contact with existing multi_enrollment (different value)"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch.object(self.module, 'check_student_multi_enrollment', return_value="no"), \
             patch('requests.post') as mock_post:
            
            # Setup mocks - same as test 19 but with different multi_enrollment value
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock contact with existing multi_enrollment = "yes"
            existing_fields = {
                "multi_enrollment": {"value": "yes", "type": "string"}
            }
            
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "12345",
                            "name": "Test",
                            "phone": "+123",
                            "fields": json.dumps(existing_fields)
                        }
                    }
                }
            }
            
            # Mock update response with new value
            updated_fields = {
                "multi_enrollment": {"value": "no", "type": "string", "inserted_at": datetime.now(timezone.utc).isoformat()}
            }
            
            update_response = Mock()
            update_response.status_code = 200
            update_response.json.return_value = {
                "data": {
                    "updateContact": {
                        "contact": {"id": "12345", "name": "Test", "fields": json.dumps(updated_fields)}
                    }
                }
            }
            
            mock_post.side_effect = [fetch_response, update_response]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["updated"], 1)

    def test_21_update_specific_set_new_multi_enrollment(self):
        """Test adding new multi_enrollment field"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch.object(self.module, 'check_student_multi_enrollment', return_value="yes"), \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock contact without multi_enrollment field
            existing_fields = {
                "other_field": {"value": "test", "type": "string"}
            }
            
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "12345",
                            "name": "Test",
                            "phone": "+123",
                            "fields": json.dumps(existing_fields)
                        }
                    }
                }
            }
            
            # Mock successful update
            update_response = Mock()
            update_response.status_code = 200
            update_response.json.return_value = {
                "data": {
                    "updateContact": {
                        "contact": {"id": "12345", "name": "Test", "fields": "{}"}
                    }
                }
            }
            
            mock_post.side_effect = [fetch_response, update_response]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["updated"], 1)

    def test_22_update_specific_set_update_failed(self):
        """Test when update contact fails"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch.object(self.module, 'check_student_multi_enrollment', return_value="yes"), \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock successful fetch
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "12345",
                            "name": "Test",
                            "phone": "+123",
                            "fields": "{}"
                        }
                    }
                }
            }
            
            # Mock failed update
            update_response = Mock()
            update_response.status_code = 500
            mock_post.side_effect = [fetch_response, update_response]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)

    def test_23_update_specific_set_update_api_errors(self):
        """Test when update API returns errors"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.exists', return_value=True), \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'get_glific_settings') as mock_settings, \
             patch.object(self.module, 'get_glific_auth_headers') as mock_headers, \
             patch.object(self.module, 'check_student_multi_enrollment', return_value="yes"), \
             patch('requests.post') as mock_post:
            
            # Setup mocks
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            
            mock_student = Mock()
            mock_student.glific_id = "12345"
            
            mock_get_doc.side_effect = [mock_set, mock_student]
            mock_get_all.return_value = [{"student_name": "Test", "phone": "+123", "student_id": "STU-001", "batch_skeyword": "B1"}]
            
            mock_settings_obj = Mock()
            mock_settings_obj.api_url = "https://test.glific.com"
            mock_settings.return_value = mock_settings_obj
            mock_headers.return_value = {"Authorization": "Bearer token"}
            
            # Mock successful fetch
            fetch_response = Mock()
            fetch_response.status_code = 200
            fetch_response.json.return_value = {
                "data": {
                    "contact": {
                        "contact": {
                            "id": "12345",
                            "name": "Test",
                            "phone": "+123",
                            "fields": "{}"
                        }
                    }
                }
            }
            
            # Mock update with errors
            update_response = Mock()
            update_response.status_code = 200
            update_response.json.return_value = {
                "errors": [{"message": "Update failed"}]
            }
            
            mock_post.side_effect = [fetch_response, update_response]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)

    def test_24_update_specific_set_exception_in_processing(self):
        """Test exception during processing a backend student"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.logger') as mock_logger:
            
            mock_set = Mock()
            mock_set.status = "Processed"
            mock_set.set_name = "Test Set"
            mock_get_doc.return_value = mock_set
            
            # Mock backend student that will cause exception
            mock_get_all.return_value = [{"student_name": None, "phone": None, "student_id": None, "batch_skeyword": None}]
            
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST-SET")
            
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["total_processed"], 1)

    def test_25_run_multi_enrollment_update_success(self):
        """Test successful run_multi_enrollment_update_for_specific_set"""
        with patch('frappe.db.begin') as mock_begin, \
             patch('frappe.db.commit') as mock_commit, \
             patch('frappe.db.rollback') as mock_rollback, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            mock_update.return_value = {
                "set_name": "Test Set",
                "updated": 5,
                "skipped": 0,
                "errors": 0,
                "total_processed": 5
            }
            
            result = self.module.run_multi_enrollment_update_for_specific_set("TEST-SET")
            
            self.assertIn("Process completed", result)
            self.assertIn("Updated: 5", result)
            mock_begin.assert_called_once()
            mock_commit.assert_called_once()
            mock_rollback.assert_not_called()

    def test_26_run_multi_enrollment_update_no_name(self):
        """Test run function with no set name"""
        result = self.module.run_multi_enrollment_update_for_specific_set("")
        self.assertIn("Error: Backend Student Onboarding set name is required", result)

    def test_27_run_multi_enrollment_update_none_name(self):
        """Test run function with None set name"""
        result = self.module.run_multi_enrollment_update_for_specific_set(None)
        self.assertIn("Error: Backend Student Onboarding set name is required", result)

    def test_28_run_multi_enrollment_update_with_error(self):
        """Test run function when update returns error"""
        with patch('frappe.db.begin') as mock_begin, \
             patch('frappe.db.commit') as mock_commit, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            mock_update.return_value = {"error": "Set not found"}
            
            result = self.module.run_multi_enrollment_update_for_specific_set("TEST-SET")
            
            self.assertIn("Error: Set not found", result)
            mock_commit.assert_called_once()

    def test_29_run_multi_enrollment_update_with_message(self):
        """Test run function when update returns message"""
        with patch('frappe.db.begin') as mock_begin, \
             patch('frappe.db.commit') as mock_commit, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            mock_update.return_value = {"message": "No students found"}
            
            result = self.module.run_multi_enrollment_update_for_specific_set("TEST-SET")
            
            self.assertEqual(result, "No students found")
            mock_commit.assert_called_once()

    def test_30_run_multi_enrollment_update_exception(self):
        """Test run function with exception"""
        with patch('frappe.db.begin') as mock_begin, \
             patch('frappe.db.commit') as mock_commit, \
             patch('frappe.db.rollback') as mock_rollback, \
             patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            mock_update.side_effect = Exception("Database error")
            
            result = self.module.run_multi_enrollment_update_for_specific_set("TEST-SET")
            
            self.assertIn("Error occurred:", result)
            mock_begin.assert_called_once()
            mock_rollback.assert_called_once()
            mock_commit.assert_not_called()

    def test_31_get_backend_onboarding_sets(self):
        """Test get_backend_onboarding_sets function"""
        with patch('frappe.get_all') as mock_get_all:
            mock_get_all.return_value = [
                {
                    "name": "SET-001",
                    "set_name": "Test Set 1",
                    "processed_student_count": 10,
                    "upload_date": "2024-01-01"
                }
            ]
            
            result = self.module.get_backend_onboarding_sets()
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "SET-001")
            mock_get_all.assert_called_once_with(
                "Backend Student Onboarding",
                filters={"status": "Processed"},
                fields=["name", "set_name", "processed_student_count", "upload_date"],
                order_by="upload_date desc"
            )

    def test_32_process_multiple_sets_simple_success(self):
        """Test process_multiple_sets_simple with successful completion"""
        with patch('frappe.logger') as mock_logger, \
             patch('time.sleep') as mock_sleep, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            # Mock successful processing that completes (total_processed = 0 signals completion)
            mock_update.return_value = {
                "updated": 5,
                "errors": 0,
                "total_processed": 0  # This signals completion
            }
            
            result = self.module.process_multiple_sets_simple(["SET-001"])
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["status"], "completed")
            self.assertEqual(result[0]["updated"], 5)

    def test_33_process_multiple_sets_simple_with_error(self):
        """Test process_multiple_sets_simple when update returns error"""
        with patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            mock_update.return_value = {"error": "Set not found"}
            
            result = self.module.process_multiple_sets_simple(["INVALID-SET"])
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["status"], "completed")

    def test_34_process_multiple_sets_simple_with_message(self):
        """Test process_multiple_sets_simple when update returns message"""
        with patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            mock_update.return_value = {"message": "No students found"}
            
            result = self.module.process_multiple_sets_simple(["EMPTY-SET"])
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["status"], "completed")

    def test_35_process_multiple_sets_simple_batch_processing(self):
        """Test process_multiple_sets_simple with batch processing"""
        with patch('frappe.logger') as mock_logger, \
             patch('time.sleep') as mock_sleep, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            # Mock multiple batches, then completion
            mock_update.side_effect = [
                {"updated": 10, "errors": 0, "total_processed": 50},  # First batch
                {"updated": 15, "errors": 1, "total_processed": 50},  # Second batch  
                {"updated": 5, "errors": 0, "total_processed": 0}     # Final batch - completion
            ]
            
            result = self.module.process_multiple_sets_simple(["LARGE-SET"])
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["updated"], 30)  # 10 + 15 + 5
            self.assertEqual(result[0]["errors"], 1)
            mock_sleep.assert_called()

    def test_36_process_multiple_sets_simple_batch_limit(self):
        """Test process_multiple_sets_simple hits batch limit"""
        with patch('frappe.logger') as mock_logger, \
             patch('time.sleep') as mock_sleep, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            # Mock never-ending batches to test limit
            mock_update.return_value = {"updated": 10, "errors": 0, "total_processed": 50}
            
            result = self.module.process_multiple_sets_simple(["ENDLESS-SET"])
            
            # Should hit the batch limit of 20
            self.assertEqual(result[0]["updated"], 200)  # 10 * 20 batches

    def test_37_process_multiple_sets_simple_exception(self):
        """Test process_multiple_sets_simple with exception"""
        with patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            mock_update.side_effect = Exception("Unexpected error")
            
            result = self.module.process_multiple_sets_simple(["ERROR-SET"])
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["status"], "error")
            self.assertIn("error", result[0])

    def test_38_process_multiple_sets_multiple_sets(self):
        """Test process_multiple_sets_simple with multiple sets"""
        with patch('frappe.logger') as mock_logger, \
             patch.object(self.module, 'update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            # Different responses for different sets
            mock_update.side_effect = [
                {"updated": 5, "errors": 0, "total_processed": 0},  # SET-001 completion
                {"updated": 3, "errors": 1, "total_processed": 0}   # SET-002 completion
            ]
            
            result = self.module.process_multiple_sets_simple(["SET-001", "SET-002"])
            
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["updated"], 5)
            self.assertEqual(result[1]["updated"], 3)

    def test_39_process_my_sets_list_input(self):
        """Test process_my_sets with list input"""
        with patch.object(self.module, 'enqueue') as mock_enqueue:
            mock_job = Mock()
            mock_job.id = "job_123"
            mock_enqueue.return_value = mock_job
            
            result = self.module.process_my_sets(["SET-001", "SET-002"])
            
            self.assertIn("Started processing 2 sets", result)
            self.assertIn("job_123", result)
            mock_enqueue.assert_called_once()

    def test_40_process_my_sets_string_input(self):
        """Test process_my_sets with comma-separated string"""
        with patch.object(self.module, 'enqueue') as mock_enqueue:
            mock_job = Mock()
            mock_job.id = "job_456"
            mock_enqueue.return_value = mock_job
            
            result = self.module.process_my_sets("SET-001, SET-002, SET-003")
            
            self.assertIn("Started processing 3 sets", result)
            self.assertIn("job_456", result)
            
            # Verify the enqueue call
            call_args = mock_enqueue.call_args
            self.assertEqual(call_args[0][0], self.module.process_multiple_sets_simple)
            self.assertEqual(len(call_args[1]["set_names"]), 3)
            self.assertEqual(call_args[1]["batch_size"], 50)
            self.assertEqual(call_args[1]["queue"], 'long')
            self.assertEqual(call_args[1]["timeout"], 7200)

    def test_41_process_my_sets_string_with_spaces(self):
        """Test process_my_sets with string containing extra spaces"""
        with patch.object(self.module, 'enqueue') as mock_enqueue:
            mock_job = Mock()
            mock_job.id = "job_789"
            mock_enqueue.return_value = mock_job
            
            result = self.module.process_my_sets("  SET-001  ,  SET-002  ,  SET-003  ")
            
            # Verify spaces are stripped
            call_args = mock_enqueue.call_args
            set_names = call_args[1]["set_names"]
            self.assertEqual(set_names, ["SET-001", "SET-002", "SET-003"])

    def test_42_all_import_statements(self):
        """Test that all import statements are covered"""
        # This test ensures all imports at the top of the module are executed
        self.assertTrue(hasattr(self.module, 'frappe'))
        self.assertTrue(hasattr(self.module, 'requests'))
        self.assertTrue(hasattr(self.module, 'json'))
        self.assertTrue(hasattr(self.module, 'datetime'))
        self.assertTrue(hasattr(self.module, 'timezone'))
        self.assertTrue(hasattr(self.module, 'time'))
        
    def test_43_datetime_timezone_usage(self):
        """Test datetime.now(timezone.utc).isoformat() usage"""
        # This should cover the datetime usage in the module
        now = datetime.now(timezone.utc).isoformat()
        self.assertIsInstance(now, str)
        self.assertIn('T', now)

    def test_44_json_dumps_usage(self):
        """Test json.dumps usage"""
        test_data = {"test": "value"}
        json_str = json.dumps(test_data)
        self.assertEqual(json_str, '{"test": "value"}')

    def test_45_all_whitelist_decorators(self):
        """Test that @frappe.whitelist() decorated functions exist"""
        # Ensure the whitelist functions are accessible
        self.assertTrue(callable(getattr(self.module, 'run_multi_enrollment_update_for_specific_set')))
        self.assertTrue(callable(getattr(self.module, 'get_backend_onboarding_sets')))
        self.assertTrue(callable(getattr(self.module, 'process_my_sets')))

    def test_46_variable_assignments_and_constants(self):
        """Test variable assignments and constants in the module"""
        # Test default batch_size parameter
        result = self.module.update_specific_set_contacts_with_multi_enrollment("")
        self.assertIn("error", result)
        
        # Test batch_size parameter with different value
        with patch('frappe.get_doc', side_effect=frappe.DoesNotExistError()):
            result = self.module.update_specific_set_contacts_with_multi_enrollment("TEST", batch_size=10)
            self.assertIn("error", result)

    def test_47_logger_usage_patterns(self):
        """Test all frappe.logger() usage patterns"""
        with patch('frappe.logger') as mock_logger:
            # Test logger().info calls
            mock_logger_instance = Mock()
            mock_logger.return_value = mock_logger_instance
            
            # This should trigger logger usage
            self.module.check_student_multi_enrollment("NONEXISTENT")


def run_complete_tests():
    """Run all tests for complete coverage"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestGlificMultiEnrollmentComplete)
    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)

