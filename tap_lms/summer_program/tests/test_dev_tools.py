"""
Tests for `summer_program.dev_tools` — the SP testing reset utilities.

Covers:
  1. reset_pe_to_state_0 — happy path: PE in week 3 / mid-escalation / with
     gamification points → reset to state 0 (normal_content_delivery, week 1,
     all counters and points zeroed, scheduler pointers cleared).
  2. reset_pe_to_state_0 — dry_run flag: snapshot only, no writes.
  3. reset_pe_to_state_0 — production-site safety guard: raises
     PermissionError when site name contains 'prod' unless override passed.
  4. reset_pe_to_state_0 — verifies maintain_collections is called with the
     correct from/to state delta (so CR-005 group membership reshuffles).
  5. list_pes_for_batch — read-only listing returns expected shape.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from tap_lms.summer_program.constants import (
    LABEL_CONTENT_DELIVERED,
    LABEL_ENROLLED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    STATE_NORMAL_CONTENT,
    STATE_NORMAL_ESCALATION,
)
from tap_lms.summer_program.dev_tools import (
    reset_pe_to_state_0,
    list_pes_for_batch,
    _assert_dev_site,
)


# ════════════════════════════════════════════════════════════
# Test fixtures (mirrors test_state_machine.py shape)
# ════════════════════════════════════════════════════════════

def _ensure_batch():
    name = frappe.get_value("Batch", {"name1": "DevToolsTestBatch"}, "name")
    if name:
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = "DevToolsTestBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    # Registration window (mandatory on Batch doctype as of current schema)
    batch.regist_start_date = "2025-12-01"
    batch.regist_end_date = "2025-12-31"
    batch.batch_id = "DTT01"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = 14
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix):
    name = frappe.get_value("Student", {"phone": f"+9999400{suffix}"}, "name")
    if name:
        return name
    s = frappe.new_doc("Student")
    s.name1 = f"DevToolsTestStudent{suffix}"
    s.phone = f"+9999400{suffix}"
    s.glific_id = f"glific-dt-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_advanced_pe(batch_name, student_name, suffix):
    """Create a PE in a non-default state: week 3, mid-escalation, with
    gamification points + submission counts. Reset should zero all of these.
    """
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-DT-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-dt-{suffix}"
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = STATE_NORMAL_ESCALATION
    pe.journey_label = LABEL_CONTENT_DELIVERED
    pe.current_path = PATH_CORE
    pe.current_week = 3
    pe.submission_count = 5
    pe.current_escalation_step = 2
    pe.last_escalation_step = 1
    pe.delivery_failure_count = 1
    pe.in_grace_window = 1
    pe.total_activity_points = 30
    pe.weekly_activity_points = 10
    pe.total_quiz_points = 40
    pe.weekly_quiz_points = 15
    pe.total_submission_points = 50
    pe.weekly_submission_points = 25
    pe.current_streak = 3
    pe.special_gems = 4
    pe.weekly_video_done = 1
    pe.weekly_submission_done = 1
    pe.next_action_type = "escalation"
    pe.insert(ignore_permissions=True)
    return pe


# ════════════════════════════════════════════════════════════
# 1. Happy-path reset
# ════════════════════════════════════════════════════════════

class TestResetPeToState0(FrappeTestCase):
    """Reset must move an advanced PE back to state 0 in one call."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    @patch("tap_lms.summer_program.dev_tools._assert_dev_site")
    @patch("tap_lms.summer_program.dev_tools._enqueue_contact_field_sync")
    @patch("tap_lms.summer_program.dev_tools.maintain_collections")
    def test_reset_zeros_all_state_and_counters(
        self, mock_maintain, mock_sync, _mock_guard,
    ):
        student = _ensure_student("HP")
        pe = _make_advanced_pe(self.batch_name, student, "HP")

        result = reset_pe_to_state_0(
            student,
            delete_history=False,   # keep test isolated from history doctypes
            push_to_glific=True,
            verbose=False,
        )

        pe.reload()

        # Core state machine
        self.assertEqual(pe.resolved_flow_state, STATE_NORMAL_CONTENT)
        self.assertEqual(pe.journey_label, LABEL_ENROLLED)
        self.assertEqual(pe.program_status, PROGRAM_ACTIVE)
        self.assertEqual(pe.current_week, 1)
        self.assertEqual(pe.current_path, PATH_CORE)

        # Counters
        self.assertEqual(pe.submission_count, 0)
        self.assertEqual(pe.current_escalation_step, 0)
        self.assertEqual(pe.last_escalation_step, 0)
        self.assertEqual(pe.delivery_failure_count, 0)

        # Grace
        self.assertEqual(pe.in_grace_window, 0)
        self.assertIsNone(pe.grace_window_start)
        self.assertIsNone(pe.grace_window_end_at)

        # CR-002 v2 gamification — all zeroed
        self.assertEqual(pe.total_activity_points, 0)
        self.assertEqual(pe.weekly_activity_points, 0)
        self.assertEqual(pe.total_quiz_points, 0)
        self.assertEqual(pe.weekly_quiz_points, 0)
        self.assertEqual(pe.total_submission_points, 0)
        self.assertEqual(pe.weekly_submission_points, 0)
        self.assertEqual(pe.current_streak, 0)
        self.assertEqual(pe.special_gems, 0)
        self.assertEqual(pe.weekly_video_done, 0)
        self.assertEqual(pe.weekly_submission_done, 0)

        # Scheduler pointers
        self.assertIsNone(pe.next_action_at)
        self.assertEqual(pe.next_action_type, "")

        # CR-005 group membership delta — called with the previous state
        mock_maintain.assert_called_once()
        _, kwargs = mock_maintain.call_args
        self.assertEqual(kwargs["from_state"], STATE_NORMAL_ESCALATION)
        self.assertEqual(kwargs["to_state"], STATE_NORMAL_CONTENT)

        # Glific contact-field sync — should have been enqueued
        mock_sync.assert_called_once()

        # Return shape
        self.assertIn("before", result)
        self.assertIn("after", result)
        self.assertEqual(
            result["before"]["resolved_flow_state"], STATE_NORMAL_ESCALATION
        )
        self.assertEqual(
            result["after"]["resolved_flow_state"], STATE_NORMAL_CONTENT
        )


