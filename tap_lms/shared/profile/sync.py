from __future__ import annotations

from shared.enrollment.active_batch import get_active_program_enrollment
from shared.progress.unit_progress import (
    resolve_current_unit_for_track,
    resolve_last_activity_type_for_track,
    attempt_info_for_submission,
)
from shared.enrollment.unit_rotation import next_unit_for
from shared.progress.rewards import points_for_submission_review_valid, gems_for_submission_review_valid
from shared.submission.status import is_reward_eligible


def _mark_feedback_viewed_if_pending(pe_doc) -> None:
    if pe_doc.stage == "feedback_tobe_viewed":
        pe_doc.stage = "feedback_viewed"
        pe_doc.save(ignore_permissions=True)


def _find_last_submission_row(student_id: str) -> dict | None:
    """Returns the student's most recently UPDATED submission, not the most
    recently CREATED one.

    `modified` is Frappe's own standard last-write timestamp, bumped on
    every `doc.save()` -- including every grading-pipeline update
    (feedback_processor.py, review_result.py's status/reward writes). A
    just-graded submission's `modified` is newer than any submission that
    hasn't been touched since it was created, regardless of which one was
    created first, so ordering by `modified desc` reliably surfaces
    whichever submission's state most recently changed -- which is exactly
    what "last_submission" is supposed to mean for a resume/sync screen.
    created_at is kept as a tiebreaker for the rare case of two rows with
    an identical modified timestamp.
    """
    import frappe
    rows = frappe.get_all(
        "Submission",
        filters={"student_id": student_id},
        fields=["name", "assignment_id_link", "status", "result_status", "submission_url", "grade",
                "overall_feedback_translated", "audio_feedback_url",
                "program_enrollment", "created_at", "modified", "feedback_ready_processed_at"],
        order_by="modified desc, created_at desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


def _grading_award_for_submission(sub: dict) -> tuple[int, int]:
    """Derives (points_awarded, gems_awarded) for THIS submission's grading
    bonus. There is no dedicated storage column for this on Submission, by
    design (no doctype change needed) -- the amount is recovered from what
    already exists:
      - shared.submission.status.is_reward_eligible(sub.result_status) tells
        us whether this particular submission's result ever qualifies for
        the grading-time bonus at all ("Success - Original" only -- a
        "Success - Flagged" result is complete but never earns this, per
        shared/submission/status.py's own completion-vs-reward distinction);
      - sub.feedback_ready_processed_at being set tells us the one-time
        award for this submission has actually been granted -- this is the
        exact same guard shared.submission.review_result.handle_review_result
        uses itself, via _already_rewarded, to avoid a double award;
      - the amount itself is always the CURRENT Shared Settings configured
        value (points_submission_review_valid / gems_submission_review_valid
        -- 10 points / 1 gem as configured today).

    Returns (0, 0) for a submission that is not reward-eligible, or is
    reward-eligible but not yet actually rewarded.

    Read ONLY by get_sync_payload / get_last_submission_payload below --
    both of which are gated by an updated_at/last_updated epoch comparison,
    so a given award is only ever surfaced to the app once. submission.list
    / submission.get do NOT call this -- see tap_app/api/submission.py's
    module docstring for why a one-time award field has no place on an
    ungated historical read.
    """
    result_status = sub.get("result_status")
    if not is_reward_eligible(result_status):
        return 0, 0
    if not sub.get("feedback_ready_processed_at"):
        return 0, 0
    return points_for_submission_review_valid(), gems_for_submission_review_valid()


def get_sync_payload(student_id: str, last_updated_epoch: int) -> dict:
    pe = get_active_program_enrollment(student_id)
    current_epoch = int(pe.last_activity_at.timestamp()) if pe.last_activity_at else 0

    if current_epoch <= (last_updated_epoch or 0):
        return {"changed": False, "updated_at": last_updated_epoch or current_epoch}

    last_submission = _find_last_submission_row(student_id)
    payload = {
        "changed": True,
        "updated_at": current_epoch,
        "points": pe.points or 0,
        "gems": pe.gems or 0,
        "current_learning_unit": resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for),
        "last_activity_type": resolve_last_activity_type_for_track(pe, "program"),
    }
    if last_submission:
        # attempt_info_for_submission (shared/progress/unit_progress.py)
        # resolves the owning Unit Progress row globally, by submission
        # name, with no dependency on "active enrollment" being the right
        # scope -- required here because last_submission may belong to an
        # enrollment other than the student's current active one.
        attempt_number, attempts_remaining = attempt_info_for_submission(last_submission.name)
        points_awarded, gems_awarded = _grading_award_for_submission(last_submission)
        # Frappe forwards the submission's own stored URLs (submission_url,
        # audio_feedback_url) directly, under "view_url" and
        # "overall_feedback_audio_url" -- the Worker is responsible for
        # signing/sharing these on to the frontend. Frappe does not need to
        # know the object-key shape to do this.
        #
        # Identifier: ONLY submission_id is returned here -- never a bare
        # `name` field. Frappe's own document name IS last_submission.name
        # under the hood (this source's submission_id and Frappe document
        # name are always the same value), but the wire key is always
        # submission_id, consistently with every other submission-shaped
        # response in this API (submit_artwork, submission.list,
        # submission.get) -- see tap_app/api/submission.py's module
        # docstring for the full rationale.
        #
        # Score: the submission's numeric mark is returned as `points`, not
        # `score` -- Submission.grade is the underlying stored field, but
        # the wire field name is `points` everywhere a submission's mark is
        # reported, matching how the rest of this API already talks about
        # points (points_total, points_awarded, points_tier).
        payload["last_submission"] = {
            "submission_id": last_submission.name,
            "assignment_id_link": last_submission.assignment_id_link,
            "status": last_submission.status,
            "result_status": last_submission.result_status,
            "view_url": last_submission.submission_url,
            "points": last_submission.grade,
            "overall_feedback_translated": last_submission.overall_feedback_translated,
            "overall_feedback_audio_url": last_submission.audio_feedback_url,
            "attempt_number": attempt_number,
            "attempts_remaining": attempts_remaining,
            # Derived, not stored -- see _grading_award_for_submission.
            # 0/0 unless this submission's grading just landed a
            # "Success - Original" result and the one-time award has
            # actually been granted. This whole payload is only sent when
            # current_epoch > last_updated_epoch (the gate above).
            "points_awarded": points_awarded,
            "gems_awarded": gems_awarded,
            "updated_at": current_epoch,
        }
        _mark_feedback_viewed_if_pending(pe)
    return payload


