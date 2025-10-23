# # import unittest
# # from unittest.mock import Mock, patch, MagicMock
# # import json
# # import sys
# # import os
# # import builtins

# # # Add parent directory to path
# # parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# # sys.path.insert(0, parent_dir)

# # # Mock frappe BEFORE any imports
# # mock_frappe = MagicMock()
# # # CRITICAL: Make whitelist a pass-through decorator
# # mock_frappe.whitelist = lambda: lambda f: f
# # sys.modules['frappe'] = mock_frappe
# # sys.modules['frappe.utils'] = MagicMock()

# # # Create a mock glific_integration module
# # mock_glific_integration = MagicMock()
# # mock_glific_integration.get_glific_auth_headers = MagicMock()
# # mock_glific_integration.get_glific_settings = MagicMock()

# # # Add it to sys.modules
# # sys.modules['glific_integration'] = mock_glific_integration

# # # Monkey-patch the __import__ to handle relative imports
# # _original_import = builtins.__import__

# # def _custom_import(name, globals=None, locals=None, fromlist=(), level=0):
# #     """Custom import handler - intercept relative imports"""
# #     if level > 0 and name == 'glific_integration':
# #         return mock_glific_integration
# #     return _original_import(name, globals, locals, fromlist, level)

# # builtins.__import__ = _custom_import

# # # Now we can import glific_webhook
# # import glific_webhook

# # # Restore original import
# # builtins.__import__ = _original_import


# # class TestGlificWebhook(unittest.TestCase):
# #     """Test suite for Glific webhook integration"""
    
# #     def setUp(self):
# #         """Setup test fixtures"""
# #         self.mock_teacher_doc = Mock()
# #         self.mock_teacher_doc.doctype = "Teacher"
# #         self.mock_teacher_doc.name = "TEST-TEACHER-001"
# #         self.mock_teacher_doc.glific_id = "123"
# #         self.mock_teacher_doc.first_name = "John"
# #         self.mock_teacher_doc.phone = "9876543210"
# #         self.mock_teacher_doc.language = "English"
# #         self.mock_teacher_doc.get = Mock(side_effect=lambda x: getattr(self.mock_teacher_doc, x, None))
        
# #         self.mock_settings = Mock()
# #         self.mock_settings.api_url = "https://api.glific.test"
        
# #         self.mock_headers = {"Authorization": "Bearer test_token"}
        
# #         self.mock_glific_contact = {
# #             "id": "123",
# #             "name": "John Doe",
# #             "language": {"id": "1", "label": "English"},
# #             "fields": json.dumps({
# #                 "first_name": {"value": "John", "type": "string"},
# #                 "phone": {"value": "9876543210", "type": "string"}
# #             })
# #         }


# # class TestGetGlificContact(TestGlificWebhook):
# #     """Test get_glific_contact function"""
    
# #     @patch('glific_webhook.get_glific_auth_headers')
# #     @patch('glific_webhook.get_glific_settings')
# #     @patch('glific_webhook.requests.post')
# #     def test_get_contact_success(self, mock_post, mock_settings, mock_headers):
# #         """Test successful contact retrieval"""
# #         mock_settings.return_value = self.mock_settings
# #         mock_headers.return_value = self.mock_headers
        
# #         mock_response = Mock()
# #         mock_response.status_code = 200
# #         mock_response.json.return_value = {
# #             "data": {"contact": {"contact": self.mock_glific_contact}}
# #         }
# #         mock_post.return_value = mock_response
        
# #         result = glific_webhook.get_glific_contact("123")
        
# #         self.assertIsNotNone(result)
# #         self.assertEqual(result["id"], "123")
    
# #     @patch('glific_webhook.get_glific_auth_headers')
# #     @patch('glific_webhook.get_glific_settings')
# #     @patch('glific_webhook.requests.post')
# #     def test_get_contact_not_found(self, mock_post, mock_settings, mock_headers):
# #         """Test contact not found"""
# #         mock_settings.return_value = self.mock_settings
# #         mock_headers.return_value = self.mock_headers
        
