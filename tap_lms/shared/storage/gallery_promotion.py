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


def notify_worker_gallery_index(submission_doc, unit_progress_row: dict | None,
                                 r2_object_key: str, media_type: str) -> None:
    """Tells the Worker to write a gallery_items row in D1. r2_object_key is
    a required argument, not optional, because the Worker's gallery read
    path signs object_key against R2 (r2SignGetDirect), not GCS -- a GCS key
    here would silently produce an unusable signed URL for every gallery
    viewer, so the caller must always pass the key just written into the R2
    bucket by shared.storage.gallery_r2_promotion.promote_submission_media_to_r2.
    media_type likewise must come from that same R2 promotion step (derived
    from the real copied file's extension), not from
    submission_doc.submission_type, since Submission.submission_type can be
    "text"/"emoji"/"audio" for non-media submissions that never reach this
    function anyway, and "image"/"video" is all the gallery's media_type
    column accepts.

    submission_id is recovered via
    shared.submission.object_naming.resolve_wire_submission_id -- there is
    no `worker_submission_id` column on the Submission doctype, and none
    will be added. resolve_wire_submission_id instead parses the Worker-
    minted id straight out of submission_doc.submission_url when it matches
    the expected tapapp object-key shape, falling back to the Frappe
    autoname otherwise. This function is only ever called from
    shared.submission.review_result.handle_review_result's gallery branch,
    which runs strictly after grading has completed -- at that point
    imgana's async process_submission_async has always already run and
    populated submission_url, so submission_id resolved here is reliably
    the Worker-shaped id for every genuinely tapapp-sourced submission.

    The id is still validated against the exact shape the Worker's
    internalHandlers.ts::validateRow requires
    (_WORKER_SUBMISSION_ID_PATTERN) before the request is sent: a
    submission whose submission_url never matched the expected tapapp
    shape (a non-tapapp/legacy/imgana-pipeline submission, or any other
    row resolve_wire_submission_id had to fall back to the Frappe autoname
    for) would otherwise be sent under an id the Worker's own
    FIELD_PATTERNS.submission_id regex rejects regardless -- validating
    here first fails fast, locally, with a log line that names the real
    problem, instead of round-tripping to the Worker to discover the same
    thing.

    HTTP timeout: both calls in this module use
    get_worker_internal_api_timeout_seconds() (Shared Settings.
    worker_internal_api_timeout_seconds, Int, default 15 seconds) rather
    than a hardcoded value, so an operator can tune it without a deploy if
    the Worker's own response-time characteristics change.
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
            f"required shape (^[a-z2-7]{{6,16}}$). resolve_wire_submission_id "
            f"could not recover a Worker-shaped id from this submission's "
            f"submission_url -- refusing to send a payload the Worker's "
            f"internalHandlers.ts::validateRow will reject anyway. Skipping "
            f"gallery index for this submission; it will not appear in the "
            f"gallery until its submission_url matches the expected tapapp "
            f"object-key shape."
        )
        return

    student = frappe.db.get_value(
        "Student",
        submission_doc.student_id,
        ["name1", "grade", "school_id", "state_id", "district_id"],
        as_dict=True,
    ) or {}

    state_name = frappe.db.get_value("State", student.get("state_id"), "state_name") if student.get("state_id") else None
    district_name = frappe.db.get_value("District", student.get("district_id"), "district_name") if student.get("district_id") else None
    school_name = frappe.db.get_value("School", student.get("school_id"), "name1") if student.get("school_id") else None

    payload = {
        "rows": [{
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
        }]
    }

    frappe.logger().info(
        f"notify_worker_gallery_index: submission_id={submission_id}, "
        f"r2_object_key={r2_object_key}, media_type={media_type}"
    )

    resp = requests.post(
        f"{url.rstrip('/')}/internal/gallery/index",
        json=payload,
        headers={"X-Internal-Secret": secret},
        timeout=get_worker_internal_api_timeout_seconds(),
    )
    resp.raise_for_status()


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