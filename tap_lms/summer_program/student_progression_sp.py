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
    time_diff_in_hours, date_diff, get_datetime,
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
