"""
State Machine — Resolved Flow State Transitions
tap_lms/summer_program/state_machine.py

Implements all 25 transitions (T0–T25) on ProgramEnrollment.resolved_flow_state.
Each transition:
  1. Validates the current state is allowed
  2. Updates PE fields (resolved_flow_state, journey_label, next_action_at/type, etc.)
  3. Updates Glific contact fields
  4. Logs to ProgramEventLog

Called by: update_flow_status, save_submission, reactivate_student, scheduler actions.
"""
import frappe
from frappe.utils import now_datetime, add_to_date, getdate

from tap_lms.glific_integration import update_contact_fields
from tap_lms.summer_program.constants import (
    STATE_NORMAL_CONTENT, STATE_NORMAL_ESCALATION,
    STATE_REMEDIAL_CONTENT, STATE_REMEDIAL_ESCALATION,
    STATE_GRACE_WAITING, STATE_PAUSED_NO_ACTIVITY, STATE_PAUSED_BINGE,
    STATE_SUBMITTED_AWAITING, STATE_FEEDBACK_READY,
    STATE_WEEK_COMPLETED, STATE_PROGRAM_COMPLETED, STATE_PROGRAM_DROPPED,
    PAUSED_STATES, TERMINAL_STATES,
    LABEL_CONTENT_DELIVERED, LABEL_SUBMITTED, LABEL_FEEDBACK_DELIVERED,
    LABEL_GRACE_WINDOW, LABEL_PAUSED, LABEL_RESUMED,
    LABEL_COMPLETED, LABEL_DROPPED, LABEL_WEEK_ADVANCED,
    PROGRAM_ACTIVE, PROGRAM_PAUSED, PROGRAM_COMPLETED, PROGRAM_DROPPED,
    PATH_CORE, PATH_REMEDIAL,
    ACTION_ESCALATION, ACTION_CONTENT_DELIVERY, ACTION_FEEDBACK_NOTIFICATION,
    ACTION_FEEDBACK_TIMEOUT, ACTION_WEEK_ADVANCEMENT,
    ACTION_GRACE_REMINDER, ACTION_GRACE_CHECK, ACTION_RE_ENGAGEMENT,
    ACTION_PAUSE_CHECK,
    PAUSE_NO_ACTIVITY, PAUSE_BINGE_LIMIT,
    GRACE_WINDOW_DAYS, GRACE_REMINDER_DAYS,
    FEEDBACK_TIMEOUT_HOURS,
    CF_RESOLVED_FLOW_STATE, CF_CURRENT_WEEK, CF_CURRENT_PATH,
    CF_CURRENT_TIER, CF_PROGRAM_STATUS, CF_TOTAL_POINTS,
    CF_CURRENT_STREAK, CF_GRACE_WINDOW_END, CF_EXPECTED_SUBMISSION,
    TIER_BY_WEEK, DEFAULT_TIER,
)
from tap_lms.summer_program.event_log import log_event, log_state_transition


# ════════════════════════════════════════════════════════════
# CORE TRANSITION ENGINE
# ════════════════════════════════════════════════════════════

def transition(pe, new_state, trigger_source="scheduler", extra_updates=None, skip_glific=False):
    """
    Execute a state transition on a ProgramEnrollment.

    Args:
        pe: ProgramEnrollment doc (must be loaded, not just name)
        new_state: target resolved_flow_state
        trigger_source: who triggered this
        extra_updates: dict of additional PE field updates
        skip_glific: if True, skip Glific contact field update (for batch operations)

    Returns:
        True if transition was applied
    """
    old_state = pe.resolved_flow_state

    # Apply state change
    pe.resolved_flow_state = new_state
    pe.last_label_change_at = now_datetime()

    # Apply extra updates
    if extra_updates:
        for field, value in extra_updates.items():
            setattr(pe, field, value)

    pe.save(ignore_permissions=True)

    # Log the transition
    log_state_transition(pe, old_state, new_state, trigger_source)

    # Update Glific contact fields (async — runs in background worker)
    if not skip_glific and pe.glific_id:
        _enqueue_contact_field_sync(pe)

    return True


