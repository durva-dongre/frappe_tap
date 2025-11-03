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
    
    # FIXED: Mock frappe with proper structure before loading the module
    mock_frappe = MagicMock()
    mock_frappe_utils = MagicMock()
    
    # Set up utils functions
    mock_frappe_utils.nowdate = MagicMock(return_value="2025-01-01")
    mock_frappe_utils.nowtime = MagicMock(return_value="10:00:00")
    mock_frappe_utils.now = MagicMock(return_value="2025-01-01 10:00:00")
    mock_frappe_utils.getdate = MagicMock()
    
    # Link utils to frappe (CRITICAL FIX)
    mock_frappe.utils = mock_frappe_utils
    mock_frappe.whitelist = MagicMock(return_value=lambda func: func)
    mock_frappe._ = MagicMock(side_effect=lambda x: x)  # Translation function
    
    # Install all mocks
    sys.modules['frappe'] = mock_frappe
    sys.modules['frappe.utils'] = mock_frappe_utils
    sys.modules['frappe.utils.background_jobs'] = MagicMock()
    sys.modules['tap_lms.glific_integration'] = MagicMock()
    sys.modules['tap_lms.api'] = MagicMock()
    sys.modules['rq'] = MagicMock()
    sys.modules['rq.job'] = MagicMock()
    sys.modules['rq.registry'] = MagicMock()
    
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

    # ============= Batch Management Tests =============

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
            mock_frappe.log_error = MagicMock()

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
            mock_frappe.log_error = MagicMock()

            result = self.backend_module.get_initial_stage()

            self.assertEqual(result, "STAGE_MIN")

    def test_get_initial_stage_no_stages(self):
        """Test get_initial_stage with no stages"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = []

            result = self.backend_module.get_initial_stage()

            self.assertIsNone(result)

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
                    mock_job.result = {"success": True, "processed": 50}
                    mock_job.meta = {"progress": 100}
                    mock_job_class.fetch.return_value = mock_job
                    
                    mock_frappe.whitelist.return_value = lambda func: func

                    result = self.backend_module.get_job_status("job_123")

                    self.assertEqual(result["status"], "Completed")
                    self.assertEqual(result["result"], {"success": True, "processed": 50})
                    self.assertEqual(result["progress"], 100)

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


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)