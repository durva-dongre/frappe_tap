"""
Summer Program Student Progression
tap_lms/summer_program/student_progression_sp.py

Submission-driven progression engine for the Summer Program.
Replaces the old quiz-pass/fail branching with:
  - Assignment submission tracking
  - ArchetypeConfig-driven Core/Remedial path resolution
  - Escalation step processing (time-based nudges)
  - Weekly content serving (Core or Remedial LearningUnit)

Called by Glific flows via whitelisted API endpoints.
"""
import frappe
import json
from frappe import _
from frappe.utils import (
    now_datetime, today, getdate, cint, flt,
    time_diff_in_hours, time_diff_in_seconds, date_diff, get_datetime,
)

from tap_lms.summer_program.constants import (
    ALL_ARCHETYPES,
    ALL_ARMS,
    BPR_ACTIVE,
)


# ============================================================
# CONSTANTS
# ============================================================

PATH_CORE = "Core"
PATH_REMEDIAL = "Remedial"

# Tier mapping: Summer Program uses Core/Remedial, not Basic/Intermediate/Advanced
# But LearningUnit.difficulty_tier still uses the old values.
# Core path → difficulty_tier per week (same as old logic)
TIER_BY_WEEK = {
    1: "Basic",
    2: "Intermediate",
}
DEFAULT_TIER = "Advanced"
REMEDIAL_TIER = "Remedial"

VALID_CONTENT_TYPES = ["VideoClass", "Quiz", "Assignment", "NoteContent", "CourseProject",
                       "TextMessageContent", "VoiceNoteContent", "ParentCallConfig"]
OPTION_LETTERS = ['A', 'B', 'C', 'D']


# ============================================================
# API 1: GET WEEKLY CONTENT
# ============================================================

