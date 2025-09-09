
import pytest
import frappe
import json
from unittest.mock import Mock, patch, MagicMock, call
from datetime import date, datetime

# Import the actual module
from tap_lms.backend_onboarding import *

class TestCompletePhoneNumberNormalization:
    """Complete coverage for phone number normalization"""

    def test_normalize_phone_empty_string(self):
        """Test empty string input"""
        result = normalize_phone_number("")
        assert result == (None, None)

    def test_normalize_phone_none_input(self):
        """Test None input"""
        result = normalize_phone_number(None)
        assert result == (None, None)

    def test_normalize_phone_with_spaces_and_dashes(self):
        """Test phone with multiple formatting characters"""
        result = normalize_phone_number(" 987-654-3210 ")
        assert result == ("919876543210", "9876543210")

    def test_normalize_phone_with_parentheses(self):
        """Test phone with parentheses"""
        result = normalize_phone_number("(987) 654-3210")
        assert result == ("919876543210", "9876543210")

    def test_normalize_phone_invalid_length(self):
        """Test invalid length phones"""
        # 8 digits
        result = normalize_phone_number("12345678")
        assert result == (None, None)
        
        # 13 digits
        result = normalize_phone_number("9876543210123")
        assert result == (None, None)

    def test_normalize_phone_11_digit_without_1_prefix(self):
        """Test 11 digits without 1 prefix"""
        result = normalize_phone_number("21234567890")  # starts with 2, not 1
        assert result == (None, None)

    def test_normalize_phone_with_non_digits(self):
        """Test phone with letters and special chars"""
        result = normalize_phone_number("98abc76543210")
        assert result == ("919876543210", "9876543210")  # Should filter out non-digits


class TestCompleteStudentSearch:
    """Complete coverage for student search functionality"""

    @patch('frappe.db.sql')
    def test_find_existing_student_empty_phone(self, mock_sql):
        """Test with empty phone number"""
        result = find_existing_student_by_phone_and_name("", "John Doe")
        assert result is None
        mock_sql.assert_not_called()

    @patch('frappe.db.sql')
    def test_find_existing_student_empty_name(self, mock_sql):
        """Test with empty name"""
        result = find_existing_student_by_phone_and_name("9876543210", "")
        assert result is None
        mock_sql.assert_not_called()

    @patch('frappe.db.sql')
    def test_find_existing_student_invalid_phone_format(self, mock_sql):
        """Test with invalid phone format"""
        result = find_existing_student_by_phone_and_name("invalid", "John Doe")
        assert result is None
        mock_sql.assert_not_called()

    @patch('frappe.db.sql')
    def test_find_existing_student_database_query(self, mock_sql):
        """Test actual database query execution"""
        mock_sql.return_value = [{'name': 'STU001', 'phone': '9876543210', 'name1': 'John Doe'}]
        
        result = find_existing_student_by_phone_and_name("9876543210", "John Doe")
        
        assert result['name'] == 'STU001'
        mock_sql.assert_called_once()
        # Verify the exact SQL query structure
        call_args = mock_sql.call_args
        assert "SELECT name, phone, name1" in call_args[0][0]
        assert "FROM `tabStudent`" in call_args[0][0]
        assert "WHERE name1 = %s" in call_args[0][0]
        assert "AND (phone = %s OR phone = %s)" in call_args[0][0]


class TestCompleteStudentValidation:
    """Complete coverage for student validation"""

    def test_validate_student_all_required_fields_missing(self):
        """Test with all required fields missing"""
        student_data = {}
        
        with patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name', return_value=None):
            validation = validate_student(student_data)
        
        required_fields = ["student_name", "phone", "school", "grade", "language", "batch"]
        for field in required_fields:
            assert field in validation
            assert validation[field] == "missing"

    def test_validate_student_partial_missing_fields(self):
        """Test with some required fields missing"""
        student_data = {
            'student_name': 'John Doe',
            'phone': '',  # missing
            'school': 'SCH001',
            'grade': '',  # missing
            'language': 'EN',
            'batch': 'BT001'
        }
        
        with patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name', return_value=None):
            validation = validate_student(student_data)
        
        assert 'phone' in validation
        assert 'grade' in validation
        assert validation['phone'] == 'missing'
        assert validation['grade'] == 'missing'
        # Should not have errors for fields that are present
        assert 'student_name' not in validation
        assert 'school' not in validation

    @patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name')
    def test_validate_student_duplicate_found(self, mock_find):
        """Test duplicate student detection"""
        student_data = {
            'student_name': 'John Doe',
            'phone': '9876543210',
            'school': 'SCH001',
            'grade': '5',
            'language': 'EN',
            'batch': 'BT001'
        }
        
        mock_find.return_value = {
            'name': 'STU001',
            'name1': 'John Doe'
        }
        
        validation = validate_student(student_data)
        
        assert 'duplicate' in validation
        assert validation['duplicate']['student_id'] == 'STU001'
        assert validation['duplicate']['student_name'] == 'John Doe'
        mock_find.assert_called_once_with('9876543210', 'John Doe')


class TestCompleteBatchManagement:
    """Complete coverage for batch management"""

    @patch('frappe.get_all')
    def test_get_onboarding_batches_with_print(self, mock_get_all):
        """Test get_onboarding_batches with print statement"""
        mock_get_all.return_value = [
            {'name': 'BSO001', 'set_name': 'Batch 1', 'upload_date': '2025-01-01'}
        ]
        
        # Capture print output
        with patch('builtins.print') as mock_print:
            result = get_onboarding_batches()
        
        mock_print.assert_called_once_with("get_onboarding_batches called")
        assert len(result) == 1
        mock_get_all.assert_called_once()

    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    def test_get_batch_details_complete(self, mock_get_all, mock_get_doc):
        """Test complete get_batch_details functionality"""
        # Mock batch document
        mock_batch = Mock()
        mock_batch.name = 'BSO001'
        mock_get_doc.return_value = mock_batch
        
        # Mock students with all fields
        mock_students = [
            {
                'name': 'BS001',
                'student_name': 'John Doe',
                'phone': '9876543210',
                'gender': 'Male',
                'batch': 'BT001',
                'course_vertical': 'Math',
                'grade': '5',
                'school': 'SCH001',
                'language': 'EN',
                'processing_status': 'Pending',
                'student_id': None
            }
        ]
        
        # Mock Glific group
        mock_glific_group = [{'group_id': 'GG001', 'label': 'Test Group'}]
        
        # Mock the get_all calls in order
        mock_get_all.side_effect = [mock_students, mock_glific_group]
        
        with patch('tap_lms.backend_onboarding.validate_student', return_value={'validation': 'test'}):
            result = get_batch_details('BSO001')
        
        assert result['batch'] == mock_batch
        assert len(result['students']) == 1
        assert result['students'][0]['validation'] == {'validation': 'test'}
        assert result['glific_group'] == mock_glific_group[0]
        
        # Verify correct calls
        mock_get_doc.assert_called_once_with("Backend Student Onboarding", 'BSO001')
        assert mock_get_all.call_count == 2

    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    def test_get_batch_details_no_glific_group(self, mock_get_all, mock_get_doc):
        """Test get_batch_details with no Glific group"""
        mock_batch = Mock()
        mock_get_doc.return_value = mock_batch
        
        # Mock empty students and empty glific group
        mock_get_all.side_effect = [[], []]  # Empty students, empty glific group
        
        result = get_batch_details('BSO001')
        
        assert result['batch'] == mock_batch
        assert result['students'] == []
        assert result['glific_group'] is None


