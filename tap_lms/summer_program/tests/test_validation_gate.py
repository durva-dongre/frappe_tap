"""
CR-007 regression tests — submission point award + validation gate.

What's being pinned (per user spec 2026-05-19 evening):

  AI validation always runs. Submission.result_status is populated by the
  microservice on every submission. WeekRule.submission_validation_enabled
  is the SINGLE GATE that controls TWO coupled behaviors:

    1. Whether failed/flagged submissions route to Remedial path
       (t6b_failed_feedback_to_remedial) vs. stay on Core (t12_feedback_ready).
    2. Whether submission points are gated by AI validity:
         - validation OFF (W1-2 by spec): Assignment.points_per_item always
         - validation ON, AI valid     : Assignment.points_per_item
         - validation ON, AI Failed/Flagged: 0 points
       Escalation submissions (sent_count >= 1) get
       EscalationStep.points_awarded regardless of validity.

  Streak / gems / weekly_submission_done bump on every submission regardless
  of validity — that happens at save_submission time via the submission
  transitions (T7/T9/T17/T3) with points=0, and is independent of this hook.

These tests mock the microservice + Glific layers and exercise only the
in-process logic of `feedback_consumer_hook.on_feedback_ready`. They do NOT
hit Glific, RabbitMQ, or any real flow.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock


# ════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════

def _fake_pe(name="pe-test-001", current_escalation_step=0,
              current_week=1, current_path="Core"):
    """Minimal PE-like object with the fields _compute_submission_points reads.

    Using frappe._dict so attribute access works the way the helper expects.
    """
    return frappe._dict({
        "name": name,
        "student": "STU-CR007-001",
        "batch": "palv2-test-CR007",
        "archetype": "fence_sitter",
        "experiment_arm": "default",
        "current_path": current_path,
        "current_week": current_week,
        "current_escalation_step": current_escalation_step,
        "glific_id": "",
    })


def _mock_assignment_lookup(points_per_item):
    """Build a side_effect for frappe.db.get_value that returns appropriate
    values per (doctype, name, field) tuple — covering the calls the hook makes.
    """
    def side_effect(*args, **kwargs):
        # frappe.db.get_value("Submission", name, "field") or
        #                    ("Assignment", name, "field"), etc.
        if len(args) < 2:
            return None
        doctype, _name = args[0], args[1]
        field = args[2] if len(args) >= 3 else None
        if doctype == "Assignment" and field == "points_per_item":
            return points_per_item
        return None
    return side_effect


# ════════════════════════════════════════════════════════════
# 1. _compute_submission_points — the core logic
# ════════════════════════════════════════════════════════════

class TestComputeSubmissionPoints(FrappeTestCase):
    """Unit tests for the new point-resolution function. Mocks all Frappe
    DB lookups so we exercise pure logic."""

    def test_lax_mode_valid_returns_points_per_item(self):
        """W1-2 (validation OFF) + AI valid → Assignment.points_per_item."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=0)

        with patch("tap_lms.summer_program.feedback_consumer_hook.frappe") as mock_frappe, \
             patch("tap_lms.summer_program.feedback_consumer_hook._get_week_rule_for_pe",
                   return_value={"submission_validation_enabled": 0}):
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                25 if args[:1] == ("Assignment",) and args[2:3] == ("points_per_item",)
                else (1 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else "ASN-001" if args[:1] == ("Submission",) and args[2:3] == ("assign_id",)
                      else None)
            )
            points = _compute_submission_points(pe, "SUB-001", result_status="Success")

        self.assertEqual(points, 25)

    def test_lax_mode_failed_still_returns_points_per_item(self):
        """W1-2 (validation OFF): even an AI-failed submission gets full points.
        This is the user spec — lax mode preserves the per-item award regardless
        of AI verdict. Failed submissions also do NOT route to Remedial in lax mode
        (covered by TestRoutingGate below)."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=0)

        with patch("tap_lms.summer_program.feedback_consumer_hook.frappe") as mock_frappe, \
             patch("tap_lms.summer_program.feedback_consumer_hook._get_week_rule_for_pe",
                   return_value={"submission_validation_enabled": 0}):
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                25 if args[:1] == ("Assignment",) and args[2:3] == ("points_per_item",)
                else (1 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else "ASN-001" if args[:1] == ("Submission",) and args[2:3] == ("assign_id",)
                      else None)
            )
            points = _compute_submission_points(pe, "SUB-001", result_status="Failed")

        self.assertEqual(points, 25, "Validation OFF must preserve points_per_item even on Failed")

    def test_strict_mode_valid_returns_points_per_item(self):
        """W3+ (validation ON) + AI valid → Assignment.points_per_item."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=0, current_week=3)

        with patch("tap_lms.summer_program.feedback_consumer_hook.frappe") as mock_frappe, \
             patch("tap_lms.summer_program.feedback_consumer_hook._get_week_rule_for_pe",
                   return_value={"submission_validation_enabled": 1}):
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                25 if args[:1] == ("Assignment",) and args[2:3] == ("points_per_item",)
                else (3 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else "ASN-001" if args[:1] == ("Submission",) and args[2:3] == ("assign_id",)
                      else None)
            )
            points = _compute_submission_points(pe, "SUB-001", result_status="Success")

        self.assertEqual(points, 25)

    def test_strict_mode_failed_returns_zero(self):
        """W3+ (validation ON) + AI Failed → 0 points (and routes to Remedial)."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=0, current_week=3)

        with patch("tap_lms.summer_program.feedback_consumer_hook.frappe") as mock_frappe, \
             patch("tap_lms.summer_program.feedback_consumer_hook._get_week_rule_for_pe",
                   return_value={"submission_validation_enabled": 1}):
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                25 if args[:1] == ("Assignment",) and args[2:3] == ("points_per_item",)
                else (3 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else "ASN-001" if args[:1] == ("Submission",) and args[2:3] == ("assign_id",)
                      else None)
            )
            points = _compute_submission_points(pe, "SUB-001", result_status="Failed")

        self.assertEqual(points, 0)

    def test_strict_mode_flagged_returns_zero(self):
        """W3+ (validation ON) + AI 'Success - Flagged' → 0 points.
        Same routing/awarding as Failed — Flagged is a Failed-equivalent verdict."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=0, current_week=3)

        with patch("tap_lms.summer_program.feedback_consumer_hook.frappe") as mock_frappe, \
             patch("tap_lms.summer_program.feedback_consumer_hook._get_week_rule_for_pe",
                   return_value={"submission_validation_enabled": 1}):
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                25 if args[:1] == ("Assignment",) and args[2:3] == ("points_per_item",)
                else (3 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else "ASN-001" if args[:1] == ("Submission",) and args[2:3] == ("assign_id",)
                      else None)
            )
            points = _compute_submission_points(
                pe, "SUB-001", result_status="Success - Flagged"
            )

        self.assertEqual(points, 0)

    def test_escalation_uses_escalation_step_points_regardless_of_validity(self):
        """sent_count >= 1 → EscalationStep.points_awarded, independent of
        validation flag and result_status. Escalation is its own tier system."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=2, current_week=3)

        # Fake escalation step config: [25, 15, 10, 5]
        fake_steps = [
            {"points_awarded": 25},
            {"points_awarded": 15},
            {"points_awarded": 10},
            {"points_awarded": 5},
        ]

        with patch("tap_lms.summer_program.feedback_consumer_hook._escalation_points",
                   return_value=fake_steps[2]["points_awarded"]) as mock_esc:
            points = _compute_submission_points(pe, "SUB-001", result_status="Failed")

        # sent_count=2 → step index 2 → 10 points
        self.assertEqual(points, 10)
        mock_esc.assert_called_once()

    def test_missing_assign_id_returns_zero_with_warning(self):
        """If Submission.assign_id is empty/None, log a warning and award 0
        instead of crashing or guessing."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=0)

        with patch("tap_lms.summer_program.feedback_consumer_hook.frappe") as mock_frappe, \
             patch("tap_lms.summer_program.feedback_consumer_hook._get_week_rule_for_pe",
                   return_value={"submission_validation_enabled": 0}):
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                1 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                else None  # assign_id returns None
            )
            mock_frappe.logger.return_value = MagicMock()
            points = _compute_submission_points(pe, "SUB-001", result_status="Success")

        self.assertEqual(points, 0)
        mock_frappe.logger().warning.assert_called()

    def test_missing_week_rule_treated_as_lax(self):
        """If WeekRule is missing for the week (config gap), treat as
        validation OFF so the student still gets their points. Safer default."""
        from tap_lms.summer_program.feedback_consumer_hook import (
            _compute_submission_points,
        )
        pe = _fake_pe(current_escalation_step=0)

        with patch("tap_lms.summer_program.feedback_consumer_hook.frappe") as mock_frappe, \
             patch("tap_lms.summer_program.feedback_consumer_hook._get_week_rule_for_pe",
                   return_value=None):
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                25 if args[:1] == ("Assignment",) and args[2:3] == ("points_per_item",)
                else (1 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else "ASN-001" if args[:1] == ("Submission",) and args[2:3] == ("assign_id",)
                      else None)
            )
            # Even with Failed result, no WeekRule → defaults to lax → full points
            points = _compute_submission_points(pe, "SUB-001", result_status="Failed")

        self.assertEqual(points, 25, "Missing WeekRule must default to lax (full points)")


