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
    date_diff, get_datetime,
    add_days, add_to_date,
)

from tap_lms.summer_program.custom_messages import EXPECTED_SUBMISSION_LABELS
from tap_lms.summer_program.state_machine import get_active_pe
from tap_lms.summer_program.utils import glific_response, resolve_student


def _time_diff_in_seconds(dt1, dt2):
    """Return the difference (dt1 - dt2) in seconds."""
    return (get_datetime(dt1) - get_datetime(dt2)).total_seconds()

from tap_lms.summer_program.constants import (
    ALL_ARCHETYPES,
    ALL_ARMS,
    BPR_ACTIVE,
    PATH_CORE,
    PATH_REMEDIAL,
    TIER_BY_WEEK,
    DEFAULT_TIER,
    REMEDIAL_TIER,
)


# ============================================================
# CONSTANTS (local to this module)
# ============================================================

VALID_CONTENT_TYPES = ["VideoClass", "Quiz", "Assignment", "NoteContent", "CourseProject",
                       "TextMessageContent", "VoiceNoteContent", "ParentCallConfig"]
OPTION_LETTERS = ['A', 'B', 'C', 'D']

# Grace time: hours into a new week during which a student can still submit
# for the previous week without being blocked. Default 24 hours.
SUBMISSION_GRACE_HOURS = 24


# ============================================================
# API 1: GET WEEKLY CONTENT
# ============================================================

@frappe.whitelist(allow_guest=False)
@glific_response
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
        return {"success": False, "status": "not_found",
                "error_detail": "Student not found"}

    student = frappe.get_doc("Student", student_id)
    batch, bpr = _get_active_bpr_for_student(student)
    if not batch or not bpr:
        return {"success": False, "status": "no_active_batch",
                "error_detail": "No active Summer Program batch found"}

    if not course_level:
        course_level = _get_course_level_for_student(student, batch)
    if not course_level:
        return {"success": False, "status": "no_course_level",
                "error_detail": "No course level found for student"}

    current_week = _get_current_week(batch)
    if current_week <= 0:
        return {"success": False, "status": "batch_not_started",
                "error_detail": "Batch has not started yet"}

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
        return {"success": False, "status": "no_content_for_week",
                "error_detail": f"No content found for week {current_week}"}

    # Get content items
    content_items = _get_content_items(learning_unit)

    # Get WeekRule for expected submission type
    week_rule = _get_week_rule(student, batch, current_week)

    # Update/create StudentStageProgress (side-effect, return value unused here)
    _get_or_create_sp_progress(student_id, course_level, current_week, tier, learning_unit)

    # Flatten content_items[] to numeric-suffix scalars per
    # docs/api-standard-glific.md Rule 3. Cap at 10 — log + truncate if exceeded.
    CONTENT_CAP = 10
    if len(content_items) > CONTENT_CAP:
        frappe.log_error(
            f"get_weekly_content: learning_unit {learning_unit} has "
            f"{len(content_items)} content items; truncating to {CONTENT_CAP}. "
            f"Increase the cap or split the LU.",
            "SP API contract",
        )
        content_items = content_items[:CONTENT_CAP]

    response = {
        "success": True,
        "status": "content_available",
        "student_id": student_id,
        "week": current_week,
        "path": path,
        "tier": tier,
        "learning_unit": learning_unit,
        "learning_unit_name": frappe.db.get_value("LearningUnit", learning_unit, "unit_name"),
        "expected_submission_type": (week_rule.get("expected_submission_type") if week_rule else None),
        "submission_validation_enabled": (week_rule.get("submission_validation_enabled", 0) if week_rule else 0),
        "total_weeks": batch.total_weeks,
        "content_count": len(content_items),
    }
    for i, item in enumerate(content_items, start=1):
        response[f"content_{i}_type"] = item.get("content_type")
        response[f"content_{i}_id"] = item.get("content_id")
        response[f"content_{i}_name"] = item.get("content_name")
        response[f"content_{i}_is_optional"] = bool(item.get("is_optional"))
    return response


# ════════════════════════════════════════════════════════════
# REMOVED: record_submission, get_escalation_action, get_student_sp_overview
# ════════════════════════════════════════════════════════════
# Three legacy whitelisted endpoints removed on 2026-05-11:
#
#   - record_submission        → superseded by `save_submission` (does strictly
#                                more: state machine T3/T7/T22, atomic primary
#                                claim, idempotency, AI feedback pipeline,
#                                GCS upload, state-aware terminal/paused guard)
#   - get_escalation_action    → superseded by the per-PE dispatcher (#15) +
#                                state_machine T1/T2/T4 + escalation_runner cron
#   - get_student_sp_overview  → superseded by `get_student_state` (in
#                                program_enrollment_api.py) + admin dashboard
#                                APIs in summer_program.api
#
# Verified zero callers across the codebase before deletion (grep against
# app/tap_lms turned up only the function definitions themselves). All three
# were missing from the Glific reference doc (`docs/glific-api-reference-v1.md`),
# and the live SP enrollment + submission flow does not depend on them.
#
# If any external caller (Glific flow, dashboard, ad-hoc API consumer) still
# hits these paths, they will now get a 404. That's intentional — we'd rather
# fail loud than silently accept submissions that don't transition state.
#
# Some helpers (_log_submission, _validate_submission_type, _reset_escalation,
# _get_next_escalation_step, _record_escalation_step, _has_submitted_this_week,
# _get_submission_history) MAY now be orphaned. Audit + remove in a follow-up.