class TestCompleteOnboardingStages:
    """Complete coverage for onboarding stages"""

    @patch('frappe.db.table_exists')
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_get_onboarding_stages_table_exists(self, mock_log, mock_get_all, mock_table_exists):
        """Test get_onboarding_stages when table exists"""
        mock_table_exists.return_value = True
        mock_stages = [
            {'name': 'STAGE001', 'description': 'Welcome', 'order': 0},
            {'name': 'STAGE002', 'description': 'Setup', 'order': 1}
        ]
        mock_get_all.return_value = mock_stages
        
        result = get_onboarding_stages()
        
        assert result == mock_stages
        mock_table_exists.assert_called_once_with("OnboardingStage")
        mock_get_all.assert_called_once()
        mock_log.assert_not_called()

    @patch('frappe.db.table_exists')
    @patch('frappe.log_error')
    def test_get_onboarding_stages_table_not_exists(self, mock_log, mock_table_exists):
        """Test get_onboarding_stages when table doesn't exist"""
        mock_table_exists.return_value = False
        
        result = get_onboarding_stages()
        
        assert result == []
        mock_table_exists.assert_called_once_with("OnboardingStage")
        mock_log.assert_not_called()

    @patch('frappe.db.table_exists')
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_get_onboarding_stages_exception(self, mock_log, mock_get_all, mock_table_exists):
        """Test get_onboarding_stages with exception"""
        mock_table_exists.return_value = True
        mock_get_all.side_effect = Exception("Database error")
        
        result = get_onboarding_stages()
        
        assert result == []
        mock_log.assert_called_once()
        error_call = mock_log.call_args[0]
        assert "Error fetching OnboardingStage" in error_call[0]

    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_get_initial_stage_order_zero_found(self, mock_log, mock_get_all):
        """Test get_initial_stage with order=0 stage found"""
        mock_get_all.return_value = [{'name': 'STAGE001'}]
        
        result = get_initial_stage()
        
        assert result == 'STAGE001'
        mock_get_all.assert_called_once()
        mock_log.assert_not_called()

    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_get_initial_stage_min_order(self, mock_log, mock_get_all):
        """Test get_initial_stage with minimum order when no order=0"""
        # First call returns empty (no order=0), second returns minimum order
        mock_get_all.side_effect = [[], [{'name': 'STAGE002', 'order': 1}]]
        
        result = get_initial_stage()
        
        assert result == 'STAGE002'
        assert mock_get_all.call_count == 2
        mock_log.assert_not_called()

    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_get_initial_stage_exception(self, mock_log, mock_get_all):
        """Test get_initial_stage with exception"""
        mock_get_all.side_effect = Exception("Database error")
        
        result = get_initial_stage()
        
        assert result is None
        mock_log.assert_called_once()
        error_call = mock_log.call_args[0]
        assert "Error getting initial stage" in error_call[0]

    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_get_initial_stage_no_stages(self, mock_log, mock_get_all):
        """Test get_initial_stage when no stages exist"""
        mock_get_all.side_effect = [[], []]  # No order=0, no minimum order stages
        
        result = get_initial_stage()
        
        assert result is None
        assert mock_get_all.call_count == 2


class TestCompleteStudentTypeDetection:
    """Complete coverage for student type detection"""

    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_invalid_phone_format(self, mock_log, mock_sql):
        """Test with invalid phone format"""
        result = determine_student_type_backend("invalid_phone", "John Doe", "Math")
        
        assert result == "New"
        mock_sql.assert_not_called()
        mock_log.assert_called()

    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_existing_student_null_course(self, mock_log, mock_sql):
        """Test existing student with NULL course enrollments"""
        # Mock existing student
        mock_sql.side_effect = [
            [{'name': 'STU001', 'phone': '9876543210', 'name1': 'John Doe'}],  # Student exists
            [{'name': 'ENR001', 'course': None, 'batch': 'BT001', 'grade': '5', 'school': 'SCH001'}]  # NULL course
        ]
        
        result = determine_student_type_backend("9876543210", "John Doe", "Math")
        
        assert result == "Old"
        mock_log.assert_called()
        # Check that the log message mentions NULL course
        log_calls = mock_log.call_args_list
        found_null_log = any("NULL courses: 1" in str(call) for call in log_calls)
        assert found_null_log

    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_mixed_enrollments_priority(self, mock_log, mock_sql):
        """Test mixed enrollments with priority logic"""
        # Mock existing student with mixed enrollment types
        mock_sql.side_effect = [
            [{'name': 'STU001', 'phone': '9876543210', 'name1': 'John Doe'}],  # Student exists
            [
                {'name': 'ENR001', 'course': 'CL001', 'batch': 'BT001', 'grade': '5', 'school': 'SCH001'},  # Same vertical
                {'name': 'ENR002', 'course': 'CL002', 'batch': 'BT002', 'grade': '6', 'school': 'SCH001'}   # Different vertical
            ],
            [{'vertical_name': 'Math'}],  # First course vertical
            [{'vertical_name': 'Science'}]  # Second course vertical
        ]
        
        result = determine_student_type_backend("9876543210", "John Doe", "Math")
        
        # Should be "Old" because same vertical takes priority
        assert result == "Old"
        mock_log.assert_called()

    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_database_exception(self, mock_log, mock_sql):
        """Test database exception handling"""
        mock_sql.side_effect = Exception("Database connection failed")
        
        result = determine_student_type_backend("9876543210", "John Doe", "Math")
        
        assert result == "New"  # Default on error
        mock_log.assert_called()
        error_call = mock_log.call_args[0]
        assert "Error determining student type" in error_call[0]

    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_determine_student_type_undetermined_vertical(self, mock_log, mock_sql):
        """Test enrollment with undetermined vertical"""
        mock_sql.side_effect = [
            [{'name': 'STU001', 'phone': '9876543210', 'name1': 'John Doe'}],  # Student exists
            [{'name': 'ENR001', 'course': 'CL001', 'batch': 'BT001', 'grade': '5', 'school': 'SCH001'}],
            []  # No vertical data found - undetermined
        ]
        
        result = determine_student_type_backend("9876543210", "John Doe", "Math")
        
        assert result == "Old"
        mock_log.assert_called()
        # Check that log mentions undetermined vertical
        log_calls = mock_log.call_args_list
        found_undetermined_log = any("Undetermined: 1" in str(call) for call in log_calls)
        assert found_undetermined_log


class TestCompleteAcademicYear:
    """Complete coverage for academic year calculation"""

    @patch('frappe.utils.getdate')
    @patch('frappe.log_error')
    def test_get_current_academic_year_april_first(self, mock_log, mock_getdate):
        """Test academic year on April 1st (boundary condition)"""
        mock_getdate.return_value = date(2025, 4, 1)  # April 1st
        
        result = get_current_academic_year_backend()
        
        assert result == "2025-26"
        mock_log.assert_called()
        log_call = mock_log.call_args[0]
        assert "Current academic year determined: 2025-26" in log_call[0]

    @patch('frappe.utils.getdate')
    @patch('frappe.log_error')
    def test_get_current_academic_year_march_last(self, mock_log, mock_getdate):
        """Test academic year on March 31st (boundary condition)"""
        mock_getdate.return_value = date(2025, 3, 31)  # March 31st
        
        result = get_current_academic_year_backend()
        
        assert result == "2024-25"
        mock_log.assert_called()

    @patch('frappe.utils.getdate')
    @patch('frappe.log_error')
    def test_get_current_academic_year_exception(self, mock_log, mock_getdate):
        """Test academic year calculation with exception"""
        mock_getdate.side_effect = Exception("Date calculation error")
        
        result = get_current_academic_year_backend()
        
        assert result is None
        mock_log.assert_called()
        error_call = mock_log.call_args[0]
        assert "Error calculating academic year" in error_call[0]