@frappe.whitelist(allow_guest=False)
def get_weekly_content(student_id, course_level=None):
    """
    Get the current week's content for a Summer Program student.
    Returns the appropriate LearningUnit (Core or Remedial)
    based on the student's archetype, submission history,
    and ArchetypeConfig rules.

    Called by: Glific content_delivery flow

    Args:
        student_id: Student ID, Glific ID, or phone
        course_level: Optional. If omitted, resolved from enrollment.

    Returns:
        dict with week info, content items, path (Core/Remedial),
        expected submission type, and LearningUnit details.
    """
    student_id = _resolve_student_id(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    student = frappe.get_doc("Student", student_id)
    batch, bpr = _get_active_bpr_for_student(student)
    if not batch or not bpr:
        return {"success": False, "error": "No active Summer Program batch found"}

    if not course_level:
        course_level = _get_course_level_for_student(student, batch)
    if not course_level:
        return {"success": False, "error": "No course level found for student"}

    current_week = _get_current_week(batch)
    if current_week <= 0:
        return {"success": False, "error": "Batch has not started yet"}

    if current_week > (batch.total_weeks or 0):
        return {"success": True, "status": "program_completed", "week": current_week}

    # Determine path: Core or Remedial
    path = _resolve_path(student, batch, bpr, current_week)

    # Get the right LearningUnit
    if path == PATH_REMEDIAL:
        tier = REMEDIAL_TIER
    else:
        tier = TIER_BY_WEEK.get(current_week, DEFAULT_TIER)

    learning_unit = _get_learning_unit(course_level, current_week, tier)
    if not learning_unit:
        # Fallback: if no Remedial LU exists, serve Core
        if path == PATH_REMEDIAL:
            tier = TIER_BY_WEEK.get(current_week, DEFAULT_TIER)
            learning_unit = _get_learning_unit(course_level, current_week, tier)
            path = PATH_CORE

    if not learning_unit:
        return {"success": False, "error": f"No content found for week {current_week}"}

    # Get content items
    content_items = _get_content_items(learning_unit)

    # Get WeekRule for expected submission type
    week_rule = _get_week_rule(student, batch, current_week)

    # Update/create StudentStageProgress
    progress = _get_or_create_sp_progress(student_id, course_level, current_week, tier, learning_unit)

    return {
        "success": True,
        "student_id": student_id,
        "week": current_week,
        "path": path,
        "tier": tier,
        "learning_unit": learning_unit,
        "learning_unit_name": frappe.db.get_value("LearningUnit", learning_unit, "unit_name"),
        "content_items": content_items,
        "expected_submission_type": week_rule.get("expected_submission_type") if week_rule else None,
        "submission_validation_enabled": week_rule.get("submission_validation_enabled", 0) if week_rule else 0,
        "total_weeks": batch.total_weeks,
    }


# ============================================================
# API 2: RECORD SUBMISSION
# ============================================================

@frappe.whitelist(allow_guest=False)
def record_submission(student_id, week=None, submission_type=None, content_id=None, course_level=None):
    """
    Record an assignment submission from a student.
    Called by Glific when student sends back their assignment task
    (emoji, text, voice note, photo, video, etc.)

    This is the CORE event that drives progression in Summer Program.

    Args:
        student_id: Student ID, Glific ID, or phone
        week: Week number (if omitted, uses current batch week)
        submission_type: What the student submitted (emoji, text_word, voice_note, photo, video, etc.)
        content_id: Optional assignment/content ID
        course_level: Optional course level

    Returns:
        dict with submission result, validation status, points awarded
    """
    student_id = _resolve_student_id(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    student = frappe.get_doc("Student", student_id)
    batch, bpr = _get_active_bpr_for_student(student)
    if not batch or not bpr:
        return {"success": False, "error": "No active Summer Program batch found"}

    current_week = cint(week) or _get_current_week(batch)

    # Get WeekRule for validation
    week_rule = _get_week_rule(student, batch, current_week)
    validation_enabled = week_rule.get("submission_validation_enabled", 0) if week_rule else 0
    expected_type = week_rule.get("expected_submission_type") if week_rule else None

    # Validate submission type if validation is enabled
    is_valid = True
    if validation_enabled and expected_type and submission_type:
        is_valid = _validate_submission_type(submission_type, expected_type)

    # Calculate points from escalation step
    points = _calculate_submission_points(student, batch, bpr, current_week)

    if not course_level:
        course_level = _get_course_level_for_student(student, batch)

    # Log the submission
    _log_submission(
        student_id=student_id,
        course_level=course_level,
        week=current_week,
        submission_type=submission_type,
        content_id=content_id,
        is_valid=is_valid,
        points=points,
    )

    # Update EngagementState
    _update_engagement_state(student_id)

    # Update StudentStageProgress
    if course_level:
        _mark_week_submitted(student_id, course_level, current_week)

    # Reset escalation tracking for this student/week
    _reset_escalation(student_id, current_week)

    return {
        "success": True,
        "student_id": student_id,
        "week": current_week,
        "submission_type": submission_type,
        "is_valid": is_valid,
        "validation_enabled": bool(validation_enabled),
        "expected_type": expected_type,
        "points_awarded": points,
    }


# ============================================================
# API 3: GET ESCALATION ACTION
# ============================================================

@frappe.whitelist(allow_guest=False)
def get_escalation_action(student_id):
    """
    Get the next escalation action for a student who hasn't submitted.
    Called by the Glific escalation flow to determine what message to send.

    Returns the escalation step details (message_type, points_awarded)
    or indicates no escalation needed (student already submitted).

    Args:
        student_id: Student ID, Glific ID, or phone

    Returns:
        dict with escalation step info or skip indicator
    """
    student_id = _resolve_student_id(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    student = frappe.get_doc("Student", student_id)
    batch, bpr = _get_active_bpr_for_student(student)
    if not batch or not bpr:
        return {"success": False, "error": "No active batch"}

    current_week = _get_current_week(batch)

    # Check if student already submitted this week
    if _has_submitted_this_week(student_id, current_week):
        return {
            "success": True,
            "action": "skip",
            "reason": "already_submitted",
            "week": current_week,
        }

    # Get current escalation position
    escalation_step = _get_next_escalation_step(student, batch, current_week)

    if not escalation_step:
        return {
            "success": True,
            "action": "skip",
            "reason": "escalation_exhausted",
            "week": current_week,
        }

    # Record that this escalation step was sent
    _record_escalation_step(student_id, current_week, escalation_step)

    return {
        "success": True,
        "action": "escalate",
        "week": current_week,
        "escalation_order": escalation_step.get("escalation_order"),
        "message_type": escalation_step.get("message_type"),
        "points_if_submit_now": escalation_step.get("points_awarded", 0),
    }


# ============================================================
# API 4: GET STUDENT SP STATUS
# ============================================================

@frappe.whitelist(allow_guest=False)
def get_student_sp_overview(student_id):
    """
    Get comprehensive Summer Program status for a student.
    Called by Glific for status check flows or by admin dashboard.

    Returns:
        dict with week progress, submission history, path, archetype info
    """
    student_id = _resolve_student_id(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    student = frappe.get_doc("Student", student_id)
    batch, bpr = _get_active_bpr_for_student(student)
    if not batch:
        return {"success": False, "error": "No active batch"}

    current_week = _get_current_week(batch) if batch else 0
    total_weeks = batch.total_weeks or 0

    # Submission history per week
    submissions = _get_submission_history(student_id, total_weeks)

    # Engagement state
    engagement = frappe.db.get_value(
        "EngagementState",
        {"student": student_id},
        ["last_activity_date", "current_streak", "completion_rate"],
        as_dict=True,
    )

    # Count submitted weeks
    weeks_submitted = sum(1 for w in submissions if w.get("submitted"))

    return {
        "success": True,
        "student_id": student_id,
        "archetype": student.archetype,
        "experiment_arm": student.experiment_arm,
        "current_week": current_week,
        "total_weeks": total_weeks,
        "weeks_submitted": weeks_submitted,
        "submission_rate": round(weeks_submitted / max(current_week, 1) * 100, 1),
        "current_path": _resolve_path(student, batch, bpr, current_week) if bpr else None,
        "submissions": submissions,
        "engagement": engagement,
    }


# ============================================================
# API 5: GET NEXT CONTENT (Content Stepping)
# ============================================================

@frappe.whitelist(allow_guest=False)
def get_next_content(student_id, course_level=None):
    """
    Get next content item for a Summer Program student.
    Steps through LearningUnit items one at a time using
    current_content_index in StudentStageProgress.

    Handles:
      - Active quiz detection (resume)
      - Content stepping within a LearningUnit
      - LU completion → next LU in same week/tier
      - Week completion → next week (via _resolve_path for Core/Remedial)
      - Course completion

    Called by: Glific content delivery sub-flow (replaces flat get_weekly_content
    for step-by-step delivery).

    Args:
        student_id: Student ID, Glific ID, or phone
        course_level: Course Level name (resolved from enrollment if omitted)

    Returns:
        dict with content_available / quiz_in_progress / stage_complete /
        course_complete status plus content details.
    """
    try:
        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "error": "Student not found"}

        student = frappe.get_doc("Student", student_id)
        batch, bpr = _get_active_bpr_for_student(student)
        if not batch or not bpr:
            return {"success": False, "error": "No active Summer Program batch found"}

        if not course_level:
            course_level = _get_course_level_for_student(student, batch)
        if not course_level:
            return {"success": False, "error": "No course level found for student"}

        current_week = _get_current_week(batch)
        if current_week <= 0:
            return {"success": False, "error": "Batch has not started yet"}

        # Resolve path: Core or Remedial
        path = _resolve_path(student, batch, bpr, current_week)
        if path == PATH_REMEDIAL:
            tier = REMEDIAL_TIER
        else:
            tier = TIER_BY_WEEK.get(current_week, DEFAULT_TIER)

        # Get or create progress
        learning_unit = _get_learning_unit(course_level, current_week, tier)
        if not learning_unit and path == PATH_REMEDIAL:
            tier = TIER_BY_WEEK.get(current_week, DEFAULT_TIER)
            learning_unit = _get_learning_unit(course_level, current_week, tier)
            path = PATH_CORE

        if not learning_unit:
            return {"success": False, "error": f"No content found for week {current_week}"}

        progress = _get_or_create_sp_progress(student_id, course_level, current_week, tier, learning_unit)
        progress_data = frappe.db.get_value(
            "StudentStageProgress", progress,
            ["name", "student", "stage", "status", "current_week", "current_tier",
             "current_content_index", "is_on_remedial", "remedial_attempts",
             "active_content_type", "active_content_id", "content_started_at",
             "active_quiz_attempt", "question_started_at", "course_context"],
            as_dict=True,
        )

        # Check if course complete
        if progress_data.get("status") == "completed":
            return {
                "success": True,
                "status": "course_complete",
                "message": "You have completed the program.",
                "student_id": student_id,
            }

        # Check for active quiz
        if progress_data.get("active_quiz_attempt"):
            return {
                "success": True,
                "status": "quiz_in_progress",
                "student_id": student_id,
                "position": {
                    "week": cint(progress_data["current_week"]),
                    "tier": progress_data["current_tier"],
                    "learning_unit": progress_data["stage"],
                    "is_remedial": bool(progress_data.get("is_on_remedial")),
                    "path": path,
                },
                "content": {
                    "type": "Quiz",
                    "id": progress_data.get("active_content_id"),
                },
                "has_active_quiz": True,
                "quiz_attempt_id": progress_data["active_quiz_attempt"],
            }

        # Ensure progress points to correct LU for current week/path
        if progress_data["stage"] != learning_unit:
            frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                "stage": learning_unit,
                "current_tier": tier,
                "is_on_remedial": 1 if tier == REMEDIAL_TIER else 0,
                "current_content_index": 0,
                "last_activity_timestamp": now_datetime(),
            })
            frappe.db.commit()
            progress_data["stage"] = learning_unit
            progress_data["current_content_index"] = 0

        # Get content items for current LU
        content_items = _get_content_items(progress_data["stage"])
        current_index = cint(progress_data["current_content_index"])

        if current_index < len(content_items):
            item = content_items[current_index]
            lu_info = _get_learning_unit_info(progress_data["stage"])

            # Mark content as started
            frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                "active_content_type": item["content_type"],
                "active_content_id": item["content_id"],
                "content_started_at": now_datetime(),
                "status": "in_progress",
                "last_activity_timestamp": now_datetime(),
            })
            frappe.db.commit()

            return {
                "success": True,
                "status": "content_available",
                "student_id": student_id,
                "position": {
                    "week": cint(progress_data["current_week"]),
                    "tier": progress_data["current_tier"],
                    "learning_unit": progress_data["stage"],
                    "learning_unit_name": lu_info["name"] if lu_info else None,
                    "content_index": current_index,
                    "is_remedial": bool(progress_data.get("is_on_remedial")),
                    "path": path,
                },
                "content": {
                    "type": item["content_type"],
                    "id": item["content_id"],
                    "name": item["content_name"],
                    "order": current_index + 1,
                    "total_in_unit": len(content_items),
                    "is_optional": item.get("is_optional"),
                },
                "has_active_quiz": False,
                "course_level": course_level,
            }

        # Current LU exhausted — try next LU in same week/tier
        next_lu = _get_next_learning_unit(course_level, current_week, tier, progress_data["stage"])
        if next_lu:
            frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                "stage": next_lu,
                "current_content_index": 0,
                "status": "in_progress",
                "active_content_type": None,
                "active_content_id": None,
                "content_started_at": None,
                "last_activity_timestamp": now_datetime(),
            })
            frappe.db.commit()

            content_items = _get_content_items(next_lu)
            if content_items:
                item = content_items[0]
                lu_info = _get_learning_unit_info(next_lu)
                return {
                    "success": True,
                    "status": "content_available",
                    "student_id": student_id,
                    "position": {
                        "week": current_week,
                        "tier": tier,
                        "learning_unit": next_lu,
                        "learning_unit_name": lu_info["name"] if lu_info else None,
                        "content_index": 0,
                        "is_remedial": tier == REMEDIAL_TIER,
                        "path": path,
                    },
                    "content": {
                        "type": item["content_type"],
                        "id": item["content_id"],
                        "name": item["content_name"],
                        "order": 1,
                        "total_in_unit": len(content_items),
                        "is_optional": item.get("is_optional"),
                    },
                    "has_active_quiz": False,
                    "new_learning_unit": True,
                    "course_level": course_level,
                }

        # Week complete — check if programme finished
        total_weeks = batch.total_weeks or 0
        if current_week >= total_weeks:
            frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                "status": "completed",
                "last_activity_timestamp": now_datetime(),
            })
            frappe.db.commit()
            return {
                "success": True,
                "status": "course_complete",
                "message": "Congratulations! You have completed the program.",
                "student_id": student_id,
                "completed_week": current_week,
            }

        # Week complete but more weeks remain — signal stage_complete
        # Actual next-week content is served on the NEXT call after the
        # batch's calendar week advances and _resolve_path re-evaluates.
        return {
            "success": True,
            "status": "stage_complete",
            "message": f"Week {current_week} complete!",
            "student_id": student_id,
            "completed_week": current_week,
            "total_weeks": total_weeks,
            "course_level": course_level,
        }

    except Exception as e:
        frappe.log_error(f"get_next_content error: {str(e)}", "SP Progression API")
        return {"success": False, "error": str(e)}


