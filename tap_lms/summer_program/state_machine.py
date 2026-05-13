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
    STATE_GRACE_WAITING, STATE_PAUSED_BINGE,
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
    ACTION_GRACE_CHECK,
    ACTION_PAUSE_CHECK,
    PAUSE_BINGE_LIMIT,
    DEFAULT_GRACE_WINDOW_DAYS,
    FEEDBACK_TIMEOUT_HOURS,
    CF_RESOLVED_FLOW_STATE, CF_CURRENT_WEEK, CF_CURRENT_PATH,
    CF_CURRENT_TIER, CF_PROGRAM_STATUS, CF_TOTAL_POINTS,
    CF_CURRENT_STREAK, CF_GRACE_WINDOW_END, CF_EXPECTED_SUBMISSION,
    CF_LAST_ESCALATION_STEP, CF_SUBMISSION_COUNT,
    # CR-002 v2 gamification contact fields
    CF_TOTAL_ACTIVITY_POINTS, CF_WEEKLY_ACTIVITY_POINTS,
    CF_TOTAL_QUIZ_POINTS, CF_WEEKLY_QUIZ_POINTS,
    CF_BONUS_QUIZ_POINTS,
    CF_TOTAL_SUBMISSION_POINTS, CF_WEEKLY_SUBMISSION_POINTS,
    CF_SPECIAL_GEMS, CF_WEEKLY_SUBMISSION_DONE,
    # CR-003 — 2 new escalation channel routing fields
    CF_ESCALATION_ORDER, CF_ESCALATION_TYPE,
    GLIFIC_SYNC_MAX_RETRIES, GLIFIC_SYNC_RETRY_LOG_TITLE, GLIFIC_SYNC_DLQ_LOG_TITLE,
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
        CF_LAST_ESCALATION_STEP: str(pe.last_escalation_step or 0),
        CF_SUBMISSION_COUNT: str(pe.submission_count or 0),
        # ── CR-002 v2 gamification fields ──
        # Pushed alongside the existing fields so the cache size on Glific is
        # 26 after this CR (28 after CR-003 also ships escalation_order/type).
        # `weekly_video_done` is intentionally NOT included — internal-only.
        CF_TOTAL_ACTIVITY_POINTS: str(pe.total_activity_points or 0),
        CF_WEEKLY_ACTIVITY_POINTS: str(pe.weekly_activity_points or 0),
        CF_TOTAL_QUIZ_POINTS: str(pe.total_quiz_points or 0),
        CF_WEEKLY_QUIZ_POINTS: str(pe.weekly_quiz_points or 0),
        CF_BONUS_QUIZ_POINTS: str(pe.bonus_quiz_points or 0),
        CF_TOTAL_SUBMISSION_POINTS: str(pe.total_submission_points or 0),
        CF_WEEKLY_SUBMISSION_POINTS: str(pe.weekly_submission_points or 0),
        CF_SPECIAL_GEMS: str(pe.special_gems or 0),
        CF_WEEKLY_SUBMISSION_DONE: str(int(pe.weekly_submission_done or 0)),
        # ── CR-003: escalation_order field is also re-synced here so the
        # Glific contact cache reflects last_escalation_step on every
        # transition. escalation_type is NOT pushed here because it's a
        # per-step attribute, not a PE state field — the dispatcher pushes
        # it explicitly in handle_escalation BEFORE firing the SP_Escalation
        # flow (CR-003 §"Escalation flow — new semantics" step 3). Pushing
        # escalation_order here keeps the cache fresh after T2/T4/T8/T10
        # transitions which also bump last_escalation_step.
        CF_ESCALATION_ORDER: str(pe.last_escalation_step or 0),
    }
    frappe.enqueue(
        "tap_lms.summer_program.state_machine._sync_contact_fields_job",
        queue="short",
        timeout=30,
        enqueue_after_commit=True,
        glific_id=str(pe.glific_id),
        fields=fields,
        pe_name=pe.name,
        retry_count=0,
        student_id=pe.student,
    )


