import frappe
import json
import time
import psutil
import urllib.request
import urllib.error
from datetime import datetime, timedelta

from tap_lms.ca.jobs._shared import rotation_succeeded_today

JOB_KEY = "Analytics Report"
JOB_LABEL = "Analytics Report"
JOB_LOCK_KEY = "ca:analytics:running"
JOB_START_KEY = "ca:analytics:started_at"

_MEM_FLOOR_MB = 512
_MEM_TARGET_PCT = 0.35
_SCAN_CHUNK_MIN = 1000
_SCAN_CHUNK_MAX = 25000
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 600
_LOCK_TTL_PER_MILLION_SEC = 900

_TOP_N_XP_EARNERS = 100
_HTTP_TIMEOUT_SEC = 60
_IST_OFFSET = timedelta(hours=5, minutes=30)

_ROTATE_LOCK_KEY = "ca:xp_rotate:running"
_ROTATE_WAIT_MAX_SEC = 1800
_ROTATE_WAIT_POLL_SEC = 10


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


def _ist_date_str() -> str:
    return (frappe.utils.now_datetime() + _IST_OFFSET).strftime("%Y-%m-%d")


def _wait_for_rotation_lock_clear():
    cache = frappe.cache()
    waited = 0
    while cache.get_value(_ROTATE_LOCK_KEY) and waited < _ROTATE_WAIT_MAX_SEC:
        time.sleep(_ROTATE_WAIT_POLL_SEC)
        waited += _ROTATE_WAIT_POLL_SEC


def _scan_learners_chunked(select_sql: str, extra_params: tuple = ()):
    last_name = ""
    while True:
        chunk_size = _dynamic_batch(_SCAN_CHUNK_MIN, _SCAN_CHUNK_MAX)
        rows = frappe.db.sql(
            select_sql,
            (*extra_params, last_name, chunk_size),
            as_dict=True,
        )
        if not rows:
            break
        for r in rows:
            yield r
        last_name = rows[-1].learner_id
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)


def _percentiles(sorted_vals: list, points=(50, 75, 90, 95, 99)):
    n = len(sorted_vals)
    if not n:
        return {p: 0 for p in points}
    out = {}
    for p in points:
        idx = min(int(n * p / 100), n - 1)
        out[p] = sorted_vals[idx]
    return out


def _metric_dal(date_str):
    row = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
          FROM "tabCitizenship Learner"
         WHERE last_activity_date = CURRENT_DATE
        """,
        as_dict=True,
    )[0]
    return [[date_str, row.n or 0]]


def _metric_xp_per_weekday(date_str):
    row = frappe.db.sql(
        """
        SELECT AVG(xp_d0)::float AS avg_xp
          FROM "tabCitizenship Learner"
         WHERE last_activity_date = CURRENT_DATE
        """,
        as_dict=True,
    )[0]
    return [[date_str, round(row.avg_xp or 0, 2)]]


def _metric_weekly_xp_histogram(date_str):
    vals = []
    for r in _scan_learners_chunked(
        """
        SELECT name AS learner_id, weekly_xp
          FROM "tabCitizenship Learner"
         WHERE name > %s
         ORDER BY name
         LIMIT %s
        """
    ):
        vals.append(r.weekly_xp or 0)
    vals.sort()
    buckets = [0, 50, 100, 250, 500, 1000, 2500, 99999999]
    labels = ["0-49", "50-99", "100-249", "250-499", "500-999", "1000-2499", "2500+"]
    counts = [0] * (len(buckets) - 1)
    for v in vals:
        for i in range(len(buckets) - 1):
            if buckets[i] <= v < buckets[i + 1]:
                counts[i] += 1
                break
    return [[date_str, labels[i], counts[i]] for i in range(len(labels))]


def _metric_mal(date_str):
    row = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
          FROM "tabCitizenship Learner"
         WHERE last_activity_date >= CURRENT_DATE - INTERVAL '30 DAYS'
        """,
        as_dict=True,
    )[0]
    return [[date_str, row.n or 0]]


def _metric_level_distribution(date_str):
    rows = frappe.db.sql(
        """
        SELECT level, COUNT(*) AS n
          FROM "tabCitizenship Learner"
         GROUP BY level
        """,
        as_dict=True,
    )
    return [[date_str, r.level or "Unset", r.n] for r in rows]


def _metric_level_vs_xp_stats(date_str):
    rows = frappe.db.sql(
        """
        SELECT level, AVG(xp)::float AS avg_xp, MIN(xp) AS min_xp, MAX(xp) AS max_xp
          FROM "tabCitizenship Learner"
         GROUP BY level
        """,
        as_dict=True,
    )
    return [[date_str, r.level or "Unset", round(r.avg_xp or 0, 2), r.min_xp or 0, r.max_xp or 0] for r in rows]


