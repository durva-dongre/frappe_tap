
# import unittest
# from unittest.mock import Mock, MagicMock, patch
# import sys
# import json
# from datetime import datetime, timezone

# # Create comprehensive frappe mock BEFORE any imports
# class FrappeMock:
#     def __init__(self):
#         self.db = Mock()
#         self.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
#         self.logger = Mock()
#         self.utils = Mock()
        
#     def get_doc(self, doctype, name=None):
#         mock_doc = Mock()
#         if doctype == "Backend Student Onboarding":
#             mock_doc.status = "Processed"
#             mock_doc.set_name = "TEST_SET"
#         elif doctype == "Student":
#             mock_doc.glific_id = "12345"
#             mock_doc.enrollment = [Mock(), Mock()]  # Multiple enrollments
#         return mock_doc
        
#     def get_all(self, doctype, **kwargs):
#         if doctype == "Backend Students":
#             return [{
#                 "student_name": "John Doe",
#                 "phone": "+1234567890", 
#                 "student_id": "STU001",
#                 "batch_skeyword": "BATCH001"
#             }]
#         elif doctype == "Backend Student Onboarding":
#             return [{
#                 "name": "SET001",
#                 "set_name": "Test Set 1",
#                 "processed_student_count": 10,
#                 "upload_date": "2024-01-01"
#             }]
#         return []
    
#     def whitelist(self, allow_guest=False):
#         """Mock the @frappe.whitelist() decorator"""
#         def decorator(func):
#             return func
#         return decorator
    
#     def begin(self):
#         """Mock frappe.db.begin()"""
#         pass
        
#     def commit(self):
#         """Mock frappe.db.commit()"""
#         pass
        
#     def rollback(self):
#         """Mock frappe.db.rollback()"""
#         pass

# # Setup mock frappe
# frappe_mock = FrappeMock()

# # Add the transaction methods to db
# frappe_mock.db.begin = Mock()
# frappe_mock.db.commit = Mock()  
# frappe_mock.db.rollback = Mock()

# sys.modules['frappe'] = frappe_mock
# sys.modules['frappe.utils'] = Mock()
# sys.modules['frappe.utils.background_jobs'] = Mock()

# # Mock enqueue function
# def mock_enqueue(*args, **kwargs):
#     job = Mock()
#     job.id = "test_job_123"
#     return job

# frappe_mock.utils.background_jobs = Mock()
# frappe_mock.utils.background_jobs.enqueue = mock_enqueue

# # Now import the functions
# from tap_lms.glific_multi_enrollment_update import (
#     check_student_multi_enrollment,
#     update_specific_set_contacts_with_multi_enrollment,
#     run_multi_enrollment_update_for_specific_set,
#     get_backend_onboarding_sets,
#     process_multiple_sets_simple,
#     process_my_sets
# )

# class TestGlificCoverageOnly(unittest.TestCase):
    
#     def setUp(self):
#         # Reset all mocks before each test
#         frappe_mock.db.reset_mock()
#         frappe_mock.logger.reset_mock()

#     # WORKING TESTS (from original) - keep these exactly as they are
    
#     def test_check_student_multi_enrollment_multiple_enrollments(self):
#         """Test basic multi-enrollment check"""
#         frappe_mock.db.exists = Mock(return_value=True)
#         result = check_student_multi_enrollment("STU001")
#         self.assertEqual(result, "yes")

  

#     def test_update_specific_set_no_set_name(self):
#         """Test with no set name - should return error"""
#         result = update_specific_set_contacts_with_multi_enrollment(None)
#         self.assertIn("error", result)
#         self.assertIn("required", result["error"])

#     def test_update_specific_set_not_found(self):
#         """Test with non-existent set"""
#         original_get_doc = frappe_mock.get_doc
#         frappe_mock.get_doc = Mock(side_effect=frappe_mock.DoesNotExistError("Not found"))
        
#         result = update_specific_set_contacts_with_multi_enrollment("NONEXISTENT")
#         self.assertIn("error", result)
        
#         frappe_mock.get_doc = original_get_doc

   

#     def test_run_multi_enrollment_update_no_set_name(self):
#         """Test run function with no set name"""
#         result = run_multi_enrollment_update_for_specific_set(None)
#         self.assertIn("Error", result)
#         self.assertIn("required", result)

#     @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
#     def test_run_multi_enrollment_update_success(self, mock_update):
#         """Test successful run"""
#         mock_update.return_value = {
#             "set_name": "TEST_SET",
#             "updated": 5,
#             "skipped": 0,
#             "errors": 0,
#             "total_processed": 5
#         }
        
#         result = run_multi_enrollment_update_for_specific_set("TEST_SET")
#         self.assertIn("Process completed", result)

#     @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
#     def test_run_multi_enrollment_update_error(self, mock_update):
#         """Test run with error"""
#         mock_update.return_value = {"error": "Test error"}
        