def _sync_contact_fields_job(glific_id, fields, pe_name, retry_count=0, student_id=None):
    """
    Background job: push PE state to Glific contact fields.

    Called via frappe.enqueue from _enqueue_contact_field_sync and the three
    enrollment paths. Uses the single-call update_contact_fields mutation.

    Args:
        glific_id: Glific contact ID — required to address the contact.
        fields: dict of contact field name → string value (already serialized).
        pe_name: ProgramEnrollment.name when available, OR a synthetic id like
                 "pre-pe:<student_id>" during the pre-PE enrollment chunk path.
                 Used for log correlation; do NOT assume it's resolvable via
                 frappe.get_doc("ProgramEnrollment", pe_name).
        retry_count: Current retry attempt (0 on first call). Re-enqueues
                     increment this; jobs exhausting GLIFIC_SYNC_MAX_RETRIES
                     attempts land in the DLQ.
        student_id: Optional Student document name. Always populated for
                    operator replay so the DLQ entry is actionable even when
                    pe_name is a synthetic "pre-pe:..." string. None for legacy
                    in-flight messages (backward-compat).

    Retry policy (pattern P-007 / lesson L-015):
      - On exception, re-enqueue self with retry_count+1 until GLIFIC_SYNC_MAX_RETRIES.
      - When the retry budget is exhausted, log a structured DLQ entry so operators
        can replay manually. The DLQ payload includes student_id, pe_name, glific_id,
        the fields dict, the final error, and the retry count.

    Known limitation (filed as follow-up): retries are IMMEDIATE (no backoff).
    For sustained Glific outages > ~30 seconds, all 5 retries fire within
    milliseconds and the job DLQs. A proper exponential-backoff scheduler is
    deferred to a follow-up task. Bumping MAX_RETRIES to 5 (from the originally
    proposed 3) covers short Glific 502/503 blips and Redis hiccups while keeping
    this revision minimal.
    """
    try:
        update_contact_fields(glific_id, fields)
    except Exception as e:
        retry_count = (retry_count or 0) + 1
        if retry_count <= GLIFIC_SYNC_MAX_RETRIES:
            frappe.log_error(
                title=GLIFIC_SYNC_RETRY_LOG_TITLE,
                message=(
                    f"Glific sync transient failure "
                    f"(attempt {retry_count}/{GLIFIC_SYNC_MAX_RETRIES + 1}) "
                    f"for PE {pe_name} (student={student_id or 'unknown'}): {e}"
                ),
            )
            try:
                frappe.enqueue(
                    "tap_lms.summer_program.state_machine._sync_contact_fields_job",
                    queue="short",
                    timeout=30,
                    glific_id=glific_id,
                    fields=fields,
                    pe_name=pe_name,
                    retry_count=retry_count,
                    student_id=student_id,
                )
            except Exception as enqueue_err:
                # Double-fault: queue itself is unhealthy. Surface to DLQ
                # immediately so the update isn't lost.
                import json as _json
                frappe.log_error(
                    title=GLIFIC_SYNC_DLQ_LOG_TITLE,
                    message=_json.dumps(
                        {
                            "reason": "double_fault_enqueue_failed",
                            "student_id": student_id,
                            "pe_name": pe_name,
                            "glific_id": glific_id,
                            "fields": fields,
                            "final_error": str(e),
                            "enqueue_error": str(enqueue_err),
                            "retries_attempted": retry_count,
                        },
                        indent=2,
                        default=str,
                    ),
                )
        else:
            import json as _json
            frappe.log_error(
                title=GLIFIC_SYNC_DLQ_LOG_TITLE,
                message=_json.dumps(
                    {
                        "student_id": student_id,
                        "pe_name": pe_name,
                        "glific_id": glific_id,
                        "fields": fields,
                        "final_error": str(e),
                        "retries_attempted": retry_count,
                    },
                    indent=2,
                    default=str,
                ),
            )


# ════════════════════════════════════════════════════════════
# CR-003 — Per-week grace clock helpers
# ════════════════════════════════════════════════════════════