# #         mock_response = Mock()
# #         mock_response.status_code = 200
# #         mock_response.json.return_value = {"data": {}}
# #         mock_post.return_value = mock_response
        
# #         result = glific_webhook.get_glific_contact("999")
        
# #         self.assertIsNone(result)
    
# #     @patch('glific_webhook.get_glific_auth_headers')
# #     @patch('glific_webhook.get_glific_settings')
# #     @patch('glific_webhook.requests.post')
# #     def test_get_contact_non_200_status(self, mock_post, mock_settings, mock_headers):
# #         """Test non-200 status code"""
# #         mock_settings.return_value = self.mock_settings
# #         mock_headers.return_value = self.mock_headers
        
# #         mock_response = Mock()
# #         mock_response.status_code = 404
# #         mock_post.return_value = mock_response
        
# #         result = glific_webhook.get_glific_contact("123")
        
# #         self.assertIsNone(result)


# # class TestPrepareUpdatePayload(TestGlificWebhook):
# #     """Test prepare_update_payload function"""
    
# #     @patch('glific_webhook.frappe')
# #     def test_prepare_payload_with_changes(self, mock_frappe):
# #         """Test payload with field changes"""
# #         # Create Mock objects with attributes instead of dicts
# #         mapping1 = Mock()
# #         mapping1.frappe_field = "first_name"
# #         mapping1.glific_field = "first_name"
        
# #         mock_frappe.get_all.return_value = [mapping1]
# #         mock_frappe.utils.now_datetime().isoformat.return_value = "2024-01-15T10:00:00"
# #         mock_frappe.db.get_value.return_value = "1"
        
# #         self.mock_teacher_doc.first_name = "Jane"
        
# #         result = glific_webhook.prepare_update_payload(
# #             self.mock_teacher_doc, 
# #             self.mock_glific_contact
# #         )
        
# #         self.assertIsNotNone(result)
# #         self.assertIn("fields", result)
    
# #     @patch('glific_webhook.frappe')
# #     def test_prepare_payload_no_changes(self, mock_frappe):
# #         """Test payload with no changes"""
# #         # Create Mock objects with attributes
# #         mapping1 = Mock()
# #         mapping1.frappe_field = "first_name"
# #         mapping1.glific_field = "first_name"
        
# #         mock_frappe.get_all.return_value = [mapping1]
# #         mock_frappe.db.get_value.return_value = "1"
        
# #         result = glific_webhook.prepare_update_payload(
# #             self.mock_teacher_doc,
# #             self.mock_glific_contact
# #         )
        
# #         self.assertIsNone(result)
    
# #     @patch('glific_webhook.frappe')
# #     def test_prepare_payload_empty_mappings(self, mock_frappe):
# #         """Test with no field mappings"""
# #         mock_frappe.get_all.return_value = []
# #         mock_frappe.db.get_value.return_value = "1"
        
# #         result = glific_webhook.prepare_update_payload(
# #             self.mock_teacher_doc,
# #             self.mock_glific_contact
# #         )
        
# #         self.assertIsNone(result)


# # class TestSendGlificUpdate(TestGlificWebhook):
# #     """Test send_glific_update function"""
    
# #     @patch('glific_webhook.get_glific_auth_headers')
# #     @patch('glific_webhook.get_glific_settings')
# #     @patch('glific_webhook.requests.post')
# #     def test_send_update_success(self, mock_post, mock_settings, mock_headers):
# #         """Test successful update"""
# #         mock_settings.return_value = self.mock_settings
# #         mock_headers.return_value = self.mock_headers
        
# #         mock_response = Mock()
# #         mock_response.status_code = 200
# #         mock_response.json.return_value = {
# #             "data": {"updateContact": {"contact": {"id": "123"}, "errors": None}}
# #         }
# #         mock_post.return_value = mock_response
        
