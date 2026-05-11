"""
FeedbackConsumer → Summer Program Hook
tap_lms/summer_program/feedback_consumer_hook.py

This module provides the hook that FeedbackConsumer calls after processing
AI feedback from RabbitMQ. It bridges the existing feedback pipeline into
the SP state machine without duplicating Glific notification logic.

── Integration Point ──────────────────────────────────────────────
Add this call in FeedbackConsumer.process_message() AFTER update_submission()
and send_glific_notification() succeed:

    from tap_lms.summer_program.feedback_consumer_hook import on_feedback_ready
    on_feedback_ready(submission_name, student_id)

── What This Replaces ─────────────────────────────────────────────
Previously, pe_dispatcher.py had a `handle_feedback_notification` handler that:
  1. Checked PE state == feedback_ready
  2. Triggered SP_Feedback_Delivery Glific flow
  3. Cleared next_action

That was redundant because FeedbackConsumer ALREADY sends the feedback to the
student via Glific (start_contact_flow with label="feedback"). We only need the
state machine transition (T12 → feedback_ready), which unlocks week advancement.

── Safety Net ─────────────────────────────────────────────────────
If this hook fails or FeedbackConsumer crashes before calling it,
pe_dispatcher's `handle_feedback_timeout` acts as a fallback: it polls
Submission.status every hour and triggers T12 if feedback arrived but
the state wasn't updated.
"""
import frappe


def on_feedback_ready(submission_name, student_id=None):
    """
    Called by FeedbackConsumer after AI feedback is saved to Submission
    and the Glific notification is sent.

    Triggers T12 (feedback_ready) on the student's active ProgramEnrollment
    if they're in the 'submitted_awaiting_feedback' state.

    Args:
        submission_name: Submission document name (e.g., "SUB-00123")
        student_id: Student document name (optional — resolved from submission if not provided)

    Returns:
        dict with status ("transitioned", "skipped", "no_pe", or "error")
    """
    from tap_lms.summer_program.state_machine import t12_feedback_ready
    from tap_lms.summer_program.constants import STATE_SUBMITTED_AWAITING

    try:
        # Resolve student from submission if not provided
        if not student_id:
            student_id = frappe.db.get_value("Submission", submission_name, "student_id")

        if not student_id:
            return {"status": "error", "message": f"No student found for submission {submission_name}"}

        # Find the active SP enrollment for this student
        pe_name = frappe.db.get_value(
            "ProgramEnrollment",
            {
                "student": student_id,
                "program_status": "active",
                "resolved_flow_state": STATE_SUBMITTED_AWAITING,
            },
            "name",
        )

        if not pe_name:
            # Student isn't in SP or isn't awaiting feedback — skip silently
            return {"status": "no_pe"}

        pe = frappe.get_doc("ProgramEnrollment", pe_name)

        # Double-check: is this submission for the PE's current week?
        sub_week = frappe.db.get_value("Submission", submission_name, "week")
        if sub_week and pe.current_week and int(sub_week) != int(pe.current_week):
            # Feedback for a different week — don't transition
            return {"status": "skipped", "reason": "week_mismatch",
                    "sub_week": sub_week, "pe_week": pe.current_week}

        # Transition: submitted_awaiting_feedback → feedback_ready
        # NOTE: Do NOT commit here — let the caller (FeedbackConsumer.process_message)
        # handle the commit so that submission update + state transition are atomic.
        t12_feedback_ready(pe, trigger_source="feedback_consumer")

        return {"status": "transitioned", "pe": pe_name}

    except Exception as e:
        frappe.log_error(
            f"SP feedback hook failed: submission={submission_name}, "
            f"student={student_id}, error={str(e)}",
            "SP Feedback Consumer Hook",
        )
        return {"status": "error", "message": str(e)}
