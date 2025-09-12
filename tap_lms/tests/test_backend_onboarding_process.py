# """
# Test Suite for Backend Onboarding Process
# Tests for backend student onboarding functionality
# """

# import sys
# import os
# import unittest
# from unittest.mock import Mock, patch, MagicMock
# import json
# from datetime import datetime, date

# # Add the parent directory to Python path
# sys.path.insert(0, os.path.join(os.path.dirname(_file_), '..'))

# # =============================================================================
# # COMPREHENSIVE MOCKING SETUP
# # =============================================================================

# # Create mock modules that will be needed
# mock_frappe = Mock()
# mock_frappe.session = Mock()
# mock_frappe.session.user = 'test_user'
# mock_frappe.local = Mock()
# mock_frappe.local.response = Mock()
# mock_frappe.local.response.http_status_code = 200

# # Mock frappe.utils
# mock_frappe_utils = Mock()
# mock_frappe_utils.nowdate = Mock(return_value=date(2025, 8, 20))
# mock_frappe_utils.nowtime = Mock(return_value="10:30:00")
# mock_frappe_utils.now = Mock(return_value=datetime.now())
# mock_frappe_utils.getdate = Mock(return_value=date(2025, 8, 20))

# mock_frappe.utils = mock_frappe_utils
# mock_frappe.log_error = Mock()
# mock_frappe.get_all = Mock()
# mock_frappe.get_doc = Mock()
# mock_frappe.new_doc = Mock()
# mock_frappe.enqueue = Mock()
# mock_frappe.publish_progress = Mock()
# mock_frappe.db = Mock()
# mock_frappe.db.sql = Mock()
# mock_frappe.db.exists = Mock()
# mock_frappe.db.get_value = Mock()
# mock_frappe.db.table_exists = Mock()
# mock_frappe.whitelist = lambda allow_guest=False: lambda func: func
# mock_frappe._ = lambda x: x

# # Mock other required modules
# mock_glific = Mock()
# mock_glific.create_or_get_glific_group_for_batch = Mock()
# mock_glific.add_student_to_glific_for_onboarding = Mock()
# mock_glific.get_contact_by_phone = Mock()

# mock_api = Mock()
# mock_api.get_course_level = Mock(return_value="TEST_COURSE_LEVEL")

# # Mock json module
# mock_json = Mock()
# mock_json.loads = json.loads

# # Patch all the modules in sys.modules before any imports
# sys.modules['frappe'] = mock_frappe
# sys.modules['frappe.utils'] = mock_frappe_utils
# sys.modules['tap_lms.glific_integration'] = mock_glific
# sys.modules['tap_lms.api'] = mock_api
# sys.modules['json'] = mock_json

# # Now we can import the actual functions
# try:
#     from tap_lms.page.backend_onboarding_process.backend_onboarding_process import (
#         normalize_phone_number,
#         find_existing_student_by_phone_and_name,
#         get_onboarding_batches,
#         get_batch_details,
#         validate_student,
#         get_onboarding_stages,
#         get_initial_stage,
#         get_current_academic_year_backend,
#         get_job_status
#     )
#     IMPORTS_SUCCESSFUL = True
#     print("✓ Successfully imported backend onboarding functions")
# except ImportError as e:
#     print(f"✗ Import failed: {e}")
#     IMPORTS_SUCCESSFUL = False
    
#     # Create fallback implementations for testing
#     def normalize_phone_number(phone):
#         if not phone:
#             return None, None
#         phone = ''.join(filter(str.isdigit, str(phone).replace(' ', '').replace('-', '').replace('(', '').replace(')', '')))
#         if len(phone) == 10:
#             return f"91{phone}", phone
#         elif len(phone) == 12 and phone.startswith('91'):
#             return phone, phone[2:]
#         elif len(phone) == 11 and phone.startswith('1'):
#             return f"9{phone}", phone[1:]
#         else:
#             return None, None
    
