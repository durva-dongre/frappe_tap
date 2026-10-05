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
    TERMINATION_PENDING,
)
from tap_lms.tapvoice.lib import runlog, runstate, tokens
from tap_lms.tapvoice.lib import secrets as secrets_lib
from tap_lms.tapvoice.lib import settings as settings_lib
from tap_lms.tapvoice.lib import text as text_lib
from tap_lms.tapvoice.lib.planner import plan_batch
from tap_lms.tapvoice.lib.runpod import (
    RunPodClient,
    RunPodError,
    build_create_payload,
    is_capacity_error,
)

LOCK_KEY = "tapvoice:deploy:mutex"
LOCK_TTL_SECONDS = 300
DECISION_SKIP_LIMITS = "Skip: limits"
WAITING_FOR_CAPACITY = "waiting_for_capacity"


def _acquire_mutex():
    acquired = frappe.cache().set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    return bool(acquired)


def _release_mutex():
    frappe.cache().delete(LOCK_KEY)


def _blocker(settings):
    if not settings.kill_switch_on():
        return DECISION_SKIP_DISABLED, "disabled"
    if not (settings.image_name or "").strip() or not (settings.model_revision or "").strip():
        return DECISION_SKIP_BLOCKED, "image_name or model_revision is empty"
    missing = secrets_lib.check_all_present()
    if missing:
        return DECISION_SKIP_BLOCKED, "missing secrets: " + ",".join(missing)
    if frappe.db.exists(RUN_DOCTYPE, {"status": ["in", list(ACTIVE_STATUSES)]}):
        return DECISION_SKIP_BLOCKED, "another run is active"
    if frappe.db.exists(
        RUN_DOCTYPE,
        {"termination_status": ["in", [TERMINATION_PENDING, TERMINATION_MANUAL_ACTION_NEEDED]]},
    ):
        return DECISION_SKIP_BLOCKED, "a pod termination is unverified"
    started = frappe.get_all(
        RUN_DOCTYPE,
        filters={
            "status": ["not in", [STATUS_DRAFT, STATUS_SKIPPED]],
            "creation": [">=", frappe.utils.get_datetime(frappe.utils.nowdate())],
        },
        fields=["creation"],
        order_by="creation desc",
    )
    if len(started) >= (settings.max_runs_per_day or 0):
        return DECISION_SKIP_LIMITS, "max runs per day reached"
    if started and settings.min_minutes_between_runs:
        gap = frappe.utils.time_diff_in_seconds(frappe.utils.now_datetime(), started[0].creation) / 60.0
        if gap < settings.min_minutes_between_runs:
            return DECISION_SKIP_LIMITS, "minimum gap between runs not reached"
    return None


def _plan_fields(plan):
    return {
        "status_reason": plan.reason,
        "decision": plan.decision,
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
        "manifest_json": frappe.as_json(
            [
                {
                    "id": item.id,
                    "language": item.language,
                    "fingerprint": text_lib.fingerprint(item.text, item.language),
                }
                for item in plan.items
            ]
        ),
        "manifest_count": len(plan.items),
    }


def _new_run(settings, trigger_type, triggered_by, status, extra):
    doc = frappe.get_doc(
        {
            "doctype": RUN_DOCTYPE,
            "status": status,
            "trigger_type": trigger_type,
            "triggered_by": triggered_by or frappe.session.user,
            "created_at": frappe.utils.now_datetime(),
            "termination_status": "Not Needed",
        }
    )
    for key, value in settings.snapshot().items():
        if doc.meta.has_field(key):
            doc.set(key, value)
    for key, value in extra.items():
        doc.set(key, value)
    doc.insert(ignore_permissions=True)
    return doc


