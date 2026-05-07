"""
Student Reactivation API
tap_lms/summer_program/reactivation.py

API A5: reactivate_student — resume a paused student.

Called by SP_Incoming_Router when a paused student sends any message.
The router reads @contact.program_status = 'paused' and calls this API.
"""
import frappe
from frappe import _

from tap_lms.summer_program.constants import (
    STATE_PAUSED_NO_ACTIVITY, STATE_PAUSED_BINGE,
    PAUSED_STATES, TERMINAL_STATES,
    PROGRAM_PAUSED, PATH_CORE, PATH_REMEDIAL,
)
from tap_lms.summer_program.state_machine import (
    get_active_pe,
    t19_reactivate_core,
    t20_reactivate_remedial,
    t21_binge_resume,
)
from tap_lms.summer_program.event_log import log_event


@frappe.whitelist(allow_guest=False)
def reactivate_student(student_id):
    """
    API A5: reactivate_student

    Resumes a paused student. Called by SP_Incoming_Router when
    a paused student sends any WhatsApp message.

    Logic:
      - paused_no_activity + Core path → T19 → normal_content_delivery
      - paused_no_activity + Remedial path → T20 → remedial_content_delivery
      - paused_binge → T21 → normal_content_delivery (if calendar allows)

    Args:
        student_id: Student name, glific_id, or phone

    Returns:
        dict with reactivation result, new state, current path
    """
    student_id = _resolve_student(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    pe = get_active_pe(student_id)
    if not pe:
        return {"success": False, "error": "No active ProgramEnrollment"}

    # Must be in a paused state
    if pe.program_status != PROGRAM_PAUSED:
        return {
            "success": False,
            "error": "Student is not paused",
            "program_status": pe.program_status,
            "resolved_flow_state": pe.resolved_flow_state,
        }

    if pe.resolved_flow_state in TERMINAL_STATES:
        return {
            "success": False,
            "error": "Student in terminal state",
            "resolved_flow_state": pe.resolved_flow_state,
        }

    # ── Handle paused_no_activity ───────────────────────────
    if pe.resolved_flow_state == STATE_PAUSED_NO_ACTIVITY:
        if pe.current_path == PATH_REMEDIAL:
            t20_reactivate_remedial(pe, "glific_flow")
        else:
            t19_reactivate_core(pe, "glific_flow")

        log_event(pe, "resume", trigger_source="glific_flow",
                  details={"reactivation_type": "message", "path": pe.current_path})

        frappe.db.commit()
        return {
            "success": True,
            "status": "reactivated",
            "resolved_flow_state": pe.resolved_flow_state,
            "current_path": pe.current_path,
            "current_week": pe.current_week,
            "pause_count": pe.pause_count,
        }

    # ── Handle paused_binge ─────────────────────────────────
    if pe.resolved_flow_state == STATE_PAUSED_BINGE:
        # Check if calendar now allows advancement
        batch = frappe.get_doc("Batch", pe.batch)
        max_allowed = (batch.current_calendar_week or 1) + 1
        next_week = (pe.current_week or 1) + 1

        if next_week <= max_allowed:
            t21_binge_resume(pe, "glific_flow")

            log_event(pe, "resume", trigger_source="glific_flow",
                      details={"reactivation_type": "binge_eligible"})

            frappe.db.commit()
            return {
                "success": True,
                "status": "reactivated",
                "resolved_flow_state": pe.resolved_flow_state,
                "current_week": pe.current_week,
            }
        else:
            # Still binge-limited — can't resume yet
            return {
                "success": True,
                "status": "still_paused",
                "reason": "binge_limit",
                "current_week": pe.current_week,
                "max_allowed_week": max_allowed,
                "resolved_flow_state": pe.resolved_flow_state,
            }

    return {
        "success": False,
        "error": "Unhandled pause state",
        "resolved_flow_state": pe.resolved_flow_state,
    }


def _resolve_student(identifier):
    """Delegate to shared utility."""
    from tap_lms.summer_program.utils import resolve_student
    return resolve_student(identifier)
