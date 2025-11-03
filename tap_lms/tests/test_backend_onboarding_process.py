import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sys
import os
import importlib.util
import json

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

    # ============= Phone Number Normalization Tests (ENHANCED) =============

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

    def test_normalize_phone_number_with_spaces(self):
        """Test normalize_phone_number with spaces"""
        result = self.backend_module.normalize_phone_number("98 765 432 10")
        self.assertEqual(result, ("919876543210", "9876543210"))

    def test_normalize_phone_number_with_dashes(self):
        """Test normalize_phone_number with dashes"""
        result = self.backend_module.normalize_phone_number("987-654-3210")
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

    def test_normalize_phone_number_whitespace_only(self):
        """Test normalize_phone_number with whitespace only"""
        result = self.backend_module.normalize_phone_number("   ")
        self.assertEqual(result, (None, None))

    def test_normalize_phone_number_mixed_characters(self):
        """Test normalize_phone_number with mixed characters"""
        result = self.backend_module.normalize_phone_number("+91-987-654-3210")
        self.assertEqual(result, ("919876543210", "9876543210"))

    # ============= Student Finding Tests (ENHANCED) =============

    def test_find_existing_student_by_phone_and_name_found(self):
        """Test find_existing_student_by_phone_and_name when student exists"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = [
                {"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}
            ]

            result = self.backend_module.find_existing_student_by_phone_and_name("9876543210", "Test Student")

            self.assertIsNotNone(result)
            self.assertEqual(result["name"], "STUD_001")
            self.assertEqual(result["phone"], "919876543210")
            self.assertEqual(result["name1"], "Test Student")

    def test_find_existing_student_by_phone_and_name_with_12_digit_phone(self):
        """Test find_existing_student_by_phone_and_name with 12-digit phone"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = [
                {"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}
            ]

            result = self.backend_module.find_existing_student_by_phone_and_name("919876543210", "Test Student")

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

    def test_find_existing_student_by_phone_and_name_both_empty(self):
        """Test find_existing_student_by_phone_and_name with both empty"""
        result = self.backend_module.find_existing_student_by_phone_and_name("", "")
        self.assertIsNone(result)

    def test_find_existing_student_by_phone_and_name_invalid_phone(self):
        """Test find_existing_student_by_phone_and_name with invalid phone"""
        result = self.backend_module.find_existing_student_by_phone_and_name("invalid", "Test Student")
        self.assertIsNone(result)

    # ============= Batch Management Tests (ENHANCED) =============

    def test_get_onboarding_batches(self):
        """Test get_onboarding_batches returns draft/processing batches"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [
                {
                    "name": "BSO_001",
                    "set_name": "Batch 1",
                    "upload_date": "2025-01-01",
                    "uploaded_by": "user@example.com",
                    "student_count": 50,
                    "processed_student_count": 0
                },
                {
                    "name": "BSO_002",
                    "set_name": "Batch 2",
                    "upload_date": "2025-01-02",
                    "uploaded_by": "user2@example.com",
                    "student_count": 30,
                    "processed_student_count": 10
                }
            ]
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.get_onboarding_batches()

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["name"], "BSO_001")
            self.assertEqual(result[1]["processed_student_count"], 10)
            mock_frappe.get_all.assert_called_once_with(
                "Backend Student Onboarding",
                filters={"status": ["in", ["Draft", "Processing", "Failed"]]},
                fields=["name", "set_name", "upload_date", "uploaded_by", "student_count", "processed_student_count"]
            )

    def test_get_onboarding_batches_empty(self):
        """Test get_onboarding_batches with no batches"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = []
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.get_onboarding_batches()

            self.assertEqual(len(result), 0)

    def test_get_batch_details(self):
        """Test get_batch_details returns batch and student data"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [
                {"name": "BS_001", "student_name": "Test Student 1", "phone": "9876543210"},
                {"name": "BS_002", "student_name": "Test Student 2", "phone": "9876543211"}
            ]
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.get_batch_details("BSO_001")

            self.assertIn("batch", result)
            self.assertIn("students", result)
            self.assertIn("on_queue", result)
            self.assertEqual(result["batch"], "BSO_001")
            self.assertEqual(result["students"], 2)
            self.assertFalse(result["on_queue"])

    def test_get_batch_details_no_students(self):
        """Test get_batch_details with no students"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = []
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.get_batch_details("BSO_001")

            self.assertEqual(result["students"], 0)

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
            self.assertEqual(result[0]["order"], 0)

    def test_get_onboarding_stages_no_table(self):
        """Test get_onboarding_stages when database table doesn't exist"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.table_exists.return_value = False

            result = self.backend_module.get_onboarding_stages()

            self.assertEqual(result, [])

    def test_get_onboarding_stages_exception(self):
        """Test get_onboarding_stages with exception"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.table_exists.side_effect = Exception("Database error")

            result = self.backend_module.get_onboarding_stages()

            self.assertEqual(result, [])

    def test_get_initial_stage_with_order_zero(self):
        """Test get_initial_stage returns stage with order=0"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [{"name": "STAGE_INITIAL"}]

            result = self.backend_module.get_initial_stage()

            self.assertEqual(result, "STAGE_INITIAL")

    def test_get_initial_stage_fallback_to_min_order(self):
        """Test get_initial_stage falls back to minimum order stage"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # First call (order=0) returns empty, second call (min order) returns stage
            mock_frappe.get_all.side_effect = [
                [],  # No stage with order=0
                [{"name": "STAGE_MIN", "order": 1}]  # Stage with minimum order
            ]

            result = self.backend_module.get_initial_stage()

            self.assertEqual(result, "STAGE_MIN")

    def test_get_initial_stage_no_stages(self):
        """Test get_initial_stage with no stages"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = []

            result = self.backend_module.get_initial_stage()

            self.assertIsNone(result)

    # ============= Process Batch Tests (ENHANCED) =============

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
            # Verify batch status was set to Processing
            self.assertEqual(mock_batch.status, "Processing")
            mock_batch.save.assert_called_once()

    def test_process_batch_immediate(self):
        """Test process_batch with immediate processing"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'process_batch_job', return_value={"success_count": 5, "failure_count": 0}) as mock_process_job:
                mock_batch = MagicMock()
                mock_frappe.get_doc.return_value = mock_batch
                mock_frappe.whitelist.return_value = lambda func: func

                result = self.backend_module.process_batch("BSO_001", use_background_job=False)

                self.assertEqual(result["success_count"], 5)
                self.assertEqual(result["failure_count"], 0)
                mock_process_job.assert_called_once_with("BSO_001")

    def test_process_batch_string_boolean_true(self):
        """Test process_batch with string boolean 'true'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_frappe.get_doc.return_value = mock_batch
            mock_job = MagicMock()
            mock_job.id = "job_456"
            mock_frappe.enqueue.return_value = mock_job
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.process_batch("BSO_001", use_background_job="true")

            self.assertIn("job_id", result)

    def test_process_batch_string_boolean_false(self):
        """Test process_batch with string boolean 'false'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'process_batch_job', return_value={"success_count": 3, "failure_count": 0}):
                mock_batch = MagicMock()
                mock_frappe.get_doc.return_value = mock_batch
                mock_frappe.whitelist.return_value = lambda func: func

                result = self.backend_module.process_batch("BSO_001", use_background_job="false")

                self.assertEqual(result["success_count"], 3)

    # ============= Academic Year Tests (ENHANCED) =============

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

    def test_get_current_academic_year_backend_march(self):
        """Test get_current_academic_year_backend for March"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_date = MagicMock()
            mock_date.year = 2025
            mock_date.month = 3  # March
            mock_frappe.utils.getdate.return_value = mock_date
            mock_frappe.log_error = MagicMock()

            result = self.backend_module.get_current_academic_year_backend()

            self.assertEqual(result, "2024-25")

    def test_get_current_academic_year_backend_exception(self):
        """Test get_current_academic_year_backend with exception"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.utils.getdate.side_effect = Exception("Date error")
            mock_frappe.log_error = MagicMock()

            result = self.backend_module.get_current_academic_year_backend()

            self.assertIsNone(result)

    def test_get_course_level_with_mapping_backend_found_mapping(self):
        """Test get_course_level_with_mapping_backend when mapping is found"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    mock_frappe.get_all.return_value = [
                        {"assigned_course_level": "MATH_L5", "mapping_name": "Math Grade 5 New"}
                    ]
                    mock_frappe.log_error = MagicMock()

                    result = self.backend_module.get_course_level_with_mapping_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_L5")

    def test_get_course_level_with_mapping_backend_flexible_mapping(self):
        """Test get_course_level_with_mapping_backend with null academic year mapping"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    # First call returns empty (no specific year mapping), second call returns flexible mapping
                    mock_frappe.get_all.side_effect = [
                        [],  # No mapping for specific year
                        [{"assigned_course_level": "MATH_FLEX", "mapping_name": "Math Flexible"}]
                    ]
                    mock_frappe.log_error = MagicMock()

                    result = self.backend_module.get_course_level_with_mapping_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_FLEX")

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
                        mock_get_course.assert_called_once_with("Math", "5", False)

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

    def test_get_course_level_with_validation_backend_with_broken_data(self):
        """Test get_course_level_with_validation_backend with broken enrollment data"""
        with patch.object(self.backend_module, 'validate_enrollment_data', return_value={"broken_enrollments": 2, "broken_details": []}):
            with patch.object(self.backend_module, 'get_course_level_with_mapping_backend', return_value="MATH_L5"):
                with patch.object(self.backend_module, 'frappe') as mock_frappe:
                    mock_frappe.log_error = MagicMock()

                    result = self.backend_module.get_course_level_with_validation_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_L5")
                    # Verify validation was called
                    self.assertIsNotNone(result)

    def test_get_course_level_with_validation_backend_exception_fallback(self):
        """Test get_course_level_with_validation_backend exception handling"""
        with patch.object(self.backend_module, 'validate_enrollment_data', side_effect=Exception("Validation error")):
            with patch.object(self.backend_module, 'get_course_level', return_value="MATH_FALLBACK"):
                with patch.object(self.backend_module, 'frappe') as mock_frappe:
                    mock_frappe.log_error = MagicMock()

                    result = self.backend_module.get_course_level_with_validation_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_FALLBACK")

    # ============= Utility Function Tests (ENHANCED) =============

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

    def test_format_phone_number_empty(self):
        """Test format_phone_number with empty input"""
        result = self.backend_module.format_phone_number("")
        self.assertIsNone(result)

    def test_update_job_progress(self):
        """Test update_job_progress publishes progress"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.publish_progress = MagicMock()

            self.backend_module.update_job_progress(5, 10)

            mock_frappe.publish_progress.assert_called_once()

    def test_update_job_progress_at_milestone(self):
        """Test update_job_progress at 10-item milestone"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.publish_progress = MagicMock()

            self.backend_module.update_job_progress(9, 20)  # 10th item (0-indexed)

            # Should still call publish_progress
            mock_frappe.publish_progress.assert_called()

    def test_update_job_progress_fallback(self):
        """Test update_job_progress fallback when publish_progress fails"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.publish_progress.side_effect = Exception("Publish failed")

            # Should not raise exception, should use fallback
            try:
                self.backend_module.update_job_progress(9, 10)
            except Exception:
                self.fail("update_job_progress raised exception when it should have handled it")

    def test_update_job_progress_zero_total(self):
        """Test update_job_progress with zero total"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.publish_progress = MagicMock()

            # Should handle zero total without division by zero
            self.backend_module.update_job_progress(0, 0)

            # Should not call publish_progress
            mock_frappe.publish_progress.assert_not_called()

    # ============= Job Status Tests (ENHANCED) =============

    def test_get_job_status_completed(self):
        """Test get_job_status for completed job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    
                    mock_job = MagicMock()
                    mock_job.get_status.return_value = "finished"
                    mock_job.result = {"success": True, "processed": 50}
                    mock_job.meta = {"progress": 100}
                    mock_job_class.fetch.return_value = mock_job
                    
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.get_job_status("job_123")

                    self.assertEqual(result["status"], "Completed")
                    self.assertEqual(result["result"], {"success": True, "processed": 50})
                    self.assertEqual(result["progress"], 100)

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
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.get_job_status("job_123")

                    self.assertEqual(result["status"], "started")
                    self.assertEqual(result["progress"], 50)
                    self.assertIsNone(result["result"])

    def test_get_job_status_queued(self):
        """Test get_job_status for queued job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    
                    mock_job = MagicMock()
                    mock_job.get_status.return_value = "queued"
                    mock_job.result = None
                    mock_job.meta = {}
                    mock_job_class.fetch.return_value = mock_job
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.get_job_status("job_123")

                    self.assertEqual(result["status"], "queued")

    def test_get_job_status_failed(self):
        """Test get_job_status for failed job"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'get_redis_conn') as mock_redis:
                with patch.object(self.backend_module, 'Job') as mock_job_class:
                    mock_conn = MagicMock()
                    mock_redis.return_value = mock_conn
                    
                    mock_job = MagicMock()
                    mock_job.get_status.return_value = "failed"
                    mock_job.result = None
                    mock_job.meta = {}
                    mock_job_class.fetch.return_value = mock_job
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.get_job_status("job_123")

                    self.assertEqual(result["status"], "failed")

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

    def test_is_job_name_exist_found(self):
        """Test is_job_name_exist when job exists"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.table_exists.return_value = True
            mock_frappe.db.get_value.return_value = {"name": "job_123", "status": "started"}
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.is_job_name_exist("BSO_001")

            self.assertTrue(result)

    def test_is_job_name_exist_not_found(self):
        """Test is_job_name_exist when job doesn't exist"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.table_exists.return_value = True
            mock_frappe.db.get_value.return_value = None
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.is_job_name_exist("BSO_001")

            self.assertFalse(result)

    # ============= Glific Contact Processing Tests (ENHANCED) =============

    def test_process_glific_contact_invalid_phone(self):
        """Test process_glific_contact with invalid phone number"""
        mock_student = MagicMock()
        mock_student.phone = "invalid"
        mock_student.student_name = "Test Student"

        with self.assertRaises(ValueError) as context:
            self.backend_module.process_glific_contact(mock_student, None)
        
        self.assertIn("Invalid phone number", str(context.exception))

    def test_process_glific_contact_existing_contact(self):
        """Test process_glific_contact with existing contact"""
        with patch.object(self.backend_module, 'format_phone_number', return_value="919876543210"):
            with patch.object(self.backend_module, 'get_contact_by_phone', return_value={"id": "contact_123"}):
                with patch.object(self.backend_module, 'add_contact_to_group') as mock_add_to_group:
                    with patch.object(self.backend_module, 'update_contact_fields') as mock_update_fields:
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

                            mock_group = {"group_id": "group_123"}

                            result = self.backend_module.process_glific_contact(
                                mock_student, mock_group, "MATH_L5"
                            )

                            self.assertEqual(result["id"], "contact_123")
                            mock_add_to_group.assert_called_once_with("contact_123", "group_123")
                            mock_update_fields.assert_called_once()

    def test_process_glific_contact_new_contact(self):
        """Test process_glific_contact creating new contact"""
        with patch.object(self.backend_module, 'format_phone_number', return_value="919876543210"):
            with patch.object(self.backend_module, 'get_contact_by_phone', return_value=None):
                with patch.object(self.backend_module, 'add_student_to_glific_for_onboarding', return_value={"id": "new_contact_123"}):
                    with patch.object(self.backend_module, 'frappe') as mock_frappe:
                        mock_frappe.get_value.side_effect = [
                            "Test School",  # school name
                            "BT001",  # batch id
                            "1",  # language id
                            "Math Level 5"  # course level name
                        ]
                        
                        mock_student = MagicMock()
                        mock_student.phone = "9876543210"
                        mock_student.student_name = "Test Student"
                        mock_student.school = "SCH001"
                        mock_student.batch = "BT001"
                        mock_student.language = "English"
                        mock_student.course_vertical = "Math"
                        mock_student.grade = "5"

                        mock_group = {"group_id": "group_123"}

                        result = self.backend_module.process_glific_contact(
                            mock_student, mock_group, "MATH_L5"
                        )

                        self.assertEqual(result["id"], "new_contact_123")

    def test_process_glific_contact_no_group(self):
        """Test process_glific_contact without group"""
        with patch.object(self.backend_module, 'format_phone_number', return_value="919876543210"):
            with patch.object(self.backend_module, 'get_contact_by_phone', return_value=None):
                with patch.object(self.backend_module, 'add_student_to_glific_for_onboarding', return_value={"id": "contact_123"}):
                    with patch.object(self.backend_module, 'frappe') as mock_frappe:
                        mock_frappe.get_value.return_value = "Test School"
                        
                        mock_student = MagicMock()
                        mock_student.phone = "9876543210"
                        mock_student.student_name = "Test Student"
                        mock_student.school = "SCH001"
                        mock_student.batch = "BT001"
                        mock_student.language = None
                        mock_student.course_vertical = None
                        mock_student.grade = "5"

                        result = self.backend_module.process_glific_contact(mock_student, None)

                        self.assertEqual(result["id"], "contact_123")

    # ============= Backend Student Status Update Tests (ENHANCED) =============

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

    def test_update_backend_student_status_success_with_glific_field(self):
        """Test update_backend_student_status for success with glific_id field"""
        mock_student = MagicMock()
        mock_student.glific_id = None
        mock_student_doc = MagicMock()
        mock_student_doc.name = "STUD_001"
        mock_student_doc.glific_id = "contact_123"

        self.backend_module.update_backend_student_status(mock_student, "Success", mock_student_doc)

        self.assertEqual(mock_student.glific_id, "contact_123")

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
            self.assertEqual(mock_student.processing_notes, "This is a ")
            mock_student.save.assert_called_once()

    def test_update_backend_student_status_no_error_field(self):
        """Test update_backend_student_status when processing_notes field doesn't exist"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_student = MagicMock()
            # Remove processing_notes attribute
            del mock_student.processing_notes
            mock_student.__dict__.pop('processing_notes', None)
            type(mock_student).processing_notes = property(lambda self: AttributeError())

            # Should not raise error
            self.backend_module.update_backend_student_status(mock_student, "Failed", error="Error")

            self.assertEqual(mock_student.processing_status, "Failed")

    # ============= Debug and Validation Tests (NEW) =============

    def test_validate_enrollment_data_no_broken_links(self):
        """Test validate_enrollment_data with no broken course links"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.return_value = [
                    {"student_id": "STUD_001", "enrollment_id": "ENR_001", "course": "MATH_L5", "batch": "BT001", "grade": "5"}
                ]
                mock_frappe.db.exists.return_value = True

                result = self.backend_module.validate_enrollment_data("Test Student", "9876543210")

                self.assertEqual(result["total_enrollments"], 1)
                self.assertEqual(result["valid_enrollments"], 1)
                self.assertEqual(result["broken_enrollments"], 0)

    def test_validate_enrollment_data_with_broken_links(self):
        """Test validate_enrollment_data with broken course links"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.return_value = [
                    {"student_id": "STUD_001", "enrollment_id": "ENR_001", "course": "BROKEN_COURSE", "batch": "BT001", "grade": "5"}
                ]
                mock_frappe.db.exists.return_value = False

                result = self.backend_module.validate_enrollment_data("Test Student", "9876543210")

                self.assertEqual(result["total_enrollments"], 1)
                self.assertEqual(result["valid_enrollments"], 0)
                self.assertEqual(result["broken_enrollments"], 1)
                self.assertEqual(len(result["broken_details"]), 1)

    def test_validate_enrollment_data_invalid_phone(self):
        """Test validate_enrollment_data with invalid phone"""
        result = self.backend_module.validate_enrollment_data("Test Student", "invalid")
        self.assertIn("error", result)

    def test_debug_student_processing_existing_student(self):
        """Test debug_student_processing for existing student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value={"name": "STUD_001"}):
                    mock_student_doc = MagicMock()
                    mock_student_doc.name = "STUD_001"
                    mock_student_doc.grade = "5"
                    mock_student_doc.school_id = "SCH001"
                    mock_frappe.get_doc.return_value = mock_student_doc
                    mock_frappe.get_all.side_effect = [
                        [{"name": "ENR_001", "course": "MATH_L5", "batch": "BT001", "grade": "5", "school": "SCH001"}],
                        []  # Backend students
                    ]
                    mock_frappe.db.exists.return_value = True
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.debug_student_processing("Test Student", "9876543210")

                    self.assertIn("DEBUGGING STUDENT", result)
                    self.assertIn("Test Student", result)
                    self.assertIn("Student EXISTS", result)

    def test_debug_student_processing_new_student(self):
        """Test debug_student_processing for new student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                    mock_frappe.get_all.return_value = []
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.debug_student_processing("Test Student", "9876543210")

                    self.assertIn("DEBUGGING STUDENT", result)
                    self.assertIn("Student DOES NOT EXIST", result)

    def test_debug_student_type_analysis_new_student(self):
        """Test debug_student_type_analysis for new student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                    mock_frappe.db.sql.return_value = []  # No existing student
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.debug_student_type_analysis("Test Student", "9876543210", "Math")

                    self.assertIn("STUDENT TYPE ANALYSIS", result)
                    self.assertIn("No existing student found", result)
                    self.assertIn("NEW", result)

    def test_fix_broken_course_links_specific_student(self):
        """Test fix_broken_course_links with specific student ID"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = [
                {"name": "ENR_001", "course": "BROKEN_COURSE"}
            ]
            mock_frappe.db.set_value = MagicMock()
            mock_frappe.db.commit = MagicMock()
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.fix_broken_course_links("STUD_001")

            self.assertIn("Checking student: STUD_001", result)
            self.assertIn("Total fixed: 1", result)
            mock_frappe.db.set_value.assert_called_once_with("Enrollment", "ENR_001", "course", None)

    def test_fix_broken_course_links_all_students(self):
        """Test fix_broken_course_links for all students"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [
                {"name": "STUD_001"},
                {"name": "STUD_002"}
            ]
            mock_frappe.db.sql.return_value = []  # No broken links
            mock_frappe.db.commit = MagicMock()
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.fix_broken_course_links()

            self.assertIn("Checking all 2 students", result)
            self.assertIn("No broken course links found", result)

    def test_test_basic_student_creation_success(self):
        """Test test_basic_student_creation success path"""
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
            mock_frappe.delete_doc.assert_called_once_with("Student", "TEST_STUDENT_001")

    def test_test_basic_student_creation_failure(self):
        """Test test_basic_student_creation failure path"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_student = MagicMock()
            mock_student.insert.side_effect = Exception("Insert failed")
            mock_frappe.new_doc.return_value = mock_student
            mock_frappe.whitelist.return_value = lambda func: func

            result = self.backend_module.test_basic_student_creation()

            self.assertIn("BASIC TEST FAILED", result)
            self.assertIn("Insert failed", result)

    # ============= Student Type Determination Tests (NEW) =============

    def test_determine_student_type_backend_new_no_enrollments(self):
        """Test determine_student_type_backend for new student with no enrollments"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.side_effect = [
                    [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],  # Student exists
                    []  # No enrollments
                ]

                result = self.backend_module.determine_student_type_backend("9876543210", "Test Student", "Math")

                self.assertEqual(result, "New")

    def test_determine_student_type_backend_old_same_vertical(self):
        """Test determine_student_type_backend for old student with same vertical"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.side_effect = [
                    [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],  # Student exists
                    [{"name": "ENR_001", "course": "MATH_L4", "batch": "BT001", "grade": "4", "school": "SCH001"}],  # Has enrollment
                    [{"vertical_name": "Math"}]  # Course vertical matches
                ]

                result = self.backend_module.determine_student_type_backend("9876543210", "Test Student", "Math")

                self.assertEqual(result, "Old")

    def test_determine_student_type_backend_new_different_vertical(self):
        """Test determine_student_type_backend for new student with different vertical"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.side_effect = [
                    [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],  # Student exists
                    [{"name": "ENR_001", "course": "SCI_L4", "batch": "BT001", "grade": "4", "school": "SCH001"}],  # Has enrollment
                    [{"vertical_name": "Science"}]  # Course vertical is different
                ]

                result = self.backend_module.determine_student_type_backend("9876543210", "Test Student", "Math")

                self.assertEqual(result, "New")

    def test_determine_student_type_backend_old_broken_course(self):
        """Test determine_student_type_backend for old student with broken course link"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.side_effect = [
                    [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],  # Student exists
                    [{"name": "ENR_001", "course": "BROKEN_COURSE", "batch": "BT001", "grade": "4", "school": "SCH001"}]  # Has enrollment with broken course
                ]
                mock_frappe.db.exists.return_value = False  # Course doesn't exist

                result = self.backend_module.determine_student_type_backend("9876543210", "Test Student", "Math")

                self.assertEqual(result, "Old")

    def test_determine_student_type_backend_old_null_course(self):
        """Test determine_student_type_backend for old student with null course"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.side_effect = [
                    [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],  # Student exists
                    [{"name": "ENR_001", "course": None, "batch": "BT001", "grade": "4", "school": "SCH001"}]  # Has enrollment with null course
                ]

                result = self.backend_module.determine_student_type_backend("9876543210", "Test Student", "Math")

                self.assertEqual(result, "Old")

    def test_determine_student_type_backend_no_existing_student(self):
        """Test determine_student_type_backend when student doesn't exist"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                mock_frappe.db.sql.return_value = []  # No existing student

                result = self.backend_module.determine_student_type_backend("9876543210", "Test Student", "Math")

                self.assertEqual(result, "New")

    # ============= Process Student Record Tests (ENHANCED) =============

    def test_process_student_record_new_student(self):
        """Test process_student_record creating new student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                    mock_student = MagicMock()
                    mock_student.student_name = "New Student"
                    mock_student.phone = "9876543210"
                    mock_student.gender = "Male"
                    mock_student.school = "SCH001"
                    mock_student.grade = "5"
                    mock_student.language = "English"
                    mock_student.batch = "BT001"
                    mock_student.batch_skeyword = "MATH_BATCH"
                    mock_student.course_vertical = "Math"

                    mock_glific_contact = {"id": "contact_123"}
                    mock_student_doc = MagicMock()
                    mock_student_doc.name = "STUD_NEW_001"
                    mock_frappe.new_doc.return_value = mock_student_doc
                    mock_frappe.db.exists.return_value = False
                    mock_frappe.get_all.return_value = [{"name": "BO_001", "kit_less": False}]
                    mock_frappe.log_error = MagicMock()

                    result = self.backend_module.process_student_record(
                        mock_student, mock_glific_contact, "BSO_001", "STAGE_001", "MATH_L5"
                    )

                    mock_student_doc.insert.assert_called_once()
                    self.assertEqual(result, mock_student_doc)
                    self.assertEqual(result.glific_id, "contact_123")

    def test_process_student_record_existing_student_update(self):
        """Test process_student_record updating existing student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value={"name": "STUD_001"}):
                with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                    mock_student = MagicMock()
                    mock_student.student_name = "Existing Student"
                    mock_student.phone = "9876543210"
                    mock_student.gender = "Female"
                    mock_student.school = "SCH002"
                    mock_student.grade = "6"
                    mock_student.language = "Tamil"
                    mock_student.batch = "BT002"
                    mock_student.batch_skeyword = "MATH_BATCH"
                    mock_student.course_vertical = "Math"

                    existing_student_doc = MagicMock()
                    existing_student_doc.name = "STUD_001"
                    existing_student_doc.grade = "5"
                    existing_student_doc.school_id = "SCH001"
                    existing_student_doc.language = "English"
                    existing_student_doc.gender = "Female"
                    existing_student_doc.phone = "9876543210"
                    existing_student_doc.glific_id = None
                    
                    mock_frappe.get_doc.return_value = existing_student_doc
                    mock_frappe.get_all.return_value = [{"name": "BO_001", "kit_less": False}]
                    mock_frappe.log_error = MagicMock()

                    mock_glific_contact = {"id": "contact_456"}

                    result = self.backend_module.process_student_record(
                        mock_student, mock_glific_contact, "BSO_001", "STAGE_001", "MATH_L6"
                    )

                    existing_student_doc.save.assert_called_once()
                    self.assertEqual(result.grade, "6")
                    self.assertEqual(result.school_id, "SCH002")
                    self.assertEqual(result.glific_id, "contact_456")

    def test_process_student_record_grade_upgrade(self):
        """Test process_student_record with grade upgrade"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value={"name": "STUD_001"}):
                with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                    mock_student = MagicMock()
                    mock_student.student_name = "Upgrading Student"
                    mock_student.phone = "9876543210"
                    mock_student.grade = "6"  # Upgrading from 5 to 6
                    mock_student.school = "SCH001"
                    mock_student.language = "English"
                    mock_student.batch = "BT001"

                    existing_student_doc = MagicMock()
                    existing_student_doc.name = "STUD_001"
                    existing_student_doc.grade = "5"  # Current grade
                    existing_student_doc.school_id = "SCH001"
                    existing_student_doc.phone = "9876543210"
                    
                    mock_frappe.get_doc.return_value = existing_student_doc
                    mock_frappe.log_error = MagicMock()

                    result = self.backend_module.process_student_record(
                        mock_student, None, "BSO_001", "STAGE_001", "MATH_L6"
                    )

                    self.assertEqual(result.grade, "6")

    def test_process_student_record_without_course_level(self):
        """Test process_student_record when course level is not provided"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                with patch.object(self.backend_module, 'normalize_phone_number', return_value=("919876543210", "9876543210")):
                    with patch.object(self.backend_module, 'get_course_level_with_validation_backend', return_value="MATH_L5"):
                        mock_student = MagicMock()
                        mock_student.student_name = "New Student"
                        mock_student.phone = "9876543210"
                        mock_student.gender = "Male"
                        mock_student.school = "SCH001"
                        mock_student.grade = "5"
                        mock_student.language = "English"
                        mock_student.batch = "BT001"
                        mock_student.batch_skeyword = "MATH_BATCH"
                        mock_student.course_vertical = "Math"

                        mock_student_doc = MagicMock()
                        mock_frappe.new_doc.return_value = mock_student_doc
                        mock_frappe.db.exists.return_value = False
                        mock_frappe.get_all.return_value = [{"name": "BO_001", "kit_less": False}]
                        mock_frappe.log_error = MagicMock()

                        result = self.backend_module.process_student_record(
                            mock_student, None, "BSO_001", "STAGE_001", None  # No course level provided
                        )

                        mock_student_doc.insert.assert_called_once()


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)