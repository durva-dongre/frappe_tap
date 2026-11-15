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

_PROGRAM_ENROLLMENT_TABLE = "tabProgramEnrollment"
_PROGRAM_ENROLLMENT_DOCTYPE = "ProgramEnrollment"


def handle_review_result(submission_doc) -> dict:
    """The one audited path that grants points/gems for a graded submission,
    bumps the weekly submission_this_week counter, and detects and reports
    unit/course completion driven by a submission's own grading outcome.

    Gallery promotion is NOT handled here -- it runs as a separate nightly
    batch job (shared/jobs/gallery_promotion_sweep.py).

    The ProgramEnrollment this function awards points/gems/last_activity_at
    against is resolved from the Unit Progress row's own, live `parent`
    field (row["parent"]) whenever a row resolves at all, rather than from
    submission_doc.program_enrollment, since a Unit Progress row is
    immutably tied to whichever ProgramEnrollment it was created under.
    submission_doc.program_enrollment is used only as a last-resort
    fallback for the case where no Unit Progress row can be resolved at
    all.

    Completion and reward eligibility are two different gates, defined in
    shared.submission.status: "Success - Flagged" counts as a completed,
    scored submission for unit/track completion purposes
    (is_submission_complete), even though it never earns the points/gems
    bonus (is_reward_eligible).

    SUBMISSION_THIS_WEEK: this function is the SOLE increment site for
    ProgramEnrollment.submission_this_week, firing on every call to this
    function for a program-track row, for EVERY result_status --
    "Success - Original", "Success - Flagged", AND "Failed" all count.
    This is unconditional on status/result_status, happening before the
    reward/completion branches below, and only when a Unit Progress row
    (and therefore an owning ProgramEnrollment) actually resolves. The
    increment is scoped to program context only, matching the field's own
    doctype description; an event-context submission does NOT bump this
    counter.

    There is no per-submission dedupe guard on this increment: a duplicate
    delivery of the same grading event (a RabbitMQ redelivery, or both the
    consumer and review_webhook.py firing for the same event) can
    increment this counter more than once for the same submission. This
    is accepted, at-least-once behavior, consistent with
    shared.progress.rewards.max_submissions_per_week's own documented
    position that the weekly cap is a practical deterrent, not a hard
    guarantee -- a rare double-increment only ever makes the cap bind
    slightly earlier for that student that week, and self-corrects at the
    next weekly reset (shared/jobs/student_weekly_reset.py).

    The reward branch (points/gems) is unaffected by the above and keeps
    its own real idempotency guard, via Submission.feedback_ready_processed_at
    (_already_rewarded), since double-awarding points/gems is a materially
    worse failure mode than an occasionally-early weekly cap.

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
      An event-track row completing never evaluates or reports
      course_completed / next_learning_unit_id at all -- course
      completion is a program-track-only concept.
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

    program_enrollment_name = (row.get("parent") if row else None) or submission_doc.program_enrollment

    # submission_this_week increment -- program context only, every
    # call, no per-submission dedupe (see docstring).
    if row and row.get("unit_type") == "program" and program_enrollment_name:
        _increment_submission_this_week(program_enrollment_name)

    status_result = None
    if row:
        status_result = recompute_unit_status_by_name(row["name"])

    is_rewardable = status == "Completed" and is_reward_eligible(result_status)
    is_program_row = bool(row and row.get("unit_type") == "program")

    # ── Unit / course completion ─────────────────────────────────────────
    if status_result and status_result["just_completed"] and program_enrollment_name:
        outcome["unit_status"] = status_result["status"]
        outcome["unit_completed"] = True
        if is_program_row:
            pe_doc = frappe.get_doc(_PROGRAM_ENROLLMENT_DOCTYPE, program_enrollment_name)
            if is_course_complete(pe_doc):
                mark_course_completed(program_enrollment_name)
                outcome["course_completed"] = True
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


def _increment_submission_this_week(program_enrollment_name: str) -> None:
    """Increment site for ProgramEnrollment.submission_this_week -- see
    handle_review_result's own docstring for the full reasoning (every
    call, any result_status, program context only, no per-submission
    dedupe guard)."""
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