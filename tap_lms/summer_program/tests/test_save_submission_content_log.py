import json
import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _import_save_submission_with_stubs():
    frappe = MagicMock()
    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.now_datetime = MagicMock(return_value="2026-05-12 10:00:00")
    frappe_utils.today = MagicMock(return_value="2026-05-12")
    frappe_utils.getdate = MagicMock(side_effect=lambda value: value)
    frappe_utils.cint = lambda value: int(value or 0)

    state_machine = types.ModuleType("tap_lms.summer_program.state_machine")
    state_machine.get_active_pe = MagicMock()
    state_machine.apply_submission_transition = MagicMock(return_value=("T7", True))

    event_log = types.ModuleType("tap_lms.summer_program.event_log")
    event_log.log_event = MagicMock()

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe_utils
    sys.modules["tap_lms.summer_program.state_machine"] = state_machine
    sys.modules["tap_lms.summer_program.event_log"] = event_log
    sys.modules.pop("tap_lms.summer_program.save_submission", None)
    return importlib.import_module("tap_lms.summer_program.save_submission")


class TestSaveSubmissionContentLogBridge(unittest.TestCase):
    def test_primary_submission_writes_student_content_log(self):
        save_submission = _import_save_submission_with_stubs()

        pe = MagicMock()
        pe.name = "PE-001"
        pe.course_level = "CL-001"
        pe.current_tier = "Basic"
        pe.current_expected_submission_type = "photo_video_artefact"
        submission_doc = MagicMock()
        submission_doc.name = "SUB-001"

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.db.exists.return_value = None
            log = MagicMock()
            mock_frappe.new_doc.return_value = log

            save_submission._log_student_content_submission(
                pe=pe,
                student_id="STU-001",
                week=2,
                payload={"submission_type": "image"},
                assignment_id="ASN-001",
                points=10,
                submission_doc=submission_doc,
            )

        mock_frappe.new_doc.assert_called_once_with("StudentContentLog")
        self.assertEqual(log.student, "STU-001")
        self.assertEqual(log.course_level, "CL-001")
        self.assertEqual(log.stage_no, 2)
        self.assertEqual(log.content_type, "Assignment")
        self.assertEqual(log.content_id, "ASN-001")
        self.assertEqual(log.action, "completed")
        self.assertEqual(log.tier, "Basic")
        metadata = json.loads(log.metadata)
        self.assertEqual(metadata["source"], "save_submission")
        self.assertEqual(metadata["submission_id"], "SUB-001")
        self.assertEqual(metadata["program_enrollment"], "PE-001")
        self.assertTrue(metadata["is_valid"])
        log.insert.assert_called_once_with(ignore_permissions=True)

    def test_existing_student_content_log_is_not_duplicated(self):
        save_submission = _import_save_submission_with_stubs()

        pe = MagicMock()

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.db.exists.return_value = "SCL-001"

            save_submission._log_student_content_submission(
                pe=pe,
                student_id="STU-001",
                week=1,
                payload={"submission_type": "text"},
                assignment_id="ASN-001",
                points=0,
                submission_doc=None,
            )

        mock_frappe.new_doc.assert_not_called()

    def test_expected_submission_type_compatibility(self):
        save_submission = _import_save_submission_with_stubs()
        _is_expected_submission_type = save_submission._is_expected_submission_type

        self.assertTrue(_is_expected_submission_type("image", "photo"))
        self.assertTrue(_is_expected_submission_type("video", "photo_video_artefact"))
        self.assertTrue(_is_expected_submission_type("text", "voice_note_text_summary"))
        self.assertFalse(_is_expected_submission_type("image", "voice_note_text_summary"))


if __name__ == "__main__":
    unittest.main()
