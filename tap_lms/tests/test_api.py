
"""
Solutions for fixing Frappe import issues in tests
"""

# =============================================================================
# SOLUTION 1: PROPER FRAPPE TEST SETUP (RECOMMENDED)
# =============================================================================
"""
Complete test_api.py for tapLMS
This is a comprehensive test file that should pass all tests.
Replace your current test_api.py with this entire file.
"""

import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta

# =============================================================================
# COMPLETE FRAPPE MOCKING SETUP
# =============================================================================

class MockFrappeUtils:
    """Complete mock of frappe.utils with all required functions"""
    
    @staticmethod
    def cint(value):
        try:
            if value is None or value == '':
                return 0
            return int(value)
        except (ValueError, TypeError):
            return 0
    
    @staticmethod
    def today():
        return "2025-01-15"
    
    @staticmethod
    def get_url():
        return "http://localhost:8000"
    
    @staticmethod
    def now_datetime():
        return datetime.now()
    
    @staticmethod
    def getdate(date_str=None):
        if date_str is None:
            return datetime.now().date()
        if isinstance(date_str, str):
            try:
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return datetime.now().date()
        return date_str
    
    @staticmethod
    def cstr(value):
        if value is None:
            return ""
        return str(value)
    
    @staticmethod
    def get_datetime(dt):
        if isinstance(dt, str):
            try:
                return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return datetime.now()
        return dt if dt else datetime.now()
    
    @staticmethod
    def add_days(date, days):
        if isinstance(date, str):
            date = datetime.strptime(date, '%Y-%m-%d').date()
        return date + timedelta(days=days)

class MockFrappe:
    """Complete mock of the frappe module"""
    
    def __init__(self):
        self.utils = MockFrappeUtils()
        
        # Response object
        self.response = Mock()
        self.response.http_status_code = 200
        self.response.status_code = 200
        
        # Local object for request data
        self.local = Mock()
        self.local.form_dict = {}
        
        # Database mock
        self.db = Mock()
        self.db.commit = Mock()
        self.db.rollback = Mock()
        self.db.sql = Mock(return_value=[])
        self.db.get_value = Mock(return_value="test_value")
        self.db.set_value = Mock()
        
        # Request object
        self.request = Mock()
        self.request.get_json = Mock(return_value={})
        self.request.data = '{}'
        
        # Flags and configuration
        self.flags = Mock()
        self.flags.ignore_permissions = False
        self.conf = Mock()
        
        # Form dict (sometimes accessed directly)
        self.form_dict = Mock()
        
        # Logger
        self.logger = Mock()
        self.logger.return_value = Mock()
        
        # Set up exception classes
        self.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
        self.ValidationError = type('ValidationError', (Exception,), {})
        self.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
    
    def get_doc(self, doctype, filters=None, **kwargs):
        """Enhanced get_doc that handles different document types"""
        
        if doctype == "API Key":
            if isinstance(filters, dict) and filters.get('key') == 'valid_key':
                doc = Mock()
                doc.name = "valid_api_key_doc"
                doc.key = "valid_key"
                doc.enabled = 1
                return doc
            else:
                raise self.DoesNotExistError("API Key not found")
        
        elif doctype == "Batch":
            doc = Mock()
            doc.name = "BATCH_001"
            doc.active = True
            doc.regist_end_date = (datetime.now() + timedelta(days=30)).date()
            doc.batch_id = "BATCH_2025_001"
            return doc
        
        elif doctype == "Student":
            doc = Mock()
            doc.name = "STUDENT_001"
            doc.name1 = "Test Student"
            doc.phone = "9876543210"
            doc.grade = "5"
            doc.language = "ENGLISH"
            doc.school_id = "SCHOOL_001"
            doc.glific_id = "glific_123"
            doc.insert = Mock()
            doc.save = Mock()
            doc.append = Mock()
            return doc
        
        elif doctype == "Teacher":
            doc = Mock()
            doc.name = "TEACHER_001"
            doc.first_name = "Test Teacher"
            doc.phone_number = "9876543210"
            doc.school_id = "SCHOOL_001"
            doc.glific_id = "glific_123"
            doc.insert = Mock()
            doc.save = Mock()
            return doc
        
        elif doctype == "OTP Verification":
            doc = Mock()
            doc.name = "OTP_VER_001"
            doc.phone_number = "9876543210"
            doc.otp = "1234"
            doc.expiry = datetime.now() + timedelta(minutes=15)
            doc.verified = False
            doc.context = "{}"
            doc.insert = Mock()
            doc.save = Mock()
            return doc
        
        # Default document
        doc = Mock()
        doc.name = "TEST_DOC"
        doc.insert = Mock()
        doc.save = Mock()
        doc.append = Mock()
        return doc
    
    def new_doc(self, doctype):
        """Create new document mock"""
        return self.get_doc(doctype)
    
    def get_all(self, doctype, filters=None, fields=None, **kwargs):
        """Enhanced get_all that returns realistic data"""
        
        if doctype == "Teacher" and filters and filters.get("phone_number"):
            return []  # No existing teacher by default
        
        elif doctype == "Student" and filters and filters.get("glific_id"):
            return []  # No existing student by default
        
        elif doctype == "Batch onboarding":
            if filters and filters.get("batch_skeyword") == "test_batch":
                return [{
                    'name': 'BATCH_ONBOARDING_001',
                    'school': 'SCHOOL_001',
                    'batch': 'BATCH_001',
                    'kit_less': 1,
                    'model': 'MODEL_001'
                }]
            elif filters and filters.get("batch_skeyword") == "invalid_batch":
                return []
            else:
                return [{
                    'school': 'SCHOOL_001',
                    'batch': 'BATCH_001',
                    'kit_less': 1,
                    'model': 'MODEL_001'
                }]
        
        elif doctype == "Course Verticals":
            if filters and filters.get("name2") == "Math":
                return [{'name': 'VERTICAL_001'}]
            else:
                return [{'name': 'VERTICAL_001'}]
        
        elif doctype == "District":
            return [{'name': 'DISTRICT_001', 'district_name': 'Test District'}]
        
        elif doctype == "City":
            return [{'name': 'CITY_001', 'city_name': 'Test City'}]
        
        elif doctype == "Batch":
            return [{'name': 'BATCH_001', 'batch_id': 'BATCH_2025_001'}]
        
        return []
    
    def get_single(self, doctype):
        """Get single document (settings, etc.)"""
        if doctype == "Gupshup OTP Settings":
            settings = Mock()
            settings.api_key = "test_gupshup_key"
            settings.source_number = "918454812392"
            settings.app_name = "test_app"
            settings.api_endpoint = "https://api.gupshup.io/sm/api/v1/msg"
            return settings
        
        return Mock()
    
    def get_value(self, doctype, name, field, **kwargs):
        """Enhanced get_value with realistic responses"""
        
        if doctype == "School" and field == "name1":
            return "Test School"
        elif doctype == "School" and field == "keyword":
            return "test_school"
        elif doctype == "Batch" and field == "batch_id":
            return "BATCH_2025_001"
        elif doctype == "OTP Verification" and field == "name":
            return "OTP_VER_001"
        elif doctype == "TAP Language" and field == "language_name":
            return "English"
        elif doctype == "TAP Language" and field == "glific_language_id":
            return "1"
        elif doctype == "District" and field == "district_name":
            return "Test District"
        elif doctype == "City" and field == "city_name":
            return "Test City"
        
        return "test_value"
    
    def throw(self, message):
        """Throw exception"""
        raise Exception(message)
    
    def log_error(self, message, title=None):
        """Log error (mock)"""
        pass
    
    def whitelist(self, allow_guest=False):
        """Whitelist decorator"""
        def decorator(func):
            return func
        return decorator
    
    def _dict(self, data=None):
        """Dict helper"""
        return data or {}
    
    def msgprint(self, message):
        """Message print"""
        pass

