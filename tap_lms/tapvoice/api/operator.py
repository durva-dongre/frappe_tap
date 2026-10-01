import frappe

from tap_lms.tapvoice.constants import (
    ACTIVE_STATUSES,
    MAX_URL_LENGTH,
    RUN_DOCTYPE,
    STATUS_DRAFT,
    STATUS_STOPPING,
    TRIGGER_MANUAL,
)
from tap_lms.tapvoice.lib import planner as planner_lib
from tap_lms.tapvoice.lib import runstate
from tap_lms.tapvoice.lib import secrets as secrets_lib
from tap_lms.tapvoice.lib.runpod import RunPodClient
from tap_lms.tapvoice.lib.settings import load as load_settings


def _require_system_manager():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted", frappe.PermissionError)


def _image_is_immutable(image_name):
    name = (image_name or "").strip().lower()
    if not name:
        return False
    if "@sha256:" in name:
        return True
    last = name.rsplit("/", 1)[-1]
    tag = last.split(":", 1)[1] if ":" in last else ""
    return tag not in ("", "stable", "latest")


@frappe.whitelist()
def preview_eligible():
    _require_system_manager()
    settings = load_settings()
    plan = planner_lib.plan_batch(settings)
    return {
        "decision": plan.decision,
        "reason": plan.reason,
        "eligible_found": plan.eligible_found,
        "urgent_count": plan.urgent_count,
        "truncated_count": plan.truncated_count,
        "skipped_unsupported_language": plan.skipped_unsupported_language,
        "unsupported_language_values": plan.unsupported_language_values,
        "skipped_empty_text": plan.skipped_empty_text,
        "skipped_recent_failure": plan.skipped_recent_failure,
        "skipped_flagged": plan.skipped_flagged,
        "deferred_over_budget": plan.deferred_over_budget,
        "estimated_cost_usd": plan.estimated_cost_usd,
        "estimated_seconds": plan.estimated_seconds,
        "today_spend_usd": plan.today_spend_usd,
        "month_spend_usd": plan.month_spend_usd,
    }


@frappe.whitelist()
def start_batch_manual():
    _require_system_manager()
    from tap_lms.tapvoice.job.start import start_batch

    return start_batch(TRIGGER_MANUAL)


@frappe.whitelist()
def create_draft():
    _require_system_manager()
    existing = frappe.get_all(RUN_DOCTYPE, filters={"status": STATUS_DRAFT}, limit_page_length=1)
    if existing:
        return {"name": existing[0].name, "created": False}
    settings = load_settings()
    doc = frappe.get_doc(
        {
            "doctype": RUN_DOCTYPE,
            "status": STATUS_DRAFT,
            "trigger_type": TRIGGER_MANUAL,
            "triggered_by": frappe.session.user,
            "created_at": frappe.utils.now_datetime(),
        }
    )
    for key, value in settings.snapshot().items():
        if doc.meta.has_field(key):
            doc.set(key, value)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "created": True}


@frappe.whitelist()
def deploy_run(run_name):
    _require_system_manager()
    from tap_lms.tapvoice.job.deploy import deploy

    run = frappe.get_doc(RUN_DOCTYPE, run_name)
    if run.status != STATUS_DRAFT:
        frappe.throw("Only Draft runs can be deployed")
    return deploy(run_name)


@frappe.whitelist()
def refresh_status(run_name):
    _require_system_manager()
    from tap_lms.tapvoice.job.reaper import reap_one

    run = frappe.get_doc(RUN_DOCTYPE, run_name)
    if run.status in ACTIVE_STATUSES and run.pod_id:
        settings = load_settings()
        client = RunPodClient(
            settings.runpod_api_base, secrets_lib.runpod_api_key(), settings.http_timeout_seconds
        )
        pod = client.get_pod(run.pod_id)
        if pod:
            rate = pod.get("costPerHr") or pod.get("hourly_rate")
            if rate:
                runstate.set_fields(run.name, {"hourly_rate": rate})
    reap_one(run_name)
    return {"status": frappe.db.get_value(RUN_DOCTYPE, run_name, "status")}


@frappe.whitelist()
def cancel_run(run_name):
    _require_system_manager()
    run = frappe.get_doc(RUN_DOCTYPE, run_name)
    if run.status not in ACTIVE_STATUSES:
        frappe.throw("Run is not active")
    runstate.transition(run_name, run.status, STATUS_STOPPING)
    return {"status": STATUS_STOPPING}


@frappe.whitelist()
def force_terminate(run_name):
    _require_system_manager()
    from tap_lms.tapvoice.job.termination import force_delete_now

    return force_delete_now(run_name)


@frappe.whitelist()
def verify_termination(run_name):
    _require_system_manager()
    from tap_lms.tapvoice.job.termination import verify_termination as verify

    return verify(run_name)


@frappe.whitelist()
def run_reaper_now():
    _require_system_manager()
    from tap_lms.tapvoice.job.reaper import reap_runs

    return reap_runs()


@frappe.whitelist()
def check_setup():
    _require_system_manager()
    settings = load_settings()
    results = {}

    missing_secrets = secrets_lib.check_all_present()
    results["secrets"] = {"ok": not missing_secrets, "missing": missing_secrets}

    results["https_base_url"] = {
        "ok": settings.public_base_url.startswith("https://"),
        "value": settings.public_base_url,
    }

    results["alert_email"] = {"ok": bool(settings.alert_email)}

    results["gpu_type_ids"] = {"ok": bool(settings.gpu_type_ids)}

    results["image_name"] = {
        "ok": _image_is_immutable(settings.image_name),
        "value": settings.image_name or "empty",
    }

    results["model_revision"] = {
        "ok": bool((settings.model_revision or "").strip()),
        "value": settings.model_revision or "empty",
    }

    max_len = len(settings.cdn_base_url) + 1 + len(settings.gcs_prefix) + 1 + len("marathi") + 1 + 32 + 4
    results["url_length"] = {"ok": max_len <= MAX_URL_LENGTH, "max_len": max_len}

    try:
        key = secrets_lib.runpod_api_key()
        client = RunPodClient(settings.runpod_api_base, key, settings.http_timeout_seconds)
        client.ping()
        results["runpod_key"] = {"ok": True}
    except Exception as exc:
        results["runpod_key"] = {"ok": False, "error": str(exc)}

    results["all_ok"] = all(v.get("ok") for v in results.values() if isinstance(v, dict))
    return results