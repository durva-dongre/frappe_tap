"""
Test Suite for tap_lms/api.py
Focus: Success paths with comprehensive assertions
"""

import sys
import unittest
from unittest.mock import Mock, patch
import json
from datetime import datetime, timedelta

# =============================================================================
# MOCK SETUP
# =============================================================================

class MockFrappeUtils:
    @staticmethod
    def cint(value):
        try:
            return 0 if value is None or value == '' else int(value)
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
        return "" if value is None else str(value)
    
    @staticmethod
    def get_datetime(dt):
        if isinstance(dt, str):
            try:
                return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return datetime.now()
        return dt if dt else datetime.now()


class MockFrappeDocument:
    def __init__(self, doctype, name=None, **kwargs):
        self.doctype = doctype
        self.name = name or f"{doctype.upper().replace(' ', '_')}_001"
        self.creation = kwargs.get('creation', datetime.now())
        self.modified = kwargs.get('modified', datetime.now())
        self.owner = kwargs.get('owner', 'Administrator')
        self.modified_by = kwargs.get('modified_by', 'Administrator')
        self.docstatus = kwargs.get('docstatus', 0)
        self.idx = kwargs.get('idx', 1)
        
        self._setup_attributes(doctype, kwargs)
        
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)
    
    def _setup_attributes(self, doctype, kwargs):
        if doctype == "API Key":
            self.key = kwargs.get('key', 'valid_key')
            self.enabled = kwargs.get('enabled', 1)
            self.api_key_name = kwargs.get('api_key_name', 'Test API Key')
            
        elif doctype == "Student":
            self.name1 = kwargs.get('name1', 'Test Student')
            self.phone = kwargs.get('phone', '9876543210')
            self.grade = kwargs.get('grade', '5')
            self.language = kwargs.get('language', 'LANG_001')
            self.school_id = kwargs.get('school_id', 'SCHOOL_001')
            self.glific_id = kwargs.get('glific_id', 'glific_123')
            self.gender = kwargs.get('gender', 'Male')
            self.joined_on = kwargs.get('joined_on', datetime.now().date())
            self.status = kwargs.get('status', 'active')
            self.enrollment = kwargs.get('enrollment', [])
            
        elif doctype == "Teacher":
            self.first_name = kwargs.get('first_name', 'Test')
            self.last_name = kwargs.get('last_name', 'Teacher')
            self.phone_number = kwargs.get('phone_number', '9876543210')
            self.school_id = kwargs.get('school_id', 'SCHOOL_001')
            self.glific_id = kwargs.get('glific_id', '')
            self.email_id = kwargs.get('email_id', 'teacher@example.com')
            self.teacher_role = kwargs.get('teacher_role', 'Teacher')
            self.language = kwargs.get('language', 'LANG_001')
            
        elif doctype == "OTP Verification":
            self.phone_number = kwargs.get('phone_number', '9876543210')
            self.otp = kwargs.get('otp', '1234')
            self.expiry = kwargs.get('expiry', datetime.now() + timedelta(minutes=15))
            self.verified = kwargs.get('verified', 0)
            self.context = kwargs.get('context', '{}')
            
        elif doctype == "Batch":
            self.batch_id = kwargs.get('batch_id', 'BATCH_2025_001')
            self.name1 = kwargs.get('name1', 'Batch 2025')
            self.active = kwargs.get('active', True)
            self.regist_end_date = kwargs.get('regist_end_date', (datetime.now() + timedelta(days=30)).date())
            self.start_date = kwargs.get('start_date', datetime.now().date())
            self.end_date = kwargs.get('end_date', (datetime.now() + timedelta(days=90)).date())
            
        elif doctype == "School":
            self.name1 = kwargs.get('name1', 'Test School')
            self.keyword = kwargs.get('keyword', 'test_school')
            self.city = kwargs.get('city', 'CITY_001')
            self.district = kwargs.get('district', 'DISTRICT_001')
            self.state = kwargs.get('state', 'STATE_001')
            self.model = kwargs.get('model', 'MODEL_001')
            
        elif doctype == "Batch onboarding":
            self.batch_skeyword = kwargs.get('batch_skeyword', 'test_batch')
            self.school = kwargs.get('school', 'SCHOOL_001')
            self.batch = kwargs.get('batch', 'BATCH_001')
            self.kit_less = kwargs.get('kit_less', 1)
            self.model = kwargs.get('model', 'MODEL_001')
            self.from_grade = kwargs.get('from_grade', '1')
            self.to_grade = kwargs.get('to_grade', '10')
    
    def insert(self, ignore_permissions=False):
        return self
    
    def save(self, ignore_permissions=False):
        return self
    
    def append(self, field, data):
        if not hasattr(self, field):
            setattr(self, field, [])
        getattr(self, field).append(data)
        return self
    
    def get(self, field, default=None):
        return getattr(self, field, default)