# Create and configure the mock
mock_frappe = MockFrappe()

# Mock external modules
mock_glific = Mock()
mock_glific.create_contact = Mock(return_value={'id': 'contact_123'})
mock_glific.start_contact_flow = Mock(return_value=True)
mock_glific.get_contact_by_phone = Mock(return_value=None)
mock_glific.update_contact_fields = Mock(return_value=True)
mock_glific.add_contact_to_group = Mock(return_value=True)
mock_glific.create_or_get_teacher_group_for_batch = Mock(return_value={'group_id': 'group_123', 'label': 'teacher_batch_test'})

mock_background = Mock()
mock_background.enqueue_glific_actions = Mock()

mock_requests = Mock()

# Inject all mocks into sys.modules
sys.modules['frappe'] = mock_frappe
sys.modules['frappe.utils'] = mock_frappe.utils
sys.modules['tap_lms.glific_integration'] = mock_glific
sys.modules['tap_lms.background_jobs'] = mock_background
sys.modules['requests'] = mock_requests

# NOW import the API functions
from tap_lms.api import (
    authenticate_api_key, 
    create_student, 
    send_otp, 
    list_districts,
    create_teacher_web,
    verify_batch_keyword
)

# =============================================================================
# COMPREHENSIVE TEST CLASSES
# =============================================================================

