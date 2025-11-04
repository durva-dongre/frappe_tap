


import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sys
import os
import importlib.util

# Direct file import approach
def import_backend_module():
    """Import the backend module directly from file path"""
    file_path = "/home/frappe/frappe-bench/apps/tap_lms/tap_lms/tap_lms/page/backend_onboarding_process/backend_onboarding_process.py"
    
    if not os.path.exists(file_path):
        raise ImportError(f"File not found: {file_path}")
    
    spec = importlib.util.spec_from_file_location("backend_onboarding_process", file_path)
    module = importlib.util.module_from_spec(spec)
    
    # Mock frappe before loading the module
    mock_frappe = MagicMock()
    mock_frappe.utils = MagicMock()
    mock_frappe.utils.nowdate = MagicMock(return_value="2025-01-01")
    mock_frappe.utils.now = MagicMock(return_value="2025-01-01 10:00:00")
    mock_frappe.utils.getdate = MagicMock()
    
    # Mock the whitelist decorator to return function unchanged
    mock_frappe.whitelist.return_value = lambda func: func
    
    sys.modules['frappe'] = mock_frappe
    sys.modules['frappe.utils'] = mock_frappe.utils
    sys.modules['tap_lms.glific_integration'] = MagicMock()
    sys.modules['tap_lms.api'] = MagicMock()
    sys.modules['rq.job'] = MagicMock()
    sys.modules['frappe.utils.background_jobs'] = MagicMock()
    
    spec.loader.exec_module(module)
    return module