# ============================================================
# API 5: GET NEXT CONTENT (Content Stepping)
# ============================================================

@frappe.whitelist(allow_guest=False)
@glific_response
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
    # ASSESSMENT_CAP — must match get_content_details for consistency.
    # `assessment_<i>_id` is CRITICAL — it's the assignment_id Glific passes
    # to save_submission. Do NOT drop these.
    ASSESSMENT_CAP = 5

    def _flat_content_response(item, content_index, total_in_unit, position_kwargs,
                                new_learning_unit=False):
        """Build the flat content_available response (helper to avoid
        duplicating the same flat-shape logic across the two LU variants)."""
        assessments = _get_video_assessments(item["content_type"], item["content_id"]) or []
        if len(assessments) > ASSESSMENT_CAP:
            frappe.log_error(
                f"{item['content_type']} {item['content_id']} has "
                f"{len(assessments)} assessments; truncating to {ASSESSMENT_CAP}.",
                "SP API contract",
            )
            assessments = assessments[:ASSESSMENT_CAP]

        resp = {
            "success": True,
            "status": "content_available",
            "student_id": student_id,
            "has_active_quiz": False,
            "new_learning_unit": new_learning_unit,
            "course_level": course_level,
            # position.* flattened
            "position_week": position_kwargs["week"],
            "position_tier": position_kwargs["tier"],
            "position_learning_unit": position_kwargs["learning_unit"],
            "position_learning_unit_name": position_kwargs.get("learning_unit_name"),
            "position_content_index": content_index,
            "position_is_remedial": position_kwargs["is_remedial"],
            "position_path": position_kwargs["path"],
            # content.* flattened
            "content_type": item["content_type"],
            "content_id": item["content_id"],
            "content_name": item["content_name"],
            "content_order": content_index + 1,
            "content_total_in_unit": total_in_unit,
            "content_is_optional": bool(item.get("is_optional")),
            # assessments[] flattened — assessment_<i>_id is the assignment_id
            # input to save_submission. Critical path.
            "assessment_count": len(assessments),
        }
        for i, a in enumerate(assessments, start=1):
            resp[f"assessment_{i}_type"] = a.get("assessment_type")
            resp[f"assessment_{i}_id"] = a.get("assessment_id")
        return resp

    try:
        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "status": "not_found",
                    "error_detail": "Student not found"}

        student = frappe.get_doc("Student", student_id)
        batch, bpr = _get_active_bpr_for_student(student)
        if not batch or not bpr:
            return {"success": False, "status": "no_active_batch",
                    "error_detail": "No active Summer Program batch found"}

        if not course_level:
            course_level = _get_course_level_for_student(student, batch)
        if not course_level:
            return {"success": False, "status": "no_course_level",
                    "error_detail": "No course level found for student"}

        calendar_week = _get_current_week(batch)
        if calendar_week <= 0:
            return {"success": False, "status": "batch_not_started",
                    "error_detail": "Batch has not started yet"}

        # Determine effective week: student may be ahead of or behind calendar
        current_week = _get_effective_week(student, batch, calendar_week)

        # Check content blocking: if student didn't submit previous week,
        # they can't access current week content (escalation handles follow-up).
        if current_week > 1:
            prev_submission = _get_submission_validity(student.name, current_week - 1)
            if not prev_submission["submitted"]:
                if not _is_within_grace_period(batch, current_week):
                    return {
                        "success": True,
                        "status": "content_blocked",
                        "user_message": f"Please complete your Week {current_week - 1} submission first.",
                        "student_id": student_id,
                        "blocked_reason": "missing_previous_submission",
                        "pending_week": current_week - 1,
                        "calendar_week": calendar_week,
                    }

        # Resolve path: Core or Remedial
        path = _resolve_path(student, batch, bpr, current_week)
        if path == PATH_REMEDIAL:
            tier = REMEDIAL_TIER
        else:
            tier = TIER_BY_WEEK.get(current_week, DEFAULT_TIER)

        learning_unit = _get_learning_unit(course_level, current_week, tier)
        if not learning_unit and path == PATH_REMEDIAL:
            tier = TIER_BY_WEEK.get(current_week, DEFAULT_TIER)
            learning_unit = _get_learning_unit(course_level, current_week, tier)
            path = PATH_CORE

        if not learning_unit:
            return {"success": False, "status": "no_content_for_week",
                    "error_detail": f"No content found for week {current_week}"}

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
                "user_message": "You have completed the program.",
                "student_id": student_id,
            }

        # Check for active quiz — flat shape per Rules 2 + 3.
        if progress_data.get("active_quiz_attempt"):
            return {
                "success": True,
                "status": "quiz_in_progress",
                "student_id": student_id,
                "has_active_quiz": True,
                "quiz_attempt_id": progress_data["active_quiz_attempt"],
                "position_week": cint(progress_data["current_week"]),
                "position_tier": progress_data["current_tier"],
                "position_learning_unit": progress_data["stage"],
                "position_is_remedial": bool(progress_data.get("is_on_remedial")),
                "position_path": path,
                "content_type": "Quiz",
                "content_id": progress_data.get("active_content_id"),
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
            # Removed mid-handler commit per L-017 — Frappe commits at request-end.
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
            # Removed mid-handler commit per L-017 — Frappe commits at request-end.

            return _flat_content_response(
                item=item,
                content_index=current_index,
                total_in_unit=len(content_items),
                position_kwargs={
                    "week": cint(progress_data["current_week"]),
                    "tier": progress_data["current_tier"],
                    "learning_unit": progress_data["stage"],
                    "learning_unit_name": lu_info["name"] if lu_info else None,
                    "is_remedial": bool(progress_data.get("is_on_remedial")),
                    "path": path,
                },
            )

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
            # Removed mid-handler commit per L-017 — Frappe commits at request-end.

            content_items = _get_content_items(next_lu)
            if content_items:
                item = content_items[0]
                lu_info = _get_learning_unit_info(next_lu)
                return _flat_content_response(
                    item=item,
                    content_index=0,
                    total_in_unit=len(content_items),
                    position_kwargs={
                        "week": current_week,
                        "tier": tier,
                        "learning_unit": next_lu,
                        "learning_unit_name": lu_info["name"] if lu_info else None,
                        "is_remedial": tier == REMEDIAL_TIER,
                        "path": path,
                    },
                    new_learning_unit=True,
                )

        # Week complete — check if programme finished
        total_weeks = batch.total_weeks or 0
        if current_week >= total_weeks:
            frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                "status": "completed",
                "last_activity_timestamp": now_datetime(),
            })
            # Removed mid-handler commit per L-017 — Frappe commits at request-end.
            return {
                "success": True,
                "status": "course_complete",
                "user_message": "Congratulations! You have completed the program.",
                "student_id": student_id,
                "completed_week": current_week,
            }

        # Week complete but more weeks remain — see comments inline.
        this_week_submitted = _has_submitted_week(student.name, current_week)
        next_week = current_week + 1
        max_allowed_week = min(calendar_week + 1, total_weeks)

        if this_week_submitted and next_week <= max_allowed_week:
            frappe.db.set_value("StudentStageProgress", progress_data["name"], {
                "current_week": next_week,
                "current_content_index": 0,
                "active_content_type": None,
                "active_content_id": None,
                "content_started_at": None,
                "last_activity_timestamp": now_datetime(),
            })
            # Removed mid-handler commit per L-017 — Frappe commits at request-end.
            return {
                "success": True,
                "status": "stage_complete",
                "user_message": f"Week {current_week} complete! Moving to Week {next_week}.",
                "student_id": student_id,
                "completed_week": current_week,
                "next_week": next_week,
                "can_advance": True,
                "total_weeks": total_weeks,
                "course_level": course_level,
            }

        if this_week_submitted and next_week > max_allowed_week:
            return {
                "success": True,
                "status": "stage_complete",
                "user_message": f"Week {current_week} complete! New content will be available in Week {next_week}.",
                "student_id": student_id,
                "completed_week": current_week,
                "can_advance": False,
                "paused": True,
                "paused_reason": "ahead_of_calendar",
                "next_week": next_week,
                "calendar_week": calendar_week,
                "total_weeks": total_weeks,
                "course_level": course_level,
            }

        # Student hasn't submitted yet
        return {
            "success": True,
            "status": "stage_complete",
            "user_message": f"Week {current_week} complete! Submit your assignment to continue.",
            "student_id": student_id,
            "completed_week": current_week,
            "can_advance": False,
            "needs_submission": True,
            "total_weeks": total_weeks,
            "course_level": course_level,
        }

    except Exception as e:
        frappe.log_error(f"get_next_content error: {str(e)}", "SP Progression API")
        return {"success": False, "status": "error", "error_detail": str(e)}


