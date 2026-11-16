"""
shared/jobs/gallery_promotion_sweep.py
Nightly sweep: promotes eligible graded submissions from GCS to R2 and
indexes them into the Worker's D1 gallery_items table via chunked
/internal/gallery/index calls, using /internal/gallery/known_ids to
compute the pending = eligible minus known set-difference.

FIX (dead lookback config): _resolve_sweep_window previously ignored
Shared Settings.gallery_sweep_lookback_days entirely and always used a
hardcoded 26h rolling window, with hit_ceiling always False — so a sweep
that failed for longer than the configured ceiling silently never
widened its window, and older pending submissions were never picked up.
It now anchors to the last successful sweep's own finished_at (read from
Shared Logs), falling back to the full lookback ceiling only on the very
first run or when the gap since last success exceeds that ceiling —
hit_ceiling now reflects that real condition instead of always being False.
"""

from __future__ import annotations

import mimetypes
import time
from typing import Optional, TypedDict

import frappe

from shared.config.secrets_cache import (
    get_gcs_credentials,
    get_r2_credentials,
    get_r2_sweep_batch_size,
    get_gallery_index_chunk_size,
    get_gallery_sweep_lookback_days,
)
from shared.submission.object_naming import (
    build_object_key,
    extract_gcs_bucket_and_key,
    normalize_assignment_id_for_scope,
    sanitize_scope_value,
    submission_type_from_content_type,
    submission_type_from_ext,
    resolve_wire_submission_id,
)
from shared.submission.status import is_submission_complete
from shared.progress.unit_progress import find_unit_progress_row_for_submission
from shared.storage.gallery_promotion import (
    notify_worker_gallery_index_batch,
    fetch_worker_known_submission_ids,
)
from shared.jobs._log import log_job_run

_GCS_DOWNLOAD_SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"
_GCS_API_TIMEOUT_SECONDS = 30

# Small safety overlap applied on top of the last-success anchor, so nothing
# right at the boundary is missed due to clock/commit skew between runs.
ROLLING_WINDOW_HOURS = 26


class R2PromotionResult(TypedDict):
    r2_object_key: str
    media_type: str


def _last_successful_sweep_epoch() -> Optional[int]:
    """Reads this job's own last successful finish time from Shared Logs
    (written by log_job_run at the bottom of run()). None if the sweep has
    never succeeded before."""
    rows = frappe.db.sql(
        """
        SELECT finished_at FROM "tabShared Logs"
         WHERE source = 'gallery_promotion_sweep' AND status = 'success'
         ORDER BY finished_at DESC
         LIMIT 1
        """,
        as_dict=True,
    )
    if not rows or not rows[0].get("finished_at"):
        return None
    return int(rows[0]["finished_at"].timestamp())


def _resolve_sweep_window() -> tuple[int, bool]:
    """Anchors to the last successful sweep run, with a bounded safety
    overlap, instead of a hardcoded rolling window. Falls back to the full
    configured lookback ceiling (Shared Settings.gallery_sweep_lookback_days)
    only on the very first-ever run, or if the gap since the last success
    exceeds that ceiling — in which case hit_ceiling is reported True so
    callers/analytics can see the fallback actually fired."""
    ceiling_seconds = get_gallery_sweep_lookback_days() * 86400
    now = int(time.time())
    last_success = _last_successful_sweep_epoch()

    if last_success is None:
        return now - ceiling_seconds, False

    gap_seconds = now - last_success
    if gap_seconds > ceiling_seconds:
        return now - ceiling_seconds, True

    overlap_seconds = min(ROLLING_WINDOW_HOURS * 3600, ceiling_seconds)
    return last_success - overlap_seconds, False


def _fetch_eligible_submissions(since_epoch: int, limit: int) -> list[dict]:
    from datetime import datetime

    since_dt = datetime.fromtimestamp(since_epoch)
    complete_statuses = tuple(("Success - Original", "Success - Flagged"))

    rows = frappe.db.sql(
        """
        SELECT name, assign_id, assignment_id_link, student_id, submission_url,
               grade, created_at, completed_at, status, result_status
          FROM "tabSubmission"
         WHERE status = 'Completed'
           AND result_status IN %(statuses)s
           AND completed_at >= %(since)s
         ORDER BY completed_at ASC
         LIMIT %(limit)s
        """,
        {"statuses": complete_statuses, "since": since_dt, "limit": limit},
        as_dict=True,
    )
    return rows


def _count_eligible_submissions(since_epoch: int) -> int:
    from datetime import datetime

    since_dt = datetime.fromtimestamp(since_epoch)
    complete_statuses = tuple(("Success - Original", "Success - Flagged"))

    result = frappe.db.sql(
        """
        SELECT COUNT(*) FROM "tabSubmission"
         WHERE status = 'Completed'
           AND result_status IN %(statuses)s
           AND completed_at >= %(since)s
        """,
        {"statuses": complete_statuses, "since": since_dt},
    )
    return result[0][0] if result else 0


