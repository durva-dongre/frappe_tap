import frappe
import time
import psutil
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Citizenship / Tapapp Academy — daily job
#
# record_activity() already rolls a single learner's window forward lazily
# on their next activity, so this job is NOT required for correctness of
# the binge lock itself. What it IS required for is:
#
#   1. Streak decay: a learner who simply stops being active never calls
#      record_activity again, so their `streak` would stay frozen at
#      whatever it last was forever, even though they missed windows.
#      This job detects "window_start_date + 7 days has passed AND no
#      activity happened in that window" and resets streak to 0.
#
#   2. is_bingeing flag hygiene: once a window expires, is_bingeing should
#      go back to 0 even for learners who don't immediately start a new
#      one, so reporting/UI reads a clean value instead of a stale "1".
#
# This does NOT touch xp (cumulative, never rotated) and does NOT touch
# activities_watched_this_week beyond the reset that accompanies a window
# roll (matches the "reset to 0 only when the 7-day window has elapsed"
# description on the doctype).
# ---------------------------------------------------------------------------

JOB_KEY = "Tapapp Window Rollover"
JOB_LABEL = "Tapapp Window Rollover"
JOB_LOCK_KEY = "tapapp:window_rollover:running"
JOB_START_KEY = "tapapp:window_rollover:started_at"

_MEM_FLOOR_MB = 512
_MEM_TARGET_PCT = 0.35
_BATCH_MIN = 1000
_BATCH_MAX = 20000
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 300
_LOCK_TTL_PER_MILLION_SEC = 600

WINDOW_DAYS = 7
# A learner has "missed" their window (streak should reset) once we're past
# a second full window with no new activity, since the window that just
# expired might still get topped up right up to its last day.
STREAK_RESET_GRACE_DAYS = WINDOW_DAYS * 2


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
        total = frappe.db.sql('SELECT COUNT(*) AS n FROM "tabTapapp Learner"', as_dict=True)[0].n or 0
    except Exception:
        total = 0
    return int(_LOCK_TTL_BASE_SEC + (total / 1_000_000) * _LOCK_TTL_PER_MILLION_SEC)


def _rollover_expired_windows(today: date) -> int:
    """
    For any learner whose window has expired (today >= window_start_date + 7)
    but who has NOT already been rolled forward by an activity today:
      - if they were active at all inside that now-closed window
        (last_activity_date >= window_start_date), leave streak as-is —
        they'll get streak credit lazily the next time they act, same as
        record_activity would do.
      - if they were NOT active in that window at all, reset streak to 0
        (they broke the chain).
    In both cases: clear activities_watched_this_week to 0, clear
    is_bingeing, and advance window_start_date to today so the next
    activity starts a clean window.
    """
    updated = 0
    last_name = ""
    while True:
        batch = _dynamic_batch(_BATCH_MIN, _BATCH_MAX)
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

        broke_streak_names = []
        kept_streak_names = []
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
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)

    return updated


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


def _mark(doc, status: str, duration: float, records: int = 0, error: str = None):
    doc.status = status
    doc.last_run_at = frappe.utils.now_datetime()
    doc.last_duration_seconds = round(duration, 1)
    if status == "Success":
        doc.last_success_at = frappe.utils.now_datetime()
        doc.last_error = None
    doc.last_error = error
    doc.save(ignore_permissions=True)
    frappe.db.commit()


def run_window_rollover():
    """
    Scheduled once daily. Safe to run more than once a day if ever
    triggered manually — it's idempotent (rows that don't need rolling are
    simply not matched by the WHERE clause).
    """
    tracker = _get_or_create_tracker()
    if tracker.paused:
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("Tapapp window rollover already running, skipping.")
        return
    lock_ttl = _dynamic_lock_ttl()
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    try:
        today = date.today()
        updated = _rollover_expired_windows(today)
        duration = time.time() - t0
        _mark(tracker, "Success", duration, records=updated)
        frappe.logger().info(f"Tapapp window rollover done in {round(duration, 1)}s. Rows updated={updated} FreeMB={_free_mb()}")
    except Exception as e:
        duration = time.time() - t0
        _mark(tracker, "Failed", duration, error=str(e)[:5000])
        frappe.log_error(title="Tapapp window rollover failed", message=frappe.get_traceback())
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)