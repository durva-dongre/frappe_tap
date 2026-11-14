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
(see BUGFIX below) stamping program_enrollment onto the new row.

Worker route wiring: tap_app/api/submission.py::submit_artwork is the only
whitelisted entrypoint the Worker calls for this. Do not point the Worker
directly at tap_lms.imgana.submission.submit_artwork -- it has no
attempt-cap or Unit Progress awareness of its own.

SUBMISSION_ID -- NOT RETURNED BY submit_artwork:

submit_artwork's own response does not carry a submission_id field at all.
imgana's own async job -- which is what actually populates the row's
submission_url, the only place the Worker-minted id is later recoverable
from -- runs AFTER this function returns. A client that needs a
submission's id/state reads it from /progress/sync or
/progress/last_submission instead, both of which resolve the row
themselves (never from a client-supplied id).

BUGFIX -- program_enrollment is now stamped on the newly created
Submission row, immediately after imgana reports success:

tap_lms.imgana.submission.submit_artwork (and the _create_submission
helper it calls) never sets Submission.program_enrollment -- it's shared
with the WhatsApp channel, which has no ProgramEnrollment concept at all,
so that field is simply never in its write list. Previously nothing on
the TapApp side corrected this either, so every Submission row created
through this path had program_enrollment = NULL forever.

This mattered because shared/profile/sync.py::_find_last_submission_row
filters `WHERE program_enrollment = program_enrollment_name` when looking
for a student's most recently updated submission to report in
/progress/sync and /progress/last_submission. A submission with
program_enrollment = NULL can never match that filter, no matter how
recently it was created or graded -- it is permanently invisible to both
of those endpoints. It also meant
shared/submission/review_result.py::handle_review_result's own fallback
(`row.get("parent") if row else None) or submission_doc.program_enrollment`)
could never fall back to anything useful for a row with no resolvable Unit
Progress row, since submission_doc.program_enrollment was always None too.

Fix: this module -- which is the one place in the TapApp-facing call chain
that actually holds a loaded `pe` (the active ProgramEnrollment) alongside
the newly created submission's name -- now writes
Submission.program_enrollment = pe.name directly, via a minimal
frappe.db.set_value call, immediately after imgana confirms success and
before returning. No change to imgana itself is needed or made; imgana
remains exactly as it is, shared unmodified with the WhatsApp channel.

resolve_learning_unit_for_assignment's primary lookup queries
tabUnitContentItem.content_type / tabUnitContentItem.content. That query
is wrapped in a savepoint (release/rollback) as defense in depth: because
Postgres (unlike MySQL) aborts the entire transaction on any SQL error
until an explicit ROLLBACK, a savepoint here means a future schema
mismatch on this query degrades to the documented fallback paths (and
ultimately NOT_FOUND) instead of poisoning the whole surrounding
transaction. The savepoint's except clause narrows to
frappe.db.InternalError / frappe.db.ProgrammingError (the actual
DB-driver exception classes for a schema mismatch) and re-raises anything
else after still issuing the ROLLBACK TO SAVEPOINT, so the transaction is
never left poisoned either way.

WEEKLY SUBMISSION CAP:

Both check_attempt_cap and submit_artwork check
ProgramEnrollment.submission_this_week against
shared.progress.rewards.max_submissions_per_week() BEFORE enforcing the
existing per-assignment attempt cap. This is a separate, weekly,
cross-assignment cap (distinct from max_submission_attempts, which caps
attempts on one specific assignment) -- a student who has exhausted their
weekly submission budget is rejected with CapReached (CONFLICT) regardless
of how many attempts remain on this particular assignment. Checking this
in check_attempt_cap too (not just submit_artwork) means a student at the
weekly cap never gets issued a signed upload URL in the first place --
without this check here, the Worker would sign an upload, the student
would spend time/bandwidth uploading, and only then discover via
submit_artwork that the attempt was rejected.

submission_this_week itself is NOT incremented anywhere in this file. Its
increment happens exactly once per GRADED REVIEW OUTCOME, in
shared/submission/review_result.py::handle_review_result -- not at submit
time.

check_attempt_cap has no write side effect: get_or_create_unit_progress_row
is never called here (unlike submit_artwork), so a client polling this
endpoint before the student has decided to submit anything can never
materialize an empty, "Not Started" Unit Progress row for a unit the
student hasn't actually engaged with. If no row exists yet, attempt_number
is reported as 1 without writing anything to the database.

ATTEMPT-NUMBER INTEGRITY: Unit Progress.submission_attempts is a plain Int
column with no doctype-level enforcement of its own -- the Worker's own
check on object_key (assertObjectKeyMatches) only confirms the key is
internally self-consistent with itself, never that its embedded "attempt"
segment actually matches what Frappe believes the next attempt number is.
submit_artwork therefore re-derives the real next attempt number
(row.submission_attempts + 1) and rejects a client-supplied object_key
whose own attempt segment disagrees with it, BEFORE calling into imgana --
so a mismatched key can never create a Submission row, and R2/gallery
storage can never diverge from Frappe's own attempt count.

