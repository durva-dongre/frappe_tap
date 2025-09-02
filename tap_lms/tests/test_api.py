"""
TARGETED HIGH-COVERAGE Test Suite for tap_lms/api.py

This approach mocks ONLY external dependencies, allowing the actual API code to execute
and be measured by coverage tools. The key is to mock frappe.* calls but let our
API functions run their real logic.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# =============================================================================
# MINIMAL TARGETED MOCKS - Only Mock External Dependencies
# =============================================================================

# Create minimal frappe mock that only handles external calls
frappe_mock = Mock()
frappe_mock.utils = Mock()
frappe_mock.utils.cint = lambda x: int(x) if x and str(x).isdigit() else 0
frappe_mock.utils.today = lambda: "2025-01-15"
frappe_mock.utils.now_datetime = lambda: datetime.now()
frappe_mock.utils.getdate = lambda x=None: datetime.strptime(x, '%Y-%m-%d').date() if x and isinstance(x, str) else datetime.now().date()
frappe_mock.utils.cstr = lambda x: str(x) if x is not None else ""
frappe_mock.utils.get_datetime = lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S') if isinstance(x, str) else (x if isinstance(x, datetime) else datetime.now())

# Response mock
frappe_mock.response = Mock()
frappe_mock.response.http_status_code = 200
frappe_mock.response.update = Mock()

# Request mock
frappe_mock.request = Mock()
frappe_mock.request.get_json = Mock()
frappe_mock.request.data = '{}'
frappe_mock.local = Mock()
frappe_mock.local.form_dict = {}

# Database operations mock - return realistic data
frappe_mock.db = Mock()
frappe_mock.db.commit = Mock()
frappe_mock.db.rollback = Mock()

# Other frappe functions
frappe_mock.flags = Mock()
frappe_mock.flags.ignore_permissions = False
frappe_mock.log_error = Mock()
frappe_mock.logger = Mock(return_value=Mock())
frappe_mock.throw = Mock(side_effect=Exception)
frappe_mock.whitelist = Mock(return_value=lambda x: x)
frappe_mock.as_json = Mock(side_effect=json.dumps)
frappe_mock._dict = Mock(side_effect=lambda x: x or {})

# Exception classes
frappe_mock.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
frappe_mock.ValidationError = type('ValidationError', (Exception,), {})
frappe_mock.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})

# Mock external dependencies
requests_mock = Mock()
requests_mock.get = Mock()
requests_mock.post = Mock()
requests_mock.RequestException = Exception

random_mock = Mock()
random_mock.choices = Mock(return_value=['1', '2', '3', '4'])
string_mock = Mock()
string_mock.digits = '0123456789'

# Mock integration modules
glific_mock = Mock()
glific_mock.create_contact = Mock(return_value={'id': 'contact_123'})
glific_mock.get_contact_by_phone = Mock(return_value={'id': 'contact_123'})
glific_mock.update_contact_fields = Mock(return_value=True)
glific_mock.add_contact_to_group = Mock(return_value=True)
glific_mock.create_or_get_teacher_group_for_batch = Mock(return_value={'group_id': 'group_123'})
glific_mock.start_contact_flow = Mock(return_value=True)

bg_jobs_mock = Mock()
bg_jobs_mock.enqueue_glific_actions = Mock()

# Inject minimal mocks
sys.modules['frappe'] = frappe_mock
sys.modules['frappe.utils'] = frappe_mock.utils
sys.modules['requests'] = requests_mock
sys.modules['random'] = random_mock
sys.modules['string'] = string_mock
sys.modules['urllib'] = Mock()
sys.modules['urllib.parse'] = Mock()
sys.modules['tap_lms.glific_integration'] = glific_mock
sys.modules['tap_lms.background_jobs'] = bg_jobs_mock
sys.modules['.glific_integration'] = glific_mock
sys.modules['.background_jobs'] = bg_jobs_mock

# =============================================================================
# PATCH STRATEGY - Mock specific frappe calls to return test data
# =============================================================================

class TargetedHighCoverageTests(unittest.TestCase):
    """Tests designed to execute actual API code with minimal mocking"""
    
    def setUp(self):
        """Setup for each test"""
        frappe_mock.response.http_status_code = 200
        frappe_mock.response.reset_mock()
        frappe_mock.local.form_dict = {}
        frappe_mock.request.data = '{}'
        frappe_mock.request.get_json.return_value = {}

    # Import API module inside test methods to ensure mocks are in place
    def get_api_module(self):
        """Dynamically import API module"""
        try:
            import tap_lms.api as api
            return api
        except ImportError:
            self.skipTest("Could not import tap_lms.api")

    # =============================================================================
    # AUTHENTICATION FUNCTION TESTS - Execute Real Code
    # =============================================================================

    def test_authenticate_api_key_real_execution(self):
        """Test authenticate_api_key with real code execution"""
        api = self.get_api_module()
        
        # Mock frappe.get_doc to return valid API key doc
        with patch.object(frappe_mock, 'get_doc') as mock_get_doc:
            # Test valid API key
            mock_doc = Mock()
            mock_doc.name = "API_KEY_001"
            mock_get_doc.return_value = mock_doc
            
            result = api.authenticate_api_key('valid_key')
            self.assertEqual(result, "API_KEY_001")
            
            # Test invalid API key (DoesNotExistError)
            mock_get_doc.side_effect = frappe_mock.DoesNotExistError("Not found")
            result = api.authenticate_api_key('invalid_key')
            self.assertIsNone(result)

    # =============================================================================
    # BATCH MANAGEMENT TESTS - Execute Real Code
    # =============================================================================

    def test_get_active_batch_for_school_real_execution(self):
        """Test get_active_batch_for_school with real code execution"""
        api = self.get_api_module()
        
        # Test with active batch found
        with patch.object(frappe_mock, 'get_all') as mock_get_all:
            with patch.object(frappe_mock.db, 'get_value') as mock_get_value:
                # Mock data for active batch
                mock_get_all.side_effect = [
                    [{'batch': 'BATCH_001'}],  # Batch onboarding
                    ['BATCH_001', 'BATCH_002']  # Active batches
                ]
                mock_get_value.return_value = 'BATCH_2025_001'  # batch_id
                
                result = api.get_active_batch_for_school('SCHOOL_001')
                
                self.assertIsInstance(result, dict)
                self.assertIn('batch_name', result)
                self.assertIn('batch_id', result)
                self.assertEqual(result['batch_name'], 'BATCH_001')
                self.assertEqual(result['batch_id'], 'BATCH_2025_001')
        
        # Test with no active batch
        with patch.object(frappe_mock, 'get_all', return_value=[]):
            result = api.get_active_batch_for_school('SCHOOL_002')
            
            self.assertIsInstance(result, dict)
            self.assertIsNone(result['batch_name'])
            self.assertEqual(result['batch_id'], 'no_active_batch_id')

    # =============================================================================
    # DISTRICT/CITY API TESTS - Execute Real Code
    # =============================================================================

    def test_list_districts_real_execution(self):
        """Test list_districts with real code execution"""
        api = self.get_api_module()
        
        # Test successful case
        test_data = {'api_key': 'valid_key', 'state': 'test_state'}
        frappe_mock.request.data = json.dumps(test_data)
        
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock, 'get_all') as mock_get_all:
                mock_get_all.return_value = [
                    {'name': 'DIST_001', 'district_name': 'District 1'},
                    {'name': 'DIST_002', 'district_name': 'District 2'}
                ]
                
                result = api.list_districts()
                
                self.assertIsInstance(result, dict)
                self.assertEqual(result['status'], 'success')
                self.assertIn('data', result)
        
        # Test missing parameters
        frappe_mock.request.data = json.dumps({'api_key': 'valid_key'})
        result = api.list_districts()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(frappe_mock.response.http_status_code, 400)
        
        # Test invalid API key
        frappe_mock.request.data = json.dumps(test_data)
        with patch.object(api, 'authenticate_api_key', return_value=None):
            result = api.list_districts()
            self.assertEqual(result['status'], 'error')
            self.assertEqual(frappe_mock.response.http_status_code, 401)

    def test_list_cities_real_execution(self):
        """Test list_cities with real code execution"""
        api = self.get_api_module()
        
        # Test successful case
        test_data = {'api_key': 'valid_key', 'district': 'test_district'}
        frappe_mock.request.data = json.dumps(test_data)
        
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock, 'get_all') as mock_get_all:
                mock_get_all.return_value = [
                    {'name': 'CITY_001', 'city_name': 'City 1'},
                    {'name': 'CITY_002', 'city_name': 'City 2'}
                ]
                
                result = api.list_cities()
                
                self.assertIsInstance(result, dict)
                self.assertEqual(result['status'], 'success')
                self.assertIn('data', result)

    # =============================================================================
    # KEYWORD VERIFICATION TESTS - Execute Real Code
    # =============================================================================

    def test_verify_keyword_real_execution(self):
        """Test verify_keyword with real code execution"""
        api = self.get_api_module()
        
        # Test valid keyword
        frappe_mock.request.get_json.return_value = {'api_key': 'valid_key', 'keyword': 'test_keyword'}
        
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock.db, 'get_value') as mock_get_value:
                mock_get_value.return_value = {'name1': 'Test School', 'model': 'Model 1'}
                
                result = api.verify_keyword()
                
                # Function uses frappe.response.update, so check response was called
                frappe_mock.response.update.assert_called()
                self.assertEqual(frappe_mock.response.http_status_code, 200)
        
        # Test keyword not found
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock.db, 'get_value', return_value=None):
                result = api.verify_keyword()
                self.assertEqual(frappe_mock.response.http_status_code, 404)

    def test_verify_batch_keyword_real_execution(self):
        """Test verify_batch_keyword with real code execution"""
        api = self.get_api_module()
        
        # Test valid batch keyword
        test_data = {'api_key': 'valid_key', 'batch_skeyword': 'test_batch'}
        frappe_mock.request.data = json.dumps(test_data)
        
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock, 'get_all') as mock_get_all:
                with patch.object(frappe_mock, 'get_doc') as mock_get_doc:
                    with patch.object(frappe_mock.db, 'get_value') as mock_get_value:
                        # Mock batch onboarding data
                        mock_get_all.return_value = [{
                            'school': 'SCHOOL_001', 'batch': 'BATCH_001', 
                            'model': 'MODEL_001', 'kit_less': 1
                        }]
                        
                        # Mock batch document
                        mock_batch = Mock()
                        mock_batch.active = True
                        mock_batch.regist_end_date = datetime.now().date() + timedelta(days=30)
                        mock_get_doc.return_value = mock_batch
                        
                        # Mock other data
                        mock_get_value.side_effect = [
                            'Test School',      # school name
                            'BATCH_2025_001',   # batch_id
                            'Test District'     # district name
                        ]
                        
                        # Mock Tap Model
                        mock_tap_model = Mock()
                        mock_tap_model.name = 'MODEL_001'
                        mock_tap_model.mname = 'Test Model'
                        with patch.object(frappe_mock, 'get_doc', return_value=mock_tap_model):
                            result = api.verify_batch_keyword()
                            
                            self.assertIsInstance(result, dict)
                            self.assertEqual(result['status'], 'success')
                            self.assertEqual(frappe_mock.response.http_status_code, 200)

    # =============================================================================
    # STUDENT CREATION TESTS - Execute Real Code
    # =============================================================================

    def test_create_student_real_execution(self):
        """Test create_student with real code execution"""
        api = self.get_api_module()
        
        # Set up form data
        form_data = {
            'api_key': 'valid_key',
            'student_name': 'Test Student',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch',
            'vertical': 'Math',
            'glific_id': 'test_glific'
        }
        frappe_mock.local.form_dict = form_data
        
        # Mock all the dependencies
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock, 'get_all') as mock_get_all:
                with patch.object(frappe_mock, 'get_doc') as mock_get_doc:
                    with patch.object(api, 'get_tap_language') as mock_get_lang:
                        with patch.object(api, 'get_course_level_with_mapping') as mock_get_course:
                            # Mock batch onboarding
                            mock_get_all.side_effect = [
                                [{'school': 'SCHOOL_001', 'batch': 'BATCH_001', 'kit_less': 1}],  # batch onboarding
                                [],  # no existing student
                                [{'name': 'VERTICAL_001'}]  # course vertical
                            ]
                            
                            # Mock batch document
                            mock_batch = Mock()
                            mock_batch.active = True
                            mock_batch.regist_end_date = datetime.now().date() + timedelta(days=30)
                            mock_get_doc.return_value = mock_batch
                            
                            # Mock other functions
                            mock_get_lang.return_value = 'LANG_001'
                            mock_get_course.return_value = 'COURSE_001'
                            
                            result = api.create_student()
                            
                            self.assertIsInstance(result, dict)
                            self.assertEqual(result['status'], 'success')

    # =============================================================================
    # OTP FUNCTIONALITY TESTS - Execute Real Code
    # =============================================================================

    def test_send_otp_real_execution(self):
        """Test send_otp with real code execution"""
        api = self.get_api_module()
        
        # Test new teacher case
        frappe_mock.request.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
        
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock, 'get_all', return_value=[]):  # No existing teacher
                with patch.object(frappe_mock, 'get_doc') as mock_get_doc:
                    with patch.object(requests_mock, 'get') as mock_request:
                        # Mock OTP doc creation
                        mock_otp_doc = Mock()
                        mock_get_doc.return_value = mock_otp_doc
                        
                        # Mock successful WhatsApp response
                        mock_response = Mock()
                        mock_response.json.return_value = {"status": "success", "id": "msg_123"}
                        mock_request.return_value = mock_response
                        
                        result = api.send_otp()
                        
                        self.assertIsInstance(result, dict)
                        self.assertEqual(result['status'], 'success')
                        self.assertEqual(frappe_mock.response.http_status_code, 200)

    def test_verify_otp_real_execution(self):
        """Test verify_otp with real code execution"""
        api = self.get_api_module()
        
        frappe_mock.request.get_json.return_value = {
            'api_key': 'valid_key', 'phone': '9876543210', 'otp': '1234'
        }
        
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock.db, 'sql') as mock_sql:
                # Mock OTP verification data
                mock_sql.return_value = [{
                    'name': 'OTP_001',
                    'expiry': datetime.now() + timedelta(minutes=15),
                    'context': '{"action_type": "new_teacher"}',
                    'verified': False
                }]
                
                result = api.verify_otp()
                
                self.assertIsInstance(result, dict)
                self.assertEqual(result['status'], 'success')
                self.assertEqual(frappe_mock.response.http_status_code, 200)

    # =============================================================================
    # UTILITY FUNCTION TESTS - Execute Real Code  
    # =============================================================================

    def test_send_whatsapp_message_real_execution(self):
        """Test send_whatsapp_message with real code execution"""
        api = self.get_api_module()
        
        # Test successful case
        with patch.object(frappe_mock, 'get_single') as mock_get_single:
            with patch.object(requests_mock, 'post') as mock_post:
                # Mock Gupshup settings
                mock_settings = Mock()
                mock_settings.api_key = 'test_key'
                mock_settings.source_number = '123456'
                mock_settings.app_name = 'test_app'
                mock_settings.api_endpoint = 'https://api.test.com'
                mock_get_single.return_value = mock_settings
                
                # Mock successful response
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_post.return_value = mock_response
                
                result = api.send_whatsapp_message('9876543210', 'Test message')
                
                self.assertTrue(result)
        
        # Test no settings case
        with patch.object(frappe_mock, 'get_single', return_value=None):
            result = api.send_whatsapp_message('9876543210', 'Test message')
            self.assertFalse(result)

    # =============================================================================
    # COMPREHENSIVE FUNCTION COVERAGE TESTS
    # =============================================================================

    def test_remaining_api_functions_real_execution(self):
        """Test remaining API functions with real execution"""
        api = self.get_api_module()
        
        # Test get_school_name_keyword_list
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock.db, 'get_all') as mock_get_all:
                mock_get_all.return_value = [
                    {'name': 'SCHOOL_001', 'name1': 'School 1', 'keyword': 'school1'}
                ]
                result = api.get_school_name_keyword_list('valid_key', 0, 10)
                self.assertIsInstance(result, list)
        
        # Test grade_list
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock, 'get_all') as mock_get_all:
                mock_get_all.return_value = [{'name': 'BATCH_001', 'from_grade': '1', 'to_grade': '10'}]
                result = api.grade_list('valid_key', 'test_keyword')
                self.assertIsInstance(result, dict)
        
        # Test list_batch_keyword
        with patch.object(api, 'authenticate_api_key', return_value='API_KEY_001'):
            with patch.object(frappe_mock, 'get_all') as mock_get_all:
                with patch.object(frappe_mock, 'get_doc') as mock_get_doc:
                    mock_get_all.return_value = [
                        {'batch': 'BATCH_001', 'school': 'SCHOOL_001', 'batch_skeyword': 'batch1'}
                    ]
                    mock_batch = Mock()
                    mock_batch.active = True
                    mock_batch.regist_end_date = datetime.now().date() + timedelta(days=30)
                    mock_batch.batch_id = 'BATCH_2025_001'
                    mock_get_doc.return_value = mock_batch
                    
                    with patch.object(frappe_mock.db, 'get_value', return_value='Test School'):
                        result = api.list_batch_keyword('valid_key')
                        self.assertIsInstance(result, list)

    # =============================================================================
    # HELPER FUNCTIONS TESTS - Execute Real Code
    # =============================================================================

    def test_helper_functions_real_execution(self):
        """Test helper functions with real execution"""
        api = self.get_api_module()
        
        # Test determine_student_type if it exists
        if hasattr(api, 'determine_student_type'):
            with patch.object(frappe_mock.db, 'sql', return_value=[]):
                result = api.determine_student_type('9876543210', 'Test Student', 'VERTICAL_001')
                self.assertEqual(result, 'New')
            
            with patch.object(frappe_mock.db, 'sql', return_value=[{'name': 'STUDENT_001'}]):
                result = api.determine_student_type('9876543210', 'Test Student', 'VERTICAL_001')
                self.assertEqual(result, 'Old')
        
        # Test get_current_academic_year if it exists
        if hasattr(api, 'get_current_academic_year'):
            result = api.get_current_academic_year()
            self.assertIsInstance(result, str)
        
        # Test get_model_for_school
        if hasattr(api, 'get_model_for_school'):
            with patch.object(frappe_mock, 'get_all') as mock_get_all:
                with patch.object(frappe_mock.db, 'get_value') as mock_get_value:
                    mock_get_all.return_value = [{'model': 'MODEL_001'}]
                    mock_get_value.return_value = 'Test Model'
                    
                    result = api.get_model_for_school('SCHOOL_001')
                    self.assertEqual(result, 'Test Model')

if __name__ == '__main__':
    print("=" * 80)
    print("TARGETED HIGH-COVERAGE TEST SUITE")
    print("Mocking only external dependencies, executing real API code...")
    print("=" * 80)
    
    unittest.main(verbosity=2)