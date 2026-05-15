import json
import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _import_save_submission_with_stubs():
    frappe = MagicMock()
    frappe.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
    frappe.whitelist = _frappe_whitelist
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


def _frappe_whitelist(fn=None, **kwargs):
    if fn:
        return fn

    def decorator(func):
        return func

    return decorator


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


class TestGetSubmissionFeedback(unittest.TestCase):
    def test_completed_submission_returns_feedback_fields(self):
        save_submission = _import_save_submission_with_stubs()

        submission = MagicMock()
        submission.status = "Completed"
        submission.overall_feedback = "Good work"
        submission.overall_feedback_translated = "Good work translated"
        submission.audio_feedback_url = "https://example.com/audio.mp3"

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.get_doc.return_value = submission

            response = save_submission.get_submission_feedback("SUB-001")

        mock_frappe.get_doc.assert_called_once_with("Submission", "SUB-001")
        self.assertEqual(response, {
            "status": "Completed",
            "overall_feedback": "Good work",
            "overall_feedback_translated": "Good work translated",
            "audio_feedback_url": "https://example.com/audio.mp3",
        })

    def test_pending_submission_returns_status_only(self):
        save_submission = _import_save_submission_with_stubs()

        submission = MagicMock()
        submission.status = "Processing"

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.get_doc.return_value = submission

            response = save_submission.get_submission_feedback("SUB-001")

        self.assertEqual(response, {"status": "Processing"})

    def test_missing_submission_returns_not_found_error(self):
        save_submission = _import_save_submission_with_stubs()

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
            mock_frappe.get_doc.side_effect = mock_frappe.DoesNotExistError()

            response = save_submission.get_submission_feedback("SUB-MISSING")

        self.assertEqual(response, {"error": "Submission not found"})

    def test_unexpected_error_is_logged(self):
        save_submission = _import_save_submission_with_stubs()

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.DoesNotExistError = type("DoesNotExistError", (Exception,), {})
            mock_frappe.get_doc.side_effect = RuntimeError("database unavailable")

            response = save_submission.get_submission_feedback("SUB-001")

        self.assertEqual(
            response,
            {"error": "An error occurred while checking submission feedback"},
        )
        mock_frappe.log_error.assert_called_once()


# ════════════════════════════════════════════════════════════
# Audit-fix tests (2026-05-15) — tasks #77/79, #78, #80, #81
# Uses the same import-stub strategy as the bridge tests above so it can
# run without a live bench. No frappe.db.commit() per L-017.
# ════════════════════════════════════════════════════════════