def _enqueue_contact_field_sync(pe):
    """
    Enqueue Glific contact field sync as a background job.

    Serializes the PE fields into a plain dict so the background worker
    doesn't need to reload the doc. This keeps the API response fast
    (~50ms) while Glific sync happens in the background (~200-500ms).
    """
    fields = {
        CF_RESOLVED_FLOW_STATE: pe.resolved_flow_state or "",
        CF_CURRENT_WEEK: str(pe.current_week or 0),
        CF_CURRENT_PATH: pe.current_path or "",
        CF_CURRENT_TIER: pe.current_tier or "",
        CF_PROGRAM_STATUS: pe.program_status or "",
        CF_TOTAL_POINTS: str(pe.total_points or 0),
        CF_CURRENT_STREAK: str(pe.current_streak or 0),
        CF_GRACE_WINDOW_END: str(pe.grace_window_end_at) if pe.grace_window_end_at else "",
        CF_EXPECTED_SUBMISSION: pe.current_expected_submission_type or "",
    }
    frappe.enqueue(
        "tap_lms.summer_program.state_machine._sync_contact_fields_job",
        queue="short",
        timeout=30,
        enqueue_after_commit=True,
        glific_id=str(pe.glific_id),
        fields=fields,
        pe_name=pe.name,
    )


def _sync_contact_fields_job(glific_id, fields, pe_name):
    """
    Background job: push PE state to Glific contact fields.

    Called via frappe.enqueue from _enqueue_contact_field_sync.
    Uses the single-call update_contact_fields mutation.
    """
    try:
        update_contact_fields(glific_id, fields)
    except Exception as e:
        frappe.log_error(
            f"Glific sync error for PE {pe_name}: {str(e)}",
            "SP State Machine Glific Sync",
        )


# ════════════════════════════════════════════════════════════
# NAMED TRANSITIONS (T0–T25)
# ════════════════════════════════════════════════════════════

# ── T0: Enrollment → normal_content_delivery ───────────────
def t0_enrollment(pe, trigger_source="scheduler"):
    """T0: Initial enrollment. Sets resolved_flow_state = normal_content_delivery."""
    return transition(pe, STATE_NORMAL_CONTENT, trigger_source, {
        "journey_label": LABEL_CONTENT_DELIVERED,
        "program_status": PROGRAM_ACTIVE,
        "current_path": PATH_CORE,
        "current_week": 1,
    })


# ── T1: Content delivered, no response → stays, schedule escalation ──
def t1_content_no_response(pe, escalation_step, trigger_source="flow_callback"):
    """
    T1: Content delivered but student didn't respond within wait window.
    State stays normal_content_delivery but schedule escalation.
    """
    hours = escalation_step.get("hours_after_previous", 24) if escalation_step else 24
    return transition(pe, STATE_NORMAL_CONTENT, trigger_source, {
        "next_action_at": add_to_date(now_datetime(), hours=hours),
        "next_action_type": ACTION_ESCALATION,
    })


# ── T2: Start escalation (Core) ───────────────────────────
def t2_start_escalation(pe, step_number=1, trigger_source="scheduler"):
    """T2: normal_content_delivery → normal_escalation."""
    return transition(pe, STATE_NORMAL_ESCALATION, trigger_source, {
        "last_escalation_step": step_number,
        "journey_label": LABEL_CONTENT_DELIVERED,
    })


# ── T3: Submission during escalation ──────────────────────
def t3_escalation_submission(pe, points=0, trigger_source="flow_callback"):
    """T3: normal_escalation → submitted_awaiting_feedback."""
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        "next_action_at": add_to_date(now_datetime(), hours=FEEDBACK_TIMEOUT_HOURS),
        "next_action_type": ACTION_FEEDBACK_TIMEOUT,
    })


# ── T4: Next escalation step ─────────────────────────────
def t4_next_escalation_step(pe, step_number, next_hours=24, trigger_source="scheduler"):
    """T4: normal_escalation → normal_escalation (next step)."""
    return transition(pe, STATE_NORMAL_ESCALATION, trigger_source, {
        "last_escalation_step": step_number,
        "next_action_at": add_to_date(now_datetime(), hours=next_hours),
        "next_action_type": ACTION_ESCALATION,
    })


