import pytest
from unittest.mock import MagicMock, patch, call
import json
from datetime import datetime

# Import the functions to test (adjust the import path as needed)
# Since we can't import the actual frappe module, we'll mock everything
try:
    from your_module import (
        normalize_phone_number,
        find_existing_student_by_phone_and_name,
        validate_student,
        get_initial_stage,
        process_batch_job,
        determine_student_type_backend,
        get_course_level_with_mapping_backend,
        process_glific_contact,
        process_student_record,
        update_backend_student_status,
        format_phone_number,
        get_current_academic_year_backend
    )
except ImportError:
    # Define the functions locally for testing
    def normalize_phone_number(phone):
        if not phone:
            return None, None
        
        phone = phone.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        phone = ''.join(filter(str.isdigit, phone))
        
        if len(phone) == 10:
            return f"91{phone}", phone
        elif len(phone) == 12 and phone.startswith('91'):
            return phone, phone[2:]
        elif len(phone) == 11 and phone.startswith('1'):
            return f"9{phone}", phone[1:]
        else:
            return None, None

    def find_existing_student_by_phone_and_name(phone, name):
        return None  # Mock implementation

    def validate_student(student):
        return {}  # Mock implementation

    def get_initial_stage():
        return "STAGE001"  # Mock implementation

    # Other functions would be defined similarly...


