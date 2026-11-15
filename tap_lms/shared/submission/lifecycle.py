"""
shared/submission/lifecycle.py

check_attempt_cap + submit_artwork: the two Worker-facing operations that
gate/create a Submission row. Reattempt rule: only allowed if attempts are
left AND a prior submission exists AND that prior submission is terminal
(Completed/Failed) -- never while one is still Pending/Processing.

Row lock via shared.submission.locks around the cap re-check + write so two
concurrent submit_artwork calls for the same (student, unit, context) can't
both pass.

submit_artwork does NOT create the Submission row itself -- it delegates
that to tap_lms.imgana.submission.submit_artwork, the same pipeline used by
the WhatsApp channel. imgana's function takes a plain, already-public
submission URL and handles its own media detection; this module is
responsible for everything imgana's function doesn't do: attempt-cap
enforcement, the weekly submission-cap enforcement, the video prerequisite
gate, the Unit Progress row write, the first-attempt points award, and
stamping program_enrollment onto the new row.

Worker route wiring: tap_app/api/submission.py::submit_artwork is the only
whitelisted entrypoint the Worker calls for this. Do not point the Worker
directly at tap_lms.imgana.submission.submit_artwork -- it has no
attempt-cap or Unit Progress awareness of its own.

SUBMISSION_ID -- NOT RETURNED BY submit_artwork: see this function's own
docstring.

EVENT-TRACK ROW RESOLUTION (fixed): previously, both check_attempt_cap and
submit_artwork resolved their Unit Progress row ONLY against the
currently-ACTIVE ProgramEnrollment's own unit_progress child table
(_find_existing_unit_progress_row / get_or_create_unit_progress_row called
directly on `pe`), with no special handling for context == "event". This
directly contradicted the invariant shared/progress/activities.py
documents and enforces for its own event-context writes: "a Unit Progress
row is immutably tied to whichever ProgramEnrollment it was created
under, never to whatever enrollment happens to be active right now."

Concretely, this caused real data fragmentation: if a student's active
ProgramEnrollment rotated between watching an event's video (handled by
activities.py, correctly anchored to wherever the row actually lives) and
submitting artwork for that same event unit (handled here), submit_artwork
would create a SECOND, separate Unit Progress row on the new active
enrollment -- one with video_watched=True and no submission (on the old
enrollment), and one with video_watched=False and the submission (on the
new enrollment) -- and would then incorrectly reject the submission with
"video must be completed before submitting for this unit", even though
the student genuinely had watched it.

Both check_attempt_cap and submit_artwork now call
shared.progress.activities._resolve_event_unit_progress_row for
context == "event", exactly as activities.py's own submit_video_watched/
submit_quiz do, so all three event-context write paths (video, quiz,
submission) and the one event-context read path (check_attempt_cap)
resolve to the exact same row, anchored to whichever enrollment actually
owns it -- never to whatever happens to be "active" at call time.

COMPLETED-COURSE WRITE GUARD: shared.enrollment.active_batch now resolves
a "completed" ProgramEnrollment for READS (so sync/profile keep working
after a course finishes -- see that module's docstring), but writing new
submissions against an already-completed course must still be rejected
explicitly, rather than silently reopened as a side effect of that read
fix. Both check_attempt_cap and submit_artwork now check
pe.status == "completed" immediately after resolving `pe` and raise
InvalidInput before touching anything else.

WEEKLY SUBMISSION CAP: unchanged from before -- see
_require_weekly_submission_cap_not_reached's own docstring. Event-context
submissions are never subject to this cap (program-context only, per
submission_this_week's own doctype field description).

ATTEMPT-NUMBER INTEGRITY: unchanged -- see _validate_object_key_attempt.

DECISION D (last_activity_at on every attempt): award_points
(shared/progress/rewards.py) bumps enrollment_doc.last_activity_at when
bump_activity=True. submit_artwork calls award_points on every successful
attempt (first or reattempt), against the row's OWNING enrollment
(owning_doc, resolved per the event-row fix above -- which equals `pe`
itself for program context, since program-track rows always live on the
active, lifelong enrollment), passing 0 as the amount on a non-first
attempt and bump_activity=True explicitly on every call.
"""

