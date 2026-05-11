"""
Per-PE Scheduler Dispatcher
tap_lms/summer_program/pe_dispatcher.py

The per-PE dispatcher is the "brain" of the time-based automation layer.
It runs every 1-2 minutes, queries all PEs with overdue next_action_at,
and routes each one to the appropriate handler based on next_action_type.

Unlike the collection-based daily scheduler (scheduler.py) which triggers
flows on entire groups, this dispatcher handles individual student timelines.

Register in hooks.py:
    scheduler_events = {
        "cron": {
            "*/2 * * * *": [
                "tap_lms.summer_program.pe_dispatcher.dispatch_pending_actions",
            ]
        }
    }

Scheduler partition: this dispatcher processes PEs whose next_action_type is
an individual-timer action (feedback_timeout, grace_reminder, pause_check,
etc.). Synchronous events shared across many students (content_delivery,
week_advancement at batch start) are handled by collection-mode batchers
when those exist. Partition is by next_action_type, not by Batch.
"""
import frappe
from frappe.utils import now_datetime, get_datetime, add_to_date

from tap_lms.summer_program.constants import (
    BPR_ACTIVE,
    PROGRAM_ACTIVE,
    TERMINAL_STATES,
    ACTION_CONTENT_DELIVERY,
    ACTION_ESCALATION,
    ACTION_FEEDBACK_TIMEOUT,
    ACTION_WEEK_ADVANCEMENT,
    ACTION_GRACE_REMINDER,
    ACTION_GRACE_CHECK,
    ACTION_RE_ENGAGEMENT,
    ACTION_PAUSE_CHECK,
    ACTION_FLOW_FIELD_MAP,
    STATE_NORMAL_CONTENT, STATE_NORMAL_ESCALATION,
    STATE_REMEDIAL_CONTENT, STATE_REMEDIAL_ESCALATION,
    STATE_SUBMITTED_AWAITING,
    STATE_GRACE_WAITING, STATE_WEEK_COMPLETED,
    STATE_PAUSED_NO_ACTIVITY, STATE_PAUSED_BINGE,
    GRACE_REMINDER_DAYS,
)
from tap_lms.summer_program.event_log import log_event


# ════════════════════════════════════════════════════════════
# DISPATCHER (entry point)
# ════════════════════════════════════════════════════════════

# Max PEs to process per dispatch cycle (prevents runaway)
DISPATCH_BATCH_SIZE = 500


def dispatch_pending_actions():
    """
    Main dispatcher entry point. Called every 1-2 minutes by Frappe scheduler.

    Finds all PEs where:
      - next_action_at <= now
      - program_status is active (not paused/completed/dropped)
      - next_action_type is a per-PE individual-timer action

    Routes each PE to the appropriate handler based on next_action_type.

    Note: there is no batch-level partition. Collection-mode batchers (when
    built) filter on different next_action_type values; this dispatcher and
    those batchers are partitioned by action type, not by Batch. See
    architecture §8.
    """
    now = now_datetime()

    # Query overdue PEs. No JOIN to Batch needed — partition is by action type,
    # not by batch-level feature flag.
    overdue_pes = frappe.db.sql(
        """
        SELECT pe.name, pe.next_action_type, pe.next_action_at,
               pe.batch, pe.student, pe.glific_id,
               pe.resolved_flow_state, pe.current_week,
               pe.last_escalation_step, pe.current_path
        FROM `tabProgramEnrollment` pe
        WHERE pe.next_action_at IS NOT NULL
          AND pe.next_action_at <= %s
          AND pe.program_status = %s
          AND pe.next_action_type != ''
        ORDER BY pe.next_action_at ASC
        LIMIT %s
        """,
        (now, PROGRAM_ACTIVE, DISPATCH_BATCH_SIZE),
        as_dict=True,
    )

    if not overdue_pes:
        return {"dispatched": 0}

    processed = 0
    errors = 0

    for pe_row in overdue_pes:
        try:
            _dispatch_single(pe_row)
            processed += 1
        except Exception as e:
            errors += 1
            frappe.log_error(
                f"Dispatcher error for PE {pe_row.name} "
                f"(action={pe_row.next_action_type}): {str(e)}",
                "SP PE Dispatcher",
            )
            # Clear the action to prevent infinite retry loop
            _clear_action(pe_row.name)

    if processed or errors:
        frappe.db.commit()

    return {"dispatched": processed, "errors": errors}


