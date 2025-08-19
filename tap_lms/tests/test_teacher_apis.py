# # tests/test_teacher_apis.py
# import frappe
# import unittest
# from unittest.mock import patch, MagicMock
# import json
# from datetime import datetime, timedelta
# from .test_base import BaseAPITest
# from tap_lms.api import (
#     create_teacher, get_school_name_keyword_list, send_otp, verify_otp,
#     create_teacher_web, update_teacher_role, get_teacher_by_glific_id
# )

# class TestCreateTeacher(BaseAPITest):
#     """Test teacher creation API"""
    
#     def setUp(self):
#         super().setUp()
#         self.school = self.create_test_school("TEST_SCHOOL", "test_keyword")
        
#     def test_create_teacher_success(self):
#         """Test successful teacher creation"""
#         result = create_teacher(
#             api_key=self.valid_api_key,
#             keyword="test_keyword",
#             first_name="John",
#             phone_number="1234567890",
#             glific_id="123",
#             last_name="Doe",
#             email="john@example.com",
#             language="English"
#         )
        
#         self.assertIn("message", result)
#         self.assertIn("teacher_id", result)
#         self.assertEqual(result["message"], "Teacher created successfully")
        
#     def test_create_teacher_invalid_api_key(self):
#         """Test teacher creation with invalid API key"""
#         with self.assertRaises(Exception) as context:
#             create_teacher(
#                 api_key=self.invalid_api_key,
#                 keyword="test_keyword",
#                 first_name="John",
#                 phone_number="1234567890",
#                 glific_id="123"
#             )
#         self.assertIn("Invalid API key", str(context.exception))
        
#     def test_create_teacher_invalid_keyword(self):
#         """Test teacher creation with invalid keyword"""
#         result = create_teacher(
#             api_key=self.valid_api_key,
#             keyword="invalid_keyword",
#             first_name="John",
#             phone_number="1234567890",
#             glific_id="123"
#         )
        
#         self.assertIn("error", result)
#         self.assertIn("No school found", result["error"])
        
#     def test_create_teacher_duplicate_phone(self):
#         """Test teacher creation with duplicate phone number"""
#         # Create first teacher
#         create_teacher(
#             api_key=self.valid_api_key,
#             keyword="test_keyword",
#             first_name="John",
#             phone_number="1234567890",
#             glific_id="123"
#         )
        
#         # Try to create second teacher with same phone
#         result = create_teacher(
#             api_key=self.valid_api_key,
#             keyword="test_keyword",
#             first_name="Jane",
#             phone_number="1234567890",
#             glific_id="124"
#         )
        
#         self.assertIn("error", result)
#         self.assertIn("already exists", result["error"])
        
#     def test_create_teacher_exception_handling(self):
#         """Test teacher creation exception handling"""
#         with patch('frappe.new_doc') as mock_new_doc:
#             mock_new_doc.side_effect = Exception("Database error")
            
#             result = create_teacher(
#                 api_key=self.valid_api_key,
#                 keyword="test_keyword",
#                 first_name="John",
#                 phone_number="1234567890",
#                 glific_id="123"
#             )
            
#             self.assertIn("error", result)
#             self.assertIn("Database error", result["error"])

# class TestSchoolKeywordList(BaseAPITest):
#     """Test school keyword listing API"""
    
#     def setUp(self):
#         super().setUp()
#         self.school1 = self.create_test_school("SCHOOL_1", "keyword1")
#         self.school2 = self.create_test_school("SCHOOL_2", "keyword2")
        
#     def test_get_school_name_keyword_list_success(self):
#         """Test successful school keyword list retrieval"""
#         result = get_school_name_keyword_list(
#             api_key=self.valid_api_key,
#             start=0,
#             limit=10
#         )
        
#         self.assertIsInstance(result, list)
#         self.assertGreater(len(result), 0)
        
#         # Check structure of returned data
#         for school_data in result:
#             self.assertIn("school_name", school_data)
#             self.assertIn("teacher_keyword", school_data)
#             self.assertIn("whatsapp_link", school_data)
#             self.assertTrue(school_data["teacher_keyword"].startswith("tapschool:"))
            
