import frappe
import json
import urllib.request
import urllib.error
from datetime import timedelta

ROTATE_JOB_KEY = "XP Window Rotate"

_IST_OFFSET = timedelta(hours=5, minutes=30)
_HTTP_TIMEOUT_SEC = 30
_JOB_LOG_TAB = "Job-Log"


def rotation_succeeded_today() -> bool:
    if not frappe.db.exists("Citizenship Tasks", ROTATE_JOB_KEY):
        return False
    last_success_at = frappe.db.get_value("Citizenship Tasks", ROTATE_JOB_KEY, "last_success_at")
    if not last_success_at:
        return False
    return frappe.utils.getdate(last_success_at) == frappe.utils.getdate(frappe.utils.now_datetime())


def _ist_now_parts():
    ist = frappe.utils.now_datetime() + _IST_OFFSET
    return ist.strftime("%Y-%m-%d"), ist.strftime("%H:%M:%S")


def send_job_log(job_key: str, status: str, records: int, duration: float, error: str = None):
    try:
        webapp_url = frappe.get_doc("Secrets", "appsheet_webapp_url").get_password("value")
        webapp_secret = frappe.get_doc("Secrets", "appsheet_webapp_secret").get_password("value")

        date_str, time_str = _ist_now_parts()
        row = [date_str, time_str, job_key, status, records or 0, round(duration or 0, 1), (error or "")[:500]]

        payload = {
            _JOB_LOG_TAB: {"mode": "append", "rows": [row]},
        }
        body = json.dumps({"tabs": payload, "__secret": webapp_secret}).encode()
        req = urllib.request.Request(
            webapp_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
            resp.read()
    except Exception as e:
        frappe.log_error(title="CA send_job_log failed", message=f"job_key={job_key} status={status} error={e}")