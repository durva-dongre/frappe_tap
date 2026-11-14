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
from shared.enrollment.unit_rotation import is_course_complete, next_unit_for
from shared.enrollment.enrollment import mark_course_completed
from shared.storage.gallery_promotion import notify_worker_gallery_index
from shared.submission.status import is_reward_eligible, is_submission_complete

try:
    from shared.storage.gallery_r2_promotion import promote_submission_media_to_r2
except ImportError:
    promote_submission_media_to_r2 = None

# _PROGRAM_ENROLLMENT_TABLE is the raw, "tab"-prefixed SQL table name, for
# use inside frappe.db.sql(f'UPDATE "{_PROGRAM_ENROLLMENT_TABLE}" ...')
# (see _mark_feedback_tobe_viewed and _increment_submission_this_week
# below). _PROGRAM_ENROLLMENT_DOCTYPE is the bare doctype name, used
# wherever the frappe.db.* API (e.g. frappe.db.set_value) expects a
# doctype name rather than a table name -- frappe.db.set_value prepends
# "tab" itself, so passing the already-prefixed table name there would
# produce a double-prefixed, nonexistent relation. Keeping both constants,
# each used only where its own naming convention applies, is what keeps
# every call site in this module pointed at the correct relation.
_PROGRAM_ENROLLMENT_TABLE = "tabProgramEnrollment"
_PROGRAM_ENROLLMENT_DOCTYPE = "ProgramEnrollment"


