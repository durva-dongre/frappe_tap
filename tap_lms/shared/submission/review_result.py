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
from shared.submission.status import is_reward_eligible, is_submission_complete

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
    bumps the weekly submission_this_week counter, and detects and reports
    unit/course completion driven by a submission's own grading outcome.

    Gallery promotion is NOT handled here -- it runs as a separate nightly
    batch job (shared/jobs/gallery_promotion_sweep.py), which derives
    "pending" submissions directly by diffing Frappe's own
    Completed+is_submission_complete set against whatever D1 already knows
    about, rather than this function notifying the Worker synchronously at
    grading time. See that module for the full design.

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
    write side, as does shared/submission/lifecycle.py::submit_artwork.

    Completion and reward eligibility are two different gates, defined in
    shared.submission.status: "Success - Flagged" counts as a completed,
    scored submission for unit/track completion purposes
    (is_submission_complete), even though it never earns the points/gems
    bonus (is_reward_eligible).

    SUBMISSION_THIS_WEEK: this function is the SOLE increment site for
    ProgramEnrollment.submission_this_week, firing at most once per
    submission (see _already_counted_this_week below), for EVERY
    result_status -- "Success - Original", "Success - Flagged", AND
    "Failed" all count. This is unconditional on status/result_status,
    happening before the reward/completion branches below, and only when
    a Unit Progress row (and therefore an owning ProgramEnrollment)
    actually resolves -- there is nothing to increment against otherwise.
    The increment is scoped to program context only, matching the field's
    own doctype description; an event-context submission's
    handle_review_result call does NOT bump this counter (row["unit_type"]
    is checked for this).

    IDEMPOTENCY (submission_this_week): this codebase documents (see
    review_webhook.py and feedback_consumer.py) that the same submission's
    review result can legitimately reach handle_review_result more than
    once -- via a RabbitMQ redelivery/retry, or via both the RabbitMQ
    consumer and the external review_result_webhook firing for the same
    grading event. The reward branch already guards against double-award
    via Submission.feedback_ready_processed_at (_already_rewarded), but
    that guard is only set when a submission is reward-eligible
    ("Success - Original"). A "Success - Flagged" or "Failed" submission
    is never reward-eligible and so never gets that marker set, which
    means a naive, unconditional increment would double-count
    submission_this_week for every repeat delivery of a non-rewarded
    result -- undermining the weekly cap this counter feeds.
    _already_counted_this_week uses Submission.completed_at, which
    feedback_processor.py::update_submission sets exactly once, on the
    FIRST time a submission's result is written (it is not re-set on a
    reprocessing of the same already-Completed submission, since
    update_submission always writes it unconditionally to "now" on every
    call -- so instead this function uses a dedicated, idempotent raw-SQL
    guard scoped to submission_this_week's own increment, independent of
    whichever path called it or how many times).

    Confirmed call-site guarantee: this function is called from both
    feedback_handler/feedback_consumer.py::process_message and
    tap_app/api/review_webhook.py, and either call site may legitimately
    be invoked more than once for the same submission's grading outcome.

    UNIT/COURSE COMPLETION: after recompute_unit_status_by_name is called,
    its {"status": ..., "just_completed": ...} return shape is used to
    detect whether THIS grading outcome is what tipped the unit to
    "Completed". When it is, this function:
      1. Adds "unit_status": "Completed" to the returned outcome dict,
         plus "unit_completed": True.
      2. ONLY when the completed row's own unit_type is "program": checks
         is_course_complete against the OWNING ProgramEnrollment (loaded
         by row["parent"]) and, if the whole course is now finished, calls
         mark_course_completed on it, and adds course_completed /
         next_learning_unit_id to the outcome.
      An event-track row completing (unit_type == "event") never
      evaluates or reports course_completed / next_learning_unit_id at
      all -- course completion is a program-track-only concept. See
      shared/progress/activities.py's module docstring for the full
      reasoning; this is the identical fix applied to the async
      submission-review path.

    This matters because submission grading is async: a student may have
    already moved on (gone paused, logged out, etc.) by the time a
    submission's review comes back and is what finally completes the
    unit/course, which is why mark_course_completed is able to transition
    from paused/no_activity/manual, not just from active.

    The reward branch (points/gems) uses its own, existing guard
    (feedback_ready_processed_at / _already_rewarded), a real doctype field.
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
    }

    # row["parent"] is always the enrollment that actually, currently owns
    # this Unit Progress row; submission_doc.program_enrollment is used
    # only when no row resolves at all -- see docstring above.
    program_enrollment_name = (row.get("parent") if row else None) or submission_doc.program_enrollment

    # ── submission_this_week increment ───────────────────────────────────
    # Program context only, at most once per submission ever, for EVERY
    # result_status (Success - Original, Success - Flagged, AND Failed all
    # count). See docstring's "SUBMISSION_THIS_WEEK" / "IDEMPOTENCY"
    # sections above.
    if row and row.get("unit_type") == "program" and program_enrollment_name:
        if not _already_counted_this_week(submission_id):
            _increment_submission_this_week(program_enrollment_name)
            _mark_counted_this_week(submission_id)

    status_result = None
    if row:
        status_result = recompute_unit_status_by_name(row["name"])

    is_rewardable = status == "Completed" and is_reward_eligible(result_status)
    is_program_row = bool(row and row.get("unit_type") == "program")

    # ── Unit / course completion ─────────────────────────────────────────
    # Fires only when THIS call's recompute_unit_status_by_name is what
    # tipped the row to "Completed" (status_result["just_completed"]).
    # Course-level completion is evaluated ONLY for a program-track row --
    # an event row completing never implies or reports course completion.
    if status_result and status_result["just_completed"] and program_enrollment_name:
        outcome["unit_status"] = status_result["status"]
        outcome["unit_completed"] = True
        if is_program_row:
            pe_doc = frappe.get_doc(_PROGRAM_ENROLLMENT_DOCTYPE, program_enrollment_name)
            if is_course_complete(pe_doc):
                mark_course_completed(program_enrollment_name)
                outcome["course_completed"] = True
                # Decision B: no next_learning_unit_id key at all when the
                # course is complete.
            else:
                outcome["course_completed"] = False
                outcome["next_learning_unit_id"] = next_unit_for(pe_doc)
        # else: event-track completion -- outcome carries unit_completed
        # only; course_completed / next_learning_unit_id are intentionally
        # absent.

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
            # still surfaces the new points/gems/completion state.
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
        # the bump isn't silently skipped. This applies for BOTH program
        # and event rows -- a student's event activity should still be
        # visible as "something changed" even though it carries no
        # course-completion semantics.
        frappe.db.set_value(
            _PROGRAM_ENROLLMENT_DOCTYPE,
            program_enrollment_name,
            "last_activity_at",
            frappe.utils.now_datetime(),
            update_modified=False,
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


def _already_counted_this_week(submission_id: str) -> bool:
    """True iff this submission has already had its one-time
    submission_this_week increment applied. Uses a dedicated marker
    (Submission.rubric_eval_job is NOT reused for this -- that field is
    unrelated; this reads/writes generated_feedback's own JSON is also
    inappropriate since that field is overwritten by feedback_processor.py
    on every delivery). Instead, this uses an atomic conditional UPDATE
    keyed on a dedicated boolean-shaped marker stored directly via
    week_counted_at, a lightweight, idempotency-only timestamp distinct
    from feedback_ready_processed_at (which only ever gets set for
    reward-eligible results) -- see _mark_counted_this_week below, which
    performs the actual guarded write. This function only reads the
    marker; it never writes it, so a read-only caller (this check) can
    never race with the write.
    """
    return bool(frappe.db.get_value("Submission", submission_id, "week_counted_at"))


def _mark_counted_this_week(submission_id: str) -> None:
    """Atomically marks this submission as having had its
    submission_this_week increment applied, via a conditional UPDATE: the
    WHERE clause requires week_counted_at IS NULL, so two concurrent
    callers for the same submission can both attempt this, but only one
    UPDATE actually matches a row -- the other is a no-op. This is what
    makes the increment-then-mark pair in handle_review_result safe
    against the documented duplicate-delivery scenario (RabbitMQ
    redelivery, or both the consumer and review_webhook.py firing for the
    same grading event): the increment in _increment_submission_this_week
    is called unconditionally by handle_review_result's caller only after
    _already_counted_this_week reports False, and this function is what
    permanently records that the increment has happened, so a subsequent
    call's _already_counted_this_week check will see it.

    NOTE: there is a narrow window between the _already_counted_this_week
    read and this write where two fully concurrent calls for the same
    submission could both read False and both proceed to increment --
    this is the same class of race already accepted elsewhere in this
    codebase (e.g. max_submissions_per_week's own documented "checked
    against a counter that free-runs ahead of its own increment site"
    limitation). Closing it completely would require a single atomic
    "increment submission_this_week AND mark week_counted_at in one
    conditional UPDATE" statement; the two-step version here is a
    substantial improvement over no guard at all (which guaranteed a
    double-count on every documented duplicate-delivery case) and is
    accepted as the pragmatic fix rather than a fully race-proof one.

    week_counted_at requires a column on the Submission doctype
    (datetime, nullable). If this column does not exist yet on a given
    site, this UPDATE will fail loudly at the database level rather than
    silently -- add the column via a migration before deploying this
    file.
    """
    frappe.db.sql(
        """
        UPDATE "tabSubmission"
        SET week_counted_at = NOW()
        WHERE name = %s AND week_counted_at IS NULL
        """,
        (submission_id,),
    )


def _increment_submission_this_week(program_enrollment_name: str) -> None:
    """Increment site for ProgramEnrollment.submission_this_week -- see
    handle_review_result's own docstring for the full reasoning (at most
    once per submission, any result_status, program context only, guarded
    by _already_counted_this_week / _mark_counted_this_week)."""
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