class MockFrappe:
    def __init__(self):
        self.utils = MockFrappeUtils()
        self.response = Mock()
        self.response.http_status_code = 200
        self.response.update = Mock()
        self.local = Mock()
        self.local.form_dict = {}
        self.db = Mock()
        self.db.commit = Mock()
        self.db.rollback = Mock()
        self.db.sql = Mock(return_value=[])
        self.db.get_value = Mock(return_value="test_value")
        self.db.get_all = Mock(return_value=[])
        self.request = Mock()
        self.request.get_json = Mock(return_value={})
        self.request.data = '{}'
        self.flags = Mock()
        self.flags.ignore_permissions = False
        self.conf = Mock()
        self.conf.get = Mock(side_effect=lambda key, default: default)
        self.logger = Mock(return_value=Mock())
        
        self.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
        self.ValidationError = type('ValidationError', (Exception,), {})
        self.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
        
        self._configure_mocks()
    
    def _configure_mocks(self):
        def get_doc_side_effect(doctype, filters=None, **kwargs):
            if doctype == "API Key":
                key = filters.get('key') if isinstance(filters, dict) else filters
                if key in ['valid_key', 'test_key']:
                    return MockFrappeDocument(doctype, key=key, enabled=1)
                raise self.DoesNotExistError("API Key not found")
            return MockFrappeDocument(doctype, **kwargs)
        
        self.get_doc = Mock(side_effect=get_doc_side_effect)
    
    def new_doc(self, doctype):
        return MockFrappeDocument(doctype)
    
    def get_single(self, doctype):
        return MockFrappeDocument(doctype)
    
    def get_all(self, *args, **kwargs):
        return []
    
    def throw(self, message):
        raise Exception(message)
    
    def log_error(self, message, title=None):
        pass
    
    def whitelist(self, allow_guest=False):
        def decorator(func):
            return func
        return decorator


mock_frappe = MockFrappe()
mock_glific = Mock()
mock_background = Mock()
mock_requests = Mock()
mock_random = Mock()
mock_random.choices = Mock(return_value=['1', '2', '3', '4'])
mock_string = Mock()
mock_string.digits = '0123456789'

sys.modules['frappe'] = mock_frappe
sys.modules['frappe.utils'] = mock_frappe.utils
sys.modules['.glific_integration'] = mock_glific
sys.modules['tap_lms.glific_integration'] = mock_glific
sys.modules['.background_jobs'] = mock_background
sys.modules['tap_lms.background_jobs'] = mock_background
sys.modules['requests'] = mock_requests
sys.modules['random'] = mock_random
sys.modules['string'] = mock_string

try:
    import tap_lms.api as api_module
    API_MODULE_IMPORTED = True
except ImportError as e:
    print(f"ERROR: Could not import tap_lms.api: {e}")
    API_MODULE_IMPORTED = False
    api_module = None

# =============================================================================
# TEST SUITE
# =============================================================================

