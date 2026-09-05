import frappe
import pickle
import time
from datetime import timedelta
from tap_lms.tapapp.jobs._shared import (
    free_mb,
    dynamic_batch,
    dynamic_lock_ttl,
    get_or_create_tracker,
    mark_tracker,
)

JOB_KEY = "Nightly Window Maintenance"
JOB_LABEL = "Nightly Window Maintenance"
JOB_LOCK_KEY = "tapapp:nightly_maintenance:running"
JOB_START_KEY = "tapapp:nightly_maintenance:started_at"

_BATCH_MIN = 2000
_BATCH_MAX = 25000
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 600
_LOCK_TTL_PER_MILLION_SEC = 900

WINDOW_DAYS = 7


def _process_chunk(names: list, today, cutoff):
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
               xp_d0 = 0,
               window_start_date = CASE
                   WHEN window_start_date IS NOT NULL AND window_start_date <= %s THEN %s
                   ELSE window_start_date
               END,
               activities_watched_this_week = CASE
                   WHEN window_start_date IS NOT NULL AND window_start_date <= %s THEN 0
                   ELSE activities_watched_this_week
               END,
               is_bingeing = CASE
                   WHEN window_start_date IS NOT NULL AND window_start_date <= %s THEN 0
                   ELSE is_bingeing
               END,
               streak = CASE
                   WHEN window_start_date IS NOT NULL AND window_start_date <= %s
                        AND (last_activity_date IS NULL OR last_activity_date < window_start_date)
                   THEN 0
                   ELSE streak
               END,
               modified = NOW()
         WHERE name IN ({placeholders})
        """,
        (cutoff, today, cutoff, cutoff, cutoff, *names),
    )
    frappe.db.commit()


def _run_maintenance(today) -> int:
    cutoff = today - timedelta(days=WINDOW_DAYS)
    last_name = ""
    updated = 0
    while True:
        batch_size = dynamic_batch(_BATCH_MIN, _BATCH_MAX)
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
        _process_chunk(names, today, cutoff)
        updated += len(names)
        time.sleep(0.2 if free_mb() < 512 else _SLEEP_BETWEEN_CHUNKS)
    return updated


def run_nightly_window_maintenance():
    cache = frappe.cache()
    lock_ttl = dynamic_lock_ttl(_LOCK_TTL_BASE_SEC, _LOCK_TTL_PER_MILLION_SEC)
    acquired = cache.set(cache.make_key(JOB_LOCK_KEY), pickle.dumps("1"), nx=True, ex=lock_ttl)
    if not acquired:
        frappe.logger().warning("Tapapp nightly window maintenance already running, skipping.")
        return
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    try:
        tracker = get_or_create_tracker(JOB_KEY, JOB_LABEL)
        if tracker.paused:
            tracker.status = "Paused"
            tracker.save(ignore_permissions=True)
            frappe.db.commit()
            return

        tracker.status = "Running"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()

        t0 = time.time()
        try:
            today = frappe.utils.getdate(frappe.utils.now_datetime())
            updated = _run_maintenance(today)
            duration = time.time() - t0
            mark_tracker(tracker, "Success", duration)
            frappe.logger().info(f"Tapapp nightly window maintenance done in {round(duration, 1)}s. Rows updated={updated} FreeMB={free_mb()}")
        except Exception as e:
            duration = time.time() - t0
            mark_tracker(tracker, "Failed", duration, str(e)[:5000])
            frappe.log_error(title="Tapapp nightly window maintenance failed", message=frappe.get_traceback())
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)