def _env(settings, run_name, count):
    shared = secrets_lib.get(SECRET_TTS_POD_SHARED_SECRET)
    ttl_minutes = int(settings.pod_limit_max_seconds / 60) + int(settings.token_buffer_minutes)
    per_item = settings.seconds_per_item_cap or 3.0
    limit = int(max(180, min(settings.pod_limit_max_seconds, count * per_item + 600)))
    env = {
        "SERVER_URL": settings.public_base_url,
        "API_PATH_PREFIX": settings_lib.api_path_prefix(settings),
        "RUN_ID": run_name,
        "RUN_TOKEN": tokens.issue(run_name, shared, ttl_minutes),
        "GCS_BUCKET": settings.gcs_bucket,
        "GCS_PREFIX": settings.gcs_prefix,
        "CDN_BASE_URL": settings.cdn_base_url,
        "MODEL_REVISION": settings.model_revision,
        "GCS_SERVICE_ACCOUNT_JSON_B64": secrets_lib.get(SECRET_TTS_GCS_SERVICE_ACCOUNT_JSON_B64),
        "RUNPOD_API_KEY": secrets_lib.runpod_pod_api_key(),
        "POD_LIMIT_SECONDS": limit,
        "SECONDS_PER_ITEM_CAP": per_item,
        "MAX_NUM_SEQS": settings.max_num_seqs,
        "DECODE_MICROBATCH": settings.decode_microbatch,
        "GPU_MEMORY_UTILIZATION": settings.gpu_memory_utilization,
        "MAX_SPEND_USD": settings.max_cost_per_run_usd,
        "GPU_HOURLY_RATE": settings.fallback_hourly_rate_usd,
        "MAX_ITEMS": settings.max_clips_per_run,
        "MAX_TEXT_CHARS": settings.max_text_chars(),
    }
    return {key: str(value) for key, value in env.items()}


def _launch(settings, run_name, count):
    try:
        client = RunPodClient(
            settings.runpod_api_base, secrets_lib.runpod_api_key(), settings.http_timeout_seconds
        )
        payload = build_create_payload(settings, run_name, _env(settings, run_name, count))
        try:
            pod = client.create_pod(payload)
        except RunPodError as exc:
            existing = None
            try:
                existing = client.find_by_name(run_name)
            except RunPodError:
                pass
            if existing:
                _record_pod(run_name, existing)
                frappe.db.commit()
                return {"deployed": True, "adopted": True, "run": run_name}
            if is_capacity_error(exc):
                return _schedule_capacity_retry(settings, run_name, str(exc))
            _mark_deploy_failed(run_name, str(exc))
            frappe.db.commit()
            return {"deployed": False, "reason": STATUS_DEPLOY_FAILED, "run": run_name}
        _record_pod(run_name, pod)
        frappe.db.commit()
        return {"deployed": True, "run": run_name}
    except Exception as exc:
        frappe.log_error(title="tapvoice_launch_failed")
        _mark_deploy_failed(run_name, f"{type(exc).__name__}: {exc}")
        frappe.db.commit()
        return {"deployed": False, "reason": STATUS_DEPLOY_FAILED, "run": run_name}


def _schedule_capacity_retry(settings, run_name, detail):
    row = frappe.db.get_value(
        RUN_DOCTYPE, run_name, ["capacity_wait_started_at", "capacity_retry_count"], as_dict=True
    )
    now = frappe.utils.now_datetime()
    started = row.capacity_wait_started_at or now
    attempts = (row.capacity_retry_count or 0) + 1
    deadline = frappe.utils.add_to_date(started, minutes=int(settings.capacity_retry_max_minutes or 60))
    next_at = frappe.utils.add_to_date(now, minutes=int(settings.capacity_retry_interval_minutes or 3))
    if next_at > deadline:
        runlog.append(run_name, f"no capacity after {attempts} attempts, giving up")
        _mark_deploy_failed(run_name, f"no_capacity_after_{attempts}_attempts")
        frappe.db.commit()
        return {"deployed": False, "reason": STATUS_DEPLOY_FAILED, "run": run_name}
    runstate.set_fields(
        run_name,
        {
            "capacity_wait_started_at": started,
            "capacity_retry_count": attempts,
            "next_capacity_retry_at": next_at,
            "status_reason": f"{WAITING_FOR_CAPACITY} attempt {attempts}",
        },
    )
    runlog.append(run_name, f"no capacity (attempt {attempts}), retry at {next_at}: {detail}")
    frappe.db.commit()
    return {
        "deployed": False,
        "reason": WAITING_FOR_CAPACITY,
        "run": run_name,
        "retry_at": str(next_at),
    }


