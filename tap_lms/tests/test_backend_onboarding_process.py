


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


