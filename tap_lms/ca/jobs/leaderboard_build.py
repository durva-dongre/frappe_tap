import frappe
import json
import time
import psutil
import boto3
from botocore.client import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from tap_lms.ca.jobs._shared import rotation_succeeded_today, send_job_log

JOB_KEY = "Leaderboard Build"
JOB_LABEL = "Leaderboard Build"
BUCKET_INTERVALS = 20
JOB_LOCK_KEY = "ca:leaderboard:running"
JOB_START_KEY = "ca:leaderboard:started_at"

_MEM_FLOOR_MB = 512
_MEM_TARGET_PCT = 0.35
_STUDENT_CHUNK_MIN = 500
_STUDENT_CHUNK_MAX = 20000
_BUCKET_CHUNK_MIN = 1000
_BUCKET_CHUNK_MAX = 50000
_UPLOAD_WORKERS_MIN = 4
_UPLOAD_WORKERS_MAX = 40
_SLEEP_BETWEEN_CHUNKS = 0.05
_LOCK_TTL_BASE_SEC = 600
_LOCK_TTL_PER_MILLION_SEC = 900
_TOP_N_SCHOOL = 100
_TOP_N_GEO = 100
_TOP_N_NATIONAL = 100
_EDGE_CACHE_SECONDS = 86400


def _now_utc_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


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
    return int(_LOCK_TTL_BASE_SEC + (total_learners / 1_000_000) * _LOCK_TTL_PER_MILLION_SEC)


def _get_r2_client():
    r2_account_id = frappe.get_doc("Secrets", "r2_account_id").get_password("value")
    r2_access_key = frappe.get_doc("Secrets", "r2_access_key").get_password("value")
    r2_secret_key = frappe.get_doc("Secrets", "r2_secret_key").get_password("value")
    r2_bucket = frappe.get_doc("Secrets", "r2_bucket").get_password("value")
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
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        CacheControl=f"public, max-age={_EDGE_CACHE_SECONDS}",
    )


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


def _get_active_scope():
    rows = frappe.db.sql(
        """
        SELECT DISTINCT
               cl.school   AS school_id,
               cl.district AS district_id,
               cl.state    AS state_id
          FROM "tabCitizenship Learner" cl
         WHERE cl.modified >= NOW() - INTERVAL '1 DAY'
        """,
        as_dict=True,
    )
    school_ids = list({r.school_id for r in rows if r.school_id})
    district_ids = list({r.district_id for r in rows if r.district_id})
    state_ids = list({r.state_id for r in rows if r.state_id})
    return school_ids, district_ids, state_ids


def _fetch_active_students_chunked(school_ids: list):
    if not school_ids:
        return {}, {}, {}

    schools: dict = {}
    districts: dict = {}
    states: dict = {}

    school_placeholders = ",".join(["%s"] * len(school_ids))
    last_name = ""

    while True:
        chunk_size = _dynamic_batch(_STUDENT_CHUNK_MIN, _STUDENT_CHUNK_MAX)
        rows = frappe.db.sql(
            f"""
            SELECT cl.name         AS learner_id,
                   cl.student_name,
                   cl.weekly_xp,
                   cl.school       AS school_id,
                   cl.district     AS district_id,
                   cl.state        AS state_id,
                   COALESCE(sap.avatar, '1') AS avatar
              FROM "tabCitizenship Learner" cl
         LEFT JOIN LATERAL (
                   SELECT avatar
                     FROM "tabCitizenship Auth Profile"
                    WHERE citizenship_learner = cl.name
                    LIMIT 1
                   ) sap ON true
             WHERE cl.school IN ({school_placeholders})
               AND cl.name > %s
             ORDER BY cl.name
             LIMIT %s
            """,
            (*school_ids, last_name, chunk_size),
            as_dict=True,
        )
        if not rows:
            break

        for r in rows:
            entry = (r.learner_id, r.student_name or "", r.weekly_xp or 0, r.avatar or "1")
            if r.school_id:
                schools.setdefault(r.school_id, []).append(entry)
            if r.district_id:
                districts.setdefault(r.district_id, []).append(entry)
            if r.state_id:
                states.setdefault(r.state_id, []).append(entry)

        last_name = rows[-1].learner_id
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)

    return schools, districts, states


