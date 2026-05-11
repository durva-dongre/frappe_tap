"""
Save Submission API
tap_lms/summer_program/save_submission.py

API A3: save_submission — the core submission handler.

Atomic idempotent submission with:
  - Atomic UPDATE WHERE journey_label check (prevents race conditions)
  - is_primary logic (first submission = primary, rest = duplicates)
  - Submission record creation
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
from frappe.utils import now_datetime, today, getdate, cint
from urllib.parse import urlparse

from tap_lms.summer_program.constants import (
    TERMINAL_STATES,
    FEEDBACK_PIPELINE_MAX_RETRIES,
    FEEDBACK_PIPELINE_RETRY_LOG_TITLE,
    FEEDBACK_PIPELINE_DLQ_LOG_TITLE,
)
from tap_lms.summer_program.state_machine import (
    get_active_pe,
    apply_submission_transition,
)
from tap_lms.summer_program.event_log import log_event
URL_SUBMISSION_TYPES = {"audio", "image", "video"}


@frappe.whitelist(allow_guest=False)
def save_submission(student_id, submission_type=None, media_url=None,
                    response_text=None, week=None, assignment_id=None,
                    submission=None):
    """
    API A3: save_submission

    Atomic idempotent submission handler.

    Args:
        student_id: Student name, glific_id, or phone
        submission_type: emoji | text_word | voice_note | photo | video |
                        photo_video_artefact | voice_note_text_summary
                        If omitted, defaults to PE.current_expected_submission_type
        media_url: URL of submitted media (photo/video/voice_note)
        response_text: Text or emoji content submitted by the student.
                       Used for emoji and text_word submission types.
        week: Override week number (defaults to PE.current_week)
        assignment_id: Assignment ID from get_content_details API
                       (e.g. "B2_FL_L1_RA12-Basic")

    Returns:
        dict with: status (accepted|duplicate|rejected), is_primary,
                   points_awarded, submission_count, submission_id
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

    # ── Normalize submission payload ────────────────────────
    # Produces the assessment Submission schema:
    #   submission_type: text | emoji | audio | image | video
    #   submission_text: text/emoji/caption
    #   submission_url: media URL
    payload = _normalize_submission_payload(
        submission,
        submission_type=submission_type,
        media_url=media_url,
        response_text=response_text,
        pe=pe,
    )

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

    # ── Create Submission record ────────────────────────────
    submission_doc = _create_submission(
        pe=pe,
        student_id=student_id,
        week=current_week,
        payload=payload,
        assignment_id=assignment_id,
        is_primary=is_primary,
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
                  "submission_type": payload["submission_type"],
                  "points_awarded": points,
                  "week": current_week,
                  "escalation_step_at_submit": pe.last_escalation_step or 0,
                  "transition": transition_id,
                  "submission_id": submission_doc.name if submission_doc else None,
              })

    # ── Upload to GCS + enqueue to RabbitMQ (background) ────
    if is_primary and submission_doc:
        _queue_submission_processing(
            submission_doc,
            pe_context=_build_pe_context(pe),
        )

    frappe.db.commit()

    return _build_submission_response(
        pe=pe,
        student_id=student_id,
        submission_doc=submission_doc,
        is_primary=is_primary,
        points=points,
        week=current_week,
    )


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

    # Use RETURNING (Postgres) to atomically check if the UPDATE matched.
    # On MariaDB, frappe.db.sql for UPDATE returns nothing, so we fall back
    # to cursor.rowcount via frappe.db._cursor.rowcount.
    try:
        result = frappe.db.sql("""
            UPDATE `tabProgramEnrollment`
            SET journey_label = 'submitted',
                last_label_change_at = NOW(),
                submission_count = COALESCE(submission_count, 0) + 1,
                last_submission_at = NOW()
            WHERE name = %s
              AND journey_label IN %s
            RETURNING name
        """, (pe.name, pre_submission_labels))
        rows_affected = len(result) if result else 0
    except Exception:
        # MariaDB doesn't support RETURNING — fall back to non-RETURNING UPDATE
        frappe.db.sql("""
            UPDATE `tabProgramEnrollment`
            SET journey_label = 'submitted',
                last_label_change_at = NOW(),
                submission_count = COALESCE(submission_count, 0) + 1,
                last_submission_at = NOW()
            WHERE name = %s
              AND journey_label IN %s
        """, (pe.name, pre_submission_labels))
        rows_affected = frappe.db._cursor.rowcount

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

    if sent_count < len(steps):
        # Submitted after N escalations → points from step N
        # (later steps award fewer points)
        return steps[sent_count].get("points_awarded", 0)

    # Submitted after all escalation steps exhausted → minimum or 0
    return steps[-1].get("points_awarded", 0) if steps else 0