DECISION D (last_activity_at on every attempt): award_points
(shared/progress/rewards.py) bumps enrollment_doc.last_activity_at when
bump_activity=True. submit_artwork calls award_points on every successful
attempt (first or reattempt), passing 0 as the amount on a non-first
attempt and bump_activity=True explicitly on every call -- this achieves
"bump last_activity_at on every attempt, award points only on the first
attempt."
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
    have left." Returns None if no such row exists yet."""
    rows = getattr(parent_doc, "unit_progress") or []
    matches = [r for r in rows if r.learning_unit == learning_unit and r.unit_type == unit_type]
    if len(matches) > 1:
        raise InvalidInput(
            f"data integrity error: multiple Unit Progress rows for "
            f"(learning_unit={learning_unit}, unit_type={unit_type})"
        )
    return matches[0] if matches else None


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
    remain for this assignment. Read-only: enforces the video prerequisite,
    the weekly submission cap (program context only), and the
    per-assignment attempt cap as checks only -- it does not create a Unit
    Progress row or save the ProgramEnrollment document.

    If no Unit Progress row exists yet for this (student, unit, context),
    the video-prerequisite check still applies (a brand-new unit has
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
    """
    pe_name = get_active_program_enrollment_name(student_id)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)
    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = _find_existing_unit_progress_row(pe, unit, context)

    # A never-started unit has no video_watched yet -- require_video_done
    # needs an object with a `.video_watched` attribute, so build a minimal
    # stand-in rather than persisting a real row just to check this.
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


def submit_artwork(student_id: str, assignment_id: str, submission_url: str, object_key: str | None = None,
                    context: str = "program") -> dict:
    """Re-checks the attempt cap, weekly submission cap (program context
    only), and video prerequisite under a row lock, cross-checks
    object_key's own attempt number against reality, then hands off the
    actual Submission creation to imgana's submit_artwork pipeline
    (unmodified). submission_url is a plain, already-public URL the caller
    provides directly -- tap_app/api/submission.py::submit_artwork is
    responsible for building this URL from the Worker's object_key before
    calling here.

    object_key's attempt segment is validated against
    row.submission_attempts + 1 (see _validate_object_key_attempt) BEFORE
    imgana is ever called, so a mismatched key can never create a
    Submission row. Beyond that cross-check, object_key is used here ONLY
    to confirm a caller supplied one (logging a warning if not) -- it is
    NOT used to compute an identifier for the response. submit_artwork's
    response carries no submission_id at all; a client reads a
    submission's id/state from /progress/sync or /progress/last_submission
    instead.

    BUGFIX: immediately after imgana creates the Submission row, this
    function stamps Submission.program_enrollment = pe.name directly, via
    a minimal frappe.db.set_value call. imgana's own pipeline is shared
    with the WhatsApp channel, which has no ProgramEnrollment concept at
    all, so it never sets this field itself -- this module is the one
    place in the TapApp-facing call chain that actually holds both `pe`
    and the newly created submission's name at the same time, so it's this
    function's responsibility to make the connection. Without this write,
    the row is permanently invisible to
    shared/profile/sync.py::_find_last_submission_row, which filters on
    program_enrollment = <active enrollment name> -- see module docstring
    for the full reasoning. update_modified=False is used deliberately:
    this is an immediate, same-transaction correction of the row imgana
    just inserted, not a later edit, so it must not shift `modified` past
    what imgana's own insert set -- that timestamp is what
    _find_last_submission_row's own "ORDER BY modified desc" and
    tap_app/api/submission.py::_resolve_updated_at_epoch both rely on as
    the row's true "last changed" signal.

    DECISION D: last_activity_at is bumped via award_points(pe, ...,
    bump_activity=True) on EVERY successful attempt (first or reattempt),
    not only on the first attempt. Points themselves are only ever awarded
    (a nonzero amount passed to award_points) on the first attempt.
    """
    if not submission_url or not isinstance(submission_url, str):
        raise InvalidInput("submission_url missing")

    pe_name = get_active_program_enrollment_name(student_id)
    lock_program_enrollment_row(pe_name)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)

    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = get_or_create_unit_progress_row(pe, unit, context)

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

    # BUGFIX: stamp program_enrollment onto the new Submission row -- see
    # module docstring and this function's own docstring above for the
    # full reasoning. This is the one write that was previously missing
    # end-to-end, since imgana's own _create_submission never populates
    # this field (it has no ProgramEnrollment concept at all).
    frappe.db.set_value("Submission", sub_name, "program_enrollment", pe.name, update_modified=False)

    row.submission = sub_name
    row.submission_attempts += 1
    recompute_unit_status(row)

    # DECISION D: award_points is called on EVERY successful attempt, not
    # only inside an `if is_first_attempt:` guard. Points themselves are
    # only ever nonzero on the first attempt (points_awarded stays 0 on a
    # reattempt) -- bump_activity=True is passed explicitly on every call
    # so a second-attempt submission still advances last_activity_at.
    points_awarded = points_for_submission_first_attempt() if is_first_attempt else 0
    award_points(pe, points_awarded, bump_activity=True)

    pe.save(ignore_permissions=True)

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
        "points_total": pe.points,
        "context": context,
        # BUGFIX: same None-safety as tap_app/api/progress.py's
        # _resolve_updated_at -- pe.last_activity_at is normally set by the
        # award_points(..., bump_activity=True) call just above, but stays
        # defensive here in case that ever changes.
        "updated_at": int(pe.last_activity_at.timestamp()) if pe.last_activity_at else int(frappe.utils.now_datetime().timestamp()),
    }