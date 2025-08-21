

import unittest
from unittest.mock import patch, MagicMock
import frappe

# Correct import path
from tap_lms.glific_utils import run_glific_id_update


class TestRunGlificIDUpdate(unittest.TestCase):
    """Test cases for run_glific_id_update function"""

    @patch("tap_lms.glific_utils.frappe.db.count")
    def test_run_glific_id_update_with_no_students(self, mock_count):
        """Test when there are no students without Glific ID"""
        mock_count.return_value = 0

        result = run_glific_id_update()
        self.assertEqual(result, "No students found without Glific ID.")

        # Ensure frappe.db.count was called once
        mock_count.assert_called_once_with("Student", {"glific_id": ["in", ["", None]]})

    @patch("tap_lms.glific_utils.enqueue")
    @patch("tap_lms.glific_utils.frappe.db.count")
    def test_run_glific_id_update_with_students(self, mock_count, mock_enqueue):
        """Test when students exist and the job gets enqueued"""
        mock_count.return_value = 5

        # Create a mock job object with an id
        mock_job = MagicMock()
        mock_job.id = "12345"
        mock_enqueue.return_value = mock_job

        result = run_glific_id_update()

        self.assertIn("Glific ID update process started", result)
        self.assertIn(mock_job.id, result)

        # Check db.count is called
        mock_count.assert_called_once_with("Student", {"glific_id": ["in", ["", None]]})

        # Check enqueue is called
        mock_enqueue.assert_called_once()
#test