# ════════════════════════════════════════════════════════════
# SUBMISSION RECORD
# ════════════════════════════════════════════════════════════

def _create_submission(pe, student_id, week, payload, assignment_id, is_primary):
    """Create assessment-style Submission with summer-program context."""
    doc = frappe.new_doc("Submission")
    doc.assign_id = assignment_id
    doc.student_id = student_id
    doc.submission_type = payload["submission_type"]
    doc.submission_text = payload["submission_text"]
    doc.submission_url = payload["submission_url"]
    doc.status = "Pending" if is_primary else "Completed"
    doc.program_enrollment = pe.name
    doc.week = week
    doc.escalation_step_at_submit = pe.last_escalation_step or 0
    doc.is_primary = 1 if is_primary else 0
    doc.created_at = now_datetime()
    doc.insert(ignore_permissions=True)
    return doc


def _build_submission_response(pe, student_id, submission_doc, is_primary, points, week):
    return {
        "success": True,
        "status": "accepted" if is_primary else "duplicate",
        "is_primary": is_primary,
        "points_awarded": points,
        "submission_count": pe.submission_count or 1,
        "week": week,
        "resolved_flow_state": pe.resolved_flow_state,
        "next_action_type": pe.next_action_type or "",
        "next_action_at": str(pe.next_action_at) if pe.next_action_at else "",
        "program_status": pe.program_status or "",
        "current_path": pe.current_path or "",
        "student_id": student_id,
        "submission_id": submission_doc.name if submission_doc else None,
    }


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
# SUBMISSION NORMALIZATION
# ════════════════════════════════════════════════════════════

def _normalize_submission_payload(
    submission=None,
    submission_type=None,
    media_url=None,
    response_text=None,
    pe=None,
):
    """
    Normalize Pal and assessment-style inputs into the Submission schema.
    """
    if submission is None:
        return _normalize_submission_parts(
            submission_type=submission_type,
            media_url=media_url,
            response_text=response_text,
            pe=pe,
        )

    if not isinstance(submission, str) or not submission.strip():
        frappe.throw("Submission is required")

    submission = submission.strip()

    if _looks_like_url(submission):
        return {
            "submission_type": (
                _to_assessment_submission_type(submission_type)
                or _infer_url_submission_type(submission)
            ),
            "submission_text": None,
            "submission_url": submission,
        }

    return {
        "submission_type": (
            _to_assessment_submission_type(submission_type)
            or ("emoji" if _contains_only_emoji(submission) else "text")
        ),
        "submission_text": submission,
        "submission_url": None,
    }


def _normalize_submission_parts(submission_type=None, media_url=None, response_text=None, pe=None):
    if not media_url and not response_text:
        frappe.throw("Submission is required")

    normalized_type = _to_assessment_submission_type(submission_type)
    if not normalized_type:
        normalized_type = _infer_structured_submission_type(media_url, response_text, pe)

    return {
        "submission_type": normalized_type,
        "submission_text": response_text.strip() if isinstance(response_text, str) else response_text,
        "submission_url": media_url.strip() if isinstance(media_url, str) else media_url,
    }


