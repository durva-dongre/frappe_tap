"""
Program Enrollment APIs
tap_lms/summer_program/program_enrollment_api.py

Bulk:  start_program_enrollment — bulk-create PEs for all students in a BPR (pipeline step 3)
API A6: create_program_enrollment — creates single PE + sets 14 Glific contact fields
API A8: get_enrollment_summary — aggregated stats for admin dashboard
API A1: get_student_state — fallback when contact fields may be stale
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
    CF_EXPERIMENT_ARM,
    CF_COURSE_LEVEL, CF_STUDENT_NAME,
    CF_LAST_ESCALATION_STEP, CF_SUBMISSION_COUNT,
    ALL_ARCHETYPES, TERMINAL_STATES,
    ENROLLMENT_CHUNK_SIZE, ENROLLMENT_QUEUE,
    BPR_COLLECTIONS_READY,
)
from tap_lms.summer_program.event_log import log_event
from tap_lms.summer_program.utils import get_student_display_name


# ════════════════════════════════════════════════════════════
# BULK PROGRAM ENROLLMENT (Pipeline Step — after collections_ready)
# ════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=False)
def start_program_enrollment(bpr_name):
    """
    Bulk-create ProgramEnrollment records for all students in a BPR.

    This is a SEPARATE pipeline step from enrollment.py (which handles
    Glific contact field updates and collection setup).

    Pipeline order:
      1. start_enrollment      → Glific field updates (enrolling)
      2. setup_collections     → Glific collections (collections_ready)
      3. start_program_enrollment → PE records (this function)
      4. validate_bpr          → Readiness check
      5. activate_bpr          → Go live

    Runs in background chunks via frappe.enqueue.

    Args:
        bpr_name: BatchProgramRun document name

    Returns:
        dict with total students queued
    """
    bpr = frappe.get_doc("BatchProgramRun", bpr_name)
    batch = frappe.get_doc("Batch", bpr.batch)

    if bpr.status not in (BPR_COLLECTIONS_READY, "active"):
        return {
            "success": False,
            "error": f"BPR status must be '{BPR_COLLECTIONS_READY}' or 'active', "
                     f"currently '{bpr.status}'",
        }

    # Gather student IDs from the BPR's onboarding sets
    from tap_lms.summer_program.enrollment import _get_students_for_bpr
    student_ids = _get_students_for_bpr(bpr)

    if not student_ids:
        return {"success": False, "error": "No students found for this BPR"}

    # Filter out students who already have a PE for this batch
    existing_pes = set(frappe.get_all(
        "ProgramEnrollment",
        filters={"batch": bpr.batch, "student": ["in", student_ids]},
        pluck="student",
    ))
    new_students = [sid for sid in student_ids if sid not in existing_pes]

    if not new_students:
        return {
            "success": True,
            "message": "All students already have ProgramEnrollment records",
            "total": len(student_ids),
            "already_enrolled": len(existing_pes),
            "new": 0,
        }

    # Enqueue in chunks
    total_chunks = (len(new_students) - 1) // ENROLLMENT_CHUNK_SIZE + 1
    for i in range(0, len(new_students), ENROLLMENT_CHUNK_SIZE):
        chunk = new_students[i : i + ENROLLMENT_CHUNK_SIZE]
        frappe.enqueue(
            "tap_lms.summer_program.program_enrollment_api._process_pe_chunk",
            queue=ENROLLMENT_QUEUE,
            timeout=600,
            bpr_name=bpr_name,
            batch_name=bpr.batch,
            student_ids=chunk,
            chunk_index=i // ENROLLMENT_CHUNK_SIZE,
        )

    frappe.msgprint(
        f"Program Enrollment started: {len(new_students)} new students "
        f"in {total_chunks} chunks. ({len(existing_pes)} already enrolled, skipped.)",
        alert=True,
    )

    return {
        "success": True,
        "total": len(student_ids),
        "already_enrolled": len(existing_pes),
        "new": len(new_students),
        "chunks": total_chunks,
    }


def _process_pe_chunk(bpr_name, batch_name, student_ids, chunk_index):
    """
    Background job: create ProgramEnrollment for a chunk of students.

    For each student:
      1. Create PE record (same logic as create_program_enrollment)
      2. Set 14 Glific contact fields
      3. Log enrollment event
    """
    batch = frappe.get_doc("Batch", batch_name)
    created = 0
    skipped = 0
    errors = []

    for sid in student_ids:
        try:
            # Skip if PE already exists (idempotency)
            existing = frappe.db.get_value(
                "ProgramEnrollment",
                {"student": sid, "batch": batch_name,
                 "program_status": ["not in", ["dropped"]]},
                "name",
            )
            if existing:
                skipped += 1
                continue

            student = frappe.get_doc("Student", sid)
            archetype = student.archetype
            experiment_arm = student.experiment_arm or "default"
            language = getattr(student, "language", None)
            glific_id = student.glific_id

            if not archetype:
                errors.append(f"{sid}: no archetype")
                continue

            course_level = _resolve_course_level(student, batch)
            expected_submission = _get_week1_submission_type(batch, archetype, experiment_arm)

            # Create PE
            pe = frappe.new_doc("ProgramEnrollment")
            pe.enrollment = f"{sid}-{batch.batch_id}"
            pe.student = sid
            pe.batch = batch_name
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
            pe.current_escalation_step = 0
            pe.current_escalation_type = ""
            pe.delivery_failure_count = 0
            pe.re_engagement_count = 0
            pe.next_action_at = None
            pe.next_action_type = ""
            pe.insert(ignore_permissions=True)

            # Set 18 Glific contact fields — async via retry-aware background job
            # so transient Glific outages don't lose the enrollment-time push.
            if glific_id:
                fields = {
                    CF_STUDENT_ID: sid,
                    CF_BATCH_ID: batch.batch_id or batch_name,
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
                    CF_EXPERIMENT_ARM: experiment_arm or "",
                    CF_COURSE_LEVEL: course_level or "",
                    CF_STUDENT_NAME: get_student_display_name(student),
                    CF_LAST_ESCALATION_STEP: "0",
                    CF_SUBMISSION_COUNT: "0",
                }
                frappe.enqueue(
                    "tap_lms.summer_program.state_machine._sync_contact_fields_job",
                    queue="short",
                    timeout=30,
                    enqueue_after_commit=True,
                    glific_id=str(glific_id),
                    fields=fields,
                    pe_name=pe.name,
                    retry_count=0,
                    student_id=sid,
                )

            # Log
            log_event(pe, "archetype_assigned", new_value=archetype,
                      trigger_source="admin",
                      details={"experiment_arm": experiment_arm, "batch": batch_name})

            created += 1

        except Exception as e:
            frappe.log_error(
                f"PE creation error for {sid}: {str(e)}",
                "SP Program Enrollment Chunk",
            )
            errors.append(f"{sid}: {str(e)}")

    frappe.db.commit()

    # Update BPR total_enrolled count
    frappe.db.sql("""
        UPDATE `tabBatchProgramRun`
        SET total_enrolled = (
            SELECT COUNT(*) FROM `tabProgramEnrollment`
            WHERE batch = (SELECT batch FROM `tabBatchProgramRun` WHERE name = %s)
              AND program_status != 'dropped'
        )
        WHERE name = %s
    """, (bpr_name, bpr_name))
    frappe.db.commit()

    frappe.logger().info(
        f"SP PE chunk {chunk_index}: created={created}, skipped={skipped}, "
        f"errors={len(errors)} for BPR {bpr_name}"
    )


@frappe.whitelist(allow_guest=False)
def create_program_enrollment(student_id, batch_id, archetype=None,
                               experiment_arm=None, language=None,
                               course_level=None, glific_group_id=None):
    """
    API A6: create_program_enrollment

    Creates a ProgramEnrollment record, sets 14 Glific contact fields,
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
    pe.current_escalation_step = 0
    pe.current_escalation_type = ""
    pe.delivery_failure_count = 0
    pe.re_engagement_count = 0

    # next_action_at = NULL for batch start (collection trigger handles it)
    pe.next_action_at = None
    pe.next_action_type = ""

    pe.insert(ignore_permissions=True)

    # ── Set 18 Glific Contact Fields ────────────────────────
    # Async via retry-aware background job (pattern P-007) so transient Glific
    # outages don't lose the enrollment-time push.
    if glific_id:
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
            CF_EXPERIMENT_ARM: experiment_arm or "",
            CF_COURSE_LEVEL: course_level or "",
            CF_STUDENT_NAME: get_student_display_name(student),
            CF_LAST_ESCALATION_STEP: "0",
            CF_SUBMISSION_COUNT: "0",
        }
        frappe.enqueue(
            "tap_lms.summer_program.state_machine._sync_contact_fields_job",
            queue="short",
            timeout=30,
            enqueue_after_commit=True,
            glific_id=str(glific_id),
            fields=fields,
            pe_name=pe.name,
            retry_count=0,
            student_id=student_id,
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

    Called by SP_Incoming_Router as fallback if contact fields seem
    inconsistent.

    Response (via frappe.local.response per docs/api-standard-glific.md Rule 1):
        Flat dict with `success` + `status` + PE fields. Does NOT return.
    """
    student_id = _resolve_student(student_id)
    if not student_id:
        frappe.local.response.update({
            "success": False, "status": "not_found",
            "error_detail": "Student not found",
        })
        return

    pe_data = frappe.db.get_value(
        "ProgramEnrollment",
        {"student": student_id, "program_status": ["not in", ["dropped"]]},
        [
            "name", "batch", "program_type", "archetype", "experiment_arm",
            "resolved_flow_state", "journey_label", "program_status",
            "current_week", "current_path", "current_tier",
            "total_points", "current_streak", "in_grace_window",
            "grace_window_end_at", "current_expected_submission_type",
            "submission_count", "current_escalation_step",
            "current_escalation_type", "course_level",
            "language", "glific_id",
            # CR-002 v2 — 8 new gamification fields. Flat-map per
            # docs/api-standard-glific.md Rule 1 (no nesting, no arrays).
            # `weekly_video_done` is internal-only and intentionally omitted.
            "total_activity_points", "weekly_activity_points",
            "total_quiz_points", "weekly_quiz_points",
            "total_submission_points", "weekly_submission_points",
            "special_gems", "weekly_submission_done",
        ],
        as_dict=True,
        order_by="creation desc",
    )

    if not pe_data:
        frappe.local.response.update({
            "success": False, "status": "no_enrollment_found",
            "error_detail": "No ProgramEnrollment found",
        })
        return

    # L-008 (Glific public contract): the Glific contact field + webhook
    # response key is `last_escalation_step`, despite the PE column being
    # renamed to `current_escalation_step` in this CR. Re-key the dict so
    # SP_Incoming_Router and any other flow reading
    # `@results.webhook.last_escalation_step` continues to work.
    # `current_escalation_type` is genuinely new — it uses its natural name.
    if "current_escalation_step" in pe_data:
        pe_data["last_escalation_step"] = pe_data.pop("current_escalation_step")

    frappe.local.response.update({
        "success": True,
        "status": "ok",
        "student_id": student_id,
        **pe_data,
    })


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _resolve_student(identifier):
    """Delegate to shared utility."""
    from tap_lms.summer_program.utils import resolve_student
    return resolve_student(identifier)


def _resolve_course_level(student, batch):
    """Get course level from student's enrollment in this batch.

    enrollment.course is a Link field pointing directly to a Course Level
    document name, so no extra lookup is needed.
    """
    if not student.enrollment:
        return None
    for enrollment in student.enrollment:
        if enrollment.batch == batch.name and enrollment.course:
            return enrollment.course
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