class BaseAPITest(unittest.TestCase):
    """Base test class with common setup"""
    
    def setUp(self):
        mock_frappe.response.http_status_code = 200
        mock_frappe.response.update = Mock()
        mock_frappe.local.form_dict = {}
        mock_frappe.request.data = '{}'
        mock_frappe.request.get_json.return_value = {}
        mock_frappe.request.get_json.side_effect = None
        mock_frappe.db.commit.reset_mock()
        mock_frappe.db.rollback.reset_mock()
        
        mock_glific.reset_mock()
        mock_glific.get_contact_by_phone = Mock(return_value={'id': 'contact_123'})
        mock_glific.create_contact = Mock(return_value={'id': 'new_contact_123'})
        mock_glific.update_contact_fields = Mock(return_value=True)
        
        mock_background.reset_mock()
        mock_background.enqueue_glific_actions = Mock()
        
        mock_requests.reset_mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}
        mock_requests.get.return_value = mock_response
        mock_requests.post.return_value = mock_response


@unittest.skipUnless(API_MODULE_IMPORTED, "API module not available")
class TestAuthentication(BaseAPITest):
    
    def test_valid_api_key(self):
        result = api_module.authenticate_api_key("valid_key")
        self.assertEqual(result, "valid_key")
    
    def test_invalid_api_key(self):
        result = api_module.authenticate_api_key("invalid_key")
        self.assertIsNone(result)


@unittest.skipUnless(API_MODULE_IMPORTED, "API module not available")
class TestListDistricts(BaseAPITest):
    
    def test_success_path(self):
        mock_frappe.request.data = json.dumps({
            'api_key': 'valid_key',
            'state': 'STATE_001'
        })
        
        with patch.object(mock_frappe, 'get_all') as mock_get_all:
            mock_get_all.return_value = [
                {'name': 'DIST_001', 'district_name': 'District 1'},
                {'name': 'DIST_002', 'district_name': 'District 2'}
            ]
            
            result = api_module.list_districts()
            
            self.assertEqual(result['status'], 'success')
            self.assertEqual(len(result['data']), 2)
            self.assertEqual(result['data']['DIST_001'], 'District 1')
            self.assertEqual(mock_frappe.response.http_status_code, 200)
            mock_get_all.assert_called_once()
    
    def test_invalid_api_key(self):
        mock_frappe.request.data = json.dumps({
            'api_key': 'invalid_key',
            'state': 'STATE_001'
        })
        
        result = api_module.list_districts()
        
        self.assertEqual(result['status'], 'error')
        self.assertEqual(mock_frappe.response.http_status_code, 401)


@unittest.skipUnless(API_MODULE_IMPORTED, "API module not available")
class TestVerifyKeyword(BaseAPITest):
    
    def test_success_path(self):
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key',
            'keyword': 'test_school'
        }
        
        with patch.object(mock_frappe.db, 'get_value') as mock_get:
            mock_school = Mock()
            mock_school.name1 = 'Test School'
            mock_school.model = 'MODEL_001'
            mock_get.return_value = mock_school
            
            result = api_module.verify_keyword()
            
            mock_frappe.response.update.assert_called_once()
            call_args = mock_frappe.response.update.call_args[0][0]
            
            self.assertEqual(call_args['status'], 'success')
            self.assertEqual(call_args['school_name'], 'Test School')
            self.assertEqual(call_args['model'], 'MODEL_001')
            self.assertEqual(mock_frappe.response.http_status_code, 200)
    
    def test_keyword_not_found(self):
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key',
            'keyword': 'nonexistent'
        }
        
        with patch.object(mock_frappe.db, 'get_value') as mock_get:
            mock_get.return_value = None
            
            result = api_module.verify_keyword()
            
            self.assertEqual(mock_frappe.response.http_status_code, 404)


