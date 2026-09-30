import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError

import frappe
import requests

from tap_lms.tapvoice.constants import (
    FAILED_ITEMS_MAX_ENTRIES,
    FAILURE_REASONS_MAX_ENTRIES,
    FORMAT_OGG,
    HEAD_CHECK_BATCH_BUDGET_SECONDS,
    HEAD_CHECK_MAX_WORKERS,
    HEAD_CHECK_TIMEOUT_SECONDS,
    OUTCOME_ALREADY_SET,
    OUTCOME_BAD_URL,
    OUTCOME_CHANGED_DURING_WRITE,
    OUTCOME_HASH_MISMATCH,
    OUTCOME_NOT_IN_MANIFEST,
    OUTCOME_RECORDED_FAILURE,
    OUTCOME_STALE,
    OUTCOME_SUBMISSION_FAILED,
    OUTCOME_WRITTEN,
    POD_BREAKER_PREFIX,
    POD_REASON_COMPLETED,
    POD_REASON_COMPLETED_WITH_FAILURES,
    POD_REASON_EMPTY,
    POD_REASON_EXCEPTION,
    POD_REASON_STARTUP_TIMEOUT,
    POD_REASON_STOPPED,
    POD_REASON_TIMEOUT,
    PROGRESS_MAX_RECORDS,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_FAILURES,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_STARTING,
    STATUS_STOPPED,
    STATUS_STOPPING,
    STATUS_TIMED_OUT,
)
from tap_lms.tapvoice.lib import breaker as breaker_lib
from tap_lms.tapvoice.lib import contract, runlog, runstate
from tap_lms.tapvoice.lib.eligibility import SUBMISSION_DOCTYPE
from tap_lms.tapvoice.lib.guard import GuardStop, enter
from tap_lms.tapvoice.lib.settings import load as load_settings
from tap_lms.tapvoice.lib.text import prepare as prepare_text


def _respond_stop(exc):
    frappe.local.response.http_status_code = exc.http_code
    return {"error": exc.message}


def _no_store():
    frappe.local.response["Cache-Control"] = "no-store"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def manifest():
    _no_store()
    try:
        run = enter("manifest")
    except GuardStop as exc:
        return _respond_stop(exc)

    settings = load_settings()

    if run.status not in (STATUS_STARTING, STATUS_RUNNING):
        frappe.local.response.http_status_code = 409
        return {"error": "wrong_phase"}

    fields = {}
    if not run.first_contact_at:
        fields["first_contact_at"] = frappe.utils.now_datetime()
    if run.status == STATUS_STARTING:
        fields["status"] = STATUS_RUNNING
    if run.manifest_served_at is None:
        fields["manifest_served_at"] = frappe.utils.now_datetime()
    runstate.set_fields(run.name, fields)

    try:
        manifest_items = frappe.parse_json(run.manifest_json) or []
    except Exception:
        manifest_items = []

    ids = [entry["id"] for entry in manifest_items]
    fingerprint_by_id = {entry["id"]: entry["fingerprint"] for entry in manifest_items}

    if not ids:
        runlog.append(run.name, "manifest served 0 items")
        return {"items": []}

    rows = frappe.get_all(
        SUBMISSION_DOCTYPE,
        filters={"name": ["in", ids]},
        fields=["name", "status", "overall_feedback_translated", "translation_language", "audio_feedback_url"],
    )
    rows_by_id = {row.name: row for row in rows}

    out_items = []
    stale = 0
    for item_id in ids:
        row = rows_by_id.get(item_id)
        if row is None:
            stale += 1
            continue
        if row.status == STATUS_FAILED:
            stale += 1
            continue
        if row.audio_feedback_url:
            stale += 1
            continue
        prepared = prepare_text(
            row.overall_feedback_translated or "",
            row.translation_language,
            settings.max_text_chars(),
            settings.over_length_policy,
        )
        if prepared is None or prepared.fingerprint != fingerprint_by_id.get(item_id):
            stale += 1
            continue
        out_items.append(
            {
                "id": item_id,
                "text": prepared.text,
                "language": prepared.language,
                "format": FORMAT_OGG,
            }
        )

    runstate.set_fields(run.name, {"served_count": len(out_items)})
    runlog.append(run.name, f"manifest served {len(out_items)} items, {stale} stale")
    return {"items": out_items}


