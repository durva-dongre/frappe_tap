import frappe
import json
import time
import psutil
import boto3
from botocore.client import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from tap_lms.ca.api.progress.learner import flush_xp_queue

BUCKET_INTERVALS      = 20
JOB_LOCK_KEY          = "ca:leaderboard:running"
JOB_START_KEY         = "ca:leaderboard:started_at"

_MEM_FLOOR_MB         = 512
_MEM_TARGET_PCT       = 0.35
_ROTATE_BATCH_MIN     = 2000
_ROTATE_BATCH_MAX     = 25000
_STUDENT_CHUNK_MIN    = 500
_STUDENT_CHUNK_MAX    = 20000
_BUCKET_CHUNK_MIN     = 1000
_BUCKET_CHUNK_MAX     = 50000
_UPLOAD_WORKERS_MIN   = 4
_UPLOAD_WORKERS_MAX   = 40
_SLEEP_BETWEEN_CHUNKS = 0.05


def _now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _dynamic_upload_workers() -> int:
    cpu = psutil.cpu_percent(interval=0.2)
    if cpu >= 80:
        return _UPLOAD_WORKERS_MIN
    ratio = 1.0 - (cpu / 100.0)
    return max(_UPLOAD_WORKERS_MIN, min(int(_UPLOAD_WORKERS_MAX * ratio), _UPLOAD_WORKERS_MAX))


def _dynamic_lock_ttl() -> int:
    try:
        total_learners = frappe.db.sql(
            'SELECT COUNT(*) AS n FROM "tabCitizenship Learner"', as_dict=True
        )[0].n or 0
    except Exception:
        total_learners = 0
    base = 600
    per_million = 900
    return int(base + (total_learners / 1_000_000) * per_million)


def _get_r2_client():
    r2_account_id = frappe.get_doc("Secrets", "r2_account_id").get_password("value")
    r2_access_key = frappe.get_doc("Secrets", "r2_access_key").get_password("value")
    r2_secret_key = frappe.get_doc("Secrets", "r2_secret_key").get_password("value")
    r2_bucket     = frappe.get_doc("Secrets", "r2_bucket").get_password("value")
    workers = _dynamic_upload_workers()
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=r2_access_key,
        aws_secret_access_key=r2_secret_key,
        config=Config(signature_version="s3v4", max_pool_connections=workers + 4),
        region_name="auto",
    )
    return client, r2_bucket, workers


def _upload(client, bucket, key, data: dict):
    body = json.dumps(data, separators=(",", ":")).encode()
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")


def _percentile_thresholds(sorted_scores: list, intervals: int = BUCKET_INTERVALS):
    n = len(sorted_scores)
    if not n:
        return []
    thresholds = []
    for i in range(1, intervals + 1):
        idx = min(int(n * i / intervals), n - 1)
        thresholds.append(sorted_scores[idx])
    thresholds[-1] = 99999
    return thresholds


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
        placeholders = ",".join(["%s"] * len(names))
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
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)


def _get_active_scope():
    rows = frappe.db.sql(
        """
        SELECT DISTINCT
               sc.name     AS school_id,
               sc.district AS district_id,
               sc.state    AS state_id
          FROM "tabCitizenship Learner" cl
          JOIN "tabStudent" s  ON s.name = cl.student
          JOIN "tabSchool"  sc ON sc.name = s.school_id
         WHERE cl.modified >= NOW() - INTERVAL '1 DAY'
        """,
        as_dict=True,
    )
    school_ids   = list({r.school_id   for r in rows if r.school_id})
    district_ids = list({r.district_id for r in rows if r.district_id})
    state_ids    = list({r.state_id    for r in rows if r.state_id})
    return school_ids, district_ids, state_ids


def _fetch_active_students_chunked(school_ids: list):
    if not school_ids:
        return {}, {}, {}

    schools: dict   = {}
    districts: dict = {}
    states: dict    = {}

    school_placeholders = ",".join(["%s"] * len(school_ids))
    last_student = ""

    while True:
        chunk_size = _dynamic_batch(_STUDENT_CHUNK_MIN, _STUDENT_CHUNK_MAX)
        rows = frappe.db.sql(
            f"""
            SELECT cl.weekly_xp,
                   s.name      AS student_id,
                   s.name1     AS student_name,
                   s.school_id AS school_id,
                   sc.district AS district_id,
                   sc.state    AS state_id,
                   COALESCE(
                       (
                           SELECT sap.avatar
                             FROM "tabStudent Auth Profile" sap
                            WHERE sap.student = s.name
                            LIMIT 1
                       ), 1
                   ) AS avatar
              FROM "tabCitizenship Learner" cl
              JOIN "tabStudent" s  ON s.name = cl.student
              JOIN "tabSchool"  sc ON sc.name = s.school_id
             WHERE s.school_id IN ({school_placeholders})
               AND s.name > %s
             ORDER BY s.name
             LIMIT %s
            """,
            (*school_ids, last_student, chunk_size),
            as_dict=True,
        )
        if not rows:
            break

        for r in rows:
            entry = (r.student_id, r.student_name or "", r.weekly_xp or 0, r.avatar or 1)
            if r.school_id:
                schools.setdefault(r.school_id, []).append(entry)
            if r.district_id:
                districts.setdefault(r.district_id, []).append(entry)
            if r.state_id:
                states.setdefault(r.state_id, []).append(entry)

        last_student = rows[-1].student_id
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)

    return schools, districts, states


