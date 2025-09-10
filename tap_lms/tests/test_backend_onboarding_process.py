


# import pytest
# from unittest.mock import MagicMock, patch, call
# import json
# from datetime import datetime


# # Define all the functions locally to avoid import issues
# def normalize_phone_number(phone):
#     if not phone:
#         return None, None
    
#     phone = phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
#     phone = ''.join(filter(str.isdigit, phone))
    
#     if len(phone) == 10:
#         return f"91{phone}", phone
#     elif len(phone) == 12 and phone.startswith('91'):
#         return phone, phone[2:]
#     elif len(phone) == 11 and phone.startswith('1'):
#         return f"9{phone}", phone[1:]
#     else:
#         return None, None


# def format_phone_number(phone):
#     """Format phone number for Glific"""
#     if phone.startswith("91"):
#         return phone
#     return f"91{phone}"


# def get_current_academic_year_backend():
#     """Get current academic year based on date"""
#     try:
#         import frappe
#         from frappe.utils import getdate
#         current_date = getdate()
#     except ImportError:
#         # For testing without frappe
#         current_date = datetime.now().date()
    
#     if current_date.month >= 4:  # April onwards is new academic year
#         return f"{current_date.year}-{str(current_date.year + 1)[-2:]}"
#     else:  # January-March is previous academic year
#         return f"{current_date.year - 1}-{str(current_date.year)[-2:]}"


# class TestBackendStudentOnboarding:
    
#     def test_normalize_phone_number_valid_formats(self):
#         """Test phone number normalization for various valid formats"""
#         # 10-digit numbers
#         assert normalize_phone_number("9876543210") == ("919876543210", "9876543210")
#         assert normalize_phone_number(" 987-654-3210 ") == ("919876543210", "9876543210")
#         assert normalize_phone_number("(987) 654-3210") == ("919876543210", "9876543210")
        
#         # 12-digit numbers
#         assert normalize_phone_number("919876543210") == ("919876543210", "9876543210")
        
#         # Edge cases
#         assert normalize_phone_number("19876543210") == ("919876543210", "9876543210")
        
#     def test_normalize_phone_number_invalid_formats(self):
#         """Test phone number normalization for invalid formats"""
#         assert normalize_phone_number("123") == (None, None)
#         assert normalize_phone_number("abcdef") == (None, None)
#         assert normalize_phone_number("") == (None, None)
#         assert normalize_phone_number("987654321") == (None, None)  # 9 digits
#         assert normalize_phone_number("9198765432101") == (None, None)  # 13 digits
    
#     @patch('frappe.db.sql')
#     def test_find_existing_student_by_phone_and_name(self, mock_sql):
#         """Test finding existing students with different phone formats"""
        
#         def find_existing_student_by_phone_and_name(phone, name):
#             normalized_phone, local_phone = normalize_phone_number(phone)
#             if not normalized_phone:
#                 return None
            
#             result = mock_sql(
#                 """
#                 SELECT name, phone, name1
#                 FROM `tabStudent`
#                 WHERE name1 = %s 
#                 AND (phone = %s OR phone = %s)
#                 LIMIT 1
#                 """, 
#                 (name, local_phone, normalized_phone),
#                 as_dict=True
#             )
#             return result[0] if result else None
        
#         test_student = {
#             "name": "STU001",
#             "name1": "Test Student",
#             "phone": "9876543210"
#         }
        
#         mock_sql.return_value = [test_student]
        
#         # Test with 10-digit format
#         result = find_existing_student_by_phone_and_name("9876543210", "Test Student")
#         assert result == test_student
        
#         # Test with 12-digit format
#         result = find_existing_student_by_phone_and_name("919876543210", "Test Student")
#         assert result == test_student
    
#     def test_validate_student_missing_fields(self):
#         """Test student validation for missing required fields"""
        
#         def validate_student(student):
#             validation = {}
#             required_fields = ["school", "grade", "language", "batch"]
            
#             for field in required_fields:
#                 if field not in student or not student[field]:
#                     validation[field] = f"{field} is required"
            
#             return validation
        
#         incomplete_student = {
#             "student_name": "Test Student",
#             "phone": "9876543210"
#             # Missing school, grade, language, batch
#         }
        
#         validation = validate_student(incomplete_student)
#         assert "school" in validation
#         assert "grade" in validation
#         assert "language" in validation
#         assert "batch" in validation
    
#     def test_validate_student_duplicate(self):
#         """Test student validation for duplicate detection"""
        
#         def validate_student_with_duplicate_check(student, existing_student=None):
#             validation = {}
            
#             # Check for duplicates
#             if existing_student:
#                 validation["duplicate"] = {
#                     "student_id": existing_student["name"],
#                     "student_name": existing_student["name1"]
#                 }
            
