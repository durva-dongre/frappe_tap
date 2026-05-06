"""
ProgramEventLog Helper
tap_lms/summer_program/event_log.py

Creates ProgramEventLog records for audit trail.
Called by all state-changing operations.
"""
import frappe
import json
from frappe.utils import now_datetime


def log_event(
    enrollment,
    event_type,
    old_value=None,
    new_value=None,
    trigger_source="scheduler",
    details=None,
):
    """
    Create a ProgramEventLog entry.

    Args:
        enrollment: ProgramEnrollment doc or name
        event_type: one of the ProgramEventLog.event_type options
        old_value: previous state/value (optional)
        new_value: new state/value (optional)
        trigger_source: scheduler | glific_flow | flow_callback | admin | microservice
        details: dict of extra data (stored as JSON)
    """
    if isinstance(enrollment, str):
        enrollment = frappe.get_doc("ProgramEnrollment", enrollment)

    try:
        log = frappe.new_doc("ProgramEventLog")
        log.enrollment = enrollment.name
        log.student = enrollment.student
        log.batch = enrollment.batch
        log.program_type = enrollment.program_type
        log.week = enrollment.current_week or 0
        log.event_type = event_type
        log.old_value = str(old_value) if old_value else None
        log.new_value = str(new_value) if new_value else None
        log.trigger_source = trigger_source
        log.details = json.dumps(details) if details else None
        log.created_at = now_datetime()
        log.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(
            f"ProgramEventLog error: {str(e)}", "SP Event Log"
        )


def log_state_transition(enrollment, old_state, new_state, trigger_source="scheduler", details=None):
    """Convenience: log a resolved_flow_state transition."""
    log_event(
        enrollment,
        event_type="label_changed",
        old_value=old_state,
        new_value=new_state,
        trigger_source=trigger_source,
        details=details,
    )