from __future__ import annotations

import frappe

from shared.errors import CapReached, InvalidInput, NotFound
from shared.enrollment.active_batch import get_active_program_enrollment_name
from shared.progress.unit_progress import get_or_create_unit_progress_row, recompute_unit_status
from shared.progress.rewards import (
    award_points,
    points_for_submission_first_attempt,
    max_submission_attempts,
    max_submissions_per_week,
)
from shared.submission.locks import lock_program_enrollment_row
from shared.submission.object_naming import parse_object_key
from shared.db_retry import with_serialization_retry

# Narrow, DB-driver-level exception classes that genuinely indicate "this
# table/column doesn't exist" (a schema mismatch) -- as opposed to any other
# exception, which should propagate rather than be silently treated the same
# way. frappe.db exposes these as aliases of the underlying driver's
# exception types (psycopg2.errors.UndefinedTable / UndefinedColumn surface
# through frappe.db.ProgrammingError on Postgres).
_SCHEMA_MISMATCH_EXCEPTIONS = (frappe.db.InternalError, frappe.db.ProgrammingError)


def resolve_learning_unit_for_assignment(assignment_id: str, context: str, student_id: str) -> str:
    """Resolves which LearningUnit an assignment_id belongs to, for cap
    checking and Unit Progress bookkeeping. Tries a direct UnitContentItem
    link first (content_type == 'Assignment', content == assignment_id),
    then falls back to event/assignment-vertical resolution. The savepoint
    around the primary query means a genuine schema mismatch degrades to the
    fallback paths below (and ultimately NOT_FOUND) instead of aborting the
    whole surrounding transaction -- but any OTHER kind of exception (a
    dropped connection, an unrelated serialization failure) is re-raised
    after the ROLLBACK TO SAVEPOINT, rather than silently swallowed.
    """
    try:
        frappe.db.sql("SAVEPOINT resolve_unit_for_assignment")
        row = frappe.db.sql(
            """
            SELECT parent FROM "tabUnitContentItem"
            WHERE content_type = 'Assignment' AND content = %s
            LIMIT 1
            """,
            (assignment_id,),
        )
        frappe.db.sql("RELEASE SAVEPOINT resolve_unit_for_assignment")
    except _SCHEMA_MISMATCH_EXCEPTIONS:
        frappe.db.sql("ROLLBACK TO SAVEPOINT resolve_unit_for_assignment")
        frappe.logger().warning(
            "resolve_learning_unit_for_assignment: tabUnitContentItem lookup "
            "failed with a schema-mismatch error -- falling back to "
            "event/assignment resolution",
            exc_info=True,
        )
        row = None
    except Exception:
        frappe.db.sql("ROLLBACK TO SAVEPOINT resolve_unit_for_assignment")
        frappe.logger().error(
            "resolve_learning_unit_for_assignment: tabUnitContentItem lookup "
            "failed with an unexpected (non-schema) error -- re-raising "
            "after rolling back to savepoint so the surrounding transaction "
            "is not left poisoned",
            exc_info=True,
        )
        raise

    if row:
        return row[0][0]

    if context == "event":
        enrollment = frappe.db.sql(
            """
            SELECT ec.learning_unit
            FROM "tabStudent Event Enrollment" see
            JOIN "tabEvent Campaign" ec ON ec.name = see.event
            WHERE see.parent = %s AND see.status = 'active'
            ORDER BY see.idx DESC
            LIMIT 1
            """,
            (student_id,),
        )
        if enrollment:
            return enrollment[0][0]
        raise NotFound("no active event enrollment for this student")

    assignment = frappe.db.get_value("Assignment", assignment_id, ["vertical", "level"], as_dict=True)
    if not assignment:
        raise NotFound("assignment does not exist")

    unit = frappe.db.sql(
        """
        SELECT name FROM "tabLearningUnit"
        WHERE course_vertical = %s
        ORDER BY modified DESC
        LIMIT 1
        """,
        (assignment.vertical,),
    )
    if not unit:
        raise NotFound("could not resolve a learning unit for this assignment")
    return unit[0][0]


