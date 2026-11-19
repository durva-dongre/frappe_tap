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

SUBMISSION_ID -- RETURNED, UNDER THE KEY "submission_id" ONLY:

This function's response carries the Worker-shaped id for the newly
created row, parsed directly out of `object_key`
(shared.submission.object_naming.parse_object_key) -- with NO dependency
on imgana's async upload job having run yet. See
_resolve_submission_id_from_object_key's own docstring for the full
reasoning. The key is always "submission_id" -- never "name" or any other
spelling -- matching every other submission-shaped response in this API
(submission.list, submission.get, progress.sync, progress.last_submission).

ASSIGNMENT -> LEARNING UNIT RESOLUTION (fixed -- see
resolve_learning_unit_for_assignment below):

An Assignment can be attached to a LearningUnit in TWO different, both
schema-legal ways:

  1. Directly, as a row in LearningUnit.content_items
     (UnitContentItem.content_type == 'Assignment').
  2. Indirectly, as a row in some VideoClass's own `assessments` child
     table (AssessmentList.assessment_type == 'Assignment'), where that
     VideoClass is itself attached to the unit via a UnitContentItem row
     (content_type == 'VideoClass'). This is the shape
     export_lms_courses.py's own export_video() already walks
     (video.assessments -> assignment_names) when building the catalog
     JSON -- so it is a real, intentionally-supported attachment path, not
     an edge case.

