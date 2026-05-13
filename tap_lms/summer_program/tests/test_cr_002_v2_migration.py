"""
Tests for CR-002 v2 migration patch.

The patch backfills 9 new gamification fields on every existing PE:
  - total_submission_points  ← COALESCE(total_points, 0)
  - total_quiz_points        ← 0
  - total_activity_points    ← 0
  - weekly_quiz_points       ← 0
  - weekly_submission_points ← 0
  - weekly_activity_points   ← 0
  - special_gems             ← 0
  - weekly_submission_done   ← 0
  - weekly_video_done        ← 0

Idempotency: WHERE total_submission_points IS NULL guards re-runs.

Tests:
  1. test_migration_backfills_submission_points — fixture with total_points=50
     ends up with total_submission_points=50 and zeros elsewhere.
  2. test_migration_idempotent — second run is a no-op (no further writes).
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.patches.cr_002_v2 import gamification_fields
from tap_lms.summer_program.constants import (
    LABEL_CONTENT_DELIVERED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    STATE_NORMAL_CONTENT,
)


def _ensure_batch():
    name = frappe.get_value("Batch", {"name1": "MigTestBatch"}, "name")
    if name:
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = "MigTestBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = "MIG01"
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
    s.name1 = f"MigTestStudent{suffix}"
    s.phone = f"+9999400{suffix}"
    s.glific_id = f"glific-mig-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(batch_name, student_name, suffix, total_points):
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-MIG-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-mig-{suffix}"
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = STATE_NORMAL_CONTENT
    pe.journey_label = LABEL_CONTENT_DELIVERED
    pe.current_path = PATH_CORE
    pe.current_week = 1
    pe.total_points = total_points
    pe.insert(ignore_permissions=True)

    # Force the 9 new fields to NULL so the WHERE clause picks the row.
    # (frappe.new_doc defaults populate with 0, but we want to simulate
    # the pre-migration state where the column was freshly added.)
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET total_submission_points  = NULL,
               total_quiz_points        = NULL,
               total_activity_points    = NULL,
               weekly_quiz_points       = NULL,
               weekly_submission_points = NULL,
               weekly_activity_points   = NULL,
               special_gems             = NULL,
               weekly_submission_done   = NULL,
               weekly_video_done        = NULL
         WHERE name = %s
        """,
        (pe.name,),
    )
    return pe.name


class TestCr002V2Migration(FrappeTestCase):
    """CR-002 v2 §Migration — gamification_fields patch coverage."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def test_migration_backfills_submission_points(self):
        """A PE with total_points=50 gets total_submission_points=50 after
        the patch runs. Other 8 new fields are zeroed."""
        student = _ensure_student("01")
        pe_name = _make_pe(self.batch_name, student, "01", total_points=50)

        gamification_fields.execute()

        row = frappe.db.sql(
            """
            SELECT total_submission_points, total_quiz_points,
                   total_activity_points, weekly_quiz_points,
                   weekly_submission_points, weekly_activity_points,
                   special_gems, weekly_submission_done, weekly_video_done,
                   total_points
              FROM "tabProgramEnrollment"
             WHERE name = %s
            """,
            (pe_name,),
            as_dict=True,
        )[0]

        self.assertEqual(row["total_submission_points"], 50,
                         "total_submission_points = old total_points (50)")
        self.assertEqual(row["total_quiz_points"], 0)
        self.assertEqual(row["total_activity_points"], 0)
        self.assertEqual(row["weekly_quiz_points"], 0)
        self.assertEqual(row["weekly_submission_points"], 0)
        self.assertEqual(row["weekly_activity_points"], 0)
        self.assertEqual(row["special_gems"], 0)
        self.assertEqual(row["weekly_submission_done"], 0)
        self.assertEqual(row["weekly_video_done"], 0)
        # total_points itself stays unchanged
        self.assertEqual(row["total_points"], 50)

    def test_migration_idempotent(self):
        """Second run finds 0 rows matching WHERE total_submission_points IS NULL
        and is a no-op. We verify by mutating total_submission_points after
        the first run and observing the second run does NOT overwrite it."""
        student = _ensure_student("02")
        pe_name = _make_pe(self.batch_name, student, "02", total_points=100)

        # First run: backfills.
        gamification_fields.execute()
        self.assertEqual(
            frappe.db.get_value("ProgramEnrollment", pe_name, "total_submission_points"),
            100,
        )

        # Simulate post-migration runtime activity: a submission lands and bumps
        # total_submission_points to 125.
        frappe.db.sql(
            """
            UPDATE "tabProgramEnrollment"
               SET total_submission_points = 125
             WHERE name = %s
            """,
            (pe_name,),
        )

        # Second run of the patch.
        gamification_fields.execute()

        # Total_submission_points stays at 125 — the WHERE IS NULL guard
        # skips already-migrated rows.
        self.assertEqual(
            frappe.db.get_value("ProgramEnrollment", pe_name, "total_submission_points"),
            125,
            "Idempotent patch must NOT overwrite post-migration runtime data",
        )
