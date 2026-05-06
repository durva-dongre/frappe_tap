"""
Program Enrollment APIs
tap_lms/summer_program/program_enrollment_api.py

API A6: create_program_enrollment — creates PE + sets 13 Glific contact fields
API A8: get_enrollment_summary — aggregated stats for admin dashboard
API extra: get_student_state — fallback when contact fields may be stale (A1)
"""
import frappe
import json
from frappe import _
from frappe.utils import now_datetime, cint

from tap_lms.glific_integration import update_contact_fields, add_contact_to_group
from tap_lms.summer_program.constants import (
    STATE_NORMAL_CONTENT,
    LABEL_ENROLLED, PROGRAM_ACTIVE,
    PATH_CORE, TIER_BY_WEEK, DEFAULT_TIER,
    CF_STUDENT_ID, CF_BATCH_ID, CF_ARCHETYPE, CF_LANGUAGE,
    CF_RESOLVED_FLOW_STATE, CF_CURRENT_WEEK, CF_CURRENT_PATH,
    CF_CURRENT_TIER, CF_PROGRAM_STATUS, CF_TOTAL_POINTS,
    CF_CURRENT_STREAK, CF_GRACE_WINDOW_END, CF_EXPECTED_SUBMISSION,
    ALL_ARCHETYPES, TERMINAL_STATES,
)
from tap_lms.summer_program.event_log import log_event


@frappe.whitelist(allow_guest=False)
def create_program_enrollment(student_id, batch_id, archetype=None,
                               experiment_arm=None, language=None,
                               course_level=None, glific_group_id=None):
    """
    API A6: create_program_enrollment

    Creates a ProgramEnrollment record, sets 13 Glific contact fields,
    and optionally adds student to a Glific collection.

    Called during onboarding Step 3a for each student.

    Args:
        student_id: Student document name
        batch_id: Batch document name
        archetype: Student archetype (defaults to Student.archetype)
        experiment_arm: Experiment arm (defaults to Student.experiment_arm)
        language: Language (defaults to Student.language)
        course_level: Course Level name (resolved if not provided)
        glific_group_id: Glific collection group ID to add student to

    Returns:
        dict with PE name, enrollment details
    """
    if not frappe.db.exists("Student", student_id):
        return {"success": False, "error": f"Student {student_id} not found"}

    if not frappe.db.exists("Batch", batch_id):
        return {"success": False, "error": f"Batch {batch_id} not found"}

    student = frappe.get_doc("Student", student_id)
    batch = frappe.get_doc("Batch", batch_id)

    # Resolve defaults from Student record
    archetype = archetype or student.archetype
    experiment_arm = experiment_arm or student.experiment_arm or "default"
    language = language or getattr(student, "language", None)
    glific_id = student.glific_id

    if not archetype:
        return {"success": False, "error": "Student has no archetype assigned"}

    # Resolve course level if not provided
    if not course_level:
        course_level = _resolve_course_level(student, batch)

    # Get initial WeekRule for expected submission type
    expected_submission = _get_week1_submission_type(batch, archetype, experiment_arm)

    # Check for existing active PE
    existing = frappe.db.get_value(
        "ProgramEnrollment",
        {"student": student_id, "batch": batch_id,
         "program_status": ["not in", ["dropped"]]},
        "name",
    )
    if existing:
        return {
            "success": False,
            "error": "Student already enrolled in this batch",
            "enrollment": existing,
        }

    # ── Create ProgramEnrollment ────────────────────────────
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"{student_id}-{batch.batch_id}"
    pe.student = student_id
    pe.batch = batch_id
    pe.program_type = batch.program_type or "Summer"
    pe.glific_id = glific_id or ""
    pe.course_level = course_level
    pe.language = language
    pe.experiment_arm = experiment_arm
    pe.archetype = archetype
    pe.current_path = PATH_CORE
    pe.current_tier = TIER_BY_WEEK.get(1, "Basic")
    pe.journey_label = LABEL_ENROLLED
    pe.last_label_change_at = now_datetime()
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = STATE_NORMAL_CONTENT
    pe.current_expected_submission_type = expected_submission
    pe.current_week = 1
    pe.max_allowed_week = (batch.current_calendar_week or 1) + 1
    pe.total_points = 0
    pe.current_streak = 0
    pe.pause_count = 0
    pe.submission_count = 0
    pe.quiz_completed = 0
    pe.in_grace_window = 0
    pe.last_escalation_step = 0
    pe.delivery_failure_count = 0
    pe.re_engagement_count = 0

    # next_action_at = NULL for batch start (collection trigger handles it)
    pe.next_action_at = None
    pe.next_action_type = ""

    pe.insert(ignore_permissions=True)

    # ── Set 13 Glific Contact Fields ────────────────────────
    if glific_id:
        try:
            fields = {
                CF_STUDENT_ID: student_id,
                CF_BATCH_ID: batch.batch_id or batch_id,
                CF_ARCHETYPE: archetype,
                CF_LANGUAGE: language or "",
                CF_RESOLVED_FLOW_STATE: STATE_NORMAL_CONTENT,
                CF_CURRENT_WEEK: "1",
                CF_CURRENT_PATH: PATH_CORE,
                CF_CURRENT_TIER: TIER_BY_WEEK.get(1, "Basic"),
                CF_PROGRAM_STATUS: PROGRAM_ACTIVE,
                CF_TOTAL_POINTS: "0",
                CF_CURRENT_STREAK: "0",
                CF_GRACE_WINDOW_END: "",
                CF_EXPECTED_SUBMISSION: expected_submission or "",
            }
            update_contact_fields(str(glific_id), fields)
        except Exception as e:
            frappe.log_error(
                f"Glific field update error for {student_id}: {str(e)}",
                "SP Enrollment Glific",
            )

        # Add to collection if group_id provided
        if glific_group_id:
            try:
                add_contact_to_group(str(glific_id), str(glific_group_id))
            except Exception as e:
                frappe.log_error(
                    f"Glific group add error: {str(e)}", "SP Enrollment Collection"
                )

    # ── Log event ──────────────────────────────────────────
    log_event(pe, "archetype_assigned", new_value=archetype,
              trigger_source="admin",
              details={
                  "experiment_arm": experiment_arm,
                  "archetype": archetype,
                  "batch": batch_id,
              })

    frappe.db.commit()

    return {
        "success": True,
        "enrollment": pe.name,
        "student_id": student_id,
        "batch": batch_id,
        "archetype": archetype,
        "experiment_arm": experiment_arm,
        "resolved_flow_state": pe.resolved_flow_state,
        "current_week": pe.current_week,
        "current_path": pe.current_path,
    }