# ============================================================
# API 6: GET CONTENT DETAILS
# ============================================================

@frappe.whitelist(allow_guest=False)
def get_content_details(content_type, content_id, language=None):
    """
    Get detailed information about a specific content item.
    Returns type-specific payload:
      - VideoClass: youtube_url, plio_url, video_file + translations
      - Quiz: question_count, passing_score, time_limit
      - NoteContent: content text
      - Assignment: description, assignment_type
      - CourseProject: description

    Called by: Glific after get_next_content returns a content item,
    to fetch the actual media URL or quiz config.

    Args:
        content_type: DocType name (VideoClass, Quiz, etc.)
        content_id: Document name
        language: Optional language code for translation lookup

    Returns:
        dict with type-specific content details
    """
    try:
        if not content_type or not content_id:
            return {"success": False, "error": "content_type and content_id are required"}

        if content_type not in VALID_CONTENT_TYPES:
            return {"success": False, "error": f"Invalid content_type: {content_type}"}

        if not frappe.db.exists(content_type, content_id):
            return {"success": False, "error": f"{content_type} not found: {content_id}"}

        doc = frappe.get_doc(content_type, content_id)

        if content_type == "VideoClass":
            result = {
                "success": True,
                "content_type": "VideoClass",
                "content_id": content_id,
                "name": doc.video_name,
                "youtube_url": doc.video_youtube_url,
                "plio_url": doc.video_plio_url,
                "video_file": doc.video_file,
                "url": doc.video_youtube_url or doc.video_plio_url or doc.video_file,
                "duration": str(doc.duration) if doc.duration else None,
                "description": doc.description,
                "translated": False,
            }
            if language and hasattr(doc, 'video_translations'):
                for trans in doc.video_translations:
                    if trans.language == language:
                        if trans.translated_name:
                            result["name"] = trans.translated_name
                        if trans.video_youtube_url:
                            result["youtube_url"] = trans.video_youtube_url
                            result["url"] = trans.video_youtube_url
                        result["translated"] = True
                        result["language"] = language
                        break
            return result

        elif content_type == "Quiz":
            question_count = len(doc.questions) if hasattr(doc, 'questions') else 0
            return {
                "success": True,
                "content_type": "Quiz",
                "content_id": content_id,
                "name": getattr(doc, 'quiz_name', content_id),
                "total_questions": question_count,
                "passing_score": flt(getattr(doc, 'passing_score', 60)),
                "time_limit": getattr(doc, 'time_limit', None),
            }

        elif content_type == "NoteContent":
            return {
                "success": True,
                "content_type": "NoteContent",
                "content_id": content_id,
                "name": getattr(doc, 'note_name', content_id),
                "content": getattr(doc, 'content', None),
            }

        elif content_type == "Assignment":
            return {
                "success": True,
                "content_type": "Assignment",
                "content_id": content_id,
                "name": getattr(doc, 'assignment_name', content_id),
                "description": getattr(doc, 'description', None),
                "assignment_type": getattr(doc, 'assignment_type', None),
            }

        elif content_type == "CourseProject":
            return {
                "success": True,
                "content_type": "CourseProject",
                "content_id": content_id,
                "name": getattr(doc, 'project_name', content_id),
                "description": getattr(doc, 'description', None),
            }

        # TextMessageContent, VoiceNoteContent, ParentCallConfig — minimal
        return {
            "success": True,
            "content_type": content_type,
            "content_id": content_id,
            "name": _get_content_display_name(content_type, content_id),
        }

    except Exception as e:
        frappe.log_error(f"get_content_details error: {str(e)}", "SP Progression API")
        return {"success": False, "error": str(e)}


# ============================================================
# API 7: COMPLETE CONTENT (Non-Quiz)
# ============================================================

@frappe.whitelist(allow_guest=False)
def complete_content(student_id, course_level, content_type, content_id):
    """
    Mark non-quiz content as complete and advance to next item.
    For Quiz content, use start_quiz / submit_answer instead.

    Called by: Glific after student views a video, reads a note, etc.

    Args:
        student_id: Student ID, Glific ID, or phone
        course_level: Course Level document name
        content_type: Content DocType (VideoClass, NoteContent, etc.)
        content_id: Content document name

    Returns:
        dict with next_content / next_learning_unit / week_complete /
        course_complete action and next content details.
    """
    try:
        if not all([student_id, course_level, content_type, content_id]):
            return {"success": False, "error": "All parameters required"}

        if content_type == "Quiz":
            return {"success": False, "error": "Use start_quiz and submit_answer for Quiz content"}

        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "error": "Student not found"}

        progress_data = frappe.db.get_value(
            "StudentStageProgress",
            {"student": student_id, "course_context": course_level, "stage_type": "LearningUnit"},
            ["name", "student", "stage", "current_week", "current_tier",
             "current_content_index", "is_on_remedial", "remedial_attempts",
             "content_started_at", "course_context"],
            as_dict=True,
        )

        if not progress_data:
            return {"success": False, "error": "No progress record found. Call get_next_content first."}

        # Validate content matches current position
        content_items = _get_content_items(progress_data["stage"])
        current_index = cint(progress_data["current_content_index"])

        if current_index >= len(content_items):
            return {"success": False, "error": "No content at current position"}

        current_item = content_items[current_index]
        if current_item["content_id"] != content_id:
            return {
                "success": False,
                "error": f"Content mismatch. Expected: {current_item['content_id']}, Got: {content_id}",
            }

        # Calculate time spent
        time_spent = 0
        if progress_data.get("content_started_at"):
            time_spent = cint(time_diff_in_seconds(now_datetime(), progress_data["content_started_at"]))

        # Log content completion via background job
        frappe.enqueue(
            "tap_lms.journey.background_jobs.job_log_content_completion",
            queue="short",
            timeout=60,
            student_id=student_id,
            course_level=course_level,
            progress_name=progress_data["name"],
            content_type=content_type,
            content_id=content_id,
            action="completed",
            time_spent_seconds=time_spent,
            stage_no=progress_data["current_week"],
            tier=progress_data["current_tier"],
            learning_unit=progress_data["stage"],
        )

        # Update statistics
        frappe.enqueue(
            "tap_lms.journey.background_jobs.job_update_statistics",
            queue="short",
            timeout=30,
            progress_name=progress_data["name"],
            content_completed=1,
            time_spent=time_spent,
        )

        # Advance to next content
        return _advance_to_next_content(progress_data, course_level)

    except Exception as e:
        frappe.log_error(f"complete_content error: {str(e)}", "SP Progression API")
        return {"success": False, "error": str(e)}