# ════════════════════════════════════════════════════════════
# 2. Dry-run safety
# ════════════════════════════════════════════════════════════

class TestResetPeDryRun(FrappeTestCase):
    """dry_run=True must not modify the database."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    @patch("tap_lms.summer_program.dev_tools._assert_dev_site")
    @patch("tap_lms.summer_program.dev_tools._enqueue_contact_field_sync")
    @patch("tap_lms.summer_program.dev_tools.maintain_collections")
    def test_dry_run_no_writes(self, mock_maintain, mock_sync, _mock_guard):
        student = _ensure_student("DRY")
        pe = _make_advanced_pe(self.batch_name, student, "DRY")

        result = reset_pe_to_state_0(student, dry_run=True, verbose=False)

        # State unchanged
        pe.reload()
        self.assertEqual(pe.resolved_flow_state, STATE_NORMAL_ESCALATION)
        self.assertEqual(pe.current_week, 3)
        self.assertEqual(pe.submission_count, 5)
        self.assertEqual(pe.current_streak, 3)

        # No Glific side effects
        mock_maintain.assert_not_called()
        mock_sync.assert_not_called()

        # Return shape — before populated, after is None
        self.assertIsNotNone(result["before"])
        self.assertIsNone(result["after"])


# ════════════════════════════════════════════════════════════
# 3. Production-site safety guard
# ════════════════════════════════════════════════════════════

class TestSafetyGuard(FrappeTestCase):
    """_assert_dev_site refuses on production-suggestive site names."""

    def test_guard_raises_on_prod_site_name(self):
        with patch.object(frappe.local, "site", "tap_lms.prod"):
            with self.assertRaises(frappe.PermissionError) as ctx:
                _assert_dev_site(i_know_this_is_destructive=False)
            self.assertIn("prod", str(ctx.exception).lower())

    def test_guard_raises_on_live_site_name(self):
        with patch.object(frappe.local, "site", "tap-live.example.com"):
            with self.assertRaises(frappe.PermissionError):
                _assert_dev_site(i_know_this_is_destructive=False)

    def test_guard_override_bypasses_check(self):
        with patch.object(frappe.local, "site", "tap_lms.prod"):
            # Should NOT raise
            _assert_dev_site(i_know_this_is_destructive=True)

    def test_guard_passes_on_dev_site(self):
        with patch.object(frappe.local, "site", "tap_lms.dev"):
            # Should NOT raise
            _assert_dev_site(i_know_this_is_destructive=False)


# ════════════════════════════════════════════════════════════
# 4. list_pes_for_batch
# ════════════════════════════════════════════════════════════

class TestListPesForBatch(FrappeTestCase):
    """list_pes_for_batch is read-only and returns the expected shape."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def test_list_returns_active_and_paused_only(self):
        student_active = _ensure_student("LST_A")
        student_dropped = _ensure_student("LST_D")
        pe_active = _make_advanced_pe(self.batch_name, student_active, "LSTA")
        pe_dropped = _make_advanced_pe(self.batch_name, student_dropped, "LSTD")
        pe_dropped.program_status = "dropped"
        pe_dropped.save(ignore_permissions=True)

        rows = list_pes_for_batch(self.batch_name)

        pe_names = {r["pe"] for r in rows}
        self.assertIn(pe_active.name, pe_names)
        self.assertNotIn(
            pe_dropped.name, pe_names,
            "Dropped PEs should not appear in the listing",
        )

        # Shape check — each row has the expected keys
        for r in rows:
            for key in (
                "pe", "student", "resolved_flow_state",
                "current_week", "current_path", "submission_count",
            ):
                self.assertIn(key, r)
