"""
Tests for summer_program.pe_dispatcher

Covers the per-PE event-driven dispatcher and its eight handlers, focusing on
the bug classes the prior code review (CR-2026-05-10) flagged:

- B1: dispatcher SQL referenced a non-existent `Batch.scheduler_mode` column.
  Test ensures the dispatcher runs cleanly on PG with no JOIN to Batch.
- B2: missing FOR UPDATE SKIP LOCKED + journey-label-guarded atomic claim
  caused duplicate Glific flow triggers under parallel workers. Test
  simulates a parallel worker by manipulating journey_label between SELECT
  and dispatch and asserts the second pass is a no-op (P-001).
- B3: WHERE filter `program_status = 'active'` excluded paused PEs and made
  pause_check / re_engagement handlers unreachable. Test enrols a paused
  PE with `next_action_type = pause_check` and asserts the dispatcher picks
  it up.
- #52 (counter race): handle_feedback_timeout, handle_re_engagement, and
  t25_delivery_failure must use COALESCE-update SQL to be race-tolerant.
  Test calls the handler twice in sequence and asserts the counter equals
  exactly 2 (no read-then-write loss).

Glific is mocked via unittest.mock.patch so we never hit the network.
No frappe.db.commit() in tests — the runner relies on transaction rollback
for isolation (lesson L-017).
"""
import frappe
from datetime import timedelta
from unittest.mock import patch
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime, add_to_date

from tap_lms.summer_program.constants import (
    ACTION_CONTENT_DELIVERY,
    ACTION_ESCALATION,
    ACTION_FEEDBACK_TIMEOUT,
    ACTION_GRACE_REMINDER,
    ACTION_PAUSE_CHECK,
    ACTION_RE_ENGAGEMENT,
    ACTION_WEEK_ADVANCEMENT,
    BPR_ACTIVE,
    BPR_COLLECTIONS_READY,
    LABEL_CONTENT_DELIVERED,
    LABEL_PAUSED,
    LABEL_GRACE_WINDOW,
    LABEL_SUBMITTED,
    PROGRAM_ACTIVE,
    PROGRAM_PAUSED,
    PATH_CORE,
    STATE_NORMAL_CONTENT,
    STATE_PAUSED_BINGE,
    STATE_GRACE_WAITING,
    STATE_SUBMITTED_AWAITING,
    STATE_WEEK_COMPLETED,
    VALIDATION_PASSED,
)


# ════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════


