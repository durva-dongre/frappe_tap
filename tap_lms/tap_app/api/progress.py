"""
tap_lms/tap_app/api/progress.py

Worker-facing wrappers for the three progress-reporting activity routes
(submit_video_watched, submit_quiz) and the two sync routes (progress_sync,
last_submission).

`points_tier` is intentionally never returned by this file: the Worker
computes it from points_total against its own threshold table.

For context == "event", shared.progress.activities may resolve and mutate
a ProgramEnrollment doc other than the caller's currently-active one (the
doc that actually owns the student's existing event Unit Progress row).
_save_affected_docs saves whichever doc(s) were actually mutated: the
active `pe` always (for last_activity_at bookkeeping on the student's main
record), plus the "owning" doc the activity function returns when it
differs from `pe` (for points/gems and the Unit Progress row itself). It
also finalizes the event-enrollment unit_progress pointer after save.

WIRE-FIELD / OWNING-DOC CONSISTENCY: points_total and updated_at in the
wire response must both come from whichever doc actually received the
write for this call -- `result["_owning_doc"]`, not unconditionally the
caller's active `pe`. shared.progress.activities already returns
points_total computed off owning_doc; _resolve_updated_at below mirrors
that by taking the same owning_doc explicitly, instead of always reading
pe.last_activity_at. For program context owning_doc and pe are the same
object, so nothing changes there; for event context on a non-active
enrollment, this is what keeps updated_at in sync with the enrollment that
was actually touched.

Completion fields: shared.progress.activities' submit_video_watched/
submit_quiz optionally add unit_completed / course_completed /
next_learning_unit_id to their result dicts.
_add_completion_fields_if_present below copies those same keys into this
file's own wire response, unchanged, only when actually present.

COMPLETED-COURSE WRITE GUARD: a program-context write against an
already-completed ProgramEnrollment is rejected explicitly here, mirroring
the identical guard in shared.submission.lifecycle.check_attempt_cap /
submit_artwork. Deliberately scoped to context == "program" only -- event
activity must remain available even when the student's unrelated program
track on this same PE has separately completed.
"""

from __future__ import annotations

import frappe

from tap_lms.tap_app.api import tap_app_method
from shared.enrollment.active_batch import get_active_program_enrollment
from shared.errors import InvalidInput
from shared.progress.activities import (
    submit_video_watched as _submit_video_watched,
    submit_quiz as _submit_quiz,
    _finalize_event_enrollment_pointer,
)
from shared.profile.sync import get_sync_payload, get_last_submission_payload


def _require_course_not_completed_for_program_write(pe, context: str) -> None:
    """Rejects a program-context write against an already-completed
    ProgramEnrollment. A no-op for context == "event" -- event activity
    must remain available regardless of the enrollment's own program-track
    completion status."""
    if context == "program" and pe.status == "completed":
        raise InvalidInput(
            "course already completed; no further program activity is accepted",
            error_code="course_completed",
        )


def _save_affected_docs(pe, result: dict) -> None:
    """Saves whichever ProgramEnrollment doc(s) an activity call actually
    mutated. `pe` (the active enrollment) is always saved, since
    last_activity_at bookkeeping on the student's main record happens on
    it. If the activity resolved a *different* owning doc (event-context
    write anchored to a past enrollment's existing Unit Progress row),
    that doc is saved too, and the event enrollment's unit_progress
    pointer is finalized now that the row has a real name. The owning doc
    is popped off `result` here rather than earlier, so callers that need
    it for wire-field derivation (_resolve_updated_at below) must capture
    it from the return value of this function."""
    owning_doc = result.pop("_owning_doc", None)
    row = result.pop("_row", None)

    pe.save(ignore_permissions=True)

    if owning_doc is not None and owning_doc is not pe:
        owning_doc.save(ignore_permissions=True)

    if row is not None:
        _finalize_event_enrollment_pointer(row)

    return owning_doc


def _resolve_updated_at(doc) -> int:
    """The one place `updated_at` is computed for submit_video_watched /
    submit_quiz's wire response. Takes the doc that actually owns the
    write for this call (owning_doc, as returned by _save_affected_docs)
    -- never unconditionally the caller's active `pe` -- so event-context
    activity on a non-active enrollment reports that enrollment's own
    last_activity_at, matching the points_total this same call already
    reports off the identical doc.

    doc.last_activity_at can legitimately still be None -- e.g. a "repeat"
    call (video already watched, so award_points/bump_activity never ran)
    on an enrollment that has never otherwise had activity recorded. Falls
    back to the current server time in that case rather than crashing on
    NoneType.timestamp()."""
    if doc.last_activity_at:
        return int(doc.last_activity_at.timestamp())
    return int(frappe.utils.now_datetime().timestamp())


def _add_completion_fields_if_present(wire_response: dict, result: dict) -> None:
    """Copies unit_completed/course_completed/next_learning_unit_id from
    result into wire_response, unchanged, only for whichever of these keys
    are actually present on result."""
    for key in ("unit_completed", "course_completed", "next_learning_unit_id"):
        if key in result:
            wire_response[key] = result[key]


@tap_app_method
def submit_video_watched(student_id: str, unit_id: str, video_id: str, watched, context: str = "program"):
    watched = bool(watched)
    pe = get_active_program_enrollment(student_id)
    _require_course_not_completed_for_program_write(pe, context)
    result = _submit_video_watched(pe, unit_id, video_id, watched, context)
    owning_doc = _save_affected_docs(pe, result)
    response = {
        "points_awarded": result["points_awarded"],
        "points_total": result["points_total"],
        "context": result["context"],
        "repeat": result["repeat"],
        "video_id": result["video_id"],
        "updated_at": _resolve_updated_at(owning_doc if owning_doc is not None else pe),
    }
    _add_completion_fields_if_present(response, result)
    return response


@tap_app_method
def submit_quiz(student_id: str, unit_id: str, quiz_id: str, answers, context: str = "program"):
    pe = get_active_program_enrollment(student_id)
    _require_course_not_completed_for_program_write(pe, context)
    result = _submit_quiz(pe, unit_id, quiz_id, answers, context)
    owning_doc = _save_affected_docs(pe, result)
    response = {
        "quiz_id": result["quiz_id"],
        "correct_count": result["correct_count"],
        "total_count": result["total_count"],
        "points_awarded": result["points_awarded"],
        "points_total": result["points_total"],
        "context": result["context"],
        "repeat": result["repeat"],
        "updated_at": _resolve_updated_at(owning_doc if owning_doc is not None else pe),
    }
    _add_completion_fields_if_present(response, result)
    return response


@tap_app_method
def progress_sync(student_id: str, last_updated: int):
    return get_sync_payload(student_id, last_updated)


@tap_app_method
def last_submission(student_id: str, last_updated: int):
    return get_last_submission_payload(student_id, last_updated)