def _dispatch_single(pe_row):
    """Route a single PE to its handler based on next_action_type."""
    action_type = pe_row.next_action_type
    handler = HANDLER_MAP.get(action_type)

    if not handler:
        frappe.log_error(
            f"Unknown action_type '{action_type}' for PE {pe_row.name}",
            "SP PE Dispatcher",
        )
        _clear_action(pe_row.name)
        return

    handler(pe_row)


def _clear_action(pe_name):
    """Clear next_action fields to prevent re-processing."""
    frappe.db.set_value(
        "ProgramEnrollment", pe_name,
        {"next_action_at": None, "next_action_type": ""},
        update_modified=False,
    )


# ════════════════════════════════════════════════════════════
# HANDLERS
# ════════════════════════════════════════════════════════════


def handle_content_delivery(pe_row):
    """
    Handler: content_delivery

    Triggers SP_Content_Delivery flow for this student.
    The flow handles the content display; on completion it calls
    update_flow_status which sets the next action (or escalation on timeout).

    After triggering, clears next_action since the flow callback
    will set the next one.
    """
    flow_id = _get_flow_id(pe_row.batch, ACTION_CONTENT_DELIVERY)
    if not flow_id:
        _clear_action(pe_row.name)
        return

    if pe_row.glific_id:
        _trigger_flow(flow_id, pe_row.glific_id, pe_row.name, "content_delivery")

    # Clear — flow callback will set next action
    _clear_action(pe_row.name)


def handle_escalation(pe_row):
    """
    Handler: escalation

    Determines which escalation step to fire, triggers SP_Escalation flow,
    and schedules the next escalation step (or transitions to grace/remedial
    if all steps exhausted).
    """
    from tap_lms.summer_program.state_machine import (
        t2_start_escalation, t4_next_escalation_step,
        t5_escalation_to_grace, t6_escalation_to_remedial,
        t8_start_remedial_escalation, t10_next_remedial_escalation,
        t11_remedial_to_grace,
    )

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)
    state = pe.resolved_flow_state
    current_step = pe.last_escalation_step or 0

    # Get escalation steps config for this student
    steps = _get_escalation_steps_for_pe(pe)
    if not steps:
        # No escalation config — go to grace
        if state == STATE_NORMAL_ESCALATION:
            t5_escalation_to_grace(pe, "dispatcher")
        elif state == STATE_REMEDIAL_ESCALATION:
            t11_remedial_to_grace(pe, "dispatcher")
        else:
            _clear_action(pe_row.name)
        return

    next_step = current_step + 1

    if next_step > len(steps):
        # All steps exhausted — transition to grace or remedial
        if state in (STATE_NORMAL_CONTENT, STATE_NORMAL_ESCALATION):
            # Check if student had any activity this week
            if pe.submission_count and pe.submission_count > 0:
                t5_escalation_to_grace(pe, "dispatcher")
            else:
                t6_escalation_to_remedial(pe, trigger_source="dispatcher")
        elif state in (STATE_REMEDIAL_CONTENT, STATE_REMEDIAL_ESCALATION):
            t11_remedial_to_grace(pe, "dispatcher")
        else:
            _clear_action(pe_row.name)
        return

    # Fire escalation step
    step_config = steps[next_step - 1]
    next_hours = step_config.get("hours_after_previous", 24)

    # Transition to escalation state + schedule next
    if state == STATE_NORMAL_CONTENT:
        t2_start_escalation(pe, next_step, "dispatcher")
    elif state == STATE_NORMAL_ESCALATION:
        t4_next_escalation_step(pe, next_step, next_hours, "dispatcher")
    elif state == STATE_REMEDIAL_CONTENT:
        t8_start_remedial_escalation(pe, next_step, "dispatcher")
    elif state == STATE_REMEDIAL_ESCALATION:
        t10_next_remedial_escalation(pe, next_step, next_hours, "dispatcher")
    else:
        _clear_action(pe_row.name)
        return

    # Trigger SP_Escalation flow
    flow_id = _get_flow_id(pe_row.batch, ACTION_ESCALATION)
    if flow_id and pe.glific_id:
        _trigger_flow(flow_id, pe.glific_id, pe.name, "escalation")


