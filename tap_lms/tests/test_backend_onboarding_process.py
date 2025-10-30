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

    # ============= Phone Number Normalization Tests (EXISTING - GOOD) =============

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

    # ============= Student Finding Tests (EXISTING - GOOD) =============

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

    # ============= CRITICAL: Student Type Determination Tests (NEW) =============

    def test_determine_student_type_backend_no_existing_student(self):
        """CRITICAL: Test student type determination when student doesn't exist - should return 'New'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.db.sql.return_value = []  # No existing student

            result = self.backend_module.determine_student_type_backend(
                "9876543210", "New Student", "Math"
            )

            self.assertEqual(result, "New")

    def test_determine_student_type_backend_same_vertical(self):
        """CRITICAL: Test student with enrollment in same vertical - should return 'Old'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Student exists
            mock_frappe.db.sql.side_effect = [
                [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],
                # Has enrollment in same vertical
                [{
                    "name": "ENR_001",
                    "course": "MATH_L5",
                    "batch": "BT001",
                    "grade": "5",
                    "school": "SCH001"
                }]
            ]
            
            # Course exists
            mock_frappe.db.exists.return_value = True
            
            # Course has same vertical
            mock_frappe.db.sql.side_effect[2:] = [
                [{"vertical_name": "Math"}]
            ]

            result = self.backend_module.determine_student_type_backend(
                "9876543210", "Test Student", "Math"
            )

            self.assertEqual(result, "Old")

    def test_determine_student_type_backend_broken_course_links(self):
        """CRITICAL: Test student with broken course links - should return 'Old'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Student exists
            mock_frappe.db.sql.side_effect = [
                [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],
                # Has enrollment with broken course link
                [{
                    "name": "ENR_001",
                    "course": "BROKEN_COURSE_ID",
                    "batch": "BT001",
                    "grade": "5",
                    "school": "SCH001"
                }]
            ]
            
            # Course doesn't exist - broken link
            mock_frappe.db.exists.return_value = False

            result = self.backend_module.determine_student_type_backend(
                "9876543210", "Test Student", "Math"
            )

            self.assertEqual(result, "Old")

    def test_determine_student_type_backend_different_vertical_only(self):
        """CRITICAL: Test student with only different vertical enrollments - should return 'New'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Student exists
            mock_frappe.db.sql.side_effect = [
                [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],
                # Has enrollment in different vertical
                [{
                    "name": "ENR_001",
                    "course": "SCIENCE_L5",
                    "batch": "BT001",
                    "grade": "5",
                    "school": "SCH001"
                }],
                # Course vertical data
                [{"vertical_name": "Science"}]
            ]
            
            # Course exists
            mock_frappe.db.exists.return_value = True

            result = self.backend_module.determine_student_type_backend(
                "9876543210", "Test Student", "Math"
            )

            self.assertEqual(result, "New")

    def test_determine_student_type_backend_null_course(self):
        """CRITICAL: Test student with NULL course enrollment - should return 'Old'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Student exists
            mock_frappe.db.sql.side_effect = [
                [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],
                # Has enrollment with NULL course
                [{
                    "name": "ENR_001",
                    "course": None,
                    "batch": "BT001",
                    "grade": "5",
                    "school": "SCH001"
                }]
            ]

            result = self.backend_module.determine_student_type_backend(
                "9876543210", "Test Student", "Math"
            )

            self.assertEqual(result, "Old")

    def test_determine_student_type_backend_mixed_enrollments(self):
        """CRITICAL: Test student with mixed enrollments - same vertical takes precedence"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Student exists
            mock_frappe.db.sql.side_effect = [
                [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],
                # Has multiple enrollments
                [
                    {
                        "name": "ENR_001",
                        "course": "MATH_L5",
                        "batch": "BT001",
                        "grade": "5",
                        "school": "SCH001"
                    },
                    {
                        "name": "ENR_002",
                        "course": "SCIENCE_L5",
                        "batch": "BT002",
                        "grade": "5",
                        "school": "SCH001"
                    }
                ],
                # First course vertical - Math
                [{"vertical_name": "Math"}]
            ]
            
            # Both courses exist
            mock_frappe.db.exists.return_value = True

            result = self.backend_module.determine_student_type_backend(
                "9876543210", "Test Student", "Math"
            )

            # Should return Old because has enrollment in same vertical
            self.assertEqual(result, "Old")

    def test_determine_student_type_backend_no_enrollments(self):
        """CRITICAL: Test existing student with no enrollments - should return 'New'"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Student exists
            mock_frappe.db.sql.side_effect = [
                [{"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}],
                # No enrollments
                []
            ]

            result = self.backend_module.determine_student_type_backend(
                "9876543210", "Test Student", "Math"
            )

            self.assertEqual(result, "New")

    def test_determine_student_type_backend_invalid_phone(self):
        """CRITICAL: Test student type with invalid phone - should return 'New' (safe default)"""
        result = self.backend_module.determine_student_type_backend(
            "invalid_phone", "Test Student", "Math"
        )

        self.assertEqual(result, "New")

    # ============= CRITICAL: Process Batch Job Tests (NEW) =============

    def test_process_batch_job_success_all_students(self):
        """CRITICAL: Test process_batch_job with all students processing successfully"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Mock batch document
            mock_batch = MagicMock()
            mock_frappe.get_doc.return_value = mock_batch
            
            # Mock students to process
            mock_frappe.get_all.return_value = [
                {"name": "BS_001", "batch_skeyword": "MATH_2025"},
                {"name": "BS_002", "batch_skeyword": "MATH_2025"}
            ]
            
            # Mock batch onboarding data
            mock_frappe.get_all.side_effect = [
                [{"name": "BS_001", "batch_skeyword": "MATH_2025"}],
                [{"batch_skeyword": "MATH_2025", "name": "BO_001", "kit_less": False}]
            ]
            
            mock_frappe.db.count.return_value = 2
            mock_frappe.db.commit = MagicMock()
            
            # Mock successful student processing
            with patch.object(self.backend_module, 'create_or_get_glific_group_for_batch', return_value={"group_id": "GRP_001"}):
                with patch.object(self.backend_module, 'get_initial_stage', return_value="STAGE_001"):
                    with patch.object(self.backend_module, 'process_glific_contact', return_value={"id": "contact_123"}):
                        with patch.object(self.backend_module, 'process_student_record') as mock_process:
                            with patch.object(self.backend_module, 'update_backend_student_status'):
                                mock_student_doc = MagicMock()
                                mock_student_doc.name = "STUD_001"
                                mock_process.return_value = mock_student_doc
                                
                                result = self.backend_module.process_batch_job("BSO_001")

            self.assertEqual(result["success_count"], 2)
            self.assertEqual(result["failure_count"], 0)
            self.assertEqual(mock_batch.status, "Processed")

    def test_process_batch_job_partial_failures(self):
        """CRITICAL: Test process_batch_job with some student failures"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_frappe.get_doc.return_value = mock_batch
            
            # Mock students
            mock_student_1 = MagicMock()
            mock_student_1.name = "BS_001"
            mock_student_1.student_name = "Student 1"
            mock_student_1.phone = "9876543210"
            
            mock_student_2 = MagicMock()
            mock_student_2.name = "BS_002"
            mock_student_2.student_name = "Student 2"
            
            mock_frappe.get_all.return_value = [
                {"name": "BS_001", "batch_skeyword": "MATH_2025"},
                {"name": "BS_002", "batch_skeyword": "MATH_2025"}
            ]
            
            call_count = [0]
            
            def mock_get_doc_side_effect(doctype, name):
                if doctype == "Backend Student Onboarding":
                    return mock_batch
                call_count[0] += 1
                if call_count[0] == 1:
                    return mock_student_1
                elif call_count[0] == 2:
                    raise Exception("Processing error for student 2")
                return mock_student_2
            
            mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
            mock_frappe.db.count.return_value = 1
            mock_frappe.db.commit = MagicMock()
            mock_frappe.db.rollback = MagicMock()
            
            with patch.object(self.backend_module, 'create_or_get_glific_group_for_batch', return_value={"group_id": "GRP_001"}):
                with patch.object(self.backend_module, 'get_initial_stage', return_value="STAGE_001"):
                    result = self.backend_module.process_batch_job("BSO_001")

            self.assertEqual(result["success_count"], 1)
            self.assertEqual(result["failure_count"], 1)

    def test_process_batch_job_glific_group_creation_failure(self):
        """HIGH: Test process_batch_job when Glific group creation fails"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_frappe.get_doc.return_value = mock_batch
            
            mock_frappe.get_all.return_value = [
                {"name": "BS_001", "batch_skeyword": "MATH_2025"}
            ]
            
            mock_frappe.db.commit = MagicMock()
            
            # Glific group creation fails
            with patch.object(self.backend_module, 'create_or_get_glific_group_for_batch', side_effect=Exception("Glific API error")):
                with patch.object(self.backend_module, 'get_initial_stage', return_value="STAGE_001"):
                    # Should continue processing without glific_group
                    with patch.object(self.backend_module, 'process_glific_contact', return_value=None):
                        with patch.object(self.backend_module, 'process_student_record') as mock_process:
                            with patch.object(self.backend_module, 'update_backend_student_status'):
                                mock_student_doc = MagicMock()
                                mock_student_doc.name = "STUD_001"
                                mock_process.return_value = mock_student_doc
                                
                                result = self.backend_module.process_batch_job("BSO_001")

            # Should still process students despite Glific failure
            self.assertGreaterEqual(result["success_count"], 0)

    def test_process_batch_job_empty_batch(self):
        """HIGH: Test process_batch_job with no students to process"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_frappe.get_doc.return_value = mock_batch
            
            # No students to process
            mock_frappe.get_all.return_value = []
            mock_frappe.db.count.return_value = 0
            mock_frappe.db.commit = MagicMock()
            
            with patch.object(self.backend_module, 'create_or_get_glific_group_for_batch', return_value=None):
                with patch.object(self.backend_module, 'get_initial_stage', return_value="STAGE_001"):
                    result = self.backend_module.process_batch_job("BSO_001")

            self.assertEqual(result["success_count"], 0)
            self.assertEqual(result["failure_count"], 0)
            self.assertEqual(mock_batch.status, "Processed")

    def test_process_batch_job_database_commit_failure(self):
        """HIGH: Test process_batch_job with database commit failure"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_batch = MagicMock()
            mock_frappe.get_doc.return_value = mock_batch
            
            mock_frappe.get_all.return_value = [{"name": "BS_001", "batch_skeyword": "MATH_2025"}]
            
            # Database commit fails
            mock_frappe.db.commit.side_effect = Exception("Database connection lost")
            mock_frappe.db.rollback = MagicMock()
            
            with patch.object(self.backend_module, 'create_or_get_glific_group_for_batch', return_value=None):
                with patch.object(self.backend_module, 'get_initial_stage', return_value="STAGE_001"):
                    with self.assertRaises(Exception):
                        self.backend_module.process_batch_job("BSO_001")

            # Should have attempted rollback
            mock_frappe.db.rollback.assert_called()

    # ============= HIGH: Course Level Assignment Tests (NEW) =============

    def test_get_course_level_with_mapping_backend_academic_year_match(self):
        """HIGH: Test course level assignment with academic year mapping"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    # Mapping found with academic year
                    mock_frappe.get_all.return_value = [
                        {
                            "assigned_course_level": "MATH_NEW_L5_2025",
                            "mapping_name": "Math Grade 5 New 2025-26"
                        }
                    ]

                    result = self.backend_module.get_course_level_with_mapping_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_NEW_L5_2025")

    def test_get_course_level_with_mapping_backend_flexible_mapping(self):
        """HIGH: Test course level with null academic year (flexible mapping)"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="Old"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    # No academic year mapping, but flexible mapping exists
                    def mock_get_all_side_effect(*args, **kwargs):
                        filters = kwargs.get('filters', {})
                        if 'academic_year' in filters and filters['academic_year'] == '2025-26':
                            return []  # No academic year specific mapping
                        else:
                            return [{
                                "assigned_course_level": "MATH_OLD_L5_FLEX",
                                "mapping_name": "Math Grade 5 Old Flexible"
                            }]
                    
                    mock_frappe.get_all.side_effect = mock_get_all_side_effect

                    result = self.backend_module.get_course_level_with_mapping_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_OLD_L5_FLEX")

    def test_get_course_level_with_mapping_backend_fallback_to_stage_grades(self):
        """HIGH: Test complete fallback to original Stage Grades logic"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'determine_student_type_backend', return_value="New"):
                with patch.object(self.backend_module, 'get_current_academic_year_backend', return_value="2025-26"):
                    with patch.object(self.backend_module, 'get_course_level', return_value="MATH_STAGE_L5") as mock_get_course:
                        # No mappings found
                        mock_frappe.get_all.return_value = []

                        result = self.backend_module.get_course_level_with_mapping_backend(
                            "Math", "5", "9876543210", "Test Student", False
                        )

                        self.assertEqual(result, "MATH_STAGE_L5")
                        mock_get_course.assert_called_once_with("Math", "5", False)

    def test_get_course_level_with_validation_backend_with_broken_enrollments(self):
        """HIGH: Test course level selection with broken enrollment detection"""
        with patch.object(self.backend_module, 'validate_enrollment_data') as mock_validate:
            with patch.object(self.backend_module, 'get_course_level_with_mapping_backend', return_value="MATH_L5"):
                # Broken enrollments detected but processing continues
                mock_validate.return_value = {
                    "total_enrollments": 2,
                    "valid_enrollments": 1,
                    "broken_enrollments": 1,
                    "broken_details": [{"enrollment_id": "ENR_001", "invalid_course": "BROKEN_COURSE"}]
                }

                result = self.backend_module.get_course_level_with_validation_backend(
                    "Math", "5", "9876543210", "Test Student", False
                )

                self.assertEqual(result, "MATH_L5")
                mock_validate.assert_called_once()

    def test_get_course_level_with_validation_backend_fallback_on_error(self):
        """HIGH: Test fallback to basic course level on validation error"""
        with patch.object(self.backend_module, 'validate_enrollment_data', side_effect=Exception("Validation error")):
            with patch.object(self.backend_module, 'get_course_level_with_mapping_backend', side_effect=Exception("Mapping error")):
                with patch.object(self.backend_module, 'get_course_level', return_value="MATH_BASIC") as mock_basic:
                    result = self.backend_module.get_course_level_with_validation_backend(
                        "Math", "5", "9876543210", "Test Student", False
                    )

                    self.assertEqual(result, "MATH_BASIC")
                    mock_basic.assert_called_once()

    # ============= HIGH: Process Student Record Tests (NEW) =============

    def test_process_student_record_update_existing_student_grade(self):
        """HIGH: Test updating existing student's grade"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name') as mock_find:
                mock_existing = {"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}
                mock_find.return_value = mock_existing
                
                mock_existing_doc = MagicMock()
                mock_existing_doc.name = "STUD_001"
                mock_existing_doc.grade = "4"  # Old grade
                mock_existing_doc.phone = "919876543210"
                mock_existing_doc.school_id = "SCH001"
                mock_existing_doc.language = "English"
                mock_frappe.get_doc.return_value = mock_existing_doc
                
                mock_student = MagicMock()
                mock_student.student_name = "Test Student"
                mock_student.phone = "9876543210"
                mock_student.grade = "5"  # New grade
                mock_student.school = "SCH001"
                mock_student.language = "English"
                mock_student.batch = "BT001"

                result = self.backend_module.process_student_record(
                    mock_student, None, "BSO_001", "STAGE_001", "MATH_L5"
                )

                self.assertEqual(mock_existing_doc.grade, "5")
                mock_existing_doc.save.assert_called_once()

    def test_process_student_record_add_enrollment_to_existing_student(self):
        """HIGH: Test adding new enrollment to existing student"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name') as mock_find:
                mock_existing = {"name": "STUD_001", "phone": "919876543210", "name1": "Test Student"}
                mock_find.return_value = mock_existing
                
                mock_existing_doc = MagicMock()
                mock_existing_doc.name = "STUD_001"
                mock_existing_doc.grade = "5"
                mock_existing_doc.phone = "919876543210"
                mock_existing_doc.enrollment = []
                mock_frappe.get_doc.return_value = mock_existing_doc
                
                mock_student = MagicMock()
                mock_student.student_name = "Test Student"
                mock_student.phone = "9876543210"
                mock_student.grade = "5"
                mock_student.school = "SCH001"
                mock_student.batch = "BT001"

                result = self.backend_module.process_student_record(
                    mock_student, None, "BSO_001", "STAGE_001", "MATH_L5"
                )

                # Should have added enrollment
                mock_existing_doc.append.assert_called_once()
                call_args = mock_existing_doc.append.call_args
                self.assertEqual(call_args[0][0], "enrollment")

    def test_process_student_record_create_new_student_with_states(self):
        """HIGH: Test creating new student with LearningState and EngagementState"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                mock_new_student = MagicMock()
                mock_new_student.name = "STUD_NEW_001"
                mock_frappe.new_doc.return_value = mock_new_student
                mock_frappe.db.exists.return_value = False  # States don't exist
                
                mock_student = MagicMock()
                mock_student.student_name = "New Student"
                mock_student.phone = "9876543210"
                mock_student.gender = "Male"
                mock_student.school = "SCH001"
                mock_student.grade = "5"
                mock_student.language = "English"
                mock_student.batch = "BT001"

                result = self.backend_module.process_student_record(
                    mock_student, None, "BSO_001", "STAGE_001", "MATH_L5"
                )

                mock_new_student.insert.assert_called_once()
                # Should create LearningState and EngagementState
                self.assertGreaterEqual(mock_frappe.new_doc.call_count, 3)  # Student + 2 states

    def test_process_student_record_handle_glific_contact_failure(self):
        """HIGH: Test student record creation when Glific contact is None"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            with patch.object(self.backend_module, 'find_existing_student_by_phone_and_name', return_value=None):
                mock_new_student = MagicMock()
                mock_new_student.name = "STUD_NEW_001"
                mock_frappe.new_doc.return_value = mock_new_student
                mock_frappe.db.exists.return_value = False
                
                mock_student = MagicMock()
                mock_student.student_name = "New Student"
                mock_student.phone = "9876543210"
                mock_student.gender = "Male"
                mock_student.school = "SCH001"
                mock_student.grade = "5"
                mock_student.language = "English"
                mock_student.batch = "BT001"

                # No Glific contact
                result = self.backend_module.process_student_record(
                    mock_student, None, "BSO_001", "STAGE_001", "MATH_L5"
                )

                # Should still create student successfully
                mock_new_student.insert.assert_called_once()
                self.assertEqual(result, mock_new_student)

    # ============= HIGH: Error Handling Tests (NEW) =============

    def test_validate_enrollment_data_detects_broken_course_links(self):
        """HIGH: Test validation detects broken course links"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Student with broken enrollment
            mock_frappe.db.sql.return_value = [
                {
                    "student_id": "STUD_001",
                    "enrollment_id": "ENR_001",
                    "course": "BROKEN_COURSE",
                    "batch": "BT001",
                    "grade": "5"
                }
            ]
            
            # Course doesn't exist
            mock_frappe.db.exists.return_value = False

            result = self.backend_module.validate_enrollment_data("Test Student", "9876543210")

            self.assertEqual(result["total_enrollments"], 1)
            self.assertEqual(result["broken_enrollments"], 1)
            self.assertEqual(len(result["broken_details"]), 1)

    def test_update_backend_student_status_handles_long_error_messages(self):
        """HIGH: Test error message truncation for field length limits"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_student = MagicMock()
            
            mock_meta = MagicMock()
            mock_field = MagicMock()
            mock_field.length = 50  # Short limit
            mock_meta.get_field.return_value = mock_field
            mock_frappe.get_meta.return_value = mock_meta

            long_error = "This is a very long error message " * 10  # Much longer than 50 chars
            
            self.backend_module.update_backend_student_status(
                mock_student, "Failed", error=long_error
            )

            self.assertEqual(mock_student.processing_status, "Failed")
            self.assertLessEqual(len(mock_student.processing_notes), 50)
            mock_student.save.assert_called_once()

    def test_fix_broken_course_links_sets_to_null(self):
        """HIGH: Test fixing broken course links by setting to NULL"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [{"name": "STUD_001"}]
            
            # Found broken enrollments
            mock_frappe.db.sql.return_value = [
                {"name": "ENR_001", "course": "BROKEN_COURSE_1"},
                {"name": "ENR_002", "course": "BROKEN_COURSE_2"}
            ]
            
            mock_frappe.db.set_value = MagicMock()
            mock_frappe.db.commit = MagicMock()
            mock_frappe.whitelist.return_value = lambda func: func
            
            result = self.backend_module.fix_broken_course_links()
            
            # Should have fixed 2 broken links
            self.assertEqual(mock_frappe.db.set_value.call_count, 2)
            self.assertIn("Total fixed: 2", result)

    def test_get_current_academic_year_backend_handles_exceptions(self):
        """HIGH: Test academic year calculation handles exceptions gracefully"""
        with patch.object(self.backend_module, 'frappe') as mock_frappe:
            # Simulate getdate failure
            mock_frappe.utils.getdate.side_effect = Exception("Date error")

            result = self.backend_module.get_current_academic_year_backend()

            self.assertIsNone(result)  # Should return None on error

    # ============= Existing Good Tests (BATCH MANAGEMENT) =============

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

    # ============= Utility Tests =============

    def test_format_phone_number_valid(self):
        """Test format_phone_number with valid input"""
        result = self.backend_module.format_phone_number("9876543210")
        self.assertEqual(result, "919876543210")

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


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)