import frappe
import time
from datetime import timedelta
from tap_lms.tapapp.jobs._shared import (
    free_mb,
    dynamic_batch,
    dynamic_lock_ttl,
    get_or_create_tracker,
    mark_tracker,
)

JOB_KEY = "Weekly Window Rollover"
JOB_LABEL = "Weekly Window Rollover"
JOB_LOCK_KEY = "tapapp:window_rollover:running"
JOB_START_KEY = "tapapp:window_rollover:started_at"

_BATCH_MIN = 1000
_BATCH_MAX = 20000
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 300
_LOCK_TTL_PER_MILLION_SEC = 600

WINDOW_DAYS = 7


def _rollover_expired_windows(today) -> int:
    updated = 0
    last_name = ""
    while True:
        batch = dynamic_batch(_BATCH_MIN, _BATCH_MAX)
        rows = frappe.db.sql(
            """
            SELECT name, window_start_date, last_activity_date, streak
            FROM "tabTapapp Learner"
            WHERE name > %s
              AND window_start_date IS NOT NULL
              AND window_start_date <= %s
            ORDER BY name
            LIMIT %s
            """,
            (last_name, today - timedelta(days=WINDOW_DAYS), batch),
            as_dict=True,
        )
        if not rows:
            break

        kept_streak_names = []
        broke_streak_names = []
        for r in rows:
            was_active_in_window = bool(r.last_activity_date) and r.last_activity_date >= r.window_start_date
            if was_active_in_window:
                kept_streak_names.append(r.name)
            else:
                broke_streak_names.append(r.name)

        if kept_streak_names:
            placeholders = ",".join(["%s"] * len(kept_streak_names))
            frappe.db.sql(
                f"""
                UPDATE "tabTapapp Learner"
                   SET window_start_date = %s,
                       activities_watched_this_week = 0,
                       is_bingeing = 0,
                       modified = NOW()
                 WHERE name IN ({placeholders})
                """,
                (today, *kept_streak_names),
            )

        if broke_streak_names:
            placeholders = ",".join(["%s"] * len(broke_streak_names))
            frappe.db.sql(
                f"""
                UPDATE "tabTapapp Learner"
                   SET window_start_date = %s,
                       activities_watched_this_week = 0,
                       is_bingeing = 0,
                       streak = 0,
                       modified = NOW()
                 WHERE name IN ({placeholders})
                """,
                (today, *broke_streak_names),
            )

        frappe.db.commit()
        updated += len(rows)
        last_name = rows[-1].name
        time.sleep(0.2 if free_mb() < 512 else _SLEEP_BETWEEN_CHUNKS)

    return updated


def run_window_rollover():
    tracker = get_or_create_tracker(JOB_KEY, JOB_LABEL)
    if tracker.paused:
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("Tapapp window rollover already running, skipping.")
        return
    lock_ttl = dynamic_lock_ttl(_LOCK_TTL_BASE_SEC, _LOCK_TTL_PER_MILLION_SEC)
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    try:
        today = frappe.utils.getdate(frappe.utils.now_datetime())
        updated = _rollover_expired_windows(today)
        duration = time.time() - t0
        mark_tracker(tracker, "Success", duration)
        frappe.logger().info(f"Tapapp window rollover done in {round(duration, 1)}s. Rows updated={updated} FreeMB={free_mb()}")
    except Exception as e:
        duration = time.time() - t0
        mark_tracker(tracker, "Failed", duration, str(e)[:5000])
        frappe.log_error(title="Tapapp window rollover failed", message=frappe.get_traceback())
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)
