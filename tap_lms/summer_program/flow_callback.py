"""
Flow Callback — update_flow_status API
tap_lms/summer_program/flow_callback.py

THE critical callback that every Glific flow calls on completion.
This is the bridge between Glific and the backend state machine.

Called by:
  - SP_Content_Delivery (on timeout → no_response, on completion)
  - SP_Escalation (on completion)
  - SP_Feedback_Delivery (on completion → triggers week_completed → week_advancement)
  - SP_Grace_Entry / SP_Grace_Reminder (on completion)
  - SP_Paused_Reengagement (on completion)
  - SP_Paused_Binge (on completion)
  - SP_Week_Summary (on completion)
  - SP_Program_Complete (on completion)
  - SP_Submission (on completion)
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from tap_lms.summer_program.constants import (
    STATE_NORMAL_CONTENT, STATE_NORMAL_ESCALATION,
    STATE_REMEDIAL_CONTENT, STATE_REMEDIAL_ESCALATION,
    STATE_SUBMITTED_AWAITING, STATE_FEEDBACK_READY,
    STATE_GRACE_WAITING, STATE_WEEK_COMPLETED,
    STATE_PAUSED_NO_ACTIVITY, STATE_PAUSED_BINGE,
    PROGRAM_ACTIVE,
    ACTION_ESCALATION, ACTION_CONTENT_DELIVERY,
    TERMINAL_STATES,
)
from tap_lms.summer_program.state_machine import (
    get_active_pe,
    t1_content_no_response,
    t2_start_escalation,
    t13_feedback_delivered,
)
from tap_lms.summer_program.event_log import log_event


# ════════════════════════════════════════════════════════════
# RESPONSE HELPER — v3.0 contract
# ════════════════════════════════════════════════════════════
# Glific Integration Guide v3.0 §1.2: every webhook response from update_flow_status
# MUST return these four fields so Glific flows can read @results.webhook.* for
# immediate routing without waiting for the async contact-field sync.

def _response(pe, action, **extras):
    """Build a v3.0-compliant webhook response.

    Always emits: success, action, resolved_flow_state, next_action_type,
    next_action_at, program_status. Additional fields can be passed as **extras.
    """
    base = {
        "success": True,
        "action": action,
        "resolved_flow_state": pe.resolved_flow_state or "",
        "next_action_type": pe.next_action_type or "",
        "next_action_at": str(pe.next_action_at) if pe.next_action_at else "",
        "program_status": pe.program_status or "",
    }
    base.update(extras)
    return base


@frappe.whitelist(allow_guest=False)
def update_flow_status(student_id, flow_name, status, metadata=None):
    """
    API A4: update_flow_status

    Called by EVERY Glific flow on completion. This is how Glific tells the
    backend that a flow finished, and what the outcome was.

    Args:
        student_id: Student document name or glific_id
        flow_name: Name of the Glific flow (e.g., 'SP_Content_Delivery')
        status: Flow outcome — 'completed', 'no_response', 'timeout', 'error'
        metadata: Optional dict with extra data from the flow

    Returns:
        dict with result and any next action scheduled
    """
    student_id = _resolve_student(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    pe = get_active_pe(student_id)
    if not pe:
        return {"success": False, "error": "No active ProgramEnrollment"}

    # Track the flow delivery
    pe.last_flow_triggered = flow_name
    pe.last_flow_triggered_at = now_datetime()

    # Log the callback
    log_event(pe, "flow_completed", old_value=flow_name, new_value=status,
              trigger_source="flow_callback",
              details={"flow_name": flow_name, "status": status})

    # Route to the appropriate handler based on flow_name + status
    handler = _get_handler(flow_name, status)
    if handler:
        result = handler(pe, flow_name, status, metadata or {})
        frappe.db.commit()
        return result

    # Default: just acknowledge the callback
    pe.save(ignore_permissions=True)
    frappe.db.commit()

    return _response(pe, "acknowledged", flow_name=flow_name, status=status)


def _get_handler(flow_name, status):
    """Route to specific handler based on flow name and status."""
    handlers = {
        "SP_Content_Delivery": _handle_content_delivery,
        "SP_Escalation": _handle_escalation,
        "SP_Feedback_Delivery": _handle_feedback_delivery,
        "SP_Submission": _handle_submission_flow,
        "SP_Grace_Entry": _handle_grace_flow,
        "SP_Grace_Reminder": _handle_grace_flow,
        "SP_Paused_Reengagement": _handle_reengagement,
        "SP_Paused_Binge": _handle_binge_info,
        "SP_Week_Summary": _handle_info_flow,
        "SP_Program_Complete": _handle_info_flow,
    }
    return handlers.get(flow_name)


# ════════════════════════════════════════════════════════════
# FLOW-SPECIFIC HANDLERS
# ════════════════════════════════════════════════════════════

def _handle_content_delivery(pe, flow_name, status, metadata):
    """
    Handle SP_Content_Delivery completion.

    - no_response/timeout: student didn't engage → schedule first escalation
    - completed: student tapped button and flow ended normally
    """
    if status in ("no_response", "timeout"):
        # Student didn't respond within wait window → start escalation
        # Get first escalation step timing from ArchetypeConfig
        step = _get_first_escalation_step(pe)
        t1_content_no_response(pe, step, "flow_callback")
        return _response(pe, "escalation_scheduled")

    # completed — content was delivered, student tapped. Flow ended normally.
    # If submission happened within the flow, save_submission already handled state.
    # Just confirm delivery.
    pe.save(ignore_permissions=True)
    return _response(pe, "delivery_confirmed")


def _handle_escalation(pe, flow_name, status, metadata):
    """
    Handle SP_Escalation completion.

    - completed/timeout: escalation delivered, wait expired. No submission.
    - If submission happened during wait, save_submission already handled state.
    """
    # Escalation was delivered. If student hasn't submitted, the scheduler
    # will check next_action_at for the next escalation step.
    pe.save(ignore_permissions=True)

    log_event(pe, "escalation_sent", trigger_source="flow_callback",
              details={"step": pe.last_escalation_step})

    return _response(
        pe,
        "escalation_confirmed",
        last_escalation_step=pe.last_escalation_step,
    )


def _handle_feedback_delivery(pe, flow_name, status, metadata):
    """
    Handle SP_Feedback_Delivery completion.

    CRITICAL: This callback triggers week_completed → week_advancement.
    Without this callback, the student gets stuck in feedback_ready.
    """
    if pe.resolved_flow_state != STATE_FEEDBACK_READY:
        # State already moved (race condition or retry) — just acknowledge
        pe.save(ignore_permissions=True)
        return _response(pe, "already_advanced")

    # T13: feedback_ready → week_completed → schedule week_advancement
    t13_feedback_delivered(pe, "flow_callback")

    log_event(pe, "feedback_delivered", trigger_source="flow_callback")

    return _response(pe, "week_completed", current_week=pe.current_week)


def _handle_submission_flow(pe, flow_name, status, metadata):
    """
    Handle SP_Submission sub-flow completion.
    The actual submission was already recorded via save_submission API.
    This just confirms the flow ended.
    """
    pe.save(ignore_permissions=True)
    return _response(pe, "submission_flow_completed")


def _handle_grace_flow(pe, flow_name, status, metadata):
    """
    Handle SP_Grace_Entry / SP_Grace_Reminder completion.
    If student submitted during wait node, save_submission already cleared grace.
    """
    pe.save(ignore_permissions=True)
    return _response(
        pe,
        "grace_flow_completed",
        in_grace_window=pe.in_grace_window,
    )


def _handle_reengagement(pe, flow_name, status, metadata):
    """
    Handle SP_Paused_Reengagement completion.
    No state change — student must send a NEW message to reactivate.
    """
    pe.re_engagement_count = (pe.re_engagement_count or 0) + 1
    pe.save(ignore_permissions=True)

    log_event(pe, "re_engagement_attempt", trigger_source="flow_callback",
              details={"attempt": pe.re_engagement_count})

    return _response(
        pe,
        "reengagement_delivered",
        re_engagement_count=pe.re_engagement_count,
    )


def _handle_binge_info(pe, flow_name, status, metadata):
    """Handle SP_Paused_Binge completion. Informational only."""
    pe.save(ignore_permissions=True)
    return _response(pe, "binge_info_delivered")


def _handle_info_flow(pe, flow_name, status, metadata):
    """Handle informational flows (Week Summary, Program Complete)."""
    pe.save(ignore_permissions=True)
    return _response(pe, "info_delivered")


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _resolve_student(identifier):
    """Delegate to shared utility."""
    from tap_lms.summer_program.utils import resolve_student
    return resolve_student(identifier)


def _get_first_escalation_step(pe):
    """Get the first escalation step config for this student's archetype."""
    from tap_lms.summer_program.student_progression_sp import _get_escalation_steps
    student = frappe.get_doc("Student", pe.student)
    batch = frappe.get_doc("Batch", pe.batch)
    steps = _get_escalation_steps(student, batch)
    return steps[0] if steps else None
