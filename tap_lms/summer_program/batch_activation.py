"""
Batch Activation & Validation
tap_lms/summer_program/batch_activation.py

Step 4 of the pipeline:
  - Validate that a BatchProgramRun is ready for activation
  - Check collections, flow IDs, enrollment counts
  - Mark as active
"""
import frappe
import json
from frappe.utils import now_datetime

from tap_lms.summer_program.constants import (
    BPR_COLLECTIONS_READY,
    BPR_ACTIVE,
    VALIDATION_PASSED,
    VALIDATION_FAILED,
    ALL_ARCHETYPES,
    ARM_A,
    ARM_B,
    ACTION_FLOW_FIELD_MAP,
)


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

    Returns:
        dict with success status and message
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

    bpr.status = BPR_ACTIVE
    bpr.activated_at = now_datetime()
    bpr.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "success": True,
        "message": f"BatchProgramRun {bpr_name} is now active. "
        f"Scheduler will start processing daily actions.",
    }
