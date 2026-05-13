"""
Tests for CR-003 ArchetypeConfig escalation-hours validation
(summer_program/validators.py).

The helper hard-fails when sum(EscalationStep.hours_after_previous) exceeds
batch.grace_window_days * 24 for any archetype.
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.summer_program.validators import validate_escalation_hours_fit_grace


def _ensure_batch(name, grace_days):
    existing = frappe.get_value("Batch", {"name1": name}, "name")
    if existing:
        frappe.db.set_value("Batch", existing, "grace_window_days", grace_days,
                            update_modified=False)
        return existing
    batch = frappe.new_doc("Batch")
    batch.name1 = name
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = name[:6].upper()
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = grace_days
    batch.insert(ignore_permissions=True)
    return batch.name


def _make_ac(batch_name, hours_list):
    """Create an ArchetypeConfig with escalation_steps using the given
    hours_after_previous values."""
    ac = frappe.new_doc("ArchetypeConfig")
    ac.batch = batch_name
    ac.experiment_arm = "default"
    ac.archetype = "Submitter"
    ac.path = "Core"
    ac.is_active = 1
    for i, hours in enumerate(hours_list, start=1):
        ac.append("escalation_steps", {
            "escalation_order": i,
            "escalation_type": "help_note_a",
            "hours_after_previous": hours,
            "is_active": 1,
        })
    ac.insert(ignore_permissions=True)
    return ac.name


class TestArchetypeConfigEscalationValidator(FrappeTestCase):
    def test_passes_within_grace_window(self):
        """Sum of hours = 3 × 24 = 72h; grace = 14d = 336h → ok."""
        batch_name = _ensure_batch("ValidatorOkBatch", grace_days=14)
        ac_name = _make_ac(batch_name, [24, 24, 24])

        ok, err = validate_escalation_hours_fit_grace(ac_name)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_fails_exceeding_grace_window(self):
        """Sum of hours = 100 + 100 + 200 = 400h > 14d (336h) → fail."""
        batch_name = _ensure_batch("ValidatorOver", grace_days=14)
        ac_name = _make_ac(batch_name, [100, 100, 200])

        ok, err = validate_escalation_hours_fit_grace(ac_name)
        self.assertFalse(ok)
        self.assertIsNotNone(err)
        self.assertIn("400h", err)
        self.assertIn("336h", err)

    def test_no_steps_is_valid(self):
        """An archetype with no escalation steps is acceptable — no nudges."""
        batch_name = _ensure_batch("ValidatorEmpty", grace_days=14)
        ac_name = _make_ac(batch_name, [])
        ok, err = validate_escalation_hours_fit_grace(ac_name)
        self.assertTrue(ok)
        self.assertIsNone(err)
