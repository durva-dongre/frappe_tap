"""
Batch Activation & Validation
tap_lms/summer_program/batch_activation.py

Step 4 of the pipeline:
  - Validate that a BatchProgramRun is ready for activation
  - Check collections, flow IDs, enrollment counts
  - Mark as active
  - Seed next_action_at on all PEs (staggered to avoid thundering herd)
"""
import frappe
import json
from frappe.utils import now_datetime, get_datetime, getdate

from tap_lms.summer_program.constants import (
    BPR_COLLECTIONS_READY,
    BPR_ACTIVE,
    VALIDATION_PASSED,
    VALIDATION_FAILED,
    ALL_ARCHETYPES,
    ARM_A,
    ARM_B,
    ACTION_FLOW_FIELD_MAP,
    ACTION_CONTENT_DELIVERY,
    PROGRAM_ACTIVE,
    STATE_NORMAL_CONTENT,
)
from tap_lms.summer_program.utils import staggered_action_time


@frappe.whitelist()
def validate_bpr(bpr_name):
    """
    Run validation checks on a BatchProgramRun.
    Returns a validation report dict and updates the BPR.

    Checks:
      1. BPR is in collections_ready status
      2. All 8 archetype collections exist (4 archetypes × 2 arms)
      3. At least one flow ID is configured
      4. total_enrolled > 0
      5. Batch has start_date and total_weeks set
    """
    bpr = frappe.get_doc("BatchProgramRun", bpr_name)
    batch = frappe.get_doc("Batch", bpr.batch)

    errors = []
    warnings = []

    # 1. Status check
    if bpr.status != BPR_COLLECTIONS_READY:
        errors.append(
            f"BPR status must be '{BPR_COLLECTIONS_READY}', "
            f"currently '{bpr.status}'"
        )

    # 2. Collection completeness
    existing_labels = {c.collection_label for c in bpr.pg_collections}
    expected_count = len(ALL_ARCHETYPES) * 2  # 4 × 2 = 8
    if len(existing_labels) < expected_count:
        missing = expected_count - len(existing_labels)
        errors.append(
            f"Expected {expected_count} archetype collections, "
            f"found {len(existing_labels)} ({missing} missing)"
        )

    # Check each collection has students
    empty_collections = [
        c.collection_label
        for c in bpr.pg_collections
        if (c.student_count or 0) == 0
    ]
    if empty_collections:
        warnings.append(
            f"{len(empty_collections)} collections have 0 students: "
            f"{', '.join(empty_collections[:3])}{'...' if len(empty_collections) > 3 else ''}"
        )

    # 3. Flow IDs
    configured_flows = {}
    missing_flows = []
    for action_type, field_name in ACTION_FLOW_FIELD_MAP.items():
        flow_id = getattr(bpr, field_name, None)
        if flow_id:
            configured_flows[action_type] = flow_id
        else:
            missing_flows.append(action_type)

    if not configured_flows:
        errors.append("No Glific flow IDs configured on this BPR")
    elif missing_flows:
        warnings.append(
            f"Flows not configured: {', '.join(missing_flows)}"
        )

    # 4. Enrollment count
    if not bpr.total_enrolled or bpr.total_enrolled == 0:
        errors.append("No students enrolled (total_enrolled is 0)")

    # 4b. ProgramEnrollment records exist
    pe_count = frappe.db.count(
        "ProgramEnrollment",
        {"batch": bpr.batch, "program_status": ["!=", "dropped"]},
    )
    if pe_count == 0:
        errors.append(
            "No ProgramEnrollment records found. "
            "Run 'Start Program Enrollment' before activation."
        )
    elif pe_count < (bpr.total_enrolled or 0):
        warnings.append(
            f"Only {pe_count} ProgramEnrollment records for "
            f"{bpr.total_enrolled} enrolled students — "
            f"program enrollment may still be running"
        )

    # 5. Batch configuration
    if not batch.start_date:
        errors.append("Batch has no start_date set")
    if not batch.total_weeks:
        errors.append("Batch has no total_weeks set")

    # Build report
    report = {
        "timestamp": str(now_datetime()),
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "total_imported": bpr.total_imported or 0,
            "total_enrolled": bpr.total_enrolled or 0,
            "program_enrollments": pe_count,
            "collections": len(bpr.pg_collections),
            "configured_flows": configured_flows,
        },
        "passed": len(errors) == 0,
    }

    # Update BPR
    bpr.validation_status = VALIDATION_PASSED if report["passed"] else VALIDATION_FAILED
    bpr.validation_report = json.dumps(report, indent=2)
    bpr.save(ignore_permissions=True)
    frappe.db.commit()

    return report