# ════════════════════════════════════════════════════════════
# 2. Routing gate — does t6b vs t12 fire correctly?
# ════════════════════════════════════════════════════════════

class TestRoutingGate(FrappeTestCase):
    """Pin the t6b-vs-t12 routing decision in `on_feedback_ready`. The gate is:
    `submission_validation_enabled == 1` AND `result_status in (Failed, Flagged)`
    → t6b. Anything else → t12."""

    def _run_hook(self, result_status, validation_enabled):
        from tap_lms.summer_program import feedback_consumer_hook
        with patch.object(feedback_consumer_hook, "frappe") as mock_frappe, \
             patch.object(feedback_consumer_hook, "_get_week_rule_for_pe",
                          return_value={"submission_validation_enabled":
                                        1 if validation_enabled else 0}), \
             patch.object(feedback_consumer_hook, "_compute_submission_points",
                          return_value=0), \
             patch.object(feedback_consumer_hook, "_award_submission_points_atomic"), \
             patch.object(feedback_consumer_hook, "_sync_contact_fields"), \
             patch("tap_lms.summer_program.state_machine.t12_feedback_ready") as t12, \
             patch("tap_lms.summer_program.state_machine.t6b_failed_feedback_to_remedial") as t6b:

            # Build minimal DB plumbing
            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                "STU-001" if args[:1] == ("Submission",) and args[2:3] == ("student_id",)
                else (1 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else (result_status if args[:1] == ("Submission",) and args[2:3] == ("result_status",)
                            else ("PE-001" if args[:1] == ("ProgramEnrollment",)
                                  else None)))
            )

            pe_mock = MagicMock()
            pe_mock.name = "PE-001"
            pe_mock.current_week = 1
            pe_mock.glific_id = ""
            mock_frappe.get_doc.return_value = pe_mock

            result = feedback_consumer_hook.on_feedback_ready(
                "SUB-001", student_id="STU-001"
            )

        return result, t6b.called, t12.called

    def test_strict_mode_failed_routes_to_remedial(self):
        result, t6b_called, t12_called = self._run_hook(
            result_status="Failed", validation_enabled=True,
        )
        self.assertTrue(t6b_called, "Strict + Failed must call t6b")
        self.assertFalse(t12_called)
        self.assertEqual(result.get("branch"), "remedial")

    def test_strict_mode_flagged_routes_to_remedial(self):
        result, t6b_called, t12_called = self._run_hook(
            result_status="Success - Flagged", validation_enabled=True,
        )
        self.assertTrue(t6b_called, "Strict + Flagged must call t6b")
        self.assertFalse(t12_called)
        self.assertEqual(result.get("branch"), "remedial")

    def test_strict_mode_success_routes_to_feedback_ready(self):
        result, t6b_called, t12_called = self._run_hook(
            result_status="Success", validation_enabled=True,
        )
        self.assertFalse(t6b_called)
        self.assertTrue(t12_called, "Strict + Success must call t12")
        self.assertEqual(result.get("branch"), "feedback_ready")

    def test_lax_mode_failed_stays_on_core(self):
        """W1-2 spec: failed submissions DO NOT route to Remedial in lax mode.
        This is the regression test for the team's '1 bad submission =
        permanent Remedial' surprise scenario."""
        result, t6b_called, t12_called = self._run_hook(
            result_status="Failed", validation_enabled=False,
        )
        self.assertFalse(t6b_called, "Lax + Failed must NOT call t6b")
        self.assertTrue(t12_called)
        self.assertEqual(result.get("branch"), "feedback_ready")

    def test_lax_mode_flagged_stays_on_core(self):
        result, t6b_called, t12_called = self._run_hook(
            result_status="Success - Flagged", validation_enabled=False,
        )
        self.assertFalse(t6b_called)
        self.assertTrue(t12_called)
        self.assertEqual(result.get("branch"), "feedback_ready")


