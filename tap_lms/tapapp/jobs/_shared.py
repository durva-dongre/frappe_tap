import frappe
import psutil

_MEM_FLOOR_MB = 512
_MEM_TARGET_PCT = 0.35


def free_mb() -> int:
    return psutil.virtual_memory().available // (1024 * 1024)


def dynamic_batch(min_size: int, max_size: int) -> int:
    free = free_mb()
    if free <= _MEM_FLOOR_MB:
        return min_size
    total = psutil.virtual_memory().total // (1024 * 1024)
    ratio = min(free / total, 1.0)
    size = int(min_size + (max_size - min_size) * ratio * _MEM_TARGET_PCT / 0.35)
    return max(min_size, min(size, max_size))


def dynamic_lock_ttl(base_sec: int, per_million_sec: int) -> int:
    try:
        total = frappe.db.sql('SELECT COUNT(*) AS n FROM "tabTapapp Learner"', as_dict=True)[0].n or 0
    except Exception:
        total = 0
    return int(base_sec + (total / 1_000_000) * per_million_sec)


def get_or_create_tracker(job_key: str, job_label: str):
    if frappe.db.exists("Tapapp Tasks", job_key):
        return frappe.get_doc("Tapapp Tasks", job_key)
    doc = frappe.get_doc({
        "doctype": "Tapapp Tasks",
        "job_key": job_key,
        "job_label": job_label,
        "status": "Pending",
        "paused": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def mark_tracker(doc, status: str, duration: float, error: str = None):
    doc.status = status
    doc.last_run_at = frappe.utils.now_datetime()
    doc.last_duration_seconds = round(duration, 1)
    if status == "Success":
        doc.last_success_at = frappe.utils.now_datetime()
        doc.last_error = None
    doc.last_error = error
    doc.save(ignore_permissions=True)
    frappe.db.commit()