@frappe.whitelist()
def activate_bpr(bpr_name):
    """
    Activate a validated BatchProgramRun.
    Requires validation_status == 'passed'.

    On activation:
      1. Sets BPR status = active
      2. Seeds next_action_at on ALL PEs for this batch (staggered with jitter)
         so the per-PE dispatcher picks them up for first content delivery.

    Returns:
        dict with success status, message, and seeded_count
    """
    bpr = frappe.get_doc("BatchProgramRun", bpr_name)

    if bpr.validation_status != VALIDATION_PASSED:
        return {
            "success": False,
            "message": "Cannot activate: validation has not passed. Run validate first.",
        }

    if bpr.status == BPR_ACTIVE:
        return {
            "success": False,
            "message": "BPR is already active.",
        }

    batch = frappe.get_doc("Batch", bpr.batch)

    bpr.status = BPR_ACTIVE
    bpr.activated_at = now_datetime()
    bpr.save(ignore_permissions=True)
    frappe.db.commit()

    # Seed next_action_at on all PEs for first content delivery
    seeded = _seed_pe_actions(bpr, batch)

    return {
        "success": True,
        "message": f"BatchProgramRun {bpr_name} is now active. "
        f"{seeded} students seeded for content delivery.",
        "seeded_count": seeded,
    }


def _seed_pe_actions(bpr, batch):
    """
    Seed next_action_at and next_action_type on all PEs for this batch.

    Uses batch.start_date as base time (or now() if start_date is today/past).
    Applies staggered jitter (30-min window) to prevent thundering herd.

    Only seeds PEs that:
      - Are in program_status = 'active'
      - Are in resolved_flow_state = 'normal_content_delivery'
      - Don't already have a next_action_at set (idempotency)
    """
    # Determine base delivery time
    start_date = batch.start_date
    if start_date and getdate(start_date) > getdate(now_datetime()):
        # Batch hasn't started yet — schedule for start_date at 09:00
        base_time = get_datetime(f"{start_date} 09:00:00")
    else:
        # Batch started already or start_date is today — deliver now
        base_time = now_datetime()

    # Get all PEs that need seeding
    pe_list = frappe.db.get_all(
        "ProgramEnrollment",
        filters={
            "batch": bpr.batch,
            "program_status": PROGRAM_ACTIVE,
            "resolved_flow_state": STATE_NORMAL_CONTENT,
            "next_action_at": ["is", "not set"],
        },
        fields=["name"],
        limit_page_length=0,
    )

    if not pe_list:
        return 0

    # Bulk update with staggered times (batch SQL for performance at 100K scale)
    # Process in chunks of 5000 to avoid memory issues
    CHUNK = 5000
    seeded = 0

    for i in range(0, len(pe_list), CHUNK):
        chunk = pe_list[i:i + CHUNK]
        for pe_row in chunk:
            action_time = staggered_action_time(base_time, pe_row.name, window_minutes=30)
            frappe.db.set_value(
                "ProgramEnrollment", pe_row.name,
                {
                    "next_action_at": action_time,
                    "next_action_type": ACTION_CONTENT_DELIVERY,
                },
                update_modified=False,
            )
        frappe.db.commit()
        seeded += len(chunk)

    return seeded


# ── Auto-activation (daily scheduler hook) ──────────────────


def check_auto_activate():
    """
    Daily scheduler hook: auto-activate BPRs whose batch.start_date is today or past.

    Finds BPRs in 'collections_ready' status with validation_status='passed'
    where batch.start_date <= today. Activates them and seeds PEs.

    Register in hooks.py:
        scheduler_events.daily: tap_lms.summer_program.batch_activation.check_auto_activate
    """
    today = getdate(now_datetime())

    # Find BPRs ready to activate
    candidates = frappe.db.sql(
        """
        SELECT bpr.name AS bpr_name, bpr.batch, b.start_date
        FROM `tabBatchProgramRun` bpr
        JOIN `tabBatch` b ON b.name = bpr.batch
        WHERE bpr.status = %s
          AND bpr.validation_status = %s
          AND b.start_date IS NOT NULL
          AND b.start_date <= %s
        """,
        (BPR_COLLECTIONS_READY, VALIDATION_PASSED, today),
        as_dict=True,
    )

    activated = 0
    for row in candidates:
        try:
            result = activate_bpr(row.bpr_name)
            if result.get("success"):
                activated += 1
                frappe.logger().info(
                    f"Auto-activated BPR {row.bpr_name} for batch {row.batch} "
                    f"(start_date={row.start_date}, seeded={result.get('seeded_count', 0)})"
                )
        except Exception as e:
            frappe.log_error(
                f"Auto-activate error for BPR {row.bpr_name}: {str(e)}",
                "SP Auto Activate",
            )

    return activated
