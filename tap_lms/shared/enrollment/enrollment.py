from __future__ import annotations

import frappe

from shared.db_retry import run_sql_one, with_serialization_retry
from shared.errors import ValidationFailed

ALLOWED_TRANSITIONS = {
    "default": frozenset({"active", "dropped"}),
    "active": frozenset({"paused", "no_activity", "completed", "dropped", "manual"}),
    "paused": frozenset({"active", "dropped"}),
    "no_activity": frozenset({"active", "dropped"}),
    "completed": frozenset({"manual"}),
    "dropped": frozenset({"active"}),
    "manual": frozenset({"active", "dropped"}),
}

VALID_ACTIVITY_TYPES = ("video", "submission", "quiz")

STAGE_IMPLIES_STATUS = {
    "manually_dropped": "dropped",
    "reengagement_exhausted": "dropped",
    "delivery_failure": "no_activity",
}


@with_serialization_retry
def create_enrollment(student_id: str, batch: str, course_level: str) -> dict:
    """
    One ProgramEnrollment per (student, course_level) for life -- the name
    is the stable, human-readable key "{student_id}-{course_level}", e.g.
    "ST00034562-LVL2". No hash suffix: uniqueness is guaranteed by this
    function itself, not by a random component.

    Unlike the old version, the lookup below does NOT exclude status =
    'dropped'. A dropped enrollment for this (student, course_level) pair
    is reactivated in place (status -> 'active', batch updated to the new
    one) rather than causing a second row to be created -- which would
    both violate "one enrollment per student per course for life" and
    collide on the name. All existing Unit Progress / Submission history
    tied to that row's name is preserved across the drop/re-enroll cycle.
    """
    name = f"{student_id}-{course_level}"
    rows = frappe.db.sql(
        """
        WITH existing AS (
            SELECT name, status FROM "tabProgramEnrollment"
             WHERE student = %(student_id)s AND course_level = %(course_level)s
             LIMIT 1
        ),
        reactivated AS (
            UPDATE "tabProgramEnrollment"
               SET status = 'active', batch = %(batch)s, modified = now()
             WHERE name = (SELECT name FROM existing)
               AND (SELECT status FROM existing) = 'dropped'
            RETURNING name
        ),
        inserted AS (
            INSERT INTO "tabProgramEnrollment"
                (name, student, batch, course_level, status, creation, modified, owner, modified_by)
            SELECT %(name)s, %(student_id)s, %(batch)s, %(course_level)s, 'default',
                   now(), now(), %(owner)s, %(owner)s
             WHERE NOT EXISTS (SELECT 1 FROM existing)
            RETURNING name
        )
        SELECT COALESCE(
                   (SELECT name FROM inserted),
                   (SELECT name FROM reactivated),
                   (SELECT name FROM existing)
               ) AS enrollment_name,
               EXISTS(SELECT 1 FROM existing) AS already_existed
        """,
        {"student_id": student_id, "batch": batch, "course_level": course_level,
         "name": name, "owner": frappe.session.user},
        as_dict=True,
    )
    frappe.db.commit()
    result = rows[0]
    return {"enrollment_name": result["enrollment_name"], "already_existed": result["already_existed"]}


# NOTE: there used to be a `touch_activity(enrollment_name, activity_type=None)`
# function here. It has been removed.
#
# Why: it issued a raw SQL `UPDATE "tabProgramEnrollment" SET
# last_activity_type = ...`, but ProgramEnrollment has no `last_activity_type`
# column -- and is never meant to. last_activity_type is a DERIVED value,
# computed live from Unit Progress rows, never a stored column on either
# ProgramEnrollment or Student Event Enrollment (confirmed by both doctypes'
# actual field lists). Calling the old touch_activity() would have raised a
# Postgres UndefinedColumn error immediately.
#
# Nothing in this codebase called it (verified: no references anywhere under
# tap_app/api/ or shared/), so removing it changes no live behavior. Its two
# legitimate side effects are already handled correctly elsewhere, on the
# real write path, so there is nothing to port forward:
#   - bumping last_activity_at: done directly on program_enrollment_doc /
#     owning_doc inside shared/progress/activities.py's submit_video_watched
#     and submit_quiz, and inside shared/submission/lifecycle.py's
#     submit_artwork (via shared/progress/rewards.py::award_points).
#   - clearing stage when it was 'no_response': already handled, more
#     correctly, by apply_stage()/transition() below, which route every
#     stage/status change through ALLOWED_TRANSITIONS instead of a blind
#     unconditional SQL overwrite.
#
# If a caller ever needs "what did this student last do", the answer is
# always a derived read, never a write:
#   - program track: shared.progress.unit_progress.resolve_last_activity_type_for_track
#   - event track:   shared.events.enrollment.is_enrolled (which resolves it
#     via Student Event Enrollment.unit_progress -> find_unit_progress_row_by_name_global)
# Do not reintroduce a write to a `last_activity_type` field on either
# doctype -- add the column deliberately first if a stored value is ever
# actually required, and update this module and its callers together.


@with_serialization_retry
def transition(enrollment_name: str, new_status: str) -> None:
    current = run_sql_one(
        """SELECT status FROM "tabProgramEnrollment" WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name},
    )
    if not current:
        raise ValidationFailed("enrollment not found", error_code="enrollment_not_found")
    allowed = ALLOWED_TRANSITIONS.get(current["status"], frozenset())
    if new_status not in allowed:
        raise ValidationFailed(
            f"cannot transition from {current['status']} to {new_status}",
            error_code="invalid_transition",
        )
    frappe.db.sql(
        """UPDATE "tabProgramEnrollment" SET status = %(new_status)s, modified = now() WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name, "new_status": new_status},
    )
    frappe.db.commit()


@with_serialization_retry
def apply_stage(enrollment_name: str, new_stage: str) -> None:
    frappe.db.sql(
        """UPDATE "tabProgramEnrollment" SET stage = %(stage)s, modified = now() WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name, "stage": new_stage},
    )
    frappe.db.commit()

    implied_status = STAGE_IMPLIES_STATUS.get(new_stage)
    if not implied_status:
        return
    current = run_sql_one(
        """SELECT status FROM "tabProgramEnrollment" WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name},
    )
    if current and implied_status in ALLOWED_TRANSITIONS.get(current["status"], frozenset()):
        transition(enrollment_name, implied_status)


@with_serialization_retry
def bump_points_and_activity(enrollment_name: str, points_delta: int = 0, activity_delta: int = 0) -> dict:
    """Direct, synchronous bump - replaces the old Redis-queue enqueue_points.
    No queue anywhere in the TapApp path."""
    rows = frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET points = COALESCE(points, 0) + %(points_delta)s,
               activity_this_week = COALESCE(activity_this_week, 0) + %(activity_delta)s,
               modified = now()
         WHERE name = %(enrollment)s
        RETURNING points, activity_this_week
        """,
        {"enrollment": enrollment_name, "points_delta": points_delta, "activity_delta": activity_delta},
        as_dict=True,
    )
    frappe.db.commit()
    if not rows:
        raise ValidationFailed("enrollment not found", error_code="enrollment_not_found")
    return {"points": rows[0]["points"], "activity_this_week": rows[0]["activity_this_week"]}