# #         payload = {"fields": json.dumps({"test": "data"})}
# #         result = glific_webhook.send_glific_update("123", payload)
        
# #         self.assertTrue(result)
    
# #     @patch('glific_webhook.get_glific_auth_headers')
# #     @patch('glific_webhook.get_glific_settings')
# #     @patch('glific_webhook.requests.post')
# #     @patch('glific_webhook.frappe')
# #     def test_send_update_with_errors(self, mock_frappe, mock_post, mock_settings, mock_headers):
# #         """Test update with errors"""
# #         mock_settings.return_value = self.mock_settings
# #         mock_headers.return_value = self.mock_headers
        
# #         mock_response = Mock()
# #         mock_response.status_code = 200
# #         mock_response.json.return_value = {"errors": [{"message": "Error"}]}
# #         mock_post.return_value = mock_response
        
# #         payload = {"fields": json.dumps({"test": "data"})}
# #         result = glific_webhook.send_glific_update("123", payload)
        
# #         self.assertFalse(result)
    
# #     @patch('glific_webhook.get_glific_auth_headers')
# #     @patch('glific_webhook.get_glific_settings')
# #     @patch('glific_webhook.requests.post')
# #     def test_send_update_non_200_status(self, mock_post, mock_settings, mock_headers):
# #         """Test with non-200 status"""
# #         mock_settings.return_value = self.mock_settings
# #         mock_headers.return_value = self.mock_headers
        
# #         mock_response = Mock()
# #         mock_response.status_code = 500
# #         mock_post.return_value = mock_response
        
# #         payload = {"fields": json.dumps({"test": "data"})}
# #         result = glific_webhook.send_glific_update("123", payload)
        
# #         self.assertFalse(result)


# # class TestUpdateGlificContact(TestGlificWebhook):
# #     """Test update_glific_contact function"""
    
# #     @patch('glific_webhook.send_glific_update')
# #     @patch('glific_webhook.prepare_update_payload')
# #     @patch('glific_webhook.get_glific_contact')
# #     @patch('glific_webhook.frappe')
# #     def test_update_success_workflow(self, mock_frappe, mock_get, mock_prepare, mock_send):
# #         """Test complete update workflow"""
# #         mock_get.return_value = self.mock_glific_contact
# #         mock_prepare.return_value = {"fields": json.dumps({"test": "data"})}
# #         mock_send.return_value = True
        
# #         glific_webhook.update_glific_contact(self.mock_teacher_doc, "on_update")
        
# #         mock_get.assert_called_once_with("123")
# #         mock_prepare.assert_called_once()
# #         mock_send.assert_called_once()
    
# #     @patch('glific_webhook.frappe')
# #     def test_update_wrong_doctype(self, mock_frappe):
# #         """Test with wrong doctype"""
# #         student_doc = Mock()
# #         student_doc.doctype = "Student"
        
# #         result = glific_webhook.update_glific_contact(student_doc, "on_update")
        
# #         self.assertIsNone(result)
    
# #     @patch('glific_webhook.get_glific_contact')
# #     @patch('glific_webhook.frappe')
# #     def test_update_contact_not_found(self, mock_frappe, mock_get):
# #         """Test when contact not found"""
# #         mock_get.return_value = None
        
# #         glific_webhook.update_glific_contact(self.mock_teacher_doc, "on_update")
        
# #         mock_get.assert_called_once_with("123")
# #         mock_frappe.logger().error.assert_called()
    
# #     @patch('glific_webhook.prepare_update_payload')
# #     @patch('glific_webhook.get_glific_contact')
# #     @patch('glific_webhook.frappe')
# #     def test_update_no_changes(self, mock_frappe, mock_get, mock_prepare):
# #         """Test when no updates needed"""
# #         mock_get.return_value = self.mock_glific_contact
# #         mock_prepare.return_value = None
        