def _advance_to_next_content(progress_data, course_level):
    """Move to next content item within LU, or next LU, or signal week complete."""
    current_index = cint(progress_data["current_content_index"])
    new_index = current_index + 1
    content_items = _get_content_items(progress_data["stage"])

    if new_index < len(content_items):
        # More content in current LU
        frappe.db.set_value("StudentStageProgress", progress_data["name"], {
            "current_content_index": new_index,
            "status": "in_progress",
            "active_content_type": None,
            "active_content_id": None,
            "content_started_at": None,
            "last_activity_timestamp": now_datetime(),
        })
        frappe.db.commit()

        next_item = content_items[new_index]
        return {
            "success": True,
            "action": "next_content",
            "message": "Content completed!",
            "next_content": {
                "type": next_item["content_type"],
                "id": next_item["content_id"],
                "name": next_item["content_name"],
                "order": new_index + 1,
            },
            "progress": {
                "completed": new_index,
                "total": len(content_items),
                "percentage": round((new_index / len(content_items)) * 100, 1),
            },
        }

    # Current LU exhausted — try next LU in same week/tier
    current_week = cint(progress_data["current_week"])
    tier = progress_data["current_tier"]

    next_lu = _get_next_learning_unit(course_level, current_week, tier, progress_data["stage"])
    if next_lu:
        frappe.db.set_value("StudentStageProgress", progress_data["name"], {
            "stage": next_lu,
            "current_content_index": 0,
            "active_content_type": None,
            "active_content_id": None,
            "content_started_at": None,
            "last_activity_timestamp": now_datetime(),
        })
        frappe.db.commit()

        content_items = _get_content_items(next_lu)
        first_content = content_items[0] if content_items else None
        lu_info = _get_learning_unit_info(next_lu)

        return {
            "success": True,
            "action": "next_learning_unit",
            "message": "Learning Unit completed!",
            "new_learning_unit": next_lu,
            "new_learning_unit_name": lu_info["name"] if lu_info else None,
            "next_content": {
                "type": first_content["content_type"],
                "id": first_content["content_id"],
                "name": first_content["content_name"],
                "order": 1,
            } if first_content else None,
        }

    # Week complete
    return {
        "success": True,
        "action": "week_complete",
        "message": f"Week {current_week} content complete!",
        "completed_week": current_week,
    }


# ============================================================
# API 8: START QUIZ
# ============================================================

@frappe.whitelist(allow_guest=False)
def start_quiz(student_id, course_level, quiz_id, language=None):
    """
    Begin a quiz attempt or resume an existing in-progress attempt.
    Returns the first (or current) question with options A/B/C/D.

    Called by: Glific quiz sub-flow after get_next_content returns
    a Quiz content item.

    Args:
        student_id: Student ID, Glific ID, or phone
        course_level: Course Level document name
        quiz_id: Quiz document name
        language: Optional language code for question translations

    Returns:
        dict with quiz_started / quiz_resumed status, quiz_attempt_id,
        and first question details.
    """
    try:
        if not all([student_id, course_level, quiz_id]):
            return {"success": False, "error": "student_id, course_level, and quiz_id required"}

        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "error": "Student not found"}

        if not frappe.db.exists("Quiz", quiz_id):
            return {"success": False, "error": f"Quiz not found: {quiz_id}"}

        progress_data = frappe.db.get_value(
            "StudentStageProgress",
            {"student": student_id, "course_context": course_level, "stage_type": "LearningUnit"},
            ["name", "stage", "current_week", "current_tier", "current_content_index",
             "is_on_remedial", "active_quiz_attempt"],
            as_dict=True,
        )

        if not progress_data:
            return {"success": False, "error": "No progress record. Call get_next_content first."}

        # Resume existing in-progress attempt
        if progress_data.get("active_quiz_attempt"):
            attempt = frappe.get_doc("StudentQuizAttempt", progress_data["active_quiz_attempt"])
            if attempt.quiz == quiz_id and attempt.status == "in_progress":
                return _resume_quiz(attempt, progress_data, language)

        # Create new attempt
        quiz_doc = frappe.get_doc("Quiz", quiz_id)
        questions = _get_quiz_questions(quiz_doc)
        if not questions:
            return {"success": False, "error": "Quiz has no questions"}

        prev_attempts = frappe.db.count("StudentQuizAttempt", {
            "student": student_id, "quiz": quiz_id, "course_level": course_level,
        })

        attempt = frappe.get_doc({
            "doctype": "StudentQuizAttempt",
            "student": student_id,
            "course_level": course_level,
            "student_progress": progress_data["name"],
            "quiz": quiz_id,
            "quiz_name": getattr(quiz_doc, 'quiz_name', quiz_id),
            "stage_no": progress_data["current_week"],
            "tier": progress_data["current_tier"],
            "attempt_number": prev_attempts + 1,
            "status": "in_progress",
            "total_questions": len(questions),
            "current_question_index": 0,
            "question_started_at": now_datetime(),
            "started_at": now_datetime(),
            "passing_score": flt(getattr(quiz_doc, 'passing_score', 60)),
            "score": 0,
            "correct_answers": 0,
            "passed": 0,
            "answers": [],
        })
        attempt.insert(ignore_permissions=True)
        frappe.db.commit()

        # Update progress
        frappe.db.set_value("StudentStageProgress", progress_data["name"], {
            "active_quiz_attempt": attempt.name,
            "active_content_type": "Quiz",
            "active_content_id": quiz_id,
            "content_started_at": now_datetime(),
            "question_started_at": now_datetime(),
            "last_activity_timestamp": now_datetime(),
        })
        frappe.db.commit()

        first_q = _get_question_details(questions[0].question, language)
        return {
            "success": True,
            "status": "quiz_started",
            "message": "Quiz started! Good luck!",
            "quiz_attempt_id": attempt.name,
            "quiz_name": attempt.quiz_name,
            "total_questions": len(questions),
            "passing_score": attempt.passing_score,
            "question": {
                "index": 1,
                "id": questions[0].question,
                "text": first_q.get("question"),
                "type": first_q.get("question_type", "Multiple Choice"),
                "options": {
                    "A": first_q.get("option_a"),
                    "B": first_q.get("option_b"),
                    "C": first_q.get("option_c"),
                    "D": first_q.get("option_d"),
                },
                "correct_option": first_q.get("correct_option"),
            },
        }

    except Exception as e:
        frappe.log_error(f"start_quiz error: {str(e)}", "SP Progression API")
        return {"success": False, "error": str(e)}


def _resume_quiz(attempt, progress_data, language=None):
    """Resume an in-progress quiz attempt."""
    quiz_doc = frappe.get_doc("Quiz", attempt.quiz)
    questions = _get_quiz_questions(quiz_doc)

    answered_indices = {cint(a.question_index) for a in attempt.answers}
    next_index = 1
    for i in range(1, len(questions) + 1):
        if i not in answered_indices:
            next_index = i
            break

    frappe.db.set_value("StudentStageProgress", progress_data["name"], {
        "question_started_at": now_datetime(),
        "last_activity_timestamp": now_datetime(),
    })
    attempt.question_started_at = now_datetime()
    attempt.save(ignore_permissions=True)
    frappe.db.commit()

    q_row = questions[next_index - 1]
    q_details = _get_question_details(q_row.question, language)
    correct_so_far = sum(1 for a in attempt.answers if a.is_correct)

    return {
        "success": True,
        "status": "quiz_resumed",
        "message": f"Welcome back! Continuing from question {next_index}.",
        "quiz_attempt_id": attempt.name,
        "quiz_name": attempt.quiz_name,
        "total_questions": attempt.total_questions,
        "questions_answered": len(attempt.answers),
        "correct_so_far": correct_so_far,
        "question": {
            "index": next_index,
            "id": q_row.question,
            "text": q_details.get("question"),
            "type": q_details.get("question_type", "Multiple Choice"),
            "options": {
                "A": q_details.get("option_a"),
                "B": q_details.get("option_b"),
                "C": q_details.get("option_c"),
                "D": q_details.get("option_d"),
            },
            "correct_option": q_details.get("correct_option"),
        },
    }