@unittest.skipUnless(API_MODULE_IMPORTED, "API module not available")
class TestCreateStudent(BaseAPITest):
    
    def test_success_new_student(self):
        mock_frappe.local.form_dict = {
            'api_key': 'valid_key',
            'student_name': 'John Doe',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'test_batch',
            'vertical': 'Math',
            'glific_id': 'new_glific_123'
        }
        
        with patch.object(mock_frappe, 'get_all') as mock_get_all:
            mock_get_all.side_effect = [
                [{'name': 'BO_001', 'school': 'SCHOOL_001', 
                  'batch': 'BATCH_001', 'kit_less': 1}],
                [{'name': 'VERT_001'}],
                []
            ]
            
            with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
                mock_batch = MockFrappeDocument('Batch',
                    name='BATCH_001',
                    active=True,
                    regist_end_date=(datetime.now() + timedelta(days=30)).date())
                mock_get_doc.return_value = mock_batch
                
                with patch.object(api_module, 'get_course_level_with_mapping') as mock_course:
                    mock_course.return_value = 'COURSE_LEVEL_001'
                    
                    with patch.object(api_module, 'create_new_student') as mock_create:
                        mock_student = MockFrappeDocument('Student', 
                            name='STUDENT_NEW_001',
                            name1='John Doe',
                            phone='9876543210')
                        mock_student.enrollment = []
                        mock_student.save = Mock()
                        mock_create.return_value = mock_student
                        
                        result = api_module.create_student()
                        
                        self.assertEqual(result['status'], 'success')
                        self.assertEqual(result['crm_student_id'], 'STUDENT_NEW_001')
                        self.assertEqual(result['assigned_course_level'], 'COURSE_LEVEL_001')
                        
                        mock_create.assert_called_once()
                        self.assertEqual(len(mock_student.enrollment), 1)
                        mock_student.save.assert_called_once()
    
    def test_missing_required_fields(self):
        mock_frappe.local.form_dict = {
            'api_key': 'valid_key',
            'student_name': 'Test'
        }
        
        result = api_module.create_student()
        
        self.assertEqual(result['status'], 'error')
    
    def test_inactive_batch(self):
        mock_frappe.local.form_dict = {
            'api_key': 'valid_key',
            'student_name': 'Test',
            'phone': '9876543210',
            'gender': 'Male',
            'grade': '5',
            'language': 'English',
            'batch_skeyword': 'inactive_batch',
            'vertical': 'Math',
            'glific_id': 'test'
        }
        
        with patch.object(mock_frappe, 'get_all') as mock_get_all:
            mock_get_all.return_value = [
                {'name': 'BO_001', 'school': 'SCHOOL_001', 
                 'batch': 'BATCH_001', 'kit_less': 1}
            ]
            
            with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
                mock_batch = MockFrappeDocument('Batch', active=False)
                mock_get_doc.return_value = mock_batch
                
                result = api_module.create_student()
                
                self.assertEqual(result['status'], 'error')


@unittest.skipUnless(API_MODULE_IMPORTED, "API module not available")
class TestGetActiveBatch(BaseAPITest):
    
    def test_success_batch_found(self):
        with patch.object(mock_frappe, 'get_all') as mock_get_all:
            mock_get_all.return_value = [
                {'batch': 'BATCH_ACTIVE_001', 'name': 'BO_001'}
            ]
            
            with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
                mock_batch = MockFrappeDocument('Batch',
                    name='BATCH_ACTIVE_001',
                    batch_id='BATCH_2025_ACTIVE',
                    active=True,
                    regist_end_date=(datetime.now() + timedelta(days=10)).date())
                mock_get_doc.return_value = mock_batch
                
                result = api_module.get_active_batch_for_school('SCHOOL_001')
                
                self.assertIsNotNone(result)
                self.assertEqual(result['batch_name'], 'BATCH_ACTIVE_001')
                self.assertEqual(result['batch_id'], 'BATCH_2025_ACTIVE')
                mock_get_doc.assert_called_with('Batch', 'BATCH_ACTIVE_001')


