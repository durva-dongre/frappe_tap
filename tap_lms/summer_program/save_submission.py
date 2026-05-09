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
import re


@frappe.whitelist(allow_guest=False)
def save_submission(student_id, submission_type=None, media_url=None,
                    response_text=None, week=None, assignment_id=None):
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
                   points_awarded, submission_count, img_submission
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

    # ── Resolve submission_type ──────────────────────────────
    # Glific can't identify the type, so we detect from inputs:
    #   media_url + response_text → photo_video_artefact (media with description)
    #   media_url only → detect from URL extension (photo/video/voice_note)
    #   response_text only → detect emoji vs text
    #   nothing → fall back to PE's expected type
    if not submission_type:
        submission_type = _detect_submission_type(media_url, response_text, pe)

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
        response_text=response_text,
        assignment_id=assignment_id,
        is_primary=is_primary,
        points=points,
    )

    # ── Upload to GCS + enqueue to RabbitMQ (background) ────
    # Runs async so the API responds instantly (~50ms).
    # For media: GCS upload + RabbitMQ (2-10s)
    # For emoji/text: RabbitMQ only (~100ms)
    if is_primary and img_sub:
        # Serialize PE fields needed by pipeline (can't pass doc to background job)
        pe_context = {
            "student": pe.student,
            "archetype": pe.archetype,
            "experiment_arm": pe.experiment_arm,
            "current_expected_submission_type": pe.current_expected_submission_type,
            "language": getattr(pe, "language", ""),
            "batch": pe.batch,
            "current_week": pe.current_week,
            "current_path": pe.current_path,
            "current_tier": pe.current_tier,
            "course_level": pe.course_level,
            "last_escalation_step": pe.last_escalation_step,
        }
        frappe.enqueue(
            "tap_lms.summer_program.save_submission._enqueue_to_feedback_pipeline",
            queue="default",
            timeout=120,
            img_sub_name=img_sub,
            media_url=media_url,
            response_text=response_text,
            submission_type=submission_type,
            pe_context=pe_context,
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
        "img_submission": img_sub,
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
# IMG SUBMISSION RECORD
# ════════════════════════════════════════════════════════════

def _create_img_submission(pe, student_id, week, submission_type,
                           media_url, response_text, assignment_id,
                           is_primary, points):
    """Create ImgSubmission record for tracking and AI feedback pipeline."""
    try:
        doc = frappe.new_doc("ImgSubmission")
        doc.student_id = student_id
        doc.program_enrollment = pe.name
        doc.week = week
        doc.submission_type = submission_type or ""
        doc.img_url = media_url or ""
        doc.response_text = response_text or ""
        doc.assign_id = assignment_id
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
# SUBMISSION TYPE DETECTION
# ════════════════════════════════════════════════════════════

# File extensions for media type detection from Glific URLs
PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp")
AUDIO_EXTENSIONS = (".ogg", ".oga", ".opus", ".mp3", ".m4a", ".wav", ".aac")

# Common single-character emojis and emoji patterns
# Covers most Unicode emoji ranges used in WhatsApp
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended-A
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero width joiner
    "\U00000023\U0000002A\U00000030-\U00000039\U000020E3"  # keycap sequences
    "]+",
    flags=re.UNICODE,
)


def _detect_submission_type(media_url, response_text, pe):
    """
    Auto-detect submission type from inputs since Glific can't identify it.

    Detection logic (in priority order):
      1. media_url + response_text → "photo_video_artefact"
         (Student sent media with a text description/caption)
      2. media_url only → detect from URL extension:
         - .jpg/.png/etc → "photo"
         - .mp4/.mov/etc → "video"
         - .ogg/.opus/.mp3/etc → "voice_note"
      3. response_text only → detect emoji vs text:
         - Pure emoji (1-3 emoji chars, no text) → "emoji"
         - Otherwise → "text_word"
      4. Neither → fall back to PE's current_expected_submission_type

    Args:
        media_url: URL of submitted media (from Glific/WhatsApp)
        response_text: Text or emoji content from the student
        pe: ProgramEnrollment doc (for fallback type)

    Returns:
        str: submission type
    """
    # Case 1: Both media and text → artefact with description
    if media_url and response_text:
        return "photo_video_artefact"

    # Case 2: Media URL only → detect from file extension
    if media_url:
        return _detect_media_type(media_url)

    # Case 3: Text/emoji only → detect emoji vs text
    if response_text:
        return _detect_text_type(response_text)

    # Case 4: Nothing provided → use PE's expected type
    return pe.current_expected_submission_type or "photo"