#             return validation
        
#         existing_student = {"name": "EXISTING_STU", "name1": "Existing Student"}
        
#         complete_student = {
#             "student_name": "Test Student",
#             "phone": "9876543210",
#             "school": "SCH001",
#             "grade": "5",
#             "language": "EN",
#             "batch": "BATCH001"
#         }
        
#         validation = validate_student_with_duplicate_check(complete_student, existing_student)
#         assert "duplicate" in validation
#         assert validation["duplicate"]["student_id"] == "EXISTING_STU"
    
  
#     def test_process_batch_job_success(self):
#         """Test successful batch processing"""
        
#         def process_batch_job_mock(batch_id):
#             """Mock implementation of process_batch_job"""
#             # Mock batch processing logic
#             students_to_process = [
#                 {
#                     "name": "BACKEND_STU001",
#                     "student_name": "Test Student",
#                     "phone": "9876543210",
#                     "batch_skeyword": "TEST_BATCH"
#                 }
#             ]
            
#             success_count = 0
#             failure_count = 0
            
#             for student in students_to_process:
#                 try:
#                     # Mock successful processing
#                     success_count += 1
#                 except Exception:
#                     failure_count += 1
            
#             return {"success_count": success_count, "failure_count": failure_count}
        
#         result = process_batch_job_mock("BATCH001")
        
#         assert result["success_count"] == 1
#         assert result["failure_count"] == 0
    
#     def test_determine_student_type_backend(self):
#         """Test student type determination logic"""
        
#         def determine_student_type_backend_mock(phone, name, course_vertical):
#             """Mock implementation - in real scenario this would check database"""
#             # For testing, assume all students are "New"
#             return "New"
        
#         result = determine_student_type_backend_mock("9876543210", "Test Student", "MATH")
#         assert result == "New"
    
#     def test_get_course_level_with_mapping_backend(self):
#         """Test course level selection with mapping"""
        
#         def get_course_level_with_mapping_backend_mock(course_vertical, grade, phone, name, kit_less):
#             """Mock implementation"""
#             return f"{course_vertical}_GRADE{grade}"
        
#         result = get_course_level_with_mapping_backend_mock(
#             "MATH", "5", "9876543210", "Test Student", False
#         )
#         assert result == "MATH_GRADE5"
    
#     def test_process_glific_contact(self):
#         """Test Glific contact processing"""
        
#         def process_glific_contact_mock(student, glific_group):
#             """Mock implementation"""
#             return {"id": "GLIFIC001"}
        
#         mock_student = MagicMock()
#         mock_student.phone = "9876543210"
#         mock_student.student_name = "Test Student"
        
#         result = process_glific_contact_mock(mock_student, {"group_id": "GROUP001"})
#         assert result["id"] == "GLIFIC001"
    
#     def test_process_student_record_new_student(self):
#         """Test processing a new student record"""
        
#         def process_student_record_mock(backend_student, glific_contact, batch_id, initial_stage):
#             """Mock implementation"""
#             # Mock creating new student document
#             mock_student_doc = MagicMock()
#             mock_student_doc.name = "STU001"
#             mock_student_doc.name1 = backend_student.student_name
#             mock_student_doc.phone = backend_student.phone
#             return mock_student_doc
        
#         mock_backend_student = MagicMock()
#         mock_backend_student.phone = "9876543210"
#         mock_backend_student.student_name = "New Student"
        
#         result = process_student_record_mock(
#             mock_backend_student, 
#             {"id": "GLIFIC001"}, 
#             "BATCH001", 
#             "STAGE001"
#         )
        
#         assert result.name == "STU001"
#         assert result.name1 == "New Student"
#         assert result.phone == "9876543210"
    
#     def test_update_backend_student_status_success(self):
#         """Test updating backend student status for success"""
        
#         def update_backend_student_status_mock(backend_student, status, student_doc=None, error=None):
#             """Mock implementation"""
#             backend_student.processing_status = status
#             if student_doc:
#                 backend_student.student_id = student_doc.name
#                 backend_student.glific_id = getattr(student_doc, 'glific_id', None)
#             if error:
#                 backend_student.error_message = error
        
#         mock_student = MagicMock()
#         mock_student_doc = MagicMock()
#         mock_student_doc.name = "STU001"
#         mock_student_doc.glific_id = "GLIFIC001"
        
#         update_backend_student_status_mock(mock_student, "Success", mock_student_doc)
        
#         assert mock_student.processing_status == "Success"
#         assert mock_student.student_id == "STU001"
#         assert mock_student.glific_id == "GLIFIC001"
    
#     def test_update_backend_student_status_failed(self):
#         """Test updating backend student status for failure"""
        