# ── T5: Escalation exhausted + some activity → grace ─────
def t5_escalation_to_grace(pe, trigger_source="scheduler"):
    """T5: normal_escalation → grace_waiting (had some activity)."""
    grace_end = add_to_date(now_datetime(), days=GRACE_WINDOW_DAYS)
    first_reminder = add_to_date(now_datetime(), days=GRACE_REMINDER_DAYS[0])
    return transition(pe, STATE_GRACE_WAITING, trigger_source, {
        "journey_label": LABEL_GRACE_WINDOW,
        "in_grace_window": 1,
        "grace_window_start": now_datetime(),
        "grace_window_end_at": grace_end,
        "next_action_at": first_reminder,
        "next_action_type": ACTION_GRACE_REMINDER,
    })


# ── T6: Escalation exhausted + ZERO activity → remedial ──
def t6_escalation_to_remedial(pe, week_rule=None, trigger_source="scheduler"):
    """T6: normal_escalation → remedial_content_delivery."""
    updates = {
        "journey_label": LABEL_CONTENT_DELIVERED,
        "current_path": PATH_REMEDIAL,
        "last_escalation_step": 0,
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_CONTENT_DELIVERY,
    }
    if week_rule:
        updates["current_expected_submission_type"] = week_rule.get("expected_submission_type", "")

    log_event(pe, "path_changed", PATH_CORE, PATH_REMEDIAL, trigger_source)

    return transition(pe, STATE_REMEDIAL_CONTENT, trigger_source, updates)


# ── T7: First submission (Core, from content delivery) ────
def t7_core_submission(pe, points=0, trigger_source="flow_callback"):
    """T7: normal_content_delivery → submitted_awaiting_feedback."""
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        "next_action_at": add_to_date(now_datetime(), hours=FEEDBACK_TIMEOUT_HOURS),
        "next_action_type": ACTION_FEEDBACK_TIMEOUT,
    })


# ── T8: Start Remedial escalation ────────────────────────
def t8_start_remedial_escalation(pe, step_number=1, trigger_source="scheduler"):
    """T8: remedial_content_delivery → remedial_escalation."""
    return transition(pe, STATE_REMEDIAL_ESCALATION, trigger_source, {
        "last_escalation_step": step_number,
    })


# ── T9: Remedial submission ──────────────────────────────
def t9_remedial_submission(pe, points=0, trigger_source="flow_callback"):
    """T9: remedial_content_delivery → submitted_awaiting_feedback."""
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        "next_action_at": add_to_date(now_datetime(), hours=FEEDBACK_TIMEOUT_HOURS),
        "next_action_type": ACTION_FEEDBACK_TIMEOUT,
    })


# ── T10: Next Remedial escalation step ───────────────────
def t10_next_remedial_escalation(pe, step_number, next_hours=24, trigger_source="scheduler"):
    """T10: remedial_escalation → remedial_escalation (next step)."""
    return transition(pe, STATE_REMEDIAL_ESCALATION, trigger_source, {
        "last_escalation_step": step_number,
        "next_action_at": add_to_date(now_datetime(), hours=next_hours),
        "next_action_type": ACTION_ESCALATION,
    })


# ── T11: All Remedial escalation exhausted → grace ──────
def t11_remedial_to_grace(pe, trigger_source="scheduler"):
    """T11: remedial_escalation → grace_waiting."""
    grace_end = add_to_date(now_datetime(), days=GRACE_WINDOW_DAYS)
    first_reminder = add_to_date(now_datetime(), days=GRACE_REMINDER_DAYS[0])
    return transition(pe, STATE_GRACE_WAITING, trigger_source, {
        "journey_label": LABEL_GRACE_WINDOW,
        "in_grace_window": 1,
        "grace_window_start": now_datetime(),
        "grace_window_end_at": grace_end,
        "next_action_at": first_reminder,
        "next_action_type": ACTION_GRACE_REMINDER,
    })


# ── T12: AI feedback generated ──────────────────────────
def t12_feedback_ready(pe, trigger_source="microservice"):
    """T12: submitted_awaiting_feedback → feedback_ready."""
    return transition(pe, STATE_FEEDBACK_READY, trigger_source, {
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_FEEDBACK_NOTIFICATION,
    })


# ── T13: Feedback delivered → week_completed ─────────────
def t13_feedback_delivered(pe, trigger_source="flow_callback"):
    """T13: feedback_ready → week_completed."""
    return transition(pe, STATE_WEEK_COMPLETED, trigger_source, {
        "journey_label": LABEL_FEEDBACK_DELIVERED,
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_WEEK_ADVANCEMENT,
    })


