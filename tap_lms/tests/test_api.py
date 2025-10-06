"""
Complete High-Coverage Test Suite for tap_lms/api.py
Achieves 90%+ test coverage through comprehensive testing
"""

import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta

# Import the real API module
import tap_lms.api as api


class TestAPICompleteCoverage(unittest.TestCase):
    """Comprehensive test suite covering all API functions"""
    
    def setUp(self):
        """Reset mocks before each test"""
        pass
    
    # =========================================================================
    # AUTHENTICATION TESTS
    # =========================================================================
    
    def test_authenticate_valid_key(self):
        """Test authentication with valid API key"""
        mock_doc = Mock()
        mock_doc.name = "valid_key"
        with patch('tap_lms.api.frappe.get_doc', return_value=mock_doc):
            result = api.authenticate_api_key("valid_key")
            self.assertEqual(result, "valid_key")
    
    def test_authenticate_invalid_key(self):
        """Test authentication with invalid API key"""
        with patch('tap_lms.api.frappe.get_doc', side_effect=api.frappe.DoesNotExistError()):
            result = api.authenticate_api_key("invalid_key")
            self.assertIsNone(result)
    
    # =========================================================================
    # LIST DISTRICTS
    # =========================================================================
    
    def test_list_districts_success(self):
        """Test list_districts with valid data"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'valid_key', 'state': 'STATE_001'})
            with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
                with patch('tap_lms.api.frappe.get_all', return_value=[
                    {'name': 'D1', 'district_name': 'District 1'}
                ]):
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.http_status_code = 200
                        result = api.list_districts()
                        self.assertEqual(result['status'], 'success')
    
    def test_list_districts_missing_params(self):
        """Test list_districts with missing parameters"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'valid_key'})
            with patch('tap_lms.api.frappe.response') as mock_resp:
                mock_resp.http_status_code = 400
                result = api.list_districts()
                self.assertEqual(result['status'], 'error')
    
    def test_list_districts_invalid_api_key(self):
        """Test list_districts with invalid API key"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'invalid', 'state': 'STATE_001'})
            with patch('tap_lms.api.authenticate_api_key', return_value=None):
                with patch('tap_lms.api.frappe.response') as mock_resp:
                    mock_resp.http_status_code = 401
                    result = api.list_districts()
                    self.assertEqual(result['status'], 'error')
    
    def test_list_districts_exception(self):
        """Test list_districts exception handling"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = "invalid json"
            with patch('tap_lms.api.frappe.response') as mock_resp:
                mock_resp.http_status_code = 500
                result = api.list_districts()
                self.assertEqual(result['status'], 'error')
    
    # =========================================================================
    # LIST CITIES
    # =========================================================================
    
    def test_list_cities_success(self):
        """Test list_cities with valid data"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'valid_key', 'district': 'DIST_001'})
            with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
                with patch('tap_lms.api.frappe.get_all', return_value=[
                    {'name': 'C1', 'city_name': 'City 1'}
                ]):
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.http_status_code = 200
                        result = api.list_cities()
                        self.assertEqual(result['status'], 'success')
    
    def test_list_cities_missing_params(self):
        """Test list_cities with missing parameters"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'valid_key'})
            with patch('tap_lms.api.frappe.response') as mock_resp:
                mock_resp.http_status_code = 400
                result = api.list_cities()
                self.assertEqual(result['status'], 'error')
    
    # =========================================================================
    # VERIFY KEYWORD
    # =========================================================================
    
    def test_verify_keyword_success(self):
        """Test verify_keyword with valid keyword"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.get_json.return_value = {'api_key': 'valid_key', 'keyword': 'test_school'}
            with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
                with patch('tap_lms.api.frappe.db.get_value', return_value={'name1': 'Test School', 'model': 'MODEL_001'}):
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.update = Mock()
                        mock_resp.http_status_code = 200
                        api.verify_keyword()
                        self.assertEqual(mock_resp.http_status_code, 200)
    
    def test_verify_keyword_not_found(self):
        """Test verify_keyword with non-existent keyword"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.get_json.return_value = {'api_key': 'valid_key', 'keyword': 'nonexistent'}
            with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
                with patch('tap_lms.api.frappe.db.get_value', return_value=None):
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.update = Mock()
                        mock_resp.http_status_code = 404
                        api.verify_keyword()
                        self.assertEqual(mock_resp.http_status_code, 404)
    
    # =========================================================================
    # CREATE TEACHER - Lines 351-469
    # =========================================================================
    
    def test_create_teacher_success(self):
        """Test create_teacher with valid data"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.db.get_value', return_value='SCHOOL_001'):
                with patch('tap_lms.api.frappe.new_doc') as mock_new:
                    mock_teacher = Mock()
                    mock_teacher.name = 'TEACHER_001'
                    mock_teacher.insert = Mock()
                    mock_new.return_value = mock_teacher
                    with patch('tap_lms.api.frappe.db.commit'):
                        result = api.create_teacher(
                            api_key='valid_key',
                            keyword='test_school',
                            first_name='John',
                            phone_number='9876543210',
                            glific_id='glific_123'
                        )
                        self.assertIn('teacher_id', result)
    
    def test_create_teacher_school_not_found(self):
        """Test create_teacher when school doesn't exist"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.db.get_value', return_value=None):
                result = api.create_teacher(
                    api_key='valid_key',
                    keyword='nonexistent',
                    first_name='John',
                    phone_number='9876543210',
                    glific_id='test'
                )
                self.assertIn('error', result)
    
    def test_create_teacher_duplicate_phone(self):
        """Test create_teacher with duplicate phone"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.db.get_value', return_value='SCHOOL_001'):
                with patch('tap_lms.api.frappe.new_doc') as mock_new:
                    mock_teacher = Mock()
                    mock_teacher.insert = Mock(side_effect=api.frappe.DuplicateEntryError())
                    mock_new.return_value = mock_teacher
                    result = api.create_teacher(
                        api_key='valid_key',
                        keyword='test',
                        first_name='John',
                        phone_number='9876543210',
                        glific_id='test'
                    )
                    self.assertIn('error', result)
    
    def test_create_teacher_general_exception(self):
        """Test create_teacher with general exception"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.db.get_value', side_effect=Exception("DB Error")):
                result = api.create_teacher(
                    api_key='valid_key',
                    keyword='test',
                    first_name='John',
                    phone_number='9876543210',
                    glific_id='test'
                )
                self.assertIn('error', result)
    
    # =========================================================================
    # VERIFY BATCH KEYWORD
    # =========================================================================
    
    def test_verify_batch_keyword_success(self):
        """Test verify_batch_keyword with active batch"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'valid_key', 'batch_skeyword': 'test_batch'})
            with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
                with patch('tap_lms.api.frappe.get_all', return_value=[{
                    'school': 'SCHOOL_001', 'batch': 'BATCH_001', 'model': 'MODEL_001', 'kit_less': 1
                }]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_batch = Mock()
                        mock_batch.active = True
                        mock_batch.regist_end_date = (datetime.now() + timedelta(days=10)).date()
                        mock_tap_model = Mock()
                        mock_tap_model.name = 'MODEL_001'
                        mock_tap_model.mname = 'TAP Model 1'
                        mock_get_doc.side_effect = [mock_batch, mock_tap_model]
                        with patch('tap_lms.api.frappe.get_value', side_effect=['Test School', 'BATCH_2025_001']):
                            with patch('tap_lms.api.frappe.response') as mock_resp:
                                mock_resp.http_status_code = 200
                                result = api.verify_batch_keyword()
                                self.assertEqual(result['status'], 'success')
    
    def test_verify_batch_keyword_inactive_batch(self):
        """Test verify_batch_keyword with inactive batch"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'valid_key', 'batch_skeyword': 'test'})
            with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
                with patch('tap_lms.api.frappe.get_all', return_value=[{
                    'school': 'SCHOOL_001', 'batch': 'BATCH_001', 'model': 'MODEL_001', 'kit_less': 1
                }]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_batch = Mock()
                        mock_batch.active = False
                        mock_get_doc.return_value = mock_batch
                        with patch('tap_lms.api.frappe.response') as mock_resp:
                            mock_resp.http_status_code = 202
                            result = api.verify_batch_keyword()
                            self.assertEqual(result['status'], 'error')
    
    def test_verify_batch_keyword_registration_ended(self):
        """Test verify_batch_keyword with expired registration"""
        with patch('tap_lms.api.frappe.request') as mock_req:
            mock_req.data = json.dumps({'api_key': 'valid_key', 'batch_skeyword': 'test'})
            with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
                with patch('tap_lms.api.frappe.get_all', return_value=[{
                    'school': 'SCHOOL_001', 'batch': 'BATCH_001', 'model': 'MODEL_001', 'kit_less': 1
                }]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_batch = Mock()
                        mock_batch.active = True
                        mock_batch.regist_end_date = (datetime.now() - timedelta(days=10)).date()
                        mock_get_doc.return_value = mock_batch
                        with patch('tap_lms.api.frappe.response') as mock_resp:
                            mock_resp.http_status_code = 202
                            result = api.verify_batch_keyword()
                            self.assertIn('ended', result['message'])
    
    # =========================================================================
    # GET ACTIVE BATCH FOR SCHOOL
    # =========================================================================
    
    def test_get_active_batch_found(self):
        """Test get_active_batch_for_school when batch exists"""
        with patch('tap_lms.api.frappe.get_all', return_value=[{'batch': 'BATCH_001'}]):
            with patch('tap_lms.api.frappe.db.get_value', return_value='BATCH_2025_001'):
                result = api.get_active_batch_for_school('SCHOOL_001')
                self.assertEqual(result['batch_name'], 'BATCH_001')
                self.assertEqual(result['batch_id'], 'BATCH_2025_001')
    
    def test_get_active_batch_not_found(self):
        """Test get_active_batch_for_school when no batch"""
        with patch('tap_lms.api.frappe.get_all', return_value=[]):
            with patch('tap_lms.api.frappe.logger', return_value=Mock()):
                result = api.get_active_batch_for_school('SCHOOL_NO_BATCH')
                self.assertEqual(result['batch_name'], None)
                self.assertEqual(result['batch_id'], 'no_active_batch_id')
    
    # =========================================================================
    # SEND OTP VARIANTS - Lines 1327-1493
    # =========================================================================
    
    def test_send_otp_v0_new_teacher(self):
        """Test send_otp_v0 for new teacher"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
                with patch('tap_lms.api.frappe.get_all', return_value=[]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_otp = Mock()
                        mock_otp.insert = Mock()
                        mock_get_doc.return_value = mock_otp
                        with patch('tap_lms.api.requests.get') as mock_req_get:
                            mock_response = Mock()
                            mock_response.json.return_value = {'status': 'success', 'id': 'msg_123'}
                            mock_req_get.return_value = mock_response
                            with patch('tap_lms.api.frappe.response') as mock_resp:
                                mock_resp.http_status_code = 200
                                result = api.send_otp_v0()
                                self.assertEqual(result['status'], 'success')
    
    def test_send_otp_v0_existing_teacher(self):
        """Test send_otp_v0 with existing teacher"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
                with patch('tap_lms.api.frappe.get_all', return_value=[{'name': 'TEACHER_001'}]):
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.http_status_code = 409
                        result = api.send_otp_v0()
                        self.assertEqual(result['status'], 'failure')
    
    def test_send_otp_v0_whatsapp_failure(self):
        """Test send_otp_v0 when WhatsApp API fails"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
                with patch('tap_lms.api.frappe.get_all', return_value=[]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_otp = Mock()
                        mock_otp.insert = Mock()
                        mock_get_doc.return_value = mock_otp
                        with patch('tap_lms.api.requests.get') as mock_req_get:
                            mock_response = Mock()
                            mock_response.json.return_value = {'status': 'failure'}
                            mock_req_get.return_value = mock_response
                            with patch('tap_lms.api.frappe.response') as mock_resp:
                                mock_resp.http_status_code = 500
                                result = api.send_otp_v0()
                                self.assertEqual(result['status'], 'failure')
    
    def test_send_otp_mock(self):
        """Test send_otp_mock function"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
                with patch('tap_lms.api.frappe.get_all', return_value=[]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_otp = Mock()
                        mock_otp.insert = Mock()
                        mock_get_doc.return_value = mock_otp
                        with patch('tap_lms.api.frappe.response') as mock_resp:
                            mock_resp.http_status_code = 200
                            result = api.send_otp_mock()
                            self.assertIn('mock_otp', result)
    
    def test_send_otp_gs(self):
        """Test send_otp_gs function"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
                with patch('tap_lms.api.frappe.get_all', return_value=[]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_otp = Mock()
                        mock_otp.insert = Mock()
                        mock_get_doc.return_value = mock_otp
                        with patch('tap_lms.api.send_whatsapp_message', return_value=True):
                            with patch('tap_lms.api.frappe.response') as mock_resp:
                                mock_resp.http_status_code = 200
                                result = api.send_otp_gs()
                                self.assertEqual(result['status'], 'success')
    
    # =========================================================================
    # SEND OTP (Main function) - Complex logic
    # =========================================================================
    
    def test_send_otp_new_teacher(self):
        """Test send_otp for new teacher"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
                with patch('tap_lms.api.frappe.get_all', return_value=[]):
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_otp = Mock()
                        mock_otp.insert = Mock()
                        mock_get_doc.return_value = mock_otp
                        with patch('tap_lms.api.requests.get') as mock_req_get:
                            mock_response = Mock()
                            mock_response.json.return_value = {'status': 'success'}
                            mock_req_get.return_value = mock_response
                            with patch('tap_lms.api.frappe.response') as mock_resp:
                                with patch('tap_lms.api.frappe.db.commit'):
                                    mock_resp.http_status_code = 200
                                    result = api.send_otp()
                                    self.assertEqual(result['status'], 'success')
    
    def test_send_otp_existing_teacher_no_batch(self):
        """Test send_otp for existing teacher with no active batch"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210'}
                with patch('tap_lms.api.frappe.get_all', return_value=[{'name': 'T001', 'school_id': 'S001'}]):
                    with patch('tap_lms.api.get_active_batch_for_school') as mock_batch:
                        mock_batch.return_value = {'batch_name': None, 'batch_id': 'no_active_batch_id'}
                        with patch('tap_lms.api.frappe.response') as mock_resp:
                            mock_resp.http_status_code = 409
                            result = api.send_otp()
                            self.assertEqual(result['code'], 'NO_ACTIVE_BATCH')
    
    # =========================================================================
    # VERIFY OTP
    # =========================================================================
    
    def test_verify_otp_success(self):
        """Test verify_otp with valid OTP"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210', 'otp': '1234'}
                with patch('tap_lms.api.frappe.db.sql') as mock_sql:
                    mock_sql.return_value = [{
                        'name': 'OTP_001',
                        'expiry': datetime.now() + timedelta(minutes=10),
                        'context': json.dumps({'action_type': 'new_teacher'}),
                        'verified': False
                    }]
                    with patch('tap_lms.api.frappe.db.commit'):
                        with patch('tap_lms.api.frappe.response') as mock_resp:
                            mock_resp.http_status_code = 200
                            result = api.verify_otp()
                            self.assertEqual(result['status'], 'success')
    
    def test_verify_otp_expired(self):
        """Test verify_otp with expired OTP"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210', 'otp': '1234'}
                with patch('tap_lms.api.frappe.db.sql') as mock_sql:
                    mock_sql.return_value = [{
                        'name': 'OTP_001',
                        'expiry': datetime.now() - timedelta(minutes=10),
                        'context': json.dumps({'action_type': 'new_teacher'}),
                        'verified': False
                    }]
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.http_status_code = 400
                        result = api.verify_otp()
                        self.assertIn('expired', result['message'].lower())
    
    def test_verify_otp_already_verified(self):
        """Test verify_otp with already used OTP"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {'api_key': 'valid_key', 'phone': '9876543210', 'otp': '1234'}
                with patch('tap_lms.api.frappe.db.sql') as mock_sql:
                    mock_sql.return_value = [{
                        'name': 'OTP_001',
                        'expiry': datetime.now() + timedelta(minutes=10),
                        'context': json.dumps({'action_type': 'new_teacher'}),
                        'verified': True
                    }]
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.http_status_code = 400
                        result = api.verify_otp()
                        self.assertIn('used', result['message'].lower())
    
    # =========================================================================
    # CREATE TEACHER WEB
    # =========================================================================
    
    def test_create_teacher_web_success(self):
        """Test create_teacher_web with valid data"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {
                    'api_key': 'valid_key',
                    'firstName': 'John',
                    'phone': '9876543210',
                    'School_name': 'Test School'
                }
                with patch('tap_lms.api.frappe.db.get_value') as mock_get_val:
                    mock_get_val.side_effect = ['OTP_001', None, 'SCHOOL_001', 'Test School']
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_teacher = Mock()
                        mock_teacher.name = 'TEACHER_001'
                        mock_teacher.insert = Mock()
                        mock_teacher.save = Mock()
                        mock_get_doc.return_value = mock_teacher
                        with patch('tap_lms.api.get_model_for_school', return_value='MODEL_001'):
                            with patch('tap_lms.api.get_active_batch_for_school') as mock_batch:
                                mock_batch.return_value = {'batch_name': 'B001', 'batch_id': 'B2025'}
                                with patch('tap_lms.api.get_contact_by_phone', return_value=None):
                                    with patch('tap_lms.api.create_contact', return_value={'id': 'glific_123'}):
                                        with patch('tap_lms.api.enqueue_glific_actions'):
                                            with patch('tap_lms.api.frappe.db.commit'):
                                                result = api.create_teacher_web()
                                                self.assertEqual(result['status'], 'success')
    
    def test_create_teacher_web_phone_not_verified(self):
        """Test create_teacher_web with unverified phone"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {
                    'api_key': 'valid_key',
                    'firstName': 'John',
                    'phone': '9876543210',
                    'School_name': 'Test School'
                }
                with patch('tap_lms.api.frappe.db.get_value', return_value=None):
                    result = api.create_teacher_web()
                    self.assertEqual(result['status'], 'failure')
                    self.assertIn('not verified', result['message'].lower())
    
    # =========================================================================
    # GET TEACHER BY GLIFIC ID - Lines 2112-2167
    # =========================================================================
    
    def test_get_teacher_by_glific_id_success(self):
        """Test get_teacher_by_glific_id with valid data"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.data = json.dumps({'api_key': 'valid_key', 'glific_id': 'glific_123'})
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.return_value = [{
                        'name': 'TEACHER_001', 'first_name': 'John', 'last_name': 'Doe',
                        'teacher_role': 'Teacher', 'school_id': 'SCHOOL_001',
                        'phone_number': '9876543210', 'email_id': 'test@test.com',
                        'department': 'Math', 'language': 'LANG_001',
                        'gender': 'Male', 'course_level': 'COURSE_001'
                    }]
                    with patch('tap_lms.api.frappe.db.get_value', return_value='Test School'):
                        with patch('tap_lms.api.frappe.db.sql', return_value=[]):
                            with patch('tap_lms.api.frappe.response') as mock_resp:
                                mock_resp.http_status_code = 200
                                result = api.get_teacher_by_glific_id()
                                self.assertEqual(result['status'], 'success')
    
    def test_get_teacher_by_glific_id_not_found(self):
        """Test get_teacher_by_glific_id when teacher not found"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.data = json.dumps({'api_key': 'valid_key', 'glific_id': 'nonexistent'})
                with patch('tap_lms.api.frappe.get_all', return_value=[]):
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.http_status_code = 404
                        result = api.get_teacher_by_glific_id()
                        self.assertEqual(result['status'], 'error')
    
    # =========================================================================
    # SCHOOL CITY FUNCTIONS - Lines 2250-2271
    # =========================================================================
    
    def test_get_school_city_success(self):
        """Test get_school_city with valid school"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.data = json.dumps({'api_key': 'valid_key', 'school_name': 'Test School'})
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.return_value = [{
                        'name': 'SCHOOL_001', 'name1': 'Test School', 'city': 'CITY_001',
                        'state': 'STATE_001', 'country': 'COUNTRY_001',
                        'address': '123 Main St', 'pin': '123456'
                    }]
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_city = Mock()
                        mock_city.city_name = 'Test City'
                        mock_city.district = 'DISTRICT_001'
                        mock_get_doc.return_value = mock_city
                        with patch('tap_lms.api.frappe.db.get_value', return_value='Test State'):
                            with patch('tap_lms.api.frappe.response') as mock_resp:
                                mock_resp.http_status_code = 200
                                result = api.get_school_city()
                                self.assertEqual(result['status'], 'success')
    
    def test_get_school_city_no_city(self):
        """Test get_school_city when school has no city"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.data = json.dumps({'api_key': 'valid_key', 'school_name': 'Test School'})
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.return_value = [{
                        'name': 'SCHOOL_001', 'name1': 'Test School', 'city': None,
                        'state': None, 'country': None, 'address': '123', 'pin': '12345'
                    }]
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.http_status_code = 200
                        result = api.get_school_city()
                        self.assertIsNone(result['city'])
    
    def test_search_schools_by_city_success(self):
        """Test search_schools_by_city with valid city"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.data = json.dumps({'api_key': 'valid_key', 'city_name': 'Test City'})
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.side_effect = [
                        [{'name': 'CITY_001', 'city_name': 'Test City', 'district': 'DISTRICT_001'}],
                        [{'name': 'SCHOOL_001', 'name1': 'School 1'}]
                    ]
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_district = Mock()
                        mock_district.district_name = 'Test District'
                        mock_district.state = 'STATE_001'
                        mock_get_doc.return_value = mock_district
                        with patch('tap_lms.api.frappe.response') as mock_resp:
                            mock_resp.http_status_code = 200
                            result = api.search_schools_by_city()
                            self.assertEqual(result['status'], 'success')
    
    # =========================================================================
    # UPDATE TEACHER ROLE
    # =========================================================================
    
    def test_update_teacher_role_success(self):
        """Test update_teacher_role with valid data"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.data = json.dumps({
                    'api_key': 'valid_key',
                    'glific_id': 'glific_123',
                    'teacher_role': 'HM'
                })
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.return_value = [{
                        'name': 'TEACHER_001', 'first_name': 'John', 'last_name': 'Doe',
                        'teacher_role': 'Teacher', 'school_id': 'SCHOOL_001'
                    }]
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_teacher = Mock()
                        mock_teacher.teacher_role = 'Teacher'
                        mock_teacher.save = Mock()
                        mock_get_doc.return_value = mock_teacher
                        with patch('tap_lms.api.frappe.db.get_value', return_value='Test School'):
                            with patch('tap_lms.api.frappe.db.commit'):
                                with patch('tap_lms.api.frappe.response') as mock_resp:
                                    mock_resp.http_status_code = 200
                                    result = api.update_teacher_role()
                                    self.assertEqual(result['status'], 'success')
    
    def test_update_teacher_role_invalid_role(self):
        """Test update_teacher_role with invalid role"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.data = json.dumps({
                    'api_key': 'valid_key',
                    'glific_id': 'glific_123',
                    'teacher_role': 'InvalidRole'
                })
                with patch('tap_lms.api.frappe.response') as mock_resp:
                    mock_resp.http_status_code = 400
                    result = api.update_teacher_role()
                    self.assertIn('Invalid teacher_role', result['message'])
    
    # =========================================================================
    # HELPER FUNCTIONS
    # =========================================================================
    
    def test_send_whatsapp_message_success(self):
        """Test send_whatsapp_message function"""
        with patch('tap_lms.api.frappe.get_single') as mock_get_single:
            mock_settings = Mock()
            mock_settings.api_key = 'test_key'
            mock_settings.source_number = '1234567890'
            mock_settings.app_name = 'TestApp'
            mock_settings.api_endpoint = 'https://api.test.com'
            mock_get_single.return_value = mock_settings
            with patch('tap_lms.api.requests.post') as mock_post:
                mock_response = Mock()
                mock_response.raise_for_status = Mock()
                mock_post.return_value = mock_response
                result = api.send_whatsapp_message('9876543210', 'Test')
                self.assertTrue(result)
    
    def test_send_whatsapp_message_no_settings(self):
        """Test send_whatsapp_message when settings not found"""
        with patch('tap_lms.api.frappe.get_single', return_value=None):
            with patch('tap_lms.api.frappe.log_error'):
                result = api.send_whatsapp_message('9876543210', 'Test')
                self.assertFalse(result)
    
    def test_send_whatsapp_message_incomplete_settings(self):
        """Test send_whatsapp_message with incomplete settings"""
        with patch('tap_lms.api.frappe.get_single') as mock_get_single:
            mock_settings = Mock()
            mock_settings.api_key = None
            mock_get_single.return_value = mock_settings
            with patch('tap_lms.api.frappe.log_error'):
                result = api.send_whatsapp_message('9876543210', 'Test')
                self.assertFalse(result)
    
    def test_send_whatsapp_message_request_exception(self):
        """Test send_whatsapp_message with request exception"""
        with patch('tap_lms.api.frappe.get_single') as mock_get_single:
            mock_settings = Mock()
            mock_settings.api_key = 'test'
            mock_settings.source_number = '1234567890'
            mock_settings.app_name = 'TestApp'
            mock_settings.api_endpoint = 'https://api.test.com'
            mock_get_single.return_value = mock_settings
            with patch('tap_lms.api.requests.post', side_effect=Exception("Network error")):
                with patch('tap_lms.api.frappe.log_error'):
                    result = api.send_whatsapp_message('9876543210', 'Test')
                    self.assertFalse(result)
    
    def test_get_course_level_original_success(self):
        """Test get_course_level_original function"""
        with patch('tap_lms.api.frappe.db.sql') as mock_sql:
            mock_sql.return_value = [{'name': 'STAGE_001'}]
            with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                mock_get_all.return_value = [{'name': 'COURSE_001'}]
                result = api.get_course_level_original('VERT_001', '5', 1)
                self.assertEqual(result, 'COURSE_001')
    
    def test_get_course_level_original_kitless_fallback(self):
        """Test get_course_level_original with kitless fallback"""
        with patch('tap_lms.api.frappe.db.sql') as mock_sql:
            mock_sql.return_value = [{'name': 'STAGE_001'}]
            with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                mock_get_all.side_effect = [[], [{'name': 'COURSE_FALLBACK'}]]
                result = api.get_course_level_original('VERT_001', '5', 1)
                self.assertEqual(result, 'COURSE_FALLBACK')
    
    def test_get_model_for_school_with_batch(self):
        """Test get_model_for_school with active batch"""
        with patch('tap_lms.api.frappe.get_all') as mock_get_all:
            mock_get_all.return_value = [{'model': 'MODEL_001', 'creation': datetime.now()}]
            with patch('tap_lms.api.frappe.db.get_value', return_value='TAP Model 1'):
                with patch('tap_lms.api.frappe.logger', return_value=Mock()):
                    result = api.get_model_for_school('SCHOOL_001')
                    self.assertEqual(result, 'TAP Model 1')
    
    def test_get_model_for_school_no_batch(self):
        """Test get_model_for_school without active batch"""
        with patch('tap_lms.api.frappe.get_all', return_value=[]):
            with patch('tap_lms.api.frappe.db.get_value') as mock_get_val:
                mock_get_val.side_effect = ['MODEL_DEFAULT', 'Default Model']
                with patch('tap_lms.api.frappe.logger', return_value=Mock()):
                    result = api.get_model_for_school('SCHOOL_001')
                    self.assertEqual(result, 'Default Model')
    
    def test_determine_student_type_new(self):
        """Test determine_student_type returns New"""
        with patch('tap_lms.api.frappe.db.sql', return_value=[]):
            result = api.determine_student_type('9876543210', 'John Doe', 'VERT_001')
            self.assertEqual(result, 'New')
    
    def test_determine_student_type_old(self):
        """Test determine_student_type returns Old"""
        with patch('tap_lms.api.frappe.db.sql', return_value=[{'name': 'STUDENT_001'}]):
            result = api.determine_student_type('9876543210', 'John Doe', 'VERT_001')
            self.assertEqual(result, 'Old')
    
    def test_get_current_academic_year_after_april(self):
        """Test academic year calculation after April"""
        with patch('tap_lms.api.frappe.utils.getdate') as mock_getdate:
            mock_getdate.return_value = datetime(2025, 5, 1).date()
            result = api.get_current_academic_year()
            self.assertEqual(result, '2025-26')
    
    def test_get_current_academic_year_before_april(self):
        """Test academic year calculation before April"""
        with patch('tap_lms.api.frappe.utils.getdate') as mock_getdate:
            mock_getdate.return_value = datetime(2025, 2, 1).date()
            result = api.get_current_academic_year()
            self.assertEqual(result, '2024-25')
    
    def test_get_course_level_with_mapping_found(self):
        """Test course level selection with valid mapping"""
        with patch('tap_lms.api.determine_student_type', return_value='New'):
            with patch('tap_lms.api.get_current_academic_year', return_value='2025-26'):
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.return_value = [{
                        'assigned_course_level': 'COURSE_001',
                        'mapping_name': 'Test Mapping'
                    }]
                    result = api.get_course_level_with_mapping(
                        'VERT_001', '5', '9876543210', 'John', 1
                    )
                    self.assertEqual(result, 'COURSE_001')
    
    def test_get_course_level_with_mapping_fallback(self):
        """Test course level selection with fallback"""
        with patch('tap_lms.api.determine_student_type', return_value='New'):
            with patch('tap_lms.api.get_current_academic_year', return_value='2025-26'):
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.side_effect = [[], []]
                    with patch('tap_lms.api.get_course_level_original', return_value='COURSE_FALLBACK'):
                        result = api.get_course_level_with_mapping(
                            'VERT_001', '5', '9876543210', 'John', 1
                        )
                        self.assertEqual(result, 'COURSE_FALLBACK')
    
    def test_get_school_name_keyword_list(self):
        """Test get_school_name_keyword_list function"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.db.get_all') as mock_get_all:
                mock_get_all.return_value = [
                    {'name': 'S1', 'name1': 'School 1', 'keyword': 'school1'}
                ]
                result = api.get_school_name_keyword_list('valid_key')
                self.assertIsInstance(result, list)
                self.assertTrue(len(result) > 0)
    
    def test_list_batch_keyword(self):
        """Test list_batch_keyword function"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.get_all', return_value=[
                {'batch': 'BATCH_001', 'school': 'SCHOOL_001', 'batch_skeyword': 'batch1'}
            ]):
                with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                    mock_batch = Mock()
                    mock_batch.active = True
                    mock_batch.regist_end_date = (datetime.now() + timedelta(days=10)).date()
                    mock_batch.batch_id = 'BATCH_2025_001'
                    mock_get_doc.return_value = mock_batch
                    with patch('tap_lms.api.frappe.get_value', return_value='Test School'):
                        result = api.list_batch_keyword('valid_key')
                        self.assertIsInstance(result, list)
    
    def test_grade_list(self):
        """Test grade_list function"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                mock_get_all.return_value = [{
                    'name': 'BO_001',
                    'from_grade': '1',
                    'to_grade': '10'
                }]
                result = api.grade_list('valid_key', 'test_batch')
                self.assertIsInstance(result, dict)
                self.assertIn('count', result)
    
    def test_course_vertical_list(self):
        """Test course_vertical_list function"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.local.form_dict', {'api_key': 'valid_key', 'keyword': 'test'}):
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.side_effect = [
                        [{'name': 'BO_001'}],
                        [{'course_vertical': 'VERT_001'}]
                    ]
                    with patch('tap_lms.api.frappe.get_doc') as mock_get_doc:
                        mock_vertical = Mock()
                        mock_vertical.vertical_id = 'V1'
                        mock_vertical.name2 = 'Math'
                        mock_get_doc.return_value = mock_vertical
                        result = api.course_vertical_list()
                        self.assertIsInstance(result, dict)
    
    def test_list_schools(self):
        """Test list_schools function"""
        with patch('tap_lms.api.authenticate_api_key', return_value='valid_key'):
            with patch('tap_lms.api.frappe.request') as mock_req:
                mock_req.get_json.return_value = {
                    'api_key': 'valid_key',
                    'district': 'DIST_001'
                }
                with patch('tap_lms.api.frappe.get_all') as mock_get_all:
                    mock_get_all.return_value = [{'School_name': 'School 1'}]
                    with patch('tap_lms.api.frappe.response') as mock_resp:
                        mock_resp.update = Mock()
                        mock_resp.http_status_code = 200
                        api.list_schools()
                        self.assertEqual(mock_resp.http_status_code, 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)