def _stream_bucket_data(district_scores: dict, state_scores: dict, national_scores: list):
    last_name = ""
    while True:
        chunk_size = _dynamic_batch(_BUCKET_CHUNK_MIN, _BUCKET_CHUNK_MAX)
        rows = frappe.db.sql(
            """
            SELECT cl.name       AS learner_id,
                   cl.weekly_xp,
                   cl.district   AS district_id,
                   cl.state      AS state_id
              FROM "tabCitizenship Learner" cl
             WHERE cl.name > %s
             ORDER BY cl.name
             LIMIT %s
            """,
            (last_name, chunk_size),
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
        last_name = rows[-1].learner_id
        time.sleep(0.2 if _free_mb() < _MEM_FLOOR_MB else _SLEEP_BETWEEN_CHUNKS)


def _fetch_national_top():
    return frappe.db.sql(
        """
        SELECT cl.name         AS sid,
               cl.student_name AS n,
               cl.weekly_xp    AS w,
               COALESCE(sap.avatar, '1') AS a
          FROM "tabCitizenship Learner" cl
     LEFT JOIN LATERAL (
               SELECT avatar
                 FROM "tabCitizenship Auth Profile"
                WHERE citizenship_learner = cl.name
                LIMIT 1
               ) sap ON true
         ORDER BY cl.weekly_xp DESC
         LIMIT %s
        """,
        (_TOP_N_NATIONAL,),
        as_dict=True,
    )


def _build_school_file(entries: list, updated_at: str) -> dict:
    entries.sort(key=lambda x: x[2], reverse=True)
    return {"u": [[s, n, w, a] for s, n, w, a in entries[:_TOP_N_SCHOOL]], "t": updated_at}


def _build_geo_file(entries: list, updated_at: str) -> dict:
    entries.sort(key=lambda x: x[2], reverse=True)
    return {"u": [[s, n, w, a] for s, n, w, a in entries[:_TOP_N_GEO]], "t": updated_at}


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
                f.result()

    for item in uploads_iter:
        batch.append(item)
        if len(batch) >= batch_size:
            _flush(batch, workers)
            batch = []
            workers = _dynamic_upload_workers()
            batch_size = max(workers * 4, 40)

    if batch:
        _flush(batch, workers)


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


def run_leaderboard_build():
    tracker = _get_or_create_tracker()
    if _is_paused(tracker):
        tracker.status = "Paused"
        tracker.save(ignore_permissions=True)
        frappe.db.commit()
        return

    cache = frappe.cache()
    if cache.get_value(JOB_LOCK_KEY):
        frappe.logger().warning("CA Leaderboard build already running, skipping.")
        return
    lock_ttl = _dynamic_lock_ttl()
    cache.set_value(JOB_LOCK_KEY, "1", expires_in_sec=lock_ttl)
    cache.set_value(JOB_START_KEY, str(int(time.time())), expires_in_sec=lock_ttl)

    tracker.status = "Running"
    tracker.save(ignore_permissions=True)
    frappe.db.commit()

    t0 = time.time()
    records = 0
    try:
        if not rotation_succeeded_today():
            raise Exception("XP window rotation has not succeeded today; leaderboard build skipped")

        school_ids, district_ids, state_ids = _get_active_scope()
        schools_map, districts_map, states_map = _fetch_active_students_chunked(school_ids)
        records = sum(len(v) for v in schools_map.values())

        district_scores: dict = {}
        state_scores: dict = {}
        national_scores: list = []
        _stream_bucket_data(district_scores, state_scores, national_scores)

        national_top = _fetch_national_top()
        client, r2_bucket, workers = _get_r2_client()
        updated_at = _now_utc_iso()

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

        _upload_streaming(client, r2_bucket, _gen_uploads(), workers)

        duration = time.time() - t0
        _mark(tracker, "Success", duration)
        send_job_log(JOB_KEY, "Success", records, duration)
        frappe.logger().info(
            f"CA Leaderboard build done in {round(duration, 1)}s. "
            f"Schools={len(schools_map)} Districts={len(districts_map)} States={len(states_map)} FreeMB={_free_mb()}"
        )
    except Exception as e:
        duration = time.time() - t0
        _mark(tracker, "Failed", duration, str(e)[:5000])
        send_job_log(JOB_KEY, "Failed", records, duration, str(e)[:1000])
        frappe.log_error(title="CA Leaderboard build failed", message=str(e))
    finally:
        cache.delete_value(JOB_LOCK_KEY)
        cache.delete_value(JOB_START_KEY)