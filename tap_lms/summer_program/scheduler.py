"""
Summer Program Scheduler
tap_lms/summer_program/scheduler.py

PAL Scheduler — runs as a Frappe scheduled task.
Handles collection-based and per-student flow triggers.

Register in hooks.py:
    scheduler_events = {
        "daily": [
            "tap_lms.summer_program.scheduler.run_daily_actions",
        ]
    }
"""
import frappe
from frappe.utils import now_datetime, getdate, today, date_diff

from tap_lms.glific_integration import start_contact_flow
from tap_lms.summer_program.constants import (
    BPR_ACTIVE,
    ACTION_CONTENT_DELIVERY,
    ACTION_ESCALATION,
    ACTION_REENGAGEMENT,
    ACTION_GRACE_REMINDER,
    ACTION_FLOW_FIELD_MAP,
    COLLECTION_ACTIONS,
    PER_STUDENT_ACTIONS,
    ARCHETYPE_DORMANT,
    ARCHETYPE_FENCE_SITTER,
    PROGRAM_PAUSED,
)
from tap_lms.summer_program.glific_extensions import start_group_flow


def run_daily_actions():
    """
    Main scheduler entry point. Called daily by Frappe scheduler.
    Finds all active BatchProgramRuns and processes scheduled actions.
    """
    active_bprs = frappe.get_all(
        "BatchProgramRun",
        filters={"status": BPR_ACTIVE},
        fields=["name"],
    )

    for row in active_bprs:
        try:
            bpr = frappe.get_doc("BatchProgramRun", row.name)
            batch = frappe.get_doc("Batch", bpr.batch)
            _process_bpr_actions(bpr, batch)
        except Exception as e:
            frappe.log_error(
                f"Scheduler error for BPR {row.name}: {str(e)}",
                "SP Scheduler",
            )


def _process_bpr_actions(bpr, batch):
    """
    Determine which actions to run today for a given BPR.
    """
    current_week = _get_current_week(batch)
    total_weeks = batch.total_weeks or 0
    grace_days = batch.grace_window_days or 0

    # ── Collection-based actions ─────────────────────────
    # Content delivery: runs daily for active batches
    _run_collection_action(bpr, ACTION_CONTENT_DELIVERY)

    # Escalation: for Dormant and Fence Sitter collections
    _run_escalation(bpr)

    # Re-engagement: for Dormant students who haven't responded
    _run_reengagement(bpr)

    # ── Per-student actions ──────────────────────────────
    # Grace notification: students in grace period
    _run_grace_notifications(bpr, batch, grace_days)

    # Program complete: when batch reaches total_weeks
    if current_week and total_weeks and current_week > total_weeks:
        _run_program_complete(bpr, batch)


# ── Collection-Based Actions ────────────────────────────────


def _run_collection_action(bpr, action_type):
    """
    Trigger a flow on ALL archetype collections for this BPR.
    """
    flow_field = ACTION_FLOW_FIELD_MAP.get(action_type)
    if not flow_field:
        return

    flow_id = getattr(bpr, flow_field, None)
    if not flow_id:
        frappe.logger().info(
            f"No flow configured for {action_type} on BPR {bpr.name}"
        )
        return

    for collection in bpr.pg_collections:
        try:
            result = start_group_flow(flow_id, collection.glific_group_id)
            if result:
                frappe.logger().info(
                    f"{action_type}: triggered flow {flow_id} "
                    f"on collection {collection.collection_label}"
                )
            else:
                frappe.logger().error(
                    f"{action_type}: FAILED flow {flow_id} "
                    f"on collection {collection.collection_label}"
                )
        except Exception as e:
            frappe.log_error(
                f"{action_type} error on {collection.collection_label}: {str(e)}",
                "SP Scheduler Action",
            )


def _run_escalation(bpr):
    """
    Run escalation flow only on Dormant and Fence Sitter collections.
    """
    flow_id = bpr.escalation_flow
    if not flow_id:
        return

    target_archetypes = [ARCHETYPE_DORMANT, ARCHETYPE_FENCE_SITTER]
    for collection in bpr.pg_collections:
        if collection.archetype in target_archetypes:
            try:
                start_group_flow(flow_id, collection.glific_group_id)
                frappe.logger().info(
                    f"Escalation: flow {flow_id} on {collection.collection_label}"
                )
            except Exception as e:
                frappe.log_error(
                    f"Escalation error: {collection.collection_label}: {str(e)}",
                    "SP Scheduler Escalation",
                )


