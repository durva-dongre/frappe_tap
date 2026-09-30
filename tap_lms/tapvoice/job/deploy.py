import frappe

from tap_lms.tapvoice.lib import secrets as secrets_lib
from tap_lms.tapvoice.lib import settings as settings_lib
from tap_lms.tapvoice.lib.planner import plan_batch
from tap_lms.tapvoice.lib.runpod import AmbiguousCreateError, RunPodClient, RunPodError

LOCK_KEY = "tapvoice:deploy:mutex"
LOCK_TTL_SECONDS = 300


def _acquire_mutex():
    cache = frappe.cache()
    acquired = cache.set_value(LOCK_KEY, "1", expires_in_sec=LOCK_TTL_SECONDS)
    if acquired is False:
        return False
    current = cache.get_value(LOCK_KEY)
    return current in ("1", b"1")


def _release_mutex():
    frappe.cache().delete_value(LOCK_KEY)


def deploy_new(trigger_type="Manual", triggered_by=None, force=False):
    if not _acquire_mutex():
        return {"decision": "Skip: blocked", "reason": "another deploy is in progress"}
    try:
        settings = settings_lib.load_fresh()
        if not settings.enabled:
            return {"decision": "Skip: disabled", "reason": "kill switch is off"}

        active = frappe.db.exists(
            "Tap Voice Run",
            {"status": ["in", ["Deploying", "Starting", "Running", "Stopping"]]},
        )
        if active:
            return {"decision": "Skip: blocked", "reason": f"active run {active}"}

        pending_termination = frappe.db.exists(
            "Tap Voice Run",
            {"termination_status": ["in", ["Pending", "Manual Action Needed"]]},
        )
        if pending_termination:
            return {"decision": "Skip: blocked", "reason": f"termination pending on {pending_termination}"}

        plan = plan_batch(settings, force=force)
        if plan["decision"] != "Deploy":
            run = _create_run(settings, trigger_type, triggered_by, plan, status="Skipped")
            return {"decision": plan["decision"], "reason": plan.get("reason"), "run": run.name}

        run = _create_run(settings, trigger_type, triggered_by, plan, status="Deploying")
        frappe.db.commit()

        client = RunPodClient(settings, secrets_lib.all_required())
        try:
            pod = client.create(_pod_payload(settings, run.name, plan))
        except AmbiguousCreateError:
            existing = client.find_by_name(run.name)
            if existing:
                _record_pod(run.name, existing)
            else:
                _mark_deploy_failed(run.name, "ambiguous create, no pod found on lookup")
                return {"decision": "Deploy Failed", "run": run.name}
        except RunPodError as exc:
            _mark_deploy_failed(run.name, str(exc))
            return {"decision": "Deploy Failed", "run": run.name}
        else:
            _record_pod(run.name, pod)

        return {"decision": "Deploy", "run": run.name}
    finally:
        _release_mutex()


def _pod_payload(settings, run_name, plan):
    return {
        "name": run_name,
        "imageName": settings.image_name,
        "gpuTypeIds": [line.strip() for line in (settings.gpu_type_ids or "").splitlines() if line.strip()],
        "gpuCount": settings.gpu_count,
        "cloudType": settings.cloud_type or "SECURE",
        "containerDiskInGb": settings.container_disk_gb,
        "volumeInGb": settings.volume_gb,
        "interruptible": bool(settings.interruptible),
        "env": {},
    }


def _create_run(settings, trigger_type, triggered_by, plan, status):
    doc = frappe.get_doc(
        {
            "doctype": "Tap Voice Run",
            "status": status,
            "status_reason": plan.get("reason"),
            "trigger_type": trigger_type,
            "triggered_by": triggered_by or frappe.session.user,
            "created_at": frappe.utils.now_datetime(),
            "decision": plan["decision"],
            "eligible_found": plan.get("eligible_found", 0),
            "urgent_count": plan.get("urgent_count", 0),
            "truncated_count": plan.get("truncated_count", 0),
            "estimated_cost_usd": plan.get("estimated_cost_usd", 0),
            "manifest_json": frappe.as_json(plan.get("manifest", [])),
            "manifest_count": len(plan.get("manifest", [])),
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
            "status": "Starting",
        },
    )


def _mark_deploy_failed(run_name, reason):
    from tap_lms.tapvoice.lib import runstate

    runstate.set_fields(
        run_name,
        {
            "status": "Deploy Failed",
            "status_reason": reason[:140],
        },
    )