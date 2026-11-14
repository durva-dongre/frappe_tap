from __future__ import annotations

import frappe

from shared.db_retry import run_sql_one, with_serialization_retry
from shared.errors import ValidationFailed

# "completed" is a legal target from every non-terminal status except
# "dropped" (active/paused/no_activity/manual can all reach it). This
# matters because a submission can grade "Success - Original"
# asynchronously after a student has gone paused/no_activity/manual, and
# course completion must be recordable whenever it genuinely happens,
# regardless of the enrollment's engagement-status at that moment.
# "dropped" deliberately does NOT gain "completed": a dropped enrollment
# reaching course completion is treated as out of scope for direct
# completion.
#
# "completed" can also transition to "dropped" directly, so an operator
# who needs to drop an already-completed enrollment is not forced through
# an undocumented "completed -> manual -> dropped" detour. "completed ->
# manual" is left in place for any workflow that depends on it.
ALLOWED_TRANSITIONS = {
    "default": frozenset({"active", "dropped"}),
    "active": frozenset({"paused", "no_activity", "completed", "dropped", "manual"}),
    "paused": frozenset({"active", "completed", "dropped"}),
    "no_activity": frozenset({"active", "completed", "dropped"}),
    "completed": frozenset({"manual", "dropped"}),
    "dropped": frozenset({"active"}),
    "manual": frozenset({"active", "completed", "dropped"}),
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

    The lookup below does NOT exclude status = 'dropped'. A dropped
    enrollment for this (student, course_level) pair is reactivated in
    place (status -> 'active', batch updated to the new one) rather than
    causing a second row to be created -- which would both violate "one
    enrollment per student per course for life" and collide on the name.
    All existing Unit Progress / Submission history tied to that row's
    name is preserved across the drop/re-enroll cycle.

    Batch-mismatch detection: if a row already exists in any status other
    than 'dropped' (e.g. 'completed', 'active', 'paused'), this function
    reports `already_existed=True` and, if the caller's requested `batch`
    differs from the row's stored batch, also reports that mismatch
    explicitly via `batch_mismatch` (with the existing row's own batch
    alongside it) -- rather than silently keeping the existing batch with
    no signal that the caller asked for a different one. No implicit
    write happens for this case: changing a live enrollment's batch is a
    deliberate decision callers must make explicitly (there is no
    "reassign batch" transition defined on this state machine), so this
    function never writes in that branch; it only stops hiding the
    mismatch from the caller.
    """
    name = f"{student_id}-{course_level}"
    rows = frappe.db.sql(
        """
        WITH existing AS (
            SELECT name, status, batch FROM "tabProgramEnrollment"
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
               EXISTS(SELECT 1 FROM existing) AS already_existed,
               (SELECT status FROM existing) AS existing_status,
               (SELECT batch FROM existing) AS existing_batch
        """,
        {"student_id": student_id, "batch": batch, "course_level": course_level,
         "name": name, "owner": frappe.session.user},
        as_dict=True,
    )
    frappe.db.commit()
    result = rows[0]

    already_existed = result["already_existed"]
    existing_status = result["existing_status"]
    existing_batch = result["existing_batch"]

    # A mismatch only matters for a row that already existed, was NOT just
    # reactivated from 'dropped' (which already took the new batch above),
    # and whose stored batch differs from the one this call asked for.
    batch_mismatch = bool(
        already_existed
        and existing_status != "dropped"
        and existing_batch is not None
        and existing_batch != batch
    )

    return {
        "enrollment_name": result["enrollment_name"],
        "already_existed": already_existed,
        "batch_mismatch": batch_mismatch,
        "existing_batch": existing_batch if batch_mismatch else None,
    }


# There is deliberately no `touch_activity(enrollment_name, activity_type)`
# function in this module. ProgramEnrollment has no `last_activity_type`
# column, and is never meant to have one -- last_activity_type is a
# DERIVED value, computed live from Unit Progress rows, never a stored
# column on either ProgramEnrollment or Student Event Enrollment.
#
# The two legitimate side effects such a helper would otherwise be used
# for are already handled correctly on the real write path:
#   - bumping last_activity_at: done directly on program_enrollment_doc /
#     owning_doc inside shared/progress/activities.py's submit_video_watched
#     and submit_quiz, and inside shared/submission/lifecycle.py's
#     submit_artwork (via shared/progress/rewards.py::award_points).
#   - clearing stage when it was 'no_response': handled by
#     apply_stage()/transition() below, which route every stage/status
#     change through ALLOWED_TRANSITIONS instead of a blind, unconditional
#     overwrite.
#
# If a caller ever needs "what did this student last do", the answer is
# always a derived read, never a write:
#   - program track: shared.progress.unit_progress.resolve_last_activity_type_for_track
#   - event track:   shared.events.enrollment.is_enrolled (which resolves it
#     via Student Event Enrollment.unit_progress -> find_unit_progress_row_by_name_global)
# Do not add a write to a `last_activity_type` field on either doctype
# without first adding the column deliberately and updating this module
# and its callers together.


@with_serialization_retry
def transition(enrollment_name: str, new_status: str) -> None:
    """Performs the read-check-write sequence under a `SELECT ... FOR
    UPDATE` row lock, so two concurrent callers can never both read the
    same `current status`, both pass the ALLOWED_TRANSITIONS check against
    it, and then have one UPDATE silently overwrite the other's -- e.g.
    one caller moving the row to "completed" and another concurrently
    moving it to "dropped" based on a status read before either write
    landed, with only the last UPDATE's value surviving and no error
    raised to either caller. The @with_serialization_retry decorator
    already retries on a serialization failure, so taking the row lock
    here is safe: a genuine conflict is detected (not silently lost) and
    retried from scratch rather than silently clobbered.
    """
    current = run_sql_one(
        """SELECT status FROM "tabProgramEnrollment" WHERE name = %(enrollment)s FOR UPDATE""",
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
    """Direct, synchronous bump against ProgramEnrollment -- no queue
    anywhere in the TapApp path.

    The column this bumps is submission_this_week (ProgramEnrollment's
    former activity_this_week field was renamed to submission_this_week;
    this function's own `activity_delta` parameter name is kept for
    backward compatibility with any external/future caller, since no
    caller of this specific function exists anywhere in tap_app/api or
    shared today). If this function is ever wired up to a real caller,
    confirm at that point whether "activity_delta" is still the right
    increment semantics for submission_this_week's "once per graded
    review outcome" counting rule (see shared/submission/review_result.py),
    since this function's current semantics (bump on arbitrary activity)
    predate that rule and may not match it.
    """
    rows = frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET points = COALESCE(points, 0) + %(points_delta)s,
               submission_this_week = COALESCE(submission_this_week, 0) + %(activity_delta)s,
               modified = now()
         WHERE name = %(enrollment)s
        RETURNING points, submission_this_week
        """,
        {"enrollment": enrollment_name, "points_delta": points_delta, "activity_delta": activity_delta},
        as_dict=True,
    )
    frappe.db.commit()
    if not rows:
        raise ValidationFailed("enrollment not found", error_code="enrollment_not_found")
    return {"points": rows[0]["points"], "submission_this_week": rows[0]["submission_this_week"]}


# ---------------------------------------------------------------------------
# Course completion from a non-"active" status, and the two auto-activation
# call sites (first activity log, login/sync reads).
# ---------------------------------------------------------------------------

def mark_course_completed(enrollment_name: str) -> bool:
    """Idempotently transitions enrollment_name to "completed", from
    whatever ALLOWED_TRANSITIONS-legal state it is currently in (active,
    paused, no_activity, or manual). A no-op, returning False, if the
    enrollment is already "completed" -- this function is designed to be
    called every time a unit completion check determines the course is
    finished, including on a repeat call for an enrollment that was
    already marked completed by an earlier call (e.g. a submission's
    async grading callback firing more than once, or both the quiz path
    and the submission path independently detecting completion for the
    same already-completed course). Raises ValidationFailed (mapped to a
    400) only for a genuinely illegal transition -- i.e. an enrollment in
    "dropped" status, which deliberately has no path to "completed" -- or
    for an enrollment_name that does not exist at all.

    The current status is read under transition()'s own row lock (by
    simply calling transition(), which itself takes `FOR UPDATE`), so the
    check-and-transition is a single atomic step from the caller's
    perspective: either transition() raises (truly illegal), or it
    succeeds exactly once. This avoids a window where two concurrent
    callers could both see "not yet completed" and both call transition()
    independently, which would rely entirely on transition()'s own
    serialization retry to avoid a double-apply rather than being
    guaranteed by this function's own check.

    Returns True iff this call actually performed the transition (i.e.
    the enrollment was not already "completed"); False if it was already
    "completed" and nothing needed to change. Callers that need to react
    to "did completion just happen on this call" can use this return
    value for that purpose.
    """
    current = run_sql_one(
        """SELECT status FROM "tabProgramEnrollment" WHERE name = %(enrollment)s FOR UPDATE""",
        {"enrollment": enrollment_name},
    )
    if not current:
        raise ValidationFailed("enrollment not found", error_code="enrollment_not_found")
    if current["status"] == "completed":
        return False
    transition(enrollment_name, "completed")
    return True


def activate_if_inactive(enrollment_doc) -> bool:
    """Flips enrollment_doc.status to "active" if it is currently
    "default" or "no_activity". Never touches "paused", "manual",
    "completed", or "dropped" -- those are states a human, or an explicit
    business rule (apply_stage's STAGE_IMPLIES_STATUS), put the enrollment
    into on purpose, and neither a routine activity log nor a login/sync
    read is allowed to silently undo that.

    This is the single helper backing BOTH call sites that need this
    behavior:
      1. First-ever Unit Progress row creation for ANY activity type
         (video, quiz, or submission) -- called from
         shared/progress/activities.py::submit_video_watched and
         submit_quiz alike, so a unit whose first-ever logged activity is
         a quiz activates the enrollment exactly as a first video watch
         would.
      2. Every login/profile/sync read -- called from
         shared/profile/sync.py::get_sync_payload /
         get_profile_select_payload, and from
         tap_app/api/auth.py::_build_resume_payload (via
         shared.profile.sync.get_profile_select_payload, which both now
         share -- see that module).

    Caller is responsible for persisting the change: enrollment_doc here
    is a live, in-memory Frappe Document (not a bare name string, unlike
    transition()/mark_course_completed() above), because both call sites
    already hold a loaded doc they are about to save or have just loaded
    for a read. This function mutates enrollment_doc.status directly, in
    memory, rather than calling transition() (which operates by name via
    raw SQL and its own frappe.db.commit()) -- using transition() here
    would require the caller to immediately reload the doc to see the new
    status, which both call sites would otherwise have to do redundantly.
    Call sites that only READ (sync.py's two functions) must explicitly
    persist this themselves (frappe.db.set_value, since they do not
    otherwise save the doc) immediately after calling this, or the flip
    will be silently lost; call sites that already SAVE the doc as part of
    their normal flow (activities.py's submit_video_watched/submit_quiz,
    whose caller tap_app/api/progress.py::_save_affected_docs always calls
    pe.save()) get persistence for free.

    This function performs the ALLOWED_TRANSITIONS legality check inline
    rather than delegating to transition(), specifically so it can return
    a plain boolean (did it flip or not) instead of raising for the
    expected, common case of "nothing to do" (status is already active,
    paused, manual, completed, or dropped) -- transition() raises
    ValidationFailed for a disallowed target, which would be the wrong
    signal here: "this call didn't need to activate anything" is normal,
    frequent, and not an error.

    Returns True iff this call actually changed enrollment_doc.status (so
    callers can decide whether to surface the change -- e.g. adding a
    "status" field to a login/sync response only when it just flipped,
    never otherwise, per this project's "absent means unchanged"
    convention for status-change notification).
    """
    if enrollment_doc.status not in ("default", "no_activity"):
        return False
    enrollment_doc.status = "active"
    return True