#     def test_get_school_name_keyword_list_invalid_api_key(self):
#         """Test school keyword list with invalid API key"""
#         with self.assertRaises(Exception) as context:
#             get_school_name_keyword_list(
#                 api_key=self.invalid_api_key,
#                 start=0,
#                 limit=10
#             )
#         self.assertIn("Invalid API key", str(context.exception))
        
#     def test_get_school_name_keyword_list_pagination(self):
#         """Test school keyword list pagination"""
#         result1 = get_school_name_keyword_list(
#             api_key=self.valid_api_key,
#             start=0,
#             limit=1
#         )
        
#         result2 = get_school_name_keyword_list(
#             api_key=self.valid_api_key,
#             start=1,
#             limit=1
#         )
        
#         self.assertEqual(len(result1), 1)
#         # Results should be different if we have more than 1 school
#         if len(result2) > 0:
#             self.assertNotEqual(result1[0]["school_name"], result2[0]["school_name"])

# class TestOTPAPIs(BaseAPITest):
#     """Test OTP sending and verification APIs"""
    
#     def setUp(self):
#         super().setUp()
#         # Create Gupshup OTP Settings if not exists
#         if not frappe.db.exists("Gupshup OTP Settings"):
#             settings = frappe.get_doc({
#                 "doctype": "Gupshup OTP Settings",
#                 "api_key": "test_api_key",
#                 "source_number": "1234567890",
#                 "app_name": "test_app",
#                 "api_endpoint": "https://test.api.com"
#             })
#             settings.insert(ignore_permissions=True)
            
#     @patch('requests.get')
#     def test_send_otp_success_new_teacher(self, mock_requests):
#         """Test successful OTP sending for new teacher"""
#         mock_response = MagicMock()
#         mock_response.json.return_value = {"status": "success", "id": "msg123"}
#         mock_requests.return_value = mock_response
        
#         data = {
#             "api_key": self.valid_api_key,
#             "phone": "9876543210"
#         }
#         self.mock_request_data(data)
        
#         result = send_otp()
        
#         self.assertEqual(result["status"], "success")
#         self.assertEqual(result["action_type"], "new_teacher")
#         self.assertEqual(frappe.response.http_status_code, 200)
        
#     def test_send_otp_existing_teacher(self):
#         """Test OTP sending for existing teacher"""
#         # Create test school and teacher
#         school = self.create_test_school("TEST_SCHOOL", "test_keyword")
#         batch = self.create_test_batch("TEST_BATCH")
#         self.create_test_batch_onboarding(school, batch)
        
#         teacher = frappe.get_doc({
#             "doctype": "Teacher",
#             "first_name": "John",
#             "phone_number": "9876543210",
#             "school_id": school,
#             "glific_id": "123"
#         })
#         teacher.insert(ignore_permissions=True)
        
#         with patch('requests.get') as mock_requests:
#             mock_response = MagicMock()
#             mock_response.json.return_value = {"status": "success", "id": "msg123"}
#             mock_requests.return_value = mock_response
            
#             data = {
#                 "api_key": self.valid_api_key,
#                 "phone": "9876543210"
#             }
#             self.mock_request_data(data)
            
#             result = send_otp()
            
#             self.assertEqual(result["status"], "success")
#             self.assertEqual(result["action_type"], "update_batch")
            
#     def test_send_otp_invalid_api_key(self):
#         """Test OTP sending with invalid API key"""
#         data = {
#             "api_key": self.invalid_api_key,
#             "phone": "9876543210"
#         }
#         self.mock_request_data(data)
        
#         result = send_otp()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 401)
        
#     def test_send_otp_missing_phone(self):
#         """Test OTP sending with missing phone"""
#         data = {"api_key": self.valid_api_key}
#         self.mock_request_data(data)
        
#         result = send_otp()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     @patch('requests.get')
#     def test_send_otp_whatsapp_failure(self, mock_requests):
#         """Test OTP sending with WhatsApp API failure"""
#         mock_response = MagicMock()
#         mock_response.json.return_value = {"status": "error", "message": "API error"}
#         mock_requests.return_value = mock_response
        
