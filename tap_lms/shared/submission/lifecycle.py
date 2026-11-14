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
the WhatsApp channel (RabbitMQ enqueue, Gemini/AI feedback generation,
Glific flow delivery). imgana's function takes a plain, already-public
submission URL and handles its own media detection; this module is
responsible for everything imgana's function doesn't do: attempt-cap
enforcement, the weekly submission-cap enforcement (new, see below), the
video prerequisite gate, the Unit Progress row write (submission link,
attempt count, unit_status recompute), the first-attempt points award, AND
-- critically -- making the canonical submission_id actually line up
between the Worker's object key and what this call's own response reports.

Worker route wiring: tap_app/api/submission.py::submit_artwork is the only
whitelisted entrypoint the Worker calls for this. Do not point the Worker
directly at tap_lms.imgana.submission.submit_artwork -- it has no
attempt-cap or Unit Progress awareness of its own, so calling it directly
would skip the cap check and leave Unit Progress (and therefore
unit_status/points/resume state) never updated.

CANONICAL submission_id -- NO SCHEMA CHANGE, NO IMGANA CHANGE:

There is deliberately no `worker_submission_id` column on the Submission
doctype, and tap_lms/imgana/submission.py is never modified by this module
or any other part of the TapApp path -- imgana creates the row under its
OWN Frappe autoname (e.g. "SUB-0503"), exactly as it always has, and this
module never asks it to do otherwise.