def _metric_xp_velocity_by_level(date_str):
    rows = frappe.db.sql(
        """
        SELECT level, AVG(xp_d0 + xp_d1 + xp_d2 + xp_d3 + xp_d4 + xp_d5 + xp_d6)::float AS avg_weekly
          FROM "tabCitizenship Learner"
         GROUP BY level
        """,
        as_dict=True,
    )
    return [[date_str, r.level or "Unset", round(r.avg_weekly or 0, 2)] for r in rows]


def _metric_streak_length_histogram(date_str):
    vals = []
    for r in _scan_learners_chunked(
        """
        SELECT name AS learner_id, streak
          FROM "tabCitizenship Learner"
         WHERE name > %s
         ORDER BY name
         LIMIT %s
        """
    ):
        vals.append(r.streak or 0)
    buckets = [0, 1, 3, 7, 14, 30, 60, 99999999]
    labels = ["0", "1-2", "3-6", "7-13", "14-29", "30-59", "60+"]
    counts = [0] * (len(buckets) - 1)
    for v in vals:
        for i in range(len(buckets) - 1):
            if buckets[i] <= v < buckets[i + 1]:
                counts[i] += 1
                break
    return [[date_str, labels[i], counts[i]] for i in range(len(labels))]


def _metric_streak_gap_count(date_str):
    row = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
          FROM "tabCitizenship Learner"
         WHERE streak = 0
           AND longest_streak > 0
        """,
        as_dict=True,
    )[0]
    return [[date_str, row.n or 0]]


def _metric_churn_risk_segments(date_str):
    rows = frappe.db.sql(
        """
        SELECT
          SUM(CASE WHEN last_activity_date >= CURRENT_DATE - INTERVAL '7 DAYS' THEN 1 ELSE 0 END) AS healthy,
          SUM(CASE WHEN last_activity_date < CURRENT_DATE - INTERVAL '7 DAYS'
                    AND last_activity_date >= CURRENT_DATE - INTERVAL '21 DAYS' THEN 1 ELSE 0 END) AS at_risk,
          SUM(CASE WHEN last_activity_date < CURRENT_DATE - INTERVAL '21 DAYS'
                    OR last_activity_date IS NULL THEN 1 ELSE 0 END) AS churned
          FROM "tabCitizenship Learner"
        """,
        as_dict=True,
    )[0]
    return [
        [date_str, "healthy", rows.healthy or 0],
        [date_str, "at_risk", rows.at_risk or 0],
        [date_str, "churned", rows.churned or 0],
    ]


def _metric_reengagement_after_gap(date_str):
    row = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
          FROM "tabCitizenship Learner"
         WHERE last_activity_date = CURRENT_DATE
           AND streak <= 1
           AND longest_streak >= 7
        """,
        as_dict=True,
    )[0]
    return [[date_str, row.n or 0]]


def _metric_enrollment_count_distribution(date_str):
    rows = frappe.db.sql(
        """
        SELECT enrollment_count, COUNT(*) AS n
          FROM (
            SELECT cl.name, COUNT(ce.name) AS enrollment_count
              FROM "tabCitizenship Learner" cl
         LEFT JOIN "tabCitizenship Enrollment" ce
                ON ce.parent = cl.name
             GROUP BY cl.name
          ) sub
         GROUP BY enrollment_count
         ORDER BY enrollment_count
        """,
        as_dict=True,
    )
    return [[date_str, str(r.enrollment_count), r.n] for r in rows]


def _metric_achievement_unlock_rates(date_str):
    rows = frappe.db.sql(
        """
        SELECT cla.achievement, COUNT(DISTINCT cla.parent) AS n
          FROM "tabCitizenship Learner Achievement" cla
         GROUP BY cla.achievement
         ORDER BY n DESC
         LIMIT 50
        """,
        as_dict=True,
    )
    return [[date_str, r.achievement or "Unknown", r.n] for r in rows]


def _metric_achievements_vs_xp_correlation(date_str):
    rows = frappe.db.sql(
        """
        SELECT achievement_count, AVG(xp)::float AS avg_xp
          FROM (
            SELECT cl.name, cl.xp, COUNT(cla.name) AS achievement_count
              FROM "tabCitizenship Learner" cl
         LEFT JOIN "tabCitizenship Learner Achievement" cla
                ON cla.parent = cl.name
             GROUP BY cl.name, cl.xp
          ) sub
         GROUP BY achievement_count
         ORDER BY achievement_count
        """,
        as_dict=True,
    )
    return [[date_str, r.achievement_count, round(r.avg_xp or 0, 2)] for r in rows]