def _expected_for(item_id, manifest_by_id, settings):
    entry = manifest_by_id.get(item_id)
    if entry is None:
        return None, None, None
    expected_hash = contract.expected_hash(entry["text"], entry["language"], settings.model_revision)
    expected_url = contract.expected_url(
        entry["text"], entry["language"], settings.model_revision, settings.gcs_prefix, settings.cdn_base_url
    )
    return entry, expected_hash, expected_url


def _head_check(url):
    try:
        response = requests.head(url, timeout=HEAD_CHECK_TIMEOUT_SECONDS, allow_redirects=True)
        return response.status_code == 200
    except Exception:
        return False


def _verify_urls(urls):
    if not urls:
        return {}
    verified = {}
    deadline = time.monotonic() + HEAD_CHECK_BATCH_BUDGET_SECONDS
    workers = min(HEAD_CHECK_MAX_WORKERS, max(1, len(urls)))
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = {pool.submit(_head_check, url): url for url in urls}
    try:
        remaining = max(0.1, deadline - time.monotonic())
        for future in as_completed(futures, timeout=remaining):
            url = futures[future]
            try:
                verified[url] = bool(future.result())
            except Exception:
                verified[url] = False
    except FuturesTimeoutError:
        pass
    finally:
        pool.shutdown(wait=False)
    for url in urls:
        verified.setdefault(url, False)
    return verified


def _bounded_update(existing, updates, max_entries):
    merged = dict(existing)
    merged.update(updates)
    if len(merged) > max_entries:
        overflow = len(merged) - max_entries
        for key in list(merged.keys())[:overflow]:
            del merged[key]
    return merged