class TestCompleteCourseLevelMapping:
    """Complete coverage for course level mapping"""

    @patch('tap_lms.backend_onboarding.determine_student_type_backend')
    @patch('tap_lms.backend_onboarding.get_current_academic_year_backend')
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    @patch('tap_lms.api.get_course_level')
    def test_get_course_level_mapping_complete_flow(self, mock_get_course, mock_log, mock_get_all, 
                                                   mock_academic_year, mock_student_type):
        """Test complete course level mapping flow"""
        mock_student_type.return_value = "New"
        mock_academic_year.return_value = "2025-26"
        
        # Test current year mapping found
        mock_get_all.return_value = [
            {
                'assigned_course_level': 'CL001',
                'mapping_name': 'Math Grade 5 New 2025-26'
            }
        ]
        
        result = get_course_level_with_mapping_backend("Math", "5", "9876543210", "John Doe", False)
        
        assert result == "CL001"
        mock_log.assert_called()
        # Verify logging calls
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("Course level mapping lookup" in log for log in log_calls)
        assert any("Found mapping" in log for log in log_calls)

    @patch('tap_lms.backend_onboarding.determine_student_type_backend')
    @patch('tap_lms.backend_onboarding.get_current_academic_year_backend')
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    @patch('tap_lms.api.get_course_level')
    def test_get_course_level_mapping_fallback_chain(self, mock_get_course, mock_log, mock_get_all,
                                                    mock_academic_year, mock_student_type):
        """Test complete fallback chain"""
        mock_student_type.return_value = "Old"
        mock_academic_year.return_value = "2025-26"
        mock_get_course.return_value = "CL_FALLBACK"
        
        # No current year mapping, no flexible mapping
        mock_get_all.side_effect = [[], []]
        
        result = get_course_level_with_mapping_backend("Math", "5", "9876543210", "John Doe", True)
        
        assert result == "CL_FALLBACK"
        mock_get_course.assert_called_once_with("Math", "5", True)
        mock_log.assert_called()
        # Verify fallback log message
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("No mapping found" in log and "Stage Grades fallback" in log for log in log_calls)

    @patch('tap_lms.backend_onboarding.determine_student_type_backend')
    @patch('frappe.log_error')
    @patch('tap_lms.api.get_course_level')
    def test_get_course_level_mapping_exception_handling(self, mock_get_course, mock_log, mock_student_type):
        """Test exception handling in course level mapping"""
        mock_student_type.side_effect = Exception("Student type error")
        mock_get_course.return_value = "CL_ERROR_FALLBACK"
        
        result = get_course_level_with_mapping_backend("Math", "5", "9876543210", "John Doe", False)
        
        assert result == "CL_ERROR_FALLBACK"
        mock_log.assert_called()
        error_call = mock_log.call_args[0]
        assert "Error in course level mapping" in error_call[0]


class TestCompleteEnrollmentValidation:
    """Complete coverage for enrollment validation"""

    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    @patch('frappe.log_error')
    def test_validate_enrollment_data_mixed_valid_invalid(self, mock_log, mock_exists, mock_sql):
        """Test validation with mixed valid and invalid enrollments"""
        # Mock enrollment data with mix of valid/invalid
        mock_sql.return_value = [
            {
                'student_id': 'STU001',
                'enrollment_id': 'ENR001',
                'course': 'VALID_COURSE',
                'batch': 'BT001',
                'grade': '5'
            },
            {
                'student_id': 'STU001',
                'enrollment_id': 'ENR002',
                'course': 'INVALID_COURSE',
                'batch': 'BT002',
                'grade': '6'
            },
            {
                'student_id': 'STU001',
                'enrollment_id': 'ENR003',
                'course': 'ANOTHER_VALID',
                'batch': 'BT003',
                'grade': '7'
            }
        ]
        
        # Mock course existence - first and third exist, second doesn't
        mock_exists.side_effect = [True, False, True]
        
        result = validate_enrollment_data("John Doe", "9876543210")
        
        assert result['total_enrollments'] == 3
        assert result['valid_enrollments'] == 2
        assert result['broken_enrollments'] == 1
        assert len(result['broken_details']) == 1
        assert result['broken_details'][0]['invalid_course'] == 'INVALID_COURSE'
        
        # Verify logging of broken data
        mock_log.assert_called()
        log_call = mock_log.call_args[0]
        assert "Detected broken course_level link" in log_call[0]

    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_validate_enrollment_data_invalid_phone(self, mock_log, mock_sql):
        """Test validation with invalid phone format"""
        result = validate_enrollment_data("John Doe", "invalid_phone")
        
        assert result == {"error": "Invalid phone number format"}
        mock_sql.assert_not_called()

    @patch('frappe.db.sql')
    @patch('frappe.log_error')
    def test_validate_enrollment_data_exception(self, mock_log, mock_sql):
        """Test validation with database exception"""
        mock_sql.side_effect = Exception("Database connection failed")
        
        result = validate_enrollment_data("John Doe", "9876543210")
        
        assert 'error' in result
        assert "Database connection failed" in str(result['error'])
        mock_log.assert_called_once()