# ── T14: Week advance (normal) ──────────────────────────
def t14_week_advance(pe, new_week, week_rule=None, trigger_source="scheduler"):
    """T14: week_completed → normal_content_delivery (next week)."""
    tier = TIER_BY_WEEK.get(new_week, DEFAULT_TIER)
    updates = {
        "journey_label": LABEL_WEEK_ADVANCED,
        "current_week": new_week,
        "current_path": PATH_CORE,
        "current_tier": tier,
        "submission_count": 0,
        "quiz_completed": 0,
        "last_escalation_step": 0,
        "in_grace_window": 0,
        "grace_window_start": None,
        "grace_window_end_at": None,
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_CONTENT_DELIVERY,
    }
    if week_rule:
        updates["current_expected_submission_type"] = week_rule.get("expected_submission_type", "")

    log_event(pe, "week_advanced", str(pe.current_week), str(new_week), trigger_source)

    return transition(pe, STATE_NORMAL_CONTENT, trigger_source, updates)


# ── T15: Binge limit hit ────────────────────────────────
def t15_binge_pause(pe, next_open_date=None, trigger_source="scheduler"):
    """T15: week_completed → paused_binge."""
    return transition(pe, STATE_PAUSED_BINGE, trigger_source, {
        "journey_label": LABEL_PAUSED,
        "program_status": PROGRAM_PAUSED,
        "pause_reason": PAUSE_BINGE_LIMIT,
        "next_action_at": next_open_date,
        "next_action_type": ACTION_PAUSE_CHECK,
    })


# ── T16: Program completed ──────────────────────────────
def t16_program_completed(pe, trigger_source="scheduler"):
    """T16: week_completed → program_completed."""
    return transition(pe, STATE_PROGRAM_COMPLETED, trigger_source, {
        "journey_label": LABEL_COMPLETED,
        "program_status": PROGRAM_COMPLETED,
        "next_action_at": None,
        "next_action_type": "",
    })


# ── T17: Grace submission ───────────────────────────────
def t17_grace_submission(pe, points=0, trigger_source="flow_callback"):
    """T17: grace_waiting → submitted_awaiting_feedback."""
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "in_grace_window": 0,
        "grace_window_start": None,
        "grace_window_end_at": None,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        "next_action_at": add_to_date(now_datetime(), hours=FEEDBACK_TIMEOUT_HOURS),
        "next_action_type": ACTION_FEEDBACK_TIMEOUT,
    })


# ── T17b: Grace reminder (no state change) ──────────────
def t17b_grace_reminder(pe, reminder_index, trigger_source="scheduler"):
    """T17b: grace_waiting → grace_waiting (reminder sent, schedule next)."""
    if reminder_index + 1 < len(GRACE_REMINDER_DAYS):
        next_day = GRACE_REMINDER_DAYS[reminder_index + 1]
        next_at = add_to_date(pe.grace_window_start, days=next_day)
        next_type = ACTION_GRACE_REMINDER
    else:
        next_at = pe.grace_window_end_at
        next_type = ACTION_GRACE_CHECK

    log_event(pe, "grace_reminder_sent", trigger_source=trigger_source,
              details={"reminder_index": reminder_index})

    return transition(pe, STATE_GRACE_WAITING, trigger_source, {
        "next_action_at": next_at,
        "next_action_type": next_type,
    })


# ── T18: Grace expired → paused ─────────────────────────
def t18_grace_expired(pe, trigger_source="scheduler"):
    """T18: grace_waiting → paused_no_activity."""
    return transition(pe, STATE_PAUSED_NO_ACTIVITY, trigger_source, {
        "journey_label": LABEL_PAUSED,
        "program_status": PROGRAM_PAUSED,
        "pause_reason": PAUSE_NO_ACTIVITY,
        "in_grace_window": 0,
        "next_action_at": add_to_date(now_datetime(), days=3),
        "next_action_type": ACTION_RE_ENGAGEMENT,
    })


# ── T19: Reactivate (Core path) ─────────────────────────
def t19_reactivate_core(pe, trigger_source="glific_flow"):
    """T19: paused_no_activity → normal_content_delivery."""
    return transition(pe, STATE_NORMAL_CONTENT, trigger_source, {
        "journey_label": LABEL_RESUMED,
        "program_status": PROGRAM_ACTIVE,
        "pause_reason": "",
        "pause_count": (pe.pause_count or 0) + 1,
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_CONTENT_DELIVERY,
    })