# ════════════════════════════════════════════════════════════
# 3. End-to-end: atomic SQL award fires through on_feedback_ready
# ════════════════════════════════════════════════════════════

class TestAtomicAwardEndToEnd(FrappeTestCase):
    """Pins the full chain: on_feedback_ready → _compute_submission_points
    (non-zero) → _award_submission_points_atomic called with the computed
    value. Code-review caught that TestRoutingGate alone doesn't prove the
    atomic SQL bump actually executes with real points (it mocks
    _compute_submission_points to 0, which short-circuits the bump).

    This test mocks _compute_submission_points to return 25 and asserts
    _award_submission_points_atomic was called with (pe_name, 25).
    """

    def test_on_feedback_ready_awards_points_atomically_when_computed_nonzero(self):
        from tap_lms.summer_program import feedback_consumer_hook

        with patch.object(feedback_consumer_hook, "frappe") as mock_frappe, \
             patch.object(feedback_consumer_hook, "_get_week_rule_for_pe",
                          return_value={"submission_validation_enabled": 0}), \
             patch.object(feedback_consumer_hook, "_compute_submission_points",
                          return_value=25) as mock_compute, \
             patch.object(feedback_consumer_hook, "_award_submission_points_atomic") as mock_award, \
             patch.object(feedback_consumer_hook, "_sync_contact_fields"), \
             patch("tap_lms.summer_program.state_machine.t12_feedback_ready") as t12:

            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                "STU-001" if args[:1] == ("Submission",) and args[2:3] == ("student_id",)
                else (1 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else ("Success" if args[:1] == ("Submission",) and args[2:3] == ("result_status",)
                            else ("PE-001" if args[:1] == ("ProgramEnrollment",)
                                  else None)))
            )

            pe_mock = MagicMock()
            pe_mock.name = "PE-001"
            pe_mock.current_week = 1
            pe_mock.glific_id = ""
            mock_frappe.get_doc.return_value = pe_mock

            result = feedback_consumer_hook.on_feedback_ready(
                "SUB-001", student_id="STU-001"
            )

        # _compute_submission_points was called once with the PE, submission, status
        mock_compute.assert_called_once()
        # _award_submission_points_atomic was called with (pe.name, 25)
        mock_award.assert_called_once_with("PE-001", 25)
        # t12 fires (not t6b — result was Success)
        t12.assert_called_once()
        # Response payload reports the points awarded
        self.assertEqual(result.get("points_awarded"), 25)

    def test_on_feedback_ready_skips_atomic_award_when_points_zero(self):
        """Confirm short-circuit: when _compute_submission_points returns 0
        (e.g., strict-mode Failed), the atomic UPDATE is NOT executed.
        Prevents pointless DB round-trips."""
        from tap_lms.summer_program import feedback_consumer_hook

        with patch.object(feedback_consumer_hook, "frappe") as mock_frappe, \
             patch.object(feedback_consumer_hook, "_get_week_rule_for_pe",
                          return_value={"submission_validation_enabled": 1}), \
             patch.object(feedback_consumer_hook, "_compute_submission_points",
                          return_value=0), \
             patch.object(feedback_consumer_hook, "_award_submission_points_atomic") as mock_award, \
             patch.object(feedback_consumer_hook, "_sync_contact_fields"), \
             patch("tap_lms.summer_program.state_machine.t12_feedback_ready"), \
             patch("tap_lms.summer_program.state_machine.t6b_failed_feedback_to_remedial"):

            mock_frappe.db.get_value.side_effect = lambda *args, **kwargs: (
                "STU-001" if args[:1] == ("Submission",) and args[2:3] == ("student_id",)
                else (3 if args[:1] == ("Submission",) and args[2:3] == ("week",)
                      else ("Failed" if args[:1] == ("Submission",) and args[2:3] == ("result_status",)
                            else ("PE-001" if args[:1] == ("ProgramEnrollment",)
                                  else None)))
            )

            pe_mock = MagicMock()
            pe_mock.name = "PE-001"
            pe_mock.current_week = 3
            pe_mock.glific_id = ""
            mock_frappe.get_doc.return_value = pe_mock

            feedback_consumer_hook.on_feedback_ready(
                "SUB-001", student_id="STU-001"
            )

        # Award helper NEVER called when computed points == 0
        mock_award.assert_not_called()