# ============================================================
# API 6: GET CONTENT DETAILS
# ============================================================

@frappe.whitelist(allow_guest=False)
@glific_response
def get_content_details(content_type, content_id, language=None, student_id=None):
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
        student_id: Optional student identifier. When provided for VideoClass,
            includes unguided submission text fields for the student's active
            enrollment.

    Returns:
        dict with type-specific content details
    """
    try:
        if not content_type or not content_id:
            return {"success": False, "status": "invalid_input",
                    "error_detail": "content_type and content_id are required"}

        if content_type not in VALID_CONTENT_TYPES:
            return {"success": False, "status": "invalid_content_type",
                    "error_detail": f"Invalid content_type: {content_type}"}

        if not frappe.db.exists(content_type, content_id):
            return {"success": False, "status": "not_found",
                    "error_detail": f"{content_type} not found: {content_id}"}

        doc = frappe.get_doc(content_type, content_id)

        if content_type == "VideoClass":
            # Flatten `assessments` array using numeric-suffix expansion per
            # docs/api-standard-glific.md Rule 3. `assessment_<i>_id` is CRITICAL —
            # it's the assignment_id that Glific passes to save_submission when
            # the student submits after watching the video. Do NOT drop this.
            # Cap at 5 (videos typically have 1 assessment, max 2-3).
            assessments = _get_video_assessments("VideoClass", content_id) or []
            ASSESSMENT_CAP = 5
            if len(assessments) > ASSESSMENT_CAP:
                frappe.log_error(
                    f"VideoClass {content_id} has {len(assessments)} assessments; "
                    f"truncating to {ASSESSMENT_CAP}.",
                    "SP API contract",
                )
                assessments = assessments[:ASSESSMENT_CAP]

            result = {
                "success": True,
                "status": "video_class",
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
                "language": "",
                "assessment_count": len(assessments),
            }
            for i, a in enumerate(assessments, start=1):
                result[f"assessment_{i}_type"] = a.get("assessment_type")
                result[f"assessment_{i}_id"] = a.get("assessment_id")
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
            if student_id:
                unguided = _get_video_unguided_submission_message(
                    student_id, assessments, language
                )
                result["unguided_text"] = unguided.get("unguided_text")
                result["unguided_text_url"] = unguided.get("unguided_text_url")
            return result

        elif content_type == "Quiz":
            question_count = len(doc.questions) if hasattr(doc, 'questions') else 0
            return {
                "success": True,
                "status": "quiz",
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
                "status": "note_content",
                "content_type": "NoteContent",
                "content_id": content_id,
                "name": getattr(doc, 'note_name', content_id),
                "content": getattr(doc, 'content', None),
            }

        elif content_type == "Assignment":
            return {
                "success": True,
                "status": "assignment",
                "content_type": "Assignment",
                "content_id": content_id,
                "name": getattr(doc, 'assignment_name', content_id),
                "description": getattr(doc, 'description', None),
                "assignment_type": getattr(doc, 'assignment_type', None),
            }

        elif content_type == "CourseProject":
            return {
                "success": True,
                "status": "course_project",
                "content_type": "CourseProject",
                "content_id": content_id,
                "name": getattr(doc, 'project_name', content_id),
                "description": getattr(doc, 'description', None),
            }

        # TextMessageContent, VoiceNoteContent, ParentCallConfig — minimal
        return {
            "success": True,
            "status": "generic_content",
            "content_type": content_type,
            "content_id": content_id,
            "name": _get_content_display_name(content_type, content_id),
        }

    except Exception as e:
        frappe.log_error(f"get_content_details error: {str(e)}", "SP Progression API")
        return {"success": False, "status": "error", "error_detail": str(e)}


# ============================================================
# API 7: COMPLETE CONTENT (Non-Quiz)
# ============================================================

@frappe.whitelist(allow_guest=False)
@glific_response
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
            return {"success": False, "status": "invalid_input",
                    "error_detail": "All parameters required"}

        if content_type == "Quiz":
            return {"success": False, "status": "wrong_endpoint",
                    "error_detail": "Use start_quiz and submit_answer for Quiz content"}

        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "status": "not_found",
                    "error_detail": "Student not found"}

        progress_data = frappe.db.get_value(
            "StudentStageProgress",
            {"student": student_id, "course_context": course_level, "stage_type": "LearningUnit"},
            ["name", "student", "stage", "current_week", "current_tier",
             "current_content_index", "is_on_remedial", "remedial_attempts",
             "content_started_at", "course_context"],
            as_dict=True,
        )

        if not progress_data:
            return {"success": False, "status": "no_progress",
                    "error_detail": "No progress record found. Call get_next_content first."}

        # Validate content matches current position
        content_items = _get_content_items(progress_data["stage"])
        current_index = cint(progress_data["current_content_index"])

        if current_index >= len(content_items):
            return {"success": False, "status": "no_content_at_position",
                    "error_detail": "No content at current position"}

        current_item = content_items[current_index]
        if current_item["content_id"] != content_id:
            return {
                "success": False,
                "status": "content_mismatch",
                "error_detail": f"Content mismatch. Expected: {current_item['content_id']}, Got: {content_id}",
            }

        # Calculate time spent
        time_spent = 0
        if progress_data.get("content_started_at"):
            time_spent = cint(_time_diff_in_seconds(now_datetime(), progress_data["content_started_at"]))

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
        return {"success": False, "status": "error", "error_detail": str(e)}


def _advance_to_next_content(progress_data, course_level):
    """Move to next content item within LU, or next LU, or signal week complete.

    Returns a flat dict per docs/api-standard-glific.md (Rules 2 + 3):
      - status: "next_content" | "next_learning_unit" | "week_complete"
      - next-content fields flattened to next_content_type / next_content_id /
        next_content_name / next_content_order (no nested object)
      - progress fields flattened to progress_completed / progress_total /
        progress_percentage
    """
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
        # Removed mid-handler commit per L-017 — Frappe commits at request-end.

        next_item = content_items[new_index]
        return {
            "success": True,
            "status": "next_content",
            "user_message": "Content completed!",
            "next_content_type": next_item["content_type"],
            "next_content_id": next_item["content_id"],
            "next_content_name": next_item["content_name"],
            "next_content_order": new_index + 1,
            "progress_completed": new_index,
            "progress_total": len(content_items),
            "progress_percentage": round((new_index / len(content_items)) * 100, 1),
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
        # Removed mid-handler commit per L-017 — Frappe commits at request-end.

        content_items = _get_content_items(next_lu)
        first_content = content_items[0] if content_items else None
        lu_info = _get_learning_unit_info(next_lu)

        return {
            "success": True,
            "status": "next_learning_unit",
            "user_message": "Learning Unit completed!",
            "new_learning_unit": next_lu,
            "new_learning_unit_name": lu_info["name"] if lu_info else None,
            "next_content_type": first_content["content_type"] if first_content else None,
            "next_content_id": first_content["content_id"] if first_content else None,
            "next_content_name": first_content["content_name"] if first_content else None,
            "next_content_order": 1 if first_content else 0,
        }

    # Week complete
    return {
        "success": True,
        "status": "week_complete",
        "user_message": f"Week {current_week} content complete!",
        "completed_week": current_week,
    }


# ============================================================
# API 8: START QUIZ
# ============================================================

@frappe.whitelist(allow_guest=False)
@glific_response
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
            return {"success": False, "status": "invalid_input",
                    "error_detail": "student_id, course_level, and quiz_id required"}

        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "status": "not_found",
                    "error_detail": "Student not found"}

        if not frappe.db.exists("Quiz", quiz_id):
            return {"success": False, "status": "quiz_not_found",
                    "error_detail": f"Quiz not found: {quiz_id}"}

        progress_data = frappe.db.get_value(
            "StudentStageProgress",
            {"student": student_id, "course_context": course_level, "stage_type": "LearningUnit"},
            ["name", "stage", "current_week", "current_tier", "current_content_index",
             "is_on_remedial", "active_quiz_attempt"],
            as_dict=True,
        )

        if not progress_data:
            return {"success": False, "status": "no_progress",
                    "error_detail": "No progress record. Call get_next_content first."}

        # Resume existing in-progress attempt
        if progress_data.get("active_quiz_attempt"):
            attempt = frappe.get_doc("StudentQuizAttempt", progress_data["active_quiz_attempt"])
            if attempt.quiz == quiz_id and attempt.status == "in_progress":
                return _resume_quiz(attempt, progress_data, language)

        # Create new attempt
        quiz_doc = frappe.get_doc("Quiz", quiz_id)
        questions = _get_quiz_questions(quiz_doc)
        if not questions:
            return {"success": False, "status": "empty_quiz",
                    "error_detail": "Quiz has no questions"}

        prev_attempts = frappe.db.count("StudentQuizAttempt", {
            "student": student_id, "quiz": quiz_id, "course_level": course_level,
        })

        attempt = frappe.get_doc({
            "doctype": "StudentQuizAttempt",
            "student": student_id,
            "course_level": course_level,
            "student_progress": progress_data["name"],
            "quiz": quiz_id,
            "quizname": getattr(quiz_doc, 'quiz_name', quiz_id),
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
        # Removed mid-handler commit per L-017 — Frappe commits at request-end.

        # Update progress
        frappe.db.set_value("StudentStageProgress", progress_data["name"], {
            "active_quiz_attempt": attempt.name,
            "active_content_type": "Quiz",
            "active_content_id": quiz_id,
            "content_started_at": now_datetime(),
            "question_started_at": now_datetime(),
            "last_activity_timestamp": now_datetime(),
        })
        # Removed mid-handler commit per L-017 — Frappe commits at request-end.

        first_q = _get_question_details(questions[0].question, language)
        # Flat shape per docs/api-standard-glific.md (Rules 2 + 3): no nested
        # question/options objects. Glific reads `question_text`, `option_a`,
        # etc. directly. Question is at index 1 (1-based).
        return {
            "success": True,
            "status": "quiz_started",
            "user_message": "Quiz started! Good luck!",
            "quiz_attempt_id": attempt.name,
            "quiz_name": attempt.quizname,
            "total_questions": len(questions),
            "passing_score": attempt.passing_score,
            "question_index": 1,
            "question_id": questions[0].question,
            "question_text": first_q.get("question"),
            "question_type": first_q.get("question_type", "Multiple Choice"),
            "option_a": first_q.get("option_a"),
            "option_b": first_q.get("option_b"),
            "option_c": first_q.get("option_c"),
            "option_d": first_q.get("option_d"),
            "correct_option": first_q.get("correct_option"),
        }

    except Exception as e:
        frappe.log_error(f"start_quiz error: {str(e)}", "SP Progression API")
        return {"success": False, "status": "error", "error_detail": str(e)}


def _resume_quiz(attempt, progress_data, language=None):
    """Resume an in-progress quiz attempt."""
    quiz_doc = frappe.get_doc("Quiz", attempt.quiz)
    questions = _get_quiz_questions(quiz_doc)

    answered_indices = {cint(a.question_index) for a in attempt.answers}
    next_index = None
    for i in range(1, len(questions) + 1):
        if i not in answered_indices:
            next_index = i
            break

    # All questions already answered — complete the quiz instead of re-serving
    if next_index is None:
        return _complete_quiz_sp(attempt, quiz_doc, questions, language)

    frappe.db.set_value("StudentStageProgress", progress_data["name"], {
        "question_started_at": now_datetime(),
        "last_activity_timestamp": now_datetime(),
    })
    attempt.question_started_at = now_datetime()
    attempt.save(ignore_permissions=True)
    # Removed mid-handler commit per L-017 — Frappe commits at request-end.

    q_row = questions[next_index - 1]
    q_details = _get_question_details(q_row.question, language)
    correct_so_far = sum(1 for a in attempt.answers if a.is_correct)

    # Flat shape per docs/api-standard-glific.md (Rules 2 + 3).
    return {
        "success": True,
        "status": "quiz_resumed",
        "user_message": f"Welcome back! Continuing from question {next_index}.",
        "quiz_attempt_id": attempt.name,
        "quiz_name": attempt.quizname,
        "total_questions": attempt.total_questions,
        "questions_answered": len(attempt.answers),
        "correct_so_far": correct_so_far,
        "question_index": next_index,
        "question_id": q_row.question,
        "question_text": q_details.get("question"),
        "question_type": q_details.get("question_type", "Multiple Choice"),
        "option_a": q_details.get("option_a"),
        "option_b": q_details.get("option_b"),
        "option_c": q_details.get("option_c"),
        "option_d": q_details.get("option_d"),
        "correct_option": q_details.get("correct_option"),
    }


# ============================================================
# API 9: SUBMIT ANSWER
# ============================================================

@frappe.whitelist(allow_guest=False)
@glific_response
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
            return {"success": False, "status": "invalid_input",
                    "error_detail": "All parameters required"}

        question_index = cint(question_index)
        answer = answer.strip().upper()
        if answer not in OPTION_LETTERS:
            return {"success": False, "status": "invalid_answer",
                    "error_detail": "Invalid answer. Must be A, B, C, or D"}

        student_id = _resolve_student_id(student_id)
        if not student_id:
            return {"success": False, "status": "not_found",
                    "error_detail": "Student not found"}

        if not frappe.db.exists("StudentQuizAttempt", quiz_attempt_id):
            return {"success": False, "status": "attempt_not_found",
                    "error_detail": f"Quiz attempt not found: {quiz_attempt_id}"}

        attempt = frappe.get_doc("StudentQuizAttempt", quiz_attempt_id)
        if attempt.student != student_id:
            return {"success": False, "status": "wrong_student",
                    "error_detail": "Attempt does not belong to this student"}
        if attempt.status != "in_progress":
            return {"success": False, "status": "attempt_not_in_progress",
                    "error_detail": "Quiz attempt is not in progress"}
        if question_index < 1 or question_index > attempt.total_questions:
            return {"success": False, "status": "invalid_question_index",
                    "error_detail": f"Invalid question_index. Must be 1-{attempt.total_questions}"}

        quiz_doc = frappe.get_doc("Quiz", attempt.quiz)
        questions = _get_quiz_questions(quiz_doc)
        q_row = questions[question_index - 1]

        q_details = _get_question_details(q_row.question)
        correct_option = q_details.get("correct_option", "A")
        is_correct = (answer == correct_option)

        started_at = attempt.question_started_at or attempt.started_at
        answered_at = now_datetime()
        time_spent = cint(_time_diff_in_seconds(answered_at, started_at))

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
        # Removed mid-handler commit per L-017 — Frappe commits at request-end.

        progress_name = attempt.student_progress
        if progress_name:
            frappe.db.set_value("StudentStageProgress", progress_name, {
                "question_started_at": now_datetime(),
                "last_activity_timestamp": now_datetime(),
            })
            # Removed mid-handler commit per L-017 — Frappe commits at request-end.

        next_q_row = questions[question_index]  # 0-based → next question
        next_q = _get_question_details(next_q_row.question, language)

        # Flat shape per docs/api-standard-glific.md (Rules 2 + 3):
        #   - answer_result.* → answered_question_*, was_correct, time_spent_seconds
        #   - progress.* → progress_answered, progress_total, progress_correct, progress_percentage
        #   - question.* + nested options.* → question_*, option_a..option_d
        return {
            "success": True,
            "status": "next_question",
            "answered_question_index": question_index,
            "selected_answer": answer,
            "correct_answer": correct_option,
            "was_correct": is_correct,
            "time_spent_seconds": time_spent,
            "progress_answered": question_index,
            "progress_total": attempt.total_questions,
            "progress_correct": attempt.correct_answers,
            "progress_percentage": round((question_index / attempt.total_questions) * 100, 1),
            "question_index": question_index + 1,
            "question_id": next_q_row.question,
            "question_text": next_q.get("question"),
            "question_type": next_q.get("question_type", "Multiple Choice"),
            "option_a": next_q.get("option_a"),
            "option_b": next_q.get("option_b"),
            "option_c": next_q.get("option_c"),
            "option_d": next_q.get("option_d"),
            "correct_option": next_q.get("correct_option"),
        }

    except Exception as e:
        frappe.log_error(f"submit_answer error: {str(e)}", "SP Progression API")
        return {"success": False, "status": "error", "error_detail": str(e)}


def _complete_quiz_sp(attempt, quiz_doc, questions, language=None):
    """
    Complete quiz attempt and determine next action.

    Quiz behavior is the SAME on both Core and Remedial paths:
      - Quiz pass or fail → advance to next content item
      - If no more content → week_complete
    Quiz results do NOT affect path routing. Only assignment submission
    (valid vs invalid type) determines Core/Remedial for the next week.
    """
    correct_count = sum(1 for a in attempt.answers if a.is_correct)
    total = attempt.total_questions
    score = (correct_count / total * 100) if total > 0 else 0
    passed = score >= flt(attempt.passing_score)

    total_time = cint(_time_diff_in_seconds(now_datetime(), attempt.started_at))

    # Finalize attempt
    attempt.status = "completed"
    attempt.completed_at = now_datetime()
    attempt.score = score
    attempt.correct_answers = correct_count
    attempt.passed = 1 if passed else 0
    attempt.time_spent_seconds = total_time
    attempt.save(ignore_permissions=True)
    # Removed mid-handler commit per L-017 — Frappe commits at request-end.

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
    # Removed mid-handler commit per L-017 — Frappe commits at request-end.

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

    # Build base response — flat per docs/api-standard-glific.md (Rules 2 + 3).
    # Note: removed boolean `quiz_passed` field that previously collided with
    # the `status` enum value ("quiz_passed" / "quiz_failed"). The status enum
    # already conveys pass/fail unambiguously; flows read it via Split-by-Expression.
    last_ans = attempt.answers[-1] if attempt.answers else None
    response = {
        "success": True,
        "status": "quiz_passed" if passed else "quiz_failed",
        "user_message": "Great job! Quiz passed!" if passed
                        else "Quiz complete. Let's continue with the next content.",
        # answer_result.* flattened
        "answered_question_index": attempt.total_questions,
        "selected_answer": last_ans.selected_option if last_ans else None,
        "correct_answer": last_ans.correct_option if last_ans else None,
        "was_correct": bool(last_ans.is_correct) if last_ans else False,
        "time_spent_seconds": last_ans.time_spent_seconds if last_ans else 0,
        # quiz_result.* flattened with quiz_ prefix to avoid colliding with
        # next-content fields injected below
        "quiz_score": round(score, 1),
        "quiz_correct": correct_count,
        "quiz_total": total,
        "quiz_passing_score": attempt.passing_score,
        "quiz_time_spent_seconds": total_time,
    }

    # Progression: same for both Core and Remedial paths.
    # Quiz pass/fail → advance to next content or week_complete.
    # Path routing (Core vs Remedial) is determined solely by assignment
    # submission validity, not quiz results.
    #
    # _advance_to_next_content returns a flat dict with `status` and
    # next-content fields. Merge into our response, but our outer `status`
    # ("quiz_passed" / "quiz_failed") and `user_message` win — Glific reads
    # those for the quiz outcome and reads `next_action_status` for what to
    # do next (the merged child's status enum). The renamed key avoids the
    # confusion of a "next_action" key holding what is actually a status string.
    next_action = _advance_to_next_content(progress_data, course_level)
    next_action.pop("success", None)
    response["next_action_status"] = next_action.pop("status", "next_content")
    next_action.pop("user_message", None)  # quiz outcome msg wins over next-content msg
    response.update(next_action)

    return response


# ============================================================
# CORE LOGIC: PATH RESOLUTION
# ============================================================

def _resolve_path(student, batch, bpr, current_week):
    """
    Determine whether a student should be on Core or Remedial path
    for the current week.

    Path resolution is based on SUBMISSION TYPE VALIDITY, not presence:
      - No submission at all → Core path (escalation flow handles follow-up,
        content is blocked via get_next_content until they submit)
      - Submitted with VALID type → Core path
      - Submitted with WRONG/INVALID type → Remedial path

    For week 1, everyone starts on Core (no prior history to evaluate).
    """
    if current_week <= 1:
        return PATH_CORE

    archetype = student.archetype or "submitter"
    arm = student.experiment_arm or "default"

    # Check previous week's submission status AND validity
    prev_week = current_week - 1
    submission = _get_submission_validity(student.name, prev_week)

    if not submission["submitted"]:
        # No submission → stay on Core (escalation flow + content blocking
        # handle follow-up; Remedial is NOT triggered by missing submission)
        return PATH_CORE

    if submission["is_valid"]:
        # Valid submission type → Core
        return PATH_CORE

    # Invalid submission type (wrong type) → check if Remedial config exists
    config = _get_archetype_config(batch.name, arm, archetype, PATH_REMEDIAL)
    if config:
        return PATH_REMEDIAL

    # No Remedial config for this archetype → stay on Core
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
    # Cache for 1 hour. ArchetypeConfig is essentially static admin-controlled
    # configuration (escalation timings, archetype rules per batch/arm/path).
    # At 100K students × per-tick dispatcher reads, the 5-minute TTL that was
    # here originally caused ~12x more DB hits than necessary for data that
    # rarely changes. Trade-off: after an admin edits an ArchetypeConfig row,
    # workers may use stale config for up to 1 hour. If that becomes a problem,
    # add an on_update hook on ArchetypeConfig that invalidates the cache key
    # for the affected (batch, arm, archetype, path) combination.
    frappe.cache().set_value(cache_key, config, expires_in_sec=3600)
    return config


def _get_week_rule(student, batch, week):
    """
    Get the WeekRule for a student's archetype/arm/week.
    Determines expected submission type and whether validation is on.
    """
    archetype = student.archetype or "submitter"
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

    CR-003: step dicts now carry `escalation_type` (Select:
    help_note_a/help_note_b/voice_note/parent_call) instead of the previous
    `message_type` Data field. Glific reads `escalation_type` via the
    contact field pushed by the dispatcher to pick its per-channel branch
    in SP_Escalation. `parent_call` steps are routed by the dispatcher
    through `summer_program/vocallabs.py` and skip Glific entirely.
    """
    archetype = student.archetype or "submitter"
    arm = student.experiment_arm or "default"

    config = _get_archetype_config(batch.name, arm, archetype, PATH_CORE)
    if not config or not config.escalation_steps:
        return []

    steps = []
    for step in config.escalation_steps:
        if step.is_active:
            steps.append({
                "escalation_order": step.escalation_order,
                "escalation_type": step.escalation_type or "help_note_a",
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


def _get_submission_validity(student_id, week):
    """
    Check a student's submission status and validity for a specific week.

    Returns:
        dict with:
          - submitted (bool): whether any submission exists
          - is_valid (bool or None): True if valid, False if invalid, None if no submission
    """
    log = frappe.db.get_value(
        "StudentContentLog",
        {
            "student": student_id,
            "stage_no": week,
            "content_type": "Assignment",
            "action": "completed",
        },
        ["metadata"],
        as_dict=True,
    )

    if not log:
        return {"submitted": False, "is_valid": None}

    # Parse metadata to get is_valid flag
    is_valid = True  # default if metadata missing
    if log.metadata:
        try:
            meta = json.loads(log.metadata)
            is_valid = meta.get("is_valid", True)
        except (json.JSONDecodeError, TypeError):
            pass

    return {"submitted": True, "is_valid": is_valid}


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
    # CR-003: step shape now uses `escalation_type` (Select) not `message_type` (Data).
    log.content_name = f"Escalation: {step.get('escalation_type', 'help_note_a')}"
    log.action = "started"  # 'started' = escalation sent, 'completed' = submission received
    log.tier = "Escalation"
    log.started_at = now_datetime()
    log.metadata = json.dumps({
        "escalation_order": step["escalation_order"],
        "escalation_type": step.get("escalation_type", "help_note_a"),
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


def _get_video_assessments(content_type, content_id):
    """If content is a VideoClass, return its linked assessments (type + id)."""
    if content_type != "VideoClass":
        return None
    rows = frappe.get_all(
        "AssessmentList",
        filters={"parent": content_id, "parenttype": "VideoClass"},
        fields=["assessment_type", "assessment"],
        order_by="idx asc",
    )
    if not rows:
        return None
    return [{"assessment_type": r.assessment_type, "assessment_id": r.assessment}
            for r in rows if r.assessment]


def _get_video_unguided_submission_message(student_id, assessments, language=None):
    """Return unguided submission copy for a video's assignment, when resolvable."""
    response = {"unguided_text": None, "unguided_text_url": None}

    student_id = resolve_student(student_id)
    if not student_id:
        return response

    pe = get_active_pe(student_id)
    if not pe:
        return response

    submission_labels = EXPECTED_SUBMISSION_LABELS.get(
        pe.current_expected_submission_type
    )
    if not submission_labels:
        return response

    message_language = language or pe.language
    if not message_language:
        return response

    assignment_id = None
    for assessment in assessments or []:
        if assessment.get("assessment_type") == "Assignment":
            assignment_id = assessment.get("assessment_id")
            break

    if not assignment_id:
        return response

    rows = frappe.get_all(
        "Assignment Submission Rule",
        filters={
            "parent": assignment_id,
            "parenttype": "Assignment",
            "submission_label": ["in", submission_labels],
            "language": message_language,
        },
        fields=["unguided_text", "unguided_text_audio"],
        order_by="display_order asc, idx asc",
        limit_page_length=1,
    )
    if not rows:
        return response

    return {
        "unguided_text": _strip_html_text(rows[0].unguided_text),
        "unguided_text_url": rows[0].unguided_text_audio,
    }


def _strip_html_text(value):
    if not value:
        return value
    from frappe.utils import strip_html_tags
    return strip_html_tags(value).strip()


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

    Enrollment.course is a Link to Course Level, despite the field label being
    "Course". Return it directly instead of querying non-existent Course Level
    fields like course/grade.
    """
    if not student.enrollment:
        return None

    for enrollment in student.enrollment:
        if enrollment.batch == batch.name and enrollment.course:
            return enrollment.course

    return None


def _is_within_grace_period(batch, current_week):
    """
    Check if we're still within the grace period at the start of a new week.

    Grace period = SUBMISSION_GRACE_HOURS after the week boundary.
    During this time, students who haven't submitted for the previous week
    are NOT blocked yet — they still have time to submit.

    Returns True if within grace period, False if grace has expired.
    """
    if not batch.start_date:
        return False

    # Calculate when the current week started
    week_start_days = (current_week - 1) * 7
    week_start_date = add_days(batch.start_date, week_start_days)

    # Grace deadline = week_start + SUBMISSION_GRACE_HOURS
    grace_deadline = add_to_date(
        get_datetime(week_start_date),
        hours=SUBMISSION_GRACE_HOURS,
    )

    return now_datetime() <= grace_deadline


def _get_current_week(batch):
    """Calculate current calendar week from batch start_date."""
    if not batch.start_date:
        return 0
    days = date_diff(today(), batch.start_date)
    if days < 0:
        return 0
    return (days // 7) + 1


def _get_effective_week(student, batch, calendar_week):
    """
    Determine the student's effective week based on their progress.

    Students can advance AT MOST one week ahead of the calendar week.
    Example: during calendar week 1, a student can complete week 1 and
    advance to week 2 content. But they CANNOT start week 3 — they are
    paused until calendar week 3 arrives.

    Rule: effective_week <= calendar_week + 1

    Returns the week the student should be working on.
    """
    # Get student's progress record (scoped to this batch)
    progress = frappe.db.get_value(
        "StudentStageProgress",
        {
            "student": student.name,
            "course_context": batch.name,
            "stage_type": "LearningUnit",
        },
        ["current_week"],
        as_dict=True,
    )

    if not progress or not progress.current_week:
        return calendar_week

    student_week = cint(progress.current_week)
    total_weeks = cint(batch.total_weeks) or calendar_week

    # Cap: student can be at most 1 week ahead of calendar
    max_allowed = min(calendar_week + 1, total_weeks)

    # Effective week is bounded by [1, max_allowed]
    effective = min(max(student_week, 1), max_allowed)

    return effective


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
            # Removed mid-handler commit per L-017 — Frappe commits at request-end.
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
    # Removed mid-handler commit per L-017 — Frappe commits at request-end.
    return doc.name


def _mark_week_submitted(student_id, course_level, week, total_weeks=0):
    """Mark the current week as submitted in StudentStageProgress.

    Only sets status='completed' when the student finishes the LAST week.
    For earlier weeks, status stays 'in_progress' and the week advancement
    logic in get_next_content handles progression.
    """
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
        updates = {
            "last_activity_timestamp": now_datetime(),
        }
        # Only mark completed on the LAST week
        if total_weeks and week >= total_weeks:
            updates["status"] = "completed"

        frappe.db.set_value("StudentStageProgress", progress_name, updates)

        # Atomic increment for total_content_completed
        frappe.db.sql("""
            UPDATE `tabStudentStageProgress`
            SET total_content_completed = COALESCE(total_content_completed, 0) + 1
            WHERE name = %s
        """, (progress_name,))
        frappe.db.commit()
