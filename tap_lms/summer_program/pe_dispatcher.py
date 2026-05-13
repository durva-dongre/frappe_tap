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
    PROGRAM_PAUSED,
    TERMINAL_STATES,
    ACTION_CONTENT_DELIVERY,
    ACTION_ESCALATION,
    ACTION_FEEDBACK_TIMEOUT,
    ACTION_WEEK_ADVANCEMENT,
    ACTION_GRACE_CHECK,
    ACTION_PAUSE_CHECK,
    ACTION_FLOW_FIELD_MAP,
    STATE_NORMAL_CONTENT, STATE_NORMAL_ESCALATION,
    STATE_REMEDIAL_CONTENT, STATE_REMEDIAL_ESCALATION,
    STATE_SUBMITTED_AWAITING,
    STATE_GRACE_WAITING, STATE_WEEK_COMPLETED,
    STATE_PAUSED_BINGE,
    CF_ESCALATION_ORDER, CF_ESCALATION_TYPE,
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
      - program_status is active OR paused (paused PEs need pause_check
        / re_engagement handlers to be reachable; B3 fix)
      - next_action_type is a per-PE individual-timer action

    Routes each PE to the appropriate handler based on next_action_type.

    Note: there is no batch-level partition. Collection-mode batchers (when
    built) filter on different next_action_type values; this dispatcher and
    those batchers are partitioned by action type, not by Batch. See
    architecture §8.
    """
    now = now_datetime()

    # SELECT candidate PEs with FOR UPDATE SKIP LOCKED so multiple parallel
    # workers can run this loop without contending for the same rows
    # (architecture §8.1, pattern P-001). The SKIP LOCKED clause makes each
    # worker take a different slice. We also capture journey_label here so
    # the atomic claim below can guard against state moving under us.
    #
    # program_status filter includes both ACTIVE and PAUSED so paused-state
    # handlers (handle_pause_check for binge-resume, handle_re_engagement)
    # are reachable. Earlier ACTIVE-only filter excluded them entirely (B3).
    # PG `= ANY(%s)` with a list parameter per L-005 (avoid IN-tuple).
    candidates = frappe.db.sql(
        """
        SELECT pe.name, pe.next_action_type, pe.next_action_at,
               pe.batch, pe.student, pe.glific_id,
               pe.resolved_flow_state, pe.current_week,
               pe.last_escalation_step, pe.current_path,
               pe.journey_label
        FROM `tabProgramEnrollment` pe
        WHERE pe.next_action_at IS NOT NULL
          AND pe.next_action_at <= %s
          AND pe.program_status = ANY(%s)
          AND pe.next_action_type != ''
        ORDER BY pe.next_action_at ASC
        LIMIT %s
        FOR UPDATE SKIP LOCKED
        """,
        (now, [PROGRAM_ACTIVE, PROGRAM_PAUSED], DISPATCH_BATCH_SIZE),
        as_dict=True,
    )

    if not candidates:
        return {"dispatched": 0, "skipped": 0, "errors": 0}

    processed = 0
    skipped = 0
    errors = 0

    for pe_row in candidates:
        # Atomic claim per P-001: clear next_action_at conditionally on the
        # journey_label still matching what we read. If 0 rows are updated,
        # another worker (or a flow callback) moved the state under us and
        # we must NOT dispatch — skip and continue. Postgres-specific
        # RETURNING NAME is the idempotency primitive; see L-001/L-018.
        #
        # Note: architecture §8.1 also calls for `last_dispatched_at = NOW()`
        # as an audit trail. That column doesn't exist on PE yet — file a
        # follow-up to add it via DocType UI if dispatcher debugging needs it.
        # The atomic-claim primitive works without it.
        claimed = frappe.db.sql(
            """
            UPDATE `tabProgramEnrollment`
            SET next_action_at = NULL
            WHERE name = %s
              AND journey_label = %s
              AND next_action_at IS NOT NULL
            RETURNING name
            """,
            (pe_row.name, pe_row.journey_label),
        )
        if not claimed:
            skipped += 1
            continue

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
            # Action already cleared by the atomic claim above; no retry loop.

    if processed or errors or skipped:
        frappe.db.commit()

    return {"dispatched": processed, "skipped": skipped, "errors": errors}


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
    Handler: escalation (CR-003 channel-aware)

    Determines which escalation step to fire, pushes the per-step contact
    fields to Glific (escalation_order + escalation_type), then branches on
    the step's `escalation_type`:

    - help_note_a / help_note_b / voice_note → fire SP_Escalation flow.
      Glific reads the two contact fields and routes per-channel content.
    - parent_call → enqueue Vocallabs job, SKIP SP_Escalation entirely.
      The Glific flow is not involved in this branch; the call is placed
      via the Vocallabs 3-step API in summer_program/vocallabs.py.

    Step exhaustion routes per the existing T5 / T6 / T11 split (preserved
    from pre-CR-003). The grace clock is NOT armed here — it was already
    armed at week start (T0 / T19); these transitions just flip the state
    label and let the existing `grace_check` scheduler tick handle expiry.
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
        # All steps exhausted — transition to grace or remedial.
        # CR-003: the grace clock is already armed at the week start; T5/T11
        # preserve it. T6 (zero-activity → remedial) is unchanged.
        if state in (STATE_NORMAL_CONTENT, STATE_NORMAL_ESCALATION):
            if pe.submission_count and pe.submission_count > 0:
                t5_escalation_to_grace(pe, "dispatcher")
            else:
                t6_escalation_to_remedial(pe, trigger_source="dispatcher")
        elif state in (STATE_REMEDIAL_CONTENT, STATE_REMEDIAL_ESCALATION):
            t11_remedial_to_grace(pe, "dispatcher")
        else:
            _clear_action(pe_row.name)
        return

    # ── Fire escalation step (CR-003 branch on escalation_type) ─────
    step_config = steps[next_step - 1]
    next_hours = step_config.get("hours_after_previous", 24)
    escalation_type = step_config.get("escalation_type") or "help_note_a"

    # CR-003 §"Escalation flow — new semantics" step 3:
    # Push escalation_order + escalation_type to Glific BEFORE any flow
    # trigger or Vocallabs enqueue. This is the contract the updated
    # SP_Escalation flow reads from to pick its per-channel branch.
    # Failure to push is logged but does not block the dispatcher — the
    # next state-transition's _enqueue_contact_field_sync will re-sync
    # escalation_order, and the next handle_escalation tick will push
    # escalation_type again on its branch.
    if pe.glific_id:
        _push_escalation_contact_fields(
            pe.glific_id, pe.name, pe.student,
            escalation_order=next_step,
            escalation_type=escalation_type,
        )

    # Transition to escalation state + schedule next step.
    # Note: t2/t4/t8/t10 do NOT fire Glific themselves — they just bump
    # last_escalation_step and schedule next_action_at. The flow trigger
    # (or Vocallabs enqueue) happens below, after the state transition.
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

    # ── Channel branch ─────────────────────────────────────────────
    if escalation_type == "parent_call":
        # Resolve ParentCallConfig and enqueue Vocallabs call. Skip
        # SP_Escalation entirely — Glific is not involved for parent calls.
        # The Vocallabs module handles its own retry/DLQ; the dispatcher
        # tick continues without waiting on the actual call.
        frappe.enqueue(
            "tap_lms.summer_program.vocallabs.initiate_parent_call",
            queue="long",
            timeout=300,
            enqueue_after_commit=True,
            pe_name=pe.name,
            escalation_step=step_config,
        )
        log_event(pe, "escalation_sent", trigger_source="dispatcher",
                  details={"step": next_step, "escalation_type": "parent_call"})
        return

    # Text or voice-note channels → fire SP_Escalation flow.
    flow_id = _get_flow_id(pe_row.batch, ACTION_ESCALATION)
    if flow_id and pe.glific_id:
        _trigger_flow(flow_id, pe.glific_id, pe.name, "escalation")


def _push_escalation_contact_fields(glific_id, pe_name, student_id,
                                    escalation_order, escalation_type):
    """Push escalation_order + escalation_type to Glific via the same async
    retry+DLQ pipeline used by transition syncs (pattern P-007 / L-015).

    Reusing _sync_contact_fields_job keeps both pushes (the per-transition
    full-cache push and this per-step delta push) going through one retry
    machinery. We only push the two CR-003 fields here so the call is
    cheap and targeted — Glific's update_contact_fields is per-field
    idempotent, so partial pushes are safe.
    """
    fields = {
        CF_ESCALATION_ORDER: str(escalation_order),
        CF_ESCALATION_TYPE: str(escalation_type or ""),
    }
    try:
        frappe.enqueue(
            "tap_lms.summer_program.state_machine._sync_contact_fields_job",
            queue="short",
            timeout=30,
            enqueue_after_commit=True,
            glific_id=str(glific_id),
            fields=fields,
            pe_name=pe_name,
            retry_count=0,
            student_id=student_id,
        )
    except Exception as e:
        # Don't crash the dispatcher tick if the queue is briefly down —
        # log and continue. The Glific contact cache will catch up on the
        # next state-transition sync.
        frappe.log_error(
            f"CR-003 escalation contact-field enqueue failed for PE {pe_name}: {e}",
            "SP Escalation Contact Field Sync",
        )


def handle_feedback_timeout(pe_row):
    """
    Handler: feedback_timeout

    Safety-net check: if FeedbackConsumer hasn't processed the AI feedback
    within the expected window, verify once whether it arrived (DB check).
    If yes, trigger T12 as a fallback. If no after 3 retries, alert admin.

    NOTE: Normal path is handled by FeedbackConsumer directly — it calls
    t12_feedback_ready after updating Submission and sending the Glific
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
        "Submission",
        {
            "student_id": pe.student,
            "program_enrollment": pe.name,
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


def handle_grace_check(pe_row):
    """
    Handler: grace_check (CR-003 — direct drop)

    Grace window has expired. CR-003 §"Grace window — new semantics":
    if the student hasn't submitted (weekly_submission_done = 0) the PE
    transitions directly to STATE_PROGRAM_DROPPED via t17_grace_expired.
    No paused_no_activity hop, no re-engagement loop — that's all deleted
    in this CR.

    If the student DID submit during the window (weekly_submission_done = 1)
    and we somehow land here (a race or a stale scheduler row), the handler
    is a no-op — clear the action and trust the existing state.

    Defensive: if `resolved_flow_state` is not grace_waiting (student moved
    via T17 grace submission already), no-op as well.
    """
    from tap_lms.summer_program.state_machine import t17_grace_expired

    pe = frappe.get_doc("ProgramEnrollment", pe_row.name)

    # Student already moved out of grace_waiting (submission landed → T17
    # transitioned them, or they were dropped by an admin). No-op.
    if pe.resolved_flow_state != STATE_GRACE_WAITING:
        _clear_action(pe_row.name)
        return

    # CR-003 + CR-002 v2: if weekly_submission_done is set, the student
    # submitted within the window. Don't drop — clear the action and let
    # the next T19 (week advance) re-arm the clock.
    if pe.weekly_submission_done:
        _clear_action(pe_row.name)
        return

    # Defensive: if the clock hasn't actually expired yet, re-schedule the
    # tick for the proper expiry time rather than dropping early. Should
    # match exactly under normal scheduling but absorbs minor clock skew.
    now = now_datetime()
    if pe.grace_window_end_at and get_datetime(pe.grace_window_end_at) > now:
        pe.next_action_at = pe.grace_window_end_at
        pe.next_action_type = ACTION_GRACE_CHECK
        pe.save(ignore_permissions=True)
        return

    # Clock expired AND no submission this week → drop.
    t17_grace_expired(pe, "dispatcher")


# CR-003: handle_re_engagement and handle_grace_reminder removed.
# Re-engagement is now inbound-only (SP_Incoming_Router routes a rejoin path
# when program_status = 'dropped'); the backend no longer reaches out to
# paused students. Grace reminders are also gone — the escalation steps
# within the week ARE the reminders.


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
    ACTION_GRACE_CHECK: handle_grace_check,
    ACTION_PAUSE_CHECK: handle_pause_check,
    # CR-003: handle_re_engagement and handle_grace_reminder removed.
    # Legacy PEs with next_action_type IN ('re_engagement', 'grace_reminder')
    # are nulled by the migration patch (cr_003.grace_and_reengagement); any
    # post-migration row that somehow holds these values falls through to
    # the "Unknown action_type" branch in _dispatch_single which logs and
    # clears the action defensively.
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


def _get_next_week_open_date(batch, target_week):
    """Calculate when a specific week becomes available based on batch calendar."""
    if not batch.start_date:
        return add_to_date(now_datetime(), days=7)

    # Each week opens 7 days after the previous
    days_offset = (target_week - 1) * 7
    return add_to_date(get_datetime(batch.start_date), days=days_offset)