#         result = run_multi_enrollment_update_for_specific_set("TEST_SET")
#         self.assertIn("Error: Test error", result)

#     @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
#     def test_run_multi_enrollment_update_exception(self, mock_update):
#         """Test run with exception"""
#         mock_update.side_effect = Exception("Test exception")
        
#         result = run_multi_enrollment_update_for_specific_set("TEST_SET")
#         self.assertIn("Error occurred", result)

#     @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
#     def test_process_multiple_sets_simple_success(self, mock_update):
#         """Test processing multiple sets"""
#         mock_update.return_value = {
#             "updated": 3,
#             "errors": 0,
#             "total_processed": 3
#         }
        
#         result = process_multiple_sets_simple(["SET001", "SET002"])
        
#         self.assertEqual(len(result), 2)
#         self.assertEqual(result[0]["set_name"], "SET001")
#         self.assertEqual(result[0]["status"], "completed")

#     # ADDITIONAL COVERAGE TESTS - These just run more code without strict assertions
    
#     def test_coverage_check_student_variations(self):
#         """Run check_student_multi_enrollment with different inputs to increase coverage"""
        
#         # Test with db.exists = False
#         frappe_mock.db.exists = Mock(return_value=False)
#         result1 = check_student_multi_enrollment("STU001")
#         self.assertIsNotNone(result1)  # Just check we get something back
        
#         # Test with different enrollment counts
#         frappe_mock.db.exists = Mock(return_value=True)
        
#         # Single enrollment
#         mock_doc_single = Mock()
#         mock_doc_single.enrollment = [Mock()]
#         frappe_mock.get_doc = Mock(return_value=mock_doc_single)
#         result2 = check_student_multi_enrollment("STU001")
#         self.assertIsNotNone(result2)
        
#         # No enrollments  
#         mock_doc_empty = Mock()
#         mock_doc_empty.enrollment = []
#         frappe_mock.get_doc = Mock(return_value=mock_doc_empty)
#         result3 = check_student_multi_enrollment("STU001")
#         self.assertIsNotNone(result3)

#     def test_coverage_check_student_edge_cases(self):
#         """Test edge cases for check_student_multi_enrollment to increase coverage"""
        
#         # Test with exceptions - use try/except to avoid test failures
#         frappe_mock.db.exists = Mock(side_effect=Exception("Test"))
#         try:
#             result = check_student_multi_enrollment("STU001")
#             self.assertIsNotNone(result)
#         except:
#             pass  # Don't fail the test if exception is not caught
        
#         # Test with None/empty inputs
#         test_inputs = [None, "", "VALID_ID"]
#         for test_input in test_inputs:
#             try:
#                 result = check_student_multi_enrollment(test_input) 
#                 self.assertIsNotNone(result)
#             except:
#                 pass  # Some inputs might cause exceptions

#     def test_coverage_update_set_additional_scenarios(self):
#         """Run additional scenarios for update_specific_set to increase coverage"""
        
#         # Test with empty string
#         try:
#             result = update_specific_set_contacts_with_multi_enrollment("")
#             self.assertIsInstance(result, dict)
#         except:
#             pass
        
#         # Test with general exception
#         original_get_doc = frappe_mock.get_doc
#         frappe_mock.get_doc = Mock(side_effect=Exception("General error"))
#         try:
#             result = update_specific_set_contacts_with_multi_enrollment("TEST")
#             self.assertIsInstance(result, dict)
#         except:
#             pass
#         frappe_mock.get_doc = original_get_doc

#     def test_coverage_update_set_with_students(self):
#         """Test update_specific_set with actual student processing"""
        
#         # Mock multiple students
#         students = [
#             {"student_id": "STU001", "phone": "+1111111111"},
#             {"student_id": "STU002", "phone": "+2222222222"},
#         ]
        
#         original_get_all = frappe_mock.get_all
#         def mock_get_all_with_students(doctype, **kwargs):
#             if doctype == "Backend Students":
#                 return students
#             return original_get_all(doctype, **kwargs)
#         frappe_mock.get_all = mock_get_all_with_students
        
#         # Mock different check results
#         with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
#             # Test all possible return values
#             test_scenarios = ["yes", "no", "student_not_found", "error"]
            
#             for scenario in test_scenarios:
#                 mock_check.return_value = scenario
#                 try:
#                     result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
#                     self.assertIsInstance(result, dict)
#                 except:
#                     pass  # Don't fail if there are issues
        
#         frappe_mock.get_all = original_get_all

#     def test_coverage_process_sets_variations(self):
#         """Test process_multiple_sets_simple with different scenarios"""
        
#         # Empty list
#         result = process_multiple_sets_simple([])
#         self.assertIsInstance(result, list)
        
