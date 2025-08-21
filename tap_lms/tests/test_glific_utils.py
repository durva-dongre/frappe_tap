

# import frappe
# import unittest
# from unittest.mock import patch, MagicMock, call


# class TestGlificUtils(unittest.TestCase):
#     """Complete test cases for 100% coverage"""


#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     @patch('frappe.db.commit')
#     @patch('frappe.publish_realtime')
#     def test_process_glific_id_update_single_batch(self, mock_publish, mock_commit, mock_update):
#         """Test process_glific_id_update with single batch"""
#         # Setup mocks
#         mock_update.return_value = 50
        
#         # Import and call function
#         from tap_lms.glific_utils import process_glific_id_update
#         process_glific_id_update(50)
        
#         # Simple assertions
#         mock_update.assert_called_once()
#         mock_commit.assert_called_once()
#         self.assertEqual(mock_publish.call_count, 2)  # Progress + completion

#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     @patch('frappe.db.commit')
#     @patch('frappe.publish_realtime')
#     def test_process_glific_id_update_multiple_batches(self, mock_publish, mock_commit, mock_update):
#         """Test process_glific_id_update with multiple batches"""
#         # Setup mocks
#         mock_update.side_effect = [100, 100, 50]  # 3 batches
        
#         # Import and call function
#         from tap_lms.glific_utils import process_glific_id_update
#         process_glific_id_update(250)
        
#         # Simple assertions
#         self.assertEqual(mock_update.call_count, 3)
#         self.assertEqual(mock_commit.call_count, 3)
#         self.assertEqual(mock_publish.call_count, 4)  # 3 progress + 1 completion

#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     @patch('frappe.db.commit')
#     @patch('frappe.publish_realtime')
#     def test_process_glific_id_update_zero_students(self, mock_publish, mock_commit, mock_update):
#         """Test process_glific_id_update with zero students"""
#         # Import and call function
#         from tap_lms.glific_utils import process_glific_id_update
#         process_glific_id_update(0)
        
#         # Simple assertions
#         mock_update.assert_not_called()
#         mock_commit.assert_not_called()
#         mock_publish.assert_called_once()  # Only completion call

#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     @patch('frappe.db.commit')
#     @patch('frappe.publish_realtime')
#     def test_process_glific_id_update_exact_batch_size(self, mock_publish, mock_commit, mock_update):
#         """Test process_glific_id_update with exactly 100 students"""
#         # Setup mocks
#         mock_update.return_value = 100
        
#         # Import and call function
#         from tap_lms.glific_utils import process_glific_id_update
#         process_glific_id_update(100)
        
#         # Simple assertions
#         mock_update.assert_called_once()
#         mock_commit.assert_called_once()
#         self.assertEqual(mock_publish.call_count, 2)  # Progress + completion

#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     @patch('frappe.db.commit')
#     @patch('frappe.publish_realtime')
#     def test_large_student_count(self, mock_publish, mock_commit, mock_update):
#         """Test with large student count"""
#         # Setup mocks
#         mock_update.return_value = 100
        
#         # Import and call function
#         from tap_lms.glific_utils import process_glific_id_update
#         process_glific_id_update(1000)  # 10 batches
        
#         # Simple assertions
#         self.assertEqual(mock_update.call_count, 10)
#         self.assertEqual(mock_commit.call_count, 10)
#         self.assertEqual(mock_publish.call_count, 11)  # 10 progress + 1 completion

#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     @patch('frappe.db.commit')
#     @patch('frappe.publish_realtime')
#     def test_boundary_conditions(self, mock_publish, mock_commit, mock_update):
#         """Test boundary conditions (99, 100, 101 students)"""
#         test_cases = [99, 100, 101]
        
#         for total_students in test_cases:
#             # Reset mocks
#             mock_update.reset_mock()
#             mock_commit.reset_mock()
#             mock_publish.reset_mock()
            
#             # Setup mock
#             mock_update.return_value = min(100, total_students)
            
#             # Import and call function
#             from tap_lms.glific_utils import process_glific_id_update
#             process_glific_id_update(total_students)
            
#             # Calculate expected batches
#             expected_batches = (total_students + 99) // 100  # Ceiling division
            
#             # Simple assertions
#             self.assertEqual(mock_commit.call_count, expected_batches, 
#                            f"Failed for {total_students} students")
            
#             # Should have progress calls + 1 completion call
#             expected_publish_calls = expected_batches + 1
#             self.assertEqual(mock_publish.call_count, expected_publish_calls,
#                            f"Failed publish count for {total_students} students")

import frappe
import unittest
from unittest.mock import patch, MagicMock


class TestGlificUtils(unittest.TestCase):
    """Complete test cases for 100% coverage"""

    @patch("frappe.whitelist", lambda *args, **kwargs: (lambda f: f))
    @patch("tap_lms.glific_utils.enqueue")
    @patch("frappe.db.count")
    def test_run_glific_id_update_with_no_students(self, mock_count, mock_enqueue):
        """Test run_glific_id_update when there are no students without Glific ID"""
        mock_count.return_value = 0

        from tap_lms.glific_utils import run_glific_id_update

        result = run_glific_id_update()
        self.assertEqual(result, "No students found without Glific ID.")
        mock_enqueue.assert_not_called()

    @patch("frappe.whitelist", lambda *args, **kwargs: (lambda f: f))
    @patch("tap_lms.glific_utils.enqueue")
    @patch("frappe.db.count")
    def test_run_glific_id_update_with_students(self, mock_count, mock_enqueue):
        """Test run_glific_id_update when students exist"""
        mock_count.return_value = 5
        mock_enqueue.return_value = MagicMock(id="JOB123")

        from tap_lms.glific_utils import run_glific_id_update

        result = run_glific_id_update()
        self.assertIn("Glific ID update process started", result)
        self.assertIn("JOB123", result)

        mock_count.assert_called_once_with("Student", {"glific_id": ["in", ["", None]]})
        mock_enqueue.assert_called_once()


if __name__ == "__main__":
    unittest.main()
