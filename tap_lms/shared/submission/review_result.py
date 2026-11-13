from __future__ import annotations

import frappe

from shared.progress.rewards import (
    award_points_by_name,
    award_gems_by_name,
    points_for_submission_review_valid,
    gems_for_submission_review_valid,
)
from shared.progress.unit_progress import (
    find_unit_progress_row_for_submission,
    recompute_unit_status_by_name,
)
from shared.storage.gallery_promotion import notify_worker_gallery_index
from shared.submission.status import is_reward_eligible, is_submission_complete

try:
    from shared.storage.gallery_r2_promotion import promote_submission_media_to_r2
except ImportError:
    promote_submission_media_to_r2 = None

# _PROGRAM_ENROLLMENT_TABLE is the raw, "tab"-prefixed SQL table name, for
# use inside frappe.db.sql(f'UPDATE "{_PROGRAM_ENROLLMENT_TABLE}" ...')
# (see _mark_feedback_tobe_viewed below). _PROGRAM_ENROLLMENT_DOCTYPE is
# the bare doctype name, used wherever the frappe.db.* API (e.g.
# frappe.db.set_value) expects a doctype name rather than a table name --
# frappe.db.set_value prepends "tab" itself, so passing the already-
# prefixed table name there would produce a double-prefixed, nonexistent
# relation. Keeping both constants, each used only where its own naming
# convention applies, is what keeps every call site in this module
# pointed at the correct relation.
_PROGRAM_ENROLLMENT_TABLE = "tabProgramEnrollment"
_PROGRAM_ENROLLMENT_DOCTYPE = "ProgramEnrollment"