def handle_feedback_timeout(pe_row):
    """
    Handler: feedback_timeout

    Safety-net check: if FeedbackConsumer hasn't processed the AI feedback
    within the expected window, verify once whether it arrived (DB check).
    If yes, trigger T12 as a fallback. If no after 3 retries, alert admin.

    NOTE: Normal path is handled by FeedbackConsumer directly — it calls
    t12_feedback_ready after updating ImgSubmission and sending the Glific
    notification. This handler only fires as a timeout fallback.
    """
    from tap_lms.summer_program.state_machine import t12_feedback_ready

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)

    if pe.resolved_flow_state != STATE_SUBMITTED_AWAITING:
        # FeedbackConsumer already handled it — state moved
        _clear_action(pe_row.name)
        return

    # Check if feedback arrived but FeedbackConsumer missed the SP hook
    has_feedback = frappe.db.exists(
        "ImgSubmission",
        {
            "student": pe.student,
            "batch": pe.batch,
            "week": pe.current_week,
            "is_primary": 1,
            "status": "Completed",
        },
    )

    if has_feedback:
        # Feedback arrived but state wasn't updated — trigger T12 as fallback
        t12_feedback_ready(pe, "feedback_timeout_fallback")
    else:
        # Retry: schedule another check in 1 hour (max 3 retries)
        retry_count = pe.delivery_failure_count or 0
        if retry_count < 3:
            pe.delivery_failure_count = retry_count + 1
            pe.next_action_at = add_to_date(now_datetime(), hours=1)
            pe.next_action_type = ACTION_FEEDBACK_TIMEOUT
            pe.save(ignore_permissions=True)
        else:
            # Give up — alert admin, clear action
            frappe.log_error(
                f"Feedback timeout: AI feedback not received for PE {pe.name} "
                f"(student={pe.student}, week={pe.current_week}). "
                f"Check RabbitMQ/GCS pipeline.",
                "SP Feedback Timeout Alert",
            )
            _clear_action(pe_row.name)


def handle_week_advancement(pe_row):
    """
    Handler: week_advancement

    Advances the student to the next week. Checks:
      - If next week > total_weeks → T16 (program completed)
      - If next week > max_allowed_week → T15 (binge pause)
      - Otherwise → T14 (normal week advance)
    """
    from tap_lms.summer_program.state_machine import (
        t14_week_advance, t15_binge_pause, t16_program_completed,
    )

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)

    if pe.resolved_flow_state != STATE_WEEK_COMPLETED:
        _clear_action(pe_row.name)
        return

    batch = frappe.get_doc("Batch", pe.batch)
    next_week = (pe.current_week or 1) + 1
    total_weeks = batch.total_weeks or 8
    max_allowed = pe.max_allowed_week or (batch.current_calendar_week or 1) + 1

    if next_week > total_weeks:
        # Program completed
        t16_program_completed(pe, "dispatcher")
        # Trigger program_complete flow
        flow_id = _get_flow_id(pe.batch, "program_complete")
        if flow_id and pe.glific_id:
            _trigger_flow(flow_id, pe.glific_id, pe.name, "program_complete")

    elif next_week > max_allowed:
        # Binge limit — can't go faster than batch calendar
        # Calculate when next week opens (next Monday or batch schedule)
        next_open = _get_next_week_open_date(batch, next_week)
        t15_binge_pause(pe, next_open, "dispatcher")
        # Trigger binge info flow
        flow_id = _get_flow_id(pe.batch, ACTION_PAUSE_CHECK)
        if flow_id and pe.glific_id:
            _trigger_flow(flow_id, pe.glific_id, pe.name, "binge_info")

    else:
        # Normal advancement
        week_rule = _get_week_rule(pe, batch, next_week)
        t14_week_advance(pe, next_week, week_rule, "dispatcher")


