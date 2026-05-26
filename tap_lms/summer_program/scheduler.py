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
    ACTION_FLOW_FIELD_MAP,
    COLLECTION_ACTIONS,
    PER_STUDENT_ACTIONS,
    ARCHETYPE_DORMANT,
    ARCHETYPE_FENCE_SITTER,
)
# CR-003: ACTION_REENGAGEMENT and ACTION_GRACE_REMINDER removed from constants.
# _run_reengagement and _run_grace_notifications were the daily-scheduler
# entry points that consumed those action types; both functions are deleted
# from this file (re-engagement is now inbound-only; grace reminders are
# replaced by per-week escalation steps).
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

    # CR-003: proactive re-engagement removed. Dropped students are
    # re-engaged via SP_Incoming_Router when they send an inbound
    # message; the backend does not push re-engagement nudges.

    # ── Per-student actions ──────────────────────────────
    # CR-003: proactive grace notifications removed. The per-week
    # escalation steps within the active week ARE the reminders;
    # grace expiry is policed by handle_grace_check in pe_dispatcher.

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


# CR-003: _run_reengagement removed — re-engagement is now inbound-only via
# SP_Incoming_Router when the student sends a message and program_status =
# 'dropped'. The backend never reaches out to dropped students.
#
# CR-003: _run_grace_notifications removed — the per-week escalation steps
# inside the active week ARE the reminders. handle_grace_check in
# pe_dispatcher fires once at grace_window_end_at; on expiry the PE drops
# directly to program_dropped (no proactive grace notification flow).


# ── Per-Student Actions ─────────────────────────────────────


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


# ── CR-005 (2026-05-15): Weekly content delivery via main collection ──

def weekly_content_delivery_trigger():
    """CR-005: Tuesday 09:00 IST (03:30 UTC). For each active BPR, fire
    SP_Content_Delivery against the `main` Glific collection. Membership is
    already current because state transitions wrote it continuously throughout
    the week (Approach B). No recompute, no reconcile.

    Idempotency: re-running produces another start_group_flow call for each
    active BPR. Glific deduplicates identical group-flow starts within a short
    window; operator discipline (don't manually invoke during the cron window)
    is the documented mitigation. No code-level mutex per locked decision
    2026-05-15.
    """
    active_bprs = frappe.db.sql(
        """
        SELECT name, batch, content_delivery_flow
          FROM "tabBatchProgramRun"
         WHERE status = 'active'
           AND content_delivery_flow IS NOT NULL
        """,
        as_dict=True,
    )

    for bpr in active_bprs:
        main_col = frappe.db.sql(
            """
            SELECT name, glific_group_id, collection_label, member_count
              FROM "tabPGCollection"
             WHERE parent = %s
               AND kind = %s
               AND COALESCE(is_active, 0) = 1
             LIMIT 1
            """,
            (bpr["name"], "main"),
            as_dict=True,
        )
        if not main_col:
            continue
        main_col = main_col[0]

        if not main_col.get("glific_group_id"):
            continue

        # Skip BPRs whose main collection has zero members. Reading
        # member_count avoids a needless Glific call (which would either
        # error or no-op). The count is maintained by the state-driven
        # collection_membership writes (Approach B); if a deployment doesn't
        # yet maintain member_count, treat NULL as zero to be safe.
        if (main_col.get("member_count") or 0) <= 0:
            frappe.logger().info(
                f"weekly_content_delivery_trigger: skipping BPR "
                f"{bpr['name']} — main collection empty"
            )
            continue

        try:
            start_group_flow(
                flow_id=str(bpr["content_delivery_flow"]),
                group_id=str(main_col["glific_group_id"]),
            )
            frappe.logger().info(
                f"weekly_content_delivery_trigger: fired flow "
                f"{bpr['content_delivery_flow']} for BPR {bpr['name']} "
                f"(main members: {main_col.get('member_count', 0)})"
            )
        except Exception as e:
            frappe.log_error(
                f"weekly_content_delivery_trigger failed for BPR "
                f"{bpr['name']}: {e}",
                "SP Weekly Content Delivery",
            )


# ════════════════════════════════════════════════════════════
# Periodic Glific reconciliation safety net (added 2026-05-25)
# ════════════════════════════════════════════════════════════