#         data = {
#             "api_key": self.valid_api_key,
#             "phone": "9876543210"
#         }
#         self.mock_request_data(data)
        
#         result = send_otp()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 500)
        
#     def test_verify_otp_success_new_teacher(self):
#         """Test successful OTP verification for new teacher"""
#         # First create OTP
#         otp_doc = frappe.get_doc({
#             "doctype": "OTP Verification",
#             "phone_number": "9876543210",
#             "otp": "1234",
#             "expiry": frappe.utils.now_datetime() + timedelta(minutes=15),
#             "verified": 0,
#             "context": json.dumps({"action_type": "new_teacher"})
#         })
#         otp_doc.insert(ignore_permissions=True)
        
#         data = {
#             "api_key": self.valid_api_key,
#             "phone": "9876543210",
#             "otp": "1234"
#         }
#         self.mock_request_data(data)
        
#         result = verify_otp()
        
#         self.assertEqual(result["status"], "success")
#         self.assertEqual(result["action_type"], "new_teacher")
#         self.assertEqual(frappe.response.http_status_code, 200)
        
#     def test_verify_otp_invalid_otp(self):
#         """Test OTP verification with invalid OTP"""
#         data = {
#             "api_key": self.valid_api_key,
#             "phone": "9876543210",
#             "otp": "0000"
#         }
#         self.mock_request_data(data)
        
#         result = verify_otp()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     def test_verify_otp_expired(self):
#         """Test OTP verification with expired OTP"""
#         # Create expired OTP
#         otp_doc = frappe.get_doc({
#             "doctype": "OTP Verification",
#             "phone_number": "9876543210",
#             "otp": "1234",
#             "expiry": frappe.utils.now_datetime() - timedelta(minutes=5),
#             "verified": 0,
#             "context": json.dumps({"action_type": "new_teacher"})
#         })
#         otp_doc.insert(ignore_permissions=True)
        
#         data = {
#             "api_key": self.valid_api_key,
#             "phone": "9876543210",
#             "otp": "1234"
#         }
#         self.mock_request_data(data)
        
#         result = verify_otp()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 400)
#         self.assertIn("expired", result["message"])
        
#     def test_verify_otp_already_used(self):
#         """Test OTP verification with already used OTP"""
#         # Create already verified OTP
#         otp_doc = frappe.get_doc({
#             "doctype": "OTP Verification",
#             "phone_number": "9876543210",
#             "otp": "1234",
#             "expiry": frappe.utils.now_datetime() + timedelta(minutes=15),
#             "verified": 1,
#             "context": json.dumps({"action_type": "new_teacher"})
#         })
#         otp_doc.insert(ignore_permissions=True)
        
#         data = {
#             "api_key": self.valid_api_key,
#             "phone": "9876543210",
#             "otp": "1234"
#         }
#         self.mock_request_data(data)
        
#         result = verify_otp()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 400)
#         self.assertIn("already used", result["message"])

# class TestCreateTeacherWeb(BaseAPITest):
#     """Test web teacher creation API"""
    
#     def setUp(self):
#         super().setUp()
#         self.school = self.create_test_school("TEST_SCHOOL", "test_keyword")
#         # Create verified OTP
#         otp_doc = frappe.get_doc({
#             "doctype": "OTP Verification",
#             "phone_number": "9876543210",
#             "otp": "1234",
#             "expiry": frappe.utils.now_datetime() + timedelta(minutes=15),
#             "verified": 1
#         })
#         otp_doc.insert(ignore_permissions=True)
        
#     @patch('tap_lms.api.create_contact')
#     @patch('tap_lms.api.enqueue_glific_actions')
#     def test_create_teacher_web_success(self, mock_enqueue, mock_create_contact):
#         """Test successful teacher creation via web"""
#         mock_create_contact.return_value = {"id": "glific123"}
        
#         data = {
#             "api_key": self.valid_api_key,
#             "firstName": "John",
#             "phone": "9876543210",
#             "School_name": "TEST_SCHOOL_DISPLAY",
#             "lastName": "Doe",
#             "email": "john@example.com",
#             "language": "English"
#         }
#         self.mock_request_data(data)
        