# ── T20: Reactivate (Remedial path) ─────────────────────
def t20_reactivate_remedial(pe, trigger_source="glific_flow"):
    """T20: paused_no_activity → remedial_content_delivery."""
    return transition(pe, STATE_REMEDIAL_CONTENT, trigger_source, {
        "journey_label": LABEL_RESUMED,
        "program_status": PROGRAM_ACTIVE,
        "pause_reason": "",
        "pause_count": (pe.pause_count or 0) + 1,
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_CONTENT_DELIVERY,
    })


# ── T21: Binge-paused resumes ───────────────────────────
def t21_binge_resume(pe, trigger_source="scheduler"):
    """T21: paused_binge → normal_content_delivery (calendar advanced)."""
    return transition(pe, STATE_NORMAL_CONTENT, trigger_source, {
        "journey_label": LABEL_RESUMED,
        "program_status": PROGRAM_ACTIVE,
        "pause_reason": "",
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_WEEK_ADVANCEMENT,
    })


# ── T22: Duplicate submission (no state change) ─────────
def t22_duplicate_submission(pe, trigger_source="flow_callback"):
    """T22: submitted_awaiting_feedback stays same. Log only."""
    log_event(pe, "submission_received", trigger_source=trigger_source,
              details={"is_primary": False, "duplicate": True})
    return True


# ── T24: Admin drops student ────────────────────────────
def t24_admin_drop(pe, trigger_source="admin"):
    """T24: ANY → program_dropped."""
    return transition(pe, STATE_PROGRAM_DROPPED, trigger_source, {
        "journey_label": LABEL_DROPPED,
        "program_status": PROGRAM_DROPPED,
        "next_action_at": None,
        "next_action_type": "",
    })


# ── T25: Delivery failure (no state change) ─────────────
def t25_delivery_failure(pe, flow_name, trigger_source="scheduler"):
    """T25: ANY → same state. Increment failure count."""
    pe.delivery_failure_count = (pe.delivery_failure_count or 0) + 1
    pe.save(ignore_permissions=True)

    log_event(pe, "delivery_failed", trigger_source=trigger_source,
              details={"flow_name": flow_name, "failure_count": pe.delivery_failure_count})
    return True


# ════════════════════════════════════════════════════════════
# SUBMISSION DISPATCH
# ════════════════════════════════════════════════════════════

def apply_submission_transition(pe, points=0, trigger_source="flow_callback"):
    """
    Apply the correct submission transition based on current state.
    Returns (transition_id, success).
    """
    state = pe.resolved_flow_state

    if state == STATE_NORMAL_CONTENT:
        t7_core_submission(pe, points, trigger_source)
        return "T7", True

    if state == STATE_NORMAL_ESCALATION:
        t3_escalation_submission(pe, points, trigger_source)
        return "T3", True

    if state == STATE_REMEDIAL_CONTENT:
        t9_remedial_submission(pe, points, trigger_source)
        return "T9", True

    if state == STATE_REMEDIAL_ESCALATION:
        t9_remedial_submission(pe, points, trigger_source)
        return "T9", True

    if state == STATE_GRACE_WAITING:
        t17_grace_submission(pe, points, trigger_source)
        return "T17", True

    if state == STATE_SUBMITTED_AWAITING:
        t22_duplicate_submission(pe, trigger_source)
        return "T22", True

    # Terminal or paused — should not receive submissions
    return None, False


# ════════════════════════════════════════════════════════════
# HELPER: Get PE for student
# ════════════════════════════════════════════════════════════

def get_active_pe(student_id, batch_name=None):
    """
    Get the active ProgramEnrollment for a student.
    Returns PE doc or None.
    """
    filters = {
        "student": student_id,
        "program_status": ["in", [PROGRAM_ACTIVE, PROGRAM_PAUSED]],
    }
    if batch_name:
        filters["batch"] = batch_name

    pe_name = frappe.db.get_value("ProgramEnrollment", filters, "name",
                                   order_by="creation desc")
    if pe_name:
        return frappe.get_doc("ProgramEnrollment", pe_name)
    return None
