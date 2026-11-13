"""
tap_lms/tap_app/api/progress.py

Worker-facing wrappers for the three progress-reporting activity routes
(submit_video_watched, submit_quiz) and the two sync routes
(progress_sync, last_submission). submit_video_watched's and submit_quiz's
responses return `context` and `repeat` directly from
shared.progress.activities' own result dicts, because the contract
(API_Reference.md §3.1/§3.2) requires both fields on every call, including
a repeat.

`points_tier` is intentionally never returned by this file, or by any
other progress/auth endpoint in this codebase: the Worker computes it from
points_total against its own threshold table (API_Reference.md §0.2/§3.1),
keyed by POINT_TIERS_VERSION. Keeping that computation on the Worker side,
not Frappe's, means the tier table can change without a Frappe deploy --
this file has nothing to do and nothing to change if that table is ever
revised.

For context == "event", shared.progress.activities may resolve and mutate
a ProgramEnrollment doc other than the caller's currently-active one (the
doc that actually owns the student's existing event Unit Progress row --
see that module's docstring for why event-track writes must stay anchored
there rather than to "whichever enrollment is active right now").
_save_affected_docs saves whichever doc(s) were actually mutated: the
active `pe` always (for last_activity_at/activity_this_week bookkeeping),
plus the "owning" doc the activity function returns when it differs from
`pe` (for points/gems and the Unit Progress row itself). It also finalizes
the event-enrollment unit_progress pointer after save, via
shared.progress.activities._finalize_event_enrollment_pointer, because a
brand-new Unit Progress child row only receives its Frappe-assigned `name`
once its parent doc is saved -- the pointer write has to happen after that
point, not before.
"""

from __future__ import annotations

from tap_lms.tap_app.api import tap_app_method
from shared.enrollment.active_batch import get_active_program_enrollment
from shared.progress.activities import (
    submit_video_watched as _submit_video_watched,
    submit_quiz as _submit_quiz,
    _finalize_event_enrollment_pointer,
)
from shared.profile.sync import get_sync_payload, get_last_submission_payload


def _save_affected_docs(pe, result: dict) -> None:
    """Saves whichever ProgramEnrollment doc(s) an activity call actually
    mutated. `pe` (the active enrollment) is always saved, since
    last_activity_at/activity_this_week bookkeeping always happens on it.
    If the activity resolved a *different* owning doc (event-context write
    anchored to a past enrollment's existing Unit Progress row), that doc
    is saved too, and the event enrollment's unit_progress pointer is
    finalized now that the row has a real name."""
    owning_doc = result.pop("_owning_doc", None)
    row = result.pop("_row", None)

    pe.save(ignore_permissions=True)

    if owning_doc is not None and owning_doc is not pe:
        owning_doc.save(ignore_permissions=True)

    if row is not None:
        _finalize_event_enrollment_pointer(row)


@tap_app_method
def submit_video_watched(student_id: str, unit_id: str, video_id: str, watched, context: str = "program"):
    watched = bool(watched)
    pe = get_active_program_enrollment(student_id)
    result = _submit_video_watched(pe, unit_id, video_id, watched, context)
    _save_affected_docs(pe, result)
    return {
        "points_awarded": result["points_awarded"],
        "points_total": result["points_total"],
        "context": result["context"],
        "repeat": result["repeat"],
        "video_id": result["video_id"],
        "updated_at": int(pe.last_activity_at.timestamp()),
    }


@tap_app_method
def submit_quiz(student_id: str, unit_id: str, quiz_id: str, answers, context: str = "program"):
    pe = get_active_program_enrollment(student_id)
    result = _submit_quiz(pe, unit_id, quiz_id, answers, context)
    _save_affected_docs(pe, result)
    return {
        "quiz_id": result["quiz_id"],
        "correct_count": result["correct_count"],
        "total_count": result["total_count"],
        "points_awarded": result["points_awarded"],
        "points_total": result["points_total"],
        "context": result["context"],
        "repeat": result["repeat"],
        "updated_at": int(pe.last_activity_at.timestamp()),
    }


@tap_app_method
def progress_sync(student_id: str, last_updated: int):
    return get_sync_payload(student_id, last_updated)


@tap_app_method
def last_submission(student_id: str, last_updated: int):
    return get_last_submission_payload(student_id, last_updated)