def _infer_structured_submission_type(media_url=None, response_text=None, pe=None):
    if media_url:
        return _infer_url_submission_type(media_url)
    if response_text:
        return "emoji" if _contains_only_emoji(response_text) else "text"
    return _to_assessment_submission_type(
        getattr(pe, "current_expected_submission_type", None)
    ) or "image"


def _contains_only_emoji(submission):
    text = submission.strip()
    if not text:
        return False

    return not any(char.isalnum() for char in text)


def _looks_like_url(submission):
    parsed = urlparse(submission.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _infer_url_submission_type(submission):
    path = urlparse(submission.strip()).path.lower()

    audio_extensions = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac")
    image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic")
    video_extensions = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".mpeg")

    if path.endswith(audio_extensions):
        return "audio"
    if path.endswith(video_extensions):
        return "video"
    if path.endswith(image_extensions):
        return "image"

    return "image"


def _to_assessment_submission_type(submission_type):
    mapping = {
        "text_word": "text",
        "voice_note": "audio",
        "photo": "image",
        "photo_video_artefact": "image",
        "voice_note_text_summary": "audio",
    }
    return mapping.get(submission_type or "", submission_type or "")


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _resolve_student(identifier):
    """Delegate to shared utility."""
    from tap_lms.summer_program.utils import resolve_student
    return resolve_student(identifier)


def _build_pe_context(pe):
    return {
        "program_enrollment": pe.name,
        "archetype": pe.archetype,
        "experiment_arm": pe.experiment_arm,
        "expected_submission_type": _to_assessment_submission_type(
            pe.current_expected_submission_type
        ),
        "language": getattr(pe, "language", ""),
        "batch": pe.batch,
        "current_week": pe.current_week,
        "current_path": pe.current_path,
        "current_tier": pe.current_tier,
        "course_level": pe.course_level,
        "last_escalation_step": pe.last_escalation_step,
    }


def _queue_submission_processing(submission_doc, pe_context):
    queue_name = (
        "long"
        if submission_doc.submission_type in URL_SUBMISSION_TYPES
        else "default"
    )
    frappe.enqueue(
        "tap_lms.summer_program.save_submission.process_submission_async",
        queue=queue_name,
        timeout=600,
        enqueue_after_commit=True,
        submission_id=submission_doc.name,
        submission_url=submission_doc.submission_url,
        pe_context=pe_context,
    )


def process_submission_async(submission_id, submission_url=None, pe_context=None):
    """
    Upload URL submissions to GCS, mark the record Processing, and enqueue
    feedback processing. Text and emoji submissions skip GCS upload.
    """
    pe_context = pe_context or {}
    try:
        submission = frappe.get_doc("Submission", submission_id)

        if submission.submission_type in URL_SUBMISSION_TYPES:
            from tap_lms.imgana.submission import upload_to_gcs

            uploaded_url = upload_to_gcs(submission_url, submission.name)
            submission.submission_url = uploaded_url

        submission.status = "Processing"
        submission.upload_error_log = None
        submission.save(ignore_permissions=True)
        frappe.db.commit()

        enqueue_submission(submission.name, pe_context=pe_context)

    except Exception as e:
        frappe.db.rollback()
        frappe.logger("submission").error(
            f"Error in background processing for submission {submission_id}: {str(e)}"
        )

        try:
            submission = frappe.get_doc("Submission", submission_id)
            submission.status = "Failed"
            submission.upload_error_log = frappe.get_traceback()[:5000]
            submission.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as log_error:
            frappe.logger("submission").error(
                f"Failed to update submission {submission_id} after background error: {str(log_error)}"
            )