#     def validate_student(student):
#         validation = {}
#         required_fields = ["student_name", "phone", "school", "grade", "language", "batch"]
#         for field in required_fields:
#             if not student.get(field):
#                 validation[field] = "missing"
#         return validation
    
#     def get_current_academic_year_backend():
#         current_date = date(2025, 8, 20)
#         if current_date.month >= 4:
#             return f"{current_date.year}-{str(current_date.year + 1)[-2:]}"
#         else:
#             return f"{current_date.year - 1}-{str(current_date.year)[-2:]}"
    
#     def find_existing_student_by_phone_and_name(phone, name):
#         return None
    
#     def get_onboarding_batches():
#         return []
    
#     def get_batch_details(batch_id):
#         return {"batch": None, "students": [], "glific_group": None}
    
#     def get_onboarding_stages():
#         return []
    
#     def get_initial_stage():
#         return None
    
#     def get_job_status(job_id):
#         return {"status": "Unknown"}

# # =============================================================================
# # TEST CLASSES
# # =============================================================================

# class TestPhoneNumberNormalization(unittest.TestCase):
#     """Test phone number normalization functionality"""
    
#     def test_normalize_10_digit_phone(self):
#         """Test normalizing 10-digit phone number"""
#         phone_12, phone_10 = normalize_phone_number("9876543210")
#         self.assertEqual(phone_12, "919876543210")
#         self.assertEqual(phone_10, "9876543210")
    
#     def test_normalize_12_digit_phone(self):
#         """Test normalizing 12-digit phone number"""
#         phone_12, phone_10 = normalize_phone_number("919876543210")
#         self.assertEqual(phone_12, "919876543210")
#         self.assertEqual(phone_10, "9876543210")
    
#     def test_normalize_11_digit_phone_with_1_prefix(self):
#         """Test normalizing 11-digit phone number starting with 1"""
#         phone_12, phone_10 = normalize_phone_number("19876543210")
#         self.assertEqual(phone_12, "919876543210")
#         self.assertEqual(phone_10, "9876543210")
    
#     def test_normalize_phone_with_formatting(self):
#         """Test normalizing phone number with formatting characters"""
#         phone_12, phone_10 = normalize_phone_number("(987) 654-3210")
#         self.assertEqual(phone_12, "919876543210")
#         self.assertEqual(phone_10, "9876543210")
    
#     def test_normalize_invalid_phone(self):
#         """Test normalizing invalid phone numbers"""
#         # Test with invalid length
#         phone_12, phone_10 = normalize_phone_number("12345")
#         self.assertIsNone(phone_12)
#         self.assertIsNone(phone_10)
        
#         # Test with None
#         phone_12, phone_10 = normalize_phone_number(None)
#         self.assertIsNone(phone_12)
#         self.assertIsNone(phone_10)
        
#         # Test with empty string
#         phone_12, phone_10 = normalize_phone_number("")
#         self.assertIsNone(phone_12)
#         self.assertIsNone(phone_10)
    
#     def test_normalize_phone_edge_cases(self):
#         """Test edge cases for phone normalization"""
#         test_cases = [
#             ("987-654-3210", "919876543210", "9876543210"),
#             ("987 654 3210", "919876543210", "9876543210"),
#             ("91 9876543210", "919876543210", "9876543210"),
#             ("91-9876543210", "919876543210", "9876543210"),
#         ]
        
#         for input_phone, expected_12, expected_10 in test_cases:
#             with self.subTest(phone=input_phone):
#                 phone_12, phone_10 = normalize_phone_number(input_phone)
#                 self.assertEqual(phone_12, expected_12)
#                 self.assertEqual(phone_10, expected_10)

# class TestStudentValidation(unittest.TestCase):
#     """Test student validation functionality"""
    
#     def setUp(self):
#         """Set up test data"""
#         self.complete_student = {
#             'student_name': 'Test Student',
#             'phone': '919876543210',
#             'school': 'Test School',
#             'grade': '5',
#             'language': 'English',
#             'batch': 'Test Batch'
#         }
    