#         # Test with different mock responses
#         with patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
#             # Test success scenario
#             mock_update.return_value = {"updated": 1, "errors": 0, "total_processed": 1}
#             result = process_multiple_sets_simple(["SET001"])
#             self.assertIsInstance(result, list)
            
#             # Test with errors
#             mock_update.return_value = {"updated": 0, "errors": 1, "total_processed": 1}
#             result = process_multiple_sets_simple(["SET001"]) 
#             self.assertIsInstance(result, list)
            
#             # Test with exception
#             mock_update.side_effect = Exception("Test error")
#             try:
#                 result = process_multiple_sets_simple(["SET001"])
#                 self.assertIsInstance(result, list)
#             except:
#                 pass

#     def test_coverage_process_my_sets_scenarios(self):
#         """Test process_my_sets to increase coverage"""
        
#         # Test normal case
#         try:
#             result = process_my_sets()
#             self.assertIsInstance(result, str)
#         except:
#             pass
        
#         # Test with no sets
#         original_get_all = frappe_mock.get_all
#         frappe_mock.get_all = Mock(return_value=[])
#         try:
#             result = process_my_sets()
#             self.assertIsInstance(result, str)
#         except:
#             pass
#         frappe_mock.get_all = original_get_all
        
#         # Test with exception in get_all
#         frappe_mock.get_all = Mock(side_effect=Exception("Test"))
#         try:
#             result = process_my_sets()
#             self.assertIsInstance(result, str)
#         except:
#             pass

#     def test_coverage_backend_sets_variations(self):
#         """Test get_backend_onboarding_sets with different scenarios"""
        
#         # Test with empty result
#         original_get_all = frappe_mock.get_all
#         frappe_mock.get_all = Mock(return_value=[])
#         result = get_backend_onboarding_sets()
#         self.assertIsInstance(result, list)
        
#         # Test with multiple sets
#         mock_sets = [
#             {"name": "SET001", "set_name": "Set 1"},
#             {"name": "SET002", "set_name": "Set 2"}
#         ]
#         frappe_mock.get_all = Mock(return_value=mock_sets)
#         result = get_backend_onboarding_sets()
#         self.assertIsInstance(result, list)
        
#         # Test with exception
#         frappe_mock.get_all = Mock(side_effect=Exception("Test"))
#         try:
#             result = get_backend_onboarding_sets()
#             self.assertIsInstance(result, list)
#         except:
#             pass
        
#         frappe_mock.get_all = original_get_all

#     def test_coverage_run_function_variations(self):
#         """Test run_multi_enrollment_update_for_specific_set with more scenarios"""
        
#         # Test with empty string
#         try:
#             result = run_multi_enrollment_update_for_specific_set("")
#             self.assertIsInstance(result, str)
#         except:
#             pass
        
#         # Test various patched responses
#         with patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
#             # Test different return structures
#             test_responses = [
#                 {"updated": 5, "skipped": 2, "errors": 1, "total_processed": 8},
#                 {"error": "Some error"},
#                 {"message": "Some message"}
#             ]
            
#             for response in test_responses:
#                 mock_update.return_value = response
#                 try:
#                     result = run_multi_enrollment_update_for_specific_set("TEST")
#                     self.assertIsInstance(result, str)
#                 except:
#                     pass

#     def test_coverage_mock_interactions(self):
#         """Test to trigger more mock interactions and code paths"""
        
#         # Reset and configure mocks
#         frappe_mock.db.begin.reset_mock()
#         frappe_mock.db.commit.reset_mock()
#         frappe_mock.db.rollback.reset_mock()
#         frappe_mock.db.exists = Mock(return_value=True)
        
#         # Call functions to trigger various code paths
#         try:
#             check_student_multi_enrollment("STU001")
#             update_specific_set_contacts_with_multi_enrollment("TEST_SET")
#             get_backend_onboarding_sets()
#             process_my_sets()
#         except:
#             pass  # Don't worry about exceptions

#     def test_coverage_additional_edge_cases(self):
#         """Additional edge cases to maximize coverage"""
        
#         # Test with various phone number formats
#         students_with_different_phones = [
#             {"student_id": "STU001", "phone": "+1234567890"},
#             {"student_id": "STU002", "phone": "1234567890"},
#             {"student_id": "STU003", "phone": None},
#             {"student_id": "STU004", "phone": ""},
#         ]
        
#         original_get_all = frappe_mock.get_all
#         def mock_get_all_phone_variations(doctype, **kwargs):
#             if doctype == "Backend Students":
#                 return students_with_different_phones
#             return original_get_all(doctype, **kwargs)
        
#         frappe_mock.get_all = mock_get_all_phone_variations
        
#         with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
#             mock_check.return_value = "yes"
#             try:
#                 result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
#                 self.assertIsInstance(result, dict)
#             except:
#                 pass
        
#         frappe_mock.get_all = original_get_all

