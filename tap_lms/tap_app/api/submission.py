from __future__ import annotations

import frappe

from tap_lms.tap_app.api import tap_app_method
from shared.submission.lifecycle import check_attempt_cap as _check_attempt_cap
from shared.submission.lifecycle import submit_artwork as _submit_artwork
from shared.progress.unit_progress import (
    attempt_info_for_submission,
    find_unit_progress_row_for_submission,
)
from shared.errors import NotFound


@tap_app_method
def check_attempt_cap(student_id: str, assignment_id: str, context: str = "program"):
    return _check_attempt_cap(student_id, assignment_id, context)


@tap_app_method
def submit_artwork(
    student_id: str,
    assignment_id: str,
    object_key: str,
    submission_id: str,
    attempt,
    generation,
    md5,
    context: str = "program",
    submission: str | None = None,
    idempotency_key: str | None = None,
    source: str | None = None,
):
    """Worker route: POST /submission/submit_artwork -> FRAPPE_METHODS.submitArtwork.

    FIX (mapRequest.ts): the Worker previously pointed this route at
    tap_lms.imgana.submission.submit_artwork -- the legacy WhatsApp/Glific
    channel's own submission pipeline, which has an entirely different
    signature (assignment_id, student_id, submission, source="whatsapp"),
    no object_key/attempt/generation/md5/context parameters at all, no
    attempt-cap enforcement, no Unit Progress writes, and no reward
    computation. Every TapApp upload was silently hitting the wrong backend.
    mapRequest.ts's FRAPPE_METHODS.submitArtwork now points at THIS function.

    This wrapper is the correct target: it accepts exactly the kwargs the
    Worker's submissionHandlers.ts::submitArtwork actually sends (note
    "submission" here is the signed GCS URL the Worker already confirmed
    exists, sized, and content-typed -- it maps onto lifecycle.submit_artwork's
    `gcs_url` parameter) and delegates to shared.submission.lifecycle.submit_artwork,
    which is the implementation actually written to this exact contract
    (attempt-cap + first-attempt-bonus + Unit Progress write, all scoped by
    context).

    idempotency_key is accepted and ignored: the Worker already wraps this
    whole call in its own Cache-API-backed idempotency layer
    (cache/idempotency.ts::withIdempotency) keyed by
    (route, student_id, idempotency_key), so Frappe never needs to dedupe
    this call itself. It's accepted here only so an unexpected-kwarg error
    doesn't fire if the Worker's request body still includes it.

    FIX: `source` is likewise accepted and ignored. submissionHandlers.ts's
    submitArtwork always sends "source": "tapapp" in the request body
    (carried over from the legacy pipeline's own `source` field) but this
    function previously had no matching parameter. Since Frappe's
    @frappe.whitelist() dispatch calls the target function with every body
    key as a keyword argument, that unmatched key raised
    TypeError: submit_artwork() got an unexpected keyword argument 'source'
    on every single call -- tap_app_method's catch-all then turned that into
    a clean-looking but completely wrong {"error_code": "server_error"}
    response, so every TapApp artwork submission was failing before it ever
    reached shared.submission.lifecycle.submit_artwork. Declaring the
    parameter (and not using it, since source is implicitly always "tapapp"
    on this route -- lifecycle.submit_artwork never asks for it and
    Submission.source already defaults appropriately for this channel)
    fixes that without changing the lifecycle contract itself.
    """
    return _submit_artwork(
        student_id=student_id,
        assignment_id=assignment_id,
        object_key=object_key,
        submission_id=submission_id,
        attempt=attempt,
        generation=generation,
        md5=md5,
        context=context,
        gcs_url=submission,
    )


def _resolve_submission_context(student_id: str, submission_name: str) -> str | None:
    """FIX: previously resolved via get_active_program_enrollment(student_id)
    and searched only that doc's unit_progress table -- which misses any
    submission that belongs to a PAST/inactive enrollment (e.g. the student
    renewed/changed enrollment since making this submission). That caused a
    context-filtered submission.get lookup to incorrectly 404 on perfectly
    valid old submissions, because the active enrollment's child table
    simply never contained that row.

    find_unit_progress_row_for_submission queries the Unit Progress child
    table directly by submission name, with no dependency on which
    enrollment currently owns it -- this is the same direct-lookup pattern
    shared/jobs/event_maintenance.py already uses correctly."""
    row = find_unit_progress_row_for_submission(submission_name)
    return row["unit_type"] if row else None


def _submission_wire_shape(sub, attempt_number: int, attempts_remaining: int) -> dict:
    # Frappe forwards the submission's own stored URLs directly, under
    # "view_url" and "overall_feedback_audio_url" -- the Worker signs/shares
    # these on to the frontend from the URL itself (see
    # worker/src/storage/resign.ts::signSubmission), so Frappe does not need
    # to know or send the raw object key.
    return {
        "name": sub.name,
        "assignment_id_link": sub.assignment_id_link,
        "status": sub.status,
        "result_status": sub.result_status,
        "view_url": sub.submission_url,
        "score": sub.grade,
        "overall_feedback_translated": sub.overall_feedback_translated,
        "overall_feedback_audio_url": sub.audio_feedback_url,
        "attempt_number": attempt_number,
        "attempts_remaining": attempts_remaining,
        "created_at": sub.created_at.isoformat() if getattr(sub, "created_at", None) else None,
        "updated_at": int(sub.created_at.timestamp()) if getattr(sub, "created_at", None) else 0,
    }


@tap_app_method
def list_submissions(student_id: str):
    rows = frappe.get_all(
        "Submission",
        filters={"student_id": student_id},
        fields=["name", "assignment_id_link", "status", "result_status",
                "submission_url", "grade", "overall_feedback_translated",
                "audio_feedback_url", "created_at"],
        order_by="created_at desc",
    )
    out = []
    for r in rows:
        # FIX: attempt_info_for_submission is the single correct, globally-
        # scoped implementation (shared/progress/unit_progress.py) -- it no
        # longer matters whether r.name belongs to the student's currently
        # active enrollment or an older one.
        attempt_number, attempts_remaining = attempt_info_for_submission(r.name)
        out.append(_submission_wire_shape(r, attempt_number, attempts_remaining))
    return {"submissions": out, "count": len(out), "total_count": len(out), "has_more": False}


@tap_app_method
def get_submission(student_id: str, submission_id: str, context: str | None = None):
    try:
        sub = frappe.get_doc("Submission", submission_id)
    except frappe.DoesNotExistError:
        raise NotFound()
    if sub.student_id != student_id:
        raise NotFound()
    if context:
        actual_context = _resolve_submission_context(student_id, submission_id)
        if actual_context != context:
            raise NotFound()
    attempt_number, attempts_remaining = attempt_info_for_submission(submission_id)
    return _submission_wire_shape(sub, attempt_number, attempts_remaining)