class TestCompleteGlificIntegration:
    """Complete coverage for Glific integration"""

    @patch('tap_lms.backend_onboarding.format_phone_number')
    @patch('frappe.get_value')
    @patch('tap_lms.glific_integration.get_contact_by_phone')
    def test_process_glific_contact_invalid_phone(self, mock_get_contact, mock_get_value, mock_format_phone):
        """Test process_glific_contact with invalid phone"""
        student = Mock()
        student.phone = "invalid_phone"
        student.student_name = "John Doe"
        
        mock_format_phone.return_value = None
        
        with pytest.raises(ValueError, match="Invalid phone number format"):
            process_glific_contact(student, None)

    @patch('tap_lms.backend_onboarding.format_phone_number')
    @patch('frappe.get_value')
    @patch('tap_lms.glific_integration.get_contact_by_phone')
    @patch('tap_lms.glific_integration.add_contact_to_group')
    @patch('tap_lms.glific_integration.update_contact_fields')
    @patch('frappe.log_error')
    def test_process_glific_contact_existing_complete(self, mock_log, mock_update_fields, 
                                                    mock_add_to_group, mock_get_contact, 
                                                    mock_get_value, mock_format_phone):
        """Test complete existing contact processing with all fields"""
        student = Mock()
        student.phone = "9876543210"
        student.student_name = "John Doe"
        student.school = "SCH001"
        student.batch = "BT001"
        student.language = "EN"
        student.course_vertical = "Math"
        student.grade = "5"
        
        glific_group = {"group_id": "GG001"}
        
        mock_format_phone.return_value = "919876543210"
        existing_contact = {"id": "GC001", "name": "John Doe"}
        mock_get_contact.return_value = existing_contact
        
        # Mock all get_value calls for field updates
        mock_get_value.side_effect = [
            "Test School",      # school name
            "BT001",           # batch name  
            1,                 # language_id
            "Basic Math",      # course_level_name
            "Mathematics"      # course_vertical_name
        ]
        
        # Mock successful field update
        mock_update_fields.return_value = {"success": True}
        
        with patch('builtins.print') as mock_print:
            result = process_glific_contact(student, glific_group, "CL001")
        
        assert result == existing_contact
        mock_add_to_group.assert_called_once_with("GC001", "GG001")
        mock_update_fields.assert_called_once()
        
        # Verify update_contact_fields called with correct fields
        update_call_args = mock_update_fields.call_args[0]
        fields_updated = update_call_args[1]
        
        expected_fields = {
            "buddy_name": "John Doe",
            "batch_id": "BT001",
            "school": "Test School",
            "course_level": "Basic Math",
            "course": "Mathematics",
            "grade": "5"
        }
        assert fields_updated == expected_fields
        
        # Verify print statements
        mock_print.assert_called()
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Updated John Doe" in call for call in print_calls)

    @patch('tap_lms.backend_onboarding.format_phone_number')
    @patch('frappe.get_value')
    @patch('tap_lms.glific_integration.get_contact_by_phone')
    @patch('tap_lms.glific_integration.add_student_to_glific_for_onboarding')
    @patch('frappe.log_error')
    def test_process_glific_contact_new_contact_creation(self, mock_log, mock_add_student, 
                                                       mock_get_contact, mock_get_value, mock_format_phone):
        """Test new contact creation in Glific"""
        student = Mock()
        student.phone = "9876543210"
        student.student_name = "Jane Doe"
        student.school = "SCH001"
        student.batch = "BT001"
        student.language = "EN"
        student.course_vertical = "Science"
        student.grade = "6"
        
        glific_group = {"group_id": "GG001"}
        
        mock_format_phone.return_value = "919876543210"
        mock_get_contact.return_value = None  # No existing contact
        
        # Mock get_value calls
        mock_get_value.side_effect = [
            "Test School",      # school name
            "BT001",           # batch name
            2,                 # language_id
            "Basic Science",   # course_level_name
            "Science"          # course_vertical_name
        ]
        
        # Mock successful contact creation
        new_contact = {"id": "GC002", "name": "Jane Doe"}
        mock_add_student.return_value = new_contact
        
        with patch('builtins.print') as mock_print:
            result = process_glific_contact(student, glific_group, "CL002")
        
        assert result == new_contact
        mock_add_student.assert_called_once_with(
            "Jane Doe",
            "919876543210", 
            "Test School",
            "BT001",
            "GG001",
            2,
            "Basic Science",
            "Science",
            "6"
        )
        mock_print.assert_called()

    @patch('tap_lms.backend_onboarding.format_phone_number')
    @patch('frappe.get_value')
    @patch('tap_lms.glific_integration.get_contact_by_phone')
    @patch('tap_lms.glific_integration.add_student_to_glific_for_onboarding')
    @patch('frappe.log_error')
    def test_process_glific_contact_creation_failure(self, mock_log, mock_add_student,
                                                   mock_get_contact, mock_get_value, mock_format_phone):
        """Test failed contact creation in Glific"""
        student = Mock()
        student.phone = "9876543210"
        student.student_name = "Failed User"
        student.school = "SCH001"
        student.batch = "BT001"
        student.language = "EN"
        student.course_vertical = "Math"
        student.grade = "5"
        
        glific_group = {"group_id": "GG001"}
        
        mock_format_phone.return_value = "919876543210"
        mock_get_contact.return_value = None
        mock_get_value.side_effect = ["Test School", "BT001", 1, "Basic Math", "Mathematics"]
        
        # Mock failed contact creation - no 'id' in response
        mock_add_student.return_value = {"error": "Failed to create"}
        
        result = process_glific_contact(student, glific_group, "CL001")
        
        assert result == {"error": "Failed to create"}
        mock_log.assert_called()
        log_call = mock_log.call_args[0]
        assert "Failed to create Glific contact for Failed User" in log_call[0]

    def test_format_phone_number_function(self):
        """Test format_phone_number utility function"""
        with patch('tap_lms.backend_onboarding.normalize_phone_number') as mock_normalize:
            mock_normalize.return_value = ("919876543210", "9876543210")
            
            result = format_phone_number("9876543210")
            
            assert result == "919876543210"
            mock_normalize.assert_called_once_with("9876543210")

    @patch('tap_lms.backend_onboarding.format_phone_number')
    def test_process_glific_contact_no_course_level_provided(self, mock_format_phone):
        """Test process_glific_contact without course level"""
        student = Mock()
        student.phone = "9876543210"
        student.student_name = "No Course Student"
        student.school = "SCH001"
        student.batch = "BT001"
        student.language = "EN"
        student.course_vertical = "Math"
        student.grade = "5"
        
        mock_format_phone.return_value = "919876543210"
        
        with patch('frappe.get_value') as mock_get_value, \
             patch('tap_lms.glific_integration.get_contact_by_phone') as mock_get_contact, \
             patch('builtins.print') as mock_print:
            
            mock_get_contact.return_value = None
            mock_get_value.side_effect = ["Test School", "BT001", 1, "", "Mathematics"]
            
            with patch('tap_lms.glific_integration.add_student_to_glific_for_onboarding') as mock_add_student:
                mock_add_student.return_value = {"id": "GC003"}
                
                result = process_glific_contact(student, None, None)  # No course level
        
        # Verify print statement about no course level
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("No course level provided" in call for call in print_calls)