class TestBackendStudentOnboarding:
    
    def test_normalize_phone_number_valid_formats(self):
        """Test phone number normalization for various valid formats"""
        # 10-digit numbers
        assert normalize_phone_number("9876543210") == ("919876543210", "9876543210")
        assert normalize_phone_number(" 987-654-3210 ") == ("919876543210", "9876543210")
        assert normalize_phone_number("(987) 654-3210") == ("919876543210", "9876543210")
        
        # 12-digit numbers
        assert normalize_phone_number("919876543210") == ("919876543210", "9876543210")
        
        # Edge cases
        assert normalize_phone_number("19876543210") == ("919876543210", "9876543210")  # 11-digit starting with 1
        
    def test_normalize_phone_number_invalid_formats(self):
        """Test phone number normalization for invalid formats"""
        assert normalize_phone_number("123") == (None, None)
        assert normalize_phone_number("abcdef") == (None, None)
        assert normalize_phone_number("") == (None, None)
        assert normalize_phone_number("987654321") == (None, None)  # 9 digits
        assert normalize_phone_number("9198765432101") == (None, None)  # 13 digits
    
    @patch('frappe.db.sql')
    def test_find_existing_student_by_phone_and_name(self, mock_sql):
        """Test finding existing students with different phone formats"""
        test_student = {
            "name": "STU001",
            "name1": "Test Student",
            "phone": "9876543210"
        }
        
        mock_sql.return_value = [test_student]
        
        # Test with 10-digit format
        result = find_existing_student_by_phone_and_name("9876543210", "Test Student")
        assert result == test_student
        
        # Test with 12-digit format
        result = find_existing_student_by_phone_and_name("919876543210", "Test Student")
        assert result == test_student
        
        # Verify SQL was called with correct parameters
        mock_sql.assert_called_with(
            """
            SELECT name, phone, name1
            FROM `tabStudent`
            WHERE name1 = %s 
            AND (phone = %s OR phone = %s)
            LIMIT 1
            """, 
            ("Test Student", "9876543210", "919876543210"),
            as_dict=True
        )
    
    def test_validate_student_missing_fields(self):
        """Test student validation for missing required fields"""
        incomplete_student = {
            "student_name": "Test Student",
            "phone": "9876543210"
            # Missing school, grade, language, batch
        }
        
        validation = validate_student(incomplete_student)
        assert "school" in validation
        assert "grade" in validation
        assert "language" in validation
        assert "batch" in validation
    
    @patch('find_existing_student_by_phone_and_name')
    def test_validate_student_duplicate(self, mock_find):
        """Test student validation for duplicate detection"""
        mock_find.return_value = {"name": "EXISTING_STU", "name1": "Existing Student"}
        
        complete_student = {
            "student_name": "Test Student",
            "phone": "9876543210",
            "school": "SCH001",
            "grade": "5",
            "language": "EN",
            "batch": "BATCH001"
        }
        
        validation = validate_student(complete_student)
        assert "duplicate" in validation
        assert validation["duplicate"]["student_id"] == "EXISTING_STU"
    
    @patch('frappe.get_all')
    def test_get_initial_stage(self, mock_get_all):
        """Test getting initial onboarding stage"""
        mock_get_all.return_value = [{"name": "STAGE001"}]
        
        result = get_initial_stage()
        assert result == "STAGE001"
        
        # Test with order=0
        mock_get_all.return_value = [{"name": "STAGE002"}]
        result = get_initial_stage()
        assert result == "STAGE002"
    
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('create_or_get_glific_group_for_batch')
    @patch('process_glific_contact')
    @patch('process_student_record')
    @patch('update_backend_student_status')
    @patch('frappe.db.commit')
    @patch('frappe.log_error')
    def test_process_batch_job_success(self, mock_log, mock_commit, mock_update, 
                                     mock_process, mock_glific, mock_glific_group, 
                                     mock_get_all, mock_get_doc):
        """Test successful batch processing"""
        # Setup mock data
        mock_batch = MagicMock()
        mock_batch.status = "Draft"
        
        test_student = {
            "name": "BACKEND_STU001",
            "student_name": "Test Student",
            "phone": "9876543210",
            "batch_skeyword": "TEST_BATCH"
        }
        
        mock_get_doc.return_value = mock_batch
        mock_get_all.side_effect = [
            [test_student],  # Students to process
            [{"name": "BATCH_ONBOARDING", "kit_less": False}]  # Batch onboarding
        ]
        mock_glific_group.return_value = {"group_id": "GROUP001"}
        mock_glific.return_value = {"id": "GLIFIC001"}
        mock_process.return_value = MagicMock(name="STU001")
        
        # Execute
        result = process_batch_job("BATCH001")
        
        # Assertions
        assert result["success_count"] == 1
        assert result["failure_count"] == 0
        mock_glific.assert_called_once()
        mock_process.assert_called_once()
        mock_update.assert_called_once()
        assert mock_batch.status == "Processing"
    
    @patch('frappe.db.sql')
    @patch('frappe.db.exists')
    def test_determine_student_type_backend(self, mock_exists, mock_sql):
        """Test student type determination logic"""
        # Mock student exists
        mock_sql.side_effect = [
            [{"name": "STU001"}],  # Student exists
            [{"course": "COURSE001", "batch": "BATCH001"}]  # Enrollments
        ]
        mock_exists.return_value = True  # Course exists
        
        result = determine_student_type_backend("9876543210", "Test Student", "MATH")
        assert result == "Old"
    
    @patch('frappe.get_all')
    @patch('get_current_academic_year_backend')
    def test_get_course_level_with_mapping_backend(self, mock_year, mock_get_all):
        """Test course level selection with mapping"""
        mock_year.return_value = "2024-25"
        mock_get_all.return_value = [{"assigned_course_level": "MATH_GRADE5"}]
        
        result = get_course_level_with_mapping_backend(
            "MATH", "5", "9876543210", "Test Student", False
        )
        assert result == "MATH_GRADE5"
    
    @patch('get_contact_by_phone')
    @patch('add_student_to_glific_for_onboarding')
    def test_process_glific_contact_existing(self, mock_add, mock_get_contact):
        """Test Glific contact processing for existing contact"""
        mock_student = MagicMock()
        mock_student.phone = "9876543210"
        mock_student.student_name = "Test Student"
        mock_student.school = "SCH001"
        mock_student.batch = "BATCH001"
        mock_student.course_vertical = "MATH"
        mock_student.grade = "5"
        mock_student.language = "EN"
        
        mock_get_contact.return_value = {"id": "CONTACT001"}
        
        result = process_glific_contact(mock_student, {"group_id": "GROUP001"})
        assert result["id"] == "CONTACT001"
        mock_get_contact.assert_called_with("919876543210")
    
    @patch('get_contact_by_phone')
    @patch('add_student_to_glific_for_onboarding')
    def test_process_glific_contact_new(self, mock_add, mock_get_contact):
        """Test Glific contact processing for new contact"""
        mock_student = MagicMock()
        mock_student.phone = "9876543210"
        mock_student.student_name = "Test Student"
        mock_student.school = "SCH001"
        mock_student.batch = "BATCH001"
        mock_student.course_vertical = "MATH"
        mock_student.grade = "5"
        mock_student.language = "EN"
        
        mock_get_contact.return_value = None
        mock_add.return_value = {"id": "CONTACT002"}
        
        result = process_glific_contact(mock_student, {"group_id": "GROUP001"})
        assert result["id"] == "CONTACT002"
        mock_add.assert_called_once()
    
    @patch('find_existing_student_by_phone_and_name')
    @patch('frappe.new_doc')
    @patch('frappe.db.exists')
    def test_process_student_record_new_student(self, mock_exists, mock_new, mock_find):
        """Test processing a new student record"""
        mock_backend_student = MagicMock()
        mock_backend_student.phone = "9876543210"
        mock_backend_student.student_name = "New Student"
        mock_backend_student.gender = "Male"
        mock_backend_student.school = "SCH001"
        mock_backend_student.grade = "5"
        mock_backend_student.language = "EN"
        mock_backend_student.batch = "BATCH001"
        
        mock_find.return_value = None
        mock_exists.return_value = False
        
        mock_student_doc = MagicMock()
        mock_new.return_value = mock_student_doc
        
        result = process_student_record(
            mock_backend_student, 
            {"id": "GLIFIC001"}, 
            "BATCH001", 
            "STAGE001"
        )
        
        assert result == mock_student_doc
        mock_student_doc.insert.assert_called_once()
    
    @patch('find_existing_student_by_phone_and_name')
    def test_process_student_record_existing_student(self, mock_find):
        """Test processing an existing student record"""
        mock_backend_student = MagicMock()
        mock_backend_student.phone = "9876543210"
        mock_backend_student.student_name = "Existing Student"
        mock_backend_student.gender = "Male"
        mock_backend_student.school = "SCH001"
        mock_backend_student.grade = "5"
        mock_backend_student.language = "EN"
        mock_backend_student.batch = "BATCH001"
        
        mock_existing_student = MagicMock()
        mock_existing_student.name = "STU001"
        mock_existing_student.grade = "4"  # Different grade
        mock_existing_student.school_id = "SCH002"  # Different school
        
        mock_find.return_value = mock_existing_student
        
        result = process_student_record(
            mock_backend_student, 
            {"id": "GLIFIC001"}, 
            "BATCH001", 
            "STAGE001"
        )
        
        assert result == mock_existing_student
        assert mock_existing_student.grade == "5"  # Should be updated
        assert mock_existing_student.school_id == "SCH001"  # Should be updated
        mock_existing_student.save.assert_called_once()
    
    def test_update_backend_student_status_success(self):
        """Test updating backend student status for success"""
        mock_student = MagicMock()
        mock_student_doc = MagicMock()
        mock_student_doc.name = "STU001"
        mock_student_doc.glific_id = "GLIFIC001"
        
        update_backend_student_status(mock_student, "Success", mock_student_doc)
        
        assert mock_student.processing_status == "Success"
        assert mock_student.student_id == "STU001"
        assert mock_student.glific_id == "GLIFIC001"
        mock_student.save.assert_called_once()
    
    def test_update_backend_student_status_failed(self):
        """Test updating backend student status for failure"""
        mock_student = MagicMock()
        
        update_backend_student_status(mock_student, "Failed", error="Test error")
        
        assert mock_student.processing_status == "Failed"
        mock_student.save.assert_called_once()
    
    def test_format_phone_number(self):
        """Test phone number formatting for Glific"""
        result = format_phone_number("9876543210")
        assert result == "919876543210"
        
        result = format_phone_number("919876543210")
        assert result == "919876543210"
    
    def test_get_current_academic_year_backend(self):
        """Test academic year calculation"""
        with patch('frappe.utils.getdate') as mock_date:
            # Test April onwards (new academic year)
            mock_date.return_value = datetime(2024, 6, 15).date()  # June 2024
            result = get_current_academic_year_backend()
            assert result == "2024-25"
            
            # Test January-March (previous academic year)
            mock_date.return_value = datetime(2024, 2, 15).date()  # February 2024
            result = get_current_academic_year_backend()
            assert result == "2023-24"
    
    @patch('frappe.get_doc')
    @patch('frappe.enqueue')
    def test_process_batch_background_job(self, mock_enqueue, mock_get_doc):
        """Test batch processing with background job"""
        mock_batch = MagicMock()
        mock_batch.status = "Draft"
        mock_get_doc.return_value = mock_batch
        mock_enqueue.return_value = MagicMock(id="JOB001")
        
        result = process_batch("BATCH001", use_background_job=True)
        
        assert "job_id" in result
        assert result["job_id"] == "JOB001"
        mock_enqueue.assert_called_once()
        assert mock_batch.status == "Processing"
        mock_batch.save.assert_called_once()
    
    @patch('frappe.db.get_value')
    def test_get_job_status(self, mock_get_value):
        """Test getting job status"""
        mock_get_value.return_value = {
            "status": "finished",
            "progress_data": '{"percent": 100}',
            "result": '{"success": true}'
        }
        
        result = get_job_status("JOB001")
        assert result["status"] == "Completed"
        assert "result" in result

if __name__ == "__main__":
    pytest.main([__file__, "-v"])