#     def test_validate_complete_student(self):
#         """Test validation of complete student record"""
#         validation = validate_student(self.complete_student)
#         self.assertEqual(validation, {})
    
#     def test_validate_student_missing_fields(self):
#         """Test validation with missing required fields"""
#         incomplete_student = self.complete_student.copy()
#         incomplete_student['student_name'] = ''
#         incomplete_student['school'] = ''
#         incomplete_student['phone'] = ''
        
#         validation = validate_student(incomplete_student)
        
#         self.assertIn('student_name', validation)
#         self.assertEqual(validation['student_name'], 'missing')
#         self.assertIn('school', validation)
#         self.assertEqual(validation['school'], 'missing')
#         self.assertIn('phone', validation)
#         self.assertEqual(validation['phone'], 'missing')
    
#     def test_validate_all_missing_fields(self):
#         """Test validation when all required fields are missing"""
#         empty_student = {
#             'student_name': '',
#             'phone': '',
#             'school': '',
#             'grade': '',
#             'language': '',
#             'batch': ''
#         }
        
#         validation = validate_student(empty_student)
        
#         required_fields = ['student_name', 'phone', 'school', 'grade', 'language', 'batch']
#         for field in required_fields:
#             self.assertIn(field, validation)
#             self.assertEqual(validation[field], 'missing')

# class TestAcademicYear(unittest.TestCase):
#     """Test academic year calculation"""
    
#     def test_current_academic_year_after_april(self):
#         """Test academic year calculation when current date is after April"""
#         result = get_current_academic_year_backend()
#         self.assertEqual(result, "2025-26")
    
#     def test_current_academic_year_logic(self):
#         """Test the academic year calculation logic"""
#         # This test works with our fallback implementation
#         result = get_current_academic_year_backend()
#         # Should return current academic year based on August date
#         self.assertIsInstance(result, str)
#         self.assertIn("-", result)

# class TestBasicFunctionality(unittest.TestCase):
#     """Test basic functionality to ensure imports work"""
    
#     def test_find_existing_student_basic(self):
#         """Test basic find student functionality"""
#         result = find_existing_student_by_phone_and_name("919876543210", "Test Student")
#         # Should return None in test environment
#         self.assertIsNone(result)
    
#     def test_get_onboarding_batches_basic(self):
#         """Test basic get onboarding batches functionality"""
#         result = get_onboarding_batches()
#         self.assertIsInstance(result, list)
    
#     def test_get_batch_details_basic(self):
#         """Test basic get batch details functionality"""
#         result = get_batch_details("BATCH001")
#         self.assertIsInstance(result, dict)
#         self.assertIn('batch', result)
#         self.assertIn('students', result)
#         self.assertIn('glific_group', result)
    
#     def test_get_onboarding_stages_basic(self):
#         """Test basic get onboarding stages functionality"""
#         result = get_onboarding_stages()
#         self.assertIsInstance(result, list)
    
#     def test_get_initial_stage_basic(self):
#         """Test basic get initial stage functionality"""
#         result = get_initial_stage()
#         # Should return None or a string
#         self.assertTrue(result is None or isinstance(result, str))
    
#     def test_get_job_status_basic(self):
#         """Test basic get job status functionality"""
#         result = get_job_status("job123")
#         self.assertIsInstance(result, dict)
#         self.assertIn('status', result)

# class TestFrappeMocking(unittest.TestCase):
#     """Test that frappe mocking is working correctly"""
    
#     def test_frappe_session_user(self):
#         """Test that frappe session user is mocked correctly"""
#         self.assertEqual(mock_frappe.session.user, 'test_user')
    
#     def test_frappe_utils_date(self):
#         """Test that frappe utils date functions are mocked"""
#         result = mock_frappe.utils.nowdate()
#         self.assertEqual(result, date(2025, 8, 20))
    
