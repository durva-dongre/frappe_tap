from __future__ import annotations

import time

import frappe
import requests

from shared.config.secrets_cache import get_worker_internal_api_url, get_worker_internal_secret


def notify_worker_gallery_index(submission_doc, unit_progress_row: dict | None,
                                 r2_object_key: str, media_type: str) -> None:
    """Tells the Worker to write a gallery_items row in D1. r2_object_key is
    the key just written into the R2 bucket by
    shared.storage.gallery_r2_promotion.promote_submission_media_to_r2 --
    this is now a REQUIRED argument (not optional) because the Worker's
    gallery read path signs object_key against R2 (r2SignGetDirect), not
    GCS, so a GCS key here would silently produce an unusable signed URL
    for every gallery viewer. media_type likewise comes from the R2
    promotion step (derived from the real copied file's extension), not
    from submission_doc.submission_type, since the Submission doctype's
    submission_type can be "text"/"emoji"/"audio" for non-media submissions
    that never reach this function anyway, and "image"/"video" is all the
    gallery's media_type column accepts.
    """
    url = get_worker_internal_api_url()
    secret = get_worker_internal_secret()
    if not url or not secret:
        frappe.logger().warning(
            f"notify_worker_gallery_index: worker internal API not configured, "
            f"skipping for {submission_doc.name}"
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

    # submission_id sent to the gallery index is the Worker-minted id when one
    # exists (worker_submission_id, persisted by shared.submission.lifecycle's
    # TapApp path), falling back to Frappe's own autoname hash for legacy/
    # imgana-pipeline submissions (which is exactly what the R2 object key's
    # own {submission_id} segment was built from in
    # gallery_r2_promotion.promote_submission_media_to_r2 -- the two must
    # always agree, since the Worker parses the id back out of the object_key
    # on the read side).
    submission_id = getattr(submission_doc, "worker_submission_id", None) or submission_doc.name

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
        timeout=15,
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
        timeout=15,
    )
    resp.raise_for_status()