resolve_learning_unit_for_assignment previously only ever checked path 1.
When an assignment used path 2 exclusively (no direct UnitContentItem row
at all), the direct-link query returned nothing, and the function fell
straight through to the vertical-based guess (any LearningUnit sharing the
assignment's own `vertical`, ordered by `modified DESC`) -- which has no
guarantee of landing on the unit this specific assignment actually belongs
to. In the reported case, this guess resolved to the WRONG unit (one whose
Unit Progress row had never been touched, so video_watched read as 0),
even though the student had genuinely watched the video for the unit the
assignment was actually attached to via path 2. check_attempt_cap and
submit_artwork then raised "video must be completed before submitting for
this unit" despite submit_video_watched having already succeeded against
the correct unit moments earlier.

The fix adds path 2 as an explicit, ordered middle step -- assignment_id
-> owning VideoClass (via AssessmentList) -> owning LearningUnit (via
UnitContentItem) -- checked AFTER the direct link and BEFORE the
event-enrollment / vertical-guess fallbacks. The vertical-guess fallback
itself is unchanged and remains a genuine last resort, now only ever
reached when an assignment has NEITHER a direct UnitContentItem row NOR a
VideoClass.assessments row pointing at it.

EVENT-TRACK ROW RESOLUTION (fixed): previously, both check_attempt_cap and
submit_artwork resolved their Unit Progress row ONLY against the
currently-ACTIVE ProgramEnrollment's own unit_progress child table
(_find_existing_unit_progress_row / get_or_create_unit_progress_row called
directly on `pe`), with no special handling for context == "event". This
directly contradicted the invariant shared/progress/activities.py
documents and enforces for its own event-context writes: "a Unit Progress
row is immutably tied to whichever ProgramEnrollment it was created
under, never to whatever enrollment happens to be active right now."

Both check_attempt_cap and submit_artwork now call
shared.progress.activities._resolve_event_unit_progress_row for
context == "event", exactly as activities.py's own submit_video_watched/
submit_quiz do, so all three event-context write paths (video, quiz,
submission) and the one event-context read path (check_attempt_cap)
resolve to the exact same row, anchored to whichever enrollment actually
owns it -- never to whatever happens to be "active" at call time.

COMPLETED-COURSE WRITE GUARD -- PROGRAM CONTEXT ONLY (bugfix):
shared.enrollment.active_batch now resolves a "completed" ProgramEnrollment
for READS (so sync/profile keep working after a course finishes -- see
that module's docstring). Writing new PROGRAM-context submissions against
an already-completed course must still be rejected explicitly, rather than
silently reopened as a side effect of that read fix.

Previously, _require_course_not_completed(pe) was called unconditionally
in both check_attempt_cap and submit_artwork, regardless of `context`.
Because `pe` here is always the student's ACTIVE PROGRAM-track enrollment
(resolved via get_active_program_enrollment_name, which keys off
course_level, not off any particular event), an EVENT-context call for a
student whose unrelated program course happened to be "completed" was
incorrectly rejected too -- directly contradicting this module's own
documented intent ("an event should remain submittable even if the
student's unrelated PROGRAM course has separately completed").

The guard is now scoped: it only ever raises when context == "program".
An event-context call never has its event-row resolution or submission
gated on the active program enrollment's own completion status -- only
the program-context write path cares whether `pe.status == "completed"`.

WEEKLY SUBMISSION CAP: unchanged from before -- see
_require_weekly_submission_cap_not_reached's own docstring. Event-context
submissions are never subject to this cap (program-context only, per
submission_this_week's own doctype field description).

ATTEMPT-NUMBER INTEGRITY: unchanged -- see _validate_object_key_attempt.
Note: that function's cross-check is a defense-in-depth layer on top of
the Worker's own assertObjectKeyMatches; see
shared/submission/object_naming.py's OBJECT_KEY_RE for the related fix
that lets this check actually fire for assignment_ids containing a space
(previously it silently no-op'd for those -- see that module's docstring).

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
from shared.submission.object_naming import parse_object_key, resolve_wire_submission_id
from shared.db_retry import with_serialization_retry

# Narrow, DB-driver-level exception classes that genuinely indicate "this
# table/column doesn't exist" (a schema mismatch) -- as opposed to any other
# exception, which should propagate rather than be silently treated the same
# way. frappe.db exposes these as aliases of the underlying driver's
# exception types (psycopg2.errors.UndefinedTable / UndefinedColumn surface
# through frappe.db.ProgrammingError on Postgres).
_SCHEMA_MISMATCH_EXCEPTIONS = (frappe.db.InternalError, frappe.db.ProgrammingError)


def _resolve_unit_via_direct_content_item(assignment_id: str) -> str | None:
    """Path 1: a direct UnitContentItem row
    (content_type == 'Assignment', content == assignment_id).

    Runs inside a savepoint so a genuine schema-mismatch error (a missing
    table/column) degrades to the caller trying the next resolution path
    instead of aborting the whole surrounding transaction. Any OTHER kind
    of exception (a dropped connection, an unrelated serialization
    failure) is re-raised after the ROLLBACK TO SAVEPOINT, rather than
    silently swallowed.

    Returns the owning LearningUnit's name, or None if no such row
    exists.
    """
    try:
        frappe.db.sql("SAVEPOINT resolve_unit_direct_link")
        row = frappe.db.sql(
            """
            SELECT parent FROM "tabUnitContentItem"
            WHERE content_type = 'Assignment' AND content = %s
            LIMIT 1
            """,
            (assignment_id,),
        )
        frappe.db.sql("RELEASE SAVEPOINT resolve_unit_direct_link")
    except _SCHEMA_MISMATCH_EXCEPTIONS:
        frappe.db.sql("ROLLBACK TO SAVEPOINT resolve_unit_direct_link")
        frappe.logger().warning(
            "resolve_learning_unit_for_assignment: tabUnitContentItem direct-link "
            "lookup failed with a schema-mismatch error -- falling back to the "
            "video-assessment / event / vertical resolution paths",
            exc_info=True,
        )
        return None
    except Exception:
        frappe.db.sql("ROLLBACK TO SAVEPOINT resolve_unit_direct_link")
        frappe.logger().error(
            "resolve_learning_unit_for_assignment: tabUnitContentItem direct-link "
            "lookup failed with an unexpected (non-schema) error -- re-raising "
            "after rolling back to savepoint so the surrounding transaction is "
            "not left poisoned",
            exc_info=True,
        )
        raise

    return row[0][0] if row else None


def _resolve_unit_via_video_assessment(assignment_id: str) -> str | None:
    """Path 2: an INDIRECT attachment, via some VideoClass's own
    `assessments` child table (AssessmentList row with
    assessment_type == 'Assignment', assessment == assignment_id), where
    that VideoClass is itself attached to a unit via a UnitContentItem row
    (content_type == 'VideoClass', content == that video's name).

    This mirrors exactly what export_lms_courses.py's own export_video()
    already walks when building the catalog JSON (video.assessments ->
    assignment_names) -- it is a real, intentionally-supported attachment
    shape, not a workaround. An assignment configured this way has NO
    direct UnitContentItem row of its own at all, which is why
    _resolve_unit_via_direct_content_item alone was missing it entirely.

    Returns the owning LearningUnit's name, or None if this assignment
    has no VideoClass.assessments row, or that video itself isn't
    attached to any unit.
    """
    video_link = frappe.db.sql(
        """
        SELECT al.parent AS video_name
          FROM "tabAssessmentList" al
         WHERE al.assessment_type = 'Assignment'
           AND al.assessment = %s
         LIMIT 1
        """,
        (assignment_id,),
    )
    if not video_link:
        return None
    video_name = video_link[0][0]

    unit_row = frappe.db.sql(
        """
        SELECT uci.parent FROM "tabUnitContentItem" uci
        WHERE uci.content_type = 'VideoClass' AND uci.content = %s
        LIMIT 1
        """,
        (video_name,),
    )
    return unit_row[0][0] if unit_row else None


def _resolve_unit_via_event_enrollment(student_id: str) -> str | None:
    """Path 3a (event context only): the learning_unit of the student's
    currently active Event Campaign enrollment. Returns None if there is
    no active event enrollment."""
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
    return enrollment[0][0] if enrollment else None


def _resolve_unit_via_vertical_guess(assignment_id: str) -> str | None:
    """Path 3b (program context only) -- LAST-RESORT fallback. Picks ANY
    LearningUnit sharing the assignment's own `vertical`, ordered by
    `modified DESC`. This has no guarantee of landing on the unit this
    specific assignment actually belongs to -- it is only ever reached
    once paths 1 and 2 have both failed to find a real attachment, i.e.
    for an assignment with neither a direct UnitContentItem row nor a
    VideoClass.assessments row pointing at it.

    Raises NotFound if the assignment itself doesn't exist. Returns None
    (never raises) if the assignment exists but no LearningUnit shares
    its vertical -- the caller raises NotFound for that case so the
    "assignment doesn't exist" and "no matching unit" error messages stay
    distinct.
    """
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
    return unit[0][0] if unit else None


def resolve_learning_unit_for_assignment(assignment_id: str, context: str, student_id: str) -> str:
    """Resolves which LearningUnit an assignment_id belongs to, for cap
    checking and Unit Progress bookkeeping.

    Tries, in order:
      1. A direct UnitContentItem link
         (_resolve_unit_via_direct_content_item).
      2. An indirect link via a VideoClass's own `assessments` child table
         (_resolve_unit_via_video_assessment) -- see module docstring,
         "ASSIGNMENT -> LEARNING UNIT RESOLUTION", for why this path
         exists and what broke without it.
      3. Only once BOTH of the above have failed to find a real
         attachment:
           - event context: the student's active Event Campaign
             enrollment (_resolve_unit_via_event_enrollment). Raises
             NotFound if there is none.
           - program context: a vertical-based guess
             (_resolve_unit_via_vertical_guess) -- a genuine last resort
             with no uniqueness guarantee. Raises NotFound if the
             assignment doesn't exist, or if no LearningUnit shares its
             vertical at all.

    Raises NotFound if no resolution path produces a unit.
    """
    unit = _resolve_unit_via_direct_content_item(assignment_id)
    if unit:
        return unit

    unit = _resolve_unit_via_video_assessment(assignment_id)
    if unit:
        return unit

    if context == "event":
        unit = _resolve_unit_via_event_enrollment(student_id)
        if unit:
            return unit
        raise NotFound("no active event enrollment for this student")

    unit = _resolve_unit_via_vertical_guess(assignment_id)
    if not unit:
        raise NotFound("could not resolve a learning unit for this assignment")
    return unit


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


def _require_course_not_completed(pe, context: str) -> None:
    """Rejects a write against an already-completed ProgramEnrollment --
    PROGRAM CONTEXT ONLY.

    shared.enrollment.active_batch.get_active_program_enrollment_name now
    resolves a "completed" enrollment for READ paths (sync, profile) that
    previously broke entirely once a student's only enrollment finished --
    see that module's docstring. That fix is deliberately READ-only: it
    must not silently reopen check_attempt_cap / submit_artwork for a
    finished course.

    The guard only ever raises for context == "program". An event-context
    call never has its event-row resolution or submission gated on the
    active program enrollment's own completion status -- only the
    program-context write path cares whether `pe.status == "completed"`.
    """
    if context != "program":
        return
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
    _resolve_row_for_context below), which already performs the
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


def _resolve_submission_id_from_object_key(object_key: str | None, sub_name: str) -> str:
    """Returns the Worker-shaped submission_id embedded in object_key
    itself, parsed synchronously and immediately -- with NO dependency on
    imgana's async upload job having run yet.

    object_key is the exact value the Worker's own /submission/
    request_upload minted and the client's PUT already confirmed exists on
    GCS -- by the time this function runs, _validate_object_key_attempt has
    already confirmed its embedded attempt number matches reality, so the
    key is known-good.

    Falls back to resolve_wire_submission_id(sub_name) -- the same
    fallback every other read path in this API already uses, which itself
    falls back to the plain Frappe autoname if submission_url isn't
    populated yet -- for any caller that didn't supply an object_key, or
    supplied one that fails to parse. This never raises.
    """
    if object_key:
        try:
            return parse_object_key(object_key)["submission_id"]
        except InvalidInput:
            pass
    return resolve_wire_submission_id(sub_name)


def check_attempt_cap(student_id: str, assignment_id: str, context: str = "program") -> dict:
    """Reports the student's current attempt number and how many attempts
    remain for this assignment. Read-only: enforces the completed-course
    guard (program context only -- see _require_course_not_completed), the
    video prerequisite, the weekly submission cap (program context only),
    and the per-assignment attempt cap as checks only -- it does not create
    a Unit Progress row for program context (event context may create one
    on first-ever activity, per _resolve_row_for_context's own docstring)
    and does not save the ProgramEnrollment document.

    The unit this assignment belongs to is resolved via
    resolve_learning_unit_for_assignment, which now checks BOTH the direct
    UnitContentItem link AND the indirect VideoClass.assessments link
    before falling back to event/vertical resolution -- see that
    function's and this module's own docstring for why both links matter.

    For context == "event", the Unit Progress row is resolved via the
    SAME global, by-name lookup submit_artwork and activities.py's
    video/quiz writes use (see _resolve_row_for_context) -- previously
    this function only ever looked inside the currently-active
    enrollment's own unit_progress table, which could report a stale
    attempt_number: 1 for a student whose real event progress (and real
    attempt count) lived on a different, prior enrollment.

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

    COMPLETED COURSE (program context only): raises InvalidInput
    (error_code="course_completed") if pe.status == "completed" AND
    context == "program".

    This function is read-only (no writes, no row lock beyond the implicit
    read), so it is NOT wrapped in @with_serialization_retry -- there is no
    write here that a SerializationFailure could silently discard.
    """
    pe_name = get_active_program_enrollment_name(student_id)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)

    _require_course_not_completed(pe, context)

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
    """Re-checks the completed-course guard (program context only), attempt
    cap, weekly submission cap (program context only), and video
    prerequisite under a row lock, cross-checks object_key's own attempt
    number against reality, then hands off the actual Submission creation
    to imgana's submit_artwork pipeline (unmodified). submission_url is a
    plain, already-public URL the caller provides directly --
    tap_app/api/submission.py::submit_artwork is responsible for building
    this URL from the Worker's object_key before calling here.

    The unit this assignment belongs to is resolved via
    resolve_learning_unit_for_assignment -- see that function's and this
    module's own docstring for the direct-link / video-assessment-link /
    fallback resolution order.

    RESPONSE INCLUDES "submission_id": the Worker-shaped id, parsed
    directly out of object_key via _resolve_submission_id_from_object_key.
    The key is "submission_id" only -- never "name" or any other spelling
    -- matching every other submission-shaped response in this API.

    EVENT-TRACK ROW RESOLUTION: the Unit Progress row for
    context == "event" is resolved via the SAME global, by-name lookup
    (_resolve_row_for_context -> activities._resolve_event_unit_progress_row)
    that activities.py's own submit_video_watched/submit_quiz use, instead
    of always creating/reusing a row on the currently-active enrollment.
    This also means points/last_activity_at for an event submission are
    awarded against the row's true owning enrollment (owning_doc), not
    unconditionally against `pe` -- see award_points's call below.

    object_key's attempt segment is validated against
    row.submission_attempts + 1 (see _validate_object_key_attempt) BEFORE
    imgana is ever called, so a mismatched key can never create a
    Submission row.

    program_enrollment is stamped on the new Submission row as
    owning_doc.name (the row's TRUE owning enrollment -- `pe` for program
    context, or whatever enrollment actually owns the event row for event
    context), not unconditionally `pe.name`, now that the two can differ.

    COMPLETED COURSE (program context only): raises InvalidInput
    (error_code="course_completed") only when context == "program" AND
    pe.status == "completed". Event submissions are never gated on the
    active program enrollment's own completion status.

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

    _require_course_not_completed(pe, context)

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
            f"route. The response will fall back to resolve_wire_submission_id "
            f"for this submission's id, which may report the plain Frappe "
            f"autoname instead of a Worker-shaped id until the async upload "
            f"job populates submission_url."
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

    # Resolved synchronously from object_key -- see
    # _resolve_submission_id_from_object_key's own docstring. Falls back
    # to resolve_wire_submission_id(sub_name) (the same fallback every
    # other read path already uses) if object_key is missing or doesn't
    # parse, so this never raises and never blocks the response.
    submission_id = _resolve_submission_id_from_object_key(object_key, sub_name)

    return {
        "submission_id": submission_id,
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