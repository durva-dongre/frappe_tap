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
from shared.storage.gallery_r2_promotion import promote_submission_media_to_r2
from shared.submission.status import is_reward_eligible

_PROGRAM_ENROLLMENT_TABLE = "tabProgramEnrollment"


def handle_review_result(submission_doc) -> dict:
    """The one audited path that grants points/gems for a graded submission,
    and (new) promotes a reward-eligible submission's media to R2 so it can
    be served publicly from the gallery.

    Delegates "is this result rewardable" to shared.submission.status.is_reward_eligible
    so there is exactly one place that gate is defined.

    This function must be called exactly once per submission whose grading
    just came back -- see tap_app/api/review_webhook.py (external webhook
    entrypoint) and feedback_handler/feedback_consumer.py::process_message
    (RabbitMQ consumer entrypoint -- now called for EVERY source, tapapp
    included, not just via the separate webhook), both of which call this
    after persisting the submission's own graded fields. The
    feedback_ready_processed_at guard below (_already_rewarded) makes a
    second call for the same submission safe regardless of which entrypoint
    gets there first.

    R2 promotion (new): when the result is reward-eligible ("Success -
    Original" -- see shared.submission.status), the submission's GCS media is
    copied into the gallery's R2 bucket BEFORE notify_worker_gallery_index is
    called, so the gallery row's object_key sent to the Worker is the R2 key,
    not the GCS one. A promotion failure (R2 misconfigured, GCS object
    missing, etc.) never blocks the points/gems award -- the student's reward
    does not depend on gallery visibility succeeding. If R2 promotion fails
    or the submission has no media, the Worker is not notified at all (an
    empty D1 gallery_items row with no real media would be worse than no row).
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

    program_enrollment_name = submission_doc.program_enrollment
    if not program_enrollment_name and row:
        program_enrollment_name = row.get("parent")

    if row:
        recompute_unit_status_by_name(row["name"])

    is_rewardable = status == "Completed" and is_reward_eligible(result_status)

    if is_rewardable and program_enrollment_name:
        already = _already_rewarded(submission_id)
        if not already:
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
                _PROGRAM_ENROLLMENT_TABLE,
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
                    notify_worker_gallery_index(submission_doc, row, r2_object_key=r2_result["r2_object_key"],
                                                 media_type=r2_result["media_type"])
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