# #         glific_webhook.update_glific_contact(self.mock_teacher_doc, "on_update")
        
# #         mock_get.assert_called_once()
# #         mock_prepare.assert_called_once()
# #         mock_frappe.logger().info.assert_called()


# # if __name__ == '__main__':
# #     unittest.main(verbosity=2)



# import unittest
# from unittest.mock import Mock, patch, MagicMock
# import json
# import sys
# import os

# # Add parent directory to path
# parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# sys.path.insert(0, parent_dir)


# class TestGlificWebhook(unittest.TestCase):
#     """Test suite for Glific webhook integration"""
    
#     def setUp(self):
#         """Setup test fixtures"""
#         self.mock_teacher_doc = Mock()
#         self.mock_teacher_doc.doctype = "Teacher"
#         self.mock_teacher_doc.name = "TEST-TEACHER-001"
#         self.mock_teacher_doc.glific_id = "123"
#         self.mock_teacher_doc.first_name = "John"
#         self.mock_teacher_doc.phone = "9876543210"
#         self.mock_teacher_doc.language = "English"
#         self.mock_teacher_doc.get = Mock(side_effect=lambda x: getattr(self.mock_teacher_doc, x, None))
        
#         self.mock_settings = Mock()
#         self.mock_settings.api_url = "https://api.glific.test"
        
#         self.mock_headers = {"Authorization": "Bearer test_token"}
        
#         self.mock_glific_contact = {
#             "id": "123",
#             "name": "John Doe",
#             "language": {"id": "1", "label": "English"},
#             "fields": json.dumps({
#                 "first_name": {"value": "John", "type": "string"},
#                 "phone": {"value": "9876543210", "type": "string"}
#             })
#         }
        
#         # Create mock for glific_integration
#         mock_glific_integration = MagicMock()
#         mock_glific_integration.get_glific_auth_headers = MagicMock()
#         mock_glific_integration.get_glific_settings = MagicMock()
        
#         # Setup module mocks for each test - MUST include glific_integration
#         self.patcher_modules = patch.dict('sys.modules', {
#             'frappe': MagicMock(),
#             'frappe.utils': MagicMock(),
#             'glific_integration': mock_glific_integration,  # CRITICAL: Mock this BEFORE import
#             'tap_lms.tap_lms.glific_integration': mock_glific_integration,  # For package imports
#         })
#         self.patcher_modules.start()
        
#         # Configure frappe mock
#         sys.modules['frappe'].whitelist = lambda: lambda f: f
#         sys.modules['frappe'].logger.return_value = Mock(info=Mock(), error=Mock(), warning=Mock())
        
#         # Import glific_webhook AFTER patching
#         import glific_webhook
#         self.glific_webhook = glific_webhook
    
#     def tearDown(self):
#         """Clean up patches after each test"""
#         self.patcher_modules.stop()
        
#         # Remove the imported module to ensure clean state
#         if 'glific_webhook' in sys.modules:
#             del sys.modules['glific_webhook']


# class TestGetGlificContact(TestGlificWebhook):
#     """Test get_glific_contact function"""
    
#     @patch('glific_webhook.get_glific_auth_headers')
#     @patch('glific_webhook.get_glific_settings')
#     @patch('glific_webhook.requests.post')
#     def test_get_contact_success(self, mock_post, mock_settings, mock_headers):
#         """Test successful contact retrieval"""
#         mock_settings.return_value = self.mock_settings
#         mock_headers.return_value = self.mock_headers
        
#         mock_response = Mock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {
#             "data": {"contact": {"contact": self.mock_glific_contact}}
#         }
#         mock_post.return_value = mock_response
        
#         result = self.glific_webhook.get_glific_contact("123")
        
#         self.assertIsNotNone(result)
#         self.assertEqual(result["id"], "123")
    