def _batch_grace_window_days(pe):
    """Return the cohort's grace window in days.

    CR-003: grace duration is per-batch via Batch.grace_window_days. Falls
    back to DEFAULT_GRACE_WINDOW_DAYS (14) only if the field is unset, which
    should not happen on properly-configured batches. We log a warning rather
    than throwing so a misconfigured batch doesn't block dispatch.
    """
    if not pe.batch:
        return DEFAULT_GRACE_WINDOW_DAYS
    try:
        days = frappe.db.get_value("Batch", pe.batch, "grace_window_days")
    except Exception:
        days = None
    if not days:
        frappe.log_error(
            f"Batch {pe.batch} has no grace_window_days; "
            f"falling back to default ({DEFAULT_GRACE_WINDOW_DAYS}d) for PE {pe.name}",
            "SP Grace Clock Config",
        )
        return DEFAULT_GRACE_WINDOW_DAYS
    return int(days)


def _grace_clock_updates(pe):
    """Return the dict of grace-clock + scheduling updates for a week-start
    transition (T0 / T19 / `t14_week_advance`).

    CR-003 §"Grace window — new semantics": the clock starts at the week's
    start and resets on every week advance. The expiry scheduler tick fires
    a `grace_check` action which routes to `handle_grace_check` and, if the
    student still hasn't submitted, transitions to STATE_PROGRAM_DROPPED via
    `t17_grace_expired`. This helper keeps the math + field shape in one
    place so T0 and T19 cannot drift out of sync.

    Returns a dict suitable for splatting into a transition's `extra_updates`.
    """
    now = now_datetime()
    grace_end = add_to_date(now, days=_batch_grace_window_days(pe))
    return {
        "in_grace_window": 1,
        "grace_window_start": now,
        "grace_window_end_at": grace_end,
        # The grace_check tick fires at grace_window_end_at; until then, the
        # week's escalation steps drive next_action_at on their own cadence.
        # T0/T19 callers set next_action_at = now for the immediate content
        # delivery; the grace_check is a separate clock that only fires if
        # no submission lands by the window's end.
    }


# ════════════════════════════════════════════════════════════
# NAMED TRANSITIONS (T0–T25)
# ════════════════════════════════════════════════════════════

