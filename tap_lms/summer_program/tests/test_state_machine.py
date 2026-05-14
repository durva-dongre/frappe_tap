"""
Tests for CR-002 v2 state-machine extensions.

Covers:
  - T3/T7/T9/T17 submission transitions extended with streak/gem/submission
    counter bumps and `weekly_submission_done` sticky flag.
  - T19 (`t14_week_advance`) restructured to compute streak/gem updates from
    sticky flags before resetting weeklies.
  - `_enqueue_contact_field_sync` extended to push 8 new gamification fields
    (cache size 26 total, 18 existing + 8 new). `weekly_video_done` is NOT
    pushed. CR-003 adds 1 more (escalation_order) to the per-transition push
    for a total of 20 fields per transition; the 28th cache field
    (escalation_type) is pushed by the dispatcher per-step.

Tests in this file:
  1. test_t7_extends_streak_gems_submission_done_flag
  2. test_t9_extends_same_atomicity
  3. test_t17_t17b_same  (covers T17 + T3 — the four "submission transitions")
  4. test_t19_streak_reset_when_assigned_no_submit
  5. test_t19_streak_unchanged_when_not_assigned
  6. test_t19_gem_floored_at_zero
  7. test_sync_contact_fields_pushes_expected_fields (CR-003: 11 + 8 + 1)
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from tap_lms.summer_program.constants import (
    LABEL_CONTENT_DELIVERED,
    LABEL_GRACE_WINDOW,
    LABEL_SUBMITTED,
    LABEL_WEEK_ADVANCED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    STATE_GRACE_WAITING,
    STATE_NORMAL_CONTENT,
    STATE_NORMAL_ESCALATION,
    STATE_REMEDIAL_CONTENT,
    STATE_SUBMITTED_AWAITING,
    STATE_WEEK_COMPLETED,
)
from tap_lms.summer_program.state_machine import (
    t3_escalation_submission,
    t7_core_submission,
    t9_remedial_submission,
    t14_week_advance,
    t17_grace_submission,
    _enqueue_contact_field_sync,
)


# ════════════════════════════════════════════════════════════
# Test fixtures
# ════════════════════════════════════════════════════════════

def _ensure_batch():
    name = frappe.get_value("Batch", {"name1": "SMachineTestBatch"}, "name")
    if name:
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = "SMachineTestBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = "SMT01"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = 14
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix):
    name = frappe.get_value("Student", {"phone": f"+9999300{suffix}"}, "name")
    if name:
        return name
    s = frappe.new_doc("Student")
    s.name1 = f"SMachineTestStudent{suffix}"
    s.phone = f"+9999300{suffix}"
    s.glific_id = f"glific-sm-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(
    batch_name,
    student_name,
    suffix,
    *,
    resolved_flow_state=STATE_NORMAL_CONTENT,
    journey_label=LABEL_CONTENT_DELIVERED,
    current_week=1,
    total_points=0,
    current_streak=0,
    special_gems=0,
    weekly_video_done=0,
    weekly_submission_done=0,
    total_submission_points=0,
    weekly_submission_points=0,
    weekly_activity_points=0,
    weekly_quiz_points=0,
    total_activity_points=0,
    total_quiz_points=0,
):
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-SM-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-sm-{suffix}"
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = resolved_flow_state
    pe.journey_label = journey_label
    pe.current_path = PATH_CORE
    pe.current_week = current_week
    pe.total_points = total_points
    pe.current_streak = current_streak
    pe.special_gems = special_gems
    pe.weekly_video_done = weekly_video_done
    pe.weekly_submission_done = weekly_submission_done
    pe.total_submission_points = total_submission_points
    pe.weekly_submission_points = weekly_submission_points
    pe.weekly_activity_points = weekly_activity_points
    pe.weekly_quiz_points = weekly_quiz_points
    pe.total_activity_points = total_activity_points
    pe.total_quiz_points = total_quiz_points
    pe.insert(ignore_permissions=True)
    return pe


# ════════════════════════════════════════════════════════════
# T7 / T9 / T17 / T3 — submission transitions
# ════════════════════════════════════════════════════════════

class TestSubmissionTransitionsExtended(FrappeTestCase):
    """T7/T9/T17/T3 must bump the new submission counters, streak, gems, and
    set the weekly_submission_done sticky flag in one atomic save."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def _assert_submission_extras(self, pe, *, prior_streak, prior_gems, points):
        """Common assertions for any of T3/T7/T9/T17."""
        pe.reload()
        self.assertEqual(pe.weekly_submission_done, 1,
                         "Sticky flag must be set on submission")
        self.assertEqual(pe.current_streak, prior_streak + 1,
                         "current_streak += 1 on submission")
        self.assertEqual(pe.special_gems, prior_gems + 1,
                         "special_gems += 1 on submission")
        self.assertEqual(pe.total_submission_points, points,
                         f"total_submission_points += {points}")
        self.assertEqual(pe.weekly_submission_points, points,
                         f"weekly_submission_points += {points}")
        self.assertEqual(pe.total_points, points,
                         f"total_points += {points} (combined cumulative)")

    @patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync")
    def test_t7_extends_streak_gems_submission_done_flag(self, mock_sync):
        """T7 (Core path submission) bumps the full set of CR-002 v2 fields."""
        student = _ensure_student("T7")
        pe = _make_pe(
            self.batch_name, student, "T7",
            current_streak=2, special_gems=3,
        )

        t7_core_submission(pe, points=25, trigger_source="flow_callback")

        self._assert_submission_extras(pe, prior_streak=2, prior_gems=3, points=25)
        pe.reload()
        self.assertEqual(pe.resolved_flow_state, STATE_SUBMITTED_AWAITING)
        self.assertEqual(pe.journey_label, LABEL_SUBMITTED)

    @patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync")
    def test_t9_extends_same_atomicity(self, mock_sync):
        """T9 (Remedial submission) bumps the same fields as T7 — single
        atomic save, no second UPDATE."""
        student = _ensure_student("T9")
        pe = _make_pe(
            self.batch_name, student, "T9",
            resolved_flow_state=STATE_REMEDIAL_CONTENT,
            current_streak=5, special_gems=1,
        )

        t9_remedial_submission(pe, points=10, trigger_source="flow_callback")

        self._assert_submission_extras(pe, prior_streak=5, prior_gems=1, points=10)
        pe.reload()
        self.assertEqual(pe.resolved_flow_state, STATE_SUBMITTED_AWAITING)

    @patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync")
    def test_t17_t17b_same(self, mock_sync):
        """T17 (grace submission) AND T3 (escalation submission) both bump
        the full set. The CR labelled these 'T7/T9/T17/T17b'; in code T3 is
        the fourth submission transition (apply_submission_transition map).
        """
        student_a = _ensure_student("T17")
        pe_a = _make_pe(
            self.batch_name, student_a, "T17",
            resolved_flow_state=STATE_GRACE_WAITING,
            journey_label=LABEL_GRACE_WINDOW,
            current_streak=0, special_gems=0,
        )
        # Grace transition uses these — set them so the reset clauses fire.
        pe_a.in_grace_window = 1
        pe_a.save(ignore_permissions=True)

        t17_grace_submission(pe_a, points=15, trigger_source="flow_callback")
        self._assert_submission_extras(pe_a, prior_streak=0, prior_gems=0, points=15)
        pe_a.reload()
        self.assertEqual(pe_a.in_grace_window, 0)
        self.assertEqual(pe_a.resolved_flow_state, STATE_SUBMITTED_AWAITING)

        # T3 (escalation submission)
        student_b = _ensure_student("T3")
        pe_b = _make_pe(
            self.batch_name, student_b, "T3",
            resolved_flow_state=STATE_NORMAL_ESCALATION,
            current_streak=4, special_gems=2,
        )
        t3_escalation_submission(pe_b, points=20, trigger_source="flow_callback")
        self._assert_submission_extras(pe_b, prior_streak=4, prior_gems=2, points=20)