class TestCompleteStudentRecordProcessing:
    """Complete coverage for student record processing"""

    @patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name')
    @patch('frappe.new_doc')
    @patch('frappe.db.exists')
    @patch('frappe.utils.nowdate')
    @patch('frappe.utils.now')
    @patch('frappe.log_error')
    def test_process_student_record_new_student_complete(self, mock_log, mock_now, mock_nowdate,
                                                       mock_exists, mock_new_doc, mock_find_student):
        """Test complete new student record creation with all features"""
        mock_find_student.return_value = None
        mock_nowdate.return_value = "2025-01-15"
        mock_now.return_value = "2025-01-15 10:30:00"
        
        # Mock new student document
        mock_student_doc = Mock()
        mock_student_doc.name = "STU001"
        mock_student_doc.glific_id = None
        mock_student_doc.append = Mock()
        mock_student_doc.insert = Mock()
        mock_new_doc.return_value = mock_student_doc
        
        # Mock backend student
        backend_student = Mock()
        backend_student.phone = "9876543210"
        backend_student.student_name = "John Doe"
        backend_student.gender = "Male"
        backend_student.school = "SCH001"
        backend_student.grade = "5"
        backend_student.language = "EN"
        backend_student.batch = "BT001"
        backend_student.course_vertical = "Math"
        backend_student.batch_skeyword = "MATH5"
        
        # Mock Glific contact
        glific_contact = {"id": "GC001"}
        
        # Mock database operations - LearningState and EngagementState don't exist
        mock_exists.side_effect = [False, False]  
        
        with patch('frappe.new_doc') as mock_new_doc_states:
            # Mock state document creation
            mock_learning_state = Mock()
            mock_learning_state.insert = Mock()
            mock_engagement_state = Mock()
            mock_engagement_state.insert = Mock()
            mock_stage_progress = Mock()
            mock_stage_progress.insert = Mock()
            
            mock_new_doc_states.side_effect = [mock_learning_state, mock_engagement_state, mock_stage_progress]
            
            result = process_student_record(
                backend_student,
                glific_contact,
                "BSO001",
                "STAGE001", 
                "CL001"
            )
        
        assert result == mock_student_doc
        
        # Verify student creation with all fields
        assert mock_student_doc.name1 == "John Doe"
        assert mock_student_doc.phone == "919876543210"  # Should be normalized
        assert mock_student_doc.gender == "Male"
        assert mock_student_doc.school_id == "SCH001"
        assert mock_student_doc.grade == "5"
        assert mock_student_doc.language == "EN"
        assert mock_student_doc.glific_id == "GC001"
        
        # Verify enrollment creation
        mock_student_doc.append.assert_called()
        enrollment_call = mock_student_doc.append.call_args[0]
        assert enrollment_call[0] == "enrollment"
        enrollment_data = enrollment_call[1]
        assert enrollment_data["batch"] == "BT001"
        assert enrollment_data["grade"] == "5"
        assert enrollment_data["course"] == "CL001"
        
        # Verify state creation
        mock_learning_state.insert.assert_called_once()
        mock_engagement_state.insert.assert_called_once()
        mock_stage_progress.insert.assert_called_once()
        
        # Verify logging
        mock_log.assert_called()

    @patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name')
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_process_student_record_existing_student_grade_update(self, mock_log, mock_get_doc, mock_find_student):
        """Test existing student with grade update"""
        existing_student_data = {
            'name': 'STU001',
            'phone': '9876543210',
            'name1': 'John Doe'
        }
        mock_find_student.return_value = existing_student_data
        
        # Mock existing student document
        mock_existing_student = Mock()
        mock_existing_student.name = "STU001"
        mock_existing_student.phone = "9876543210"
        mock_existing_student.grade = "4"  # Old grade
        mock_existing_student.school_id = "SCH001"
        mock_existing_student.language = "EN"
        mock_existing_student.gender = "Male"
        mock_existing_student.glific_id = None
        mock_existing_student.append = Mock()
        mock_existing_student.save = Mock()
        mock_get_doc.return_value = mock_existing_student
        
        # Mock backend student with new grade
        backend_student = Mock()
        backend_student.phone = "9876543210"
        backend_student.student_name = "John Doe"
        backend_student.gender = "Male"
        backend_student.school = "SCH001"
        backend_student.grade = "5"  # New grade
        backend_student.language = "EN"
        backend_student.batch = "BT001"
        backend_student.course_vertical = "Math"
        backend_student.batch_skeyword = "MATH5"
        
        glific_contact = {"id": "GC001"}
        
        result = process_student_record(
            backend_student,
            glific_contact,
            "BSO001",
            "STAGE001",
            "CL001"
        )
        
        assert result == mock_existing_student
        assert mock_existing_student.grade == "5"  # Should be updated
        assert mock_existing_student.glific_id == "GC001"  # Should be added
        mock_existing_student.save.assert_called_once()
        
        # Verify enrollment was added
        mock_existing_student.append.assert_called()
        
        # Verify grade update logging
        mock_log.assert_called()
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("Grade update" in log for log in log_calls)

    @patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name')
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_process_student_record_phone_format_update(self, mock_log, mock_get_doc, mock_find_student):
        """Test existing student with phone format update"""
        existing_student_data = {
            'name': 'STU001',
            'phone': '9876543210',  # 10-digit format
            'name1': 'John Doe'
        }
        mock_find_student.return_value = existing_student_data
        
        # Mock existing student document with 10-digit phone
        mock_existing_student = Mock()
        mock_existing_student.name = "STU001"
        mock_existing_student.phone = "9876543210"  # Old 10-digit format
        mock_existing_student.grade = "5"
        mock_existing_student.school_id = "SCH001"
        mock_existing_student.language = "EN"
        mock_existing_student.gender = "Male"
        mock_existing_student.glific_id = None
        mock_existing_student.append = Mock()
        mock_existing_student.save = Mock()
        mock_get_doc.return_value = mock_existing_student
        
        backend_student = Mock()
        backend_student.phone = "919876543210"  # 12-digit format
        backend_student.student_name = "John Doe"
        backend_student.gender = "Male"
        backend_student.school = "SCH001"
        backend_student.grade = "5"
        backend_student.language = "EN"
        backend_student.batch = "BT001"
        backend_student.course_vertical = "Math"
        backend_student.batch_skeyword = "MATH5"
        
        result = process_student_record(
            backend_student,
            None,
            "BSO001",
            "STAGE001",
            None
        )
        
        # Verify phone was updated to 12-digit format
        assert mock_existing_student.phone == "919876543210"
        
        # Verify phone update logging
        mock_log.assert_called()
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("Updated phone format" in log for log in log_calls)

    @patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name')
    @patch('frappe.new_doc')
    @patch('frappe.log_error')
    def test_process_student_record_course_level_error_handling(self, mock_log, mock_new_doc, mock_find_student):
        """Test course level selection error handling"""
        mock_find_student.return_value = None
        
        # Mock new student document
        mock_student_doc = Mock()
        mock_student_doc.name = "STU001"
        mock_student_doc.glific_id = None
        mock_student_doc.append = Mock()
        mock_student_doc.insert = Mock()
        mock_new_doc.return_value = mock_student_doc
        
        backend_student = Mock()
        backend_student.phone = "9876543210"
        backend_student.student_name = "John Doe"
        backend_student.gender = "Male"
        backend_student.school = "SCH001"
        backend_student.grade = "5"
        backend_student.language = "EN"
        backend_student.batch = "BT001"
        backend_student.course_vertical = "Math"
        backend_student.batch_skeyword = "MATH5"
        
        with patch('frappe.get_all') as mock_get_all, \
             patch('tap_lms.backend_onboarding.get_course_level_with_validation_backend') as mock_get_course, \
             patch('tap_lms.api.get_course_level') as mock_fallback_course, \
             patch('frappe.db.exists') as mock_exists:
            
            # Mock batch onboarding data
            mock_get_all.return_value = [{'name': 'BO001', 'kit_less': False}]
            
            # Mock course level selection failure, then fallback failure
            mock_get_course.side_effect = Exception("Course selection error")
            mock_fallback_course.side_effect = Exception("Fallback error too")
            
            # Mock state creation not existing
            mock_exists.return_value = False
            
            result = process_student_record(
                backend_student,
                None,
                "BSO001",
                "STAGE001",
                None  # No pre-determined course level
            )
        
        # Should still create student successfully
        assert result == mock_student_doc
        mock_student_doc.insert.assert_called_once()
        
        # Verify error logging for course selection
        mock_log.assert_called()
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("Course selection error" in log for log in log_calls)
        assert any("Fallback course selection also failed" in log for log in log_calls)

    def test_update_backend_student_status_success_with_glific(self):
        """Test updating backend student status to success with Glific ID"""
        backend_student = Mock()
        backend_student.processing_notes = ""
        backend_student.save = Mock()
        
        # Mock student document with Glific ID
        student_doc = Mock()
        student_doc.name = "STU001"
        student_doc.glific_id = "GC001"
        
        # Mock the hasattr check for glific_id field
        backend_student.glific_id = None  # Field exists but is None
        
        update_backend_student_status(backend_student, "Success", student_doc)
        
        assert backend_student.processing_status == "Success"
        assert backend_student.student_id == "STU001"
        assert backend_student.glific_id == "GC001"  # Should be updated
        backend_student.save.assert_called_once()

    def test_update_backend_student_status_failed_with_long_error(self):
        """Test updating backend student status with long error message"""
        backend_student = Mock()
        backend_student.processing_notes = ""
        backend_student.save = Mock()
        
        # Mock the hasattr check and field metadata
        with patch('frappe.get_meta') as mock_get_meta:
            mock_meta = Mock()
            mock_field = Mock()
            mock_field.length = 50  # Short length for testing truncation
            mock_meta.get_field.return_value = mock_field
            mock_get_meta.return_value = mock_meta
            
            long_error = "This is a very long error message that should be truncated because it exceeds the maximum field length"
            
            update_backend_student_status(backend_student, "Failed", error=long_error)
        
        assert backend_student.processing_status == "Failed"
        assert len(backend_student.processing_notes) == 50  # Should be truncated
        assert backend_student.processing_notes == long_error[:50]
        backend_student.save.assert_called_once()


