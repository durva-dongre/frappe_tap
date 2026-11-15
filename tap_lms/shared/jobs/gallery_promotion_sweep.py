"""
shared/jobs/gallery_promotion_sweep.py

Nightly batch job that replaces the old per-submission synchronous gallery
promotion (formerly inline in shared/submission/review_result.py). Does
everything gallery-related for one night: finds submissions that are
graded-and-complete but not yet in D1's gallery_items table, copies their
media from GCS to R2, pushes the new rows to D1 in chunks, and triggers a
cache-generation bump on the Worker so previously-cached gallery pages
pick up the new rows.

NO NEW FRAPPE DOCTYPE FIELD. "Pending" is computed purely as a set
difference between two systems that already separately know their own
state:
  - Frappe-eligible set: Submission rows with status="Completed" and a
    reward-eligible-or-flagged result_status, within a lookback window.
  - D1-known set: whatever the Worker's /internal/gallery/known_ids route
    reports as already indexed, in that same window.
  pending = eligible - known

This also makes the sweep self-healing: a row whose R2 copy succeeded but
whose D1 index call failed last night is still "not in D1," so it's
naturally re-attempted tonight with no separate stuck-state tracking.

WINDOW: fixed 26-hour rolling lookback, every night, unconditionally --
see _resolve_sweep_window below. No anchoring to this job's own run
history (previously anchored to the last successful Shared Logs row for
this job, with a lookback-day ceiling as fallback). The rolling window is
simpler to reason about and immune to being thrown off by a manual test
run, a disabled night, or a prior failure -- "last 26 hours, every night"
never needs run-history bookkeeping to stay correct. The 2-hour overlap
over a plain 24h window is deliberate headroom against clock drift and
boundary-adjacent completed_at values; re-scanning that overlap is cheap
and side-effect-free because the known_ids diff below already drops
anything D1 has already indexed before any R2 copy or D1 write happens.

BUGFIX (eligibility window field): _fetch_eligible_submissions and
_count_eligible_submissions filter on Submission.completed_at, not
created_at. A submission with normal creation time but UNUSUALLY SLOW
grading (stuck in Processing for longer than the window before finally
completing) would have a created_at that falls OUTSIDE the window by the
time it actually becomes gallery-eligible -- filtering on completed_at
(set exactly once, by feedback_processor.py::update_submission, at the
moment grading actually finishes) avoids that gap. This is also the same
field shared/jobs/analytics_daily.py already uses for its own
submission_success_original/submission_success_flagged/submission_failed
window queries, so the "day"/"window" definition is consistent across
both jobs.

A submission with completed_at IS NULL (not yet graded, or a manually
seeded/test row that bypassed the normal grading pipeline) is correctly
excluded by the `completed_at >= since` comparison -- NULL never satisfies
a >= comparison in SQL, so this requires no separate "IS NOT NULL" guard.
In real traffic, completed_at is always set by update_submission the
moment a submission finishes grading; a NULL completed_at on a Completed
submission indicates the row was created/edited outside that normal path
(e.g. manual testing) rather than a gap in the grading pipeline itself.
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
)
from shared.submission.object_naming import (
    build_object_key,
    extract_gcs_bucket_and_key,
    submission_type_from_content_type,
    submission_type_from_ext,
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

# Fixed rolling lookback window, every night. 26h (not 24h) deliberately
# overlaps the previous night's window by 2 hours as headroom against
# clock drift or a completed_at landing right at a boundary. See module
# docstring's "WINDOW" section for why re-scanning the overlap is safe.
ROLLING_WINDOW_HOURS = 26


class R2PromotionResult(TypedDict):
    r2_object_key: str
    media_type: str


def _resolve_sweep_window() -> tuple[int, bool]:
    """Returns (since_epoch, hit_lookback_ceiling). Always a fixed
    ROLLING_WINDOW_HOURS-hour lookback from right now -- no read of
    Shared Logs, no dependency on whether last night's run succeeded,
    failed, or didn't run at all.

    hit_lookback_ceiling is always False now -- the ceiling concept from
    the old anchored-window design no longer applies. Kept in the return
    shape only so run_sweep()'s own result dict, and anything downstream
    reading it (nightly_pipeline.py's pipeline_context, analytics_daily.py),
    don't need a field rename.
    """
    since_epoch = int(time.time()) - ROLLING_WINDOW_HOURS * 3600
    return since_epoch, False


def _fetch_eligible_submissions(since_epoch: int, limit: int) -> list[dict]:
    """Submissions that are Completed + is_submission_complete-eligible
    (Success - Original or Success - Flagged), whose grading COMPLETED
    within the window, oldest first, capped at `limit`. Mirrors exactly
    the completion filter review_result.py uses for is_gallery_eligible,
    just expressed as a direct SQL query here instead of an in-memory
    boolean check.

    Filters on completed_at, not created_at -- see module docstring's
    "BUGFIX" section for why: a submission's eligibility moment is when
    its grading finishes, not when it was first created.
    """
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
    """Unbounded count of the same filter _fetch_eligible_submissions uses,
    for reporting remaining backlog size -- not used to drive the loop
    itself, only to size the nightly report. Filters on completed_at, same
    as _fetch_eligible_submissions above and for the same reason."""
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


def _promote_one_submission_to_r2(
    gcs_submission_url: str | None,
    assignment_id: str | None,
    student_id: str | None,
    submission_id: str,
    attempt: int | None = None,
) -> Optional[R2PromotionResult]:
    """Copies one submission's media from GCS to R2, under the gallery's
    tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}
    key shape, and returns {"r2_object_key": ..., "media_type": ...}.

    Returns None (logged at info level) for any legitimately-nothing-to-
    promote case: missing identifiers, no usable GCS submission_url, R2
    or GCS not configured, the source object doesn't exist, or the
    extension isn't a recognized image/video format. Lets a genuine
    infrastructure error (network failure, malformed credentials, an
    unexpected R2/GCS error response) propagate -- the caller (run_sweep's
    per-row loop) catches it, logs, and continues to the next row.

    attempt defaults to 1 if not given or falsy.
    """
    if not assignment_id or not student_id or not submission_id:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: missing assignment_id/student_id/"
            f"submission_id (assignment_id={assignment_id!r}, student_id={student_id!r}, "
            f"submission_id={submission_id!r}) -- skipping promotion for this submission."
        )
        return None

    parsed_source = extract_gcs_bucket_and_key(gcs_submission_url)
    if not parsed_source:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: submission_id={submission_id} has no "
            f"usable GCS submission_url ({gcs_submission_url!r}) -- skipping promotion "
            f"(expected for text/emoji submissions, or a row whose async upload job "
            f"has not populated submission_url yet)."
        )
        return None
    source_bucket, source_object_key = parsed_source

    r2_creds = get_r2_credentials()
    if not r2_creds.get("account_id") or not r2_creds.get("bucket"):
        frappe.logger().info(
            f"_promote_one_submission_to_r2: R2 is not configured (Shared Settings."
            f"r2_account_id / r2_bucket missing) -- skipping promotion for "
            f"submission_id={submission_id}."
        )
        return None

    try:
        gcs_creds = get_gcs_credentials()
    except Exception:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: GCS is not configured -- skipping "
            f"promotion for submission_id={submission_id}."
        )
        return None
    if not gcs_creds.get("service_account_json"):
        frappe.logger().info(
            f"_promote_one_submission_to_r2: GCS service account is not configured "
            f"-- skipping promotion for submission_id={submission_id}."
        )
        return None

    downloaded = _download_from_gcs(gcs_creds["service_account_json"], source_bucket, source_object_key)
    if downloaded is None:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: source object not found on GCS "
            f"(bucket={source_bucket!r}, object_key={source_object_key!r}) for "
            f"submission_id={submission_id} -- skipping promotion."
        )
        return None
    content_bytes, content_type = downloaded

    source_ext = source_object_key.rsplit(".", 1)[-1].lower() if "." in source_object_key else ""
    media_type = submission_type_from_ext(source_ext) or submission_type_from_content_type(content_type)
    if not media_type:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: source object's extension "
            f"({source_ext!r}) and content type ({content_type!r}) do not resolve to "
            f"a recognized image/video format for submission_id={submission_id} -- "
            f"skipping promotion (this submission is not gallery-eligible media)."
        )
        return None

    resolved_ext = source_ext or mimetypes.guess_extension(content_type or "") or ""
    resolved_ext = resolved_ext.lstrip(".").lower()
    if not resolved_ext:
        frappe.logger().info(
            f"_promote_one_submission_to_r2: could not resolve a file extension for "
            f"submission_id={submission_id} -- skipping promotion."
        )
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
        f"from gcs://{source_bucket}/{source_object_key} to r2 key={r2_object_key}, "
        f"media_type={media_type}."
    )

    return {"r2_object_key": r2_object_key, "media_type": media_type}


def _download_from_gcs(service_account_json: str, bucket: str, object_key: str) -> Optional[tuple[bytes, str | None]]:
    """Downloads one object's bytes + Content-Type from GCS, against
    whatever bucket is named -- never a hardcoded bucket. Returns None
    (not an exception) for a 404; any other non-2xx raises, since that's
    an unexpected infrastructure condition the caller should see."""
    from google.cloud import storage as gcs_storage
    from google.oauth2 import service_account
    import json as _json

    info = _json.loads(service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        info, scopes=[_GCS_DOWNLOAD_SCOPE]
    )
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
    """Uploads bytes to R2 at object_key, using the same boto3-against-the-
    R2-S3-compatible-endpoint pattern shared/export/event_exporter.py's
    _put_r2_json already uses."""
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{r2_creds['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=r2_creds["access_key_id"],
        aws_secret_access_key=r2_creds["secret_access_key"],
        region_name="auto",
    )
    put_kwargs = {
        "Bucket": r2_creds["bucket"],
        "Key": object_key,
        "Body": content_bytes,
    }
    if content_type:
        put_kwargs["ContentType"] = content_type

    client.put_object(**put_kwargs)


def _build_index_payload(sub: dict, r2_object_key: str, media_type: str) -> dict:
    """Builds one row for notify_worker_gallery_index_batch, matching the
    exact shape the Worker's indexBatch handler expects. Mirrors
    gallery_promotion.py::_build_index_row but operates on a plain dict
    (from the raw SQL query above) rather than a loaded Submission doc,
    since this sweep never loads the full doc for each row -- it's all
    done off the lighter raw-SQL row to keep the loop cheap."""
    student = frappe.db.get_value(
        "Student", sub["student_id"],
        ["name1", "grade", "school_id", "state_id", "district_id"], as_dict=True,
    ) or {}

    state_name = frappe.db.get_value("State", student.get("state_id"), "state_name") if student.get("state_id") else None
    district_name = frappe.db.get_value("District", student.get("district_id"), "district_name") if student.get("district_id") else None
    school_name = frappe.db.get_value("School", student.get("school_id"), "name1") if student.get("school_id") else None

    return {
        "academic_year": (sub.get("completed_at") or sub.get("created_at") or frappe.utils.now_datetime()).year,
        "assignment_id": sub.get("assign_id") or sub.get("assignment_id_link"),
        "student_id": sub["student_id"],
        "submission_id": sub["name"],
        "first_name": student.get("name1"),
        "state": (state_name or "").lower() or None,
        "district": (district_name or "").lower() or None,
        "school": school_name,
        "grade": int(student["grade"]) if student.get("grade") else None,
        "media_type": media_type,
        "object_key": r2_object_key,
        "score": sub.get("grade"),
        "promoted_at": int(time.time()),
    }


def run_sweep() -> dict:
    """The main nightly gallery-promotion sweep. Returns a summary dict:
    attempted, r2_promoted, r2_failed, d1_chunks_total, d1_chunks_failed,
    remaining_backlog_estimate, hit_lookback_ceiling."""
    since_epoch, hit_ceiling = _resolve_sweep_window()
    batch_size = get_r2_sweep_batch_size()
    chunk_size = get_gallery_index_chunk_size()

    eligible = _fetch_eligible_submissions(since_epoch, batch_size)
    known_ids = set(fetch_worker_known_submission_ids(since_epoch))

    pending = [s for s in eligible if s["name"] not in known_ids]

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
            frappe.logger().warning(
                f"run_sweep: R2 promotion failed for submission_id={sub['name']}",
                exc_info=True,
            )
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
            frappe.logger().warning(
                f"run_sweep: D1 index chunk {d1_chunks_total} failed ({len(chunk)} rows)",
                exc_info=True,
            )
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