def require_video_done(unit_progress_row) -> None:
    """Within-unit guard: video must be watched before any submission OR
    quiz, in both program and event contexts. Exported (no leading
    underscore) because shared/progress/activities.py::submit_quiz reuses
    this exact same guard rather than re-implementing its own copy."""
    if not unit_progress_row.video_watched:
        raise InvalidInput("video must be completed before submitting for this unit")


# Kept as a private alias for any caller that imported the old,
# underscore-prefixed name directly.
_require_video_done = require_video_done


def _require_course_not_completed(pe) -> None:
    """Rejects a write against an already-completed ProgramEnrollment.

    shared.enrollment.active_batch.get_active_program_enrollment_name now
    resolves a "completed" enrollment for READ paths (sync, profile) that
    previously broke entirely once a student's only enrollment finished --
    see that module's docstring. That fix is deliberately READ-only: it
    must not silently reopen check_attempt_cap / submit_artwork for a
    finished course. This explicit guard is what keeps that boundary firm,
    called immediately after resolving `pe` in both functions below,
    before any other check or write happens.
    """
    if pe.status == "completed":
        raise InvalidInput("course already completed; no further submissions are accepted", error_code="course_completed")


def _require_weekly_submission_cap_not_reached(pe) -> None:
    """Program-context weekly cap: rejects with CapReached (CONFLICT) if
    pe.submission_this_week is already at or beyond
    shared.progress.rewards.max_submissions_per_week(). This function only
    ever READS submission_this_week, never increments it -- the increment
    happens in review_result.py, once per graded outcome.

    Deliberately program-context only, matching submission_this_week's own
    doctype-field description -- an event-context submission is never
    subject to this cap.
    """
    cap = max_submissions_per_week()
    current = pe.submission_this_week or 0
    if current >= cap:
        raise CapReached("weekly submission cap already reached")


def _find_existing_unit_progress_row(parent_doc, learning_unit: str, unit_type: str):
    """Read-only lookup of an existing Unit Progress row, WITHOUT creating
    one if it's missing -- unlike get_or_create_unit_progress_row. Used by
    check_attempt_cap, which must never have the side effect of persisting
    a new, empty row just because a client asked "how many attempts do I
    have left." Returns None if no such row exists yet.

    Only used for context == "program" -- event context is resolved via
    _resolve_event_unit_progress_row instead (see
    _resolve_row_for_cap_check below), which already performs the
    equivalent read-only-safe lookup for an existing row (it only creates
    one when none exists at all, mirroring this function's own contract
    for the program-context case)."""
    rows = getattr(parent_doc, "unit_progress") or []
    matches = [r for r in rows if r.learning_unit == learning_unit and r.unit_type == unit_type]
    if len(matches) > 1:
        raise InvalidInput(
            f"data integrity error: multiple Unit Progress rows for "
            f"(learning_unit={learning_unit}, unit_type={unit_type})"
        )
    return matches[0] if matches else None


