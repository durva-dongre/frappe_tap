"""
Tests for CR-003 migration patch (patches/cr_003/grace_and_reengagement.py).

The patch performs three operations (Step 3 is intentionally a no-op):
  1. Migrate PEs in paused_no_activity → program_dropped with drop_reason.
  2. Null next_action_at + next_action_type for retired action types
     (grace_reminder, re_engagement).
  3. Skip grace_window_end_at backfill (intentional — see patch docstring).

Idempotency: re-running finds no rows matching the WHERE and is a no-op
(L-021 / P-004).
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.patches.cr_003 import grace_and_reengagement
from tap_lms.summer_program.constants import (
    LABEL_CONTENT_DELIVERED,
    LABEL_PAUSED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    PROGRAM_PAUSED,
    STATE_NORMAL_CONTENT,
)


def _ensure_batch():
    name = frappe.get_value("Batch", {"name1": "Cr3MigBatch"}, "name")
    if name:
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = "Cr3MigBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = "CR3M01"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = 14
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix):
    name = frappe.get_value("Student", {"phone": f"+9999600{suffix}"}, "name")
    if name:
        return name
    s = frappe.new_doc("Student")
    s.name1 = f"Cr3MigStudent{suffix}"
    s.phone = f"+9999600{suffix}"
    s.glific_id = f"glific-cr3m-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(batch_name, student_name, suffix, *,
             resolved_flow_state=STATE_NORMAL_CONTENT,
             program_status=PROGRAM_ACTIVE,
             journey_label=LABEL_CONTENT_DELIVERED,
             next_action_type="",
             re_engagement_count=0):
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-CR3M-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-cr3m-{suffix}"
    pe.program_status = program_status
    pe.resolved_flow_state = resolved_flow_state
    pe.journey_label = journey_label
    pe.current_path = PATH_CORE
    pe.current_week = 1
    pe.next_action_type = next_action_type
    pe.insert(ignore_permissions=True)

    # Force the legacy field directly — the canonical PE controller may
    # clamp values otherwise.
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET re_engagement_count = %s
         WHERE name = %s
        """,
        (re_engagement_count, pe.name),
    )
    return pe.name


class TestCr003Migration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def test_paused_no_activity_migrated_to_dropped(self):
        """A PE in resolved_flow_state='paused_no_activity' lands in
        program_dropped with drop_reason='grace_expired' (or
        'reengagement_exhausted' if re_engagement_count>=3)."""
        s1 = _ensure_student("01")
        pe1 = _make_pe(
            self.batch_name, s1, "01",
            resolved_flow_state="paused_no_activity",
            program_status=PROGRAM_PAUSED,
            journey_label=LABEL_PAUSED,
            re_engagement_count=0,
        )
        s2 = _ensure_student("02")
        pe2 = _make_pe(
            self.batch_name, s2, "02",
            resolved_flow_state="paused_no_activity",
            program_status=PROGRAM_PAUSED,
            journey_label=LABEL_PAUSED,
            re_engagement_count=3,
        )

        grace_and_reengagement.execute()

        row1 = frappe.db.get_value(
            "ProgramEnrollment", pe1,
            ["resolved_flow_state", "program_status", "drop_reason", "journey_label"],
            as_dict=True,
        )
        self.assertEqual(row1["resolved_flow_state"], "program_dropped")
        self.assertEqual(row1["program_status"], "dropped")
        self.assertEqual(row1["drop_reason"], "grace_expired")
        self.assertEqual(row1["journey_label"], "dropped")

        row2 = frappe.db.get_value(
            "ProgramEnrollment", pe2,
            ["resolved_flow_state", "drop_reason"],
            as_dict=True,
        )
        self.assertEqual(row2["resolved_flow_state"], "program_dropped")
        self.assertEqual(row2["drop_reason"], "reengagement_exhausted")

    def test_retired_action_types_nulled(self):
        """PEs with next_action_type IN ('grace_reminder', 're_engagement')
        get those fields cleared so the dispatcher's 'Unknown action_type'
        branch never sees them post-migration."""
        s1 = _ensure_student("11")
        pe_gr = _make_pe(
            self.batch_name, s1, "11",
            next_action_type="grace_reminder",
        )
        s2 = _ensure_student("12")
        pe_re = _make_pe(
            self.batch_name, s2, "12",
            next_action_type="re_engagement",
        )

        # Sanity check setup actually set the values.
        self.assertEqual(
            frappe.db.get_value("ProgramEnrollment", pe_gr, "next_action_type"),
            "grace_reminder",
        )

        grace_and_reengagement.execute()

        for pe_name in (pe_gr, pe_re):
            self.assertIn(
                frappe.db.get_value("ProgramEnrollment", pe_name, "next_action_type") or "",
                ("", None),
                f"next_action_type should be cleared for {pe_name}",
            )

    def test_migration_idempotent(self):
        """Second run is a no-op — no further state changes, and the patch
        does not double-write program_dropped event logs.
        """
        s = _ensure_student("21")
        pe_name = _make_pe(
            self.batch_name, s, "21",
            resolved_flow_state="paused_no_activity",
            program_status=PROGRAM_PAUSED,
            journey_label=LABEL_PAUSED,
            re_engagement_count=0,
        )

        # First run: migrates.
        grace_and_reengagement.execute()
        state_after_first = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "resolved_flow_state",
        )
        self.assertEqual(state_after_first, "program_dropped")

        # Count event-log entries between runs. Field name is `enrollment`
        # per programeventlog.json — earlier `program_enrollment` filter was
        # a no-op (see code review B3) and the test passed trivially.
        events_before = frappe.db.count(
            "ProgramEventLog",
            {"enrollment": pe_name, "event_type": "program_dropped"},
        )

        # Validate the first run actually wrote an event — otherwise the
        # idempotency check below is meaningless (0 == 0 is trivially true).
        self.assertGreaterEqual(
            events_before, 1,
            "First migration run must produce at least one ProgramEventLog "
            "entry per migrated PE (otherwise the audit trail is broken — B1)",
        )

        # Second run: should be a no-op (PE is no longer in paused_no_activity).
        grace_and_reengagement.execute()

        # State unchanged.
        state_after_second = frappe.db.get_value(
            "ProgramEnrollment", pe_name, "resolved_flow_state",
        )
        self.assertEqual(state_after_second, "program_dropped")

        # No new event log row.
        events_after = frappe.db.count(
            "ProgramEventLog",
            {"enrollment": pe_name, "event_type": "program_dropped"},
        )
        self.assertEqual(
            events_after, events_before,
            "Idempotent patch must NOT double-write event log entries",
        )