def handle_grace_reminder(pe_row):
    """
    Handler: grace_reminder

    Sends a grace period reminder to the student and schedules the next
    reminder or grace_check (expiry).
    """
    from tap_lms.summer_program.state_machine import t17b_grace_reminder

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)

    if pe.resolved_flow_state != STATE_GRACE_WAITING:
        _clear_action(pe_row.name)
        return

    # Determine which reminder index we're at
    reminder_index = _get_current_reminder_index(pe)

    # Fire the transition (schedules next reminder or grace_check)
    t17b_grace_reminder(pe, reminder_index, "dispatcher")

    # Trigger SP_Grace_Reminder flow
    flow_id = _get_flow_id(pe.batch, ACTION_GRACE_REMINDER)
    if flow_id and pe.glific_id:
        _trigger_flow(flow_id, pe.glific_id, pe.name, "grace_reminder")


def handle_grace_check(pe_row):
    """
    Handler: grace_check

    Grace window has expired. If student still hasn't submitted,
    transition to paused_no_activity (T18).
    """
    from tap_lms.summer_program.state_machine import t18_grace_expired

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)

    if pe.resolved_flow_state != STATE_GRACE_WAITING:
        # Student submitted during grace → already moved
        _clear_action(pe_row.name)
        return

    # Grace expired — pause the student
    t18_grace_expired(pe, "dispatcher")

    # Trigger re-engagement flow will be handled by handle_re_engagement
    # (T18 sets next_action_type = re_engagement with 3-day delay)


def handle_re_engagement(pe_row):
    """
    Handler: re_engagement

    Sends a re-engagement message to a paused student.
    If max re-engagement attempts reached, auto-drop (T23).
    """
    from tap_lms.summer_program.state_machine import t24_admin_drop

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)

    if pe.resolved_flow_state not in (STATE_PAUSED_NO_ACTIVITY,):
        # Student already reactivated or dropped
        _clear_action(pe_row.name)
        return

    re_count = pe.re_engagement_count or 0
    max_attempts = 3  # After 3 attempts, auto-drop

    if re_count >= max_attempts:
        # Auto-drop — T23/T24
        t24_admin_drop(pe, "dispatcher")
        log_event(pe, "auto_dropped", trigger_source="dispatcher",
                  details={"reason": "re_engagement_exhausted", "attempts": re_count})
        return

    # Trigger SP_Paused_Reengagement flow
    flow_id = _get_flow_id(pe.batch, ACTION_RE_ENGAGEMENT)
    if flow_id and pe.glific_id:
        _trigger_flow(flow_id, pe.glific_id, pe.name, "re_engagement")

    # Schedule next re-engagement attempt in 3 days
    pe.re_engagement_count = re_count + 1
    pe.next_action_at = add_to_date(now_datetime(), days=3)
    pe.next_action_type = ACTION_RE_ENGAGEMENT
    pe.save(ignore_permissions=True)