class TestCompleteBatchProcessing:
    """Complete coverage for batch processing"""

    @patch('frappe.get_doc')
    @patch('frappe.enqueue')
    def test_process_batch_background_job_boolean_conversion(self, mock_enqueue, mock_get_doc):
        """Test background job parameter conversion from string"""
        mock_batch = Mock()
        mock_batch.status = "Draft"
        mock_batch.save = Mock()
        mock_get_doc.return_value = mock_batch
        
        mock_job = Mock()
        mock_job.id = "JOB001"
        mock_enqueue.return_value = mock_job
        
        # Test string to boolean conversion
        result = process_batch("BSO001", use_background_job="true")
        
        assert result["job_id"] == "JOB001"
        mock_enqueue.assert_called_once()

    @patch('frappe.get_doc')
    @patch('frappe.enqueue')
    def test_process_batch_background_job_already_boolean(self, mock_enqueue, mock_get_doc):
        """Test background job parameter as boolean"""
        mock_batch = Mock()
        mock_batch.status = "Draft"
        mock_batch.save = Mock()
        mock_get_doc.return_value = mock_batch
        
        mock_job = Mock()
        mock_job.id = "JOB002"
        mock_enqueue.return_value = mock_job
        
        # Test boolean parameter
        result = process_batch("BSO001", use_background_job=True)
        
        assert result["job_id"] == "JOB002"
        mock_enqueue.assert_called_once_with(
            process_batch_job,
            queue='long',
            timeout=1800,
            job_name="student_onboarding_BSO001",
            batch_id="BSO001"
        )

    @patch('frappe.db.commit')
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    @patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch')
    @patch('tap_lms.backend_onboarding.get_initial_stage')
    def test_process_batch_job_glific_group_creation_error(self, mock_get_stage, mock_create_group,
                                                          mock_log, mock_get_all, mock_get_doc, mock_commit):
        """Test batch job with Glific group creation error"""
        mock_batch = Mock()
        mock_batch.status = "Processing"
        mock_batch.save = Mock()
        mock_get_doc.return_value = mock_batch
        
        # Mock students
        mock_get_all.return_value = []  # No students to process
        
        # Mock Glific group creation failure
        mock_create_group.side_effect = Exception("Glific API error")
        mock_get_stage.return_value = "STAGE001"
        
        result = process_batch_job("BSO001")
        
        # Should continue processing even with Glific error
        assert result["success_count"] == 0
        assert result["failure_count"] == 0
        mock_log.assert_called()
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("Error creating Glific group" in log for log in log_calls)

    @patch('frappe.db')
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    @patch('tap_lms.backend_onboarding.update_job_progress')
    def test_process_batch_job_commit_intervals(self, mock_update_progress, mock_log, 
                                              mock_get_all, mock_get_doc, mock_db):
        """Test batch job commit intervals"""
        mock_batch = Mock()
        mock_batch.status = "Processing"
        mock_batch.save = Mock()
        
        # Create 25 students to test commit interval (every 10 students)
        students = [{'name': f'BS{i:03d}', 'batch_skeyword': 'MATH5'} for i in range(25)]
        
        mock_get_all.side_effect = [
            students,  # Students
            [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]  # Batch onboarding
        ]
        
        # Mock successful student processing
        def get_doc_side_effect(doctype, name):
            if doctype == "Backend Student Onboarding":
                return mock_batch
            else:  # Backend Students
                mock_student = Mock()
                mock_student.name = name
                mock_student.student_name = f"Student {name}"
                mock_student.phone = f"98765432{name[-2:]}"
                mock_student.batch_skeyword = "MATH5"
                mock_student.save = Mock()
                return mock_student
        
        mock_get_doc.side_effect = get_doc_side_effect
        mock_db.count.return_value = 25
        mock_db.commit = Mock()
        
        with patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \
             patch('tap_lms.backend_onboarding.get_initial_stage') as mock_get_stage, \
             patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \
             patch('tap_lms.backend_onboarding.process_student_record') as mock_process_student, \
             patch('tap_lms.backend_onboarding.update_backend_student_status') as mock_update_status:
            
            mock_create_group.return_value = {"group_id": "GG001"}
            mock_get_stage.return_value = "STAGE001"
            mock_process_glific.return_value = {"id": "GC001"}
            
            mock_student_doc = Mock()
            mock_student_doc.name = "STU001"
            mock_process_student.return_value = mock_student_doc
            
            result = process_batch_job("BSO001")
        
        # Should have committed multiple times (every 10 students + final commit)
        assert mock_db.commit.call_count >= 3  # At least 10, 20, and final commits
        assert result["success_count"] == 25

    @patch('frappe.db')
    @patch('frappe.get_doc') 
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_process_batch_job_final_status_update_error(self, mock_log, mock_get_all, mock_get_doc, mock_db):
        """Test batch job with final status update error"""
        mock_batch = Mock()
        mock_batch.status = "Processing"
        mock_batch.save.side_effect = Exception("Save error")  # Error on final save
        
        mock_get_all.return_value = []  # No students
        mock_get_doc.return_value = mock_batch
        mock_db.count.return_value = 0
        mock_db.commit = Mock()
        
        with patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \
             patch('tap_lms.backend_onboarding.get_initial_stage') as mock_get_stage:
            
            mock_create_group.return_value = {"group_id": "GG001"}
            mock_get_stage.return_value = "STAGE001"
            
            result = process_batch_job("BSO001")
        
        # Should continue and return results despite status update error
        assert result["success_count"] == 0
        assert result["failure_count"] == 0
        mock_log.assert_called()
        log_calls = [call[0][0] for call in mock_log.call_args_list]
        assert any("Error updating batch status" in log for log in log_calls)

    def test_update_job_progress_basic(self):
        """Test job progress update"""
        with patch('frappe.publish_progress') as mock_publish:
            update_job_progress(5, 10)
            
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args[1]  # Get keyword arguments
            assert call_args['percent'] == 60  # (5+1) * 100 / 10
            assert "Processing student 6 of 10" in call_args['description']

    def test_update_job_progress_exception_fallback(self):
        """Test job progress update with exception fallback"""
        with patch('frappe.publish_progress') as mock_publish, \
             patch('frappe.db.commit') as mock_commit, \
             patch('builtins.print') as mock_print:
            
            mock_publish.side_effect = Exception("Progress update failed")
            
            update_job_progress(9, 10)  # Should trigger print on 10th item
            
            # Should fallback to basic print approach
            mock_print.assert_called_once_with("Processed 10 of 10 students")
            mock_commit.assert_called_once()

    def test_update_job_progress_zero_total(self):
        """Test job progress update with zero total"""
        with patch('frappe.publish_progress') as mock_publish:
            update_job_progress(5, 0)  # Zero total
            
            mock_publish.assert_not_called()  # Should not try to update progress


class TestCompleteJobStatus:
    """Complete coverage for job status tracking"""

    @patch('frappe.db')
    @patch('frappe.logger')
    def test_get_job_status_multiple_tables(self, mock_logger, mock_db):
        """Test job status checking multiple table names"""
        mock_db.table_exists.side_effect = [False, True]  # First table doesn't exist, second does
        mock_db.get_value.return_value = {
            'status': 'started',
            'progress_data': '{"percent": 25}',
            'result': None
        }
        
        result = get_job_status("JOB001")
        
        assert result['status'] == 'started'
        assert 'progress' in result
        assert mock_db.table_exists.call_count == 2


# # conftest.py - Pytest configuration and fixtures
# import pytest
# import sys
# import os
# from unittest.mock import Mock, patch

# # Add the project root to Python path
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# @pytest.fixture(scope="session", autouse=True)
# def setup_frappe_environment():
#     """Setup mock Frappe environment for all tests"""
#     # Mock frappe module
#     frappe_mock = Mock()
    
#     # Mock common frappe functions
#     frappe_mock.whitelist = lambda func: func
#     frappe_mock.log_error = Mock()
#     frappe_mock.logger = Mock()
#     frappe_mock.get_all = Mock()
#     frappe_mock.get_doc = Mock()
#     frappe_mock.new_doc = Mock()
#     frappe_mock.get_value = Mock()
#     frappe_mock.delete_doc = Mock()
#     frappe_mock.enqueue = Mock()
#     frappe_mock.publish_progress = Mock()
    
#     # Mock frappe.db
#     frappe_mock.db = Mock()
#     frappe_mock.db.sql = Mock()
#     frappe_mock.db.exists = Mock()
#     frappe_mock.db.get_value = Mock()
#     frappe_mock.db.set_value = Mock()
#     frappe_mock.db.commit = Mock()
#     frappe_mock.db.rollback = Mock()
#     frappe_mock.db.count = Mock()
#     frappe_mock.db.table_exists = Mock()
    
#     # Mock frappe.utils
#     frappe_mock.utils = Mock()
#     frappe_mock.utils.nowdate = Mock(return_value="2025-01-15")
#     frappe_mock.utils.nowtime = Mock(return_value="10:30:00")
#     frappe_mock.utils.now = Mock(return_value="2025-01-15 10:30:00")
#     frappe_mock.utils.getdate = Mock()
    
#     # Mock frappe.get_meta
#     frappe_mock.get_meta = Mock()
    
#     # Mock frappe translation
#     frappe_mock._ = lambda x: x
    
#     # Add to sys.modules
#     sys.modules['frappe'] = frappe_mock
#     sys.modules['frappe.utils'] = frappe_mock.utils
    
#     # Mock tap_lms modules
#     tap_lms_mock = Mock()
#     tap_lms_api_mock = Mock()
#     tap_lms_glific_mock = Mock()
    