def periodic_glific_reconcile():
    """Manual safety-net — push PE truth to Glific for every active batch.

    Status (2026-05-26): registered as a callable, but NOT wired into
    hooks.scheduler_events.cron. The */10-min cron entry was removed once
    the real root cause of the Himani / ST00051295 rendering bug was
    diagnosed as missing createContactsField definitions (fixed via
    `dev_tools.bootstrap_sp_contact_fields`), not value drift. Per L-027
    MVP discipline: production normal operation doesn't create the drift
    condition this guards against, so a continuously running cron isn't
    justified.

    When to use this function:
      - After a console session that ran multiple `frappe.db.set_value`
        calls against Glific-mirrored PE columns.
      - As a periodic operator-driven sanity check (e.g. once a week).
      - As a one-shot cleanup if the team reports gamification-card
        rendering issues that smell like drift.

    Alternatives for single-PE work:
      - `dev_tools.reconcile_pe_to_glific(pe_name)` — single PE.
      - `dev_tools.reconcile_batch_to_glific(batch_name, dry_run=True)` —
        cohort-wide read-only sweep with a per-field drift roll-up. Pass
        `dry_run=False` to push.

    Cost per invocation on a 45-PE cohort: ~45 Glific GraphQL reads +
    writes only for fields that drifted. Typical run completes in ~15
    seconds. Idempotent — re-running on a clean cohort is essentially
    free.

    Why this exists (CLAUDE.md "set_value bypasses save hooks" gotcha
    applied to Glific-mirrored PE columns):

      `frappe.db.set_value` and Frappe Desk UI edits on ProgramEnrollment
      do NOT trigger `_enqueue_contact_field_sync`. Operational backfills,
      QA manual edits, and any path that updates a Glific-mirrored column
      without going through `_apply_transition_to_pe` /
      `dev_tools.update_student_state` therefore leave Glific stale until
      the next state-machine transition happens to re-push.

      Reconcile sweep on 2026-05-25 (palv2-test-BT52231) found 16/45 PEs
      drifting on `total_points`, 2 on `archetype` + `experiment_arm`,
      and a few isolated stream-column drifts — all from set_value
      bypasses (no DLQ entries, no reset events, sync machinery healthy
      when invoked).

    What it does:
      For every active Batch (matched via active BPRs), call
      `dev_tools.reconcile_batch_to_glific(..., dry_run=False)` which
      diffs each PE's Glific-mirrored fields against the PE record and
      pushes only the fields that differ. The per-field roll-up is
      printed to the scheduler log so operators can spot systemic drift.

    Idempotency:
      `reconcile_pe_to_glific` is idempotent — re-running on a clean PE
      produces an empty diff and pushes nothing. Running often is
      essentially free for PEs that aren't drifting.

    Failure isolation:
      Per-batch try/except so one batch's failure doesn't stop the rest.
      Per-PE try/except is inside reconcile_batch_to_glific (already
      logs the FAILED status line).
    """
    from tap_lms.summer_program import dev_tools

    active_batches = frappe.db.sql(
        """
        SELECT DISTINCT batch
          FROM "tabBatchProgramRun"
         WHERE status = %s
        """,
        (BPR_ACTIVE,),
        as_dict=True,
    )

    if not active_batches:
        frappe.logger().info("periodic_glific_reconcile: no active BPRs — nothing to reconcile.")
        return

    total_pes_checked = 0
    total_pushed = 0
    total_mismatches = 0
    for row in active_batches:
        batch_name = row.batch
        if not batch_name:
            continue
        try:
            results = dev_tools.reconcile_batch_to_glific(
                batch_name, dry_run=False, verbose=False,
            )
        except Exception as e:
            frappe.log_error(
                f"periodic_glific_reconcile: batch {batch_name} failed: {e}",
                "SP Periodic Glific Reconcile",
            )
            continue

        batch_pushed = 0
        batch_mismatches = 0
        for pe_name, result in results.items():
            if "error" in result:
                continue
            total_pes_checked += 1
            diff_len = len(result.get("diff") or [])
            batch_mismatches += diff_len
            if result.get("pushed"):
                batch_pushed += 1
        total_pushed += batch_pushed
        total_mismatches += batch_mismatches

        # Only log per-batch when there's actual work — at 10-min cadence
        # the no-drift case dominates and noisy logs hide real signal.
        if batch_mismatches or batch_pushed:
            frappe.logger().info(
                f"periodic_glific_reconcile: batch={batch_name} "
                f"pes={len(results)} mismatches={batch_mismatches} "
                f"pushed={batch_pushed}"
            )

    # Roll-up logs only when work happened, same reason.
    if total_mismatches or total_pushed:
        frappe.logger().info(
            f"periodic_glific_reconcile DONE: pes={total_pes_checked} "
            f"mismatches={total_mismatches} pushed={total_pushed}"
        )
