import frappe
import json
import time
import urllib.request
from datetime import timedelta
from tap_lms.tapapp.jobs._shared import (
    free_mb,
    dynamic_lock_ttl,
    get_or_create_tracker,
    mark_tracker,
)

JOB_KEY = "Analytics Report"
JOB_LABEL = "Analytics Report"
JOB_LOCK_KEY = "tapapp:analytics:running"
JOB_START_KEY = "tapapp:analytics:started_at"

_LOCK_TTL_BASE_SEC = 600
_LOCK_TTL_PER_MILLION_SEC = 900
_HTTP_TIMEOUT_SEC = 60
_IST_OFFSET = timedelta(hours=5, minutes=30)

_ARCHETYPE_OPTIONS = ("dormant", "fence_sitter", "irregular_submitter", "submitter")
_LEVEL_OPTIONS = (
    "Level 1", "Level 2", "Level 2A", "Level 3", "Level 3A",
    "Level 3K", "Level 3AK", "Level 4", "Level 4K", "Unset",
)


def _ist_date_str() -> str:
    return (frappe.utils.now_datetime() + _IST_OFFSET).strftime("%Y-%m-%d")


def _metric_dal() -> dict:
    row = frappe.db.sql(
        'SELECT COUNT(*) AS n FROM "tabTapapp Learner" WHERE last_activity_date = CURRENT_DATE',
        as_dict=True,
    )[0]
    return {"DAL": row.n or 0}


def _metric_archetype_distribution() -> dict:
    rows = frappe.db.sql(
        'SELECT archetype, COUNT(*) AS n FROM "tabTapapp Learner" GROUP BY archetype',
        as_dict=True,
    )
    counts = {(r.archetype or "dormant"): r.n for r in rows}
    return {a: counts.get(a, 0) for a in _ARCHETYPE_OPTIONS}


def _metric_level_distribution() -> dict:
    rows = frappe.db.sql(
        'SELECT level, COUNT(*) AS n FROM "tabTapapp Learner" GROUP BY level',
        as_dict=True,
    )
    counts = {(r.level or "Unset"): r.n for r in rows}
    return {lvl: counts.get(lvl, 0) for lvl in _LEVEL_OPTIONS}


def _metric_submission_totals() -> dict:
    row = frappe.db.sql(
        'SELECT SUM(submission_gems) AS gems, AVG(submission_index)::float AS avg_index FROM "tabTapapp Learner"',
        as_dict=True,
    )[0]
    return {"Total Gems Awarded": row.gems or 0, "Avg Submission Index": round(row.avg_index or 0, 2)}


def _metric_bingeing_count() -> dict:
    row = frappe.db.sql(
        'SELECT COUNT(*) AS n FROM "tabTapapp Learner" WHERE is_bingeing = 1',
        as_dict=True,
    )[0]
    return {"Currently Bingeing": row.n or 0}


_DAILY_ROW_METRICS = {
    "DAL": _metric_dal,
    "Archetype-distribution": _metric_archetype_distribution,
    "Level-distribution": _metric_level_distribution,
    "Submission-totals": _metric_submission_totals,
    "Bingeing-count": _metric_bingeing_count,
}


def _compute_all_metrics() -> dict:
    date_str = _ist_date_str()
    payload = {}
    for tab_name, fn in _DAILY_ROW_METRICS.items():
        payload[tab_name] = {"mode": "daily_row", "date": date_str, "columns": fn()}
    return payload


def _send_to_apps_script(payload: dict):
    webapp_url = frappe.get_doc("Secrets", "tapapp_appsheet_webapp_url").get_password("value")
    webapp_secret = frappe.get_doc("Secrets", "tapapp_appsheet_webapp_secret").get_password("value")
    body = json.dumps({"tabs": payload, "__secret": webapp_secret}).encode()
    req = urllib.request.Request(
        webapp_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
        resp_body = json.loads(resp.read().decode())
    failed = resp_body.get("failed") or []
    if failed:
        raise Exception(f"Apps Script reported failed tabs: {failed}")
    return resp_body


def run_tapapp_analytics_report():
    tracker = get_or_create_tracker(JOB_KEY, JOB_LABEL)
    if tracker.paused:
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("Tapapp analytics report already running, skipping.")
        return
    lock_ttl = dynamic_lock_ttl(_LOCK_TTL_BASE_SEC, _LOCK_TTL_PER_MILLION_SEC)
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    try:
        payload = _compute_all_metrics()
        _send_to_apps_script(payload)
        duration = time.time() - t0
        mark_tracker(tracker, "Success", duration)
        frappe.logger().info(f"Tapapp analytics report done in {round(duration, 1)}s. FreeMB={free_mb()}")
    except Exception as e:
        duration = time.time() - t0
        mark_tracker(tracker, "Failed", duration, str(e)[:5000])
        frappe.log_error(title="Tapapp analytics report failed", message=str(e))
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)