#         def update_backend_student_status_mock(backend_student, status, student_doc=None, error=None):
#             """Mock implementation"""
#             backend_student.processing_status = status
#             if error:
#                 backend_student.error_message = error
        
#         mock_student = MagicMock()
        
#         update_backend_student_status_mock(mock_student, "Failed", error="Test error")
        
#         assert mock_student.processing_status == "Failed"
#         assert mock_student.error_message == "Test error"
    
#     def test_format_phone_number(self):
#         """Test phone number formatting for Glific"""
#         result = format_phone_number("9876543210")
#         assert result == "919876543210"
        
#         result = format_phone_number("919876543210")
#         assert result == "919876543210"
    
#     def test_get_current_academic_year_backend(self):
#         """Test academic year calculation"""
#         # Test with mock dates
#         test_cases = [
#             (datetime(2024, 6, 15), "2024-25"),  # June - new academic year
#             (datetime(2024, 2, 15), "2023-24"),  # February - previous academic year
#             (datetime(2024, 4, 1), "2024-25"),   # April 1 - new academic year starts
#             (datetime(2024, 3, 31), "2023-24"),  # March 31 - previous academic year
#         ]
        
#         for test_date, expected_year in test_cases:
#             # Mock the current date
#             with patch('datetime.datetime') as mock_datetime:
#                 mock_datetime.now.return_value = test_date
#                 mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
                
#                 # Test with the mocked date
#                 def get_current_academic_year_test():
#                     current_date = mock_datetime.now().date()
#                     if current_date.month >= 4:
#                         return f"{current_date.year}-{str(current_date.year + 1)[-2:]}"
#                     else:
#                         return f"{current_date.year - 1}-{str(current_date.year)[-2:]}"
                
#                 result = get_current_academic_year_test()
#                 assert result == expected_year
    
#     def test_background_job_processing(self):
#         """Test batch processing with background job simulation"""
        
#         def process_batch_with_job_mock(batch_id, use_background_job=False):
#             """Mock implementation of batch processing with job queue"""
#             if use_background_job:
#                 # Simulate enqueuing a background job
#                 mock_job = MagicMock()
#                 mock_job.id = "JOB001"
#                 return {"job_id": mock_job.id}
#             else:
#                 # Process immediately
#                 return {"success_count": 1, "failure_count": 0}
        
#         # Test background job
#         result = process_batch_with_job_mock("BATCH001", use_background_job=True)
#         assert "job_id" in result
#         assert result["job_id"] == "JOB001"
        
#         # Test immediate processing
#         result = process_batch_with_job_mock("BATCH001", use_background_job=False)
#         assert result["success_count"] == 1
#         assert result["failure_count"] == 0
    
#     def test_job_status_checking(self):
#         """Test getting job status"""
        
#         def get_job_status_mock(job_id):
#             """Mock implementation"""
#             # Simulate job status response
#             return {
#                 "status": "Completed",
#                 "progress": 100,
#                 "result": {"success": True, "processed_count": 10}
#             }
        
#         result = get_job_status_mock("JOB001")
#         assert result["status"] == "Completed"
#         assert result["progress"] == 100
#         assert result["result"]["success"] is True
    
#     def test_phone_number_edge_cases(self):
#         """Test edge cases for phone number handling"""
#         test_cases = [
#             ("", (None, None)),
#             (None, (None, None)),
#             ("   ", (None, None)),
#             ("abc123def", (None, None)),
#             ("12345", (None, None)),
#             ("123456789", (None, None)),  # 9 digits
#             ("12345678901234", (None, None)),  # 14 digits
#             ("0987654321", ("910987654321", "0987654321")),  # Starting with 0
#             ("+919876543210", ("919876543210", "9876543210")),  # With + sign
#         ]
        
#         for phone_input, expected in test_cases:
#             result = normalize_phone_number(phone_input)
#             assert result == expected, f"Failed for input: {phone_input}"
    
#     def test_student_validation_comprehensive(self):
#         """Test comprehensive student validation"""
        
#         def comprehensive_validate_student(student):
#             """Comprehensive validation function"""
#             validation = {}
            
#             # Required field validation
#             required_fields = {
#                 "student_name": "Student name is required",
#                 "phone": "Phone number is required",
#                 "school": "School is required",
#                 "grade": "Grade is required",
#                 "language": "Language is required",
#                 "batch": "Batch is required"
#             }
            
#             for field, message in required_fields.items():
#                 if field not in student or not str(student[field]).strip():
#                     validation[field] = message
            
#             # Phone number format validation
#             if "phone" in student:
#                 normalized_phone, _ = normalize_phone_number(student["phone"])
#                 if not normalized_phone:
#                     validation["phone_format"] = "Invalid phone number format"
            