def handle_pause_check(pe_row):
    """
    Handler: pause_check

    For binge-paused students: check if the calendar has advanced
    enough to allow them to resume. If yes, trigger T21 (binge resume).
    """
    from tap_lms.summer_program.state_machine import t21_binge_resume

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)

    if pe.resolved_flow_state != STATE_PAUSED_BINGE:
        _clear_action(pe_row.name)
        return

    batch = frappe.get_doc("Batch", pe.batch)
    next_week = (pe.current_week or 1) + 1
    max_allowed = batch.current_calendar_week or 1

    if next_week <= max_allowed:
        # Calendar caught up — resume
        t21_binge_resume(pe, "dispatcher")
    else:
        # Still ahead of calendar — check again next Monday
        pe.next_action_at = add_to_date(now_datetime(), days=7)
        pe.next_action_type = ACTION_PAUSE_CHECK
        pe.save(ignore_permissions=True)


# ════════════════════════════════════════════════════════════
# HANDLER MAP
# ════════════════════════════════════════════════════════════

HANDLER_MAP = {
    ACTION_CONTENT_DELIVERY: handle_content_delivery,
    ACTION_ESCALATION: handle_escalation,
    ACTION_FEEDBACK_TIMEOUT: handle_feedback_timeout,
    ACTION_WEEK_ADVANCEMENT: handle_week_advancement,
    ACTION_GRACE_REMINDER: handle_grace_reminder,
    ACTION_GRACE_CHECK: handle_grace_check,
    ACTION_RE_ENGAGEMENT: handle_re_engagement,
    ACTION_PAUSE_CHECK: handle_pause_check,
}


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════


def _get_flow_id(batch_name, action_type):
    """Get the Glific flow UUID for an action type from the BPR."""
    field = ACTION_FLOW_FIELD_MAP.get(action_type)
    if not field:
        return None

    bpr_name = frappe.db.get_value(
        "BatchProgramRun",
        {"batch": batch_name, "status": BPR_ACTIVE},
        "name",
    )
    if not bpr_name:
        return None

    return frappe.db.get_value("BatchProgramRun", bpr_name, field)


def _trigger_flow(flow_id, glific_id, pe_name, action_label):
    """Trigger a Glific flow for a single contact."""
    from tap_lms.glific_integration import start_contact_flow

    try:
        default_results = {
            "pe_name": pe_name,
            "action": action_label,
        }
        start_contact_flow(str(flow_id), str(glific_id), default_results)
    except Exception as e:
        frappe.log_error(
            f"Flow trigger error: PE={pe_name}, action={action_label}, "
            f"flow={flow_id}, glific_id={glific_id}: {str(e)}",
            "SP Flow Trigger",
        )


def _get_escalation_steps_for_pe(pe):
    """Get escalation step configs for a PE's archetype."""
    from tap_lms.summer_program.student_progression_sp import _get_escalation_steps

    try:
        student = frappe.get_doc("Student", pe.student)
        batch = frappe.get_doc("Batch", pe.batch)
        return _get_escalation_steps(student, batch)
    except Exception:
        return []


def _get_week_rule(pe, batch, week):
    """Get the WeekRule/ArchetypeConfig for a specific week."""
    try:
        config = frappe.db.get_value(
            "ArchetypeConfig",
            {
                "batch": batch.name,
                "archetype": pe.archetype,
                "experiment_arm": pe.experiment_arm or "default",
                "week": week,
            },
            ["expected_submission_type", "core_learning_unit", "remedial_learning_unit"],
            as_dict=True,
        )
        return config
    except Exception:
        return None


def _get_current_reminder_index(pe):
    """Determine which grace reminder we're on based on elapsed days."""
    if not pe.grace_window_start:
        return 0

    from frappe.utils import date_diff
    days_elapsed = date_diff(now_datetime(), pe.grace_window_start)

    for i, day in enumerate(GRACE_REMINDER_DAYS):
        if days_elapsed <= day:
            return max(0, i - 1)

    return len(GRACE_REMINDER_DAYS) - 1


def _get_next_week_open_date(batch, target_week):
    """Calculate when a specific week becomes available based on batch calendar."""
    if not batch.start_date:
        return add_to_date(now_datetime(), days=7)

    # Each week opens 7 days after the previous
    days_offset = (target_week - 1) * 7
    return add_to_date(get_datetime(batch.start_date), days=days_offset)