class TestTapLMSAPI(unittest.TestCase):
    """Main API test class with all test cases"""
    
    def setUp(self):
        """Reset mocks before each test"""
        mock_frappe.response.http_status_code = 200
        mock_frappe.local.form_dict = {}
        mock_frappe.request.data = '{}'
        mock_frappe.request.get_json.return_value = {}
        
        # Reset mock call counts
        if hasattr(mock_frappe.db.commit, 'reset_mock'):
            mock_frappe.db.commit.reset_mock()
            mock_frappe.db.rollback.reset_mock()

    # =========================================================================
    # AUTHENTICATION TESTS
    # =========================================================================

    def test_authenticate_api_key_valid(self):
        """Test authenticate_api_key with valid key"""
        result = authenticate_api_key("valid_key")
        self.assertEqual(result, "valid_api_key_doc")

    def test_authenticate_api_key_invalid(self):
        """Test authenticate_api_key with invalid key"""
        result = authenticate_api_key("invalid_key")
        self.assertIsNone(result)

    def test_authenticate_api_key_empty(self):
        """Test authenticate_api_key with empty/None key"""
        result = authenticate_api_key("")
        self.assertIsNone(result)
        
        result = authenticate_api_key(None)
        self.assertIsNone(result)

    # =========================================================================
    # STUDENT CREATION TESTS
    # =========================================================================

    def test_create_student_missing_api_key(self):
        """Test create_student without API key"""
        mock_frappe.local.form_dict = {
            'student_name': 'John Doe',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch',
            'vertical': 'Math',
            'glific_id': 'glific_123'
            # Missing api_key
        }
        
        result = create_student()
        self.assertEqual(result['status'], 'error')
        self.assertIn('required', result['message'].lower())

    def test_create_student_invalid_api_key(self):
        """Test create_student with invalid API key"""
        mock_frappe.local.form_dict = {
            'api_key': 'invalid_key',
            'student_name': 'John Doe',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch',
            'vertical': 'Math',
            'glific_id': 'glific_123'
        }
        
        result = create_student()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Invalid API key')

    def test_create_student_missing_required_fields(self):
        """Test create_student with missing required fields"""
        mock_frappe.local.form_dict = {
            'api_key': 'valid_key',
            'student_name': 'John Doe'
            # Missing other required fields
        }
        
        result = create_student()
        self.assertEqual(result['status'], 'error')
        self.assertIn('required', result['message'].lower())

    def test_create_student_invalid_batch(self):
        """Test create_student with invalid batch keyword"""
        mock_frappe.local.form_dict = {
            'api_key': 'valid_key',
            'student_name': 'John Doe',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'invalid_batch',
            'vertical': 'Math',
            'glific_id': 'glific_123'
        }
        
        result = create_student()
        self.assertEqual(result['status'], 'error')
        self.assertIn('batch', result['message'].lower())

    def test_create_student_success(self):
        """Test successful student creation"""
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
        
        with patch('tap_lms.api.get_course_level_with_mapping') as mock_course, \
             patch('tap_lms.api.create_new_student') as mock_create_student, \
             patch('tap_lms.api.get_tap_language') as mock_language:
            
            # Setup mocks for successful creation
            mock_course.return_value = 'COURSE_LEVEL_001'
            mock_language.return_value = 'ENGLISH'
            
            mock_student = Mock()
            mock_student.name = 'STUDENT_001'
            mock_student.append = Mock()
            mock_student.save = Mock()
            mock_create_student.return_value = mock_student
            
            result = create_student()
            
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['crm_student_id'], 'STUDENT_001')
            self.assertEqual(result['assigned_course_level'], 'COURSE_LEVEL_001')

    # =========================================================================
    # OTP TESTS  
    # =========================================================================

    def test_send_otp_success(self):
        """Test successful OTP sending"""
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key',
            'phone': '9876543210'
        }
        
        with patch('requests.get') as mock_requests_get:
            # Mock successful WhatsApp API response
            mock_response = Mock()
            mock_response.json.return_value = {
                "status": "success",
                "id": "msg_12345"
            }
            mock_requests_get.return_value = mock_response
            
            result = send_otp()
            
            self.assertEqual(result["status"], "success")
            self.assertIn("whatsapp_message_id", result)

    def test_send_otp_invalid_api_key(self):
        """Test send_otp with invalid API key"""
        mock_frappe.request.get_json.return_value = {
            'api_key': 'invalid_key',
            'phone': '9876543210'
        }
        
        result = send_otp()
        
        self.assertEqual(result["status"], "failure")
        self.assertEqual(result["message"], "Invalid API key")

    def test_send_otp_missing_phone(self):
        """Test send_otp without phone number"""
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key'
            # Missing phone
        }
        
        result = send_otp()
        
        self.assertEqual(result["status"], "failure")
        self.assertIn("phone", result["message"].lower())

    # =========================================================================
    # LOCATION TESTS
    # =========================================================================

    def test_list_districts_success(self):
        """Test successful district listing"""
        mock_frappe.request.data = json.dumps({
            'api_key': 'valid_key',
            'state': 'test_state'
        })
        
        result = list_districts()
        
        self.assertEqual(result["status"], "success")
        self.assertIn("data", result)

    def test_list_districts_invalid_api_key(self):
        """Test list_districts with invalid API key"""
        mock_frappe.request.data = json.dumps({
            'api_key': 'invalid_key',
            'state': 'test_state'
        })
        
        result = list_districts()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Invalid API key")

    def test_list_districts_missing_data(self):
        """Test list_districts with missing required data"""
        mock_frappe.request.data = json.dumps({
            'api_key': 'valid_key'
            # Missing state
        })
        
        result = list_districts()
        
        self.assertEqual(result["status"], "error")
        self.assertIn("required", result["message"].lower())


