import frappe

from tap_lms.tapvoice.constants import (
    ACTIVE_STATUSES,
    DECISION_DEPLOY,
    DECISION_SKIP_BLOCKED,
    DECISION_SKIP_DISABLED,
    RUN_DOCTYPE,
    STATUS_DEPLOY_FAILED,
    STATUS_DEPLOYING,
    STATUS_SKIPPED,
    STATUS_STARTING,
    TERMINATION_MANUAL_ACTION_NEEDED,
    TERMINATION_PENDING,
)
from tap_lms.tapvoice.lib import secrets as secrets_lib
from tap_lms.tapvoice.lib import settings as settings_lib
from tap_lms.tapvoice.lib.planner import plan_batch
from tap_lms.tapvoice.lib.runpod import RunPodClient, RunPodError, build_create_payload

LOCK_KEY = "tapvoice:deploy:mutex"
LOCK_TTL_SECONDS = 300


def _acquire_mutex():
    acquired = frappe.cache().set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    return bool(acquired)


def _release_mutex():
    frappe.cache().delete(LOCK_KEY)


def deploy_new(trigger_type="Manual", triggered_by=None, force=False):
    if not _acquire_mutex():
        return {"deployed": False, "reason": DECISION_SKIP_BLOCKED}
    try:
        settings = settings_lib.load_fresh()
        if not settings.kill_switch_on():
            return {"deployed": False, "reason": DECISION_SKIP_DISABLED}

        active = frappe.db.exists(RUN_DOCTYPE, {"status": ["in", list(ACTIVE_STATUSES)]})
        if active:
            return {"deployed": False, "reason": DECISION_SKIP_BLOCKED}

        pending_termination = frappe.db.exists(
            RUN_DOCTYPE,
            {"termination_status": ["in", [TERMINATION_PENDING, TERMINATION_MANUAL_ACTION_NEEDED]]},
        )
        if pending_termination:
            return {"deployed": False, "reason": DECISION_SKIP_BLOCKED}

        plan = plan_batch(settings, force=force)
        if plan.decision != DECISION_DEPLOY:
            run = _create_run(settings, trigger_type, triggered_by, plan, status=STATUS_SKIPPED)
            return {"deployed": False, "reason": plan.decision, "run": run.name}

        run = _create_run(settings, trigger_type, triggered_by, plan, status=STATUS_DEPLOYING)
        frappe.db.commit()

        client = RunPodClient(settings.runpod_api_base, secrets_lib.runpod_pod_api_key(), settings.http_timeout_seconds)
        payload = build_create_payload(settings, run.name, {})
        try:
            pod = client.create_pod(payload)
        except RunPodError as exc:
            existing = client.find_by_name(run.name)
            if existing:
                _record_pod(run.name, existing)
                return {"deployed": True, "adopted": True, "run": run.name}
            _mark_deploy_failed(run.name, str(exc))
            return {"deployed": False, "reason": STATUS_DEPLOY_FAILED, "run": run.name}
        else:
            _record_pod(run.name, pod)

        return {"deployed": True, "run": run.name}
    finally:
        _release_mutex()


def _create_run(settings, trigger_type, triggered_by, plan, status):
    doc = frappe.get_doc(
        {
            "doctype": RUN_DOCTYPE,
            "status": status,
            "status_reason": plan.reason,
            "trigger_type": trigger_type,
            "triggered_by": triggered_by or frappe.session.user,
            "created_at": frappe.utils.now_datetime(),
            "decision": plan.decision,
            "eligible_found": plan.eligible_found,
            "urgent_count": plan.urgent_count,
            "truncated_count": plan.truncated_count,
            "estimated_cost_usd": plan.estimated_cost_usd,
            "manifest_json": frappe.as_json(
                [{"id": item.id, "language": item.language, "fingerprint": item.text} for item in plan.items]
            ),
            "manifest_count": len(plan.items),
            "termination_status": "Not Needed",
        }
    )
    doc.insert(ignore_permissions=True)
    return doc


def _record_pod(run_name, pod):
    from tap_lms.tapvoice.lib import runstate

    runstate.set_fields(
        run_name,
        {
            "pod_id": pod.get("id"),
            "pod_name": pod.get("name"),
            "hourly_rate": pod.get("costPerHr") or 0,
            "gpu_type_allocated": pod.get("gpuTypeId"),
            "pod_created_at": frappe.utils.now_datetime(),
            "status": STATUS_STARTING,
        },
    )


def _mark_deploy_failed(run_name, reason):
    from tap_lms.tapvoice.lib import runstate

    runstate.set_fields(
        run_name,
        {
            "status": STATUS_DEPLOY_FAILED,
            "status_reason": str(reason)[:140],
        },
    )