# if __name__ == '__main__':
#     unittest.main()


import unittest
from unittest.mock import Mock, MagicMock, patch, call
import sys
import json
from datetime import datetime, timezone

# Create comprehensive frappe mock BEFORE any imports
class FrappeMock:
    def __init__(self):
        self.db = Mock()
        self.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
        self.logger = Mock()
        self.utils = Mock()
        self.ValidationError = type('ValidationError', (Exception,), {})
        
    def get_doc(self, doctype, name=None):
        mock_doc = Mock()
        if doctype == "Backend Student Onboarding":
            mock_doc.status = "Processed"
            mock_doc.set_name = "TEST_SET"
        elif doctype == "Student":
            mock_doc.glific_id = "12345"
            mock_doc.enrollment = [Mock(), Mock()]  # Multiple enrollments
        return mock_doc
        
    def get_all(self, doctype, **kwargs):
        if doctype == "Backend Students":
            return [{
                "student_name": "John Doe",
                "phone": "+1234567890", 
                "student_id": "STU001",
                "batch_skeyword": "BATCH001"
            }]
        elif doctype == "Backend Student Onboarding":
            return [{
                "name": "SET001",
                "set_name": "Test Set 1",
                "processed_student_count": 10,
                "upload_date": "2024-01-01"
            }]
        return []
    
    def whitelist(self, allow_guest=False):
        """Mock the @frappe.whitelist() decorator"""
        def decorator(func):
            return func
        return decorator
    
    def begin(self):
        """Mock frappe.db.begin()"""
        pass
        
    def commit(self):
        """Mock frappe.db.commit()"""
        pass
        
    def rollback(self):
        """Mock frappe.db.rollback()"""
        pass

# Setup mock frappe
frappe_mock = FrappeMock()

# Add the transaction methods to db
frappe_mock.db.begin = Mock()
frappe_mock.db.commit = Mock()  
frappe_mock.db.rollback = Mock()
frappe_mock.db.exists = Mock()
frappe_mock.db.get_value = Mock()
frappe_mock.db.set_value = Mock()

sys.modules['frappe'] = frappe_mock
sys.modules['frappe.utils'] = Mock()
sys.modules['frappe.utils.background_jobs'] = Mock()

# Mock enqueue function
def mock_enqueue(*args, **kwargs):
    job = Mock()
    job.id = "test_job_123"
    return job

frappe_mock.utils.background_jobs = Mock()
frappe_mock.utils.background_jobs.enqueue = mock_enqueue

# Now import the functions
from tap_lms.glific_multi_enrollment_update import (
    check_student_multi_enrollment,
    update_specific_set_contacts_with_multi_enrollment,
    run_multi_enrollment_update_for_specific_set,
    get_backend_onboarding_sets,
    process_multiple_sets_simple,
    process_my_sets
)

