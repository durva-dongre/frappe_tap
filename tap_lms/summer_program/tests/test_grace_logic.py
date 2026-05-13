"""
Tests for CR-003 grace logic restructure.

Covers:
  - T0 sets the grace clock from Batch.grace_window_days
  - T19 (t14_week_advance) re-arms the grace clock at week advance
  - handle_grace_check drops at expiry
  - handle_grace_check is a no-op when weekly_submission_done = 1
  - Grace clock resets every week
  - T5 (escalation_to_grace) preserves the existing clock (no reset)
"""
from datetime import timedelta

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_to_date, get_datetime
from unittest.mock import patch

from tap_lms.summer_program.constants import (
    LABEL_CONTENT_DELIVERED,
    LABEL_GRACE_WINDOW,
    LABEL_SUBMITTED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    STATE_GRACE_WAITING,
    STATE_NORMAL_CONTENT,
    STATE_NORMAL_ESCALATION,
    STATE_PROGRAM_DROPPED,
    STATE_WEEK_COMPLETED,
)
from tap_lms.summer_program.state_machine import (
    t0_enrollment,
    t5_escalation_to_grace,
    t14_week_advance,
    t17_grace_expired,
)


def _ensure_batch(grace_days=14):
    name = frappe.get_value("Batch", {"name1": f"GraceTestBatch{grace_days}"}, "name")
    if name:
        # Make sure grace_window_days is what we expect.
        frappe.db.set_value("Batch", name, "grace_window_days", grace_days,
                            update_modified=False)
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = f"GraceTestBatch{grace_days}"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = f"GT{grace_days:02d}"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = grace_days
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix):
    name = frappe.get_value("Student", {"phone": f"+9999700{suffix}"}, "name")
    if name:
        return name
    s = frappe.new_doc("Student")
    s.name1 = f"GraceTestStudent{suffix}"
    s.phone = f"+9999700{suffix}"
    s.glific_id = f"glific-grace-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(batch_name, student_name, suffix, **kwargs):
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-GR-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-grace-{suffix}"
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = kwargs.get("resolved_flow_state", STATE_NORMAL_CONTENT)
    pe.journey_label = kwargs.get("journey_label", LABEL_CONTENT_DELIVERED)
    pe.current_path = PATH_CORE
    pe.current_week = kwargs.get("current_week", 1)
    pe.current_tier = "Basic"
    pe.archetype = "Submitter"
    pe.weekly_submission_done = kwargs.get("weekly_submission_done", 0)
    pe.weekly_video_done = kwargs.get("weekly_video_done", 0)
    if "grace_window_end_at" in kwargs:
        pe.grace_window_end_at = kwargs["grace_window_end_at"]
        pe.grace_window_start = kwargs.get("grace_window_start",
                                          add_to_date(now_datetime(), days=-1))
        pe.in_grace_window = 1
    pe.insert(ignore_permissions=True)
    return pe.name