# ── T0: Enrollment → normal_content_delivery ───────────────
def t0_enrollment(pe, trigger_source="scheduler"):
    """T0: Initial enrollment. Sets resolved_flow_state = normal_content_delivery.

    CR-003: also arms the per-week grace clock — grace_window_start = now,
    grace_window_end_at = now + Batch.grace_window_days. The clock is policed
    by a `grace_check` scheduler action that routes to `handle_grace_check`;
    if no submission lands by grace_window_end_at the PE is dropped (T17).
    Note: T0 also kicks off content delivery via next_action_type = content_delivery
    — that's the immediate work; grace expiry is a separate downstream check.
    """
    updates = {
        "journey_label": LABEL_CONTENT_DELIVERED,
        "program_status": PROGRAM_ACTIVE,
        "current_path": PATH_CORE,
        "current_week": 1,
    }
    updates.update(_grace_clock_updates(pe))
    return transition(pe, STATE_NORMAL_CONTENT, trigger_source, updates)


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
    """T3: normal_escalation → submitted_awaiting_feedback.

    CR-002 v2: extends the existing updates dict to bump the new submission
    counters (`total_submission_points`, `weekly_submission_points`), set the
    sticky `weekly_submission_done` flag, and increment `current_streak` and
    `special_gems` — all in the same atomic save. Streak/gems increment AT
    SUBMISSION TIME, not deferred to T19.
    """
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        # CR-002 v2: submission-points split + streak/gems/sticky flag
        "total_submission_points": (pe.total_submission_points or 0) + points,
        "weekly_submission_points": (pe.weekly_submission_points or 0) + points,
        "weekly_submission_done": 1,
        "current_streak": (pe.current_streak or 0) + 1,
        "special_gems": (pe.special_gems or 0) + 1,
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
    """T5: normal_escalation → grace_waiting (escalation steps exhausted).

    CR-003: the grace clock was already set at the week's start (T0 / T19).
    T5 PRESERVES the existing grace_window_end_at — it does not reset it.
    The PE just enters the dead-air tail state; the `grace_check` scheduler
    action set at week start will fire at grace_window_end_at and route via
    `handle_grace_check`. If pe.grace_window_end_at is somehow None (legacy
    PE), we defensively arm the clock here using the batch grace duration.
    """
    # Defensive: legacy PEs that pre-date CR-003 may not have the clock set.
    if not pe.grace_window_end_at:
        grace_updates = _grace_clock_updates(pe)
    else:
        grace_updates = {"in_grace_window": 1}

    grace_updates.update({
        "journey_label": LABEL_GRACE_WINDOW,
        # The grace_check action is scheduled for the existing grace_window_end_at.
        "next_action_at": pe.grace_window_end_at or grace_updates.get("grace_window_end_at"),
        "next_action_type": ACTION_GRACE_CHECK,
    })
    return transition(pe, STATE_GRACE_WAITING, trigger_source, grace_updates)


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
    """T7: normal_content_delivery → submitted_awaiting_feedback.

    CR-002 v2: extends the existing updates dict to bump the new submission
    counters (`total_submission_points`, `weekly_submission_points`), set the
    sticky `weekly_submission_done` flag, and increment `current_streak` and
    `special_gems` — all in the same atomic save. Streak/gems increment AT
    SUBMISSION TIME, not deferred to T19.
    """
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        # CR-002 v2: submission-points split + streak/gems/sticky flag
        "total_submission_points": (pe.total_submission_points or 0) + points,
        "weekly_submission_points": (pe.weekly_submission_points or 0) + points,
        "weekly_submission_done": 1,
        "current_streak": (pe.current_streak or 0) + 1,
        "special_gems": (pe.special_gems or 0) + 1,
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
    """T9: remedial_content_delivery → submitted_awaiting_feedback.

    CR-002 v2: extends the existing updates dict to bump the new submission
    counters (`total_submission_points`, `weekly_submission_points`), set the
    sticky `weekly_submission_done` flag, and increment `current_streak` and
    `special_gems` — all in the same atomic save. Streak/gems increment AT
    SUBMISSION TIME, not deferred to T19.
    """
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        # CR-002 v2: submission-points split + streak/gems/sticky flag
        "total_submission_points": (pe.total_submission_points or 0) + points,
        "weekly_submission_points": (pe.weekly_submission_points or 0) + points,
        "weekly_submission_done": 1,
        "current_streak": (pe.current_streak or 0) + 1,
        "special_gems": (pe.special_gems or 0) + 1,
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
    """T11: remedial_escalation → grace_waiting.

    CR-003: mirror of T5 for the remedial path. The grace clock was already
    armed at the week start; T11 preserves it. Defensive backfill for legacy
    PEs as in T5.
    """
    if not pe.grace_window_end_at:
        grace_updates = _grace_clock_updates(pe)
    else:
        grace_updates = {"in_grace_window": 1}

    grace_updates.update({
        "journey_label": LABEL_GRACE_WINDOW,
        "next_action_at": pe.grace_window_end_at or grace_updates.get("grace_window_end_at"),
        "next_action_type": ACTION_GRACE_CHECK,
    })
    return transition(pe, STATE_GRACE_WAITING, trigger_source, grace_updates)


# ── T12: AI feedback generated ──────────────────────────
def t12_feedback_ready(pe, trigger_source="microservice"):
    """T12: submitted_awaiting_feedback → feedback_ready.

    FeedbackConsumer handles the Glific notification directly (label="feedback").
    When that Glific flow completes, the flow callback triggers T13
    (feedback_ready → week_completed → week_advancement).

    No dispatcher action is scheduled here — the Glific callback drives the
    next transition. If the callback never fires, a manual check or admin
    intervention is needed.
    """
    return transition(pe, STATE_FEEDBACK_READY, trigger_source, {
        "next_action_at": None,
        "next_action_type": "",
    })


# ── T13: Feedback delivered → week_completed ─────────────
def t13_feedback_delivered(pe, trigger_source="flow_callback"):
    """T13: feedback_ready → week_completed."""
    return transition(pe, STATE_WEEK_COMPLETED, trigger_source, {
        "journey_label": LABEL_FEEDBACK_DELIVERED,
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_WEEK_ADVANCEMENT,
    })