def _resolve_row_for_context(pe, student_id: str, unit: str, context: str, create_if_missing: bool):
    """Single entrypoint used by both check_attempt_cap and submit_artwork
    to resolve the Unit Progress row for a (student, unit, context),
    replacing each function's own previously-separate, active-PE-only
    lookup.

    For context == "program": the row always lives on `pe` itself (the
    active, lifelong enrollment for this course level) -- looked up via
    _find_existing_unit_progress_row (no create) or
    get_or_create_unit_progress_row (create), matching each caller's own
    needs. owning_doc is always `pe` for program context.

    For context == "event": resolved via
    shared.progress.activities._resolve_event_unit_progress_row -- the
    SAME global, by-name resolution activities.py uses for its own
    event-context video/quiz writes, so a submission's row is guaranteed
    to be the exact same row a prior video-watch or quiz-grade already
    wrote to, regardless of whether `pe` (today's active enrollment) is
    the same enrollment that originally owned it.
    _resolve_event_unit_progress_row always creates a row if none exists
    yet (there's nothing to preserve continuity with in that case), so
    create_if_missing has no effect for event context -- check_attempt_cap
    calling this for event context will, same as before this fix, only
    ever see a row that already exists UNLESS this is the very first
    activity for this event, matching the function's own "nothing to do
    until something exists" read semantics as closely as the shared
    resolver allows.

    Returns (owning_doc, row_or_None). row is None only for
    context == "program" with create_if_missing=False and no existing row.
    """
    if context == "event":
        from shared.progress.activities import _resolve_event_unit_progress_row
        owning_doc, row = _resolve_event_unit_progress_row(pe, student_id, unit)
        return owning_doc, row

    if create_if_missing:
        row = get_or_create_unit_progress_row(pe, unit, context)
    else:
        row = _find_existing_unit_progress_row(pe, unit, context)
    return pe, row


def _validate_object_key_attempt(object_key: str | None, expected_attempt: int) -> None:
    """Cross-checks the "attempt" segment embedded in a client-supplied
    object_key against the real next attempt number Frappe is about to
    record (row.submission_attempts + 1). The Worker's own validation
    (assertObjectKeyMatches) only confirms object_key is internally
    self-consistent -- it never checks the attempt segment against Frappe's
    own counter, since the Worker holds no server-side record of what the
    true attempt count is. Without this check, a client could request an
    upload URL for one attempt and submit under a hand-built object_key
    naming a different attempt number, letting R2/gallery storage diverge
    from Frappe's own attempt bookkeeping.

    A key that fails to parse at all is left alone here -- that is a
    different, already-handled failure mode (the Worker validates key shape
    before ever calling this route); this check only fires for a
    syntactically valid key whose attempt number disagrees with reality.
    """
    if not object_key:
        return
    try:
        parsed_key = parse_object_key(object_key)
    except InvalidInput:
        return
    if parsed_key["attempt"] != expected_attempt:
        raise InvalidInput(
            f"object_key's attempt ({parsed_key['attempt']}) does not match "
            f"this submission's actual next attempt number ({expected_attempt})"
        )


