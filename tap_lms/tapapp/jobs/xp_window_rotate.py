import frappe
import time
from tap_lms.tapapp.jobs._shared import (
    free_mb,
    dynamic_batch,
    dynamic_lock_ttl,
    get_or_create_tracker,
    mark_tracker,
)

JOB_KEY = "XP Window Rotate"
JOB_LABEL = "XP Window Rotate"
JOB_LOCK_KEY = "tapapp:xp_rotate:running"
JOB_START_KEY = "tapapp:xp_rotate:started_at"

_ROTATE_BATCH_MIN = 2000
_ROTATE_BATCH_MAX = 25000
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 600
_LOCK_TTL_PER_MILLION_SEC = 900


def _rotate_chunk(names: list):
    placeholders = ",".join(["%s"] * len(names))
    frappe.db.sql(
        f"""
        UPDATE "tabTapapp Learner"
           SET weekly_xp = xp_d0 + xp_d1 + xp_d2 + xp_d3 + xp_d4 + xp_d5 + xp_d6,
               xp_d6 = xp_d5,
               xp_d5 = xp_d4,
               xp_d4 = xp_d3,
               xp_d3 = xp_d2,
               xp_d2 = xp_d1,
               xp_d1 = xp_d0,
               xp_d0 = 0
         WHERE name IN ({placeholders})
        """,
        tuple(names),
    )
    frappe.db.commit()


def _rotate_xp_window():
    last_name = ""
    updated = 0
    while True:
        batch_size = dynamic_batch(_ROTATE_BATCH_MIN, _ROTATE_BATCH_MAX)
        rows = frappe.db.sql(
            """
            SELECT name FROM "tabTapapp Learner"
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
        updated += len(names)
        time.sleep(0.2 if free_mb() < 512 else _SLEEP_BETWEEN_CHUNKS)
    return updated


def run_xp_window_rotate():
    tracker = get_or_create_tracker(JOB_KEY, JOB_LABEL)
    if tracker.paused:
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("Tapapp XP window rotate already running, skipping.")
        return
    lock_ttl = dynamic_lock_ttl(_LOCK_TTL_BASE_SEC, _LOCK_TTL_PER_MILLION_SEC)
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    try:
        updated = _rotate_xp_window()
        duration = time.time() - t0
        mark_tracker(tracker, "Success", duration)
        frappe.logger().info(f"Tapapp XP window rotate done in {round(duration, 1)}s. Rows updated={updated} FreeMB={free_mb()}")
    except Exception as e:
        duration = time.time() - t0
        mark_tracker(tracker, "Failed", duration, str(e)[:5000])
        frappe.log_error(title="Tapapp XP window rotate failed", message=frappe.get_traceback())
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)
