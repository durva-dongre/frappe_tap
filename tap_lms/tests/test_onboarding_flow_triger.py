import unittest
from unittest.mock import patch, MagicMock
import tap_lms.glific_onboarding as glific_onboarding

class TestGlificOnboarding(unittest.TestCase):

    @patch("tap_lms.glific_onboarding.frappe")
    def test_trigger_onboarding_flow_success(self, mock_frappe):
        """Test successful onboarding flow"""
        # Mock student document
        mock_student = MagicMock()
        mock_frappe.get_doc.return_value = mock_student

        # Call function
        result = glific_onboarding.trigger_onboarding_flow("STU001")

        # Assertions
        self.assertEqual(result["status"], "success")
        mock_frappe.get_doc.assert_called_once_with("Student", "STU001")
        mock_student.save.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

    @patch("tap_lms.glific_onboarding.frappe")
    def test_trigger_onboarding_flow_student_not_found(self, mock_frappe):
        """Test when student record is missing"""
        mock_frappe.get_doc.side_effect = frappe.DoesNotExistError

        result = glific_onboarding.trigger_onboarding_flow("INVALID_ID")

        self.assertEqual(result["status"], "failed")
        self.assertIn("not found", result["message"])

    @patch("tap_lms.glific_onboarding.frappe")
    def test_trigger_onboarding_flow_exception(self, mock_frappe):
        """Test unexpected onboarding error"""
        mock_frappe.get_doc.side_effect = Exception("DB connection failed")

        result = glific_onboarding.trigger_onboarding_flow("STU002")

        self.assertEqual(result["status"], "error")
        self.assertIn("DB connection failed", result["message"])
