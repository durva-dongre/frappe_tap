import frappe

from tap_lms.tapvoice.constants import (
    ACTIVE_STATUSES,
    DECISION_DEPLOY,
    DECISION_SKIP_BLOCKED,
    DECISION_SKIP_DISABLED,
    RUN_DOCTYPE,
    SECRET_TTS_GCS_SERVICE_ACCOUNT_JSON_B64,
    SECRET_TTS_POD_SHARED_SECRET,
    STATUS_DEPLOY_FAILED,
    STATUS_DEPLOYING,
    STATUS_DRAFT,
    STATUS_SKIPPED,
    STATUS_STARTING,
    TERMINATION_MANUAL_ACTION_NEEDED,
    TERMINATION_NOT_NEEDED,
    TERMINATION_PENDING,
    TRIGGER_MANUAL,
)
from tap_lms.tapvoice.lib import planner as planner_lib
from tap_lms.tapvoice.lib import runlog, runstate
from tap_lms.tapvoice.lib import secrets as secrets_lib
from tap_lms.tapvoice.lib import tokens as tokens_lib
from tap_lms.tapvoice.lib.runpod import RunPodClient, RunPodError, build_create_payload
from tap_lms.tapvoice.lib.settings import api_path_prefix
from tap_lms.tapvoice.lib.settings import load as load_settings

LOCK_KEY = "tapvoice:deploy_mutex"
LOCK_TTL_SECONDS = 60


def _acquire_mutex():
    cache = frappe.cache()
    acquired = cache.set_value(LOCK_KEY, "1", expires_in_sec=LOCK_TTL_SECONDS, nx=True)
    return bool(acquired)


def _release_mutex():
    frappe.cache().delete_value(LOCK_KEY)


def _has_blocking_run():
    active = frappe.get_all(RUN_DOCTYPE, filters={"status": ["in", list(ACTIVE_STATUSES)]}, limit_page_length=1)
    if active:
        return True
    blocked_termination = frappe.get_all(
        RUN_DOCTYPE,
        filters={"termination_status": ["in", [TERMINATION_PENDING, TERMINATION_MANUAL_ACTION_NEEDED]]},
        limit_page_length=1,
    )
    return bool(blocked_termination)


def _runs_today_count():
    start = frappe.utils.get_datetime(frappe.utils.nowdate())
    return frappe.db.count(RUN_DOCTYPE, filters={"creation": [">=", start]})


def _minutes_since_last_run():
    last = frappe.get_all(
        RUN_DOCTYPE,
        filters={"status": ["not in", [STATUS_DRAFT]]},
        fields=["creation"],
        order_by="creation desc",
        limit_page_length=1,
    )
    if not last:
        return None
    return frappe.utils.time_diff_in_hours(frappe.utils.now_datetime(), last[0].creation) * 60


def _create_run_row(trigger, settings):
    doc = frappe.get_doc(
        {
            "doctype": RUN_DOCTYPE,
            "status": STATUS_DEPLOYING,
            "trigger_type": trigger,
            "triggered_by": frappe.session.user,
            "created_at": frappe.utils.now_datetime(),
            "termination_status": TERMINATION_NOT_NEEDED,
        }
    )
    for key, value in settings.snapshot().items():
        if doc.meta.has_field(key):
            doc.set(key, value)
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def deploy_new(trigger=TRIGGER_MANUAL):
    if not _acquire_mutex():
        return {"queued": False, "reason": "mutex_busy"}
    try:
        settings = load_settings()
        if not settings.kill_switch_on():
            return {"deployed": False, "reason": DECISION_SKIP_DISABLED}

        if _has_blocking_run():
            return {"deployed": False, "reason": DECISION_SKIP_BLOCKED}

        if _runs_today_count() >= settings.max_runs_per_day:
            return {"deployed": False, "reason": "max_runs_per_day"}

        minutes_since = _minutes_since_last_run()
        if minutes_since is not None and minutes_since < settings.min_minutes_between_runs:
            return {"deployed": False, "reason": "min_minutes_between_runs"}

        missing = secrets_lib.check_all_present()
        if missing:
            return {"deployed": False, "reason": f"missing_secrets:{','.join(missing)}"}

        run = _create_run_row(trigger, settings)
        frappe.db.commit()
    finally:
        _release_mutex()

    return _continue_deploy(run.name)


def deploy(run_name):
    return _continue_deploy(run_name, from_draft=True)