def enqueue_submission(submission_id, pe_context=None, retry_count=0):
    try:
        import pika
        from tap_lms.imgana.submission import get_rabbitmq_settings

        pe_context = pe_context or {}
        submission = frappe.get_doc("Submission", submission_id)

        payload = {
            "submission_id": submission.name,
            "assign_id": submission.assign_id,
            "student_id": submission.student_id,
            "submission_type": submission.submission_type,
            "submission_text": submission.submission_text,
            "submission_url": submission.submission_url,
            "program_enrollment": getattr(
                submission,
                "program_enrollment",
                pe_context.get("program_enrollment", ""),
            ),
            "week": getattr(submission, "week", pe_context.get("current_week", 1)),
            "is_primary": getattr(submission, "is_primary", 1),
            "escalation_step_at_submit": getattr(
                submission,
                "escalation_step_at_submit",
                pe_context.get("last_escalation_step", 0),
            ),
            "archetype": pe_context.get("archetype", ""),
            "experiment_arm": pe_context.get("experiment_arm", ""),
            "expected_submission_type": pe_context.get("expected_submission_type", ""),
            "language": pe_context.get("language", ""),
            "batch": pe_context.get("batch", ""),
            "current_week": pe_context.get("current_week", 1),
            "current_path": pe_context.get("current_path", ""),
            "current_tier": pe_context.get("current_tier", ""),
            "course_level": pe_context.get("course_level", ""),
            "created_at": str(getattr(submission, "created_at", submission.creation)),
        }

        rabbitmq_config = get_rabbitmq_settings()
        credentials = pika.PlainCredentials(
            rabbitmq_config["username"],
            rabbitmq_config["password"],
        )
        parameters = pika.ConnectionParameters(
            rabbitmq_config["host"],
            int(rabbitmq_config["port"]),
            rabbitmq_config["virtual_host"],
            credentials,
        )

        connection = None
        publish_succeeded = False
        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.confirm_delivery()
            channel.queue_declare(queue=rabbitmq_config["queue"], durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=rabbitmq_config["queue"],
                body=json.dumps(payload, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
                mandatory=True,
            )
            publish_succeeded = True
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception as close_err:
                    frappe.logger("submission").warning(
                        f"RabbitMQ close failed for {submission_id} "
                        f"(publish_succeeded={publish_succeeded}): {close_err}"
                    )

        if publish_succeeded:
            frappe.logger("submission").info(
                f"Enqueued submission {submission_id} with type {submission.submission_type}"
            )
    except Exception as e:
        frappe.logger("submission").error(
            f"Failed to enqueue submission {submission_id}: {str(e)}"
        )
        retry_count = (retry_count or 0) + 1
        student_id = ""

        try:
            student_id = frappe.db.get_value("Submission", submission_id, "student_id") or ""
        except Exception:
            student_id = ""

        if retry_count <= FEEDBACK_PIPELINE_MAX_RETRIES:
            frappe.log_error(
                title=FEEDBACK_PIPELINE_RETRY_LOG_TITLE,
                message=(
                    f"Feedback pipeline transient failure "
                    f"(attempt {retry_count}/{FEEDBACK_PIPELINE_MAX_RETRIES + 1}) "
                    f"for submission {submission_id} "
                    f"(student={student_id or 'unknown'}): {e}"
                ),
            )
            try:
                frappe.enqueue(
                    "tap_lms.summer_program.save_submission.enqueue_submission",
                    queue="default",
                    timeout=120,
                    submission_id=submission_id,
                    pe_context=pe_context,
                    retry_count=retry_count,
                )
            except Exception as enqueue_err:
                frappe.log_error(
                    title=FEEDBACK_PIPELINE_DLQ_LOG_TITLE,
                    message=json.dumps(
                        {
                            "reason": "double_fault_enqueue_failed",
                            "submission_id": submission_id,
                            "student_id": student_id,
                            "pe_context": pe_context,
                            "final_error": str(e),
                            "enqueue_error": str(enqueue_err),
                            "retries_attempted": retry_count,
                        },
                        indent=2,
                        default=str,
                    ),
                )
        else:
            frappe.log_error(
                title=FEEDBACK_PIPELINE_DLQ_LOG_TITLE,
                message=json.dumps(
                    {
                        "submission_id": submission_id,
                        "student_id": student_id,
                        "pe_context": pe_context,
                        "final_error": str(e),
                        "retries_attempted": retry_count,
                    },
                    indent=2,
                    default=str,
                ),
            )