def _stream_bucket_data(district_scores: dict, state_scores: dict, national_scores: list):
    last_student = ""
    while True:
        chunk_size = _dynamic_batch(_BUCKET_CHUNK_MIN, _BUCKET_CHUNK_MAX)
        rows = frappe.db.sql(
            """
            SELECT sc.district AS district_id,
                   sc.state    AS state_id,
                   cl.weekly_xp,
                   s.name      AS student_id
              FROM "tabCitizenship Learner" cl
              JOIN "tabStudent" s  ON s.name = cl.student
              JOIN "tabSchool"  sc ON sc.name = s.school_id
             WHERE s.name > %s
             ORDER BY s.name
             LIMIT %s
            """,
            (last_student, chunk_size),
            as_dict=True,
        )
        if not rows:
            break
        for r in rows:
            w = r.weekly_xp or 0
            if r.district_id:
                district_scores.setdefault(r.district_id, []).append(w)
            if r.state_id:
                state_scores.setdefault(r.state_id, []).append(w)
            national_scores.append(w)
        last_student = rows[-1].student_id
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)


def _fetch_national_top100():
    return frappe.db.sql(
        """
        SELECT s.name      AS sid,
               s.name1     AS n,
               cl.weekly_xp AS w,
               COALESCE(
                   (
                       SELECT sap.avatar
                         FROM "tabStudent Auth Profile" sap
                        WHERE sap.student = s.name
                        LIMIT 1
                   ), 1
               ) AS a
          FROM "tabCitizenship Learner" cl
          JOIN "tabStudent" s ON s.name = cl.student
         ORDER BY cl.weekly_xp DESC
         LIMIT 100
        """,
        as_dict=True,
    )


def _build_school_file(entries: list, updated_at: str) -> dict:
    entries.sort(key=lambda x: x[2], reverse=True)
    return {"u": [[s, n, w, a] for s, n, w, a in entries], "t": updated_at}


def _build_geo_file(entries: list, updated_at: str) -> dict:
    entries.sort(key=lambda x: x[2], reverse=True)
    return {"u": [[s, n, w, a] for s, n, w, a in entries[:100]], "t": updated_at}


def _build_bucket(scores: list, total: int, updated_at: str) -> dict:
    scores.sort()
    return {"total": total, "thresholds": _percentile_thresholds(scores), "t": updated_at}


def _upload_streaming(client, bucket, uploads_iter, workers: int):
    batch_size = max(workers * 4, 40)
    batch = []

    def _flush(b, w):
        with ThreadPoolExecutor(max_workers=w) as ex:
            futures = {ex.submit(_upload, client, bucket, k, d): k for k, d in b}
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as e:
                    frappe.log_error(str(e), "CA Leaderboard Upload Error")

    for item in uploads_iter:
        batch.append(item)
        if len(batch) >= batch_size:
            _flush(batch, workers)
            batch = []
            workers = _dynamic_upload_workers()
            batch_size = max(workers * 4, 40)

    if batch:
        _flush(batch, workers)


def run_leaderboard_batch():
    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("CA Leaderboard batch already running, skipping.")
        return
    lock_ttl = _dynamic_lock_ttl()
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)
    try:
        _run_leaderboard_batch_inner()
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)


def _run_leaderboard_batch_inner():
    updated_at = _now_utc_iso()
    t0 = time.time()

    try:
        _rotate_xp_window()
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: rotate failed")
        return

    try:
        flush_xp_queue()
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: flush_xp_queue failed")
        return

    try:
        school_ids, district_ids, state_ids = _get_active_scope()
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: scope fetch failed")
        return

    try:
        schools_map, districts_map, states_map = _fetch_active_students_chunked(school_ids)
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: student fetch failed")
        return

    district_scores: dict = {}
    state_scores: dict    = {}
    national_scores: list = []

    try:
        _stream_bucket_data(district_scores, state_scores, national_scores)
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: bucket stream failed")
        return

    try:
        national_top = _fetch_national_top100()
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: national top100 failed")
        return

    try:
        client, r2_bucket, workers = _get_r2_client()
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: R2 client failed")
        return

    def _gen_uploads():
        for sid, entries in schools_map.items():
            yield f"leaderboards/schools/{sid}.json", _build_school_file(entries, updated_at)
        for did, entries in districts_map.items():
            yield f"leaderboards/districts/{did}.json", _build_geo_file(entries, updated_at)
        for stid, entries in states_map.items():
            yield f"leaderboards/states/{stid}.json", _build_geo_file(entries, updated_at)
        yield (
            "leaderboards/national.json",
            {"u": [[r.sid, r.n, r.w, r.a] for r in national_top], "t": updated_at},
        )
        for did, scores in district_scores.items():
            yield f"leaderboards/buckets/district_{did}.json", _build_bucket(scores, len(scores), updated_at)
        for stid, scores in state_scores.items():
            yield f"leaderboards/buckets/state_{stid}.json", _build_bucket(scores, len(scores), updated_at)
        yield (
            "leaderboards/buckets/national.json",
            _build_bucket(national_scores, len(national_scores), updated_at),
        )

    try:
        _upload_streaming(client, r2_bucket, _gen_uploads(), workers)
    except Exception as e:
        frappe.log_error(str(e), "CA Leaderboard: R2 upload failed")
        return

    elapsed = round(time.time() - t0, 1)
    frappe.logger().info(
        f"CA Leaderboard done in {elapsed}s. "
        f"Schools={len(schools_map)} Districts={len(districts_map)} "
        f"States={len(states_map)} FreeMB={_free_mb()}"
    )