@frappe.whitelist(allow_guest=True, methods=["POST"])
def progress():
    _no_store()
    try:
        run = enter("progress")
    except GuardStop as exc:
        return _respond_stop(exc)

    settings = load_settings()
    payload = frappe.local.form_dict
    records = payload.get("records") or []
    if len(records) > PROGRESS_MAX_RECORDS:
        records = records[:PROGRESS_MAX_RECORDS]

    try:
        manifest_items = frappe.parse_json(run.manifest_json) or []
    except Exception:
        manifest_items = []
    manifest_by_id = {entry["id"]: entry for entry in manifest_items}

    ids = [r.get("id") for r in records if r.get("id")]
    submission_rows = {}
    if ids:
        rows = frappe.get_all(
            SUBMISSION_DOCTYPE,
            filters={"name": ["in", ids]},
            fields=["name", "status", "modified", "audio_feedback_url"],
        )
        submission_rows = {row.name: row for row in rows}

    results = [None] * len(records)
    counters = {
        "written": 0,
        "already_set": 0,
        "stale": 0,
        "hash_mismatch": 0,
        "bad_url": 0,
        "not_in_manifest": 0,
        "changed_during_write": 0,
        "pod_failed": 0,
    }
    failed_items = {}
    failure_reasons = {}
    pending = []
    urls_to_verify = set()

    for position, record in enumerate(records):
        item_id = record.get("id")
        status = record.get("status")
        if not item_id or item_id not in manifest_by_id:
            results[position] = {"id": item_id, "outcome": OUTCOME_NOT_IN_MANIFEST}
            counters["not_in_manifest"] += 1
            continue

        if status == "failed":
            reason = record.get("error") or "unknown"
            failed_items[item_id] = reason
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            counters["pod_failed"] += 1
            results[position] = {"id": item_id, "outcome": OUTCOME_RECORDED_FAILURE}
            continue

        entry, expected_hash, expected_url = _expected_for(item_id, manifest_by_id, settings)
        sub_row = submission_rows.get(item_id)

        if sub_row is None:
            results[position] = {"id": item_id, "outcome": OUTCOME_STALE}
            counters["stale"] += 1
            continue

        if sub_row.status == STATUS_FAILED:
            results[position] = {"id": item_id, "outcome": OUTCOME_SUBMISSION_FAILED}
            continue

        reported_hash = record.get("content_hash")
        reported_url = record.get("url")

        if not contract.hash_matches(reported_hash, expected_hash):
            results[position] = {"id": item_id, "outcome": OUTCOME_HASH_MISMATCH}
            counters["hash_mismatch"] += 1
            continue

        if not contract.url_matches(reported_url, expected_url):
            results[position] = {"id": item_id, "outcome": OUTCOME_BAD_URL}
            counters["bad_url"] += 1
            continue

        if sub_row.audio_feedback_url:
            results[position] = {"id": item_id, "outcome": OUTCOME_ALREADY_SET}
            counters["already_set"] += 1
            continue

        needs_verify = bool(settings.verify_urls_on_write)
        if needs_verify:
            urls_to_verify.add(reported_url)
        pending.append((position, item_id, reported_url, reported_hash, sub_row.modified, needs_verify))

    verified = _verify_urls(urls_to_verify)

    for position, item_id, reported_url, reported_hash, expected_modified, needs_verify in pending:
        if needs_verify and not verified.get(reported_url):
            results[position] = {"id": item_id, "outcome": OUTCOME_BAD_URL}
            counters["bad_url"] += 1
            continue
        affected = runstate.conditional_write_url(item_id, reported_url, reported_hash, expected_modified)
        if affected and affected > 0:
            results[position] = {"id": item_id, "outcome": OUTCOME_WRITTEN}
            counters["written"] += 1
        else:
            fresh = frappe.db.get_value(SUBMISSION_DOCTYPE, item_id, "audio_feedback_url")
            if fresh:
                results[position] = {"id": item_id, "outcome": OUTCOME_ALREADY_SET}
                counters["already_set"] += 1
            else:
                results[position] = {"id": item_id, "outcome": OUTCOME_CHANGED_DURING_WRITE}
                counters["changed_during_write"] += 1

    for key, value in counters.items():
        if value:
            runstate.increment(run.name, key, value)

    if failed_items:
        try:
            existing = frappe.parse_json(run.failed_items) or {}
        except Exception:
            existing = {}
        merged = _bounded_update(existing, failed_items, FAILED_ITEMS_MAX_ENTRIES)
        runstate.set_fields(run.name, {"failed_items": frappe.as_json(merged)})

    if failure_reasons:
        try:
            existing_reasons = frappe.parse_json(run.failure_reasons) or {}
        except Exception:
            existing_reasons = {}
        for reason, count in failure_reasons.items():
            existing_reasons[reason] = existing_reasons.get(reason, 0) + count
        if len(existing_reasons) > FAILURE_REASONS_MAX_ENTRIES:
            existing_reasons = dict(
                sorted(existing_reasons.items(), key=lambda pair: pair[1], reverse=True)[:FAILURE_REASONS_MAX_ENTRIES]
            )
        runstate.set_fields(run.name, {"failure_reasons": frappe.as_json(existing_reasons)})

    runstate.set_fields(run.name, {"last_progress_at": frappe.utils.now_datetime()})
    runlog.append(run.name, f"progress batch of {len(records)}: {counters}")

    return {"accepted": True, "results": results}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def beat():
    _no_store()
    try:
        run = enter("beat")
    except GuardStop as exc:
        return _respond_stop(exc)

    settings = load_settings()
    payload = frappe.local.form_dict
    phase = payload.get("phase")
    remaining = payload.get("remaining")

    fields = {
        "last_beat_at": frappe.utils.now_datetime(),
        "last_phase": phase,
        "remaining_reported": remaining,
    }
    if not run.first_contact_at:
        fields["first_contact_at"] = frappe.utils.now_datetime()
    if run.status == STATUS_STARTING:
        fields["status"] = STATUS_RUNNING
    runstate.set_fields(run.name, fields)

    should_stop = run.status == STATUS_STOPPING
    if not should_stop:
        should_stop = not settings.kill_switch_on()

    return {"stop": bool(should_stop)}