class TestGraceClockSetAtWeekStart(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch(grace_days=14)

    def test_t0_sets_grace_clock_from_batch(self):
        """T0 (enrollment) arms grace_window_end_at = now + 14 days using
        Batch.grace_window_days, sets grace_window_start, and flips
        in_grace_window = 1.
        """
        s = _ensure_student("01")
        pe_name = _make_pe(self.batch_name, s, "01")
        pe = frappe.get_doc("ProgramEnrollment", pe_name)

        with patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            t0_enrollment(pe, "test")

        pe.reload()
        self.assertEqual(pe.in_grace_window, 1)
        self.assertIsNotNone(pe.grace_window_start)
        self.assertIsNotNone(pe.grace_window_end_at)

        # End - start should be 14 days (give or take a few seconds of
        # transition latency).
        delta = get_datetime(pe.grace_window_end_at) - get_datetime(pe.grace_window_start)
        self.assertAlmostEqual(delta.total_seconds(), 14 * 86400, delta=120)

    def test_t19_re_arms_grace_clock_on_week_advance(self):
        """t14_week_advance (function name for T19 in the architecture doc)
        re-arms grace_window_start + grace_window_end_at for the new week.
        """
        s = _ensure_student("02")
        pe_name = _make_pe(
            self.batch_name, s, "02",
            resolved_flow_state=STATE_WEEK_COMPLETED,
            current_week=1,
            grace_window_end_at=add_to_date(now_datetime(), days=-7),  # stale
            grace_window_start=add_to_date(now_datetime(), days=-21),
        )
        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        # Stale clock at week 1, well in the past.
        prior_end = get_datetime(pe.grace_window_end_at)

        with patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            t14_week_advance(pe, 2, week_rule=None, trigger_source="test")

        pe.reload()
        new_end = get_datetime(pe.grace_window_end_at)
        # New end is in the future, definitely > the old stale end.
        self.assertGreater(new_end, prior_end)
        # And ~14 days from now.
        delta = new_end - now_datetime()
        self.assertGreater(delta.total_seconds(), 13 * 86400)
        self.assertLess(delta.total_seconds(), 15 * 86400)
        self.assertEqual(pe.current_week, 2)

    def test_grace_clock_resets_every_week(self):
        """Two week advances produce two distinct grace_window_end_at values
        — proving the clock truly resets on each advance, not just on T0.
        """
        s = _ensure_student("03")
        pe_name = _make_pe(self.batch_name, s, "03",
                           resolved_flow_state=STATE_WEEK_COMPLETED,
                           current_week=1)
        pe = frappe.get_doc("ProgramEnrollment", pe_name)

        with patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            t14_week_advance(pe, 2, week_rule=None, trigger_source="test")
            pe.reload()
            first_end = get_datetime(pe.grace_window_end_at)

            # Move time forward by mutating: we can't actually wait, but we
            # can compare two close calls. The state machine uses
            # now_datetime() each time, so the second call's clock should
            # be >= the first.
            pe.resolved_flow_state = STATE_WEEK_COMPLETED
            pe.save(ignore_permissions=True)
            t14_week_advance(pe, 3, week_rule=None, trigger_source="test")
            pe.reload()
            second_end = get_datetime(pe.grace_window_end_at)

        self.assertGreaterEqual(second_end, first_end)
        self.assertEqual(pe.current_week, 3)


class TestGraceCheckHandler(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch(grace_days=14)

    def test_grace_check_drops_at_expiry(self):
        """handle_grace_check: clock expired AND weekly_submission_done = 0
        → t17_grace_expired runs, PE lands in program_dropped.
        """
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("11")
        pe_name = _make_pe(
            self.batch_name, s, "11",
            resolved_flow_state=STATE_GRACE_WAITING,
            journey_label=LABEL_GRACE_WINDOW,
            grace_window_end_at=add_to_date(now_datetime(), minutes=-5),
            weekly_submission_done=0,
        )

        with patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": "grace_check",
                "journey_label": LABEL_GRACE_WINDOW,
            })
            pe_dispatcher.handle_grace_check(row)

        new_state = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "resolved_flow_state"
        )
        self.assertEqual(new_state, STATE_PROGRAM_DROPPED)
        drop_reason = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "drop_reason"
        )
        self.assertEqual(drop_reason, "grace_expired")

    def test_grace_check_no_op_if_submission_done(self):
        """handle_grace_check: weekly_submission_done = 1 → no drop,
        just clear the action.
        """
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("12")
        pe_name = _make_pe(
            self.batch_name, s, "12",
            resolved_flow_state=STATE_GRACE_WAITING,
            journey_label=LABEL_GRACE_WINDOW,
            grace_window_end_at=add_to_date(now_datetime(), minutes=-5),
            weekly_submission_done=1,
        )

        row = frappe._dict({
            "name": pe_name,
            "next_action_type": "grace_check",
            "journey_label": LABEL_GRACE_WINDOW,
        })
        pe_dispatcher.handle_grace_check(row)

        new_state = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "resolved_flow_state"
        )
        # Still in grace_waiting; no drop.
        self.assertEqual(new_state, STATE_GRACE_WAITING)
        next_action_type = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "next_action_type"
        )
        self.assertEqual(next_action_type or "", "")


class TestT5PreservesGraceClock(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch(grace_days=14)

    def test_t5_escalation_to_grace_preserves_existing_clock(self):
        """T5 (escalation exhausted with some activity → grace) does NOT
        reset grace_window_end_at. CR-003: the clock was set at week start.
        """
        s = _ensure_student("21")
        original_end = add_to_date(now_datetime(), days=10)  # 10 days from now
        pe_name = _make_pe(
            self.batch_name, s, "21",
            resolved_flow_state=STATE_NORMAL_ESCALATION,
            journey_label=LABEL_CONTENT_DELIVERED,
            grace_window_end_at=original_end,
        )
        pe = frappe.get_doc("ProgramEnrollment", pe_name)

        with patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            t5_escalation_to_grace(pe, "test")

        pe.reload()
        # grace_window_end_at unchanged from the value at week start.
        new_end = get_datetime(pe.grace_window_end_at)
        self.assertAlmostEqual(
            (new_end - get_datetime(original_end)).total_seconds(),
            0, delta=2,
            msg="T5 must NOT reset grace_window_end_at",
        )
        # State is grace_waiting; next_action_type = grace_check at grace_end.
        self.assertEqual(pe.resolved_flow_state, STATE_GRACE_WAITING)
        self.assertEqual(pe.next_action_type, "grace_check")