def _row_is_indexable(sub: dict) -> bool:
    student = frappe.db.get_value(
        "Student", sub["student_id"], ["grade", "state_id", "district_id", "school_id"], as_dict=True,
    )
    if not student or not student.get("grade"):
        frappe.logger().info(f"gallery sweep: skipping submission_id={sub['name']} -- student has no grade set")
        return False
    if not (student.get("state_id") and student.get("district_id") and student.get("school_id")):
        frappe.logger().info(f"gallery sweep: skipping submission_id={sub['name']} -- student missing state/district/school")
        return False
    if not (sub.get("assign_id") or sub.get("assignment_id_link")):
        frappe.logger().info(f"gallery sweep: skipping submission_id={sub['name']} -- no assignment_id on submission")
        return False
    return True


def _promote_one_submission_to_r2(
    gcs_submission_url: str | None,
    assignment_id: str | None,
    student_id: str | None,
    submission_id: str,
    attempt: int | None = None,
) -> Optional[R2PromotionResult]:
    if not assignment_id or not student_id or not submission_id:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: missing assignment_id/student_id/"
            f"submission_id -- skipping promotion for submission_id={submission_id!r}."
        )
        return None

    parsed_source = extract_gcs_bucket_and_key(gcs_submission_url)
    if not parsed_source:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: submission_id={submission_id} has no "
            f"usable GCS submission_url ({gcs_submission_url!r}) -- skipping."
        )
        return None
    source_bucket, source_object_key = parsed_source

    r2_creds = get_r2_credentials()
    if not r2_creds.get("account_id") or not r2_creds.get("bucket"):
        frappe.logger().info(f"_promote_one_submission_to_r2: R2 not configured -- skipping submission_id={submission_id}.")
        return None

    try:
        gcs_creds = get_gcs_credentials()
    except Exception:
        frappe.logger().info(f"_promote_one_submission_to_r2: GCS not configured -- skipping submission_id={submission_id}.")
        return None
    if not gcs_creds.get("service_account_json"):
        frappe.logger().info(f"_promote_one_submission_to_r2: GCS service account missing -- skipping submission_id={submission_id}.")
        return None

    downloaded = _download_from_gcs(gcs_creds["service_account_json"], source_bucket, source_object_key)
    if downloaded is None:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: source object not found (bucket={source_bucket!r}, "
            f"key={source_object_key!r}) for submission_id={submission_id} -- skipping."
        )
        return None
    content_bytes, content_type = downloaded

    source_ext = source_object_key.rsplit(".", 1)[-1].lower() if "." in source_object_key else ""
    media_type = submission_type_from_ext(source_ext) or submission_type_from_content_type(content_type)
    if not media_type:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: unrecognized format (ext={source_ext!r}, "
            f"content_type={content_type!r}) for submission_id={submission_id} -- skipping."
        )
        return None

    resolved_ext = source_ext or mimetypes.guess_extension(content_type or "") or ""
    resolved_ext = resolved_ext.lstrip(".").lower()
    if not resolved_ext:
        frappe.logger().info(f"_promote_one_submission_to_r2: could not resolve extension for submission_id={submission_id} -- skipping.")
        return None

    r2_object_key = build_object_key(
        assignment_id=assignment_id,
        student_id=student_id,
        submission_id=submission_id,
        attempt=int(attempt) if attempt else 1,
        ext=resolved_ext,
    )

    _upload_to_r2(r2_creds, r2_object_key, content_bytes, content_type)

    frappe.logger().info(
        f"_promote_one_submission_to_r2: promoted submission_id={submission_id} "
        f"from gcs://{source_bucket}/{source_object_key} to r2 key={r2_object_key}, media_type={media_type}."
    )

    return {"r2_object_key": r2_object_key, "media_type": media_type}


def _download_from_gcs(service_account_json: str, bucket: str, object_key: str) -> Optional[tuple[bytes, str | None]]:
    from google.cloud import storage as gcs_storage
    from google.oauth2 import service_account
    import json as _json

    info = _json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(info, scopes=[_GCS_DOWNLOAD_SCOPE])
    client = gcs_storage.Client(project=info.get("project_id"), credentials=credentials)
    bucket_ref = client.bucket(bucket)
    blob = bucket_ref.blob(object_key)

    if not blob.exists(client=client):
        return None

    blob.reload(client=client)
    content_bytes = blob.download_as_bytes(client=client, timeout=_GCS_API_TIMEOUT_SECONDS)
    content_type = blob.content_type
    return content_bytes, content_type