class TestTapLMSAPIIntegration(unittest.TestCase):
    """Integration tests for API functionality"""
    
    def setUp(self):
        """Setup for integration tests"""
        mock_frappe.response.http_status_code = 200

    def test_api_endpoint_accessibility(self):
        """Test that API endpoints are accessible and don't crash"""
        
        # Test authentication function
        try:
            result = authenticate_api_key("test_key")
            self.assertTrue(result is None or isinstance(result, str))
        except Exception as e:
            self.fail(f"Authentication endpoint failed: {str(e)}")
        
        # Test student creation with minimal data
        mock_frappe.local.form_dict = {
            'api_key': 'valid_key',
            'student_name': 'Test Student',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch',
            'vertical': 'Math',
            'glific_id': 'glific_123'
        }
        
        try:
            with patch('tap_lms.api.get_course_level_with_mapping', return_value='COURSE_001'), \
                 patch('tap_lms.api.create_new_student') as mock_create, \
                 patch('tap_lms.api.get_tap_language', return_value='ENGLISH'):
                
                mock_student = Mock()
                mock_student.name = 'STUDENT_001'
                mock_student.append = Mock()
                mock_student.save = Mock()
                mock_create.return_value = mock_student
                
                result = create_student()
                self.assertIsInstance(result, dict)
                self.assertIn('status', result)
        except Exception as e:
            self.fail(f"Student creation endpoint failed: {str(e)}")

    def test_external_api_integration(self):
        """Test external API integration with proper mocking"""
        
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key',
            'phone': '9876543210'
        }
        
        with patch('requests.get') as mock_requests_get:
            # Mock successful external API response
            mock_response = Mock()
            mock_response.json.return_value = {
                "status": "success",
                "id": "msg_12345"
            }
            mock_requests_get.return_value = mock_response
            
            try:
                result = send_otp()
                self.assertIsInstance(result, dict)
                self.assertIn('status', result)
            except Exception as e:
                self.fail(f"External API integration failed: {str(e)}")


# =============================================================================
# ADDITIONAL HELPER TESTS
# =============================================================================

class TestTapLMSAPIHelpers(unittest.TestCase):
    """Test helper functions and edge cases"""
    
    def test_mock_verification(self):
        """Verify that all mocks are working correctly"""
        
        # Test frappe utils
        self.assertEqual(mock_frappe.utils.cint("5"), 5)
        self.assertEqual(mock_frappe.utils.cstr(123), "123")
        self.assertEqual(mock_frappe.utils.today(), "2025-01-15")
        
        # Test frappe methods
        self.assertTrue(callable(mock_frappe.get_doc))
        self.assertTrue(callable(mock_frappe.get_all))
        self.assertTrue(callable(mock_frappe.get_value))
        
        # Test exception classes
        self.assertTrue(issubclass(mock_frappe.DoesNotExistError, Exception))
        self.assertTrue(issubclass(mock_frappe.ValidationError, Exception))

    def test_form_dict_handling(self):
        """Test form_dict data handling"""
        
        test_data = {
            'string_field': 'test_value',
            'number_field': 123,
            'empty_field': '',
            'none_field': None
        }
        
        mock_frappe.local.form_dict = test_data
        
        # Verify data is accessible
        self.assertEqual(mock_frappe.local.form_dict['string_field'], 'test_value')
        self.assertEqual(mock_frappe.local.form_dict['number_field'], 123)
        self.assertEqual(mock_frappe.local.form_dict.get('empty_field'), '')
        self.assertIsNone(mock_frappe.local.form_dict.get('none_field'))

    def test_database_operations(self):
        """Test database operation mocks"""
        
        # Test get_value
        result = mock_frappe.get_value("School", "SCHOOL_001", "name1")
        self.assertEqual(result, "Test School")
        
        # Test get_all
        result = mock_frappe.get_all("District", filters={"state": "test_state"})
        self.assertIsInstance(result, list)
        
        # Test database transaction methods
        mock_frappe.db.commit()
        mock_frappe.db.rollback()
        
        # Should not raise exceptions
        self.assertTrue(True)


# =============================================================================
# TEST RUNNER
# =============================================================================

if __name__ == '__main__':
    # Run all tests with detailed output
    unittest.main(verbosity=2, buffer=False)