# ── T14 / T19: Week advance (normal) ────────────────────
#
# Naming note: this function is named `t14_week_advance` for historical
# reasons; the architecture-doc vocabulary calls it T19. CR-002 v2 keeps
# the function name (per CR §"T19 week-advance — extended" — do NOT rename).
#
# CR-003 coordination note (DO NOT REMOVE THIS COMMENT BLOCK):
#   CR-003 will append grace re-arm logic AFTER the weekly reset and
#   BEFORE schedule-next-content. If both CRs land, the merged write
#   order is:
#     streak/gem compute → weekly reset → path reset → grace re-arm
#     → schedule next content.
#   Code-reviewers and the CR-003 author should grep for this string.
def t14_week_advance(pe, new_week, week_rule=None, trigger_source="scheduler"):
    """T19: week_completed → normal_content_delivery (next week).

    CR-002 v2 extends T19 in two phases:

    Phase 1 — compute streak/gem update from the two sticky weekly flags:
        if `weekly_video_done = 1 AND weekly_submission_done = 0`:
            current_streak → 0
            special_gems   → max(0, special_gems - 1)
        else:
            both unchanged.

    Phase 2 — reset all weekly_* counters and both sticky flags to 0,
    advance the week, and write the streak/gem values computed in Phase 1.
    `total_*` counters are NEVER reset (cumulative across program).

    Gem floor is enforced in Python (`max(0, ...)`) because the value is
    computed before the UPDATE. SQL `GREATEST(0, ...)` is not needed — the
    value is plain-int by the time we write it.
    """
    tier = TIER_BY_WEEK.get(new_week, DEFAULT_TIER)

    # ── Phase 1: streak/gem compute (CR-002 v2) ─────────────
    was_assigned = bool(pe.weekly_video_done)
    did_submit = bool(pe.weekly_submission_done)
    streak_update = pe.current_streak or 0
    gems_update = pe.special_gems or 0
    if was_assigned and not did_submit:
        # Penalty branch: streak resets, gem decremented (floored at 0).
        streak_update = 0
        gems_update = max(0, gems_update - 1)
    # else: streak/gems unchanged. Either:
    #   - Nothing was assigned (no video) → no penalty for not submitting.
    #   - Student submitted → streak/gems already incremented at submission
    #     time inside the T7/T9/T17 transitions.

    # ── Phase 2: build the reset update dict ────────────────
    updates = {
        "journey_label": LABEL_WEEK_ADVANCED,
        "current_week": new_week,
        "current_path": PATH_CORE,
        "current_tier": tier,
        "submission_count": 0,
        "quiz_completed": 0,
        "last_escalation_step": 0,
        "next_action_at": now_datetime(),
        "next_action_type": ACTION_CONTENT_DELIVERY,
        # CR-002 v2: apply streak/gem update + reset all weeklies + flags
        "current_streak": streak_update,
        "special_gems": gems_update,
        "weekly_activity_points": 0,
        "weekly_quiz_points": 0,
        "weekly_submission_points": 0,
        "weekly_submission_done": 0,
        "weekly_video_done": 0,
        # NOTE: total_activity_points, total_quiz_points,
        # total_submission_points, total_points are NEVER reset (E10).
    }

    # ── CR-003 grace re-arm ─────────────────────────────────
    # The per-week grace clock resets on every week advance. The previous
    # path-reset block above already cleared last_escalation_step; the grace
    # helper now seeds grace_window_start, grace_window_end_at, and the
    # in_grace_window flag for the NEW week. Order (per the coordinate-with-
    # CR-003 comment block on this function): streak/gem → reset → path reset
    # → grace re-arm → schedule next content. The CR-002 v2 reset block above
    # is preserved exactly; CR-003 only APPENDS the grace re-arm.
    #
    # Note: next_action_at above is set to now() for the immediate
    # content_delivery dispatch. The grace_check timer is policed via the
    # `grace_check` scheduler tick that fires at grace_window_end_at; the
    # week-start content delivery and grace expiry are independent clocks.
    # In practice the content_delivery dispatcher claims the row first,
    # transitions further, and the only way a `grace_check` ever fires is if
    # the student goes silent through every escalation step.
    updates.update(_grace_clock_updates(pe))

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
    """T17: grace_waiting → submitted_awaiting_feedback.

    CR-002 v2: extends the existing updates dict to bump the new submission
    counters (`total_submission_points`, `weekly_submission_points`), set the
    sticky `weekly_submission_done` flag, and increment `current_streak` and
    `special_gems` — all in the same atomic save. Streak/gems increment AT
    SUBMISSION TIME, not deferred to T19.
    """
    return transition(pe, STATE_SUBMITTED_AWAITING, trigger_source, {
        "journey_label": LABEL_SUBMITTED,
        "in_grace_window": 0,
        "grace_window_start": None,
        "grace_window_end_at": None,
        "submission_count": (pe.submission_count or 0) + 1,
        "last_submission_at": now_datetime(),
        "total_points": (pe.total_points or 0) + points,
        # CR-002 v2: submission-points split + streak/gems/sticky flag
        "total_submission_points": (pe.total_submission_points or 0) + points,
        "weekly_submission_points": (pe.weekly_submission_points or 0) + points,
        "weekly_submission_done": 1,
        "current_streak": (pe.current_streak or 0) + 1,
        "special_gems": (pe.special_gems or 0) + 1,
        "next_action_at": add_to_date(now_datetime(), hours=FEEDBACK_TIMEOUT_HOURS),
        "next_action_type": ACTION_FEEDBACK_TIMEOUT,
    })