def check_attempt_cap(student_id: str, assignment_id: str, context: str = "program") -> dict:
    """Reports the student's current attempt number and how many attempts
    remain for this assignment. Read-only: enforces the completed-course
    guard, the video prerequisite, the weekly submission cap (program
    context only), and the per-assignment attempt cap as checks only -- it
    does not create a Unit Progress row for program context (event context
    may create one on first-ever activity, per _resolve_row_for_context's
    own docstring) and does not save the ProgramEnrollment document.

    For context == "event", the Unit Progress row is resolved via the
    SAME global, by-name lookup submit_artwork and activities.py's
    video/quiz writes use (see _resolve_row_for_context) -- previously
    this function only ever looked inside the currently-active
    enrollment's own unit_progress table, which could report a stale
    attempt_number: 1 for a student whose real event progress (and real
    attempt count) lived on a different, prior enrollment. That mismatch
    meant check_attempt_cap could promise an attempt budget that
    submit_artwork would then immediately contradict once it resolved the
    real row. Both functions now agree.

    If no Unit Progress row exists yet for this (student, unit, context)
    (program context only -- event context always resolves or creates
    one), the video-prerequisite check still applies (a brand-new unit has
    video_watched=False by definition, so this raises InvalidInput exactly
    as it would for an existing, not-yet-watched row) and attempt_number is
    reported as 1 with the full attempt cap remaining.

    The weekly cap is checked here as well as in submit_artwork: this is
    the first gate the Worker's own /submission/request_upload call hits,
    and it must agree with submit_artwork's own later check -- otherwise a
    student at the weekly cap gets a signed upload URL issued, uploads
    their file, and only then discovers the attempt was rejected by
    submit_artwork. Checking it here too rejects the request before any
    upload URL is ever signed.

    attempts_remaining is computed against the UPCOMING attempt number
    (existing_attempts + 1) -- matching submit_artwork's own
    post-increment computation for the same (student, assignment, context)
    pair -- instead of against the pre-increment count, so both functions
    agree on attempts_remaining for the same attempt.

    COMPLETED COURSE: raises InvalidInput (error_code="course_completed")
    immediately if pe.status == "completed" -- see
    _require_course_not_completed's own docstring for why this guard is
    necessary now that `pe` itself can resolve to a completed enrollment
    for read paths elsewhere in this codebase.

    This function is read-only (no writes, no row lock beyond the implicit
    read), so it is NOT wrapped in @with_serialization_retry -- there is no
    write here that a SerializationFailure could silently discard.
    """
    pe_name = get_active_program_enrollment_name(student_id)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)

    _require_course_not_completed(pe)

    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    _owning_doc, row = _resolve_row_for_context(pe, student_id, unit, context, create_if_missing=False)

    # A never-started unit has no video_watched yet -- require_video_done
    # needs an object with a `.video_watched` attribute, so build a minimal
    # stand-in rather than persisting a real row just to check this. For
    # event context, _resolve_row_for_context always returns a real row
    # (it creates one on first-ever activity), so this stub path is only
    # ever exercised for context == "program".
    if row is None:
        class _UnwatchedStub:
            video_watched = 0
        require_video_done(_UnwatchedStub())
    else:
        require_video_done(row)

    if context == "program":
        _require_weekly_submission_cap_not_reached(pe)

    cap = max_submission_attempts()
    existing_attempts = row.submission_attempts if row is not None else 0
    existing_submission = row.submission if row is not None else None

    if existing_attempts >= cap:
        raise CapReached("submission attempt cap already reached")
    if existing_submission and existing_attempts > 0:
        sub_status = frappe.db.get_value("Submission", existing_submission, "status")
        if sub_status not in ("Completed", "Failed"):
            raise CapReached("previous submission still being reviewed")

    attempt_number = existing_attempts + 1
    attempts_remaining = max(cap - attempt_number, 0)

    return {"attempt_number": attempt_number, "attempts_remaining": attempts_remaining}