# ════════════════════════════════════════════════════════════
# T19 (`t14_week_advance`) — streak/gem reset logic
# ════════════════════════════════════════════════════════════

class TestT19WeekAdvanceExtended(FrappeTestCase):
    """CR-002 v2 §"T19 week-advance — revised". Penalty branch fires IFF
    weekly_video_done=1 AND weekly_submission_done=0. Cumulative counters
    are never reset; all 3 weekly_* counters and both sticky flags ARE reset."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    @patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync")
    def test_t19_streak_reset_when_assigned_no_submit(self, mock_sync):
        """Penalty branch: assigned video this week (weekly_video_done=1)
        but no submission (weekly_submission_done=0) → streak → 0,
        gems → max(0, gems-1)."""
        student = _ensure_student("T19a")
        pe = _make_pe(
            self.batch_name, student, "T19a",
            resolved_flow_state=STATE_WEEK_COMPLETED,
            current_week=1,
            current_streak=4,
            special_gems=3,
            weekly_video_done=1,
            weekly_submission_done=0,
            # Pre-existing weekly + cumulative values to verify reset behavior
            weekly_activity_points=10, weekly_quiz_points=5, weekly_submission_points=0,
            total_activity_points=30, total_quiz_points=15,
            total_submission_points=50, total_points=95,
        )

        t14_week_advance(pe, new_week=2)

        pe.reload()
        # Penalty applied
        self.assertEqual(pe.current_streak, 0, "Streak resets to 0 on penalty")
        self.assertEqual(pe.special_gems, 2, "Gems decrement by 1 (3 → 2)")
        # All weeklies reset
        self.assertEqual(pe.weekly_activity_points, 0)
        self.assertEqual(pe.weekly_quiz_points, 0)
        self.assertEqual(pe.weekly_submission_points, 0)
        self.assertEqual(pe.weekly_video_done, 0)
        self.assertEqual(pe.weekly_submission_done, 0)
        # Cumulative NEVER reset
        self.assertEqual(pe.total_activity_points, 30)
        self.assertEqual(pe.total_quiz_points, 15)
        self.assertEqual(pe.total_submission_points, 50)
        self.assertEqual(pe.total_points, 95)
        # Week advanced + journey label updated
        self.assertEqual(pe.current_week, 2)
        self.assertEqual(pe.journey_label, LABEL_WEEK_ADVANCED)

    @patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync")
    def test_t19_streak_unchanged_when_not_assigned(self, mock_sync):
        """No-penalty branch: nothing assigned this week
        (weekly_video_done=0) → streak/gems unchanged regardless of
        weekly_submission_done value."""
        student = _ensure_student("T19b")
        pe = _make_pe(
            self.batch_name, student, "T19b",
            resolved_flow_state=STATE_WEEK_COMPLETED,
            current_week=1,
            current_streak=7,
            special_gems=4,
            weekly_video_done=0,
            weekly_submission_done=0,
        )

        t14_week_advance(pe, new_week=2)

        pe.reload()
        self.assertEqual(pe.current_streak, 7,
                         "Streak unchanged when no video assigned")
        self.assertEqual(pe.special_gems, 4,
                         "Gems unchanged when no video assigned")

    @patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync")
    def test_t19_no_penalty_when_submission_done(self, mock_sync):
        """No-penalty branch: video assigned AND submitted → streak/gems
        unchanged (they were already bumped at submission time)."""
        student = _ensure_student("T19c")
        pe = _make_pe(
            self.batch_name, student, "T19c",
            resolved_flow_state=STATE_WEEK_COMPLETED,
            current_week=1,
            current_streak=3,
            special_gems=5,
            weekly_video_done=1,
            weekly_submission_done=1,
        )

        t14_week_advance(pe, new_week=2)

        pe.reload()
        self.assertEqual(pe.current_streak, 3,
                         "Streak unchanged when both flags = 1")
        self.assertEqual(pe.special_gems, 5,
                         "Gems unchanged when both flags = 1")

    @patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync")
    def test_t19_gem_floored_at_zero(self, mock_sync):
        """E9: penalty branch with special_gems already at 0 → gems stays
        0, NOT -1. Floor enforced in Python via max(0, gems-1)."""
        student = _ensure_student("T19d")
        pe = _make_pe(
            self.batch_name, student, "T19d",
            resolved_flow_state=STATE_WEEK_COMPLETED,
            current_week=1,
            current_streak=2,
            special_gems=0,
            weekly_video_done=1,
            weekly_submission_done=0,
        )

        t14_week_advance(pe, new_week=2)

        pe.reload()
        self.assertEqual(pe.current_streak, 0)
        self.assertEqual(pe.special_gems, 0,
                         "Gems must floor at 0 — never negative")


# ════════════════════════════════════════════════════════════
# Contact-field sync — 18 + 8 + 2 = 28 fields after CR-003
# ════════════════════════════════════════════════════════════

class TestSyncContactFieldsExtended(FrappeTestCase):
    """`_enqueue_contact_field_sync` must include the 8 CR-002 v2 gamification
    fields alongside the existing 18 plus the 2 new CR-003 escalation-routing
    fields (escalation_order AND escalation_type — post-2026-05-13 follow-up
    both flow via this standard sync; the eager dispatcher push was removed).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    @patch("tap_lms.summer_program.state_machine.frappe.enqueue")
    def test_sync_contact_fields_pushes_expected_fields(self, mock_enqueue):
        """The fields dict serialized into the background job includes the
        11 state-mutating fields plus 8 new gamification fields plus 2 new
        CR-003 fields (escalation_order + escalation_type) = 21 per-transition
        push fields. Plus the 7 immutable enrollment-time fields = 28 total
        in the Glific cache. Post 2026-05-13 follow-up both CR-003 fields
        flow via this standard sync; the eager dispatcher push was deleted."""
        student = _ensure_student("CFSYNC")
        pe = _make_pe(
            self.batch_name, student, "CFSYNC",
            current_streak=2, special_gems=3,
            weekly_submission_done=1, weekly_video_done=1,
            total_activity_points=42, weekly_activity_points=10,
            total_quiz_points=33, weekly_quiz_points=8,
            total_submission_points=51, weekly_submission_points=25,
        )

        _enqueue_contact_field_sync(pe)

        mock_enqueue.assert_called_once()
        kwargs = mock_enqueue.call_args.kwargs
        fields = kwargs.get("fields") or {}

        # All 8 new gamification fields must be present
        self.assertIn("total_activity_points", fields)
        self.assertIn("weekly_activity_points", fields)
        self.assertIn("total_quiz_points", fields)
        self.assertIn("weekly_quiz_points", fields)
        self.assertIn("total_submission_points", fields)
        self.assertIn("weekly_submission_points", fields)
        self.assertIn("special_gems", fields)
        self.assertIn("weekly_submission_done", fields)

        # Values are string-cast like the existing pattern
        self.assertEqual(fields["total_activity_points"], "42")
        self.assertEqual(fields["weekly_activity_points"], "10")
        self.assertEqual(fields["total_quiz_points"], "33")
        self.assertEqual(fields["weekly_quiz_points"], "8")
        self.assertEqual(fields["total_submission_points"], "51")
        self.assertEqual(fields["weekly_submission_points"], "25")
        self.assertEqual(fields["special_gems"], "3")
        self.assertEqual(fields["weekly_submission_done"], "1")

        # weekly_video_done is INTERNAL-ONLY — must NOT be in the Glific push
        self.assertNotIn("weekly_video_done", fields,
                         "weekly_video_done is internal-only; never push to Glific")

        # Sanity: existing 11 state-mutating fields are still present
        for k in (
            "resolved_flow_state", "current_week", "current_path",
            "current_tier", "program_status", "total_points", "current_streak",
            "grace_window_end_at", "current_expected_submission_type",
            "last_escalation_step", "submission_count",
            # last_escalation_step is the Glific CONTACT FIELD name (public
            # contract per L-008). The PE column was renamed to
            # current_escalation_step but the contact field name stays.
        ):
            self.assertIn(k, fields, f"existing field {k} missing from sync")

        # CR-003 (post-impl): escalation_order AND escalation_type are both
        # included in the per-transition sync. The eager
        # _push_escalation_contact_fields helper was removed — the dispatcher
        # writes current_escalation_step + current_escalation_type to PE
        # inside T2/T4/T8/T10, and this sync map pushes both to Glific.
        self.assertIn("escalation_order", fields)
        self.assertIn("escalation_type", fields)

        # Total count = 11 state-mutating + 8 CR-002 v2 gamification +
        # 2 CR-003 (escalation_order + escalation_type) = 21 per-transition
        # push fields. (The other 7 immutables live elsewhere.)
        self.assertEqual(
            len(fields), 21,
            "Per-transition sync pushes 11 existing + 8 gamification + "
            "2 CR-003 (escalation_order + escalation_type) = 21 fields",
        )