#     def test_frappe_functions_callable(self):
#         """Test that frappe functions can be called without error"""
#         # These should not raise exceptions
#         mock_frappe.get_all("Test")
#         mock_frappe.log_error("Test message")
#         mock_frappe.db.sql("SELECT * FROM test")
        
#         # Assert that the mocks were called
#         self.assertTrue(mock_frappe.get_all.called)
#         self.assertTrue(mock_frappe.log_error.called)
#         self.assertTrue(mock_frappe.db.sql.called)

# class TestImportStatus(unittest.TestCase):
#     """Test the import status and provide helpful information"""
    
#     def test_import_status_info(self):
#         """Display information about import status"""
#         if IMPORTS_SUCCESSFUL:
#             print("✓ All imports successful - testing actual implementation")
#         else:
#             print("ℹ Using fallback implementations - some functionality may be limited")
        
#         # This test always passes but provides useful info
#         self.assertTrue(True)

# # =============================================================================
# # MAIN EXECUTION
# # =============================================================================

# # if _name_ == '_main_':
# #     # Print import status
# #     if IMPORTS_SUCCESSFUL:
# #         print("✓ Backend onboarding process functions imported successfully")
# #     else:
# #         print("ℹ Using fallback implementations for testing")
    
# #     # Run the tests
# #     unittest.main(verbosity=2)

import unittest
import frappe
from frappe.utils import nowdate
from unittest.mock import patch, MagicMock, call
import json

# Import the module functions
from tap_lms.backend_student_onboarding import (
    normalize_phone_number,
    find_existing_student_by_phone_and_name,
    validate_student,
    get_initial_stage,
    process_batch,
    process_glific_contact,
    determine_student_type_backend,
    get_current_academic_year_backend,
    validate_enrollment_data,
    process_student_record,
    update_backend_student_status,
    format_phone_number,
    get_course_level_with_validation_backend
)