# ============================================================
# API 9: SUBMIT ANSWER
# ============================================================

@frappe.whitelist(allow_guest=False)
def submit_answer(student_id, quiz_attempt_id, question_index, answer, language=None):
    """
    Submit an answer for the current quiz question.

    On the last question, automatically completes the quiz and returns
    pass/fail result. Server-side time tracking per question.

    KEY DESIGN CHANGE vs old system:
      - Core quiz FAIL → advance to next content (no remedial switch)
      - Remedial quiz FAIL → restart or continue remedial LU
      - Remedial quiz PASS → advance (exit remedial for next week)
    Remedial path is driven by assignment submission, not quiz score.

    Args:
        student_id: Student ID, Glific ID, or phone
        quiz_attempt_id: StudentQuizAttempt document name
        question_index: 1-based question number
        answer: Selected option letter (A, B, C, or D)
        language: Optional language code for next question translation

    Returns:
        dict with answer_result + next_question or quiz_passed/quiz_failed
    """
    try:
        if not all([student_id, quiz_attempt_id, question_index, answer]):
            return {"success": False, "error": "All parameters required"}

        question_index = cint(question_index)
        answer = answer.strip().upper()
        if answer not in OPTION_LETTERS:
            return {"success": False, "error": "Invalid answer. Must be A, B, C, or D"}

        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "error": "Student not found"}

        if not frappe.db.exists("StudentQuizAttempt", quiz_attempt_id):
            return {"success": False, "error": f"Quiz attempt not found: {quiz_attempt_id}"}

        attempt = frappe.get_doc("StudentQuizAttempt", quiz_attempt_id)
        if attempt.student != student_id:
            return {"success": False, "error": "Attempt does not belong to this student"}
        if attempt.status != "in_progress":
            return {"success": False, "error": "Quiz attempt is not in progress"}
        if question_index < 1 or question_index > attempt.total_questions:
            return {"success": False, "error": f"Invalid question_index. Must be 1-{attempt.total_questions}"}

        quiz_doc = frappe.get_doc("Quiz", attempt.quiz)
        questions = _get_quiz_questions(quiz_doc)
        q_row = questions[question_index - 1]

        q_details = _get_question_details(q_row.question)
        correct_option = q_details.get("correct_option", "A")
        is_correct = (answer == correct_option)

        started_at = attempt.question_started_at or attempt.started_at
        answered_at = now_datetime()
        time_spent = cint(time_diff_in_seconds(answered_at, started_at))

        # Save answer (update or append)
        existing_answer = None
        for ans in attempt.answers:
            if cint(ans.question_index) == question_index:
                existing_answer = ans
                break

        if existing_answer:
            existing_answer.selected_option = answer
            existing_answer.correct_option = correct_option
            existing_answer.is_correct = 1 if is_correct else 0
            existing_answer.started_at = started_at
            existing_answer.answered_at = answered_at
            existing_answer.time_spent_seconds = time_spent
        else:
            attempt.append("answers", {
                "question_index": question_index,
                "question": q_row.question,
                "selected_option": answer,
                "correct_option": correct_option,
                "is_correct": 1 if is_correct else 0,
                "started_at": started_at,
                "answered_at": answered_at,
                "time_spent_seconds": time_spent,
            })

        attempt.current_question_index = question_index
        attempt.correct_answers = sum(1 for a in attempt.answers if a.is_correct)

        # Last question → complete quiz
        if question_index >= attempt.total_questions:
            return _complete_quiz_sp(attempt, quiz_doc, questions, language)

        # More questions — save and return next
        attempt.question_started_at = now_datetime()
        attempt.save(ignore_permissions=True)
        frappe.db.commit()

        progress_name = attempt.student_progress
        if progress_name:
            frappe.db.set_value("StudentStageProgress", progress_name, {
                "question_started_at": now_datetime(),
                "last_activity_timestamp": now_datetime(),
            })
            frappe.db.commit()

        next_q_row = questions[question_index]  # 0-based → next question
        next_q = _get_question_details(next_q_row.question, language)

        return {
            "success": True,
            "action": "next_question",
            "answer_result": {
                "question_index": question_index,
                "selected_answer": answer,
                "correct_answer": correct_option,
                "was_correct": is_correct,
                "time_spent_seconds": time_spent,
            },
            "progress": {
                "answered": question_index,
                "total": attempt.total_questions,
                "correct": attempt.correct_answers,
                "percentage": round((question_index / attempt.total_questions) * 100, 1),
            },
            "question": {
                "index": question_index + 1,
                "id": next_q_row.question,
                "text": next_q.get("question"),
                "type": next_q.get("question_type", "Multiple Choice"),
                "options": {
                    "A": next_q.get("option_a"),
                    "B": next_q.get("option_b"),
                    "C": next_q.get("option_c"),
                    "D": next_q.get("option_d"),
                },
                "correct_option": next_q.get("correct_option"),
            },
        }

    except Exception as e:
        frappe.log_error(f"submit_answer error: {str(e)}", "SP Progression API")
        return {"success": False, "error": str(e)}