def handle_review_result(submission_doc) -> dict:
    """The one audited path that grants points/gems for a graded submission,
    and (when available) promotes a submission's media to R2 so it can be
    served publicly from the gallery.

    The ProgramEnrollment this function awards points/gems/last_activity_at
    against is resolved from the Unit Progress row's own, live `parent`
    field (row["parent"]) whenever a row resolves at all, rather than from
    submission_doc.program_enrollment. A Unit Progress row is immutably
    tied to whichever ProgramEnrollment it was created under, which is not
    guaranteed to be the enrollment stamped onto
    submission_doc.program_enrollment at submission-creation time -- that
    stored field can go stale if the student's active enrollment has since
    rotated (a new course-level enrollment, etc.), especially for an
    event-context submission. row["parent"] is a live, current read of
    whichever ProgramEnrollment actually owns the row right now, so
    awarding against it is what keeps the reward landing on the enrollment
    that actually owns this submission's progress; submission_doc.
    program_enrollment is used only as a last-resort fallback for the case
    where no Unit Progress row can be resolved at all (a data-integrity
    gap, not the common path). shared/progress/activities.py's
    _resolve_event_unit_progress_row applies the same reasoning on the
    write side.

    Completion and reward eligibility are two different gates, defined in
    shared.submission.status: "Success - Flagged" counts as a completed,
    scored submission for unit/track completion purposes
    (is_submission_complete), even though it never earns the points/gems
    bonus (is_reward_eligible). Gallery promotion therefore runs for ANY
    submission that is Completed AND is_submission_complete(result_status)
    -- i.e. "Success - Original" OR "Success - Flagged" -- entirely
    independent of whether this call also grants a reward; the reward
    branch below uses is_reward_eligible on its own, narrower condition.

    The gallery branch below deliberately adds no new doctype field (no
    gallery_indexed_at or similar guard) -- it relies on two things that
    are already idempotent by construction:

      1. promote_submission_media_to_r2 copies to a deterministic R2 key
         derived from (assignment_id, student_id, submission_id, attempt) --
         re-running it for the same submission/attempt overwrites the same
         object with the same bytes, not a new one. A second copy is wasted
         work, never a correctness problem or a duplicate.
      2. notify_worker_gallery_index's payload lands in D1 via
         upsertGalleryItems's `ON CONFLICT(submission_id) DO UPDATE` (see
         worker/src/db/gallery.ts) -- a second notify for the same
         submission_id updates the existing row in place, it never creates a
         duplicate.

    A submission that gets touched by handle_review_result more than once
    after already being gallery-eligible (e.g. both the webhook and the
    RabbitMQ consumer fire for the same grading event) will re-copy to R2
    and re-notify the Worker -- extra network/R2 calls, never a correctness
    issue. If that redundant work ever becomes a real cost concern, add a
    guard field deliberately, with a migration, at that point -- this
    function does not smuggle one in as a side effect of a narrower fix.

    The reward branch (points/gems) uses its own, existing guard
    (feedback_ready_processed_at / _already_rewarded), a real doctype field,
    unchanged by anything above.

    This function must be called exactly once per submission whose grading
    just came back -- see tap_app/api/review_webhook.py (external webhook
    entrypoint) and feedback_handler/feedback_consumer.py::process_message
    (RabbitMQ consumer entrypoint), both of which call this after persisting
    the submission's own graded fields. Calling it more than once is safe:
    the reward branch cannot double-grant (feedback_ready_processed_at
    guard), and the gallery branch cannot corrupt state even though it has
    no guard of its own (see above).
    """
    submission_id = submission_doc.name
    result_status = submission_doc.result_status
    status = submission_doc.status

    row = find_unit_progress_row_for_submission(submission_id)
    outcome = {
        "submission_id": submission_id,
        "unit_progress_row": row["name"] if row else None,
        "rewarded": False,
        "points_awarded": 0,
        "gems_awarded": 0,
        "gallery_notified": False,
    }

    # row["parent"] is always the enrollment that actually, currently owns
    # this Unit Progress row; submission_doc.program_enrollment is used
    # only when no row resolves at all -- see docstring above.
    program_enrollment_name = (row.get("parent") if row else None) or submission_doc.program_enrollment

    if row:
        recompute_unit_status_by_name(row["name"])

    is_rewardable = status == "Completed" and is_reward_eligible(result_status)
    # Gallery eligibility is COMPLETION, not REWARD -- see docstring above.
    # Deliberately NOT the same boolean as is_rewardable.
    is_gallery_eligible = status == "Completed" and is_submission_complete(result_status)

    # ── Reward branch (points/gems) ──────────────────────────────────────
    if is_rewardable and program_enrollment_name:
        if not _already_rewarded(submission_id):
            points = points_for_submission_review_valid()
            gems = gems_for_submission_review_valid()

            new_points_total = award_points_by_name(program_enrollment_name, points, bump_activity=False)
            new_gems_total = award_gems_by_name(program_enrollment_name, gems)

            # last_activity_at must move forward too, or /progress/sync's
            # "current_epoch <= last_updated_epoch" short-circuit never sees
            # this as a change -- award_points_by_name only bumps it when
            # bump_activity=True, which is intentionally False here (this is
            # a review-outcome award, not a new activity the weekly-activity
            # counter should count). Bump it directly, separately, so sync
            # still surfaces the new points/gems/gallery state.
            frappe.db.set_value(
                _PROGRAM_ENROLLMENT_DOCTYPE,
                program_enrollment_name,
                "last_activity_at",
                frappe.utils.now_datetime(),
                update_modified=False,
            )

            _mark_rewarded(submission_id)

            outcome["rewarded"] = True
            outcome["points_awarded"] = points
            outcome["gems_awarded"] = gems
            outcome["points_total"] = new_points_total
            outcome["gems_total"] = new_gems_total

    # ── Gallery branch (R2 promotion + D1 index) ─────────────────────────
    # Runs independently of the reward branch above, and has NO "already
    # done" guard of its own (no new doctype field) -- see docstring for why
    # that's safe: both promote_submission_media_to_r2 and
    # notify_worker_gallery_index are idempotent by construction. A
    # "Success - Flagged" submission reaches here (is_gallery_eligible True,
    # is_rewardable False) and still gets promoted/indexed.
    if is_gallery_eligible and program_enrollment_name:
        if promote_submission_media_to_r2 is None:
            frappe.logger().info(
                f"handle_review_result: skipping gallery index for {submission_id} "
                "-- gallery_r2_promotion is not available in this install"
            )
        else:
            try:
                attempt_number = (row or {}).get("submission_attempts") or 1
                r2_result = promote_submission_media_to_r2(
                    gcs_submission_url=submission_doc.submission_url,
                    assignment_id=submission_doc.assign_id or submission_doc.assignment_id_link,
                    student_id=submission_doc.student_id,
                    submission_id=submission_id,
                    attempt=attempt_number,
                )
                if r2_result:
                    notify_worker_gallery_index(
                        submission_doc, row,
                        r2_object_key=r2_result["r2_object_key"],
                        media_type=r2_result["media_type"],
                    )
                    outcome["gallery_notified"] = True
                else:
                    frappe.logger().info(
                        f"handle_review_result: skipping gallery index for {submission_id} "
                        "-- R2 promotion returned no result (no media, or R2/GCS unavailable)"
                    )
            except Exception:
                frappe.logger().warning(
                    f"handle_review_result: gallery index notify failed for {submission_id}",
                    exc_info=True,
                )

    if program_enrollment_name:
        _mark_feedback_tobe_viewed(program_enrollment_name)

    return outcome


def _already_rewarded(submission_id: str) -> bool:
    return bool(frappe.db.get_value("Submission", submission_id, "feedback_ready_processed_at"))


def _mark_rewarded(submission_id: str) -> None:
    frappe.db.sql(
        """
        UPDATE "tabSubmission"
        SET feedback_ready_processed_at = NOW()
        WHERE name = %s AND feedback_ready_processed_at IS NULL
        """,
        (submission_id,),
    )


def _mark_feedback_tobe_viewed(program_enrollment_name: str) -> None:
    frappe.db.sql(
        f"""
        UPDATE "{_PROGRAM_ENROLLMENT_TABLE}"
        SET stage = 'feedback_tobe_viewed', modified = NOW()
        WHERE name = %s
        """,
        (program_enrollment_name,),
    )