#     @patch('glific_webhook.get_glific_auth_headers')
#     @patch('glific_webhook.get_glific_settings')
#     @patch('glific_webhook.requests.post')
#     def test_get_contact_not_found(self, mock_post, mock_settings, mock_headers):
#         """Test contact not found"""
#         mock_settings.return_value = self.mock_settings
#         mock_headers.return_value = self.mock_headers
        
#         mock_response = Mock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {"data": {}}
#         mock_post.return_value = mock_response
        
#         result = self.glific_webhook.get_glific_contact("999")
        
#         self.assertIsNone(result)
    
#     @patch('glific_webhook.get_glific_auth_headers')
#     @patch('glific_webhook.get_glific_settings')
#     @patch('glific_webhook.requests.post')
#     def test_get_contact_non_200_status(self, mock_post, mock_settings, mock_headers):
#         """Test non-200 status code"""
#         mock_settings.return_value = self.mock_settings
#         mock_headers.return_value = self.mock_headers
        
#         mock_response = Mock()
#         mock_response.status_code = 404
#         mock_post.return_value = mock_response
        
#         result = self.glific_webhook.get_glific_contact("123")
        
#         self.assertIsNone(result)


# class TestPrepareUpdatePayload(TestGlificWebhook):
#     """Test prepare_update_payload function"""
    
#     @patch('glific_webhook.frappe')
#     def test_prepare_payload_with_changes(self, mock_frappe):
#         """Test payload with field changes"""
#         # Create Mock objects with attributes instead of dicts
#         mapping1 = Mock()
#         mapping1.frappe_field = "first_name"
#         mapping1.glific_field = "first_name"
        
#         mock_frappe.get_all.return_value = [mapping1]
#         mock_frappe.utils.now_datetime().isoformat.return_value = "2024-01-15T10:00:00"
#         mock_frappe.db.get_value.return_value = "1"
        
#         self.mock_teacher_doc.first_name = "Jane"
        
#         result = self.glific_webhook.prepare_update_payload(
#             self.mock_teacher_doc, 
#             self.mock_glific_contact
#         )
        
#         self.assertIsNotNone(result)
#         self.assertIn("fields", result)
    
#     @patch('glific_webhook.frappe')
#     def test_prepare_payload_no_changes(self, mock_frappe):
#         """Test payload with no changes"""
#         # Create Mock objects with attributes
#         mapping1 = Mock()
#         mapping1.frappe_field = "first_name"
#         mapping1.glific_field = "first_name"
        
#         mock_frappe.get_all.return_value = [mapping1]
#         mock_frappe.db.get_value.return_value = "1"
        
#         result = self.glific_webhook.prepare_update_payload(
#             self.mock_teacher_doc,
#             self.mock_glific_contact
#         )
        
#         self.assertIsNone(result)
    
#     @patch('glific_webhook.frappe')
#     def test_prepare_payload_empty_mappings(self, mock_frappe):
#         """Test with no field mappings"""
#         mock_frappe.get_all.return_value = []
#         mock_frappe.db.get_value.return_value = "1"
        
#         result = self.glific_webhook.prepare_update_payload(
#             self.mock_teacher_doc,
#             self.mock_glific_contact
#         )
        
#         self.assertIsNone(result)


# class TestSendGlificUpdate(TestGlificWebhook):
#     """Test send_glific_update function"""
    
#     @patch('glific_webhook.get_glific_auth_headers')
#     @patch('glific_webhook.get_glific_settings')
#     @patch('glific_webhook.requests.post')
#     def test_send_update_success(self, mock_post, mock_settings, mock_headers):
#         """Test successful update"""
#         mock_settings.return_value = self.mock_settings
#         mock_headers.return_value = self.mock_headers
        
#         mock_response = Mock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {
#             "data": {"updateContact": {"contact": {"id": "123"}, "errors": None}}
#         }
#         mock_post.return_value = mock_response
        
#         payload = {"fields": json.dumps({"test": "data"})}
#         result = self.glific_webhook.send_glific_update("123", payload)
        
