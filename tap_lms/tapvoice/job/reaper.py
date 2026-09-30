import frappe

from tap_lms.tapvoice.constants import (
    ACTIVE_STATUSES,
    RUN_DOCTYPE,
    STATUS_DEPLOY_FAILED,
    STATUS_DEPLOYING,
    STATUS_DRAFT,
    STATUS_LOST,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    STATUS_STARTING,
    STATUS_STOPPED,
    STATUS_STOPPING,
    STATUS_TIMED_OUT,
    TERMINATION_MANUAL_ACTION_NEEDED,
    TERMINATION_PENDING,
)
from tap_lms.tapvoice.lib import runlog, runstate
from tap_lms.tapvoice.lib import secrets as secrets_lib
from tap_lms.tapvoice.lib.accounting import summarize as accounting_summarize
from tap_lms.tapvoice.lib.runpod import RunPodClient
from tap_lms.tapvoice.lib.settings import load as load_settings


def _client(settings):
    return RunPodClient(settings.runpod_api_base, secrets_lib.runpod_api_key(), settings.http_timeout_seconds)


def _force_delete(settings, client, run):
    if run.pod_id:
        try:
            client.delete_pod(run.pod_id)
        except Exception:
            frappe.log_error(title="tapvoice_reaper_delete_failed")


def _finalize(run, target_status, extra=None):
    fields = dict(extra or {})
    fields["terminated_at"] = frappe.utils.now_datetime()
    settings = load_settings()
    merged = frappe._dict(run.as_dict())
    merged.update(fields)
    acct = accounting_summarize(merged, run.hourly_rate or settings.fallback_hourly_rate_usd)
    fields.update(acct)
    fields["termination_status"] = "Verified"
    runstate.transition(run.name, run.status, target_status, fields)
    frappe.db.commit()


def reap_one(run_name):
    settings = load_settings()
    run = frappe.get_doc(RUN_DOCTYPE, run_name)
    if run.status not in ACTIVE_STATUSES:
        return False
    client = _client(settings)
    now = frappe.utils.now_datetime()

    if run.status == STATUS_STARTING:
        deadline_minutes = settings.startup_deadline_minutes
        if not run.first_contact_at and run.pod_created_at:
            elapsed = frappe.utils.time_diff_in_hours(now, run.pod_created_at) * 60
            if elapsed > deadline_minutes:
                _force_delete(settings, client, run)
                _finalize(run, STATUS_TIMED_OUT, {"status_reason": "startup_deadline_exceeded"})
                runlog.append(run_name, "reaper: startup deadline exceeded")
                return True

    if run.status == STATUS_RUNNING:
        if run.last_beat_at:
            idle_minutes = frappe.utils.time_diff_in_hours(now, run.last_beat_at) * 60
            if idle_minutes > settings.heartbeat_timeout_minutes:
                _force_delete(settings, client, run)
                _finalize(run, STATUS_LOST, {"status_reason": "heartbeat_timeout"})
                runlog.append(run_name, "reaper: heartbeat timeout")
                return True

    if run.status in ACTIVE_STATUSES and run.pod_created_at:
        max_minutes = (settings.pod_limit_max_seconds / 60.0) + settings.token_buffer_minutes
        elapsed_minutes = frappe.utils.time_diff_in_hours(now, run.pod_created_at) * 60
        if elapsed_minutes > max_minutes:
            _force_delete(settings, client, run)
            _finalize(run, STATUS_TIMED_OUT, {"status_reason": "pod_limit_exceeded"})
            runlog.append(run_name, "reaper: pod limit exceeded")
            return True

    if run.status == STATUS_STOPPING:
        stopping_since = run.last_beat_at or run.pod_created_at
        if stopping_since:
            elapsed_minutes = frappe.utils.time_diff_in_hours(now, stopping_since) * 60
            if elapsed_minutes > settings.stopping_grace_minutes:
                _force_delete(settings, client, run)
                _finalize(run, STATUS_STOPPED, {"status_reason": "stopping_grace_exceeded"})
                runlog.append(run_name, "reaper: stopping grace exceeded")
                return True

    if run.status == STATUS_DEPLOYING and not run.pod_id:
        age_minutes = frappe.utils.time_diff_in_hours(now, run.creation) * 60
        if age_minutes > 5:
            adopted = client.find_by_name(run_name)
            if adopted:
                pod_id = adopted.get("id") or adopted.get("podId")
                runstate.set_fields(
                    run_name,
                    {
                        "pod_id": pod_id,
                        "status": STATUS_STARTING,
                        "pod_created_at": frappe.utils.now_datetime(),
                    },
                )
                frappe.db.commit()
                runlog.append(run_name, f"reaper: adopted orphaned pod {pod_id}")
            else:
                runstate.set_fields(run_name, {"status": STATUS_DEPLOY_FAILED, "status_reason": "no_pod_found_by_reaper"})
                frappe.db.commit()
                runlog.append(run_name, "reaper: deploying with no pod, none found")
            return True

    return False


def _reverify_termination():
    from tap_lms.tapvoice.job.termination import verify_termination

    rows = frappe.get_all(
        RUN_DOCTYPE,
        filters={"termination_status": ["in", [TERMINATION_PENDING, TERMINATION_MANUAL_ACTION_NEEDED]]},
        fields=["name"],
    )
    for row in rows:
        try:
            verify_termination(row.name)
        except Exception:
            frappe.log_error(title="tapvoice_reaper_reverify_termination_failed")


def _reap_stale_drafts():
    cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-24)
    rows = frappe.get_all(RUN_DOCTYPE, filters={"status": STATUS_DRAFT, "creation": ["<", cutoff]}, fields=["name"])
    for row in rows:
        runstate.set_fields(row.name, {"status": STATUS_SKIPPED, "status_reason": "draft_expired"})
    if rows:
        frappe.db.commit()


def reap_runs():
    acted = 0
    active_runs = frappe.get_all(RUN_DOCTYPE, filters={"status": ["in", list(ACTIVE_STATUSES)]}, fields=["name"])
    for row in active_runs:
        try:
            if reap_one(row.name):
                acted += 1
        except Exception:
            frappe.log_error(title="tapvoice_reaper_reap_one_failed")
    _reverify_termination()
    _reap_stale_drafts()
    return {"acted": acted}