def _detect_media_type(url):
    """
    Detect media type from URL file extension.

    Glific/WhatsApp media URLs typically look like:
      https://storage.googleapis.com/.../image.jpg
      https://web.whatsapp.net/.../video.mp4
      https://filemanager.gupshup.io/.../audio.ogg

    Falls back to "photo" if extension is unrecognized.
    """
    # Strip query params and fragments to get clean path
    clean_url = url.split("?")[0].split("#")[0].lower()

    if clean_url.endswith(PHOTO_EXTENSIONS):
        return "photo"
    elif clean_url.endswith(VIDEO_EXTENSIONS):
        return "video"
    elif clean_url.endswith(AUDIO_EXTENSIONS):
        return "voice_note"

    # Unrecognized extension — default to photo (most common submission)
    return "photo"


def _detect_text_type(text):
    """
    Detect if text is an emoji reaction or a text response.

    Emoji submissions: single emoji or small cluster (1-3 emoji chars)
      e.g., "👍", "😊", "⭐⭐⭐", "🎉👏"
    Text submissions: any text with non-emoji characters
      e.g., "hello", "I liked the story", "good 👍"
    """
    stripped = text.strip()
    if not stripped:
        return "text_word"

    # Remove all emoji characters — if nothing remains, it's pure emoji
    without_emoji = EMOJI_PATTERN.sub("", stripped).strip()

    if not without_emoji and len(stripped) <= 12:
        # Pure emoji, reasonable length (3-4 emoji can be ~12 bytes)
        return "emoji"

    return "text_word"


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _resolve_student(identifier):
    """Delegate to shared utility."""
    from tap_lms.summer_program.utils import resolve_student
    return resolve_student(identifier)


def _enqueue_to_feedback_pipeline(img_sub_name, media_url, response_text,
                                  submission_type, pe_context):
    """
    Upload media to GCS (if applicable) and publish enriched payload to RabbitMQ.

    Pipeline:
      - For photo/video/voice: upload to GCS, then publish with GCS URL
      - For emoji/text: publish directly with response_text (no GCS upload)

    The feedback generation app needs archetype, experiment_arm, and
    submission_type to select the right rubric and feedback tone.

    Called for ALL primary submissions (media and text/emoji).
    """
    try:
        from tap_lms.imgana.submission import get_rabbitmq_settings
        import pika

        gcs_url = None

        # 1. Upload media to GCS (only if there's a media URL)
        if media_url:
            from tap_lms.imgana.submission import upload_to_gcs
            gcs_url = upload_to_gcs(media_url, img_sub_name)
            if gcs_url:
                frappe.db.set_value("ImgSubmission", img_sub_name, "img_url", gcs_url)

        # 2. Build enriched payload for feedback generation
        assign_id = frappe.db.get_value(
            "ImgSubmission", img_sub_name, "assign_id") or ""

        payload = {
            # Core identifiers
            "submission_id": img_sub_name,
            "assign_id": assign_id,
            "student_id": pe_context.get("student", ""),
            "img_url": gcs_url or media_url or "",
            "response_text": response_text or "",

            # Student context (needed for feedback generation)
            "archetype": pe_context.get("archetype", ""),
            "experiment_arm": pe_context.get("experiment_arm", ""),
            "submission_type": submission_type or "",
            "expected_submission_type": pe_context.get("current_expected_submission_type", ""),
            "language": pe_context.get("language", ""),

            # Program context
            "batch": pe_context.get("batch", ""),
            "current_week": pe_context.get("current_week", 1),
            "current_path": pe_context.get("current_path", "Core"),
            "current_tier": pe_context.get("current_tier", "Basic"),
            "course_level": pe_context.get("course_level", ""),

            # Scoring context
            "escalation_step_at_submit": pe_context.get("last_escalation_step", 0),

            "created_at": str(now_datetime()),
        }

        # 3. Publish to RabbitMQ
        rabbitmq_config = get_rabbitmq_settings()
        credentials = pika.PlainCredentials(
            rabbitmq_config['username'],
            rabbitmq_config['password'],
        )
        parameters = pika.ConnectionParameters(
            rabbitmq_config['host'],
            int(rabbitmq_config['port']),
            rabbitmq_config['virtual_host'],
            credentials,
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        try:
            channel.queue_declare(
                queue=rabbitmq_config['queue'], durable=True, passive=True,
            )
        except Exception:
            channel.queue_declare(
                queue=rabbitmq_config['queue'], durable=True,
            )

        channel.basic_publish(
            exchange='',
            routing_key=rabbitmq_config['queue'],
            body=json.dumps(payload),
        )
        connection.close()

        frappe.logger("submission").info(
            f"Enqueued SP submission {img_sub_name} for feedback"
        )

    except Exception as e:
        # Don't fail the submission if pipeline errors — log and continue
        frappe.log_error(
            f"Feedback pipeline error for {img_sub_name}: {str(e)}",
            "SP Feedback Pipeline",
        )