class TestSaveSubmissionAuditFixes(unittest.TestCase):
    """Tests for the 2026-05-15 audit-fix bundle (tasks #77-#82).

    - test_save_submission_accepts_legacy_content_id — task #78 (P-006/L-009).
    - test_save_submission_in_clause_handles_all_pre_submission_labels —
      task #77 (L-005 fix) + task #79 (MariaDB fallback removed).
    - test_submission_count_increments_exactly_once — task #80
      (state-machine transitions no longer bump submission_count;
      _try_claim_primary owns the column).
    - test_create_submission_failure_does_not_bump_state — task #81
      (insert-first ordering; savepoint rolls back on insert failure).
    """

    def _build_pe(self, journey_label="content_delivered"):
        pe = MagicMock()
        pe.name = "PE-001"
        pe.student = "STU-001"
        pe.batch = "BATCH-001"
        pe.glific_id = "GL-001"
        pe.current_week = 1
        pe.resolved_flow_state = "normal_content_delivery"
        pe.journey_label = journey_label
        pe.submission_count = 0
        pe.current_escalation_step = 0
        pe.current_expected_submission_type = "text_word"
        pe.current_tier = "Basic"
        pe.current_path = "core"
        pe.archetype = "submitter"
        pe.experiment_arm = "default"
        pe.course_level = "CL-001"
        pe.language = "en"
        pe.program_status = "active"
        pe.next_action_type = ""
        pe.next_action_at = None
        return pe

    def test_save_submission_accepts_legacy_content_id(self):
        """Task #78 (L-009 / P-006): content_id is a deprecated alias for
        assignment_id. Calling with `content_id=` only (no `assignment_id=`)
        must succeed and log a deprecation warning."""
        save_submission = _import_save_submission_with_stubs()
        pe = self._build_pe()
        submission_doc = MagicMock()
        submission_doc.name = "SUB-001"

        with patch.object(save_submission, "frappe") as mock_frappe, \
                patch.object(save_submission, "_resolve_student", return_value="STU-001"), \
                patch.object(save_submission, "get_active_pe", return_value=pe), \
                patch.object(save_submission, "_try_claim_primary", return_value=True), \
                patch.object(save_submission, "_calculate_points", return_value=10), \
                patch.object(save_submission, "_create_submission", return_value=submission_doc), \
                patch.object(save_submission, "_log_student_content_submission"), \
                patch.object(save_submission, "_update_engagement"), \
                patch.object(save_submission, "_queue_submission_processing"), \
                patch.object(save_submission, "apply_submission_transition", return_value=("T7", True)), \
                patch.object(save_submission, "log_event"):
            mock_frappe.local.response = {}
            mock_frappe.utils.random_string = lambda n: "abcd1234"

            response = save_submission.save_submission(
                student_id="STU-001",
                content_id="ASN-LEGACY",  # legacy param — no assignment_id
                submission="my answer",
            )

        self.assertTrue(response.get("success"))
        self.assertEqual(response.get("status"), "accepted")
        # Deprecation log should have fired with "SP API Deprecation" title.
        deprecation_logged = any(
            call_args.args and "SP API Deprecation" in (call_args.args[1] if len(call_args.args) > 1 else "")
            for call_args in mock_frappe.log_error.call_args_list
        )
        self.assertTrue(
            deprecation_logged,
            f"Expected deprecation log; got calls: {mock_frappe.log_error.call_args_list}",
        )

    def test_save_submission_missing_assignment_id_is_rejected(self):
        """Companion to the previous: with neither param the call must fail
        cleanly with status='missing_param'."""
        save_submission = _import_save_submission_with_stubs()

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.local.response = {}

            save_submission.save_submission(
                student_id="STU-001",
                submission="my answer",
            )

        self.assertEqual(mock_frappe.local.response.get("status"), "missing_param")
        self.assertFalse(mock_frappe.local.response.get("success"))

    def test_save_submission_in_clause_handles_all_pre_submission_labels(self):
        """Task #77 (L-005 fix): the atomic claim's
        `journey_label IN (%s, %s, %s, %s, %s)` must accept every
        pre-submission label without the IN-tuple mangling that the previous
        `IN %s` binding suffered on Postgres.

        We verify by inspecting the SQL+params passed to frappe.db.sql:
          - the SQL contains a flat IN-list of 5 placeholders;
          - the params include the PE name plus the 5 expected labels.
        """
        save_submission = _import_save_submission_with_stubs()
        pe = self._build_pe()

        with patch.object(save_submission, "frappe") as mock_frappe:
            # RETURNING-shaped result — single row means the claim succeeded.
            mock_frappe.db.sql.return_value = [("PE-001",)]
            result = save_submission._try_claim_primary(pe, week=1)

        self.assertTrue(result)
        self.assertEqual(mock_frappe.db.sql.call_count, 1)
        sql_call = mock_frappe.db.sql.call_args
        sql_text = sql_call.args[0]
        params = sql_call.args[1]

        # Flat IN list (no `IN %s` mangling).
        self.assertIn("IN (%s, %s, %s, %s, %s)", sql_text)
        # PE name + 5 labels = 6 params total.
        self.assertEqual(len(params), 6)
        self.assertEqual(params[0], "PE-001")
        self.assertEqual(
            set(params[1:]),
            {"enrolled", "content_delivered", "grace_window", "resumed", "week_advanced"},
        )

    def test_try_claim_primary_returns_false_on_zero_rows(self):
        """Task #79 corollary: with the MariaDB fallback gone, a 0-row
        UPDATE (RETURNING []) must short-circuit to is_primary=False without
        falling through to a second UPDATE."""
        save_submission = _import_save_submission_with_stubs()
        pe = self._build_pe(journey_label="submitted")

        with patch.object(save_submission, "frappe") as mock_frappe:
            mock_frappe.db.sql.return_value = []  # nothing claimed
            result = save_submission._try_claim_primary(pe, week=1)

        self.assertFalse(result)
        # Exactly one UPDATE — the old fallback would have made it 2.
        self.assertEqual(mock_frappe.db.sql.call_count, 1)

    def test_submission_count_not_in_primary_transition_source(self):
        """Task #80: submission_count is bumped only by _try_claim_primary's
        atomic UPDATE. The four primary transitions (T7/T9/T17/T3) must NOT
        include submission_count in their `extra_updates` dict.

        We can't import state_machine inside the stub environment (it pulls
        in real frappe and glific_integration), so we assert against the
        source file itself: each primary-transition function body must not
        contain a `submission_count` write.
        """
        import os
        import re

        here = os.path.dirname(__file__)
        sm_path = os.path.join(here, "..", "state_machine.py")
        with open(sm_path, "r", encoding="utf-8") as fh:
            source = fh.read()

        # Extract each function body. Each `def tX_...` ends at the next
        # top-level `def` or `# ──` separator. Splitting on "\ndef " is
        # robust enough for this audit-grade check.
        primary_fns = [
            "t7_core_submission",
            "t9_remedial_submission",
            "t17_grace_submission",
            "t3_escalation_submission",
        ]
        for fn_name in primary_fns:
            m = re.search(
                rf"def {fn_name}\([^)]*\):(.*?)(?=\ndef |\Z)",
                source,
                re.DOTALL,
            )
            self.assertIsNotNone(m, f"Could not locate {fn_name} in state_machine.py")
            body = m.group(1)
            # The body must not contain a `submission_count` write
            # (e.g. `"submission_count": ...`). We exclude the
            # human-readable NOTE comment that explains the ownership.
            body_no_comments = re.sub(r"#[^\n]*", "", body)
            self.assertNotIn(
                '"submission_count"', body_no_comments,
                f"{fn_name} still writes submission_count (task #80 regression).",
            )

    def test_create_submission_failure_does_not_bump_state(self):
        """Task #81: if _create_submission raises, the savepoint must roll
        back and _try_claim_primary must NOT have been called. The PE
        journey_label and submission_count remain untouched."""
        save_submission = _import_save_submission_with_stubs()
        pe = self._build_pe()

        with patch.object(save_submission, "frappe") as mock_frappe, \
                patch.object(save_submission, "_resolve_student", return_value="STU-001"), \
                patch.object(save_submission, "get_active_pe", return_value=pe), \
                patch.object(save_submission, "_try_claim_primary") as mock_claim, \
                patch.object(save_submission, "_create_submission",
                             side_effect=RuntimeError("DB write failed")), \
                patch.object(save_submission, "_update_engagement"), \
                patch.object(save_submission, "log_event"):
            mock_frappe.local.response = {}
            mock_frappe.utils.random_string = lambda n: "abcd1234"

            response = save_submission.save_submission(
                student_id="STU-001",
                assignment_id="ASN-001",
                submission="my answer",
            )

        # _try_claim_primary must NOT have run — insert failed first.
        mock_claim.assert_not_called()
        # Savepoint rollback was invoked.
        mock_frappe.db.rollback.assert_called_once()
        # Response surfaces the failure cleanly.
        self.assertEqual(mock_frappe.local.response.get("status"), "insert_failed")
        self.assertFalse(mock_frappe.local.response.get("success"))


if __name__ == "__main__":
    unittest.main()