def _metric_achievements_by_level(date_str):
    rows = frappe.db.sql(
        """
        SELECT cl.level, COUNT(cla.name) AS n
          FROM "tabCitizenship Learner" cl
     LEFT JOIN "tabCitizenship Learner Achievement" cla
             ON cla.parent = cl.name
         GROUP BY cl.level
        """,
        as_dict=True,
    )
    return [[date_str, r.level or "Unset", r.n or 0] for r in rows]


def _metric_engagement_by_language(date_str):
    rows = frappe.db.sql(
        """
        SELECT language, COUNT(*) AS n,
               SUM(CASE WHEN last_activity_date >= CURRENT_DATE - INTERVAL '7 DAYS' THEN 1 ELSE 0 END) AS active_7d
          FROM "tabCitizenship Learner"
         GROUP BY language
        """,
        as_dict=True,
    )
    return [[date_str, r.language or "Unset", r.n, r.active_7d or 0] for r in rows]


def _metric_engagement_by_age_group(date_str):
    rows = frappe.db.sql(
        """
        SELECT
          CASE
            WHEN birthdate IS NULL THEN 'Unset'
            WHEN DATE_PART('year', AGE(birthdate)) < 10 THEN 'Under 10'
            WHEN DATE_PART('year', AGE(birthdate)) < 13 THEN '10-12'
            WHEN DATE_PART('year', AGE(birthdate)) < 16 THEN '13-15'
            WHEN DATE_PART('year', AGE(birthdate)) < 19 THEN '16-18'
            ELSE '19+'
          END AS age_band,
          COUNT(*) AS n,
          SUM(CASE WHEN last_activity_date >= CURRENT_DATE - INTERVAL '7 DAYS' THEN 1 ELSE 0 END) AS active_7d
          FROM "tabCitizenship Learner"
         GROUP BY age_band
        """,
        as_dict=True,
    )
    return [[date_str, r.age_band, r.n, r.active_7d or 0] for r in rows]


def _metric_level_progression_by_language(date_str):
    rows = frappe.db.sql(
        """
        SELECT language, level, COUNT(*) AS n
          FROM "tabCitizenship Learner"
         GROUP BY language, level
        """,
        as_dict=True,
    )
    return [[date_str, r.language or "Unset", r.level or "Unset", r.n] for r in rows]


def _metric_top_xp_earners_all_time():
    rows = frappe.db.sql(
        """
        SELECT name AS learner_id, xp
          FROM "tabCitizenship Learner"
         ORDER BY xp DESC
         LIMIT %s
        """,
        (_TOP_N_XP_EARNERS,),
        as_dict=True,
    )
    return [[r.learner_id, r.xp or 0] for r in rows]


def _metric_engagement_by_district():
    rows = frappe.db.sql(
        """
        SELECT sc.district AS district_id, COUNT(*) AS n,
               SUM(CASE WHEN cl.last_activity_date >= CURRENT_DATE - INTERVAL '7 DAYS' THEN 1 ELSE 0 END) AS active_7d
          FROM "tabCitizenship Learner" cl
          JOIN "tabSchool" sc ON sc.name = cl.school
         GROUP BY sc.district
        """,
        as_dict=True,
    )
    return [[r.district_id or "Unset", r.n, r.active_7d or 0] for r in rows]


def _metric_school_performance_ranking():
    rows = frappe.db.sql(
        """
        SELECT cl.school AS school_id, AVG(cl.xp)::float AS avg_xp, COUNT(*) AS n
          FROM "tabCitizenship Learner" cl
         GROUP BY cl.school
         ORDER BY avg_xp DESC
        """,
        as_dict=True,
    )
    return [[r.school_id or "Unset", round(r.avg_xp or 0, 2), r.n] for r in rows]


def _metric_district_streak_health():
    rows = frappe.db.sql(
        """
        SELECT sc.district AS district_id, AVG(cl.streak)::float AS avg_streak
          FROM "tabCitizenship Learner" cl
          JOIN "tabSchool" sc ON sc.name = cl.school
         GROUP BY sc.district
        """,
        as_dict=True,
    )
    return [[r.district_id or "Unset", round(r.avg_streak or 0, 2)] for r in rows]


def _metric_zero_xp_learners_by_school_district():
    rows = frappe.db.sql(
        """
        SELECT cl.school AS school_id, sc.district AS district_id, COUNT(*) AS n
          FROM "tabCitizenship Learner" cl
          JOIN "tabSchool" sc ON sc.name = cl.school
         WHERE cl.xp = 0
         GROUP BY cl.school, sc.district
        """,
        as_dict=True,
    )
    return [[r.school_id or "Unset", r.district_id or "Unset", r.n] for r in rows]


