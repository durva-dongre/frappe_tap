from __future__ import annotations

import re
import time

import frappe
import requests

from shared.config.secrets_cache import (
    get_worker_internal_api_url,
    get_worker_internal_secret,
    get_worker_internal_api_timeout_seconds,
)
from shared.submission.object_naming import resolve_wire_submission_id

# Must match the Worker's FIELD_PATTERNS.submission_id exactly
# (worker/src/storage/keys.ts): /^[a-z2-7]{6,16}$/ -- lowercase base32, the
# alphabet mintSubmissionId actually generates. Frappe's own document names
# (e.g. "SUB-0503", or an autoname hash) do NOT match this shape.
_WORKER_SUBMISSION_ID_PATTERN = re.compile(r"^[a-z2-7]{6,16}$")

# Server-side page size cap on each /internal/gallery/known_ids call --
# mirrors the hard cap the Worker enforces on its own side regardless of
# what's requested, so a single page request can never return an unbounded
# D1 result or HTTP payload.
_KNOWN_IDS_PAGE_LIMIT = 500


def notify_worker_gallery_index(submission_doc, unit_progress_row: dict | None,
                                 r2_object_key: str, media_type: str) -> None:
    """Tells the Worker to write ONE gallery_items row in D1. Dormant in
    the current pipeline -- the nightly sweep (shared/jobs/
    gallery_promotion_sweep.py) calls notify_worker_gallery_index_batch
    instead, since it always has a list of rows to push, not a single one.
    Kept here, unused but not deleted, in case a future single-row call
    site needs it (same "kept but currently dormant" treatment as
    shared/submission/rejection.py gets elsewhere in this codebase).

    r2_object_key is a required argument, not optional, because the
    Worker's gallery read path signs object_key against R2
    (r2SignGetDirect), not GCS -- a GCS key here would silently produce an
    unusable signed URL for every gallery viewer. media_type likewise must
    come from the R2 promotion step (derived from the real copied file's
    extension), not from submission_doc.submission_type, since
    Submission.submission_type can be "text"/"emoji"/"audio" for
    non-media submissions that never reach this function anyway, and
    "image"/"video" is all the gallery's media_type column accepts.

    submission_id is recovered via
    shared.submission.object_naming.resolve_wire_submission_id -- there is
    no `worker_submission_id` column on the Submission doctype. The id is
    validated against the exact shape the Worker's
    internalHandlers.ts::validateRow requires before the request is sent,
    so a malformed id fails fast locally instead of round-tripping to the
    Worker to discover the same thing.

    HTTP timeout: every call in this module uses
    get_worker_internal_api_timeout_seconds() rather than a hardcoded
    value, so an operator can tune it without a deploy.
    """
    url = get_worker_internal_api_url()
    secret = get_worker_internal_secret()
    if not url or not secret:
        frappe.logger().warning(
            f"notify_worker_gallery_index: worker internal API not configured, "
            f"skipping for {submission_doc.name}"
        )
        return

    submission_id = resolve_wire_submission_id(submission_doc)

    if not _WORKER_SUBMISSION_ID_PATTERN.match(submission_id or ""):
        frappe.logger().error(
            f"notify_worker_gallery_index: submission_id={submission_id!r} for "
            f"Submission {submission_doc.name} does not match the Worker's "
            f"required shape (^[a-z2-7]{{6,16}}$). Skipping gallery index for "
            f"this submission; it will not appear in the gallery until its "
            f"submission_url matches the expected tapapp object-key shape."
        )
        return

    student = frappe.db.get_value(
        "Student",
        submission_doc.student_id,
        ["name1", "grade", "school_id", "state_id", "district_id"],
        as_dict=True,
    ) or {}

    row = _build_index_row(submission_doc, student, submission_id, r2_object_key, media_type)

    frappe.logger().info(
        f"notify_worker_gallery_index: submission_id={submission_id}, "
        f"r2_object_key={r2_object_key}, media_type={media_type}"
    )

    resp = requests.post(
        f"{url.rstrip('/')}/internal/gallery/index",
        json={"rows": [row]},
        headers={"X-Internal-Secret": secret},
        timeout=get_worker_internal_api_timeout_seconds(),
    )
    resp.raise_for_status()


