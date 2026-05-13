"""
Tests for CR-003 handle_escalation channel branching.

Covers:
  - help_note_a step fires SP_Escalation Glific flow (no Vocallabs)
  - voice_note step fires SP_Escalation Glific flow
  - parent_call step enqueues Vocallabs job, SKIPS SP_Escalation
  - escalation_order + escalation_type pushed to Glific BEFORE flow trigger
  - Step exhaustion routes to T5 (grace, had activity) / T6 (remedial,
    no activity) / T11 (remedial path → grace)
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime
from unittest.mock import patch, MagicMock

from tap_lms.summer_program.constants import (
    ACTION_ESCALATION,
    LABEL_CONTENT_DELIVERED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    STATE_GRACE_WAITING,
    STATE_NORMAL_CONTENT,
    STATE_NORMAL_ESCALATION,
    STATE_REMEDIAL_CONTENT,
    CF_ESCALATION_ORDER,
    CF_ESCALATION_TYPE,
)


def _ensure_batch():
    name = frappe.get_value("Batch", {"name1": "EscBranchBatch"}, "name")
    if name:
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = "EscBranchBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = "EBR01"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = 14
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix):
    name = frappe.get_value("Student", {"phone": f"+9999800{suffix}"}, "name")
    if name:
        return name
    s = frappe.new_doc("Student")
    s.name1 = f"EscBranchStudent{suffix}"
    s.phone = f"+9999800{suffix}"
    s.glific_id = f"glific-eb-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(batch_name, student_name, suffix, **kwargs):
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-EB-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-eb-{suffix}"
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = kwargs.get("resolved_flow_state", STATE_NORMAL_CONTENT)
    pe.journey_label = kwargs.get("journey_label", LABEL_CONTENT_DELIVERED)
    pe.current_path = PATH_CORE
    pe.current_week = 1
    pe.current_tier = "Basic"
    pe.archetype = "Submitter"
    pe.last_escalation_step = kwargs.get("last_escalation_step", 0)
    pe.submission_count = kwargs.get("submission_count", 0)
    pe.insert(ignore_permissions=True)
    return pe.name


def _step(order, etype, hours=24):
    return {
        "escalation_order": order,
        "escalation_type": etype,
        "points_awarded": 0,
        "hours_after_previous": hours,
    }


def _patch_escalation_steps(steps):
    """Patch _get_escalation_steps_for_pe to return our fixture steps."""
    return patch(
        "tap_lms.summer_program.pe_dispatcher._get_escalation_steps_for_pe",
        return_value=steps,
    )


class TestEscalationBranching(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def test_help_note_a_step_fires_glific_flow(self):
        """escalation_type='help_note_a' → SP_Escalation flow triggered,
        no Vocallabs enqueue."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("01")
        pe_name = _make_pe(self.batch_name, s, "01", last_escalation_step=0)

        with _patch_escalation_steps([_step(1, "help_note_a")]), \
             patch.object(pe_dispatcher, "_get_flow_id", return_value="flow-esc"), \
             patch.object(pe_dispatcher, "_trigger_flow") as fake_trigger, \
             patch.object(pe_dispatcher, "_push_escalation_contact_fields"), \
             patch.object(frappe, "enqueue") as fake_enqueue, \
             patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_ESCALATION,
                "batch": self.batch_name,
                "journey_label": LABEL_CONTENT_DELIVERED,
            })
            pe_dispatcher.handle_escalation(row)

        # SP_Escalation flow was triggered.
        self.assertEqual(fake_trigger.call_count, 1)
        # No Vocallabs enqueue.
        vocallabs_calls = [
            c for c in fake_enqueue.call_args_list
            if "vocallabs" in str(c).lower()
        ]
        self.assertEqual(len(vocallabs_calls), 0)

    def test_voice_note_step_fires_glific_flow(self):
        """escalation_type='voice_note' → SP_Escalation flow triggered."""
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("02")
        pe_name = _make_pe(self.batch_name, s, "02", last_escalation_step=2)

        with _patch_escalation_steps([
            _step(1, "help_note_a"),
            _step(2, "help_note_b"),
            _step(3, "voice_note"),
        ]), \
             patch.object(pe_dispatcher, "_get_flow_id", return_value="flow-esc"), \
             patch.object(pe_dispatcher, "_trigger_flow") as fake_trigger, \
             patch.object(pe_dispatcher, "_push_escalation_contact_fields"), \
             patch.object(frappe, "enqueue") as fake_enqueue, \
             patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_ESCALATION,
                "batch": self.batch_name,
                "journey_label": LABEL_CONTENT_DELIVERED,
            })
            pe_dispatcher.handle_escalation(row)

        # Voice_note still uses the SP_Escalation flow (Glific branches
        # internally on the contact fields).
        self.assertEqual(fake_trigger.call_count, 1)
        # No Vocallabs enqueue.
        vocallabs_calls = [
            c for c in fake_enqueue.call_args_list
            if "vocallabs" in str(c).lower()
        ]
        self.assertEqual(len(vocallabs_calls), 0)

    def test_parent_call_step_enqueues_vocallabs_skips_glific(self):
        """escalation_type='parent_call' → vocallabs.initiate_parent_call
        is enqueued, SP_Escalation flow is NOT triggered.
        """
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("03")
        pe_name = _make_pe(self.batch_name, s, "03", last_escalation_step=3)

        with _patch_escalation_steps([
            _step(1, "help_note_a"),
            _step(2, "help_note_b"),
            _step(3, "voice_note"),
            _step(4, "parent_call"),
        ]), \
             patch.object(pe_dispatcher, "_get_flow_id", return_value="flow-esc"), \
             patch.object(pe_dispatcher, "_trigger_flow") as fake_trigger, \
             patch.object(pe_dispatcher, "_push_escalation_contact_fields"), \
             patch.object(frappe, "enqueue") as fake_enqueue, \
             patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_ESCALATION,
                "batch": self.batch_name,
                "journey_label": LABEL_CONTENT_DELIVERED,
            })
            pe_dispatcher.handle_escalation(row)

        # SP_Escalation flow NOT triggered for parent_call.
        self.assertEqual(fake_trigger.call_count, 0)
        # Vocallabs job WAS enqueued.
        vocallabs_calls = [
            c for c in fake_enqueue.call_args_list
            if c.args
            and c.args[0] == "tap_lms.summer_program.vocallabs.initiate_parent_call"
        ]
        self.assertEqual(len(vocallabs_calls), 1)
        # Carries pe_name + step.
        kwargs = vocallabs_calls[0].kwargs
        self.assertEqual(kwargs["pe_name"], pe_name)
        self.assertEqual(kwargs["escalation_step"]["escalation_type"], "parent_call")

    def test_handle_escalation_pushes_contact_fields_before_firing(self):
        """The 2 new contact fields (escalation_order, escalation_type) are
        pushed to Glific BEFORE the SP_Escalation flow trigger / Vocallabs
        enqueue.
        """
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("04")
        pe_name = _make_pe(self.batch_name, s, "04", last_escalation_step=0)

        ordering = []  # records "push" or "trigger" event labels

        def fake_push(glific_id, pe_n, student_id, escalation_order, escalation_type):
            ordering.append(("push", escalation_order, escalation_type))

        def fake_trigger(*args, **kwargs):
            ordering.append(("trigger",))

        with _patch_escalation_steps([_step(1, "help_note_a")]), \
             patch.object(pe_dispatcher, "_get_flow_id", return_value="flow-esc"), \
             patch.object(pe_dispatcher, "_trigger_flow", side_effect=fake_trigger), \
             patch.object(pe_dispatcher, "_push_escalation_contact_fields",
                          side_effect=fake_push), \
             patch.object(frappe, "enqueue"), \
             patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"):
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_ESCALATION,
                "batch": self.batch_name,
                "journey_label": LABEL_CONTENT_DELIVERED,
            })
            pe_dispatcher.handle_escalation(row)

        self.assertEqual(len(ordering), 2)
        # Push happens before trigger.
        self.assertEqual(ordering[0][0], "push")
        self.assertEqual(ordering[0][1], 1)
        self.assertEqual(ordering[0][2], "help_note_a")
        self.assertEqual(ordering[1][0], "trigger")

    def test_step_exhausted_routes_to_grace_with_activity(self):
        """When last_escalation_step >= len(steps) AND submission_count > 0,
        the handler routes to t5_escalation_to_grace.
        """
        from tap_lms.summer_program import pe_dispatcher

        s = _ensure_student("05")
        pe_name = _make_pe(
            self.batch_name, s, "05",
            resolved_flow_state=STATE_NORMAL_ESCALATION,
            last_escalation_step=2,
            submission_count=1,  # has activity
        )

        with _patch_escalation_steps([
            _step(1, "help_note_a"),
            _step(2, "help_note_b"),
        ]), \
             patch.object(pe_dispatcher, "_get_flow_id", return_value="flow-esc"), \
             patch.object(pe_dispatcher, "_trigger_flow"), \
             patch("tap_lms.summer_program.state_machine._enqueue_contact_field_sync"), \
             patch("tap_lms.summer_program.state_machine.t5_escalation_to_grace") as fake_t5, \
             patch("tap_lms.summer_program.state_machine.t6_escalation_to_remedial") as fake_t6:
            row = frappe._dict({
                "name": pe_name,
                "next_action_type": ACTION_ESCALATION,
                "batch": self.batch_name,
                "journey_label": LABEL_CONTENT_DELIVERED,
            })
            pe_dispatcher.handle_escalation(row)

        self.assertEqual(fake_t5.call_count, 1)
        self.assertEqual(fake_t6.call_count, 0)