def retry_capacity(run_name):
    if not _acquire_mutex():
        return {"deployed": False, "reason": DECISION_SKIP_BLOCKED}
    try:
        settings = settings_lib.load_fresh()
        row = frappe.db.get_value(
            RUN_DOCTYPE, run_name, ["status", "pod_id", "manifest_count"], as_dict=True
        )
        if not row or row.status != STATUS_DEPLOYING or row.pod_id:
            return {"deployed": False, "reason": "not_waiting"}
        if not settings.kill_switch_on():
            _mark_deploy_failed(run_name, "disabled_while_waiting_for_capacity")
            frappe.db.commit()
            return {"deployed": False, "reason": DECISION_SKIP_DISABLED, "run": run_name}
        lease = frappe.utils.add_to_date(
            frappe.utils.now_datetime(), minutes=int(settings.capacity_retry_interval_minutes or 3)
        )
        runstate.set_fields(run_name, {"next_capacity_retry_at": lease})
        frappe.db.commit()
        return _launch(settings, run_name, row.manifest_count or 0)
    finally:
        _release_mutex()


def deploy_new(trigger_type="Manual", triggered_by=None, force=False):
    if not _acquire_mutex():
        return {"deployed": False, "reason": DECISION_SKIP_BLOCKED}
    try:
        settings = settings_lib.load_fresh()
        blocker = _blocker(settings)
        if blocker:
            decision, reason = blocker
            run = _new_run(
                settings, trigger_type, triggered_by, STATUS_SKIPPED,
                {"decision": decision, "status_reason": reason},
            )
            frappe.db.commit()
            return {"deployed": False, "reason": decision, "run": run.name}
        plan = plan_batch(settings, force=force)
        if plan.decision != DECISION_DEPLOY:
            run = _new_run(settings, trigger_type, triggered_by, STATUS_SKIPPED, _plan_fields(plan))
            frappe.db.commit()
            return {"deployed": False, "reason": plan.decision, "run": run.name}
        run = _new_run(settings, trigger_type, triggered_by, STATUS_DEPLOYING, _plan_fields(plan))
        frappe.db.commit()
        return _launch(settings, run.name, len(plan.items))
    finally:
        _release_mutex()


def deploy(run_name):
    if not _acquire_mutex():
        return {"deployed": False, "reason": DECISION_SKIP_BLOCKED}
    try:
        settings = settings_lib.load_fresh()
        blocker = _blocker(settings)
        if blocker:
            return {"deployed": False, "reason": blocker[0], "detail": blocker[1]}
        plan = plan_batch(settings, force=True)
        if plan.decision != DECISION_DEPLOY:
            runstate.set_fields(run_name, dict(_plan_fields(plan), status=STATUS_SKIPPED))
            frappe.db.commit()
            return {"deployed": False, "reason": plan.decision, "run": run_name}
        runstate.transition(run_name, STATUS_DRAFT, STATUS_DEPLOYING, _plan_fields(plan))
        frappe.db.commit()
        return _launch(settings, run_name, len(plan.items))
    finally:
        _release_mutex()


def _record_pod(run_name, pod):
    runstate.set_fields(
        run_name,
        {
            "pod_id": pod.get("id") or pod.get("podId"),
            "pod_name": pod.get("name"),
            "hourly_rate": pod.get("costPerHr") or 0,
            "gpu_type_allocated": pod.get("gpuTypeId") or "",
            "pod_created_at": frappe.utils.now_datetime(),
            "next_capacity_retry_at": None,
            "status": STATUS_STARTING,
        },
    )


def _mark_deploy_failed(run_name, reason):
    runstate.set_fields(
        run_name,
        {
            "status": STATUS_DEPLOY_FAILED,
            "status_reason": str(reason)[:140],
            "next_capacity_retry_at": None,
        },
    )