def _metric_low_velocity_learners():
    row = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
          FROM "tabCitizenship Learner"
         WHERE (xp_d0 + xp_d1 + xp_d2 + xp_d3 + xp_d4 + xp_d5 + xp_d6) < 20
           AND last_activity_date >= CURRENT_DATE - INTERVAL '7 DAYS'
        """,
        as_dict=True,
    )[0]
    return [[row.n or 0]]


def _metric_streak_broken_after_long_run():
    row = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
          FROM "tabCitizenship Learner"
         WHERE streak = 0
           AND longest_streak >= 14
        """,
        as_dict=True,
    )[0]
    return [[row.n or 0]]


def _metric_stuck_at_level_1():
    row = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
          FROM "tabCitizenship Learner"
         WHERE level = 'Level 1'
           AND xp >= 500
        """,
        as_dict=True,
    )[0]
    return [[row.n or 0]]


_DAILY_HISTORY_METRICS = {
    "DAL": _metric_dal,
    "XP-per-weekday": _metric_xp_per_weekday,
    "Weekly-XP-histogram": _metric_weekly_xp_histogram,
    "MAL": _metric_mal,
    "Level-distribution": _metric_level_distribution,
    "Level-vs-XP-stats": _metric_level_vs_xp_stats,
    "XP-velocity-by-level": _metric_xp_velocity_by_level,
    "Streak-length-histogram": _metric_streak_length_histogram,
    "Streak-gap-count": _metric_streak_gap_count,
    "Churn-risk-segments": _metric_churn_risk_segments,
    "Reengagement-after-gap": _metric_reengagement_after_gap,
    "Enrollment-count-distribution": _metric_enrollment_count_distribution,
    "Achievement-unlock-rates": _metric_achievement_unlock_rates,
    "Achievements-vs-XP-correlation": _metric_achievements_vs_xp_correlation,
    "Achievements-by-level": _metric_achievements_by_level,
    "Engagement-by-language": _metric_engagement_by_language,
    "Engagement-by-age-group": _metric_engagement_by_age_group,
    "Level-progression-by-language": _metric_level_progression_by_language,
}

_CURRENT_ONLY_METRICS = {
    "Top-XP-earners-all-time": _metric_top_xp_earners_all_time,
    "Engagement-by-district": _metric_engagement_by_district,
    "School-performance-ranking": _metric_school_performance_ranking,
    "District-streak-health": _metric_district_streak_health,
    "Zero-XP-learners-by-school-district": _metric_zero_xp_learners_by_school_district,
    "Low-velocity-learners": _metric_low_velocity_learners,
    "Streak-broken-after-long-run": _metric_streak_broken_after_long_run,
    "Stuck-at-Level-1": _metric_stuck_at_level_1,
}


def _compute_all_metrics() -> dict:
    date_str = _ist_date_str()
    payload = {}
    for tab_name, fn in _DAILY_HISTORY_METRICS.items():
        payload[tab_name] = {"mode": "append", "rows": fn(date_str)}
    for tab_name, fn in _CURRENT_ONLY_METRICS.items():
        payload[tab_name] = {"mode": "replace", "rows": fn()}
    return payload


def _send_to_apps_script(payload: dict):
    webapp_url = frappe.get_doc("Secrets", "appsheet_webapp_url").get_password("value")
    webapp_secret = frappe.get_doc("Secrets", "appsheet_webapp_secret").get_password("value")
    body = json.dumps({"tabs": payload}).encode()
    req = urllib.request.Request(
        webapp_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-CA-Secret": webapp_secret,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
        resp_body = json.loads(resp.read().decode())
    failed = resp_body.get("failed") or []
    if failed:
        raise Exception(f"Apps Script reported failed tabs: {failed}")
    return resp_body


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


def run_analytics_report():
    tracker = _get_or_create_tracker()
    if _is_paused(tracker):
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("CA Analytics report already running, skipping.")
        return
    lock_ttl = _dynamic_lock_ttl()
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    try:
        _wait_for_rotation_lock_clear()
        if not rotation_succeeded_today():
            raise Exception("XP window rotation has not succeeded today; analytics report skipped")

        payload = _compute_all_metrics()
        _send_to_apps_script(payload)

        _mark(tracker, "Success", time.time() - t0)
        frappe.logger().info(
            f"CA Analytics report done in {round(time.time() - t0, 1)}s. FreeMB={_free_mb()}"
        )
    except Exception as e:
        _mark(tracker, "Failed", time.time() - t0, str(e)[:5000])
        frappe.log_error(str(e), "CA Analytics report failed")
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)