def _complete_quiz_sp(attempt, quiz_doc, questions, language=None):
    """
    Complete quiz attempt and determine next action.

    KEY DIFFERENCE from old system:
      - Core quiz fail → advance to next content (NOT switch to remedial)
      - Remedial quiz fail → restart/continue remedial LU
      - Remedial quiz pass → advance (exit remedial)
    """
    correct_count = sum(1 for a in attempt.answers if a.is_correct)
    total = attempt.total_questions
    score = (correct_count / total * 100) if total > 0 else 0
    passed = score >= flt(attempt.passing_score)

    total_time = cint(time_diff_in_seconds(now_datetime(), attempt.started_at))

    # Finalize attempt
    attempt.status = "completed"
    attempt.completed_at = now_datetime()
    attempt.score = score
    attempt.correct_answers = correct_count
    attempt.passed = 1 if passed else 0
    attempt.time_spent_seconds = total_time
    attempt.save(ignore_permissions=True)
    frappe.db.commit()

    # Get progress
    progress_data = frappe.db.get_value(
        "StudentStageProgress", attempt.student_progress,
        ["name", "student", "stage", "current_week", "current_tier",
         "is_on_remedial", "remedial_attempts", "current_content_index", "course_context"],
        as_dict=True,
    )

    course_level = progress_data["course_context"]

    # Clear quiz state
    frappe.db.set_value("StudentStageProgress", progress_data["name"], {
        "active_quiz_attempt": None,
        "active_content_type": None,
        "active_content_id": None,
        "content_started_at": None,
        "question_started_at": None,
        "last_activity_timestamp": now_datetime(),
    })
    frappe.db.commit()

    # Background jobs
    frappe.enqueue(
        "tap_lms.journey.background_jobs.job_log_content_completion",
        queue="short", timeout=60,
        student_id=progress_data["student"],
        course_level=course_level,
        progress_name=progress_data["name"],
        content_type="Quiz",
        content_id=attempt.quiz,
        action="completed" if passed else "failed",
        score=score, max_score=100, passed=passed,
        time_spent_seconds=total_time,
        quiz_attempt=attempt.name,
        stage_no=progress_data["current_week"],
        tier=progress_data["current_tier"],
        learning_unit=progress_data["stage"],
    )
    frappe.enqueue(
        "tap_lms.journey.background_jobs.job_update_statistics",
        queue="short", timeout=30,
        progress_name=progress_data["name"],
        content_completed=1,
        quiz_passed=1 if passed else 0,
        quiz_failed=0 if passed else 1,
        time_spent=total_time,
    )

    # Build base response
    last_ans = attempt.answers[-1] if attempt.answers else None
    response = {
        "success": True,
        "action": "quiz_passed" if passed else "quiz_failed",
        "answer_result": {
            "question_index": attempt.total_questions,
            "selected_answer": last_ans.selected_option if last_ans else None,
            "correct_answer": last_ans.correct_option if last_ans else None,
            "was_correct": bool(last_ans.is_correct) if last_ans else False,
            "time_spent_seconds": last_ans.time_spent_seconds if last_ans else 0,
        },
        "quiz_result": {
            "score": round(score, 1),
            "correct": correct_count,
            "total": total,
            "passed": passed,
            "passing_score": attempt.passing_score,
            "time_spent_seconds": total_time,
        },
    }

    # Progression based on pass/fail
    is_remedial = bool(progress_data.get("is_on_remedial"))

    if passed:
        if is_remedial:
            # Remedial quiz pass → week complete (exit remedial)
            response.update({
                "next_action": "week_complete",
                "message": "Great job! Week complete!",
                "completed_week": progress_data["current_week"],
            })
        else:
            # Core quiz pass → advance to next content
            next_action = _advance_to_next_content(progress_data, course_level)
            next_action.pop("success", None)
            response["next_action"] = next_action.pop("action", "next_content")
            response.update(next_action)
    else:
        if is_remedial:
            # Remedial quiz fail → restart or continue remedial LU
            content_items = _get_content_items(progress_data["stage"])
            current_index = cint(progress_data["current_content_index"])

            if current_index < len(content_items) - 1:
                new_index = current_index + 1
                frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                    "current_content_index": new_index,
                    "last_activity_timestamp": now_datetime(),
                })
                frappe.db.commit()
                next_content = content_items[new_index]
                response.update({
                    "next_action": "continue_remedial",
                    "message": "Keep practicing! Continue with next content.",
                    "next_content": {
                        "type": next_content["content_type"],
                        "id": next_content["content_id"],
                        "name": next_content["content_name"],
                    },
                })
            else:
                remedial_attempts = cint(progress_data.get("remedial_attempts", 0)) + 1
                frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                    "current_content_index": 0,
                    "remedial_attempts": remedial_attempts,
                    "last_activity_timestamp": now_datetime(),
                })
                frappe.db.commit()
                first_content = content_items[0] if content_items else None
                response.update({
                    "next_action": "restart_remedial",
                    "message": "Let's review from the beginning.",
                    "remedial_attempt": remedial_attempts,
                    "next_content": {
                        "type": first_content["content_type"],
                        "id": first_content["content_id"],
                        "name": first_content["content_name"],
                    } if first_content else None,
                })
        else:
            # Core quiz fail → advance to next content (NOT switch to remedial)
            # Remedial routing is driven by assignment submission, not quiz score.
            next_action = _advance_to_next_content(progress_data, course_level)
            next_action.pop("success", None)
            response["next_action"] = next_action.pop("action", "next_content")
            response["message"] = "Quiz complete. Let's continue with the next content."
            response.update(next_action)

    return response


# ============================================================
# CORE LOGIC: PATH RESOLUTION
# ============================================================

def _resolve_path(student, batch, bpr, current_week):
    """
    Determine whether a student should be on Core or Remedial path
    for the current week.

    Logic:
      1. Look up ArchetypeConfig for this student's batch + archetype + arm
      2. Check the student's submission history for PREVIOUS weeks
      3. If student missed submissions (per ArchetypeConfig rules) → Remedial
      4. Otherwise → Core

    For week 1, everyone starts on Core (no prior history to evaluate).
    """
    if current_week <= 1:
        return PATH_CORE

    archetype = student.archetype or "Submitter"
    arm = student.experiment_arm or "default"

    # Check if student submitted LAST week
    prev_week = current_week - 1
    submitted_last_week = _has_submitted_week(student.name, prev_week)

    if submitted_last_week:
        return PATH_CORE

    # Student didn't submit last week — check ArchetypeConfig
    # for whether this archetype goes to Remedial
    config = _get_archetype_config(batch.name, arm, archetype, PATH_REMEDIAL)
    if config:
        # Remedial config exists for this archetype → route to Remedial
        return PATH_REMEDIAL

    # No Remedial config → stay on Core even without submission
    return PATH_CORE


# ============================================================
# ARCHETYPE CONFIG HELPERS
# ============================================================

def _get_archetype_config(batch_name, arm, archetype, path):
    """
    Fetch ArchetypeConfig for a specific combination.
    Uses Redis cache to avoid repeated DB lookups.

    Args:
        batch_name: Batch document name
        arm: experiment arm (default, arm_a, arm_b)
        archetype: student archetype
        path: Core or Remedial

    Returns:
        ArchetypeConfig document or None
    """
    cache_key = f"archetype_config:{batch_name}:{arm}:{archetype}:{path}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    config_name = frappe.db.get_value(
        "ArchetypeConfig",
        {
            "batch": batch_name,
            "experiment_arm": arm,
            "archetype": archetype,
            "path": path,
            "is_active": 1,
        },
        "name",
    )

    if not config_name:
        # Try with 'default' arm as fallback
        if arm != "default":
            config_name = frappe.db.get_value(
                "ArchetypeConfig",
                {
                    "batch": batch_name,
                    "experiment_arm": "default",
                    "archetype": archetype,
                    "path": path,
                    "is_active": 1,
                },
                "name",
            )

    if not config_name:
        return None

    config = frappe.get_doc("ArchetypeConfig", config_name)
    # Cache for 5 minutes
    frappe.cache().set_value(cache_key, config, expires_in_sec=300)
    return config


def _get_week_rule(student, batch, week):
    """
    Get the WeekRule for a student's archetype/arm/week.
    Determines expected submission type and whether validation is on.
    """
    archetype = student.archetype or "Submitter"
    arm = student.experiment_arm or "default"

    # Try Core config first (Core has the week rules for content delivery)
    config = _get_archetype_config(batch.name, arm, archetype, PATH_CORE)
    if not config:
        return None

    for rule in config.week_rules:
        if cint(rule.week) == cint(week):
            return {
                "week": rule.week,
                "expected_submission_type": rule.expected_submission_type,
                "submission_validation_enabled": rule.submission_validation_enabled,
            }

    return None


def _get_escalation_steps(student, batch):
    """
    Get escalation steps from ArchetypeConfig for this student.
    """
    archetype = student.archetype or "Submitter"
    arm = student.experiment_arm or "default"

    config = _get_archetype_config(batch.name, arm, archetype, PATH_CORE)
    if not config or not config.escalation_steps:
        return []

    steps = []
    for step in config.escalation_steps:
        if step.is_active:
            steps.append({
                "escalation_order": step.escalation_order,
                "message_type": step.message_type,
                "points_awarded": step.points_awarded or 0,
                "hours_after_previous": step.hours_after_previous or 24,
            })

    return sorted(steps, key=lambda s: s["escalation_order"])


# ============================================================
# SUBMISSION TRACKING
# ============================================================

def _has_submitted_this_week(student_id, current_week):
    """Check if student has submitted for the current week."""
    return _has_submitted_week(student_id, current_week)


def _has_submitted_week(student_id, week):
    """Check if student has a submission logged for a specific week."""
    return frappe.db.exists("StudentContentLog", {
        "student": student_id,
        "stage_no": week,
        "content_type": "Assignment",
        "action": "completed",
    })