def _upload_to_r2(r2_creds: dict, object_key: str, content_bytes: bytes, content_type: str | None) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{r2_creds['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=r2_creds["access_key_id"],
        aws_secret_access_key=r2_creds["secret_access_key"],
        region_name="auto",
    )
    put_kwargs = {"Bucket": r2_creds["bucket"], "Key": object_key, "Body": content_bytes}
    if content_type:
        put_kwargs["ContentType"] = content_type
    client.put_object(**put_kwargs)


def _build_index_payload(sub: dict, r2_object_key: str, media_type: str) -> dict:
    student = frappe.db.get_value(
        "Student", sub["student_id"],
        ["name1", "grade", "school_id", "state_id", "district_id"], as_dict=True,
    ) or {}

    raw_assignment_id = sub.get("assign_id") or sub.get("assignment_id_link")
    grade = int(student["grade"]) if student.get("grade") else None

    return {
        "academic_year": (sub.get("completed_at") or sub.get("created_at") or frappe.utils.now_datetime()).year,
        "assignment_id": normalize_assignment_id_for_scope(raw_assignment_id),
        "student_id": sub["student_id"],
        "submission_id": resolve_wire_submission_id(sub),
        "first_name": student.get("name1"),
        "state": sanitize_scope_value(student.get("state_id")),
        "district": sanitize_scope_value(student.get("district_id")),
        "school": sanitize_scope_value(student.get("school_id")),
        "grade": grade,
        "media_type": media_type,
        "object_key": r2_object_key,
        "score": sub.get("grade"),
        "promoted_at": int(time.time()),
    }


def run_sweep() -> dict:
    since_epoch, hit_ceiling = _resolve_sweep_window()
    batch_size = get_r2_sweep_batch_size()
    chunk_size = get_gallery_index_chunk_size()

    eligible = _fetch_eligible_submissions(since_epoch, batch_size)
    known_ids = set(fetch_worker_known_submission_ids(since_epoch))

    candidate = [s for s in eligible if s["name"] not in known_ids]

    skipped_count = 0
    pending: list[dict] = []
    for sub in candidate:
        if _row_is_indexable(sub):
            pending.append(sub)
        else:
            skipped_count += 1

    attempted = len(pending)
    r2_promoted = 0
    r2_failed = 0
    promoted_rows: list[dict] = []

    for sub in pending:
        try:
            row = find_unit_progress_row_for_submission(sub["name"])
            attempt_number = (row or {}).get("submission_attempts") or 1

            result = _promote_one_submission_to_r2(
                gcs_submission_url=sub.get("submission_url"),
                assignment_id=sub.get("assign_id") or sub.get("assignment_id_link"),
                student_id=sub.get("student_id"),
                submission_id=sub["name"],
                attempt=attempt_number,
            )
            if result:
                promoted_rows.append(_build_index_payload(sub, result["r2_object_key"], result["media_type"]))
                r2_promoted += 1
        except Exception:
            r2_failed += 1
            frappe.logger().warning(f"run_sweep: R2 promotion failed for submission_id={sub['name']}", exc_info=True)
            continue

    d1_chunks_total = 0
    d1_chunks_failed = 0
    for i in range(0, len(promoted_rows), chunk_size):
        chunk = promoted_rows[i:i + chunk_size]
        d1_chunks_total += 1
        try:
            notify_worker_gallery_index_batch(chunk)
        except Exception:
            d1_chunks_failed += 1
            frappe.logger().warning(f"run_sweep: D1 index chunk {d1_chunks_total} failed ({len(chunk)} rows)", exc_info=True)
            continue

    remaining_total_eligible = _count_eligible_submissions(since_epoch)
    remaining_backlog_estimate = max(remaining_total_eligible - r2_promoted, 0)

    return {
        "attempted": attempted,
        "r2_promoted": r2_promoted,
        "r2_failed": r2_failed,
        "d1_chunks_total": d1_chunks_total,
        "d1_chunks_failed": d1_chunks_failed,
        "remaining_backlog_estimate": remaining_backlog_estimate,
        "hit_lookback_ceiling": hit_ceiling,
        "skipped_incomplete_profile": skipped_count,
    }


def run() -> dict:
    from shared.config.secrets_cache import get_r2_sweep_enabled

    started = frappe.utils.now_datetime()

    if not get_r2_sweep_enabled():
        log_job_run(
            "gallery_promotion_sweep", "scheduled", "success",
            started, frappe.utils.now_datetime(), 0, {"skipped": True, "reason": "disabled"},
        )
        return {"status": "success", "skipped": True, "r2_promoted": 0, "remaining_backlog_estimate": 0}

    try:
        result = run_sweep()
        log_job_run(
            "gallery_promotion_sweep", "scheduled", "success",
            started, frappe.utils.now_datetime(), result["r2_promoted"], result,
        )
        return {"status": "success", **result}
    except Exception as exc:
        log_job_run(
            "gallery_promotion_sweep", "scheduled", "failed",
            started, frappe.utils.now_datetime(), 0, {"error": str(exc)},
        )
        return {"status": "failed", "error": str(exc), "r2_promoted": 0, "remaining_backlog_estimate": 0}