#             # Grade validation
#             if "grade" in student:
#                 try:
#                     grade_int = int(student["grade"])
#                     if grade_int < 1 or grade_int > 12:
#                         validation["grade_range"] = "Grade must be between 1 and 12"
#                 except (ValueError, TypeError):
#                     validation["grade_format"] = "Grade must be a valid number"
            
#             return validation
        
#         # Test complete valid student
#         valid_student = {
#             "student_name": "Test Student",
#             "phone": "9876543210",
#             "school": "SCH001",
#             "grade": "5",
#             "language": "EN",
#             "batch": "BATCH001"
#         }
        
#         validation = comprehensive_validate_student(valid_student)
#         assert len(validation) == 0
        
#         # Test invalid phone
#         invalid_phone_student = valid_student.copy()
#         invalid_phone_student["phone"] = "123"
        
#         validation = comprehensive_validate_student(invalid_phone_student)
#         assert "phone_format" in validation
        
#         # Test invalid grade
#         invalid_grade_student = valid_student.copy()
#         invalid_grade_student["grade"] = "15"
        
#         validation = comprehensive_validate_student(invalid_grade_student)
#         assert "grade_range" in validation


# if __name__ == "__main__":
#     pytest.main([__file__, "-v"])



import unittest
from unittest.mock import Mock, patch, MagicMock
import frappe
from frappe.utils import nowdate, nowtime, now
import json

# Import the module to test
from tap_lms.page.backend_onboarding_process.backend_onboarding_process import (
    normalize_phone_number,
    find_existing_student_by_phone_and_name,
    validate_student,
    get_initial_stage,
    process_batch_job,
    process_glific_contact,
    determine_student_type_backend,
    get_current_academic_year_backend,
    validate_enrollment_data,
    get_course_level_with_mapping_backend,
    get_course_level_with_validation_backend,
    process_student_record,
    update_backend_student_status,
    format_phone_number,
    fix_broken_course_links,
    debug_student_type_analysis,
    debug_student_processing,
    test_basic_student_creation
)