def _get_submission_history(student_id, total_weeks):
    """Get per-week submission status."""
    submissions = []
    for w in range(1, total_weeks + 1):
        log = frappe.db.get_value(
            "StudentContentLog",
            {
                "student": student_id,
                "stage_no": w,
                "content_type": "Assignment",
                "action": "completed",
            },
            ["completed_at", "content_id", "score", "metadata"],
            as_dict=True,
        )
        submissions.append({
            "week": w,
            "submitted": bool(log),
            "completed_at": str(log.completed_at) if log and log.completed_at else None,
            "content_id": log.content_id if log else None,
        })

    return submissions


def _log_submission(student_id, course_level, week, submission_type, content_id, is_valid, points):
    """Log a submission to StudentContentLog."""
    log = frappe.new_doc("StudentContentLog")
    log.student = student_id
    log.course_level = course_level
    log.stage_no = week
    log.content_type = "Assignment"
    log.content_id = content_id or f"sp_week_{week}_submission"
    log.content_name = f"Week {week} Submission"
    log.action = "completed"
    log.started_at = now_datetime()
    log.completed_at = today()
    log.tier = "Core"  # We record submission regardless of path
    log.metadata = json.dumps({
        "submission_type": submission_type,
        "is_valid": is_valid,
        "points_awarded": points,
        "source": "summer_program",
    })
    log.insert(ignore_permissions=True)
    frappe.db.commit()


def _validate_submission_type(actual_type, expected_type):
    """
    Check if the actual submission matches the expected type.
    Some types are compatible (e.g., photo_video_artefact accepts both photo and video).
    """
    if not actual_type or not expected_type:
        return True

    actual = actual_type.lower().strip()
    expected = expected_type.lower().strip()

    if actual == expected:
        return True

    # Compatibility rules
    compatible = {
        "photo_video_artefact": ["photo", "video"],
        "voice_note_text_summary": ["voice_note", "text_word"],
    }

    accepted = compatible.get(expected, [])
    return actual in accepted


# ============================================================
# ESCALATION TRACKING
# ============================================================

def _get_next_escalation_step(student, batch, current_week):
    """
    Determine the next escalation step for a student who hasn't submitted.
    Checks how many escalation steps have already been sent this week.
    """
    steps = _get_escalation_steps(student, batch)
    if not steps:
        return None

    # Count escalations already sent this week
    sent_count = frappe.db.count("StudentContentLog", {
        "student": student.name,
        "stage_no": current_week,
        "action": "started",  # We use 'started' action for escalation logs
        "content_type": "Assignment",
        "tier": "Escalation",
    })

    if sent_count >= len(steps):
        return None  # All steps exhausted

    return steps[sent_count]  # Return next unsent step


def _record_escalation_step(student_id, week, step):
    """Record that an escalation step was sent."""
    log = frappe.new_doc("StudentContentLog")
    log.student = student_id
    log.stage_no = week
    log.content_type = "Assignment"
    log.content_id = f"escalation_step_{step['escalation_order']}"
    log.content_name = f"Escalation: {step['message_type']}"
    log.action = "started"  # 'started' = escalation sent, 'completed' = submission received
    log.tier = "Escalation"
    log.started_at = now_datetime()
    log.metadata = json.dumps({
        "escalation_order": step["escalation_order"],
        "message_type": step["message_type"],
        "points_if_submit": step.get("points_awarded", 0),
        "source": "summer_program",
    })
    log.insert(ignore_permissions=True)
    frappe.db.commit()


def _reset_escalation(student_id, week):
    """
    When a student submits, mark escalation as resolved.
    We don't delete the escalation logs — they're useful for analytics.
    """
    # No destructive action needed. The _has_submitted_this_week check
    # will prevent further escalation. Escalation logs remain for reporting.
    pass


def _calculate_submission_points(student, batch, bpr, current_week):
    """
    Calculate points for a submission based on which escalation step
    the student is at. Earlier submission = more points.

    Points come from EscalationStep.points_awarded.
    If student submits before any escalation, they get max points.
    """
    steps = _get_escalation_steps(student, batch)
    if not steps:
        return 0

    # How many escalations were sent before this submission?
    sent_count = frappe.db.count("StudentContentLog", {
        "student": student.name,
        "stage_no": current_week,
        "action": "started",
        "content_type": "Assignment",
        "tier": "Escalation",
    })

    if sent_count == 0:
        # Submitted before any escalation → highest points
        # Use points from step 1 (the max)
        return steps[0].get("points_awarded", 0) if steps else 0

    if sent_count <= len(steps):
        # Get points for current step (decreasing)
        return steps[sent_count - 1].get("points_awarded", 0)

    return 0


# ============================================================
# ENGAGEMENT STATE
# ============================================================

def _update_engagement_state(student_id):
    """
    Update EngagementState when student submits.
    Sets last_activity_date, updates streak, completion rate.
    """
    try:
        es = frappe.db.get_value(
            "EngagementState",
            {"student": student_id},
            ["name", "last_activity_date", "current_streak", "completion_rate"],
            as_dict=True,
        )

        today_date = getdate(today())

        if es:
            updates = {
                "last_activity_date": today_date,
                "last_updated": now_datetime(),
            }

            # Update streak
            last = es.last_activity_date
            if last:
                if isinstance(last, str):
                    last = getdate(last)
                days_diff = (today_date - last).days
                if days_diff == 1:
                    updates["current_streak"] = (es.current_streak or 0) + 1
                elif days_diff > 1:
                    updates["current_streak"] = 1
                # days_diff == 0: same day, no streak change
            else:
                updates["current_streak"] = 1

            frappe.db.set_value("EngagementState", es.name, updates)
        else:
            # Create EngagementState if it doesn't exist
            new_es = frappe.new_doc("EngagementState")
            new_es.student = student_id
            new_es.last_activity_date = today_date
            new_es.current_streak = 1
            new_es.completion_rate = "0"
            new_es.last_updated = now_datetime()
            new_es.insert(ignore_permissions=True)

        frappe.db.commit()

    except Exception as e:
        frappe.log_error(
            f"Error updating EngagementState for {student_id}: {str(e)}",
            "SP EngagementState Update",
        )


# ============================================================
# CONTENT RESOLUTION
# ============================================================

def _get_learning_unit(course_level, week, tier):
    """
    Get the LearningUnit for a specific week and tier from Course Level.
    """
    result = frappe.db.sql("""
        SELECT lul.learning_unit
        FROM `tabLearningUnitList` lul
        INNER JOIN `tabLearningUnit` lu ON lu.name = lul.learning_unit
        WHERE lul.parent = %s
          AND lul.parenttype = 'Course Level'
          AND lul.week_no = %s
          AND lu.difficulty_tier = %s
        ORDER BY lul.idx ASC
        LIMIT 1
    """, (course_level, week, tier), as_dict=True)

    return result[0].learning_unit if result else None


def _get_content_items(learning_unit):
    """Get content items for a learning unit."""
    items = frappe.get_all(
        "UnitContentItem",
        filters={"parent": learning_unit, "parenttype": "LearningUnit"},
        fields=["idx", "content_type", "content", "is_optional"],
        order_by="idx asc",
    )

    result = []
    for item in items:
        name = _get_content_display_name(item.content_type, item.content)
        result.append({
            "index": item.idx,
            "content_type": item.content_type,
            "content_id": item.content,
            "content_name": name,
            "is_optional": item.is_optional,
        })

    return result


def _get_content_display_name(content_type, content_id):
    """Get display name for content."""
    field_map = {
        "VideoClass": "video_name",
        "Quiz": "quiz_name",
        "Assignment": "assignment_name",
        "NoteContent": "note_name",
        "CourseProject": "project_name",
    }
    field = field_map.get(content_type, "name")
    try:
        return frappe.db.get_value(content_type, content_id, field) or content_id
    except Exception:
        return content_id