def handle_review_result(submission_doc) -> dict:
    """The one audited path that grants points/gems for a graded submission,
    bumps the weekly submission_this_week counter, detects and reports
    unit/course completion driven by a submission's own grading outcome,
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

    SUBMISSION_THIS_WEEK (new, 2026-11-14): this function is the SOLE
    increment site for ProgramEnrollment.submission_this_week, firing
    exactly once per call to handle_review_result, for EVERY result_status
    -- "Success - Original", "Success - Flagged", AND "Failed" all count
    (per explicit instruction: "increment submission this week after
    every type of review not just normal review"). This is unconditional
    on status/result_status, happening before the reward/completion
    branches below, and only when a Unit Progress row (and therefore an
    owning ProgramEnrollment) actually resolves -- there is nothing to
    increment against otherwise. The increment is scoped to program
    context only, matching the field's own doctype description; an
    event-context submission's handle_review_result call does NOT bump
    this counter (row["unit_type"] is checked for this).

    Confirmed call-site guarantee: this function is called exactly once
    per submission whose grading just came back, from both
    feedback_handler/feedback_consumer.py::process_message (which now
    routes every tapapp-sourced submission through the same
    parse/update/handle_review_result pipeline as every other source,
    unconditionally -- see that file's own comments) and
    tap_app/api/review_webhook.py. This is exactly the single hook point
    the original design required ("after submission in review it should
    switch on itself") -- no separate wiring is needed elsewhere for the
    increment to "just work" for every tapapp submission's grading
    outcome.

    UNIT/COURSE COMPLETION (new, 2026-11-14): after recompute_unit_status_by_name
    is called (as before), its new {"status": ..., "just_completed": ...}
    return shape is used to detect whether THIS grading outcome is what
    tipped the unit to "Completed". When it is, this function:
      1. Adds "unit_status": "Completed" to the returned outcome dict
         (per the explicit instruction: "if unit status gets completed
         saying unit_status completed also"), plus the same
         unit_completed/course_completed/[next_learning_unit_id] shape
         shared/progress/activities.py's own completion block uses, kept
         identical across both the quiz/video path and this submission
         path so profile/sync.py's downstream consumers (sync,
         last_submission) handle one single shape regardless of which
         activity actually completed the unit.
      2. Checks is_course_complete against the OWNING ProgramEnrollment
         (loaded by row["parent"], the same live-ownership resolution
         already used for the reward branch) and, if the whole course is
         now finished, calls mark_course_completed on it -- exactly the
         same two-step "is_course_complete then mark_course_completed"
         pattern used in activities.py, reused here rather than
         duplicated with different logic.
    This matters because submission grading is async: a student may have
    already moved on (gone paused, logged out, etc.) by the time a
    submission's review comes back and is what finally completes the
    unit/course -- this is exactly Decision A's scenario, and is why
    mark_course_completed is able to transition from paused/no_activity/
    manual, not just from active (see shared/enrollment/enrollment.py's
    ALLOWED_TRANSITIONS).

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
    issue. The submission_this_week increment above is NOT similarly
    idempotent against a double-call -- see its own section for why this
    is accepted, not guarded, per the explicit instruction that every
    review outcome counts, and per this function's own documented "called
    exactly once per graded submission" contract. If that redundant work
    (gallery re-copy, or a double-counted submission_this_week from a
    genuine double-call) ever becomes a real cost or correctness concern,
    add a guard field deliberately, with a migration, at that point -- this
    function does not smuggle one in as a side effect of a narrower fix.

    The reward branch (points/gems) uses its own, existing guard
    (feedback_ready_processed_at / _already_rewarded), a real doctype field,
    unchanged by anything above.
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

    # ── submission_this_week increment (new) ─────────────────────────────
    # Program context only, exactly once per call, for EVERY result_status
    # (Success - Original, Success - Flagged, AND Failed all count). See
    # docstring's "SUBMISSION_THIS_WEEK" section above.
    if row and row.get("unit_type") == "program" and program_enrollment_name:
        _increment_submission_this_week(program_enrollment_name)

    status_result = None
    if row:
        status_result = recompute_unit_status_by_name(row["name"])

    is_rewardable = status == "Completed" and is_reward_eligible(result_status)
    # Gallery eligibility is COMPLETION, not REWARD -- see docstring above.
    # Deliberately NOT the same boolean as is_rewardable.
    is_gallery_eligible = status == "Completed" and is_submission_complete(result_status)

    # ── Unit / course completion (new) ───────────────────────────────────
    # Fires only when THIS call's recompute_unit_status_by_name is what
    # tipped the row to "Completed" (status_result["just_completed"]).
    # Identical response shape to activities.py's own completion block:
    # unit_completed/course_completed/[next_learning_unit_id], plus
    # unit_status for this path specifically (per explicit instruction).
    if status_result and status_result["just_completed"] and program_enrollment_name:
        outcome["unit_status"] = status_result["status"]
        outcome["unit_completed"] = True
        pe_doc = frappe.get_doc(_PROGRAM_ENROLLMENT_DOCTYPE, program_enrollment_name)
        if is_course_complete(pe_doc):
            mark_course_completed(program_enrollment_name)
            outcome["course_completed"] = True
            # Decision B: no next_learning_unit_id key at all when the
            # course is complete.
        else:
            outcome["course_completed"] = False
            outcome["next_learning_unit_id"] = next_unit_for(pe_doc)

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
            # still surfaces the new points/gems/gallery/completion state.
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
    elif status_result and status_result["just_completed"] and program_enrollment_name:
        # Completion happened but this particular outcome wasn't
        # reward-eligible (e.g. "Success - Flagged", or "Failed" somehow
        # still completing a unit via some other already-valid gate) --
        # last_activity_at still needs to move forward so sync/last_submission
        # see the completion. The reward branch above already bumps it
        # when it fires; this covers the completion-without-reward case so
        # the bump isn't silently skipped.
        frappe.db.set_value(
            _PROGRAM_ENROLLMENT_DOCTYPE,
            program_enrollment_name,
            "last_activity_at",
            frappe.utils.now_datetime(),
            update_modified=False,
        )

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


def _increment_submission_this_week(program_enrollment_name: str) -> None:
    """Sole increment site for ProgramEnrollment.submission_this_week --
    see handle_review_result's own docstring for the full reasoning (once
    per graded outcome, any result_status, program context only).
    Deliberately a plain, unconditional +1 raw-SQL increment with no
    "already counted this submission" guard -- handle_review_result's own
    contract (called exactly once per submission whose grading just came
    back) is what keeps this correct; see that function's docstring for
    what happens if that contract is ever violated by a genuine double-call."""
    frappe.db.sql(
        f"""
        UPDATE "{_PROGRAM_ENROLLMENT_TABLE}"
        SET submission_this_week = COALESCE(submission_this_week, 0) + 1,
            modified = NOW()
        WHERE name = %s
        """,
        (program_enrollment_name,),
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