@frappe.whitelist(allow_guest=False)
def get_enrollment_summary(batch_id):
    """
    API A8: get_enrollment_summary

    Aggregated stats for admin dashboard. Breaks down by:
      - archetype × resolved_flow_state
      - archetype × experiment_arm
      - per-week submission rates

    Args:
        batch_id: Batch document name

    Returns:
        dict with aggregated enrollment statistics
    """
    if not frappe.db.exists("Batch", batch_id):
        return {"success": False, "error": "Batch not found"}

    batch = frappe.get_doc("Batch", batch_id)

    # Total enrollments
    total = frappe.db.count("ProgramEnrollment", {"batch": batch_id})

    # By resolved_flow_state
    state_counts = frappe.db.sql("""
        SELECT resolved_flow_state, COUNT(*) as count
        FROM `tabProgramEnrollment`
        WHERE batch = %s
        GROUP BY resolved_flow_state
    """, batch_id, as_dict=True)

    # By archetype × program_status
    archetype_status = frappe.db.sql("""
        SELECT archetype, program_status, COUNT(*) as count
        FROM `tabProgramEnrollment`
        WHERE batch = %s
        GROUP BY archetype, program_status
    """, batch_id, as_dict=True)

    # By archetype × experiment_arm
    archetype_arm = frappe.db.sql("""
        SELECT archetype, experiment_arm, COUNT(*) as count
        FROM `tabProgramEnrollment`
        WHERE batch = %s
        GROUP BY archetype, experiment_arm
    """, batch_id, as_dict=True)

    # Per-week submission counts
    week_submissions = frappe.db.sql("""
        SELECT current_week,
               COUNT(*) as total,
               SUM(CASE WHEN submission_count > 0 THEN 1 ELSE 0 END) as submitted,
               SUM(CASE WHEN in_grace_window = 1 THEN 1 ELSE 0 END) as in_grace,
               SUM(CASE WHEN program_status = 'paused' THEN 1 ELSE 0 END) as paused
        FROM `tabProgramEnrollment`
        WHERE batch = %s AND program_status != 'dropped'
        GROUP BY current_week
        ORDER BY current_week
    """, batch_id, as_dict=True)

    # Active vs completed vs paused vs dropped
    status_summary = frappe.db.sql("""
        SELECT program_status, COUNT(*) as count
        FROM `tabProgramEnrollment`
        WHERE batch = %s
        GROUP BY program_status
    """, batch_id, as_dict=True)

    return {
        "success": True,
        "batch": batch_id,
        "total_enrolled": total,
        "total_weeks": batch.total_weeks or 0,
        "current_calendar_week": batch.current_calendar_week or 0,
        "by_state": {r.resolved_flow_state: r["count"] for r in state_counts},
        "by_archetype_status": archetype_status,
        "by_archetype_arm": archetype_arm,
        "by_week": week_submissions,
        "by_program_status": {r.program_status: r["count"] for r in status_summary},
    }


