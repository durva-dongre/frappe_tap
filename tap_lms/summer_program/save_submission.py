"""
Save Submission API
tap_lms/summer_program/save_submission.py

API A3: save_submission — the core submission handler.

Atomic idempotent submission with:
  - Atomic UPDATE WHERE journey_label check (prevents race conditions)
  - is_primary logic (first submission = primary, rest = duplicates)
  - ImgSubmission record creation
  - ProgramEnrollment state transition
  - Points calculation from EscalationStep
  - EngagementState update

Called by:
  - SP_Content_Delivery wait node (Path A — inline submission)
  - SP_Escalation wait node (Path A — inline during escalation)
  - SP_Grace_Entry / SP_Grace_Reminder wait node (Path A — during grace)
  - SP_Submission sub-flow (Path B — via SP_Incoming_Router)
"""
import frappe
import json
from frappe import _
from frappe.utils import now_datetime, today, getdate, cint

from tap_lms.summer_program.constants import (
    STATE_SUBMITTED_AWAITING, STATE_NORMAL_CONTENT,
    STATE_NORMAL_ESCALATION, STATE_REMEDIAL_CONTENT,
    STATE_REMEDIAL_ESCALATION, STATE_GRACE_WAITING,
    LABEL_CONTENT_DELIVERED, LABEL_SUBMITTED,
    CONTENT_DELIVERY_STATES, ESCALATION_STATES,
    TERMINAL_STATES, PAUSED_STATES,
)
from tap_lms.summer_program.state_machine import (
    get_active_pe,
    apply_submission_transition,
)
from tap_lms.summer_program.event_log import log_event


