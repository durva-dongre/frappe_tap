"""
Tests for flow_callback._response shape — Glific Integration Guide v3.0 §1.2.

Every webhook response from update_flow_status MUST include:
  - resolved_flow_state
  - next_action_type
  - next_action_at
  - program_status

Glific flows read @results.webhook.<field> for immediate routing because
contact-field sync is async (~200-500ms delay). If any field is missing,
flows reading it get null and either misroute or fail closed.

These tests guard the contract at the helper level. End-to-end handler tests
should call _handle_* directly with a mock PE and check the same four keys
are present.
"""
import unittest
from unittest.mock import MagicMock, patch

from tap_lms.summer_program.flow_callback import _response


REQUIRED_FIELDS = {
    "resolved_flow_state",
    "next_action_type",
    "next_action_at",
    "program_status",
}


def _make_pe(
    resolved_flow_state="normal_content_delivery",
    next_action_type="escalation",
    next_action_at="2026-06-01 12:00:00",
    program_status="active",
):
    pe = MagicMock()
    pe.resolved_flow_state = resolved_flow_state
    pe.next_action_type = next_action_type
    pe.next_action_at = next_action_at
    pe.program_status = program_status
    return pe


class TestResponseHelperContract(unittest.TestCase):
    """G2 regression coverage — v3.0 four-tuple is non-negotiable."""

    def test_response_includes_all_four_required_fields(self):
        pe = _make_pe()
        resp = _response(pe, "test_action")
        for field in REQUIRED_FIELDS:
            self.assertIn(field, resp, f"Missing v3.0 required field: {field}")

    def test_response_includes_success_and_action(self):
        pe = _make_pe()
        resp = _response(pe, "delivery_confirmed")
        self.assertTrue(resp["success"])
        self.assertEqual(resp["action"], "delivery_confirmed")

    def test_response_emits_empty_string_for_none_values(self):
        """Glific expects strings, not None — None serializes as null and breaks
        Glific's string-comparison routing."""
        pe = _make_pe(
            next_action_type=None,
            next_action_at=None,
            program_status=None,
        )
        resp = _response(pe, "submission_flow_completed")
        self.assertEqual(resp["next_action_type"], "")
        self.assertEqual(resp["next_action_at"], "")
        self.assertEqual(resp["program_status"], "")

    def test_response_stringifies_next_action_at_datetime(self):
        """next_action_at on the PE can be a datetime; Glific needs a string."""
        import datetime
        pe = _make_pe(next_action_at=datetime.datetime(2026, 6, 1, 12, 0))
        resp = _response(pe, "escalation_scheduled")
        # Just assert it's a string and non-empty
        self.assertIsInstance(resp["next_action_at"], str)
        self.assertTrue(resp["next_action_at"])

    def test_extras_merge_without_clobbering_required_fields(self):
        """Handlers add extras like current_week, in_grace_window. Those must
        not shadow the v3.0 four-tuple."""
        pe = _make_pe()
        resp = _response(pe, "week_completed", current_week=3, custom_data="x")
        self.assertEqual(resp["current_week"], 3)
        self.assertEqual(resp["custom_data"], "x")
        # All four required fields still present
        for field in REQUIRED_FIELDS:
            self.assertIn(field, resp)

    def test_extras_can_override_required_field_if_handler_must(self):
        """We deliberately don't lock the four-tuple as immutable — a handler
        that explicitly overrides program_status (e.g., to report a stale read
        as 'unknown') is allowed. The test documents this is intentional."""
        pe = _make_pe(program_status="active")
        resp = _response(pe, "test", program_status="overridden")
        self.assertEqual(resp["program_status"], "overridden")


class TestAllHandlerResponses(unittest.TestCase):
    """Smoke test: every named handler in flow_callback returns the v3.0 shape.

    These tests use mocked PE objects and patch the state-machine transitions
    so we exercise just the response-building path, not the actual state logic.
    """

    def _assert_v3_shape(self, resp):
        for field in REQUIRED_FIELDS:
            self.assertIn(field, resp, f"Response missing v3.0 field: {field}\n{resp}")
        self.assertIn("success", resp)
        self.assertIn("action", resp)

    def test_submission_flow_handler_returns_v3_shape(self):
        from tap_lms.summer_program.flow_callback import _handle_submission_flow
        pe = _make_pe()
        pe.save = MagicMock()
        resp = _handle_submission_flow(pe, "SP_Submission", "completed", {})
        self._assert_v3_shape(resp)
        self.assertEqual(resp["action"], "submission_flow_completed")

    def test_grace_flow_handler_returns_v3_shape(self):
        from tap_lms.summer_program.flow_callback import _handle_grace_flow
        pe = _make_pe()
        pe.save = MagicMock()
        pe.in_grace_window = 1
        resp = _handle_grace_flow(pe, "SP_Grace_Entry", "completed", {})
        self._assert_v3_shape(resp)
        self.assertEqual(resp["in_grace_window"], 1)

    def test_reengagement_handler_returns_v3_shape(self):
        from tap_lms.summer_program.flow_callback import _handle_reengagement
        pe = _make_pe()
        pe.save = MagicMock()
        pe.re_engagement_count = 2
        # log_event needs the pe to have a `name` attribute
        pe.name = "PE-TEST-001"
        with patch("tap_lms.summer_program.flow_callback.log_event"):
            resp = _handle_reengagement(pe, "SP_Paused_Reengagement", "completed", {})
        self._assert_v3_shape(resp)
        self.assertEqual(resp["re_engagement_count"], 3)

    def test_binge_info_handler_returns_v3_shape(self):
        from tap_lms.summer_program.flow_callback import _handle_binge_info
        pe = _make_pe()
        pe.save = MagicMock()
        resp = _handle_binge_info(pe, "SP_Paused_Binge", "completed", {})
        self._assert_v3_shape(resp)
        self.assertEqual(resp["action"], "binge_info_delivered")

    def test_info_flow_handler_returns_v3_shape(self):
        """Covers SP_Week_Summary and SP_Program_Complete."""
        from tap_lms.summer_program.flow_callback import _handle_info_flow
        pe = _make_pe()
        pe.save = MagicMock()
        resp = _handle_info_flow(pe, "SP_Week_Summary", "completed", {})
        self._assert_v3_shape(resp)
        self.assertEqual(resp["action"], "info_delivered")


if __name__ == "__main__":
    unittest.main()