def _build_index_row(submission_doc, student: dict, submission_id: str, r2_object_key: str, media_type: str) -> dict:
    state_name = frappe.db.get_value("State", student.get("state_id"), "state_name") if student.get("state_id") else None
    district_name = frappe.db.get_value("District", student.get("district_id"), "district_name") if student.get("district_id") else None
    school_name = frappe.db.get_value("School", student.get("school_id"), "name1") if student.get("school_id") else None

    return {
        "academic_year": (submission_doc.created_at or frappe.utils.now_datetime()).year,
        "assignment_id": submission_doc.assign_id or submission_doc.assignment_id_link,
        "student_id": submission_doc.student_id,
        "submission_id": submission_id,
        "first_name": student.get("name1"),
        # A missing value here is valid -- the Worker's
        # internalHandlers.ts::validateRow treats it as an empty string,
        # which falls through gallery's own fallback cascade rather than
        # hard-rejecting the whole batch.
        "state": (state_name or "").lower() or None,
        "district": (district_name or "").lower() or None,
        "school": school_name,
        "grade": int(student["grade"]) if student.get("grade") else None,
        "media_type": media_type,
        "object_key": r2_object_key,
        "score": submission_doc.grade,
        "promoted_at": int(time.time()),
    }


def notify_worker_gallery_index_batch(rows: list[dict]) -> None:
    """Pushes a whole chunk of already-built index-row dicts in one
    request to /internal/gallery/index. Each row dict must already have
    the exact shape _build_index_row produces (academic_year,
    assignment_id, student_id, submission_id, first_name, state, district,
    school, grade, media_type, object_key, score, promoted_at) -- the
    nightly sweep (shared/jobs/gallery_promotion_sweep.py) is the one
    caller, building these from its own per-submission R2-promotion
    results.

    No-op (returns immediately) for an empty list -- the Worker's own
    indexBatch handler rejects an empty rows array, so there is nothing
    useful to send and no reason to round-trip for it. Raises on any
    non-2xx response, same as the single-row function -- the sweep job
    catches this per-chunk and continues to the next chunk rather than
    aborting the whole run.
    """
    if not rows:
        return

    url = get_worker_internal_api_url()
    secret = get_worker_internal_secret()
    if not url or not secret:
        frappe.logger().warning(
            f"notify_worker_gallery_index_batch: worker internal API not configured, "
            f"skipping batch of {len(rows)} row(s)"
        )
        return

    resp = requests.post(
        f"{url.rstrip('/')}/internal/gallery/index",
        json={"rows": rows},
        headers={"X-Internal-Secret": secret},
        timeout=get_worker_internal_api_timeout_seconds(),
    )
    resp.raise_for_status()


def fetch_worker_known_submission_ids(since_epoch: int) -> list[str]:
    """Calls the Worker's /internal/gallery/known_ids route, paging
    through with cursor until a short page (or a None next_cursor) signals
    the end, and returns the full flattened list of submission_ids already
    present in D1's gallery_items table with promoted_at >= since_epoch.

    This is the "ask D1 what it already knows" half of the nightly sweep's
    pending-set computation (see shared/jobs/gallery_promotion_sweep.py):
    pending = Frappe-eligible-set minus this function's return value.
    Pagination keeps any single request/response bounded even when the
    window covers a large backlog (e.g. after several failed sweep
    nights) -- each page is capped server-side at _KNOWN_IDS_PAGE_LIMIT
    regardless of what's asked for.
    """
    url = get_worker_internal_api_url()
    secret = get_worker_internal_secret()
    if not url or not secret:
        frappe.logger().warning(
            "fetch_worker_known_submission_ids: worker internal API not configured, "
            "treating known set as empty"
        )
        return []

    timeout = get_worker_internal_api_timeout_seconds()
    all_ids: list[str] = []
    cursor = None

    while True:
        payload = {"since": since_epoch, "limit": _KNOWN_IDS_PAGE_LIMIT}
        if cursor is not None:
            payload["cursor"] = cursor

        resp = requests.post(
            f"{url.rstrip('/')}/internal/gallery/known_ids",
            json=payload,
            headers={"X-Internal-Secret": secret},
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json() or {}

        page_ids = body.get("submission_ids") or []
        all_ids.extend(page_ids)

        next_cursor = body.get("next_cursor")
        if next_cursor is None:
            break
        cursor = next_cursor

    return all_ids


def notify_worker_gallery_visibility(submission_id: str, visible: bool) -> None:
    url = get_worker_internal_api_url()
    secret = get_worker_internal_secret()
    if not url or not secret:
        return

    resp = requests.post(
        f"{url.rstrip('/')}/internal/gallery/visibility",
        json={"submission_id": submission_id, "visible": visible},
        headers={"X-Internal-Secret": secret},
        timeout=get_worker_internal_api_timeout_seconds(),
    )
    resp.raise_for_status()