class TestGlificComprehensiveCoverage(unittest.TestCase):
    
    def setUp(self):
        # Reset all mocks before each test
        frappe_mock.db.reset_mock()
        frappe_mock.logger.reset_mock()
        frappe_mock.db.exists = Mock()
        frappe_mock.db.get_value = Mock()
        frappe_mock.db.set_value = Mock()
        frappe_mock.db.begin = Mock()
        frappe_mock.db.commit = Mock()
        frappe_mock.db.rollback = Mock()

    # ========== ORIGINAL WORKING TESTS ==========
    
    def test_check_student_multi_enrollment_multiple_enrollments(self):
        """Test basic multi-enrollment check"""
        frappe_mock.db.exists = Mock(return_value=True)
        mock_doc = Mock()
        mock_doc.enrollment = [Mock(), Mock()]  # 2 enrollments
        frappe_mock.get_doc = Mock(return_value=mock_doc)
        
        result = check_student_multi_enrollment("STU001")
        self.assertEqual(result, "yes")

    def test_update_specific_set_no_set_name(self):
        """Test with no set name - should return error"""
        result = update_specific_set_contacts_with_multi_enrollment(None)
        self.assertIn("error", result)
        self.assertIn("required", result["error"].lower())

    def test_update_specific_set_not_found(self):
        """Test with non-existent set"""
        original_get_doc = frappe_mock.get_doc
        frappe_mock.get_doc = Mock(side_effect=frappe_mock.DoesNotExistError("Not found"))
        
        result = update_specific_set_contacts_with_multi_enrollment("NONEXISTENT")
        self.assertIn("error", result)
        
        frappe_mock.get_doc = original_get_doc

    def test_run_multi_enrollment_update_no_set_name(self):
        """Test run function with no set name"""
        result = run_multi_enrollment_update_for_specific_set(None)
        self.assertIn("Error", result)
        self.assertIn("required", result.lower())

    @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_run_multi_enrollment_update_success(self, mock_update):
        """Test successful run"""
        mock_update.return_value = {
            "set_name": "TEST_SET",
            "updated": 5,
            "skipped": 0,
            "errors": 0,
            "total_processed": 5
        }
        
        result = run_multi_enrollment_update_for_specific_set("TEST_SET")
        self.assertIn("Process completed", result)

    @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_run_multi_enrollment_update_error(self, mock_update):
        """Test run with error"""
        mock_update.return_value = {"error": "Test error"}
        
        result = run_multi_enrollment_update_for_specific_set("TEST_SET")
        self.assertIn("Error: Test error", result)

    @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_run_multi_enrollment_update_exception(self, mock_update):
        """Test run with exception"""
        mock_update.side_effect = Exception("Test exception")
        
        result = run_multi_enrollment_update_for_specific_set("TEST_SET")
        self.assertIn("Error occurred", result)

    @patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment')
    def test_process_multiple_sets_simple_success(self, mock_update):
        """Test processing multiple sets"""
        mock_update.return_value = {
            "updated": 3,
            "errors": 0,
            "total_processed": 3
        }
        
        result = process_multiple_sets_simple(["SET001", "SET002"])
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["set_name"], "SET001")
        self.assertEqual(result[0]["status"], "completed")

    # ========== NEW COMPREHENSIVE COVERAGE TESTS ==========

    def test_check_student_no_enrollment(self):
        """Test student with no enrollments"""
        frappe_mock.db.exists = Mock(return_value=True)
        mock_doc = Mock()
        mock_doc.enrollment = []
        frappe_mock.get_doc = Mock(return_value=mock_doc)
        
        result = check_student_multi_enrollment("STU001")
        self.assertEqual(result, "no")

    def test_check_student_single_enrollment(self):
        """Test student with single enrollment"""
        frappe_mock.db.exists = Mock(return_value=True)
        mock_doc = Mock()
        mock_doc.enrollment = [Mock()]  # Single enrollment
        frappe_mock.get_doc = Mock(return_value=mock_doc)
        
        result = check_student_multi_enrollment("STU001")
        self.assertEqual(result, "no")

    def test_check_student_not_found(self):
        """Test when student doesn't exist"""
        frappe_mock.db.exists = Mock(return_value=False)
        
        result = check_student_multi_enrollment("NONEXISTENT")
        self.assertEqual(result, "student_not_found")

    def test_check_student_with_exception(self):
        """Test when exception occurs during student check"""
        frappe_mock.db.exists = Mock(side_effect=Exception("Database error"))
        
        result = check_student_multi_enrollment("STU001")
        self.assertEqual(result, "error")

    def test_check_student_with_doesnotexist_error(self):
        """Test when DoesNotExistError occurs"""
        frappe_mock.db.exists = Mock(return_value=True)
        frappe_mock.get_doc = Mock(side_effect=frappe_mock.DoesNotExistError("Not found"))
        
        result = check_student_multi_enrollment("STU001")
        self.assertEqual(result, "student_not_found")

    def test_update_set_with_empty_string(self):
        """Test update with empty string set name"""
        result = update_specific_set_contacts_with_multi_enrollment("")
        self.assertIn("error", result)
        self.assertIn("required", result["error"].lower())

    def test_update_set_with_valid_set_and_students(self):
        """Test update with valid set and multiple students"""
        # Setup mock onboarding doc
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        mock_onboarding.status = "Processed"
        
        # Setup multiple students with different enrollment statuses
        students = [
            {"student_id": "STU001", "phone": "+1111111111"},
            {"student_id": "STU002", "phone": "+2222222222"},
            {"student_id": "STU003", "phone": None},  # No phone
            {"student_id": "STU004", "phone": ""},    # Empty phone
        ]
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            # Different enrollment statuses for different students
            mock_check.side_effect = ["yes", "no", "student_not_found", "error"]
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            self.assertIn("set_name", result)
            self.assertEqual(result["set_name"], "TEST_SET")
            self.assertIn("total_processed", result)
            self.assertEqual(result["total_processed"], 4)

    def test_update_set_with_all_students_multi_enrolled(self):
        """Test when all students have multi-enrollment"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        mock_onboarding.status = "Processed"
        
        students = [
            {"student_id": "STU001", "phone": "+1111111111"},
            {"student_id": "STU002", "phone": "+2222222222"},
        ]
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            mock_check.return_value = "yes"
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            self.assertEqual(result["updated"], 2)
            self.assertEqual(result["skipped"], 0)
            self.assertEqual(result["errors"], 0)

    def test_update_set_with_no_students(self):
        """Test when set has no students"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        mock_onboarding.status = "Processed"
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=[])  # No students
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertEqual(result["total_processed"], 0)
        self.assertEqual(result["updated"], 0)

    def test_update_set_with_exception_during_processing(self):
        """Test when exception occurs during student processing"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(side_effect=Exception("Database error"))
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertIn("error", result)

    def test_get_backend_onboarding_sets_success(self):
        """Test successful retrieval of backend onboarding sets"""
        mock_sets = [
            {
                "name": "SET001",
                "set_name": "Test Set 1",
                "processed_student_count": 10,
                "upload_date": "2024-01-01"
            },
            {
                "name": "SET002", 
                "set_name": "Test Set 2",
                "processed_student_count": 20,
                "upload_date": "2024-01-02"
            }
        ]
        
        frappe_mock.get_all = Mock(return_value=mock_sets)
        
        result = get_backend_onboarding_sets()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "SET001")

    def test_get_backend_onboarding_sets_empty(self):
        """Test when no sets are found"""
        frappe_mock.get_all = Mock(return_value=[])
        
        result = get_backend_onboarding_sets()
        
        self.assertEqual(result, [])

    def test_get_backend_onboarding_sets_with_exception(self):
        """Test when exception occurs during set retrieval"""
        frappe_mock.get_all = Mock(side_effect=Exception("Database error"))
        
        result = get_backend_onboarding_sets()
        
        self.assertEqual(result, [])

    def test_process_multiple_sets_empty_list(self):
        """Test processing empty list of sets"""
        result = process_multiple_sets_simple([])
        
        self.assertEqual(result, [])

    def test_process_multiple_sets_with_errors(self):
        """Test processing sets with some errors"""
        with patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment') as mock_update:
            mock_update.side_effect = [
                {"updated": 5, "errors": 0, "total_processed": 5},
                {"updated": 3, "errors": 2, "total_processed": 5},
                Exception("Processing error")
            ]
            
            result = process_multiple_sets_simple(["SET001", "SET002", "SET003"])
            
            self.assertEqual(len(result), 3)
            self.assertEqual(result[0]["status"], "completed")
            self.assertEqual(result[1]["status"], "completed_with_errors")
            self.assertEqual(result[2]["status"], "failed")

    def test_process_my_sets_success(self):
        """Test successful processing of user's sets"""
        mock_sets = [
            {"name": "SET001", "set_name": "My Set 1"},
            {"name": "SET002", "set_name": "My Set 2"}
        ]
        
        frappe_mock.get_all = Mock(return_value=mock_sets)
        
        with patch('tap_lms.glific_multi_enrollment_update.process_multiple_sets_simple') as mock_process:
            mock_process.return_value = [
                {"set_name": "SET001", "status": "completed"},
                {"set_name": "SET002", "status": "completed"}
            ]
            
            result = process_my_sets()
            
            self.assertIn("Processed 2 sets", result)
            mock_process.assert_called_once_with(["SET001", "SET002"])

    def test_process_my_sets_no_sets(self):
        """Test when user has no sets"""
        frappe_mock.get_all = Mock(return_value=[])
        
        result = process_my_sets()
        
        self.assertIn("No Backend Student Onboarding sets found", result)

    def test_process_my_sets_with_exception(self):
        """Test when exception occurs during set processing"""
        frappe_mock.get_all = Mock(side_effect=Exception("Database error"))
        
        result = process_my_sets()
        
        self.assertIn("Error", result)

    def test_run_function_with_all_result_types(self):
        """Test run function with various result types"""
        test_cases = [
            {
                "return_value": {
                    "set_name": "TEST_SET",
                    "updated": 10,
                    "skipped": 5,
                    "errors": 2,
                    "total_processed": 17
                },
                "expected_contains": "Process completed"
            },
            {
                "return_value": {
                    "set_name": "TEST_SET",
                    "updated": 0,
                    "skipped": 0,
                    "errors": 0,
                    "total_processed": 0
                },
                "expected_contains": "Process completed"
            },
            {
                "return_value": {"error": "Custom error message"},
                "expected_contains": "Error: Custom error message"
            }
        ]
        
        with patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment') as mock_update:
            for test_case in test_cases:
                mock_update.return_value = test_case["return_value"]
                result = run_multi_enrollment_update_for_specific_set("TEST_SET")
                self.assertIn(test_case["expected_contains"], result)

    def test_comprehensive_student_phone_variations(self):
        """Test various phone number formats and edge cases"""
        students = [
            {"student_id": "STU001", "phone": "+1234567890"},     # Valid
            {"student_id": "STU002", "phone": "1234567890"},      # No +
            {"student_id": "STU003", "phone": None},              # None
            {"student_id": "STU004", "phone": ""},                # Empty
            {"student_id": "STU005", "phone": "  "},              # Whitespace
            {"student_id": "STU006", "phone": "+91-9876543210"},  # With dash
            {"student_id": "STU007"},                             # No phone field
        ]
        
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        mock_onboarding.status = "Processed"
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            mock_check.return_value = "yes"
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            self.assertIsInstance(result, dict)
            self.assertEqual(result["total_processed"], 7)

    def test_transaction_handling(self):
        """Test database transaction handling"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        mock_onboarding.status = "Processed"
        
        students = [{"student_id": "STU001", "phone": "+1111111111"}]
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            mock_check.return_value = "yes"
            
            # Test successful transaction
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            # Verify transaction methods were called
            frappe_mock.db.begin.assert_called()
            frappe_mock.db.commit.assert_called()

    def test_error_handling_and_rollback(self):
        """Test error handling with rollback"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        
        # Simulate error during get_all
        frappe_mock.get_all = Mock(side_effect=Exception("Critical error"))
        
        result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
        
        self.assertIn("error", result)

    def test_mixed_enrollment_statuses(self):
        """Test processing students with mixed enrollment statuses"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "MIXED_SET"
        mock_onboarding.status = "Processed"
        
        students = [
            {"student_id": f"STU{i:03d}", "phone": f"+111111{i:04d}"}
            for i in range(10)
        ]
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            # Return different statuses in a pattern
            statuses = ["yes", "no", "student_not_found", "error", "yes"] * 2
            mock_check.side_effect = statuses[:10]
            
            result = update_specific_set_contacts_with_multi_enrollment("MIXED_SET")
            
            self.assertEqual(result["total_processed"], 10)
            self.assertGreater(result["updated"], 0)
            self.assertGreater(result["skipped"], 0)
            self.assertGreater(result["errors"], 0)

    def test_large_batch_processing(self):
        """Test processing large batch of students"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "LARGE_SET"
        mock_onboarding.status = "Processed"
        
        # Create 100 students
        students = [
            {"student_id": f"STU{i:03d}", "phone": f"+1{i:010d}"}
            for i in range(100)
        ]
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            mock_check.return_value = "yes"
            
            result = update_specific_set_contacts_with_multi_enrollment("LARGE_SET")
            
            self.assertEqual(result["total_processed"], 100)
            self.assertEqual(result["updated"], 100)

    def test_validation_error_handling(self):
        """Test handling of validation errors"""
        frappe_mock.get_doc = Mock(side_effect=frappe_mock.ValidationError("Invalid data"))
        
        result = update_specific_set_contacts_with_multi_enrollment("INVALID_SET")
        
        self.assertIn("error", result)

    def test_nested_exception_handling(self):
        """Test nested exception scenarios"""
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        mock_onboarding.status = "Processed"
        
        students = [{"student_id": "STU001", "phone": "+1111111111"}]
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            mock_check.side_effect = Exception("Check failed")
            
            result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
            
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["total_processed"], 1)

    def test_special_characters_in_set_name(self):
        """Test handling of special characters in set names"""
        special_names = ["SET-001", "SET_002", "SET 003", "SET@004", "SET#005"]
        
        with patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment') as mock_update:
            mock_update.return_value = {"updated": 1, "errors": 0, "total_processed": 1}
            
            result = process_multiple_sets_simple(special_names)
            
            self.assertEqual(len(result), 5)
            for r in result:
                self.assertEqual(r["status"], "completed")

    # ========== ADDITIONAL COVERAGE TESTS ==========
    
    def test_coverage_check_student_variations(self):
        """Run check_student_multi_enrollment with different inputs to increase coverage"""
        
        # Test with db.exists = False
        frappe_mock.db.exists = Mock(return_value=False)
        result1 = check_student_multi_enrollment("STU001")
        self.assertIsNotNone(result1)
        
        # Test with different enrollment counts
        frappe_mock.db.exists = Mock(return_value=True)
        
        # Single enrollment
        mock_doc_single = Mock()
        mock_doc_single.enrollment = [Mock()]
        frappe_mock.get_doc = Mock(return_value=mock_doc_single)
        result2 = check_student_multi_enrollment("STU001")
        self.assertIsNotNone(result2)
        
        # No enrollments  
        mock_doc_empty = Mock()
        mock_doc_empty.enrollment = []
        frappe_mock.get_doc = Mock(return_value=mock_doc_empty)
        result3 = check_student_multi_enrollment("STU001")
        self.assertIsNotNone(result3)

    def test_coverage_check_student_edge_cases(self):
        """Test edge cases for check_student_multi_enrollment to increase coverage"""
        
        # Test with exceptions
        frappe_mock.db.exists = Mock(side_effect=Exception("Test"))
        result = check_student_multi_enrollment("STU001")
        self.assertEqual(result, "error")
        
        # Test with None/empty inputs
        test_inputs = [None, "", "VALID_ID"]
        for test_input in test_inputs:
            frappe_mock.db.exists = Mock(return_value=True)
            mock_doc = Mock()
            mock_doc.enrollment = [Mock(), Mock()]
            frappe_mock.get_doc = Mock(return_value=mock_doc)
            result = check_student_multi_enrollment(test_input)
            self.assertIsNotNone(result)

    def test_coverage_update_set_additional_scenarios(self):
        """Run additional scenarios for update_specific_set to increase coverage"""
        
        # Test with empty string
        result = update_specific_set_contacts_with_multi_enrollment("")
        self.assertIsInstance(result, dict)
        
        # Test with general exception
        original_get_doc = frappe_mock.get_doc
        frappe_mock.get_doc = Mock(side_effect=Exception("General error"))
        result = update_specific_set_contacts_with_multi_enrollment("TEST")
        self.assertIsInstance(result, dict)
        frappe_mock.get_doc = original_get_doc

    def test_coverage_update_set_with_students(self):
        """Test update_specific_set with actual student processing"""
        
        mock_onboarding = Mock()
        mock_onboarding.set_name = "TEST_SET"
        mock_onboarding.status = "Processed"
        
        # Mock multiple students
        students = [
            {"student_id": "STU001", "phone": "+1111111111"},
            {"student_id": "STU002", "phone": "+2222222222"},
        ]
        
        frappe_mock.get_doc = Mock(return_value=mock_onboarding)
        frappe_mock.get_all = Mock(return_value=students)
        
        # Mock different check results
        with patch('tap_lms.glific_multi_enrollment_update.check_student_multi_enrollment') as mock_check:
            # Test all possible return values
            test_scenarios = ["yes", "no", "student_not_found", "error"]
            
            for scenario in test_scenarios:
                mock_check.return_value = scenario
                result = update_specific_set_contacts_with_multi_enrollment("TEST_SET")
                self.assertIsInstance(result, dict)

    def test_coverage_process_sets_variations(self):
        """Test process_multiple_sets_simple with different scenarios"""
        
        # Empty list
        result = process_multiple_sets_simple([])
        self.assertIsInstance(result, list)
        
        # Test with different mock responses
        with patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            # Test success scenario
            mock_update.return_value = {"updated": 1, "errors": 0, "total_processed": 1}
            result = process_multiple_sets_simple(["SET001"])
            self.assertIsInstance(result, list)
            
            # Test with errors
            mock_update.return_value = {"updated": 0, "errors": 1, "total_processed": 1}
            result = process_multiple_sets_simple(["SET001"]) 
            self.assertIsInstance(result, list)
            
            # Test with exception
            mock_update.side_effect = Exception("Test error")
            result = process_multiple_sets_simple(["SET001"])
            self.assertIsInstance(result, list)

    def test_coverage_process_my_sets_scenarios(self):
        """Test process_my_sets to increase coverage"""
        
        # Test normal case
        result = process_my_sets()
        self.assertIsInstance(result, str)
        
        # Test with no sets
        original_get_all = frappe_mock.get_all
        frappe_mock.get_all = Mock(return_value=[])
        result = process_my_sets()
        self.assertIsInstance(result, str)
        frappe_mock.get_all = original_get_all
        
        # Test with exception in get_all
        frappe_mock.get_all = Mock(side_effect=Exception("Test"))
        result = process_my_sets()
        self.assertIsInstance(result, str)

    def test_coverage_backend_sets_variations(self):
        """Test get_backend_onboarding_sets with different scenarios"""
        
        # Test with empty result
        original_get_all = frappe_mock.get_all
        frappe_mock.get_all = Mock(return_value=[])
        result = get_backend_onboarding_sets()
        self.assertIsInstance(result, list)
        
        # Test with multiple sets
        mock_sets = [
            {"name": "SET001", "set_name": "Set 1"},
            {"name": "SET002", "set_name": "Set 2"}
        ]
        frappe_mock.get_all = Mock(return_value=mock_sets)
        result = get_backend_onboarding_sets()
        self.assertIsInstance(result, list)
        
        # Test with exception
        frappe_mock.get_all = Mock(side_effect=Exception("Test"))
        result = get_backend_onboarding_sets()
        self.assertIsInstance(result, list)
        
        frappe_mock.get_all = original_get_all

    def test_coverage_run_function_variations(self):
        """Test run_multi_enrollment_update_for_specific_set with more scenarios"""
        
        # Test with empty string
        result = run_multi_enrollment_update_for_specific_set("")
        self.assertIsInstance(result, str)
        
        # Test various patched responses
        with patch('tap_lms.glific_multi_enrollment_update.update_specific_set_contacts_with_multi_enrollment') as mock_update:
            
            # Test different return structures
            test_responses = [
                {"updated": 5, "skipped": 2, "errors": 1, "total_processed": 8},
                {"error": "Some error"},
                {"message": "Some message"}
            ]
            
            for response in test_responses:
                mock_update.return_value = response
                result = run_multi_enrollment_update_for_specific_set("TEST")
                self.assertIsInstance(result, str)

if __name__ == '__main__':
    unittest.main()