@frappe.whitelist(allow_guest=False)
def get_student_state(student_id):
    """
    API A1: get_student_state

    Fallback API when Glific contact fields may be stale.
    Returns current PE state as a single SELECT by student_id.

    Called by SP_Incoming_Router as fallback if contact fields
    seem inconsistent.

    Args:
        student_id: Student name, glific_id, or phone

    Returns:
        dict with current PE state fields
    """
    student_id = _resolve_student(student_id)
    if not student_id:
        return {"success": False, "error": "Student not found"}

    pe_data = frappe.db.get_value(
        "ProgramEnrollment",
        {"student": student_id, "program_status": ["not in", ["dropped"]]},
        [
            "name", "batch", "program_type", "archetype", "experiment_arm",
            "resolved_flow_state", "journey_label", "program_status",
            "current_week", "current_path", "current_tier",
            "total_points", "current_streak", "in_grace_window",
            "grace_window_end_at", "current_expected_submission_type",
            "submission_count", "last_escalation_step",
        ],
        as_dict=True,
        order_by="creation desc",
    )

    if not pe_data:
        return {"success": False, "error": "No ProgramEnrollment found"}

    return {
        "success": True,
        "student_id": student_id,
        **pe_data,
    }


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _resolve_student(identifier):
    if not identifier:
        return None
    if frappe.db.exists("Student", identifier):
        return identifier
    student = frappe.db.get_value("Student", {"glific_id": identifier}, "name")
    if student:
        return student
    return frappe.db.get_value("Student", {"phone": str(identifier).strip()}, "name")


def _resolve_course_level(student, batch):
    """Get course level from student's enrollment in this batch."""
    if not student.enrollment:
        return None
    for enrollment in student.enrollment:
        if enrollment.batch == batch.name and enrollment.course:
            cl = frappe.db.get_value(
                "Course Level",
                {"course": enrollment.course, "grade": student.grade},
                "name",
            )
            if cl:
                return cl
            return frappe.db.get_value(
                "Course Level", {"course": enrollment.course}, "name"
            )
    return None


def _get_week1_submission_type(batch, archetype, experiment_arm):
    """Get expected submission type for week 1 from ArchetypeConfig."""
    config = frappe.db.get_value(
        "ArchetypeConfig",
        {
            "batch": batch.name,
            "experiment_arm": experiment_arm,
            "archetype": archetype,
            "path": PATH_CORE,
            "is_active": 1,
        },
        "name",
    )
    if not config:
        # Fallback to default arm
        config = frappe.db.get_value(
            "ArchetypeConfig",
            {
                "batch": batch.name,
                "experiment_arm": "default",
                "archetype": archetype,
                "path": PATH_CORE,
                "is_active": 1,
            },
            "name",
        )
    if not config:
        return None

    week_rule = frappe.db.get_value(
        "WeekRule",
        {"parent": config, "parenttype": "ArchetypeConfig", "week": 1},
        "expected_submission_type",
    )
    return week_rule