def _get_next_learning_unit(course_level, week_no, tier, after_lu):
    """Get next LU after current one in same week/tier."""
    current_idx = frappe.db.get_value(
        "LearningUnitList",
        {"parent": course_level, "parenttype": "Course Level", "learning_unit": after_lu},
        "idx"
    )
    if not current_idx:
        return None

    result = frappe.db.sql("""
        SELECT lul.learning_unit
        FROM `tabLearningUnitList` lul
        INNER JOIN `tabLearningUnit` lu ON lu.name = lul.learning_unit
        WHERE lul.parent = %s
          AND lul.parenttype = 'Course Level'
          AND lul.week_no = %s
          AND lu.difficulty_tier = %s
          AND lul.idx > %s
        ORDER BY lul.idx ASC
        LIMIT 1
    """, (course_level, week_no, tier, current_idx), as_dict=True)
    return result[0].learning_unit if result else None


def _check_week_exists(course_level, week_no):
    """Check if a week exists in course level."""
    return frappe.db.exists("LearningUnitList", {
        "parent": course_level, "parenttype": "Course Level", "week_no": week_no
    })


def _get_learning_unit_info(learning_unit):
    """Get LU display info."""
    if not learning_unit:
        return None
    try:
        lu = frappe.get_doc("LearningUnit", learning_unit)
        return {"id": learning_unit, "name": getattr(lu, 'unit_name', learning_unit)}
    except Exception:
        return {"id": learning_unit, "name": learning_unit}


def _get_quiz_questions(quiz_doc):
    """Get ordered list of quiz questions."""
    if not hasattr(quiz_doc, 'questions') or not quiz_doc.questions:
        return []
    questions = list(quiz_doc.questions)
    questions.sort(key=lambda q: getattr(q, 'question_number', q.idx))
    return questions


def _get_question_details(question_id, language=None):
    """Get question details with translation support."""
    try:
        from frappe.utils import strip_html_tags

        q = frappe.get_doc("QuizQuestion", question_id)
        question_text = q.question or getattr(q, 'question_name', '') or ""

        if language and hasattr(q, 'question_translations') and q.question_translations:
            for trans in q.question_translations:
                if trans.language == language and trans.translated_question:
                    question_text = trans.translated_question
                    break

        question_text = strip_html_tags(question_text) if question_text else ""

        options = {"option_a": "", "option_b": "", "option_c": "", "option_d": ""}
        if hasattr(q, 'options') and q.options:
            for i, opt_row in enumerate(q.options[:4]):
                letter = OPTION_LETTERS[i].lower()
                option_id = opt_row.options
                if option_id:
                    option_text = frappe.db.get_value("QuizOption", option_id, "option_text") or ""
                    options[f"option_{letter}"] = strip_html_tags(option_text) if option_text else ""

        correct_num = cint(q.correct_option)
        correct_letter = OPTION_LETTERS[correct_num - 1] if 1 <= correct_num <= 4 else "A"

        return {
            "question_id": question_id,
            "question": question_text,
            "question_type": getattr(q, 'question_type', 'Multiple Choice'),
            "option_a": options["option_a"],
            "option_b": options["option_b"],
            "option_c": options["option_c"],
            "option_d": options["option_d"],
            "correct_option": correct_letter,
        }
    except Exception as e:
        frappe.log_error(f"_get_question_details error for {question_id}: {str(e)}")
        return {"question_id": question_id, "error": str(e)}


# ============================================================
# STUDENT & BATCH RESOLUTION
# ============================================================

def _resolve_student_id(student_identifier):
    """Resolve various student identifiers to Student name."""
    if not student_identifier:
        return None

    # Direct match
    if frappe.db.exists("Student", student_identifier):
        return student_identifier

    # Try Glific ID
    student = frappe.db.get_value("Student", {"glific_id": student_identifier}, "name")
    if student:
        return student

    # Try phone number
    phone = str(student_identifier).strip().replace(" ", "")
    student = frappe.db.get_value("Student", {"phone": phone}, "name")
    return student


def _get_active_bpr_for_student(student):
    """
    Find the active BatchProgramRun and Batch for a student.
    Looks through student's enrollments to find a batch with
    an active BPR.
    """
    if not student.enrollment:
        return None, None

    for enrollment in student.enrollment:
        if not enrollment.batch:
            continue

        batch = frappe.get_doc("Batch", enrollment.batch)
        if batch.program_type != "Summer":
            continue

        bpr = frappe.db.get_value(
            "BatchProgramRun",
            {"batch": enrollment.batch, "status": BPR_ACTIVE},
            "name",
        )
        if bpr:
            return batch, frappe.get_doc("BatchProgramRun", bpr)

    return None, None


def _get_course_level_for_student(student, batch):
    """
    Get the course level for a student's enrollment in a batch.
    """
    if not student.enrollment:
        return None

    for enrollment in student.enrollment:
        if enrollment.batch == batch.name and enrollment.course:
            # Get Course Level from Course + Grade
            course_level = frappe.db.get_value(
                "Course Level",
                {"course": enrollment.course, "grade": student.grade},
                "name",
            )
            if course_level:
                return course_level

            # Fallback: any course level for this course
            course_level = frappe.db.get_value(
                "Course Level",
                {"course": enrollment.course},
                "name",
            )
            return course_level

    return None


def _get_current_week(batch):
    """Calculate current week from batch start_date."""
    if not batch.start_date:
        return 0
    days = date_diff(today(), batch.start_date)
    if days < 0:
        return 0
    return (days // 7) + 1


# ============================================================
# PROGRESS TRACKING
# ============================================================

def _get_or_create_sp_progress(student_id, course_level, week, tier, learning_unit):
    """
    Get or create a StudentStageProgress record for Summer Program.
    """
    progress = frappe.db.get_value(
        "StudentStageProgress",
        {
            "student": student_id,
            "course_context": course_level,
            "stage_type": "LearningUnit",
        },
        ["name", "current_week", "current_tier", "is_on_remedial"],
        as_dict=True,
    )

    if progress:
        # Update to current week if needed
        if cint(progress.current_week) != cint(week):
            frappe.db.set_value("StudentStageProgress", progress.name, {
                "current_week": week,
                "current_tier": tier,
                "stage": learning_unit,
                "is_on_remedial": 1 if tier == REMEDIAL_TIER else 0,
                "last_activity_timestamp": now_datetime(),
            })
            frappe.db.commit()
        return progress.name

    # Create new
    doc = frappe.get_doc({
        "doctype": "StudentStageProgress",
        "student": student_id,
        "stage_type": "LearningUnit",
        "stage": learning_unit,
        "course_context": course_level,
        "status": "assigned",
        "current_week": week,
        "current_tier": tier,
        "current_content_index": 0,
        "is_on_remedial": 1 if tier == REMEDIAL_TIER else 0,
        "remedial_attempts": 0,
        "start_timestamp": now_datetime(),
        "total_content_completed": 0,
        "total_quizzes_passed": 0,
        "total_quizzes_failed": 0,
        "total_time_spent_seconds": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _mark_week_submitted(student_id, course_level, week):
    """Mark the current week as submitted in StudentStageProgress."""
    progress_name = frappe.db.get_value(
        "StudentStageProgress",
        {
            "student": student_id,
            "course_context": course_level,
            "stage_type": "LearningUnit",
        },
        "name",
    )

    if progress_name:
        frappe.db.set_value("StudentStageProgress", progress_name, {
            "status": "completed",
            "last_activity_timestamp": now_datetime(),
            "total_content_completed": frappe.db.get_value(
                "StudentStageProgress", progress_name, "total_content_completed"
            ) + 1,
        })
        frappe.db.commit()