class TestPhoneNumberNormalization(unittest.TestCase):
    """Test phone number normalization functionality"""
    
    def test_10_digit_phone(self):
        """Test normalization of 10-digit phone number"""
        phone_12, phone_10 = normalize_phone_number("9876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_12_digit_phone(self):
        """Test normalization of 12-digit phone number with country code"""
        phone_12, phone_10 = normalize_phone_number("919876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_11_digit_phone_starting_with_1(self):
        """Test normalization of 11-digit phone starting with 1"""
        phone_12, phone_10 = normalize_phone_number("19876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_phone_with_special_characters(self):
        """Test normalization with special characters"""
        phone_12, phone_10 = normalize_phone_number("(98) 765-43210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_invalid_phone(self):
        """Test invalid phone number"""
        phone_12, phone_10 = normalize_phone_number("12345")
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)
    
    def test_empty_phone(self):
        """Test empty phone number"""
        phone_12, phone_10 = normalize_phone_number("")
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)


class TestFindExistingStudent(unittest.TestCase):
    """Test finding existing student by phone and name"""
    
    @patch('frappe.db.sql')
    def test_find_existing_student_found(self, mock_sql):
        """Test finding an existing student"""
        mock_sql.return_value = [
            {"name": "ST00001", "phone": "919876543210", "name1": "John Doe"}
        ]
        
        result = find_existing_student_by_phone_and_name("9876543210", "John Doe")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "ST00001")
        self.assertEqual(result["name1"], "John Doe")
    
    @patch('frappe.db.sql')
    def test_find_existing_student_not_found(self, mock_sql):
        """Test when student is not found"""
        mock_sql.return_value = []
        
        result = find_existing_student_by_phone_and_name("9876543210", "Jane Doe")
        
        self.assertIsNone(result)
    
    def test_find_student_invalid_phone(self):
        """Test finding student with invalid phone"""
        result = find_existing_student_by_phone_and_name("12345", "John Doe")
        self.assertIsNone(result)
    
    def test_find_student_empty_params(self):
        """Test finding student with empty parameters"""
        result = find_existing_student_by_phone_and_name("", "")
        self.assertIsNone(result)


class TestValidateStudent(unittest.TestCase):
    """Test student validation functionality"""
    
    @patch('tap_lms.backend_student_onboarding.find_existing_student_by_phone_and_name')
    def test_validate_complete_student(self, mock_find):
        """Test validation of student with all required fields"""
        mock_find.return_value = None
        
        student = {
            "student_name": "John Doe",
            "phone": "9876543210",
            "school": "SCH001",
            "grade": "5",
            "language": "English",
            "batch": "BT001"
        }
        
        validation = validate_student(student)
        
        self.assertEqual(validation, {})
    
    def test_validate_missing_fields(self):
        """Test validation with missing required fields"""
        student = {
            "student_name": "John Doe",
            "phone": "9876543210"
        }
        
        validation = validate_student(student)
        
        self.assertIn("school", validation)
        self.assertIn("grade", validation)
        self.assertIn("language", validation)
        self.assertIn("batch", validation)
        self.assertEqual(validation["school"], "missing")
    
    @patch('tap_lms.backend_student_onboarding.find_existing_student_by_phone_and_name')
    def test_validate_duplicate_student(self, mock_find):
        """Test validation detecting duplicate student"""
        mock_find.return_value = {
            "name": "ST00001",
            "name1": "John Doe"
        }
        
        student = {
            "student_name": "John Doe",
            "phone": "9876543210",
            "school": "SCH001",
            "grade": "5",
            "language": "English",
            "batch": "BT001"
        }
        
        validation = validate_student(student)
        
        self.assertIn("duplicate", validation)
        self.assertEqual(validation["duplicate"]["student_id"], "ST00001")


class TestDetermineStudentType(unittest.TestCase):
    """Test student type determination (New/Old)"""
    
    @patch('frappe.db.sql')
    def test_new_student_no_existing_record(self, mock_sql):
        """Test new student when no existing record found"""
        mock_sql.return_value = []
        
        result = determine_student_type_backend("9876543210", "John Doe", "Mathematics")
        
        self.assertEqual(result, "New")
    
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    def test_old_student_same_vertical(self, mock_exists, mock_sql):
        """Test old student with enrollment in same vertical"""
        # First call: find student
        # Second call: get enrollments
        # Third call: get course vertical
        mock_sql.side_effect = [
            [{"name": "ST00001", "phone": "919876543210", "name1": "John Doe"}],
            [{"name": "EN001", "course": "CL001", "batch": "BT001", "grade": "5", "school": "SCH001"}],
            [{"vertical_name": "Mathematics"}]
        ]
        mock_exists.return_value = True
        
        result = determine_student_type_backend("9876543210", "John Doe", "Mathematics")
        
        self.assertEqual(result, "Old")
    
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    def test_new_student_different_vertical(self, mock_exists, mock_sql):
        """Test new student with enrollment only in different vertical"""
        mock_sql.side_effect = [
            [{"name": "ST00001", "phone": "919876543210", "name1": "John Doe"}],
            [{"name": "EN001", "course": "CL001", "batch": "BT001", "grade": "5", "school": "SCH001"}],
            [{"vertical_name": "Science"}]
        ]
        mock_exists.return_value = True
        
        result = determine_student_type_backend("9876543210", "John Doe", "Mathematics")
        
        self.assertEqual(result, "New")
    
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    def test_old_student_broken_course_link(self, mock_exists, mock_sql):
        """Test old student with broken course link"""
        mock_sql.side_effect = [
            [{"name": "ST00001", "phone": "919876543210", "name1": "John Doe"}],
            [{"name": "EN001", "course": "CL999", "batch": "BT001", "grade": "5", "school": "SCH001"}]
        ]
        mock_exists.return_value = False  # Course doesn't exist
        
        result = determine_student_type_backend("9876543210", "John Doe", "Mathematics")
        
        self.assertEqual(result, "Old")


class TestGetCurrentAcademicYear(unittest.TestCase):
    """Test academic year calculation"""
    
    @patch('frappe.utils.getdate')
    def test_academic_year_after_april(self, mock_getdate):
        """Test academic year calculation for months after April"""
        from datetime import date
        mock_getdate.return_value = date(2025, 5, 15)  # May 2025
        
        result = get_current_academic_year_backend()
        
        self.assertEqual(result, "2025-26")
    
    @patch('frappe.utils.getdate')
    def test_academic_year_before_april(self, mock_getdate):
        """Test academic year calculation for months before April"""
        from datetime import date
        mock_getdate.return_value = date(2025, 2, 15)  # February 2025
        
        result = get_current_academic_year_backend()
        
        self.assertEqual(result, "2024-25")
    
    @patch('frappe.utils.getdate')
    def test_academic_year_in_april(self, mock_getdate):
        """Test academic year calculation for April"""
        from datetime import date
        mock_getdate.return_value = date(2025, 4, 1)  # April 1, 2025
        
        result = get_current_academic_year_backend()
        
        self.assertEqual(result, "2025-26")


class TestProcessGlificContact(unittest.TestCase):
    """Test Glific contact processing"""
    
    @patch('tap_lms.backend_student_onboarding.get_contact_by_phone')
    @patch('tap_lms.backend_student_onboarding.add_student_to_glific_for_onboarding')
    @patch('frappe.get_value')
    def test_create_new_glific_contact(self, mock_get_value, mock_add_student, mock_get_contact):
        """Test creating new Glific contact"""
        mock_get_contact.return_value = None  # No existing contact
        mock_add_student.return_value = {"id": "12345"}
        mock_get_value.side_effect = ["Test School", "BT001", "1", "Test Level", "Mathematics"]
        
        student = MagicMock()
        student.student_name = "John Doe"
        student.phone = "9876543210"
        student.school = "SCH001"
        student.batch = "BT001"
        student.language = "English"
        student.course_vertical = "CV001"
        student.grade = "5"
        
        glific_group = {"group_id": "GRP001"}
        
        result = process_glific_contact(student, glific_group, "CL001")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "12345")
        mock_add_student.assert_called_once()
    
    @patch('tap_lms.backend_student_onboarding.get_contact_by_phone')
    @patch('tap_lms.glific_integration.add_contact_to_group')
    @patch('tap_lms.glific_integration.update_contact_fields')
    @patch('frappe.get_value')
    def test_update_existing_glific_contact(self, mock_get_value, mock_update, mock_add_group, mock_get_contact):
        """Test updating existing Glific contact"""
        mock_get_contact.return_value = {"id": "12345"}
        mock_get_value.side_effect = ["Test School", "BT001", "Test Level", "Mathematics"]
        
        student = MagicMock()
        student.student_name = "John Doe"
        student.phone = "9876543210"
        student.school = "SCH001"
        student.batch = "BT001"
        student.language = "English"
        student.course_vertical = "CV001"
        student.grade = "5"
        
        glific_group = {"group_id": "GRP001"}
        
        result = process_glific_contact(student, glific_group, "CL001")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "12345")
        mock_add_group.assert_called_once_with("12345", "GRP001")
        mock_update.assert_called_once()