@frappe.whitelist(allow_guest=False)
def save_submission(student_id, submission_type=None, media_url=None,
                    week=None, content_id=None):
    """
    API A3: save_submission

    Atomic idempotent submission handler.

    Args:
        student_id: Student name, glific_id, or phone
        submission_type: emoji | text_word | voice_note | photo | video |
                        photo_video_artefact | voice_note_text_summary
        media_url: URL of submitted media (photo/video/voice)
        week: Override week number (defaults to PE.current_week)
        content_id: Optional assignment/content ID

    Returns:
        dict with: status (accepted|duplicate|rejected), is_primary,
                   points_awarded, submission_count
    """
    student_id = _resolve_student(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    pe = get_active_pe(student_id)
    if not pe:
        return {"success": False, "error": "No active ProgramEnrollment"}

    current_week = cint(week) or pe.current_week or 1

    # Check if student is in a terminal or paused state
    if pe.resolved_flow_state in TERMINAL_STATES:
        return {
            "success": False,
            "error": "Student in terminal state",
            "resolved_flow_state": pe.resolved_flow_state,
        }

    # ── Atomic is_primary check ─────────────────────────────
    # Use atomic UPDATE to claim primary submission.
    # Only succeeds if journey_label is still 'content_delivered'
    # (or any pre-submission label). If it's already 'submitted',
    # this is a duplicate.
    is_primary = _try_claim_primary(pe, current_week)

    # ── Calculate points ────────────────────────────────────
    points = 0
    if is_primary:
        points = _calculate_points(pe)

    # ── Create ImgSubmission record ─────────────────────────
    img_sub = _create_img_submission(
        pe=pe,
        student_id=student_id,
        week=current_week,
        submission_type=submission_type,
        media_url=media_url,
        content_id=content_id,
        is_primary=is_primary,
        points=points,
    )

    # ── Apply state transition ──────────────────────────────
    if is_primary:
        transition_id, success = apply_submission_transition(
            pe, points=points, trigger_source="flow_callback"
        )
    else:
        # Duplicate — no state change (T22)
        from tap_lms.summer_program.state_machine import t22_duplicate_submission
        t22_duplicate_submission(pe, "flow_callback")
        transition_id = "T22"

    # ── Update EngagementState ──────────────────────────────
    _update_engagement(student_id)

    # ── Log the submission event ────────────────────────────
    log_event(pe, "submission_received", trigger_source="flow_callback",
              details={
                  "is_primary": is_primary,
                  "submission_type": submission_type,
                  "points_awarded": points,
                  "week": current_week,
                  "escalation_step_at_submit": pe.last_escalation_step or 0,
                  "transition": transition_id,
                  "img_submission": img_sub,
              })

    frappe.db.commit()

    return {
        "success": True,
        "status": "accepted" if is_primary else "duplicate",
        "is_primary": is_primary,
        "points_awarded": points,
        "submission_count": pe.submission_count or 1,
        "week": current_week,
        "resolved_flow_state": pe.resolved_flow_state,
        "student_id": student_id,
    }


# ════════════════════════════════════════════════════════════
# ATOMIC PRIMARY CLAIM
# ════════════════════════════════════════════════════════════

def _try_claim_primary(pe, week):
    """
    Atomically claim primary submission for this week.
    Uses UPDATE WHERE to prevent race conditions.

    Returns True if this is the primary (first) submission, False if duplicate.
    """
    # Atomic UPDATE: only succeeds if journey_label is still pre-submission
    pre_submission_labels = [
        "enrolled", "content_delivered", "grace_window",
        "resumed", "week_advanced",
    ]

    result = frappe.db.sql("""
        UPDATE `tabProgramEnrollment`
        SET journey_label = 'submitted',
            last_label_change_at = NOW(),
            submission_count = COALESCE(submission_count, 0) + 1,
            last_submission_at = NOW()
        WHERE name = %s
          AND journey_label IN %s
    """, (pe.name, pre_submission_labels))

    rows_affected = frappe.db.sql("SELECT ROW_COUNT()")[0][0]

    if rows_affected > 0:
        pe.reload()
        return True

    # Already submitted — this is a duplicate
    pe.reload()
    return False


# ════════════════════════════════════════════════════════════
# POINTS CALCULATION
# ════════════════════════════════════════════════════════════

def _calculate_points(pe):
    """
    Calculate points based on which escalation step the student is at.
    Earlier submission = more points.
    """
    from tap_lms.summer_program.student_progression_sp import _get_escalation_steps

    student = frappe.get_doc("Student", pe.student)
    batch = frappe.get_doc("Batch", pe.batch)
    steps = _get_escalation_steps(student, batch)

    if not steps:
        return 0

    sent_count = pe.last_escalation_step or 0

    if sent_count == 0:
        # Submitted before any escalation → highest points (step 1)
        return steps[0].get("points_awarded", 0)

    if sent_count <= len(steps):
        return steps[sent_count - 1].get("points_awarded", 0)

    return 0


# ════════════════════════════════════════════════════════════
# IMG SUBMISSION RECORD
# ════════════════════════════════════════════════════════════

def _create_img_submission(pe, student_id, week, submission_type,
                           media_url, content_id, is_primary, points):
    """Create ImgSubmission record for tracking and AI feedback pipeline."""
    try:
        doc = frappe.new_doc("ImgSubmission")
        doc.student_id = student_id
        doc.program_enrollment = pe.name
        doc.week = week
        doc.submission_type = submission_type or ""
        doc.img_url = media_url or ""
        doc.assign_id = content_id
        doc.is_primary = 1 if is_primary else 0
        doc.escalation_step_at_submit = pe.last_escalation_step or 0
        doc.status = "Pending" if is_primary else "Completed"
        doc.created_at = now_datetime()
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception as e:
        frappe.log_error(
            f"ImgSubmission creation error: {str(e)}", "SP Save Submission"
        )
        return None


# ════════════════════════════════════════════════════════════
# ENGAGEMENT STATE
# ════════════════════════════════════════════════════════════

def _update_engagement(student_id):
    """Update EngagementState on submission."""
    try:
        es = frappe.db.get_value(
            "EngagementState", {"student": student_id},
            ["name", "last_activity_date", "current_streak"], as_dict=True,
        )
        today_date = getdate(today())

        if es:
            updates = {"last_activity_date": today_date, "last_updated": now_datetime()}
            last = es.last_activity_date
            if last:
                if isinstance(last, str):
                    last = getdate(last)
                days_diff = (today_date - last).days
                if days_diff == 1:
                    updates["current_streak"] = (es.current_streak or 0) + 1
                elif days_diff > 1:
                    updates["current_streak"] = 1
            else:
                updates["current_streak"] = 1
            frappe.db.set_value("EngagementState", es.name, updates)
        else:
            new_es = frappe.new_doc("EngagementState")
            new_es.student = student_id
            new_es.last_activity_date = today_date
            new_es.current_streak = 1
            new_es.last_updated = now_datetime()
            new_es.insert(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(f"EngagementState error: {str(e)}", "SP Engagement")


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _resolve_student(identifier):
    """Resolve student_id or glific_id to Student name."""
    if not identifier:
        return None
    if frappe.db.exists("Student", identifier):
        return identifier
    student = frappe.db.get_value("Student", {"glific_id": identifier}, "name")
    if student:
        return student
    return frappe.db.get_value("Student", {"phone": str(identifier).strip()}, "name")