Instead, the Worker-minted id embedded in object_key is recovered PURELY BY
COMPUTATION, with no new field and no extra write:

  - For THIS function's own immediate response (the one place a client sees
    a submission_id synchronously, right at creation time), the id is
    parsed straight out of the in-memory `object_key` this call was already
    given -- see shared.submission.object_naming.parse_object_key. This is
    the only correct source at this exact moment: imgana's
    process_submission_async (which is what actually populates the row's
    own `submission_url` field with the tapapp object's GCS URL) runs
    AFTER this function has already returned (it's queued
    `enqueue_after_commit=True` inside imgana.submit_artwork), so
    submission_doc.submission_url is still None when control returns here.

  - For every LATER read of this same row (sync, list, get, gallery
    promotion), shared.submission.object_naming.resolve_wire_submission_id
    recovers the exact same id from submission_url instead, once imgana's
    async job has populated it -- see that module's docstring for the full
    reasoning, including why a still-Pending row legitimately falls back to
    the Frappe autoname there too.

Neither path ever writes a new field anywhere. A malformed/missing
object_key on THIS call is logged and this response alone falls back to the
Frappe autoname; the Submission row itself is still created successfully
either way.

resolve_learning_unit_for_assignment's primary lookup queries
tabUnitContentItem.content_type / tabUnitContentItem.content -- the actual
schema for that doctype, the same shape every other resolver in this
codebase queries against (e.g. shared/progress/activities.py::
resolve_video_id_for_unit / resolve_quiz_id_for_unit). That query is
wrapped in a savepoint (release/rollback) as defense in depth: because
Postgres (unlike MySQL) aborts the entire transaction on any SQL error
until an explicit ROLLBACK, a savepoint here means a future schema mismatch
on this query degrades to the documented fallback paths (and ultimately
NOT_FOUND) instead of poisoning the whole surrounding transaction -- every
later query in the same request, including the caller's own error-logging
write, would otherwise fail with "current transaction is aborted" until the
request unwound.

WEEKLY SUBMISSION CAP (new, 2026-11-14):

check_attempt_cap and submit_artwork now both check
ProgramEnrollment.submission_this_week against
shared.progress.rewards.max_submissions_per_week() BEFORE enforcing the
existing per-assignment attempt cap. This is a separate, weekly,
cross-assignment cap (distinct from max_submission_attempts, which caps
attempts on one specific assignment) -- a student who has exhausted their
weekly submission budget is rejected with CapReached (CONFLICT) regardless
of how many attempts they have left on this particular assignment.

submission_this_week itself is NOT incremented anywhere in this file.
Despite being checked here (at submit/cap-check time), the counter's own
increment happens exactly once per GRADED REVIEW OUTCOME, in
shared/submission/review_result.py::handle_review_result -- not at submit
time. This means the cap, as checked here, reflects how many of this
student's submissions have already been GRADED this week, not how many
attempts they have SUBMITTED this week (a submission sitting in
Pending/Processing does not yet count against the cap). This is a
deliberate design point, explicitly directed: "increment submission this
week after every type of review not just normal review" -- i.e. the gate
and the counter are intentionally decoupled from submit-time, matching
every other weekly/cap-style counter's semantics of "count finished work,"
not "count attempts in flight."

DECISION D (last_activity_at on every attempt, 2026-11-14): award_points
(shared/progress/rewards.py) unconditionally bumps enrollment_doc.
last_activity_at every time it's called, regardless of the `amount`
passed in. Previously, award_points was only CALLED inside the
`if is_first_attempt:` block, which meant last_activity_at (and, by
implication, anything gated on it, such as /progress/sync's "has anything
changed" check) never advanced on a second submission attempt. The fix is
to call award_points on every successful attempt, passing 0 as the amount
on a non-first attempt (which award_points already handles correctly --
`if amount:` guards the actual points increment, but last_activity_at is
bumped unconditionally at the top of that function, outside that guard).
This achieves "bump last_activity_at on every attempt, award points only
on the first attempt" without duplicating any bump logic here -- the
existing function's own unconditional bump is reused for every attempt,
and this file's own points-amount logic (points_for_submission_first_attempt()
only on is_first_attempt, else 0) is unchanged apart from no longer being
wrapped in a separate attempt-bump branch.
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


def resolve_learning_unit_for_assignment(assignment_id: str, context: str, student_id: str) -> str:
    """Resolves which LearningUnit an assignment_id belongs to, for cap
    checking and Unit Progress bookkeeping. Tries a direct UnitContentItem
    link first (content_type == 'Assignment', content == assignment_id --
    see module docstring for the schema this relies on), then falls back
    to event/assignment-vertical resolution. The savepoint around the
    primary query means a schema mismatch here degrades to the fallback
    paths below (and ultimately NOT_FOUND, a documented error) instead of
    aborting the whole surrounding transaction.
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
    except Exception:
        frappe.db.sql("ROLLBACK TO SAVEPOINT resolve_unit_for_assignment")
        frappe.logger().warning(
            "resolve_learning_unit_for_assignment: tabUnitContentItem lookup "
            "failed -- falling back to event/assignment resolution",
            exc_info=True,
        )
        row = None

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


def _require_video_done(unit_progress_row) -> None:
    """Within-unit guard: video must be watched before any submission, in
    both program and event contexts. Quiz is independent of submission --
    a student can submit before, after, or without ever taking the quiz."""
    if not unit_progress_row.video_watched:
        raise InvalidInput("video must be completed before submitting for this unit")


def _require_weekly_submission_cap_not_reached(pe) -> None:
    """Program-context weekly cap: rejects with CapReached (CONFLICT) if
    pe.submission_this_week is already at or beyond
    shared.progress.rewards.max_submissions_per_week(). See module
    docstring for the full reasoning, including why this counter is
    incremented elsewhere (review_result.py) and not here -- this
    function only ever READS submission_this_week, never increments it.

    Deliberately program-context only, matching submission_this_week's
    own doctype-field description ("Program-context only") -- an
    event-context submission is never subject to this cap. Callers
    (check_attempt_cap, submit_artwork) are both already program/event-
    aware at the call site; this helper itself does not take a context
    parameter and must only be called from a program-context code path.
    """
    cap = max_submissions_per_week()
    current = pe.submission_this_week or 0
    if current >= cap:
        raise CapReached("weekly submission cap already reached")


def check_attempt_cap(student_id: str, assignment_id: str, context: str = "program") -> dict:
    """Reports the student's current attempt number and how many attempts
    remain for this assignment, without creating anything. Also enforces
    the video prerequisite, the weekly submission cap (program context
    only, new), and the per-assignment attempt cap itself.

    attempts_remaining is computed against the UPCOMING attempt number
    (row.submission_attempts + 1) -- matching submit_artwork's own
    post-increment computation for the same (student, assignment, context)
    pair -- instead of against the pre-increment count still sitting in
    row.submission_attempts, so both functions agree on attempts_remaining
    for the same attempt (see Reference §4.1).
    """
    pe_name = get_active_program_enrollment_name(student_id)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)
    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = get_or_create_unit_progress_row(pe, unit, context)

    _require_video_done(row)

    if context == "program":
        _require_weekly_submission_cap_not_reached(pe)

    cap = max_submission_attempts()
    if row.submission_attempts >= cap:
        raise CapReached("submission attempt cap already reached")
    if row.submission and row.submission_attempts > 0:
        sub_status = frappe.db.get_value("Submission", row.submission, "status")
        if sub_status not in ("Completed", "Failed"):
            raise CapReached("previous submission still being reviewed")

    attempt_number = row.submission_attempts + 1
    attempts_remaining = max(cap - attempt_number, 0)

    pe.save(ignore_permissions=True)

    return {"attempt_number": attempt_number, "attempts_remaining": attempts_remaining}


def submit_artwork(student_id: str, assignment_id: str, submission_url: str, object_key: str | None = None,
                    context: str = "program") -> dict:
    """Re-checks the attempt cap, weekly submission cap (program context
    only, new), and video prerequisite under a row lock, then hands off
    the actual Submission creation to imgana's submit_artwork pipeline
    (unmodified). submission_url is a plain, already-public URL the
    caller provides directly -- not signed or validated against any
    object-key shape here; it is passed straight through to imgana, which
    handles its own media-type detection and storage for the "tapapp"
    source. tap_app/api/submission.py::submit_artwork is responsible for
    building this URL from the Worker's object_key before calling here.

    object_key is the SAME Worker-issued key submission_url was built from
    (tap_app/api/submission.py passes both through unchanged). It is used
    here, after imgana creates the row, purely to compute THIS response's
    own submission_id -- never written to the database (there is no column
    to write it to, and none will be added). See module docstring for the
    full reasoning, including why this in-memory recovery -- rather than
    reading the row's own submission_url -- is the only correct source at
    this point in the request.

    object_key is optional only so this function's signature stays backward
    compatible with any caller that has no key to pass (none exist in this
    codebase today; the TapApp wrapper always passes one) -- submission_id
    then falls back to the Frappe autoname (sub_name) in that case, exactly
    as it would for a row whose submission_url hasn't been populated yet.

    Returns the created submission's id as `submission_id` -- the Worker-
    minted id recovered from object_key when available, else the Frappe
    autoname. This is the ONLY identifier key in this response; `name` is
    deliberately never returned as a second key alongside it, so there is
    exactly one field for client code to read for "which submission is
    this."

    DECISION D: last_activity_at is now bumped via award_points(pe, ...)
    on EVERY successful attempt (first or reattempt), not only on the
    first attempt -- see module docstring for the full reasoning. points
    are still only ever awarded (a nonzero amount passed to award_points)
    on the first attempt; award_points itself still unconditionally bumps
    last_activity_at regardless of whether the amount is 0 or positive.
    """
    if not submission_url or not isinstance(submission_url, str):
        raise InvalidInput("submission_url missing")

    pe_name = get_active_program_enrollment_name(student_id)
    lock_program_enrollment_row(pe_name)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)

    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = get_or_create_unit_progress_row(pe, unit, context)

    _require_video_done(row)

    if context == "program":
        _require_weekly_submission_cap_not_reached(pe)

    cap = max_submission_attempts()
    if row.submission_attempts >= cap:
        raise CapReached("submission attempt cap already reached")
    if row.submission and row.submission_attempts > 0:
        prior_status = frappe.db.get_value("Submission", row.submission, "status")
        if prior_status not in ("Completed", "Failed"):
            raise CapReached("previous submission still being reviewed")

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

    # ------------------------------------------------------------------
    # Canonical submission_id for THIS response only -- no DB write, no
    # schema change, no imgana change. Recovered from the in-memory
    # object_key already on hand, because imgana's async
    # process_submission_async (which populates submission_doc.
    # submission_url) runs only AFTER this function returns
    # (enqueue_after_commit=True) -- submission_url is still None right now,
    # so it is not a usable source for THIS particular response. Every later
    # read of this same row (sync/list/get/gallery) instead recovers the id
    # from submission_url once that async job has run -- see
    # shared.submission.object_naming.resolve_wire_submission_id.
    # ------------------------------------------------------------------
    worker_submission_id: str | None = None
    if object_key:
        try:
            parsed = parse_object_key(object_key)
            worker_submission_id = parsed["submission_id"]
        except InvalidInput:
            frappe.logger().warning(
                f"submit_artwork: object_key={object_key!r} for newly created "
                f"Submission {sub_name} does not match the expected "
                f"tapapp/{{assignment_id}}/{{student_id}}/{{submission_id}}-"
                f"{{attempt}}.{{ext}} shape -- this response's submission_id "
                f"will fall back to the Frappe autoname. The Submission row "
                f"itself was created successfully and is not affected; a "
                f"later read of this same submission (sync/list/get) will "
                f"independently try to recover the id from submission_url "
                f"once it is populated."
            )
    else:
        frappe.logger().warning(
            f"submit_artwork: no object_key supplied for newly created "
            f"Submission {sub_name} -- this response's submission_id will "
            f"fall back to the Frappe autoname. The TapApp Worker path "
            f"always supplies one; this indicates a caller other than the "
            f"documented Worker route."
        )

    # The canonical identifier returned to every caller (Worker included)
    # is the Worker-minted id when we were able to recover one from
    # object_key, else the Frappe autoname -- never both, and never a
    # separate `name` key.
    canonical_submission_id = worker_submission_id or sub_name

    row.submission = sub_name
    row.submission_attempts += 1
    recompute_unit_status(row)

    # DECISION D: award_points is now called on EVERY successful attempt,
    # not only inside an `if is_first_attempt:` guard. Points themselves
    # are only ever nonzero on the first attempt (points_awarded stays 0
    # on a reattempt, exactly as before) -- but award_points's own
    # unconditional last_activity_at bump (shared/progress/rewards.py)
    # now fires every time, which is the whole point of this change: a
    # second-attempt submission must still advance last_activity_at so
    # /progress/sync's "has anything changed" check sees it.
    points_awarded = points_for_submission_first_attempt() if is_first_attempt else 0
    award_points(pe, points_awarded)

    pe.save(ignore_permissions=True)

    attempts_remaining = max(cap - row.submission_attempts, 0)
    sub_status = frappe.db.get_value("Submission", sub_name, "status") or "Pending"
    sub_created_at = frappe.db.get_value("Submission", sub_name, "created_at")

    return {
        "submission_id": canonical_submission_id,
        "status": sub_status,
        "created_at": (sub_created_at or frappe.utils.now_datetime()).isoformat(),
        "assignment_id_link": assignment_id,
        "attempt_number": row.submission_attempts,
        "attempts_remaining": attempts_remaining,
        "points_awarded": points_awarded,
        "points_total": pe.points,
        "context": context,
        "updated_at": int(pe.last_activity_at.timestamp()) if pe.last_activity_at else int(frappe.utils.now_datetime().timestamp()),
    }