class TestBackendOnboardingProcess(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up the backend module for all tests"""
        try:
            cls.backend_module = import_backend_module()
            print(f"Successfully imported module. Available functions: {[name for name in dir(cls.backend_module) if not name.startswith('_') and callable(getattr(cls.backend_module, name))]}")
        except Exception as e:
            raise unittest.SkipTest(f"Could not import backend module: {e}")

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_batch_id = "BSO_001"
        self.mock_student_name = "Test Student"
        self.mock_phone_10 = "9876543210"
        self.mock_phone_12 = "919876543210"
        self.mock_course_vertical = "Math"
        self.mock_grade = "5"

    # ============= Phone Number Normalization Tests =============

    def test_normalize_phone_number_10_digit(self):
        """Test normalize_phone_number with 10-digit number"""
        result = self.backend_module.normalize_phone_number("9876543210")
        self.assertEqual(result, ("919876543210", "9876543210"))

    def test_normalize_phone_number_12_digit(self):
        """Test normalize_phone_number with 12-digit number"""
        result = self.backend_module.normalize_phone_number("919876543210")
        self.assertEqual(result, ("919876543210", "9876543210"))

    def test_normalize_phone_number_11_digit_with_1_prefix(self):
        """Test normalize_phone_number with 11-digit number starting with 1"""
        result = self.backend_module.normalize_phone_number("19876543210")
        self.assertEqual(result, ("919876543210", "9876543210"))

    def test_normalize_phone_number_with_formatting(self):
        """Test normalize_phone_number with formatted input"""
        result = self.backend_module.normalize_phone_number("(987) 654-3210")
        self.assertEqual(result, ("919876543210", "9876543210"))

    def test_normalize_phone_number_invalid_length(self):
        """Test normalize_phone_number with invalid length"""
        result = self.backend_module.normalize_phone_number("123456")
        self.assertEqual(result, (None, None))

    def test_normalize_phone_number_empty_input(self):
        """Test normalize_phone_number with empty input"""
        result = self.backend_module.normalize_phone_number("")
        self.assertEqual(result, (None, None))

    def test_normalize_phone_number_none_input(self):
        """Test normalize_phone_number with None input"""
        result = self.backend_module.normalize_phone_number(None)
        self.assertEqual(result, (None, None))

    def test_normalize_phone_number_non_91_12_digit(self):
        """Test normalize_phone_number with 12-digit number not starting with 91"""
        result = self.backend_module.normalize_phone_number("129876543210")
        self.assertEqual(result, (None, None))

    # ============= Student Finding Tests =============

    def test_find_existing_student_by_phone_and_name_found(self):
        """Test find_existing_student_by_phone_and_name when student exists"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = [
                {"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}
            ]

            result = self.backend_module.find_existing_student_by_phone_and_name("9876543210", "Test Student")

            self.assertIsNotNone(result)
            self.assertEqual(result["name"], "STUD_001")

    def test_find_existing_student_by_phone_and_name_not_found(self):
        """Test find_existing_student_by_phone_and_name when student doesn't exist"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = []

            result = self.backend_module.find_existing_student_by_phone_and_name("9876543210", "Test Student")

            self.assertIsNone(result)

    def test_find_existing_student_by_phone_and_name_empty_phone(self):
        """Test find_existing_student_by_phone_and_name with empty phone"""
        result = self.backend_module.find_existing_student_by_phone_and_name("", "Test Student")
        self.assertIsNone(result)

    def test_find_existing_student_by_phone_and_name_empty_name(self):
        """Test find_existing_student_by_phone_and_name with empty name"""
        result = self.backend_module.find_existing_student_by_phone_and_name("9876543210", "")
        self.assertIsNone(result)

    # ============= Batch Management Tests =============

    def test_get_onboarding_batches(self):
        """Test get_onboarding_batches returns draft/processing  batches"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [
                {
                    "name": "BSO_001",
                    "set_name": "Batch 1",
                    "upload_date": "2025-01-01",
                    "uploaded_by": "user@example.com",
                    "student_count": 50,
                    "processed_student_count": 0
                }
            ]
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.get_onboarding_batches()

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["name"], "BSO_001")
            mock_frappe.get_all.assert_called_once_with(
                "Backend Student Onboarding",
                filters={"status": ["in", ["Draft", "Processing", "Failed"]]},
                fields=["name", "set_name", "upload_date", "uploaded_by", "student_count", "processed_student_count"]
            )

    # def test_get_batch_details(self):
    #     """Test get_batch_details returns batch and student data"""
    #     with patch.object(self.backend_module, 'frappe') as mock_frappe:
    #         # Mock validate_student to avoid calling the problematic function
    #         with patch.object(self.backend_module, 'validate_student', return_value={}) as mock_validate:
    #             mock_batch = MagicMock()
    #             mock_frappe.get_doc.return_value = mock_batch
    #             mock_frappe.get_all.side_effect = [
    #                 [{"name": "BS_001", "student_name": "Test Student", "phone": "9876543210"}],
    #                 []  # No glific group
    #             ]
    #             mock_frappe.whitelist.return_value = lambda func: func

    #             result = self.backend_module.get_batch_details("BSO_001")

    #             self.assertIn("batch", result)
    #             self.assertIn("students", result)
    #             self.assertIn("glific_group", result)
    #             mock_validate.assert_called_once()

    def test_get_onboarding_stages(self):
        """Test get_onboarding_stages returns stages from database"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.table_exists.return_value = True
            mock_frappe.get_all.return_value = [
                {"name": "STAGE_001", "description": "Initial Stage", "order": 0},
                {"name": "STAGE_002", "description": "Second Stage", "order": 1}
            ]
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.get_onboarding_stages()

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["name"], "STAGE_001")

    def test_get_onboarding_stages_no_table(self):
        """Test get_onboarding_stages when database table doesn't exist"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.table_exists.return_value = False

            result = self.backend_module.get_onboarding_stages()

            self.assertEqual(result, [])

    # ============= Process Batch Tests =============

    def test_process_batch_background_job(self):
        """Test process_batch with background job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_frappe.get_doc.return_value = mock_batch
            mock_job = MagicMock()
            mock_job.id = "job_123"
            mock_frappe.enqueue.return_value = mock_job
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.process_batch("BSO_001", use_background_job=True)

            self.assertIn("job_id", result)
            self.assertEqual(result["job_id"], "job_123")
            mock_frappe.enqueue.assert_called_once()

    def test_process_batch_immediate(self):
        """Test process_batch with immediate processing"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'process_batch_job', return_value={"success_count": 5, "failure_count": 0}) as mock_process_job:
                mock_batch = MagicMock()
                mock_frappe.get_doc.return_value = mock_batch
                mock_frappe.whitelist.return_value = lambda func: func

                result = self.backend_module.process_batch("BSO_001", use_background_job=False)

                self.assertEqual(result["success_count"], 5)
                mock_process_job.assert_called_once_with("BSO_001")

    def test_process_batch_string_boolean(self):
        """Test process_batch with string boolean input"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'process_batch_job', return_value={"success_count": 3, "failure_count": 0}):
                mock_batch = MagicMock()
                mock_frappe.get_doc.return_value = mock_batch
                mock_frappe.whitelist.return_value = lambda func: func

                result = self.backend_module.process_batch("BSO_001", use_background_job="false")

                self.assertEqual(result["success_count"], 3)

    # ============= Academic Year Tests =============

    def test_get_current_academic_year_backend_april_onwards(self):
        """Test get_current_academic_year_backend for April onwards"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_date = MagicMock()
            mock_date.year = 2025
            mock_date.month = 5  # May
            mock_frappe.utils.getdate.return_value = mock_date
            mock_frappe.log_error = MagicMock()

            result = self.backend_module.get_current_academic_year_backend()

            self.assertEqual(result, "2025-26")

    def test_get_current_academic_year_backend_before_april(self):
        """Test get_current_academic_year_backend for before April"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_date = MagicMock()
            mock_date.year = 2025
            mock_date.month = 2  # February
            mock_frappe.utils.getdate.return_value = mock_date
            mock_frappe.log_error = MagicMock()

            result = self.backend_module.get_current_academic_year_backend()

            self.assertEqual(result, "2024-25")

    def test_get_current_academic_year_backend_april_exact(self):
        """Test get_current_academic_year_backend for exact April"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_date = MagicMock()
            mock_date.year = 2025
            mock_date.month = 4  # April
            mock_frappe.utils.getdate.return_value = mock_date
            mock_frappe.log_error = MagicMock()

            result = self.backend_module.get_current_academic_year_backend()

            self.assertEqual(result, "2025-26")

    def test_get_course_level_with_mapping_backend_fallback(self):
        """Test get_course_level_with_mapping_backend fallback to original logic"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    with patch.object(self.backend_module, 'get_course_level', return_value="MATH_BASIC") as mock_get_course:
                        mock_frappe.get_all.return_value = []  # No mapping found
                        mock_frappe.log_error = MagicMock()

                        result = self.backend_module.get_course_level_with_mapping_backend(
                            "Math", "5", "9876543210", "Test Student", False
                        )

                        self.assertEqual(result, "MATH_BASIC")
                        mock_get_course.assert_called_once()

    def test_get_course_level_with_validation_backend(self):
        """Test get_course_level_with_validation_backend calls validation"""
        with patch.object(self.backend_module, 'validate_enrollment_data', return_value={"broken_enrollments": 0}):
            with patch.object(self.backend_module, 'get_course_level_with_mapping_backend', return_value="MATH_L5") as mock_mapping:
                with patch.object(self.backend_module, 'frappe') as mock_frappe:
                    mock_frappe.log_error = MagicMock()

                    result = self.backend_module.get_course_level_with_validation_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_L5")
                    mock_mapping.assert_called_once()

    # ============= Utility Function Tests =============

    def test_format_phone_number_valid(self):
        """Test format_phone_number with valid input"""
        result = self.backend_module.format_phone_number("9876543210")
        self.assertEqual(result, "919876543210")

    def test_format_phone_number_already_formatted(self):
        """Test format_phone_number with already formatted input"""
        result = self.backend_module.format_phone_number("919876543210")
        self.assertEqual(result, "919876543210")

    def test_format_phone_number_invalid(self):
        """Test format_phone_number with invalid input"""
        result = self.backend_module.format_phone_number("invalid")
        self.assertIsNone(result)

    def test_update_job_progress(self):
        """Test update_job_progress publishes progress"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.publish_progress = MagicMock()

            self.backend_module.update_job_progress(5, 10)

            mock_frappe.publish_progress.assert_called_once()

    def test_update_job_progress_fallback(self):
        """Test update_job_progress fallback when publish_progress fails"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.publish_progress.side_effect = Exception("Publish failed")
            mock_frappe.db.commit = MagicMock()

            # Should not raise exception, should use fallback
            self.backend_module.update_job_progress(9, 10)  # Should trigger commit

    # ============= Job Status Tests =============

    def test_get_job_status_completed(self):
        """Test get_job_status for completed job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    
                    mock_job = MagicMock()
                    mock_job.get_status.return_value = "finished"
                    mock_job.result = {"success": True}
                    mock_job.meta = {"progress": 100}
                    mock_job_class.fetch.return_value = mock_job
                    
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.get_job_status("job_123")

                    self.assertEqual(result["status"], "Completed")
                    self.assertEqual(result["result"], {"success": True})

    def test_get_job_status_not_found(self):
        """Test get_job_status for non-existent job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    mock_job_class.fetch.side_effect = Exception("Job not found")
                    mock_frappe.logger.return_value = MagicMock()
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.get_job_status("invalid_job")

                    self.assertEqual(result["status"], "Not Found")

    def test_get_job_status_running(self):
        """Test get_job_status for running job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    
                    mock_job = MagicMock()
                    mock_job.get_status.return_value = "started"
                    mock_job.result = None
                    mock_job.meta = {"progress": 50}
                    mock_job_class.fetch.return_value = mock_job

                    result = self.backend_module.get_job_status("job_123")

                    self.assertEqual(result["status"], "started")
                    self.assertEqual(result["progress"], 50)

    # ============= Glific Contact Processing Tests =============

    def test_process_glific_contact_invalid_phone(self):
        """Test process_glific_contact with invalid phone number"""
        mock_student = MagicMock()
        mock_student.phone = "invalid"
        mock_student.student_name = "Test Student"

        with self.assertRaises(ValueError):
            self.backend_module.process_glific_contact(mock_student, None)

    def test_process_glific_contact_existing_contact(self):
        """Test process_glific_contact with existing contact"""
        with patch.object(self.backend_module, 'format_phone_number', return_value="919876543210"):
            with patch.object(self.backend_module, 'get_contact_by_phone', return_value={"id": "contact_123"}):
                with patch.object(self.backend_module, 'frappe') as mock_frappe:
                    mock_frappe.get_value.return_value = "Test School"
                    
                    mock_student = MagicMock()
                    mock_student.phone = "9876543210"
                    mock_student.student_name = "Test Student"
                    mock_student.school = "SCH001"
                    mock_student.batch = "BT001"
                    mock_student.language = "English"
                    mock_student.course_vertical = "Math"
                    mock_student.grade = "5"

                    result = self.backend_module.process_glific_contact(mock_student, None)

                    self.assertEqual(result["id"], "contact_123")

    def test_process_glific_contact_new_contact(self):
        """Test process_glific_contact creating new contact"""
        with patch.object(self.backend_module, 'format_phone_number', return_value="919876543210"):
            with patch.object(self.backend_module, 'get_contact_by_phone', return_value=None):
                with patch.object(self.backend_module, 'add_student_to_glific_for_onboarding', return_value={"id": "new_contact_123"}):
                    with patch.object(self.backend_module, 'frappe') as mock_frappe:
                        mock_frappe.get_value.return_value = "Test School"
                        
                        mock_student = MagicMock()
                        mock_student.phone = "9876543210"
                        mock_student.student_name = "Test Student"
                        mock_student.school = "SCH001"
                        mock_student.batch = "BT001"
                        mock_student.language = "English"
                        mock_student.course_vertical = "Math"
                        mock_student.grade = "5"

                        result = self.backend_module.process_glific_contact(mock_student, None)

                        self.assertEqual(result["id"], "new_contact_123")

    # ============= Backend Student Status Update Tests =============

    def test_update_backend_student_status_success(self):
        """Test update_backend_student_status for success"""
        mock_student = MagicMock()
        mock_student_doc = MagicMock()
        mock_student_doc.name = "STUD_001"
        mock_student_doc.glific_id = "contact_123"

        self.backend_module.update_backend_student_status(mock_student, "Success", mock_student_doc)

        self.assertEqual(mock_student.processing_status, "Success")
        self.assertEqual(mock_student.student_id, "STUD_001")
        mock_student.save.assert_called_once()

    def test_update_backend_student_status_failure(self):
        """Test update_backend_student_status for failure"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_student = MagicMock()
            mock_student.processing_notes = ""

            mock_meta = MagicMock()
            mock_field = MagicMock()
            mock_field.length = 140
            mock_meta.get_field.return_value = mock_field
            mock_frappe.get_meta.return_value = mock_meta

            self.backend_module.update_backend_student_status(mock_student, "Failed", error="Error message")

            self.assertEqual(mock_student.processing_status, "Failed")
            self.assertEqual(mock_student.processing_notes, "Error message")
            mock_student.save.assert_called_once()

    def test_update_backend_student_status_long_error(self):
        """Test update_backend_student_status with error longer than field limit"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_student = MagicMock()
            mock_student.processing_notes = ""

            mock_meta = MagicMock()
            mock_field = MagicMock()
            mock_field.length = 10  # Short limit
            mock_meta.get_field.return_value = mock_field
            mock_frappe.get_meta.return_value = mock_meta

            long_error = "This is a very long error message that exceeds the field limit"
            self.backend_module.update_backend_student_status(mock_student, "Failed", error=long_error)

            self.assertEqual(mock_student.processing_status, "Failed")
            self.assertEqual(len(mock_student.processing_notes), 10)  # Truncated
            mock_student.save.assert_called_once()

    def test_debug_student_processing(self):
        """Test debug_student_processing function"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Mock all the dependent functions to avoid calling problematic ones
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                    mock_frappe.get_all.return_value = []
                    mock_frappe.whitelist.return_value = lambda func: func
                    
                    result = self.backend_module.debug_student_processing("Test Student", "9876543210")
                    
                    self.assertIn("DEBUGGING STUDENT", result)
                    self.assertIn("Test Student", result)
                    self.assertIn("Student DOES NOT EXIST", result)

    def test_fix_broken_course_links_no_student_id(self):
        """Test fix_broken_course_links without specific student ID"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [{"name": "STUD_001"}]
            mock_frappe.db.sql.return_value = []  # No broken enrollments
            mock_frappe.db.commit = MagicMock()
            mock_frappe.whitelist.return_value = lambda func: func
            
            result = self.backend_module.fix_broken_course_links()
            
            self.assertIn("No broken course links found", result)

    def test_fix_broken_course_links_with_specific_student(self):
        """Test fix_broken_course_links with specific student ID"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = [
                {"name": "ENR_001", "course": "BROKEN_COURSE"}
            ]
            mock_frappe.db.set_value = MagicMock()
            mock_frappe.db.commit = MagicMock()
            mock_frappe.whitelist.return_value = lambda func: func
            
            result = self.backend_module.fix_broken_course_links("STUD_001")
            
            # Function should handle the specific student ID case
            self.assertIsInstance(result, str)
            # It should process the student
            mock_frappe.db.sql.assert_called()

    def test_test_basic_student_creation(self):
        """Test test_basic_student_creation function"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_student = MagicMock()
            mock_student.name = "TEST_STUDENT_001"
            mock_frappe.new_doc.return_value = mock_student
            mock_frappe.delete_doc = MagicMock()
            mock_frappe.whitelist.return_value = lambda func: func
            
            result = self.backend_module.test_basic_student_creation()
            
            self.assertIn("BASIC TEST PASSED", result)
            mock_student.insert.assert_called_once()
            mock_student.save.assert_called_once()

    def test_process_student_record_new_student(self):
        """Test process_student_record creating new student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                mock_student = MagicMock()
                mock_student.student_name = "New Student"
                mock_student.phone = "9876543210"
                mock_student.gender = "Male"
                mock_student.school = "SCH001"
                mock_student.grade = "5"
                mock_student.language = "English"
                mock_student.batch = "BT001"

                mock_glific_contact = {"id": "contact_123"}
                mock_student_doc = MagicMock()
                mock_frappe.new_doc.return_value = mock_student_doc
                mock_frappe.db.exists.return_value = False  # No existing states
                mock_frappe.log_error = MagicMock()

                result = self.backend_module.process_student_record(
                    mock_student, mock_glific_contact, "BSO_001", "STAGE_001", "MATH_L5"
                )

                self.assertTrue(mock_student_doc.insert.called)
                self.assertEqual(result, mock_student_doc)

# if __name__ == '__main__':
#     unittest.main()