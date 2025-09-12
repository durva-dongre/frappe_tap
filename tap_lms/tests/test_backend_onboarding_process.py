import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, date
import sys
import os
import json

# Add the project root to Python path if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(_file_))))

class TestBackendOnboardingFunctions(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_phone_10 = "9876543210"
        self.mock_phone_12 = "919876543210"
        self.mock_student_name = "Test Student"
        self.mock_batch_id = "BATCH001"
        self.current_date = date(2025, 8, 20)

        # Mock frappe module at module level
        self.frappe_patcher = patch.dict('sys.modules', {
            'frappe': MagicMock(),
            'frappe.utils': MagicMock(),
            'tap_lms.glific_integration': MagicMock(),
            'tap_lms.api': MagicMock()
        })
        self.frappe_patcher.start()

        # Import after patching
        from tap_lms.page.backend_onboarding_process.backend_onboarding_process import (
            normalize_phone_number,
            find_existing_student_by_phone_and_name,
            get_onboarding_batches,
            get_batch_details,
            validate_student,
            get_onboarding_stages,
            get_initial_stage,
            get_current_academic_year_backend,
            get_job_status,
            process_batch
        )

        # Store references to the actual functions
        self.normalize_phone_number = normalize_phone_number
        self.find_existing_student_by_phone_and_name = find_existing_student_by_phone_and_name
        self.get_onboarding_batches = get_onboarding_batches
        self.get_batch_details = get_batch_details
        self.validate_student = validate_student
        self.get_onboarding_stages = get_onboarding_stages
        self.get_initial_stage = get_initial_stage
        self.get_current_academic_year_backend = get_current_academic_year_backend
        self.get_job_status = get_job_status
        self.process_batch = process_batch

    def tearDown(self):
        """Clean up after each test."""
        self.frappe_patcher.stop()

    # Phone Number Normalization Tests
    def test_normalize_phone_number_10_digit(self):
        """Test normalizing 10-digit phone number"""
        phone_12, phone_10 = self.normalize_phone_number("9876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")

    def test_normalize_phone_number_12_digit(self):
        """Test normalizing 12-digit phone number"""
        phone_12, phone_10 = self.normalize_phone_number("919876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")

    def test_normalize_phone_number_11_digit_with_1_prefix(self):
        """Test normalizing 11-digit phone number starting with 1"""
        phone_12, phone_10 = self.normalize_phone_number("19876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")

    def test_normalize_phone_number_with_formatting(self):
        """Test normalizing phone number with formatting characters"""
        phone_12, phone_10 = self.normalize_phone_number("(987) 654-3210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")

    def test_normalize_phone_number_invalid_length(self):
        """Test normalizing invalid phone number length"""
        phone_12, phone_10 = self.normalize_phone_number("12345")
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)

    def test_normalize_phone_number_none_input(self):
        """Test normalizing None phone number"""
        phone_12, phone_10 = self.normalize_phone_number(None)
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)

    def test_normalize_phone_number_empty_string(self):
        """Test normalizing empty phone number"""
        phone_12, phone_10 = self.normalize_phone_number("")
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)

    def test_normalize_phone_number_spaces_and_dashes(self):
        """Test normalizing phone number with various formatting"""
        test_cases = [
            ("987-654-3210", "919876543210", "9876543210"),
            ("987 654 3210", "919876543210", "9876543210"),
            ("91 9876543210", "919876543210", "9876543210"),
            ("91-9876543210", "919876543210", "9876543210"),
        ]
        
        for input_phone, expected_12, expected_10 in test_cases:
            with self.subTest(phone=input_phone):
                phone_12, phone_10 = self.normalize_phone_number(input_phone)
                self.assertEqual(phone_12, expected_12)
                self.assertEqual(phone_10, expected_10)

    # Student Finding Tests
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_find_existing_student_success(self, mock_frappe):
        """Test successfully finding existing student"""
        mock_student_data = {
            'name': 'STU001',
            'phone': '919876543210',
            'name1': 'Test Student'
        }
        mock_frappe.db.sql.return_value = [mock_student_data]

        result = self.find_existing_student_by_phone_and_name("919876543210", "Test Student")

        self.assertEqual(result, mock_student_data)
        self.assertTrue(mock_frappe.db.sql.called)

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_find_existing_student_not_found(self, mock_frappe):
        """Test when student is not found"""
        mock_frappe.db.sql.return_value = []

        result = self.find_existing_student_by_phone_and_name("919876543210", "Test Student")

        self.assertIsNone(result)

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_find_existing_student_invalid_phone(self, mock_frappe):
        """Test with invalid phone input"""
        result = self.find_existing_student_by_phone_and_name(None, "Test Student")
        self.assertIsNone(result)

        result = self.find_existing_student_by_phone_and_name("919876543210", None)
        self.assertIsNone(result)

    # Batch Management Tests
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_onboarding_batches_success(self, mock_frappe):
        """Test successfully getting onboarding batches"""
        mock_batches = [
            {
                'name': 'BATCH001',
                'set_name': 'Test Batch 1',
                'upload_date': self.current_date,
                'uploaded_by': 'test_user',
                'student_count': 10,
                'processed_student_count': 5
            }
        ]
        mock_frappe.get_all.return_value = mock_batches

        result = self.get_onboarding_batches()

        self.assertEqual(result, mock_batches)
        mock_frappe.get_all.assert_called_with(
            "Backend Student Onboarding", 
            filters={"status": ["in", ["Draft", "Processing", "Failed"]]},
            fields=["name", "set_name", "upload_date", "uploaded_by", 
                   "student_count", "processed_student_count"]
        )

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_batch_details_success(self, mock_frappe):
        """Test successfully getting batch details"""
        mock_batch = Mock()
        mock_batch.name = 'BATCH001'
        mock_batch.status = 'Draft'

        mock_students = [
            {
                'name': 'BACKEND_STU001',
                'student_name': 'Test Student',
                'phone': '919876543210',
                'gender': 'Male',
                'batch': 'BT001',
                'course_vertical': 'CV001',
                'grade': '5',
                'school': 'SCH001',
                'language': 'LANG_EN',
                'processing_status': 'Pending',
                'student_id': None
            }
        ]

        mock_frappe.get_doc.return_value = mock_batch
        mock_frappe.get_all.side_effect = [mock_students, []]  # students, then glific_group

        result = self.get_batch_details('BATCH001')

        self.assertEqual(result['batch'], mock_batch)
        self.assertEqual(len(result['students']), 1)
        self.assertIn('validation', result['students'][0])
        self.assertIsNone(result['glific_group'])

    # Student Validation Tests
    def test_validate_student_complete(self):
        """Test validating a complete student record"""
        complete_student = {
            'student_name': 'Test Student',
            'phone': '919876543210',
            'school': 'SCH001',
            'grade': '5',
            'language': 'LANG_EN',
            'batch': 'BT001'
        }

        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name') as mock_find:
            mock_find.return_value = None
            
            validation = self.validate_student(complete_student)
            
            self.assertEqual(validation, {})

    def test_validate_student_missing_fields(self):
        """Test validating student with missing required fields"""
        incomplete_student = {
            'student_name': '',
            'phone': '919876543210',
            'school': '',
            'grade': '5',
            'language': 'LANG_EN',
            'batch': 'BT001'
        }

        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name') as mock_find:
            mock_find.return_value = None
            
            validation = self.validate_student(incomplete_student)
            
            self.assertIn('student_name', validation)
            self.assertEqual(validation['student_name'], 'missing')
            self.assertIn('school', validation)
            self.assertEqual(validation['school'], 'missing')

    def test_validate_student_duplicate(self):
        """Test validating student with duplicate"""
        student = {
            'student_name': 'Test Student',
            'phone': '919876543210',
            'school': 'SCH001',
            'grade': '5',
            'language': 'LANG_EN',
            'batch': 'BT001'
        }

        existing_student = {
            'name': 'STU001',
            'name1': 'Test Student'
        }

        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name') as mock_find:
            mock_find.return_value = existing_student
            
            validation = self.validate_student(student)
            
            self.assertIn('duplicate', validation)
            self.assertEqual(validation['duplicate']['student_id'], 'STU001')
            self.assertEqual(validation['duplicate']['student_name'], 'Test Student')

    # Onboarding Stages Tests
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_onboarding_stages_success(self, mock_frappe):
        """Test successfully getting onboarding stages"""
        mock_frappe.db.table_exists.return_value = True
        mock_stages = [
            {'name': 'STAGE001', 'description': 'Initial Stage', 'order': 0},
            {'name': 'STAGE002', 'description': 'Second Stage', 'order': 1}
        ]
        mock_frappe.get_all.return_value = mock_stages

        result = self.get_onboarding_stages()

        self.assertEqual(result, mock_stages)

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_onboarding_stages_table_not_exists(self, mock_frappe):
        """Test when OnboardingStage table doesn't exist"""
        mock_frappe.db.table_exists.return_value = False

        result = self.get_onboarding_stages()

        self.assertEqual(result, [])

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_onboarding_stages_exception(self, mock_frappe):
        """Test exception handling in get_onboarding_stages"""
        mock_frappe.db.table_exists.return_value = True
        mock_frappe.get_all.side_effect = Exception("Database error")

        result = self.get_onboarding_stages()

        self.assertEqual(result, [])
        self.assertTrue(mock_frappe.log_error.called)

    # Initial Stage Tests
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_initial_stage_with_order_zero(self, mock_frappe):
        """Test getting initial stage with order=0"""
        mock_frappe.get_all.side_effect = [
            [{'name': 'STAGE_INITIAL'}],  # First call with order=0
        ]

        result = self.get_initial_stage()

        self.assertEqual(result, 'STAGE_INITIAL')

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_initial_stage_no_order_zero(self, mock_frappe):
        """Test getting initial stage when no order=0 exists"""
        mock_frappe.get_all.side_effect = [
            [],  # First call with order=0 returns empty
            [{'name': 'STAGE_MIN', 'order': 1}],  # Second call with minimum order
        ]

        result = self.get_initial_stage()

        self.assertEqual(result, 'STAGE_MIN')

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_initial_stage_exception(self, mock_frappe):
        """Test exception handling in get_initial_stage"""
        mock_frappe.get_all.side_effect = Exception("Database error")

        result = self.get_initial_stage()

        self.assertIsNone(result)
        self.assertTrue(mock_frappe.log_error.called)

    # Academic Year Tests
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_current_academic_year_after_april(self, mock_frappe):
        """Test academic year calculation when current date is after April"""
        mock_frappe.utils.getdate.return_value = date(2025, 8, 20)

        result = self.get_current_academic_year_backend()

        self.assertEqual(result, "2025-26")

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_current_academic_year_before_april(self, mock_frappe):
        """Test academic year calculation when current date is before April"""
        mock_frappe.utils.getdate.return_value = date(2025, 2, 20)

        result = self.get_current_academic_year_backend()

        self.assertEqual(result, "2024-25")

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_current_academic_year_exception(self, mock_frappe):
        """Test exception handling in academic year calculation"""
        mock_frappe.utils.getdate.side_effect = Exception("Date error")

        result = self.get_current_academic_year_backend()

        self.assertIsNone(result)
        self.assertTrue(mock_frappe.log_error.called)

    # Job Status Tests
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_job_status_success(self, mock_frappe):
        """Test getting job status successfully"""
        mock_frappe.db.table_exists.return_value = True
        mock_frappe.db.get_value.return_value = {
            'status': 'finished',
            'progress_data': None,
            'result': '{"success_count": 5, "failure_count": 0}'
        }

        result = self.get_job_status('job123')

        self.assertIn('status', result)

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_get_job_status_unknown(self, mock_frappe):
        """Test getting job status when status is unknown"""
        mock_frappe.db.table_exists.return_value = False

        result = self.get_job_status('job123')

        self.assertEqual(result['status'], 'Unknown')

    # Process Batch Tests
    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_process_batch_background_job(self, mock_frappe):
        """Test processing batch with background job"""
        mock_batch = Mock()
        mock_batch.status = 'Draft'
        mock_frappe.get_doc.return_value = mock_batch

        mock_job = Mock()
        mock_job.id = 'job123'
        mock_frappe.enqueue.return_value = mock_job

        result = self.process_batch('BATCH001', use_background_job=True)

        self.assertEqual(result['job_id'], 'job123')
        self.assertEqual(mock_batch.status, 'Processing')
        self.assertTrue(mock_batch.save.called)

    @patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.frappe')
    def test_process_batch_immediate(self, mock_frappe):
        """Test processing batch immediately"""
        mock_batch = Mock()
        mock_batch.status = 'Draft'
        mock_frappe.get_doc.return_value = mock_batch

        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.process_batch_job') as mock_job:
            mock_job.return_value = {'success_count': 5, 'failure_count': 0}

            result = self.process_batch('BATCH001', use_background_job=False)

            self.assertEqual(result['success_count'], 5)
            self.assertEqual(result['failure_count'], 0)

    # Edge Cases Tests
    def test_validate_all_missing_fields(self):
        """Test validation when all required fields are missing"""
        empty_student = {
            'student_name': '',
            'phone': '',
            'school': '',
            'grade': '',
            'language': '',
            'batch': ''
        }

        with patch('tap_lms.page.backend_onboarding_process.backend_onboarding_process.find_existing_student_by_phone_and_name') as mock_find:
            mock_find.return_value = None
            
            validation = self.validate_student(empty_student)
            
            required_fields = ['student_name', 'phone', 'school', 'grade', 'language', 'batch']
            for field in required_fields:
                self.assertIn(field, validation)
                self.assertEqual(validation[field], 'missing')

# if _name_ == '_main_':
#     unittest.main(verbosity=2)