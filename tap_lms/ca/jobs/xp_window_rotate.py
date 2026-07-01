import frappe
import time
import psutil
from datetime import datetime

from tap_lms.ca.api.progress.learner import flush_xp_queue

JOB_KEY = "XP Window Rotate"
JOB_LABEL = "XP Window Rotate"
JOB_LOCK_KEY = "ca:xp_rotate:running"
JOB_START_KEY = "ca:xp_rotate:started_at"

_MEM_FLOOR_MB = 512
_MEM_TARGET_PCT = 0.35
_ROTATE_BATCH_MIN = 2000
_ROTATE_BATCH_MAX = 25000
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 600
_LOCK_TTL_PER_MILLION_SEC = 900


def _free_mb() -> int:
    return psutil.virtual_memory().available // (1024 * 1024)


def _dynamic_batch(min_size: int, max_size: int) -> int:
    free = _free_mb()
    if free <= _MEM_FLOOR_MB:
        return min_size
    total = psutil.virtual_memory().total // (1024 * 1024)
    ratio = min(free / total, 1.0)
    size = int(min_size + (max_size - min_size) * ratio * _MEM_TARGET_PCT / 0.35)
    return max(min_size, min(size, max_size))


def _dynamic_lock_ttl() -> int:
    try:
        total_learners = frappe.db.sql(
            'SELECT COUNT(*) AS n FROM "tabCitizenship Learner"', as_dict=True
        )[0].n or 0
    except Exception:
        total_learners = 0
    return int(_LOCK_TTL_BASE_SEC + (total_learners / 1_000_000) * _LOCK_TTL_PER_MILLION_SEC)


def _rotate_chunk(names: list):
    placeholders = ",".join(["%s"] * len(names))
    frappe.db.sql("BEGIN")
    try:
        frappe.db.sql(
            f"""
            UPDATE "tabCitizenship Learner"
               SET weekly_xp = xp_d0 + xp_d1 + xp_d2 + xp_d3 + xp_d4 + xp_d5 + xp_d6,
                   xp_d6     = xp_d5,
                   xp_d5     = xp_d4,
                   xp_d4     = xp_d3,
                   xp_d3     = xp_d2,
                   xp_d2     = xp_d1,
                   xp_d1     = xp_d0,
                   xp_d0     = 0
             WHERE name IN ({placeholders})
            """,
            tuple(names),
        )
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise


def _rotate_xp_window():
    last_name = ""
    while True:
        batch_size = _dynamic_batch(_ROTATE_BATCH_MIN, _ROTATE_BATCH_MAX)
        rows = frappe.db.sql(
            """
            SELECT name FROM "tabCitizenship Learner"
             WHERE name > %s
             ORDER BY name
             LIMIT %s
            """,
            (last_name, batch_size),
            as_dict=True,
        )
        if not rows:
            break
        names = [r.name for r in rows]
        last_name = names[-1]
        _rotate_chunk(names)
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)


def _get_or_create_tracker():
    if frappe.db.exists("Citizenship Tasks", JOB_KEY):
        return frappe.get_doc("Citizenship Tasks", JOB_KEY)
    doc = frappe.get_doc({
        "doctype": "Citizenship Tasks",
        "job_key": JOB_KEY,
        "job_label": JOB_LABEL,
        "status": "Pending",
        "paused": 0,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc


def _is_paused(doc) -> bool:
    return bool(doc.paused)


def _mark(doc, status: str, duration: float, error: str = None):
    doc.status = status
    doc.last_run_at = frappe.utils.now_datetime()
    doc.last_duration_seconds = round(duration, 1)
    if status == "Success":
        doc.last_success_at = frappe.utils.now_datetime()
        doc.last_error = None
    doc.last_error = error
    doc.save(ignore_permissions=True)
    frappe.db.commit()


def run_xp_window_rotate():
    tracker = _get_or_create_tracker()
    if _is_paused(tracker):
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("CA XP window rotate already running, skipping.")
        return
    lock_ttl = _dynamic_lock_ttl()
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    try:
        flush_xp_queue()
        _rotate_xp_window()
        _mark(tracker, "Success", time.time() - t0)
        frappe.logger().info(f"CA XP window rotate done in {round(time.time() - t0, 1)}s. FreeMB={_free_mb()}")
    except Exception as e:
        _mark(tracker, "Failed", time.time() - t0, str(e)[:5000])
        frappe.log_error(str(e), "CA XP Rotate failed")
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)