def _continue_deploy(run_name, from_draft=False):
    settings = load_settings()
    run = frappe.get_doc(RUN_DOCTYPE, run_name)

    if from_draft:
        runstate.transition(run_name, run.status, STATUS_DEPLOYING)
        frappe.db.commit()
        run.reload()

    plan = planner_lib.plan_batch(settings, force=(run.trigger_type == TRIGGER_MANUAL))

    decision_fields = {
        "eligible_found": plan.eligible_found,
        "urgent_count": plan.urgent_count,
        "truncated_count": plan.truncated_count,
        "skipped_unsupported_language": plan.skipped_unsupported_language,
        "unsupported_language_values": frappe.as_json(plan.unsupported_language_values),
        "skipped_empty_text": plan.skipped_empty_text,
        "skipped_recent_failure": plan.skipped_recent_failure,
        "skipped_flagged": plan.skipped_flagged,
        "deferred_over_budget": plan.deferred_over_budget,
        "estimated_cost_usd": plan.estimated_cost_usd,
        "decision": plan.decision,
        "status_reason": plan.reason,
    }
    runstate.set_fields(run_name, decision_fields)
    runlog.append(run_name, f"plan: {plan.decision} - {plan.reason}")

    if plan.decision != DECISION_DEPLOY:
        runstate.transition(run_name, STATUS_DEPLOYING, STATUS_SKIPPED)
        frappe.db.commit()
        return {"deployed": False, "reason": plan.decision}

    manifest_items = [
        {"id": item.id, "language": item.language, "fingerprint": item.fingerprint, "text": item.text}
        for item in plan.items
    ]
    runstate.set_fields(
        run_name,
        {
            "manifest_json": frappe.as_json(manifest_items),
            "manifest_count": len(manifest_items),
        },
    )
    frappe.db.commit()

    run.reload()
    recheck_plan = planner_lib.plan_batch(settings, force=True)
    still_available = {item.id for item in recheck_plan.items}
    surviving = [entry for entry in manifest_items if entry["id"] in still_available]
    if not surviving:
        runstate.transition(run_name, STATUS_DEPLOYING, STATUS_SKIPPED)
        frappe.db.commit()
        return {"deployed": False, "reason": "recount_empty"}

    token_secret = secrets_lib.get(SECRET_TTS_POD_SHARED_SECRET)
    run_token = tokens_lib.issue(
        run_name, token_secret, settings.pod_limit_max_seconds // 60 + settings.token_buffer_minutes
    )

    gcs_b64 = secrets_lib.get(SECRET_TTS_GCS_SERVICE_ACCOUNT_JSON_B64)
    pod_api_key = secrets_lib.runpod_pod_api_key()

    env = {
        "SERVER_URL": settings.public_base_url,
        "API_PATH_PREFIX": api_path_prefix(settings),
        "RUN_ID": run_name,
        "RUN_TOKEN": run_token,
        "GCS_BUCKET": settings.gcs_bucket,
        "GCS_PREFIX": settings.gcs_prefix,
        "CDN_BASE_URL": settings.cdn_base_url,
        "MODEL_REVISION": settings.model_revision,
        "GCS_SERVICE_ACCOUNT_JSON_B64": gcs_b64,
        "RUNPOD_API_KEY": pod_api_key,
        "POD_LIMIT_SECONDS": str(
            min(
                settings.pod_limit_max_seconds,
                int(len(surviving) * settings.seconds_per_item_cap) + settings.est_startup_seconds * 2,
            )
        ),
        "SECONDS_PER_ITEM_CAP": str(settings.seconds_per_item_cap),
        "MAX_NUM_SEQS": str(settings.max_num_seqs),
        "DECODE_MICROBATCH": str(settings.decode_microbatch),
        "GPU_MEMORY_UTILIZATION": str(settings.gpu_memory_utilization),
        "MAX_SPEND_USD": str(settings.max_cost_per_run_usd),
        "GPU_HOURLY_RATE": str(settings.fallback_hourly_rate_usd),
        "MAX_ITEMS": str(settings.max_clips_per_run),
        "MAX_TEXT_CHARS": str(settings.max_text_chars()),
    }

    client = RunPodClient(settings.runpod_api_base, secrets_lib.runpod_api_key(), settings.http_timeout_seconds)
    payload = build_create_payload(settings, run_name, env)

    try:
        response = client.create_pod(payload)
        pod_id = response.get("id") or response.get("podId")
        hourly_rate = response.get("costPerHr") or response.get("hourly_rate") or settings.fallback_hourly_rate_usd
        if not pod_id:
            raise RunPodError("no_pod_id_in_response")
        runstate.transition(
            run_name,
            STATUS_DEPLOYING,
            STATUS_STARTING,
            {
                "pod_id": pod_id,
                "pod_name": run_name,
                "hourly_rate": hourly_rate,
                "gpu_type_allocated": response.get("gpuTypeId") or response.get("gpu_type_id"),
                "pod_created_at": frappe.utils.now_datetime(),
            },
        )
        frappe.db.commit()
        runlog.append(run_name, f"pod created id={pod_id}")
        return {"deployed": True, "pod_id": pod_id}
    except RunPodError as exc:
        runlog.append(run_name, f"create_pod failed: {exc.summary}")
        adopted = client.find_by_name(run_name)
        if adopted:
            pod_id = adopted.get("id") or adopted.get("podId")
            runstate.transition(
                run_name,
                STATUS_DEPLOYING,
                STATUS_STARTING,
                {
                    "pod_id": pod_id,
                    "pod_name": run_name,
                    "hourly_rate": adopted.get("costPerHr") or settings.fallback_hourly_rate_usd,
                    "pod_created_at": frappe.utils.now_datetime(),
                },
            )
            frappe.db.commit()
            runlog.append(run_name, f"adopted ambiguous pod id={pod_id}")
            return {"deployed": True, "pod_id": pod_id, "adopted": True}
        runstate.transition(
            run_name,
            STATUS_DEPLOYING,
            STATUS_DEPLOY_FAILED,
            {"status_reason": exc.summary},
        )
        frappe.db.commit()
        return {"deployed": False, "reason": "deploy_failed", "detail": exc.summary}