def get_last_submission_payload(student_id: str, last_updated_epoch: int) -> dict:
    pe = get_active_program_enrollment(student_id)
    base = {"points": pe.points or 0, "gems": pe.gems or 0}

    last_submission = _find_last_submission_row(student_id)
    if not last_submission:
        return {"has_update": False, **base}

    sub_epoch = int(last_submission.modified.timestamp()) if last_submission.modified else (
        int(last_submission.created_at.timestamp()) if last_submission.created_at else 0
    )
    if sub_epoch <= (last_updated_epoch or 0):
        return {"has_update": False, **base}

    attempt_number, attempts_remaining = attempt_info_for_submission(last_submission.name)
    points_awarded, gems_awarded = _grading_award_for_submission(last_submission)
    _mark_feedback_viewed_if_pending(pe)
    return {
        "has_update": True,
        **base,
        "last_submission": {
            "submission_id": last_submission.name,
            "assignment_id_link": last_submission.assignment_id_link,
            "status": last_submission.status,
            "result_status": last_submission.result_status,
            "view_url": last_submission.submission_url,
            "points": last_submission.grade,
            "overall_feedback_translated": last_submission.overall_feedback_translated,
            "overall_feedback_audio_url": last_submission.audio_feedback_url,
            "attempt_number": attempt_number,
            "attempts_remaining": attempts_remaining,
            "points_awarded": points_awarded,
            "gems_awarded": gems_awarded,
            "updated_at": sub_epoch,
        },
    }