#         result = create_teacher_web()
        
#         self.assertEqual(result["status"], "success")
#         self.assertIn("teacher_id", result)
#         self.assertIn("glific_contact_id", result)
        
#     def test_create_teacher_web_unverified_phone(self):
#         """Test teacher creation with unverified phone"""
#         data = {
#             "api_key": self.valid_api_key,
#             "firstName": "John",
#             "phone": "1111111111",  # Unverified phone
#             "School_name": "TEST_SCHOOL_DISPLAY"
#         }
#         self.mock_request_data(data)
        
#         result = create_teacher_web()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertIn("not verified", result["message"])
        
#     def test_create_teacher_web_missing_fields(self):
#         """Test teacher creation with missing required fields"""
#         data = {
#             "api_key": self.valid_api_key,
#             "firstName": "John"
#             # Missing phone and School_name
#         }
#         self.mock_request_data(data)
        
#         result = create_teacher_web()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertIn("Missing required field", result["message"])
        
#     def test_create_teacher_web_invalid_school(self):
#         """Test teacher creation with invalid school"""
#         data = {
#             "api_key": self.valid_api_key,
#             "firstName": "John",
#             "phone": "9876543210",
#             "School_name": "NON_EXISTENT_SCHOOL"
#         }
#         self.mock_request_data(data)
        
#         result = create_teacher_web()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertIn("School not found", result["message"])

# class TestTeacherRoleManagement(BaseAPITest):
#     """Test teacher role management APIs"""
    
#     def setUp(self):
#         super().setUp()
#         self.school = self.create_test_school("TEST_SCHOOL", "test_keyword")
#         self.teacher = frappe.get_doc({
#             "doctype": "Teacher",
#             "first_name": "John",
#             "last_name": "Doe",
#             "phone_number": "9876543210",
#             "school_id": self.school,
#             "glific_id": "123",
#             "teacher_role": "Teacher"
#         })
#         self.teacher.insert(ignore_permissions=True)
        
#     def test_update_teacher_role_success(self):
#         """Test successful teacher role update"""
#         data = {
#             "api_key": self.valid_api_key,
#             "glific_id": "123",
#             "teacher_role": "HM"
#         }
#         self.mock_request_data(data)
        
#         result = update_teacher_role()
        
#         self.assertEqual(result["status"], "success")
#         self.assertEqual(result["data"]["new_role"], "HM")
#         self.assertEqual(result["data"]["old_role"], "Teacher")
#         self.assertEqual(frappe.response.http_status_code, 200)
        
#     def test_update_teacher_role_invalid_role(self):
#         """Test teacher role update with invalid role"""
#         data = {
#             "api_key": self.valid_api_key,
#             "glific_id": "123",
#             "teacher_role": "INVALID_ROLE"
#         }
#         self.mock_request_data(data)
        
#         result = update_teacher_role()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     def test_update_teacher_role_not_found(self):
#         """Test teacher role update for non-existent teacher"""
#         data = {
#             "api_key": self.valid_api_key,
#             "glific_id": "999",
#             "teacher_role": "HM"
#         }
#         self.mock_request_data(data)
        
#         result = update_teacher_role()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 404)
        
#     def test_get_teacher_by_glific_id_success(self):
#         """Test successful teacher retrieval by glific_id"""
#         data = {
#             "api_key": self.valid_api_key,
#             "glific_id": "123"
#         }
#         self.mock_request_data(data)
        
#         result = get_teacher_by_glific_id()
        
#         self.assertEqual(result["status"], "success")
#         self.assertEqual(result["data"]["glific_id"], "123")
#         self.assertEqual(result["data"]["first_name"], "John")
#         self.assertEqual(frappe.response.http_status_code, 200)
        
#     def test_get_teacher_by_glific_id_not_found(self):
#         """Test teacher retrieval for non-existent glific_id"""
#         data = {
#             "api_key": self.valid_api_key,
#             "glific_id": "999"
#         }
#         self.mock_request_data(data)
        
#         result = get_teacher_by_glific_id()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 404)