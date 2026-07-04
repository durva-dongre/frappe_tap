import frappe
import time
import psutil

JOB_KEY = "Window Rollover"
JOB_LABEL = "Window Rollover"
JOB_LOCK_KEY = "ca:window_rollover:running"
JOB_START_KEY = "ca:window_rollover:started_at"

_MEM_FLOOR_MB = 512
_MEM_TARGET_PCT = 0.35
_SCAN_CHUNK_MIN = 2000
_SCAN_CHUNK_MAX = 25000
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 600
_LOCK_TTL_PER_MILLION_SEC = 900
_WINDOW_DAYS = 7


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
            'SELECT COUNT(*) AS n FROM "tabTapapp Learner"', as_dict=True
        )[0].n or 0
    except Exception:
        total_learners = 0
    return int(_LOCK_TTL_BASE_SEC + (total_learners / 1_000_000) * _LOCK_TTL_PER_MILLION_SEC)


def _decay_stale_streaks_chunk(names: list):
    """
    For learners whose last_activity_date is more than _WINDOW_DAYS old and
    whose streak is still > 0, reset streak to 0. longest_streak is left
    untouched since it's a historical high-water mark, not a live counter.
    record_activity() (called on each student action) is what advances the
    streak forward; this job only handles decay for students who went silent
    and never triggered that path again.
    """
    placeholders = ",".join(["%s"] * len(names))
    frappe.db.sql(
        f"""
        UPDATE "tabTapapp Learner"
           SET streak = 0,
               modified = NOW()
         WHERE name IN ({placeholders})
           AND streak > 0
           AND (last_activity_date IS NULL
                OR last_activity_date < CURRENT_DATE - INTERVAL '{_WINDOW_DAYS} days')
        """,
        tuple(names),
    )
    frappe.db.commit()


def _clear_stale_binge_flag_chunk(names: list):
    """
    is_bingeing is set when a learner exhausts max_weekly_activities early in
    their rolling window. Once the window has actually elapsed (today >=
    window_start_date + _WINDOW_DAYS), the flag is stale even if
    activities_watched_this_week hasn't been reset yet by the lazy
    per-student path, so clear it here to keep reporting/UI accurate.
    """
    placeholders = ",".join(["%s"] * len(names))
    frappe.db.sql(
        f"""
        UPDATE "tabTapapp Learner"
           SET is_bingeing = 0,
               modified = NOW()
         WHERE name IN ({placeholders})
           AND is_bingeing = 1
           AND window_start_date IS NOT NULL
           AND window_start_date < CURRENT_DATE - INTERVAL '{_WINDOW_DAYS} days'
        """,
        tuple(names),
    )
    frappe.db.commit()


def _rollover_windows():
    last_name = ""
    while True:
        batch_size = _dynamic_batch(_SCAN_CHUNK_MIN, _SCAN_CHUNK_MAX)
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
        _decay_stale_streaks_chunk(names)
        _clear_stale_binge_flag_chunk(names)
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


def run_window_rollover():
    tracker = _get_or_create_tracker()
    if _is_paused(tracker):
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("Window rollover already running, skipping.")
        return
    lock_ttl = _dynamic_lock_ttl()
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    try:
        _rollover_windows()
        duration = time.time() - t0
        _mark(tracker, "Success", duration)
        frappe.logger().info(f"Window rollover done in {round(duration, 1)}s. FreeMB={_free_mb()}")
    except Exception as e:
        duration = time.time() - t0
        _mark(tracker, "Failed", duration, str(e)[:5000])
        frappe.log_error(title="Window Rollover failed", message=str(e))
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)