class TestProcessBatch(unittest.TestCase):
    """Test batch processing functionality"""
    
    @patch('frappe.get_doc')
    @patch('frappe.enqueue')
    def test_process_batch_with_background_job(self, mock_enqueue, mock_get_doc):
        """Test processing batch with background job"""
        mock_batch = MagicMock()
        mock_batch.status = "Draft"
        mock_get_doc.return_value = mock_batch
        
        mock_job = MagicMock()
        mock_job.id = "JOB123"
        mock_enqueue.return_value = mock_job
        
        result = process_batch("BSO001", use_background_job=True)
        
        self.assertEqual(result["job_id"], "JOB123")
        self.assertEqual(mock_batch.status, "Processing")
        mock_batch.save.assert_called_once()
        mock_enqueue.assert_called_once()
    
    @patch('frappe.get_doc')
    @patch('tap_lms.backend_student_onboarding.process_batch_job')
    def test_process_batch_immediate(self, mock_process_job, mock_get_doc):
        """Test immediate batch processing"""
        mock_batch = MagicMock()
        mock_batch.status = "Draft"
        mock_get_doc.return_value = mock_batch
        
        mock_process_job.return_value = {
            "success_count": 5,
            "failure_count": 0,
            "results": {"success": [], "failed": []}
        }
        
        result = process_batch("BSO001", use_background_job=False)
        
        self.assertEqual(result["success_count"], 5)
        self.assertEqual(mock_batch.status, "Processing")
        mock_process_job.assert_called_once_with("BSO001")