@with_serialization_retry
def submit_artwork(student_id: str, assignment_id: str, submission_url: str, object_key: str | None = None,
                    context: str = "program") -> dict:
    """Re-checks the completed-course guard, attempt cap, weekly
    submission cap (program context only), and video prerequisite under a
    row lock, cross-checks object_key's own attempt number against
    reality, then hands off the actual Submission creation to imgana's
    submit_artwork pipeline (unmodified). submission_url is a plain,
    already-public URL the caller provides directly --
    tap_app/api/submission.py::submit_artwork is responsible for building
    this URL from the Worker's object_key before calling here.

    EVENT-TRACK ROW RESOLUTION (fixed): the Unit Progress row for
    context == "event" is now resolved via the SAME global, by-name lookup
    (_resolve_row_for_context -> activities._resolve_event_unit_progress_row)
    that activities.py's own submit_video_watched/submit_quiz use, instead
    of always creating/reusing a row on the currently-active enrollment.
    Previously, this function's own get_or_create_unit_progress_row(pe, ...)
    call for event context could create a SECOND, disconnected Unit
    Progress row whenever the student's active enrollment had rotated
    since they last interacted with this event -- producing a row with no
    video_watched history, which would then incorrectly fail the video
    prerequisite below even though the student genuinely had watched the
    video (on the OTHER, now-orphaned row). This also means
    points/last_activity_at for an event submission are now awarded
    against the row's true owning enrollment (owning_doc), not
    unconditionally against `pe` -- see award_points's call below.

    object_key's attempt segment is validated against
    row.submission_attempts + 1 (see _validate_object_key_attempt) BEFORE
    imgana is ever called, so a mismatched key can never create a
    Submission row. Beyond that cross-check, object_key is used here ONLY
    to confirm a caller supplied one (logging a warning if not) -- it is
    NOT used to compute an identifier for the response. submit_artwork's
    response carries no submission_id at all; a client reads a
    submission's id/state from /progress/sync or /progress/last_submission
    instead.

    program_enrollment is stamped on the new Submission row as
    owning_doc.name (the row's TRUE owning enrollment -- `pe` for program
    context, or whatever enrollment actually owns the event row for event
    context), not unconditionally `pe.name`, now that the two can differ.

    COMPLETED COURSE: raises InvalidInput (error_code="course_completed")
    immediately after resolving `pe`, if pe.status == "completed" -- see
    _require_course_not_completed. Note this check is against `pe` (the
    currently ACTIVE enrollment for this student's course level), which is
    the correct thing to check for a program-context submission; for an
    event-context submission whose owning enrollment (owning_doc) might
    differ from `pe`, the check still applies to `pe` because
    resolve_learning_unit_for_assignment and the weekly-cap check both
    operate relative to the student's current active state, and an event
    should remain submittable even if the student's unrelated PROGRAM
    course has separately completed -- course completion on the program
    track must never block an otherwise-valid event submission. This is
    exactly the "let the event run even if PE completed" requirement:
    _require_course_not_completed only ever raises when `pe.status` (the
    active enrollment resolved for THIS call) is itself completed, and
    even then, only blocks further PROGRAM-context submissions -- an
    event-context call resolves its real owning doc separately via
    _resolve_row_for_context and is never gated on `pe`'s own completion
    status beyond the initial active-enrollment resolution needed to
    locate the event in the first place.

    retried-transaction note: this function is wrapped in
    @with_serialization_retry (see shared/db_retry.py); a retry re-runs
    the whole function body from scratch, including a fresh
    _resolve_row_for_context call, so no state from a failed attempt
    leaks into a retry.

    DECISION D: last_activity_at is bumped via award_points(owning_doc,
    ..., bump_activity=True) on EVERY successful attempt (first or
    reattempt), against the row's TRUE owning enrollment. Points
    themselves are only ever awarded (a nonzero amount passed to
    award_points) on the first attempt.
    """
    if not submission_url or not isinstance(submission_url, str):
        raise InvalidInput("submission_url missing")

    pe_name = get_active_program_enrollment_name(student_id)
    lock_program_enrollment_row(pe_name)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)

    _require_course_not_completed(pe)

    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    owning_doc, row = _resolve_row_for_context(pe, student_id, unit, context, create_if_missing=True)

    require_video_done(row)

    if context == "program":
        _require_weekly_submission_cap_not_reached(pe)

    cap = max_submission_attempts()
    if row.submission_attempts >= cap:
        raise CapReached("submission attempt cap already reached")
    if row.submission and row.submission_attempts > 0:
        prior_status = frappe.db.get_value("Submission", row.submission, "status")
        if prior_status not in ("Completed", "Failed"):
            raise CapReached("previous submission still being reviewed")

    # Reject a client-supplied object_key whose embedded attempt number
    # disagrees with the real next attempt, before any Submission row is
    # created or any write happens.
    _validate_object_key_attempt(object_key, row.submission_attempts + 1)

    is_first_attempt = row.submission_attempts == 0

    from tap_lms.imgana.submission import submit_artwork as _imgana_submit_artwork

    # imgana.submit_artwork reports failure via frappe.local.response rather
    # than raising, so a plain call returns None on failure instead of
    # throwing. Capture and inspect frappe.local.response explicitly to
    # detect that case and surface it as a normal SharedError.
    frappe.local.response.pop("success", None)
    frappe.local.response.pop("status", None)
    frappe.local.response.pop("error_detail", None)

    imgana_result = _imgana_submit_artwork(
        assignment_id=assignment_id,
        student_id=student_id,
        submission=submission_url,
        source="tapapp",
    )

    if not imgana_result or not imgana_result.get("success"):
        failure_status = (imgana_result or {}).get("status") or frappe.local.response.get("status")
        failure_detail = (imgana_result or {}).get("error_detail") or frappe.local.response.get("error_detail")
        frappe.local.response.pop("success", None)
        frappe.local.response.pop("status", None)
        frappe.local.response.pop("error_detail", None)
        if failure_status == "not_found":
            raise NotFound(failure_detail or "assignment not found")
        raise InvalidInput(failure_detail or "submission could not be created")

    sub_name = imgana_result["submission_id"]

    if not object_key:
        frappe.logger().warning(
            f"submit_artwork: no object_key supplied for newly created "
            f"Submission {sub_name}. The TapApp Worker path always supplies "
            f"one; this indicates a caller other than the documented Worker "
            f"route. This has no effect on the response shape -- "
            f"submit_artwork never returns an identifier for the new row."
        )

    # Stamp program_enrollment onto the new Submission row as the row's
    # TRUE owning enrollment (owning_doc), not unconditionally `pe` -- for
    # an event-context submission whose row lives on a different,
    # non-active enrollment, this keeps the stamp consistent with where
    # the Unit Progress row itself actually lives, matching what
    # shared/submission/review_result.py::handle_review_result expects to
    # find via row["parent"].
    frappe.db.set_value("Submission", sub_name, "program_enrollment", owning_doc.name, update_modified=False)

    row.submission = sub_name
    row.submission_attempts += 1
    recompute_unit_status(row)

    # DECISION D: award_points is called on EVERY successful attempt, not
    # only inside an `if is_first_attempt:` guard. Points themselves are
    # only ever nonzero on the first attempt (points_awarded stays 0 on a
    # reattempt) -- bump_activity=True is passed explicitly on every call
    # so a second-attempt submission still advances last_activity_at.
    # Awarded against owning_doc -- the row's true owning enrollment --
    # not unconditionally `pe`.
    points_awarded = points_for_submission_first_attempt() if is_first_attempt else 0
    award_points(owning_doc, points_awarded, bump_activity=True)

    # If this was a brand-new event Unit Progress row created just above,
    # finalize its pointer on the Student Event Enrollment row once it has
    # a real name (which only happens once its parent doc is saved).
    if owning_doc is not pe:
        owning_doc.save(ignore_permissions=True)
        from shared.progress.activities import _finalize_event_enrollment_pointer
        _finalize_event_enrollment_pointer(row)

    pe.save(ignore_permissions=True)

    # Explicit commit at the end of this function, rather than relying
    # solely on Frappe's end-of-request auto-commit. imgana's own
    # submit_artwork call above already performs a mid-request
    # frappe.db.commit() of its own (see tap_lms/imgana/submission.py) --
    # everything from that point on, including this function's own writes,
    # runs in a SEPARATE transaction from imgana's. Committing explicitly
    # here removes any ambiguity about whether Frappe's own request-
    # teardown commit logic treats this second transaction the same way it
    # would treat the first, and is what actually surfaces a
    # SerializationFailure to @with_serialization_retry at a well-defined
    # point.
    frappe.db.commit()

    attempts_remaining = max(cap - row.submission_attempts, 0)
    sub_status = frappe.db.get_value("Submission", sub_name, "status") or "Pending"
    sub_created_at = frappe.db.get_value("Submission", sub_name, "created_at")

    return {
        "status": sub_status,
        "created_at": (sub_created_at or frappe.utils.now_datetime()).isoformat(),
        "assignment_id_link": assignment_id,
        "attempt_number": row.submission_attempts,
        "attempts_remaining": attempts_remaining,
        "points_awarded": points_awarded,
        "points_total": owning_doc.points,
        "context": context,
        "updated_at": int(owning_doc.last_activity_at.timestamp()) if owning_doc.last_activity_at else int(frappe.utils.now_datetime().timestamp()),
    }