#         self.assertTrue(result)
    
#     @patch('glific_webhook.get_glific_auth_headers')
#     @patch('glific_webhook.get_glific_settings')
#     @patch('glific_webhook.requests.post')
#     @patch('glific_webhook.frappe')
#     def test_send_update_with_errors(self, mock_frappe, mock_post, mock_settings, mock_headers):
#         """Test update with errors"""
#         mock_settings.return_value = self.mock_settings
#         mock_headers.return_value = self.mock_headers
        
#         mock_response = Mock()
#         mock_response.status_code = 200
#         mock_response.json.return_value = {"errors": [{"message": "Error"}]}
#         mock_post.return_value = mock_response
        
#         payload = {"fields": json.dumps({"test": "data"})}
#         result = self.glific_webhook.send_glific_update("123", payload)
        
#         self.assertFalse(result)
    
#     @patch('glific_webhook.get_glific_auth_headers')
#     @patch('glific_webhook.get_glific_settings')
#     @patch('glific_webhook.requests.post')
#     def test_send_update_non_200_status(self, mock_post, mock_settings, mock_headers):
#         """Test with non-200 status"""
#         mock_settings.return_value = self.mock_settings
#         mock_headers.return_value = self.mock_headers
        
#         mock_response = Mock()
#         mock_response.status_code = 500
#         mock_post.return_value = mock_response
        
#         payload = {"fields": json.dumps({"test": "data"})}
#         result = self.glific_webhook.send_glific_update("123", payload)
        
#         self.assertFalse(result)


# class TestUpdateGlificContact(TestGlificWebhook):
#     """Test update_glific_contact function"""
    
#     @patch('glific_webhook.send_glific_update')
#     @patch('glific_webhook.prepare_update_payload')
#     @patch('glific_webhook.get_glific_contact')
#     @patch('glific_webhook.frappe')
#     def test_update_success_workflow(self, mock_frappe, mock_get, mock_prepare, mock_send):
#         """Test complete update workflow"""
#         mock_get.return_value = self.mock_glific_contact
#         mock_prepare.return_value = {"fields": json.dumps({"test": "data"})}
#         mock_send.return_value = True
        
#         self.glific_webhook.update_glific_contact(self.mock_teacher_doc, "on_update")
        
#         mock_get.assert_called_once_with("123")
#         mock_prepare.assert_called_once()
#         mock_send.assert_called_once()
    
#     @patch('glific_webhook.frappe')
#     def test_update_wrong_doctype(self, mock_frappe):
#         """Test with wrong doctype"""
#         student_doc = Mock()
#         student_doc.doctype = "Student"
        
#         result = self.glific_webhook.update_glific_contact(student_doc, "on_update")
        
#         self.assertIsNone(result)
    
#     @patch('glific_webhook.get_glific_contact')
#     @patch('glific_webhook.frappe')
#     def test_update_contact_not_found(self, mock_frappe, mock_get):
#         """Test when contact not found"""
#         mock_get.return_value = None
        
#         self.glific_webhook.update_glific_contact(self.mock_teacher_doc, "on_update")
        
#         mock_get.assert_called_once_with("123")
#         mock_frappe.logger().error.assert_called()
    
#     @patch('glific_webhook.prepare_update_payload')
#     @patch('glific_webhook.get_glific_contact')
#     @patch('glific_webhook.frappe')
#     def test_update_no_changes(self, mock_frappe, mock_get, mock_prepare):
#         """Test when no updates needed"""
#         mock_get.return_value = self.mock_glific_contact
#         mock_prepare.return_value = None
        
#         self.glific_webhook.update_glific_contact(self.mock_teacher_doc, "on_update")
        
#         mock_get.assert_called_once()
#         mock_prepare.assert_called_once()
#         mock_frappe.logger().info.assert_called()


# if __name__ == '__main__':
#     unittest.main(verbosity=2)