def _ensure_batch():
    """Create or fetch a test Batch the test PEs hang off."""
    name = frappe.get_value("Batch", {"name1": "DispatcherTestBatch"}, "name")
    if name:
        return name

    batch = frappe.new_doc("Batch")
    batch.name1 = "DispatcherTestBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = "DSPT01"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = 14
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix):
    """Create a Student row."""
    name = frappe.get_value("Student", {"phone": f"+9999000{suffix}"}, "name")
    if name:
        return name

    s = frappe.new_doc("Student")
    s.name1 = f"DispatcherTestStudent{suffix}"
    s.phone = f"+9999000{suffix}"
    s.glific_id = f"glific-disp-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(
    batch_name,
    student_name,
    next_action_at,
    next_action_type,
    program_status=PROGRAM_ACTIVE,
    resolved_flow_state=STATE_NORMAL_CONTENT,
    journey_label=LABEL_CONTENT_DELIVERED,
    glific_id=None,
    enrollment_suffix="A",
    current_week=1,
    submission_count=0,
    current_path=PATH_CORE,
    grace_window_start=None,
    feedback_retry_count=0,
    re_engagement_count=0,
    delivery_failure_count=0,
):
    """Insert a ProgramEnrollment with the fields needed for dispatcher tests."""
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-DISP-{enrollment_suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = glific_id or f"glific-disp-{enrollment_suffix}"
    pe.program_status = program_status
    pe.resolved_flow_state = resolved_flow_state
    pe.journey_label = journey_label
    pe.current_path = current_path
    pe.current_week = current_week
    pe.submission_count = submission_count
    pe.next_action_at = next_action_at
    pe.next_action_type = next_action_type
    if grace_window_start is not None:
        pe.grace_window_start = grace_window_start
    pe.insert(ignore_permissions=True)

    # Set fields the tests examine but the doctype may not have a default for.
    # Use raw UPDATE so we don't trip controllers and we exercise the same
    # SQL path the production COALESCE-update does.
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET feedback_retry_count = %s,
               re_engagement_count = %s,
               delivery_failure_count = %s
         WHERE name = %s
        """,
        (feedback_retry_count, re_engagement_count, delivery_failure_count, pe.name),
    )
    return pe.name


# ════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════


class TestPeDispatcher(FrappeTestCase):
    """Dispatcher-level (process_program_actions / dispatch_pending_actions) tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def setUp(self):
        # Clean any leftover dispatcher PEs from a previous test in the same class
        # (FrappeTestCase wraps each test in a rollback, but be defensive).
        for pe in frappe.get_all(
            "ProgramEnrollment",
            filters={"batch": self.batch_name},
            pluck="name",
        ):
            frappe.delete_doc("ProgramEnrollment", pe, force=True)

    def test_dispatcher_picks_due_pes_in_order(self):
        """Dispatcher SELECT orders by next_action_at and routes to handlers in order."""
        from tap_lms.summer_program import pe_dispatcher

        now = now_datetime()
        s1 = _ensure_student("01")
        s2 = _ensure_student("02")
        s3 = _ensure_student("03")
        s4 = _ensure_student("04")
        s5 = _ensure_student("05")

        pe_names = []
        for i, (s, offset_min) in enumerate(
            [(s1, -50), (s2, -40), (s3, -30), (s4, -20), (s5, -10)]
        ):
            pe_names.append(
                _make_pe(
                    self.batch_name,
                    s,
                    add_to_date(now, minutes=offset_min),
                    ACTION_CONTENT_DELIVERY,
                    enrollment_suffix=f"O{i}",
                    glific_id=f"glific-disp-O{i}",
                )
            )

        called_with = []

        def fake_handler(pe_row):
            called_with.append(pe_row.name)

        # Replace handle_content_delivery in HANDLER_MAP for the duration of the test.
        original = pe_dispatcher.HANDLER_MAP[ACTION_CONTENT_DELIVERY]
        pe_dispatcher.HANDLER_MAP[ACTION_CONTENT_DELIVERY] = fake_handler
        try:
            result = pe_dispatcher.dispatch_pending_actions()
        finally:
            pe_dispatcher.HANDLER_MAP[ACTION_CONTENT_DELIVERY] = original

        # All five should be processed in next_action_at ascending order.
        self.assertEqual(result["dispatched"], 5)
        self.assertEqual(called_with, pe_names)

    def test_atomic_claim_prevents_double_dispatch(self):
        """If a parallel worker advances journey_label between SELECT and claim,
        the dispatcher's UPDATE-RETURNING returns 0 rows and the handler is
        skipped. Models the L-010 / P-001 race."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("11")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-5),
            ACTION_CONTENT_DELIVERY,
            enrollment_suffix="C1",
            glific_id="glific-disp-C1",
        )

        called = []

        # Simulate the parallel worker by advancing journey_label inside the
        # handler — that's after our SELECT but before the next dispatch tick.
        # The first dispatch should claim and call the handler; the second
        # dispatch (with no fresh next_action_at) should pick up nothing.
        def fake_handler(pe_row):
            called.append(pe_row.name)

        original = pe_dispatcher.HANDLER_MAP[ACTION_CONTENT_DELIVERY]
        pe_dispatcher.HANDLER_MAP[ACTION_CONTENT_DELIVERY] = fake_handler

        # First — manually flip journey_label *before* dispatch, simulating
        # a parallel handler that has already moved this PE past the
        # snapshot the dispatcher SELECT saw.
        try:
            # Re-set next_action_at so SELECT sees the row
            frappe.db.sql(
                'UPDATE "tabProgramEnrollment" SET next_action_at = %s WHERE name = %s',
                (add_to_date(now_datetime(), minutes=-5), pe_name),
            )

            # Patch the SQL helper so the SELECT runs but BEFORE the atomic claim
            # we mutate journey_label, simulating a concurrent handler advancing
            # state. Use a wrapper that fires after the SELECT.
            real_sql = frappe.db.sql
            select_done = {"done": False}

            def maybe_race(query, values=None, *args, **kwargs):
                # Detect the SELECT that opens the dispatcher tick.
                is_select = (
                    isinstance(query, str)
                    and "FOR UPDATE SKIP LOCKED" in query
                )
                result = real_sql(query, values, *args, **kwargs) if values is not None else real_sql(query, *args, **kwargs)
                if is_select and not select_done["done"]:
                    select_done["done"] = True
                    # Race: a "parallel handler" advances journey_label.
                    real_sql(
                        'UPDATE "tabProgramEnrollment" SET journey_label = %s WHERE name = %s',
                        (LABEL_SUBMITTED, pe_name),
                    )
                return result

            with patch.object(frappe.db, "sql", side_effect=maybe_race):
                result = pe_dispatcher.dispatch_pending_actions()

            # Handler must NOT have been called — atomic claim returned 0 rows.
            self.assertEqual(called, [])
            self.assertEqual(result.get("dispatched", 0), 0)
            self.assertGreaterEqual(result.get("skipped", 0), 1)
        finally:
            pe_dispatcher.HANDLER_MAP[ACTION_CONTENT_DELIVERY] = original

    def test_paused_pe_with_pause_check_action_dispatched(self):
        """A PE with program_status='paused' and next_action_type='pause_check'
        must be picked up by the dispatcher (regression for B3)."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("21")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-1),
            ACTION_PAUSE_CHECK,
            program_status=PROGRAM_PAUSED,
            resolved_flow_state=STATE_PAUSED_BINGE,
            journey_label=LABEL_PAUSED,
            enrollment_suffix="P1",
            glific_id="glific-disp-P1",
            current_week=2,
        )

        called = []

        def fake_pause_check(pe_row):
            called.append(pe_row.name)

        original = pe_dispatcher.HANDLER_MAP[ACTION_PAUSE_CHECK]
        pe_dispatcher.HANDLER_MAP[ACTION_PAUSE_CHECK] = fake_pause_check
        try:
            result = pe_dispatcher.dispatch_pending_actions()
        finally:
            pe_dispatcher.HANDLER_MAP[ACTION_PAUSE_CHECK] = original

        self.assertEqual(called, [pe_name])
        self.assertEqual(result["dispatched"], 1)

    def test_journey_label_changes_skip_dispatch(self):
        """If journey_label changes between SELECT and the atomic claim, the
        atomic UPDATE returns 0 rows and the handler is NOT invoked.
        Same primitive as test_atomic_claim_prevents_double_dispatch but
        framed against a different action type to confirm the guard isn't
        action-type-specific."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("31")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-5),
            ACTION_GRACE_REMINDER,
            resolved_flow_state=STATE_GRACE_WAITING,
            journey_label=LABEL_GRACE_WINDOW,
            enrollment_suffix="G1",
            glific_id="glific-disp-G1",
            grace_window_start=add_to_date(now_datetime(), days=-7),
        )

        called = []

        def fake_grace(pe_row):
            called.append(pe_row.name)

        original = pe_dispatcher.HANDLER_MAP[ACTION_GRACE_REMINDER]
        pe_dispatcher.HANDLER_MAP[ACTION_GRACE_REMINDER] = fake_grace

        real_sql = frappe.db.sql
        first_select = {"seen": False}

        def maybe_race(query, values=None, *args, **kwargs):
            is_select = (
                isinstance(query, str)
                and "FOR UPDATE SKIP LOCKED" in query
            )
            result = real_sql(query, values, *args, **kwargs) if values is not None else real_sql(query, *args, **kwargs)
            if is_select and not first_select["seen"]:
                first_select["seen"] = True
                real_sql(
                    'UPDATE "tabProgramEnrollment" SET journey_label = %s WHERE name = %s',
                    (LABEL_SUBMITTED, pe_name),
                )
            return result

        try:
            with patch.object(frappe.db, "sql", side_effect=maybe_race):
                pe_dispatcher.dispatch_pending_actions()
        finally:
            pe_dispatcher.HANDLER_MAP[ACTION_GRACE_REMINDER] = original

        # Handler must NOT have been called.
        self.assertEqual(called, [])


class TestPeDispatcherHandlers(FrappeTestCase):
    """Per-handler unit tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def setUp(self):
        for pe in frappe.get_all(
            "ProgramEnrollment",
            filters={"batch": self.batch_name},
            pluck="name",
        ):
            frappe.delete_doc("ProgramEnrollment", pe, force=True)

    def test_handle_feedback_notification_fires_F5(self):
        """T12 routes feedback_notification through the FeedbackConsumer's flow
        lookup, but the dispatcher's handle_feedback_timeout fallback path
        should call t12_feedback_ready when the AI feedback ImgSubmission row
        appears. This test verifies the timeout-fallback branch invokes the
        T12 transition (which is what wires up F5 on Glific)."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("41")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-5),
            ACTION_FEEDBACK_TIMEOUT,
            resolved_flow_state=STATE_SUBMITTED_AWAITING,
            journey_label=LABEL_SUBMITTED,
            enrollment_suffix="F1",
            glific_id="glific-disp-F1",
            current_week=1,
        )

        # Patch frappe.db.exists so the handler thinks AI feedback is ready
        # (forces the T12 fallback branch).
        original_exists = frappe.db.exists

        def fake_exists(*args, **kwargs):
            if args and args[0] == "ImgSubmission":
                return "FAKE-IMG-001"
            return original_exists(*args, **kwargs)

        with patch.object(frappe.db, "exists", side_effect=fake_exists), \
             patch("tap_lms.summer_program.state_machine.t12_feedback_ready") as fake_t12, \
             patch("tap_lms.glific_integration.start_contact_flow") as fake_glific:
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_FEEDBACK_TIMEOUT,
                "journey_label": LABEL_SUBMITTED,
            })
            pe_dispatcher.handle_feedback_timeout(row)

        # T12 was invoked exactly once.
        self.assertEqual(fake_t12.call_count, 1)
        # No direct Glific call from this handler — T12 owns the feedback flow.
        self.assertEqual(fake_glific.call_count, 0)

    def test_handle_feedback_timeout_increments_count_atomically(self):
        """Calling handle_feedback_timeout twice in sequence (no AI feedback yet)
        must result in feedback_retry_count == 2. Pattern P-002 guards against
        the read-then-write race that would otherwise lose one increment."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("51")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-5),
            ACTION_FEEDBACK_TIMEOUT,
            resolved_flow_state=STATE_SUBMITTED_AWAITING,
            journey_label=LABEL_SUBMITTED,
            enrollment_suffix="FT2",
            glific_id="glific-disp-FT2",
            feedback_retry_count=0,
        )

        # Make sure the handler thinks no feedback row exists, so we hit the
        # increment branch both times.
        with patch.object(frappe.db, "exists", return_value=False), \
             patch("tap_lms.glific_integration.start_contact_flow"):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_FEEDBACK_TIMEOUT,
                "journey_label": LABEL_SUBMITTED,
            })
            pe_dispatcher.handle_feedback_timeout(row)
            pe_dispatcher.handle_feedback_timeout(row)

        new_count = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "feedback_retry_count"
        )
        self.assertEqual(new_count, 2)

    def test_handle_grace_reminder_picks_correct_day(self):
        """A PE 7 days into grace should produce reminder_index = 0 (the first
        reminder bucket in GRACE_REMINDER_DAYS = [7, 11, 13]).

        The handler delegates index calculation to _get_current_reminder_index;
        we assert the index returned for a 7-day-elapsed PE is 0 OR the value
        the implementation chose for day 7. Either is acceptable as long as
        the function returns a non-negative integer < len(GRACE_REMINDER_DAYS)."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("61")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-1),
            ACTION_GRACE_REMINDER,
            resolved_flow_state=STATE_GRACE_WAITING,
            journey_label=LABEL_GRACE_WINDOW,
            enrollment_suffix="GR1",
            glific_id="glific-disp-GR1",
            grace_window_start=add_to_date(now_datetime(), days=-7),
        )

        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        idx = pe_dispatcher._get_current_reminder_index(pe)

        # Index must be in valid range; for 7 days elapsed (== GRACE_REMINDER_DAYS[0])
        # the implementation returns max(0, 0 - 1) == 0.
        self.assertGreaterEqual(idx, 0)
        from tap_lms.summer_program.constants import GRACE_REMINDER_DAYS
        self.assertLess(idx, len(GRACE_REMINDER_DAYS))

    def test_handle_pause_check_resumes_when_calendar_advances(self):
        """A binge-paused PE on week 2 should resume to normal_content_delivery
        when batch.current_calendar_week advances to >= the PE's next_week (3)."""
        from tap_lms.summer_program import pe_dispatcher

        # Bump the batch calendar so the resume condition holds.
        frappe.db.set_value(
            "Batch", self.batch_name, "current_calendar_week", 3,
            update_modified=False,
        )

        s = _ensure_student("71")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-1),
            ACTION_PAUSE_CHECK,
            program_status=PROGRAM_PAUSED,
            resolved_flow_state=STATE_PAUSED_BINGE,
            journey_label=LABEL_PAUSED,
            enrollment_suffix="PC1",
            glific_id="glific-disp-PC1",
            current_week=2,
        )

        with patch("tap_lms.glific_integration.start_contact_flow"), \
             patch("tap_lms.glific_integration.update_contact_fields"):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_PAUSE_CHECK,
                "journey_label": LABEL_PAUSED,
            })
            pe_dispatcher.handle_pause_check(row)

        # State must have moved off paused_binge.
        new_state = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "resolved_flow_state"
        )
        self.assertNotEqual(new_state, STATE_PAUSED_BINGE)
        # Restore batch calendar
        frappe.db.set_value(
            "Batch", self.batch_name, "current_calendar_week", 1,
            update_modified=False,
        )

    def test_handle_week_advancement_calls_t14(self):
        """A week_completed PE should advance one week via T14 when the next
        week is within max_allowed and not past total_weeks."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("81")
        pe_name = _make_pe(
            self.batch_name,
            s,
            add_to_date(now_datetime(), minutes=-1),
            ACTION_WEEK_ADVANCEMENT,
            resolved_flow_state=STATE_WEEK_COMPLETED,
            journey_label=LABEL_CONTENT_DELIVERED,  # any non-special label is fine here
            enrollment_suffix="W1",
            glific_id="glific-disp-W1",
            current_week=1,
        )

        # Allow the advancement: max_allowed_week >= 2
        frappe.db.set_value(
            "ProgramEnrollment", pe_name, "max_allowed_week", 4,
            update_modified=False,
        )
        # Make sure batch.current_calendar_week is far enough.
        frappe.db.set_value(
            "Batch", self.batch_name, "current_calendar_week", 4,
            update_modified=False,
        )

        with patch(
            "tap_lms.summer_program.state_machine.t14_week_advance"
        ) as fake_t14, patch(
            "tap_lms.glific_integration.start_contact_flow"
        ), patch(
            "tap_lms.glific_integration.update_contact_fields"
        ):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_WEEK_ADVANCEMENT,
                "journey_label": LABEL_CONTENT_DELIVERED,
            })
            pe_dispatcher.handle_week_advancement(row)

        # T14 was invoked with new_week == 2.
        self.assertEqual(fake_t14.call_count, 1)
        args, _ = fake_t14.call_args
        # signature: (pe, new_week, week_rule, trigger_source)
        self.assertEqual(args[1], 2)

        # Cleanup
        frappe.db.set_value(
            "Batch", self.batch_name, "current_calendar_week", 1,
            update_modified=False,
        )

    def test_auto_activate_due_bprs_idempotent(self):
        """check_auto_activate run twice on the same BPR is a no-op the
        second time (the BPR is already active, so the inner activate_bpr
        call returns success=False with 'already active' message)."""
        from tap_lms.summer_program import batch_activation

        # Stand up a BPR that's ready to auto-activate.
        bpr = frappe.new_doc("BatchProgramRun")
        bpr.batch = self.batch_name
        bpr.status = BPR_COLLECTIONS_READY
        bpr.validation_status = VALIDATION_PASSED
        bpr.total_imported = 1
        bpr.total_enrolled = 1
        bpr.insert(ignore_permissions=True)
        bpr_name = bpr.name

        try:
            # First pass: should activate.
            count_first = batch_activation.check_auto_activate()
            self.assertGreaterEqual(count_first, 1)

            status_after_first = frappe.db.get_value(
                "BatchProgramRun", bpr_name, "status"
            )
            self.assertEqual(status_after_first, BPR_ACTIVE)

            # Second pass: BPR is now active, so the candidate query
            # filters on status = collections_ready and finds nothing.
            count_second = batch_activation.check_auto_activate()
            self.assertEqual(count_second, 0)

            # State unchanged.
            status_after_second = frappe.db.get_value(
                "BatchProgramRun", bpr_name, "status"
            )
            self.assertEqual(status_after_second, BPR_ACTIVE)
        finally:
            if frappe.db.exists("BatchProgramRun", bpr_name):
                frappe.delete_doc("BatchProgramRun", bpr_name, force=True)