def _run_reengagement(bpr):
    """
    Run re-engagement flow on Dormant collections.
    """
    flow_id = bpr.reengagement_flow
    if not flow_id:
        return

    for collection in bpr.pg_collections:
        if collection.archetype == ARCHETYPE_DORMANT:
            try:
                start_group_flow(flow_id, collection.glific_group_id)
                frappe.logger().info(
                    f"Reengagement: flow {flow_id} on {collection.collection_label}"
                )
            except Exception as e:
                frappe.log_error(
                    f"Reengagement error: {collection.collection_label}: {str(e)}",
                    "SP Scheduler Reengagement",
                )


# ── Per-Student Actions ─────────────────────────────────────


def _run_grace_notifications(bpr, batch, grace_days):
    """
    Send grace notifications to students who are in the grace period.
    Grace = student hasn't submitted in grace_days consecutive days.
    """
    flow_id = bpr.grace_notification_flow
    if not flow_id or not grace_days:
        return

    # Find students who haven't had activity in grace_days
    # and belong to this batch
    student_ids = _get_students_for_bpr(bpr)
    if not student_ids:
        return

    grace_students = frappe.db.sql(
        """
        SELECT s.name, s.glific_id
        FROM `tabStudent` s
        LEFT JOIN `tabEngagementState` es ON es.student = s.name
        WHERE s.name IN %s
          AND s.glific_id IS NOT NULL
          AND s.glific_id != ''
          AND es.last_activity_date IS NOT NULL
          AND DATEDIFF(CURDATE(), es.last_activity_date) >= %s
          AND DATEDIFF(CURDATE(), es.last_activity_date) < %s
        """,
        (student_ids, grace_days, grace_days + 3),  # notify once in a 3-day window
        as_dict=True,
    )

    for student in grace_students:
        try:
            start_contact_flow(
                str(flow_id),
                str(student.glific_id),
                {"grace_days": str(grace_days)},
            )
        except Exception as e:
            frappe.log_error(
                f"Grace notification error for {student.name}: {str(e)}",
                "SP Scheduler Grace",
            )

    if grace_students:
        frappe.logger().info(
            f"Grace notifications sent to {len(grace_students)} students "
            f"for BPR {bpr.name}"
        )


def _run_program_complete(bpr, batch):
    """
    Trigger program-complete flow for all students in the batch.
    Uses collection-based trigger since it applies to everyone.
    """
    flow_id = bpr.program_complete_flow
    if not flow_id:
        return

    # Trigger on ALL collections (every student gets this)
    for collection in bpr.pg_collections:
        try:
            start_group_flow(flow_id, collection.glific_group_id)
        except Exception as e:
            frappe.log_error(
                f"Program complete error: {collection.collection_label}: {str(e)}",
                "SP Scheduler Complete",
            )

    # Also trigger on onboarding set collections
    for pg_set in bpr.pg_onboarding_sets:
        if pg_set.glific_contact_group:
            try:
                group_doc = frappe.get_doc("GlificContactGroup", pg_set.glific_contact_group)
                start_group_flow(flow_id, group_doc.group_id)
            except Exception as e:
                frappe.log_error(
                    f"Program complete error (onboarding set): {str(e)}",
                    "SP Scheduler Complete",
                )

    # Mark BPR as completed
    bpr.status = "completed"
    bpr.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.logger().info(f"Program completed for BPR {bpr.name}")


# ── Helpers ──────────────────────────────────────────────────


def _get_current_week(batch):
    """Calculate current week number from batch start_date."""
    if not batch.start_date:
        return None
    days = date_diff(today(), batch.start_date)
    if days < 0:
        return 0
    return (days // 7) + 1


def _get_students_for_bpr(bpr):
    """Get all student names linked to a BPR."""
    from tap_lms.summer_program.enrollment import _get_students_for_bpr as get_students
    return get_students(bpr)