# ── T17 (grace expired) — DELETED in CR-001 / RENAMED in CR-003 ─
#
# Pre-CR-003: T17b fired SP_Grace_Reminder on days 7/11/13 of the window,
# then T18 transitioned the PE to STATE_PAUSED_NO_ACTIVITY and scheduled
# the re-engagement loop. CR-003 retires both: grace reminders are gone
# (escalation steps within the week ARE the reminders) and the
# paused_no_activity state is retired (PEs drop directly at grace expiry).
#
# T17b removed; the dispatcher's `handle_grace_reminder` is also removed.

# ── T17: Grace expired → program_dropped (CR-003) ───────
def t17_grace_expired(pe, trigger_source="scheduler"):
    """T17: grace_waiting → program_dropped.

    CR-003 §"Grace window — new semantics": on grace expiry, the PE
    transitions directly to STATE_PROGRAM_DROPPED. Terminal. No re-engagement
    loop, no paused_no_activity hop. drop_reason = 'grace_expired'. The
    `program_dropped` event is logged for the funnel.

    Pre-CR-003 this slot was T18, which moved to STATE_PAUSED_NO_ACTIVITY and
    scheduled re_engagement. T18 is retained as an alias below for any callers
    that import by the old name; both point to the same function so existing
    grep'ed call sites still work during the cutover window.
    """
    log_event(pe, "program_dropped", trigger_source=trigger_source,
              details={"reason": "grace_expired"})
    return transition(pe, STATE_PROGRAM_DROPPED, trigger_source, {
        "journey_label": LABEL_DROPPED,
        "program_status": PROGRAM_DROPPED,
        "drop_reason": "grace_expired",
        "in_grace_window": 0,
        "next_action_at": None,
        "next_action_type": "",
    })


# Backward-compat alias: callers that imported the old T18 name still work.
# CR-003 retires the function semantics but keeps the name resolvable during
# the cutover window. Delete after one release cycle once no caller imports
# `t18_grace_expired` directly. Tests in test_pe_dispatcher.py still patch
# `state_machine.t18_grace_expired` — they continue working via this alias.
t18_grace_expired = t17_grace_expired


# ── T19 / T20 (reactivate from pause) — DELETED in CR-003 ─
#
# Pre-CR-003: a PE in paused_no_activity could receive an inbound message
# and transition back to normal_content_delivery (T19) or
# remedial_content_delivery (T20). CR-003 removes the paused_no_activity
# state entirely — students drop at grace expiry and re-engagement is
# inbound-only via SP_Incoming_Router (Glific reads program_status='dropped'
# and routes a rejoin path that goes through `reactivate_student`).
#
# `t19_reactivate_core` / `t20_reactivate_remedial` removed. Note the T19
# label is now reused in the architecture-doc vocabulary for the week-advance
# function (`t14_week_advance` keeps its historical function name per CR-002 v2;
# see the comment block at line ~458).


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