class TestBackendOnboardingProcess(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.test_phone_10 = "9876543210"
        self.test_phone_12 = "919876543210"
        self.test_student_name = "Test Student"
        self.test_course_vertical = "Math"
        self.test_grade = "5"
        
    def tearDown(self):
        """Clean up after each test method."""
        pass

    # Test normalize_phone_number function
    def test_normalize_phone_number_10_digit(self):
        """Test normalization of 10-digit phone number."""
        phone_12, phone_10 = normalize_phone_number("9876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_normalize_phone_number_12_digit(self):
        """Test normalization of 12-digit phone number."""
        phone_12, phone_10 = normalize_phone_number("919876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_normalize_phone_number_11_digit_with_1_prefix(self):
        """Test normalization of 11-digit phone number with 1 prefix."""
        phone_12, phone_10 = normalize_phone_number("19876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_normalize_phone_number_with_spaces_and_special_chars(self):
        """Test normalization with spaces and special characters."""
        phone_12, phone_10 = normalize_phone_number("(987) 654-3210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")
    
    def test_normalize_phone_number_invalid_format(self):
        """Test normalization with invalid phone number format."""
        phone_12, phone_10 = normalize_phone_number("123")
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)
    
    def test_normalize_phone_number_empty(self):
        """Test normalization with empty phone number."""
        phone_12, phone_10 = normalize_phone_number("")
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)

    # Test find_existing_student_by_phone_and_name function
    @patch('frappe.db.sql')
    def test_find_existing_student_by_phone_and_name_found(self, mock_sql):
        """Test finding existing student by phone and name."""
        mock_sql.return_value = [{"name": "STU001", "phone": "919876543210", "name1": "Test Student"}]
        
        result = find_existing_student_by_phone_and_name("9876543210", "Test Student")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "STU001")
        mock_sql.assert_called_once()
    
    @patch('frappe.db.sql')
    def test_find_existing_student_by_phone_and_name_not_found(self, mock_sql):
        """Test when no existing student is found."""
        mock_sql.return_value = []
        
        result = find_existing_student_by_phone_and_name("9876543210", "Test Student")
        
        self.assertIsNone(result)
    
    def test_find_existing_student_by_phone_and_name_empty_params(self):
        """Test with empty parameters."""
        result = find_existing_student_by_phone_and_name("", "Test Student")
        self.assertIsNone(result)
        
        result = find_existing_student_by_phone_and_name("9876543210", "")
        self.assertIsNone(result)

    # Test validate_student function
    def test_validate_student_all_fields_present(self):
        """Test validation when all required fields are present."""
        student = {
            "student_name": "Test Student",
            "phone": "9876543210",
            "school": "SCH001",
            "grade": "5",
            "language": "English",
            "batch": "BAT001"
        }
        
        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name', return_value=None):
            validation = validate_student(student)
            self.assertEqual(len(validation), 0)
    
    def test_validate_student_missing_required_fields(self):
        """Test validation with missing required fields."""
        student = {
            "student_name": "",
            "phone": "9876543210",
            "school": "",
            "grade": "5",
            "language": "English",
            "batch": "BAT001"
        }
        
        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name', return_value=None):
            validation = validate_student(student)
            self.assertIn("student_name", validation)
            self.assertIn("school", validation)
            self.assertEqual(validation["student_name"], "missing")
            self.assertEqual(validation["school"], "missing")
    
    def test_validate_student_duplicate_found(self):
        """Test validation when duplicate student is found."""
        student = {
            "student_name": "Test Student",
            "phone": "9876543210",
            "school": "SCH001",
            "grade": "5",
            "language": "English",
            "batch": "BAT001"
        }
        
        existing = {"name": "STU001", "name1": "Test Student"}
        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name', return_value=existing):
            validation = validate_student(student)
            self.assertIn("duplicate", validation)
            self.assertEqual(validation["duplicate"]["student_id"], "STU001")

    # Test get_initial_stage function
    @patch('frappe.db.table_exists')
    @patch('frappe.get_all')
    def test_get_initial_stage_order_zero_exists(self, mock_get_all, mock_table_exists):
        """Test getting initial stage when order 0 exists."""
        mock_table_exists.return_value = True
        mock_get_all.side_effect = [
            [{"name": "Stage0"}],  # First call for order=0
            []  # Won't be called since first succeeds
        ]
        
        result = get_initial_stage()
        
        self.assertEqual(result, "Stage0")
        self.assertEqual(mock_get_all.call_count, 1)
    
    @patch('frappe.db.table_exists')
    @patch('frappe.get_all')
    def test_get_initial_stage_fallback_to_min_order(self, mock_get_all, mock_table_exists):
        """Test getting initial stage when order 0 doesn't exist."""
        mock_table_exists.return_value = True
        mock_get_all.side_effect = [
            [],  # First call for order=0 returns empty
            [{"name": "Stage1", "order": 1}]  # Second call for minimum order
        ]
        
        result = get_initial_stage()
        
        self.assertEqual(result, "Stage1")
        self.assertEqual(mock_get_all.call_count, 2)
    
    @patch('frappe.db.table_exists')
    def test_get_initial_stage_table_not_exists(self, mock_table_exists):
        """Test when OnboardingStage table doesn't exist."""
        mock_table_exists.return_value = False
        
        result = get_initial_stage()
        
        self.assertEqual(result, [])  # Should return empty list

    # Test determine_student_type_backend function
    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_backend_new_student(self, mock_log_error, mock_sql):
        """Test student type determination for new student."""
        mock_sql.return_value = []  # No existing student found
        
        result = determine_student_type_backend("9876543210", "Test Student", "Math")
        
        self.assertEqual(result, "New")
    
    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_backend_old_student_same_vertical(self, mock_log_error, mock_sql):
        """Test student type determination for old student with same vertical."""
        # Mock finding existing student
        mock_sql.side_effect = [
            [{"name": "STU001", "phone": "919876543210", "name1": "Test Student"}],  # Existing student
            [{"name": "ENR001", "course": "MATH101", "batch": "BAT001", "grade": "5", "school": "SCH001"}],  # Enrollments
            [{"vertical_name": "Math"}]  # Course vertical data
        ]
        
        result = determine_student_type_backend("9876543210", "Test Student", "Math")
        
        self.assertEqual(result, "Old")
    
    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_backend_broken_course_links(self, mock_log_error, mock_sql):
        """Test student type determination with broken course links."""
        mock_sql.side_effect = [
            [{"name": "STU001", "phone": "919876543210", "name1": "Test Student"}],  # Existing student
            [{"name": "ENR001", "course": "NONEXISTENT", "batch": "BAT001", "grade": "5", "school": "SCH001"}],  # Enrollments
            []  # No course vertical data (broken link)
        ]
        
        with patch('frappe.db.exists', return_value=False):  # Course doesn't exist
            result = determine_student_type_backend("9876543210", "Test Student", "Math")
        
        self.assertEqual(result, "Old")

    # Test get_current_academic_year_backend function
    @patch('frappe.utils.getdate')
    @patch('frappe.log_error')
    def test_get_current_academic_year_backend_after_april(self, mock_log_error, mock_getdate):
        """Test academic year calculation after April."""
        from datetime import date
        mock_getdate.return_value = date(2025, 5, 15)  # May 2025
        
        result = get_current_academic_year_backend()
        
        self.assertEqual(result, "2025-26")
    
    @patch('frappe.utils.getdate')
    @patch('frappe.log_error')
    def test_get_current_academic_year_backend_before_april(self, mock_log_error, mock_getdate):
        """Test academic year calculation before April."""
        from datetime import date
        mock_getdate.return_value = date(2025, 2, 15)  # February 2025
        
        result = get_current_academic_year_backend()
        
        self.assertEqual(result, "2024-25")
    
    @patch('frappe.utils.getdate')
    @patch('frappe.log_error')
    def test_get_current_academic_year_backend_error(self, mock_log_error, mock_getdate):
        """Test academic year calculation with error."""
        mock_getdate.side_effect = Exception("Date error")
        
        result = get_current_academic_year_backend()
        
        self.assertIsNone(result)
        mock_log_error.assert_called()

    # Test validate_enrollment_data function
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    @patch('frappe.log_error')
    def test_validate_enrollment_data_valid_enrollments(self, mock_log_error, mock_exists, mock_sql):
        """Test validation with valid enrollment data."""
        mock_sql.return_value = [
            {"student_id": "STU001", "enrollment_id": "ENR001", "course": "MATH101", "batch": "BAT001", "grade": "5"}
        ]
        mock_exists.return_value = True  # Course exists
        
        result = validate_enrollment_data("Test Student", "9876543210")
        
        self.assertEqual(result["total_enrollments"], 1)
        self.assertEqual(result["valid_enrollments"], 1)
        self.assertEqual(result["broken_enrollments"], 0)
    
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    @patch('frappe.log_error')
    def test_validate_enrollment_data_broken_enrollments(self, mock_log_error, mock_exists, mock_sql):
        """Test validation with broken enrollment data."""
        mock_sql.return_value = [
            {"student_id": "STU001", "enrollment_id": "ENR001", "course": "NONEXISTENT", "batch": "BAT001", "grade": "5"}
        ]
        mock_exists.return_value = False  # Course doesn't exist
        
        result = validate_enrollment_data("Test Student", "9876543210")
        
        self.assertEqual(result["total_enrollments"], 1)
        self.assertEqual(result["valid_enrollments"], 0)
        self.assertEqual(result["broken_enrollments"], 1)
        self.assertEqual(len(result["broken_details"]), 1)
        self.assertEqual(result["broken_details"][0]["invalid_course"], "NONEXISTENT")

    # Test format_phone_number function
    def test_format_phone_number_valid(self):
        """Test phone number formatting for Glific."""
        result = format_phone_number("9876543210")
        self.assertEqual(result, "919876543210")
    
    def test_format_phone_number_invalid(self):
        """Test phone number formatting with invalid input."""
        result = format_phone_number("123")
        self.assertIsNone(result)

    # Test update_backend_student_status function
    @patch('frappe.get_meta')
    def test_update_backend_student_status_success(self, mock_get_meta):
        """Test updating backend student status to success."""
        mock_student = Mock()
        mock_student_doc = Mock()
        mock_student_doc.name = "STU001"
        mock_student_doc.glific_id = "GLIFIC123"
        mock_student.save = Mock()
        
        # Mock metadata for processing_notes field
        mock_field = Mock()
        mock_field.length = 140
        mock_meta = Mock()
        mock_meta.get_field.return_value = mock_field
        mock_get_meta.return_value = mock_meta
        
        update_backend_student_status(mock_student, "Success", mock_student_doc)
        
        self.assertEqual(mock_student.processing_status, "Success")
        self.assertEqual(mock_student.student_id, "STU001")
        mock_student.save.assert_called_once()
    
    @patch('frappe.get_meta')
    def test_update_backend_student_status_failed_with_error(self, mock_get_meta):
        """Test updating backend student status to failed with error message."""
        mock_student = Mock()
        mock_student.save = Mock()
        
        # Mock metadata for processing_notes field
        mock_field = Mock()
        mock_field.length = 140
        mock_meta = Mock()
        mock_meta.get_field.return_value = mock_field
        mock_get_meta.return_value = mock_meta
        
        # Add processing_notes attribute
        mock_student.processing_notes = None
        
        long_error = "This is a very long error message " * 10  # Make it longer than 140 chars
        
        update_backend_student_status(mock_student, "Failed", error=long_error)
        
        self.assertEqual(mock_student.processing_status, "Failed")
        self.assertEqual(len(mock_student.processing_notes), 140)  # Should be truncated
        mock_student.save.assert_called_once()

    # Test process_glific_contact function
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.format_phone_number')
    @patch('frappe.get_value')
    @patch('tap_lms.glific_integration.get_contact_by_phone')
    @patch('tap_lms.glific_integration.add_contact_to_group')
    @patch('tap_lms.glific_integration.update_contact_fields')
    def test_process_glific_contact_existing_contact(self, mock_update_fields, mock_add_to_group, 
                                                    mock_get_contact, mock_get_value, mock_format_phone):
        """Test processing Glific contact when contact already exists."""
        mock_format_phone.return_value = "919876543210"
        mock_get_value.side_effect = ["Test School", "BAT001", None, "Math Level 1", "Mathematics"]
        mock_get_contact.return_value = {"id": "CONTACT123"}
        mock_update_fields.return_value = {"success": True}
        
        mock_student = Mock()
        mock_student.phone = "9876543210"
        mock_student.student_name = "Test Student"
        mock_student.school = "SCH001"
        mock_student.batch = "BAT001"
        mock_student.language = "EN"
        mock_student.course_vertical = "MATH"
        mock_student.grade = "5"
        
        mock_glific_group = {"group_id": "GROUP123"}
        
        result = process_glific_contact(mock_student, mock_glific_group, "MATH_L1")
        
        self.assertEqual(result["id"], "CONTACT123")
        mock_add_to_group.assert_called_once()
        mock_update_fields.assert_called_once()

    # Test process_student_record function
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name')
    @patch('frappe.get_doc')
    @patch('frappe.new_doc')
    @patch('frappe.utils.nowdate')
    @patch('frappe.db.exists')
    def test_process_student_record_new_student(self, mock_exists, mock_nowdate, 
                                              mock_new_doc, mock_get_doc, mock_find_existing):
        """Test processing student record for new student."""
        mock_find_existing.return_value = None
        mock_nowdate.return_value = "2025-01-15"
        mock_exists.side_effect = [False, False]  # LearningState and EngagementState don't exist
        
        # Mock new student document
        mock_student_doc = Mock()
        mock_student_doc.name = "STU001"
        mock_student_doc.append = Mock()
        mock_student_doc.insert = Mock()
        mock_new_doc.return_value = mock_student_doc
        
        # Mock LearningState and EngagementState creation
        mock_learning_state = Mock()
        mock_engagement_state = Mock()
        mock_stage_progress = Mock()
        mock_new_doc.side_effect = [mock_student_doc, mock_learning_state, mock_engagement_state, mock_stage_progress]
        
        # Mock student input
        mock_student = Mock()
        mock_student.student_name = "Test Student"
        mock_student.phone = "9876543210"
        mock_student.gender = "Male"
        mock_student.school = "SCH001"
        mock_student.grade = "5"
        mock_student.language = "EN"
        mock_student.batch = "BAT001"
        mock_student.course_vertical = "MATH"
        
        mock_glific_contact = {"id": "GLIFIC123"}
        
        result = process_student_record(mock_student, mock_glific_contact, "BATCH001", "STAGE001", "COURSE001")
        
        self.assertEqual(result.name, "STU001")
        mock_student_doc.insert.assert_called_once()
        mock_student_doc.append.assert_called()  # Should append enrollment

    # Integration test for process_batch_job
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.commit')
    @patch('frappe.log_error')
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.create_or_get_glific_group_for_batch')
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.get_initial_stage')
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.process_glific_contact')
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.process_student_record')
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.update_backend_student_status')
    def test_process_batch_job_success(self, mock_update_status, mock_process_student, 
                                     mock_process_glific, mock_get_initial_stage,
                                     mock_create_group, mock_log_error, mock_commit, 
                                     mock_get_all, mock_get_doc):
        """Test successful batch processing job."""
        # Mock batch document
        mock_batch = Mock()
        mock_batch.status = "Processing"
        mock_batch.save = Mock()
        mock_get_doc.return_value = mock_batch
        
        # Mock students to process
        mock_students = [{"name": "BS001", "batch_skeyword": "MATH5"}]
        mock_get_all.side_effect = [
            mock_students,  # Backend students
            [{"batch_skeyword": "MATH5", "name": "BO001", "kit_less": False}],  # Batch onboarding
            []  # Processed count query
        ]
        
        # Mock student document
        mock_student_doc = Mock()
        mock_student_doc.name = "BS001"
        mock_student_doc.student_name = "Test Student"
        mock_student_doc.phone = "9876543210"
        mock_student_doc.batch_skeyword = "MATH5"
        mock_student_doc.course_vertical = "MATH"
        mock_student_doc.grade = "5"
        mock_student_doc.save = Mock()
        mock_get_doc.side_effect = [mock_batch, mock_student_doc, mock_batch]  # batch, student, batch again for final update
        
        # Mock other functions
        mock_create_group.return_value = {"group_id": "GROUP123"}
        mock_get_initial_stage.return_value = "STAGE001"
        mock_process_glific.return_value = {"id": "GLIFIC123"}
        
        mock_processed_student = Mock()
        mock_processed_student.name = "STU001"
        mock_processed_student.name1 = "Test Student"
        mock_process_student.return_value = mock_processed_student
        
        # Mock update_job_progress to avoid errors
        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.update_job_progress'):
            result = process_batch_job("BATCH001")
        
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failure_count"], 0)
        mock_process_glific.assert_called_once()
        mock_process_student.assert_called_once()
        mock_update_status.assert_called_once()

    # Test error handling in process_batch_job
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.commit')
    @patch('frappe.db.rollback')
    @patch('frappe.log_error')
    def test_process_batch_job_with_errors(self, mock_log_error, mock_rollback, mock_commit, mock_get_all, mock_get_doc):
        """Test batch processing job with errors."""
        # Mock batch document
        mock_batch = Mock()
        mock_batch.status = "Processing"
        mock_batch.save = Mock()
        
        # Mock students to process
        mock_students = [{"name": "BS001", "batch_skeyword": "MATH5"}]
        mock_get_all.side_effect = [
            mock_students,  # Backend students
            [],  # No batch onboarding found
            []  # Processed count query
        ]
        
        # Mock student document that will cause an error
        mock_student_doc = Mock()
        mock_student_doc.name = "BS001"
        mock_student_doc.student_name = "Test Student"
        mock_student_doc.phone = "invalid_phone"
        mock_student_doc.save = Mock()
        
        mock_get_doc.side_effect = [mock_batch, mock_student_doc, mock_batch]
        
        # Mock functions to raise errors
        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.create_or_get_glific_group_for_batch', side_effect=Exception("Glific error")):
            with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.get_initial_stage', return_value="STAGE001"):
                with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.update_job_progress'):
                    result = process_batch_job("BATCH001")
        
        self.assertEqual(result["success_count"], 0)
        self.assertEqual(result["failure_count"], 1)
        mock_log_error.assert_called()

    # Test debug functions
    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_debug_student_type_analysis(self, mock_log_error, mock_sql):
        """Test debug student type analysis function."""
        mock_sql.side_effect = [
            [{"name": "STU001", "phone": "919876543210", "name1": "Test Student"}],  # Existing student
            [{"name": "ENR001", "course": "MATH101", "batch": "BAT001", "grade": "5", "school": "SCH001"}],  # Enrollments
            [{"vertical_name": "Math"}]  # Course vertical data
        ]
        
        with patch('frappe.db.exists', return_value=True):
            with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.determine_student_type_backend', return_value="Old"):
                result = debug_student_type_analysis("Test Student", "9876543210", "Math")
        
        self.assertIn("STUDENT TYPE ANALYSIS", result)
        self.assertIn("FINAL DETERMINATION: Old", result)

    @patch('frappe.new_doc')
    @patch('frappe.delete_doc')
    @patch('frappe.utils.nowdate')
    def test_basic_student_creation(self, mock_nowdate, mock_delete_doc, mock_new_doc):
        """Test basic student creation test function."""
        mock_nowdate.return_value = "2025-01-15"
        
        mock_student = Mock()
        mock_student.name = "TEST001"
        mock_student.insert = Mock()
        mock_student.append = Mock()
        mock_student.save = Mock()
        mock_new_doc.return_value = mock_student
        
        result = test_basic_student_creation()
        
        self.assertIn("BASIC TEST PASSED", result)
        mock_student.insert.assert_called_once()
        mock_delete_doc.assert_called_once_with("Student", "TEST001")

    # Test edge cases and error handling
    def test_normalize_phone_number_edge_cases(self):
        """Test edge cases for phone number normalization."""
        test_cases = [
            (None, (None, None)),
            ("", (None, None)),
            ("   ", (None, None)),
            ("abc", (None, None)),
            ("12345", (None, None)),
            ("1234567890123", (None, None)),  # Too long
        ]
        
        for phone_input, expected in test_cases:
            with self.subTest(phone_input=phone_input):
                result = normalize_phone_number(phone_input)
                self.assertEqual(result, expected)

    @patch('frappe.db.sql')
    def test_find_existing_student_error_handling(self, mock_sql):
        """Test error handling in find_existing_student_by_phone_and_name."""
        mock_sql.side_effect = Exception("Database error")
        
        # Should not raise exception, should return None
        result = find_existing_student_by_phone_and_name("9876543210", "Test Student")
        # Function doesn't have explicit error handling, so this might raise
        # In real implementation, you might want to add try-catch


# if _name_ == '_main_':
#     # Set up Frappe test environment if needed
#     unittest.main()