#     # Mock specific functions from tap_lms.api
#     tap_lms_api_mock.get_course_level = Mock(return_value="CL001")
    
#     # Mock specific functions from tap_lms.glific_integration
#     tap_lms_glific_mock.create_or_get_glific_group_for_batch = Mock()
#     tap_lms_glific_mock.add_student_to_glific_for_onboarding = Mock()
#     tap_lms_glific_mock.get_contact_by_phone = Mock()
#     tap_lms_glific_mock.add_contact_to_group = Mock()
#     tap_lms_glific_mock.update_contact_fields = Mock()
    
#     sys.modules['tap_lms'] = tap_lms_mock
#     sys.modules['tap_lms.api'] = tap_lms_api_mock
#     sys.modules['tap_lms.glific_integration'] = tap_lms_glific_mock
    
#     yield frappe_mock
    
#     # Cleanup
#     if 'frappe' in sys.modules:
#         del sys.modules['frappe']
#     if 'frappe.utils' in sys.modules:
#         del sys.modules['frappe.utils']
#     if 'tap_lms' in sys.modules:
#         del sys.modules['tap_lms']
#     if 'tap_lms.api' in sys.modules:
#         del sys.modules['tap_lms.api']
#     if 'tap_lms.glific_integration' in sys.modules:
#         del sys.modules['tap_lms.glific_integration']

# @pytest.fixture
# def sample_backend_student():
#     """Sample backend student data for testing"""
#     student = Mock()
#     student.name = "BS001"
#     student.student_name = "John Doe"
#     student.phone = "9876543210"
#     student.gender = "Male"
#     student.batch = "BT001"
#     student.course_vertical = "Math"
#     student.grade = "5"
#     student.school = "SCH001"
#     student.language = "EN"
#     student.processing_status = "Pending"
#     student.student_id = None
#     student.batch_skeyword = "MATH5"
#     return student

# @pytest.fixture
# def sample_glific_contact():
#     """Sample Glific contact data for testing"""
#     return {
#         "id": "GC001",
#         "name": "John Doe",
#         "phone": "919876543210"
#     }

# @pytest.fixture
# def sample_batch():
#     """Sample batch data for testing"""
#     batch = Mock()
#     batch.name = "BSO001"
#     batch.set_name = "Test Batch Set"
#     batch.upload_date = "2025-01-15"
#     batch.uploaded_by = "admin"
#     batch.student_count = 10
#     batch.processed_student_count = 0
#     batch.status = "Draft"
#     return batch

# # pytest.ini content (create as separate file)
# PYTEST_INI_CONTENT = """[tool:pytest]
# testpaths = tests
# python_files = test_*.py *_test.py
# python_classes = Test*
# python_functions = test_*
# addopts = 
#     -v
#     --tb=short
#     --strict-markers
#     --disable-warnings
#     --color=yes
# markers =
#     unit: Unit tests
#     integration: Integration tests
#     slow: Slow running tests
#     glific: Tests involving Glific integration
#     database: Tests requiring database operations
# """

# # requirements-test.txt content
# REQUIREMENTS_TEST_CONTENT = """pytest>=7.0.0
# pytest-mock>=3.10.0
# pytest-cov>=4.0.0
# pytest-xdist>=3.0.0
# coverage>=7.0.0
# mock>=4.0.0
# """

# # test_integration.py - Integration tests
# INTEGRATION_TESTS_CONTENT = '''import pytest
# from unittest.mock import Mock, patch, call
# import json

# class TestEndToEndIntegration:
#     """End-to-end integration tests"""
    
#     @pytest.fixture
#     def complete_batch_setup(self, sample_batch, sample_backend_student, sample_glific_contact):
#         """Complete batch setup for integration testing"""
#         return {
#             'batch': sample_batch,
#             'students': [sample_backend_student],
#             'glific_contact': sample_glific_contact
#         }
    
#     def test_complete_student_onboarding_flow(self, complete_batch_setup):
#         """Test complete student onboarding flow from batch to student creation"""
#         from tap_lms.backend_onboarding import process_batch_job
        
#         with patch('frappe.db') as mock_db, \\
#              patch('frappe.get_doc') as mock_get_doc, \\
#              patch('frappe.get_all') as mock_get_all, \\
#              patch('frappe.new_doc') as mock_new_doc, \\
#              patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
#              patch('tap_lms.backend_onboarding.get_initial_stage') as mock_get_stage, \\
#              patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
#              patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student, \\
#              patch('tap_lms.backend_onboarding.get_course_level_with_validation_backend') as mock_get_course:
            
#             # Setup mocks
#             batch = complete_batch_setup['batch']
#             student = complete_batch_setup['students'][0]
            
#             mock_get_doc.side_effect = [batch, student]
#             mock_get_all.side_effect = [
#                 [{'name': 'BS001', 'batch_skeyword': 'MATH5'}],  # Students
#                 [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]  # Batch onboarding
#             ]
            
#             mock_create_group.return_value = {"group_id": "GG001"}
#             mock_get_stage.return_value = "STAGE001"
#             mock_process_glific.return_value = complete_batch_setup['glific_contact']
#             mock_find_student.return_value = None  # New student
#             mock_get_course.return_value = "CL001"
            
#             # Mock new student creation
#             mock_student_doc = Mock()
#             mock_student_doc.name = "STU001"
#             mock_student_doc.glific_id = None
#             mock_student_doc.append = Mock()
#             mock_student_doc.insert = Mock()
#             mock_new_doc.return_value = mock_student_doc
            
#             # Mock database operations
#             mock_db.exists.return_value = False  # LearningState and EngagementState don't exist
#             mock_db.commit = Mock()
#             mock_db.count.return_value = 1
            
#             # Execute
#             result = process_batch_job("BSO001")
            
#             # Verify results
#             assert result['success_count'] == 1
#             assert result['failure_count'] == 0
#             assert len(result['results']['success']) == 1
            
#             # Verify student was created
#             mock_new_doc.assert_called_with("Student")
#             mock_student_doc.insert.assert_called_once()
            
#             # Verify Glific integration
#             mock_process_glific.assert_called_once()
            
#             # Verify course level assignment
#             mock_get_course.assert_called_once()

#     def test_batch_processing_with_mixed_results(self, complete_batch_setup):
#         """Test batch processing with both successful and failed students"""
#         from tap_lms.backend_onboarding import process_batch_job
        
#         with patch('frappe.db') as mock_db, \\
#              patch('frappe.get_doc') as mock_get_doc, \\
#              patch('frappe.get_all') as mock_get_all, \\
#              patch('frappe.new_doc') as mock_new_doc, \\
#              patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
#              patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
#              patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student:
            
#             batch = complete_batch_setup['batch']
            
#             # Create two students - one will succeed, one will fail
#             student1 = Mock()
#             student1.name = "BS001"
#             student1.student_name = "John Doe"
#             student1.phone = "9876543210"
            
#             student2 = Mock()
#             student2.name = "BS002"
#             student2.student_name = "Jane Doe"
#             student2.phone = "9876543211"
            
#             mock_get_doc.side_effect = [batch, student1, student2]
#             mock_get_all.side_effect = [
#                 [{'name': 'BS001', 'batch_skeyword': 'MATH5'}, {'name': 'BS002', 'batch_skeyword': 'MATH5'}],
#                 [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]
#             ]
            
#             mock_create_group.return_value = {"group_id": "GG001"}
#             mock_find_student.return_value = None
            
#             # First student succeeds, second fails
#             mock_student_doc = Mock()
#             mock_student_doc.name = "STU001"
#             mock_student_doc.insert = Mock()
#             mock_new_doc.return_value = mock_student_doc
            
#             # Mock Glific success for first, failure for second
#             mock_process_glific.side_effect = [
#                 complete_batch_setup['glific_contact'],  # Success
#                 Exception("Glific API error")  # Failure
#             ]
            
#             mock_db.commit = Mock()
#             mock_db.rollback = Mock()
#             mock_db.count.return_value = 1
            