@unittest.skipUnless(API_MODULE_IMPORTED, "API module not available")
class TestBatchKeywordList(BaseAPITest):
    
    def test_loop_processes_multiple_batches(self):
        with patch.object(mock_frappe, 'get_all') as mock_get_all:
            mock_get_all.return_value = [
                {'batch': 'BATCH_001', 'school': 'SCHOOL_001', 'batch_skeyword': 'batch1'},
                {'batch': 'BATCH_002', 'school': 'SCHOOL_002', 'batch_skeyword': 'batch2'},
                {'batch': 'BATCH_003', 'school': 'SCHOOL_003', 'batch_skeyword': 'batch3'}
            ]
            
            with patch.object(mock_frappe, 'get_doc') as mock_get_doc:
                def get_doc_side_effect(doctype, name):
                    batches = {
                        'BATCH_001': MockFrappeDocument('Batch', name='BATCH_001', batch_id='B1',
                            active=True, regist_end_date=(datetime.now() + timedelta(days=5)).date()),
                        'BATCH_002': MockFrappeDocument('Batch', name='BATCH_002', batch_id='B2',
                            active=True, regist_end_date=(datetime.now() + timedelta(days=10)).date()),
                        'BATCH_003': MockFrappeDocument('Batch', name='BATCH_003', batch_id='B3',
                            active=True, regist_end_date=(datetime.now() + timedelta(days=15)).date())
                    }
                    return batches.get(name, MockFrappeDocument(doctype))
                
                mock_get_doc.side_effect = get_doc_side_effect
                
                with patch.object(mock_frappe, 'get_value') as mock_get_val:
                    def get_value_side_effect(dt, name, field):
                        schools = {
                            'SCHOOL_001': 'School One',
                            'SCHOOL_002': 'School Two',
                            'SCHOOL_003': 'School Three'
                        }
                        return schools.get(name, 'Unknown')
                    
                    mock_get_val.side_effect = get_value_side_effect
                    
                    result = api_module.list_batch_keyword('valid_key')
                    
                    self.assertIsInstance(result, list)
                    self.assertEqual(len(result), 3)
                    
                    batch_ids = [item['batch_id'] for item in result]
                    self.assertIn('B1', batch_ids)
                    self.assertIn('B2', batch_ids)
                    self.assertIn('B3', batch_ids)


@unittest.skipUnless(API_MODULE_IMPORTED, "API module not available")
class TestOTPFlow(BaseAPITest):
    
    def test_send_otp_new_teacher(self):
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key',
            'phone': '9876543210'
        }
        
        with patch.object(mock_frappe, 'get_all') as mock_get_all:
            mock_get_all.return_value = []
            
            mock_response = Mock()
            mock_response.json.return_value = {"status": "success", "id": "msg_123"}
            mock_requests.get.return_value = mock_response
            
            with patch.object(mock_frappe, 'new_doc') as mock_new:
                mock_otp_doc = MockFrappeDocument('OTP Verification')
                mock_otp_doc.insert = Mock()
                mock_new.return_value = mock_otp_doc
                
                result = api_module.send_otp()
                
                self.assertEqual(result['status'], 'success')
                self.assertEqual(result['action_type'], 'new_teacher')
                self.assertEqual(mock_frappe.response.http_status_code, 200)
                mock_new.assert_called_with('OTP Verification')
                mock_otp_doc.insert.assert_called_once()
    
    def test_verify_otp_success(self):
        mock_frappe.request.get_json.return_value = {
            'api_key': 'valid_key',
            'phone': '9876543210',
            'otp': '1234'
        }
        
        with patch.object(mock_frappe.db, 'sql') as mock_sql:
            mock_sql.return_value = [{
                'name': 'OTP_001',
                'expiry': datetime.now() + timedelta(minutes=10),
                'context': json.dumps({"action_type": "new_teacher"}),
                'verified': False
            }]
            
            result = api_module.verify_otp()
            
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['action_type'], 'new_teacher')
            self.assertEqual(mock_frappe.response.http_status_code, 200)


# if __name__ == '__main__':
#     unittest.main(verbosity=2)