def _final_status(pod_reason, run):
    if pod_reason in (POD_REASON_COMPLETED, POD_REASON_EMPTY):
        manifest_count = run.manifest_count or 0
        accounted = (
            (run.written or 0)
            + (run.already_set or 0)
            + (run.stale or 0)
            + (run.hash_mismatch or 0)
            + (run.changed_during_write or 0)
            + (run.pod_failed or 0)
        )
        if manifest_count == 0 or accounted >= manifest_count:
            return STATUS_COMPLETED
        return STATUS_COMPLETED_WITH_FAILURES
    if pod_reason == POD_REASON_COMPLETED_WITH_FAILURES:
        return STATUS_COMPLETED_WITH_FAILURES
    if pod_reason == POD_REASON_STOPPED:
        return STATUS_STOPPED
    if pod_reason in (POD_REASON_TIMEOUT, POD_REASON_STARTUP_TIMEOUT):
        return STATUS_TIMED_OUT
    if pod_reason == POD_REASON_EXCEPTION or pod_reason.startswith(POD_BREAKER_PREFIX):
        return STATUS_FAILED
    return STATUS_FAILED


@frappe.whitelist(allow_guest=True, methods=["POST"])
def complete():
    _no_store()
    try:
        run = enter("complete")
    except GuardStop as exc:
        return _respond_stop(exc)

    payload = frappe.local.form_dict
    reason = payload.get("reason") or "exception"
    gpu_seconds = payload.get("gpu_seconds")
    stats = payload.get("stats") or {}

    manifest_count = run.manifest_count or 0
    accounted = (
        (run.written or 0)
        + (run.already_set or 0)
        + (run.stale or 0)
        + (run.hash_mismatch or 0)
        + (run.changed_during_write or 0)
        + (run.pod_failed or 0)
    )
    not_processed = max(0, manifest_count - accounted)

    final_status = _final_status(reason, run)

    fields = {
        "completion_reason": reason,
        "pod_reported_gpu_seconds": gpu_seconds,
        "stats_json": frappe.as_json(stats),
        "not_processed": not_processed,
        "pod_uploaded": stats.get("uploaded"),
        "pod_generated": stats.get("generated"),
        "pod_decoded": stats.get("decoded"),
        "pod_truncated": stats.get("truncated"),
        "pod_retried": stats.get("retried"),
        "pod_tokens": stats.get("tokens"),
        "pod_audio_seconds": stats.get("audio_seconds"),
        "pod_startup_seconds": stats.get("startup_seconds"),
        "pod_run_seconds": stats.get("run_seconds"),
        "pod_tokens_per_second": stats.get("tokens_per_second"),
        "pod_gpu_sec_per_audio_min": stats.get("gpu_seconds_per_audio_minute"),
        "pod_skipped_existing": stats.get("skipped_existing"),
        "termination_status": "Pending",
    }

    if runstate.can_transition(run.status, final_status):
        fields["status"] = final_status
    else:
        fields["status"] = STATUS_FAILED

    runstate.set_fields(run.name, fields)
    runlog.append(run.name, f"complete reason={reason} final_status={fields['status']}")

    try:
        breaker_lib.evaluate(run.name)
    except Exception:
        frappe.log_error(title="tapvoice_breaker_evaluate_failed")

    try:
        frappe.enqueue(
            "tap_lms.tapvoice.job.termination.verify_termination",
            queue="long",
            run_name=run.name,
            enqueue_after_commit=True,
        )
    except Exception:
        frappe.log_error(title="tapvoice_enqueue_termination_failed")

    return {"accepted": True}