#             result = process_batch_job("BSO001")
            
#             assert result['success_count'] == 1
#             assert result['failure_count'] == 1


# class TestErrorRecoveryScenarios:
#     """Test error recovery and resilience scenarios"""
    
#     def test_database_connection_failure_recovery(self, sample_batch):
#         """Test recovery from database connection failures"""
#         from tap_lms.backend_onboarding import process_batch_job
        
#         with patch('frappe.db') as mock_db, \\
#              patch('frappe.get_doc') as mock_get_doc, \\
#              patch('frappe.get_all') as mock_get_all:
            
#             mock_get_doc.return_value = sample_batch
#             mock_get_all.return_value = []  # No students
            
#             # Simulate database connection failure
#             mock_db.commit.side_effect = Exception("Database connection lost")
#             mock_db.rollback = Mock()
            
#             with pytest.raises(Exception, match="Database connection lost"):
#                 process_batch_job("BSO001")
            
#             # Verify rollback was called
#             mock_db.rollback.assert_called()

#     def test_glific_api_unavailable_graceful_handling(self, sample_backend_student, sample_batch):
#         """Test graceful handling when Glific API is unavailable"""
#         from tap_lms.backend_onboarding import process_batch_job
        
#         with patch('frappe.db') as mock_db, \\
#              patch('frappe.get_doc') as mock_get_doc, \\
#              patch('frappe.get_all') as mock_get_all, \\
#              patch('frappe.new_doc') as mock_new_doc, \\
#              patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
#              patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
#              patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student:
            
#             mock_get_doc.side_effect = [sample_batch, sample_backend_student]
#             mock_get_all.side_effect = [
#                 [{'name': 'BS001', 'batch_skeyword': 'MATH5'}],
#                 [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]
#             ]
            
#             # Glific completely unavailable
#             mock_create_group.side_effect = Exception("Glific API unavailable")
#             mock_process_glific.return_value = None
#             mock_find_student.return_value = None
            
#             # Student creation should still succeed without Glific
#             mock_student_doc = Mock()
#             mock_student_doc.name = "STU001"
#             mock_student_doc.glific_id = None
#             mock_student_doc.insert = Mock()
#             mock_new_doc.return_value = mock_student_doc
            
#             mock_db.exists.return_value = False
#             mock_db.commit = Mock()
#             mock_db.count.return_value = 1
            
#             result = process_batch_job("BSO001")
            
#             # Should succeed even without Glific
#             assert result['success_count'] == 1
#             assert result['failure_count'] == 0

#     def test_partial_data_corruption_handling(self, sample_batch):
#         """Test handling of partially corrupted data"""
#         from tap_lms.backend_onboarding import validate_enrollment_data
        
#         with patch('frappe.db') as mock_db:
#             # Mock corrupted enrollment data
#             mock_db.sql.return_value = [
#                 {
#                     'student_id': 'STU001',
#                     'enrollment_id': 'ENR001',
#                     'course': None,  # Corrupted - NULL course
#                     'batch': 'BT001',
#                     'grade': '5'
#                 },
#                 {
#                     'student_id': 'STU001',
#                     'enrollment_id': 'ENR002',
#                     'course': 'INVALID_COURSE',  # Corrupted - invalid reference
#                     'batch': 'BT002',
#                     'grade': '6'
#                 }
#             ]
            
#             mock_db.exists.return_value = False  # Course doesn't exist
            
#             result = validate_enrollment_data("John Doe", "9876543210")
            
#             assert result['total_enrollments'] == 2
#             assert result['broken_enrollments'] == 1  # Only the invalid course, not NULL
#             assert result['broken_details'][0]['invalid_course'] == 'INVALID_COURSE'


# class TestPerformanceScenarios:
#     """Test performance-related scenarios"""
    
#     @pytest.mark.slow
#     def test_large_batch_processing_performance(self):
#         """Test processing of large batches (performance test)"""
#         from tap_lms.backend_onboarding import process_batch_job
        
#         # Create 100 mock students
#         large_student_list = []
#         for i in range(100):
#             large_student_list.append({
#                 'name': f'BS{i:03d}',
#                 'batch_skeyword': 'MATH5'
#             })
        
#         with patch('frappe.db') as mock_db, \\
#              patch('frappe.get_doc') as mock_get_doc, \\
#              patch('frappe.get_all') as mock_get_all, \\
#              patch('frappe.new_doc') as mock_new_doc, \\
#              patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
#              patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
#              patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student, \\
#              patch('tap_lms.backend_onboarding.update_job_progress') as mock_update_progress:
            
#             # Setup mocks for large batch
#             mock_batch = Mock()
#             mock_batch.status = "Processing"
#             mock_get_doc.return_value = mock_batch
            
#             mock_get_all.side_effect = [
#                 large_student_list,  # Large student list
#                 [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]
#             ]
            
#             mock_create_group.return_value = {"group_id": "GG001"}
#             mock_process_glific.return_value = {"id": "GC001"}
#             mock_find_student.return_value = None
            
#             # Mock student creation to be fast
#             mock_student_doc = Mock()
#             mock_student_doc.name = "STU001"
#             mock_student_doc.insert = Mock()
#             mock_new_doc.return_value = mock_student_doc
            
#             mock_db.exists.return_value = False
#             mock_db.commit = Mock()
#             mock_db.count.return_value = 100
            
#             # Create mock students for get_doc calls
#             def get_doc_side_effect(doctype, name):
#                 if doctype == "Backend Student Onboarding":
#                     return mock_batch
#                 else:  # Backend Students
#                     mock_student = Mock()
#                     mock_student.name = name
#                     mock_student.student_name = f"Student {name}"
#                     mock_student.phone = f"98765432{name[-2:]}"
#                     mock_student.batch_skeyword = "MATH5"
#                     return mock_student
            
#             mock_get_doc.side_effect = get_doc_side_effect
            
#             result = process_batch_job("BSO001")
            
#             # Verify all students were processed
#             assert result['success_count'] == 100
#             assert result['failure_count'] == 0
            
#             # Verify progress updates were called
#             assert mock_update_progress.call_count > 0

#     def test_concurrent_batch_processing_safety(self):
#         """Test that concurrent batch processing is handled safely"""
#         from tap_lms.backend_onboarding import process_batch
        
#         with patch('frappe.get_doc') as mock_get_doc, \\
#              patch('frappe.enqueue') as mock_enqueue:
            
#             mock_batch = Mock()
#             mock_batch.status = "Draft"
#             mock_get_doc.return_value = mock_batch
            
#             mock_job = Mock()
#             mock_job.id = "JOB001"
#             mock_enqueue.return_value = mock_job
            
#             # Process same batch twice (simulating concurrent requests)
#             result1 = process_batch("BSO001", use_background_job=True)
#             result2 = process_batch("BSO001", use_background_job=True)
            
#             # Both should get job IDs (framework should handle concurrency)
#             assert "job_id" in result1
#             assert "job_id" in result2
            
#             # Batch status should be set to Processing
#             assert mock_batch.status == "Processing"
#             assert mock_batch.save.call_count >= 2  # Called at least twice


# # Run configuration script
# if __name__ == "__main__":
#     # Create pytest.ini file
#     with open("pytest.ini", "w") as f:
#         f.write(PYTEST_INI_CONTENT)
    
#     # Create requirements-test.txt file  
#     with open("requirements-test.txt", "w") as f:
#         f.write(REQUIREMENTS_TEST_CONTENT)
    
#     # Create integration tests file
#     with open("test_integration.py", "w") as f:
#         f.write(INTEGRATION_TESTS_CONTENT)
    
#     print("Pytest configuration files created successfully!")
#     print("To run tests:")
#     print("1. Install test dependencies: pip install -r requirements-test.txt")
#     print("2. Run all tests: pytest")
#     print("3. Run with coverage: pytest --cov=tap_lms.backend_onboarding")
#     print("4. Run specific test class: pytest -k TestPhoneNumberNormalization")
# '''