class TestUpdateBackendStudentStatus(unittest.TestCase):
    """Test backend student status update"""
    
    def test_update_success_status(self):
        """Test updating student status to success"""
        student = MagicMock()
        student_doc = MagicMock()
        student_doc.name = "ST00001"
        student_doc.glific_id = "12345"
        
        update_backend_student_status(student, "Success", student_doc)
        
        self.assertEqual(student.processing_status, "Success")
        self.assertEqual(student.student_id, "ST00001")
        student.save.assert_called_once()
    
    def test_update_failed_status_with_error(self):
        """Test updating student status to failed with error message"""
        student = MagicMock()
        student.processing_notes = ""
        
        error_msg = "Test error message"
        update_backend_student_status(student, "Failed", error=error_msg)
        
        self.assertEqual(student.processing_status, "Failed")
        self.assertEqual(student.processing_notes, error_msg)
        student.save.assert_called_once()


class TestValidateEnrollmentData(unittest.TestCase):
    """Test enrollment data validation"""
    
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    def test_validate_valid_enrollments(self, mock_exists, mock_sql):
        """Test validation of valid enrollments"""
        mock_sql.return_value = [
            {
                "student_id": "ST00001",
                "enrollment_id": "EN001",
                "course": "CL001",
                "batch": "BT001",
                "grade": "5"
            }
        ]
        mock_exists.return_value = True
        
        result = validate_enrollment_data("John Doe", "9876543210")
        
        self.assertEqual(result["total_enrollments"], 1)
        self.assertEqual(result["valid_enrollments"], 1)
        self.assertEqual(result["broken_enrollments"], 0)
    
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    def test_validate_broken_enrollments(self, mock_exists, mock_sql):
        """Test validation detecting broken course links"""
        mock_sql.return_value = [
            {
                "student_id": "ST00001",
                "enrollment_id": "EN001",
                "course": "CL999",
                "batch": "BT001",
                "grade": "5"
            }
        ]
        mock_exists.return_value = False
        
        result = validate_enrollment_data("John Doe", "9876543210")
        
        self.assertEqual(result["total_enrollments"], 1)
        self.assertEqual(result["valid_enrollments"], 0)
        self.assertEqual(result["broken_enrollments"], 1)
        self.assertEqual(len(result["broken_details"]), 1)


class TestGetInitialStage(unittest.TestCase):
    """Test getting initial onboarding stage"""
    
    @patch('frappe.get_all')
    def test_get_initial_stage_with_order_zero(self, mock_get_all):
        """Test getting stage with order=0"""
        mock_get_all.return_value = [{"name": "Stage1"}]
        
        result = get_initial_stage()
        
        self.assertEqual(result, "Stage1")
        mock_get_all.assert_called_once_with(
            "OnboardingStage",
            filters={"order": 0},
            fields=["name"]
        )
    
    @patch('frappe.get_all')
    def test_get_initial_stage_fallback(self, mock_get_all):
        """Test getting stage with minimum order when no order=0"""
        mock_get_all.side_effect = [
            [],  # No stage with order=0
            [{"name": "Stage2", "order": 1}]  # Stage with minimum order
        ]
        
        result = get_initial_stage()
        
        self.assertEqual(result, "Stage2")
        self.assertEqual(mock_get_all.call_count, 2)


if __name__ == '__main__':
    unittest.main()