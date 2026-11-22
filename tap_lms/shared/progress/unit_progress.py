"""
shared/progress/unit_progress.py

Generic helpers around a "Unit Progress" child table living on some parent
enrollment-shaped document (ProgramEnrollment.unit_progress). Any app with
a similar (student, unit, track) -> {video, quiz, submission} progress
shape can reuse this unchanged, as long as its child table has the same
field names (learning_unit, unit_type, video_watched, submission,
submission_attempts, quiz_json, unit_status, completed_at).

Every mutating path across every app goes through
get_or_create_unit_progress_row so "exactly one row per (learning_unit,
unit_type)" is enforced in exactly one place.

A Unit Progress row is immutably tied to whichever ProgramEnrollment it
was created under -- it is NOT guaranteed to live under whatever
enrollment is currently "active" for a student (an enrollment can be
renewed/replaced while an old submission's or old event's progress row
still points at the previous one). find_unit_progress_row_for_submission
and find_unit_progress_row_by_name_global below are the two sanctioned
ways to look up a Unit Progress row without depending on "the active
enrollment" being the right scope -- they query the child table directly,
by submission or by the row's own global `name`, the same way
shared/jobs/event_maintenance.py does it. New code should prefer these
two over "load active enrollment, then search its rows" whenever the row
being searched for might not belong to the student's *current* active
enrollment.

resolve_last_activity_type is the single entrypoint for "what did this
student last do" across both tracks. Program context is safe to read
straight off the active ProgramEnrollment's own unit_progress table
because shared.enrollment.enrollment.create_enrollment guarantees exactly
one ProgramEnrollment per (student, course_level) for life -- see that
module's docstring. Event context is NOT safe to read that way, for the
same reason find_unit_progress_row_by_name_global exists: an event's Unit
Progress row can live on a ProgramEnrollment that is no longer the
student's active one. resolve_last_activity_type's event branch mirrors
exactly what shared.events.enrollment.is_enrolled already does to resolve
that row correctly, so both reads agree.

COMPLETION SIGNAL
------------------
recompute_unit_status / recompute_unit_status_by_name return a dict, not
a bare string: {"status": <string>, "just_completed": <bool>}, where
just_completed is True iff THIS call is what flipped the row from some
other status to "Completed" (i.e. the row's status was NOT already
"Completed" before this call, and IS "Completed" after it).

Every existing caller that treats the return value reads result["status"].
There are exactly two such callers in this codebase:
  - shared/progress/activities.py (submit_video_watched, submit_quiz) --
    calls the doc-based recompute_unit_status(row).
  - shared/submission/review_result.py (handle_review_result) -- calls
    the by-name recompute_unit_status_by_name(name).

just_completed is the one signal shared/enrollment/unit_rotation.py's
is_course_complete, and shared/enrollment/enrollment.py's
mark_course_completed, are gated on: a caller only bothers checking
is_course_complete/calling mark_course_completed when just_completed is
True for this call -- there is no point re-checking course completion on
every single activity call when this particular call didn't even
complete its own unit.

CONCURRENCY
------------
recompute_unit_status_by_name performs its read, decide, and write all
under a `SELECT ... FOR UPDATE` row lock taken at the top of the
function, releasing it only when the function returns (the lock is held
for the remainder of the current transaction, same as every other locked
read-modify-write in this codebase, e.g. shared/submission/locks.py).
This is what makes just_completed's "exactly one caller sees True for a
given completion" guarantee actually hold under concurrency: two
concurrent callers touching the same Unit Progress row at nearly the same
time (e.g. a video-watch call and the async review_result.py grading
callback landing moments apart) cannot both observe "not yet Completed"
and both independently trigger mark_course_completed / reward logic for
what should be a single, one-time completion event.

recompute_unit_status (the doc-based, in-memory variant used by
activities.py, which is always called from inside a request that is
already about to save the owning ProgramEnrollment document) does not
take its own explicit row lock, because activities.py's call sites
already run under `with_serialization_retry` one level up (via
award_points's callers) for the *document* save, and -- more
importantly -- a brand-new/not-yet-persisted child row mutated purely in
memory has no DB row to lock yet in the general case. Call sites that
need the same just_completed exactly-once guarantee across genuinely
concurrent writers for the *doc-based* path should serialize at the
ProgramEnrollment row level (see shared/submission/locks.py), which
lifecycle.py's submit_artwork already does.

completed_at is cleared back to NULL whenever a row's status moves away
from "Completed" to something else. There is currently no code path that
deliberately regresses a unit out of Completed, but recompute always
re-derives status from the row's three component signals, so if a
submission is ever invalidated/replaced after completion, the row could
in principle fall back to "In Progress" -- clearing completed_at in that
case keeps the timestamp from going stale, matching the "recompute fully
from source signals on every call" philosophy already used for
unit_status itself.

BUGFIX -- infer_last_activity_type no longer always prefers "quiz":

Previously this function checked is_quiz_graded(row) FIRST,
unconditionally, before ever looking at the submission signal. Since a
quiz can only be graded once per unit (a second attempt raises
CapReached) but a submission can be reattempted and re-graded well after
the quiz was already recorded, "quiz was ever graded" being first in this
precedence chain meant last_activity_type permanently reported "quiz"
for any unit where the quiz happened to be graded before the (possibly
much later) submission grading landed -- masking the more recent
submission event indefinitely. See the function's own docstring below
for the fix and its limits.

COMPLETED ACTIVITIES (frontend convenience list)
---------------------------------------------------
completed_activities_for_row is a purely additive, read-only derivation
off the exact same three completion signals unit_status is already
computed from (video_watched / is_quiz_graded / is_submission_valid). It
returns which of {"video", "quiz", "submission"} are currently complete
for one Unit Progress row, as a list, so a frontend can show per-activity
done/pending state for "the unit the student is currently on" without
re-deriving that itself from raw fields. It has no effect on unit_status
or course-completion logic, which are untouched and continue to be
computed exactly as before by recompute_unit_status /
recompute_unit_status_by_name.
"""

from __future__ import annotations

import json
from typing import Optional, TypedDict

import frappe

from shared.errors import InvalidInput
from shared.submission.status import is_submission_complete

VALID_UNIT_TYPES = ("program", "event")
UNIT_PROGRESS_CHILD_TABLE = "tabUnit Progress"


class UnitStatusResult(TypedDict):
    status: str
    just_completed: bool


def get_or_create_unit_progress_row(parent_doc, learning_unit: str, unit_type: str, table_fieldname: str = "unit_progress"):
    if unit_type not in VALID_UNIT_TYPES:
        raise InvalidInput(f"unit_type must be one of {VALID_UNIT_TYPES}")

    rows = getattr(parent_doc, table_fieldname)
    matches = [r for r in rows if r.learning_unit == learning_unit and r.unit_type == unit_type]
    if len(matches) > 1:
        raise InvalidInput(
            f"data integrity error: multiple Unit Progress rows for "
            f"(learning_unit={learning_unit}, unit_type={unit_type})"
        )
    if matches:
        return matches[0]

    return parent_doc.append(table_fieldname, {
        "learning_unit": learning_unit,
        "unit_type": unit_type,
        "video_watched": 0,
        "submission": None,
        "submission_attempts": 0,
        "quiz_json": None,
        "unit_status": "Not Started",
    })


def find_unit_progress_row_by_name(parent_doc, row_name: str, table_fieldname: str = "unit_progress"):
    """Looks only inside parent_doc's own child table. Use this ONLY when
    parent_doc is known to be the doc that actually owns the row (e.g.
    right after get_or_create_unit_progress_row returned it on the same
    request). For a row that might belong to a different/older enrollment
    than the student's current active one, use
    find_unit_progress_row_by_name_global instead."""
    for row in getattr(parent_doc, table_fieldname):
        if row.name == row_name:
            return row
    return None


def find_unit_progress_row_by_name_global(row_name: str) -> Optional[dict]:
    """Direct, global lookup of a Unit Progress child row by its own
    `name`, independent of which parent (ProgramEnrollment) currently owns
    it or whether that parent is the student's currently-active
    enrollment. A Unit Progress row's `name` is unique across the whole
    child table, so this is always safe and correct, unlike loading "the
    active enrollment" and hoping the row is still there."""
    if not row_name:
        return None
    rows = frappe.db.sql(
        f"""
        SELECT name, parent, unit_type, learning_unit, video_watched,
               quiz_json, submission, submission_attempts, unit_status, modified
        FROM "{UNIT_PROGRESS_CHILD_TABLE}"
        WHERE name = %s
        LIMIT 1
        """,
        (row_name,),
        as_dict=True,
    )
    return rows[0] if rows else None


def find_unit_progress_row_for_submission(submission_name: str) -> Optional[dict]:
    rows = frappe.db.sql(
        f"""
        SELECT name, parent, unit_type, learning_unit, video_watched,
               quiz_json, submission, submission_attempts, unit_status, modified
        FROM "{UNIT_PROGRESS_CHILD_TABLE}"
        WHERE submission = %s
        LIMIT 1
        """,
        (submission_name,),
        as_dict=True,
    )
    return rows[0] if rows else None


def attempt_info_for_submission(submission_name: str) -> tuple[int, int]:
    """The one implementation of "how many attempts has this submission
    used, and how many remain." Resolves the owning Unit Progress row
    directly (via find_unit_progress_row_for_submission), so it works
    correctly even when the submission belongs to a past/inactive
    enrollment -- never search the student's currently active enrollment's
    unit_progress table for this, since a submission outside that scope
    would silently resolve to a wrong (1, cap) instead of its real attempt
    count.

    Callers: tap_app/api/submission.py (list_submissions, get_submission)
    and shared/profile/sync.py (get_sync_payload, get_last_submission_payload)
    should all call this instead of maintaining their own copy.
    """
    from shared.progress.rewards import max_submission_attempts

    cap = max_submission_attempts()
    row = find_unit_progress_row_for_submission(submission_name)
    if not row:
        return 1, 0
    attempts = row.get("submission_attempts") or 0
    return attempts, max(cap - attempts, 0)


def is_quiz_graded(row) -> bool:
    quiz = row.quiz_json if hasattr(row, "quiz_json") else row.get("quiz_json")
    if isinstance(quiz, str):
        try:
            quiz = json.loads(quiz)
        except (TypeError, ValueError):
            quiz = None
    return bool(quiz and isinstance(quiz, dict) and quiz.get("graded"))


def is_submission_valid(row) -> bool:
    """True iff this row's linked Submission counts toward unit completion.
    Delegates the actual result_status classification to
    shared.submission.status.is_submission_complete -- the single place
    that set of values is defined -- instead of re-inlining the tuple
    here."""
    submission = row.submission if hasattr(row, "submission") else row.get("submission")
    if not submission:
        return False
    sub = frappe.db.get_value("Submission", submission, ["status", "result_status"], as_dict=True)
    if not sub:
        return False
    return sub.status == "Completed" and is_submission_complete(sub.result_status)


def completed_activities_for_row(row) -> list[str]:
    """Returns which of the three per-unit activity signals
    (video/quiz/submission) are currently COMPLETE for this Unit Progress
    row, as a list of strings drawn from {"video", "quiz", "submission"},
    in that fixed order. Purely additive, read-only derivation off the
    exact same three signals unit_status is already computed from
    (recompute_unit_status / recompute_unit_status_by_name) -- no new
    field, no new write path.

    - "video": row.video_watched is truthy.
    - "quiz": is_quiz_graded(row) is True (the quiz has been graded for
      this unit -- quiz is one-shot per unit, so "graded" and "complete"
      are the same thing here).
    - "submission": is_submission_valid(row) is True (the linked
      Submission exists and its result_status counts as complete --
      shared.submission.status.is_submission_complete).

    Accepts either a Frappe Document child row (attribute access) or a
    plain dict (e.g. a frappe.db.sql(as_dict=True) row) -- same dual-shape
    support as infer_last_activity_type below, since both shapes are fed
    into this function by its callers (shared/profile/sync.py's live doc
    rows for the "current unit" case).

    This is purely a frontend-facing convenience list ("what's done for
    this unit") and has no effect on unit_status / course completion
    logic, which continue to be computed exactly as before by
    recompute_unit_status / recompute_unit_status_by_name.
    """
    video_watched = row.video_watched if hasattr(row, "video_watched") else row.get("video_watched")

    completed: list[str] = []
    if video_watched:
        completed.append("video")
    if is_quiz_graded(row):
        completed.append("quiz")
    if is_submission_valid(row):
        completed.append("submission")
    return completed


def recompute_unit_status_by_name(unit_progress_row_name: str) -> UnitStatusResult:
    """Returns {"status": <resulting unit_status string>, "just_completed":
    <bool>} -- just_completed is True iff THIS call is what flipped the
    row from a non-"Completed" status to "Completed" (see module
    docstring). The resulting status string is preserved under the
    "status" key; callers that only need the string read result["status"].

    The whole read-decide-write sequence happens under a
    `SELECT ... FOR UPDATE` row lock taken at the top of this function --
    see module docstring's concurrency section for why this is required
    for just_completed's exactly-once guarantee to actually hold.
    """
    row = frappe.db.sql(
        f"""
        SELECT video_watched, quiz_json, submission, unit_status, completed_at
        FROM "{UNIT_PROGRESS_CHILD_TABLE}"
        WHERE name = %s
        LIMIT 1
        FOR UPDATE
        """,
        (unit_progress_row_name,),
        as_dict=True,
    )
    if not row:
        return {"status": "Not Started", "just_completed": False}
    row = row[0]

    old_status = row.unit_status
    quiz_graded = is_quiz_graded(row)
    submission_valid = is_submission_valid(row)
    any_touch = bool(row.video_watched) or quiz_graded or bool(row.submission)

    new_status = row.unit_status
    set_completed_at = False
    clear_completed_at = False

    if row.video_watched and quiz_graded and submission_valid:
        new_status = "Completed"
        if not row.completed_at:
            set_completed_at = True
    elif any_touch and row.unit_status == "Not Started":
        new_status = "In Progress"

    # If the row had previously been marked Completed but one of its
    # three component signals is no longer satisfied (e.g. a submission
    # was invalidated/replaced after completion), the row regresses out
    # of Completed -- clear the now-stale completed_at rather than
    # leaving a timestamp that no longer reflects reality.
    if old_status == "Completed" and new_status != "Completed" and row.completed_at:
        clear_completed_at = True

    if new_status != row.unit_status or set_completed_at or clear_completed_at:
        if set_completed_at:
            frappe.db.sql(
                f"""
                UPDATE "{UNIT_PROGRESS_CHILD_TABLE}"
                SET unit_status = %s, completed_at = NOW(), modified = NOW()
                WHERE name = %s
                """,
                (new_status, unit_progress_row_name),
            )
        elif clear_completed_at:
            frappe.db.sql(
                f"""
                UPDATE "{UNIT_PROGRESS_CHILD_TABLE}"
                SET unit_status = %s, completed_at = NULL, modified = NOW()
                WHERE name = %s
                """,
                (new_status, unit_progress_row_name),
            )
        else:
            frappe.db.sql(
                f"""
                UPDATE "{UNIT_PROGRESS_CHILD_TABLE}"
                SET unit_status = %s, modified = NOW()
                WHERE name = %s
                """,
                (new_status, unit_progress_row_name),
            )

    just_completed = (old_status != "Completed") and (new_status == "Completed")
    return {"status": new_status, "just_completed": just_completed}


def recompute_unit_status(row) -> UnitStatusResult:
    """Doc-based variant: mutates the live, in-memory child row object --
    the caller is responsible for saving the parent doc. Returns
    {"status": ..., "just_completed": ...} -- see module docstring and
    recompute_unit_status_by_name's docstring above for the exact meaning
    of just_completed.

    Mirrors recompute_unit_status_by_name's completed_at-clearing
    behavior for consistency -- a row that regresses out of Completed in
    memory (a component signal became invalid before save) has its
    completed_at cleared here too, rather than only in the by-name
    variant.
    """
    old_status = row.unit_status
    quiz_graded = is_quiz_graded(row)
    submission_valid = is_submission_valid(row)
    any_touch = bool(row.video_watched) or quiz_graded or bool(row.submission)

    if row.video_watched and quiz_graded and submission_valid:
        row.unit_status = "Completed"
        if not row.completed_at:
            row.completed_at = frappe.utils.now_datetime()
    elif any_touch and row.unit_status == "Not Started":
        row.unit_status = "In Progress"

    if old_status == "Completed" and row.unit_status != "Completed" and row.completed_at:
        row.completed_at = None

    just_completed = (old_status != "Completed") and (row.unit_status == "Completed")
    return {"status": row.unit_status, "just_completed": just_completed}


def infer_last_activity_type(row) -> Optional[str]:
    """Reports the most recently updated of the three possible per-unit
    activity signals (video, quiz, submission).

    BUGFIX: previously this always returned "quiz" whenever the quiz had
    ever been graded, with no regard for whether a submission was graded
    more recently. Quiz is one-shot per unit (CapReached on a second
    attempt), but a submission can be reattempted and re-graded well
    after the quiz, so "quiz was ever graded" being permanently first in
    this precedence chain meant a student whose submission was graded
    after their quiz would show last_activity_type: "quiz" forever,
    masking the more recent submission event.

    Unit Progress rows carry no per-signal timestamp of their own
    (video_watched/quiz_json/submission are plain boolean/pointer fields
    with no "when"), so a fully exact chronological ordering across all
    three signals isn't representable without a schema change, which is
    out of scope here. What IS representable with existing fields:
    comparing the linked Submission's own `modified` timestamp (bumped on
    every grading-pipeline update -- see shared/submission/review_result.py)
    against this Unit Progress row's own `modified` timestamp. If the
    submission is valid/graded (is_submission_valid) and its own
    `modified` is at or after this row's `modified`, the submission is
    reported as more recent than quiz -- this directly fixes the reported,
    concrete case (grading landing after the quiz was already recorded)
    without claiming perfect fidelity for every conceivable interleaving.

    Accepts either a Frappe Document child row (attribute access, with
    row.modified present as a live field) or a plain dict such as the
    ones find_unit_progress_row_for_submission /
    find_unit_progress_row_by_name_global return (which also select
    `modified` -- see those functions above) -- both call sites that feed
    rows into this function rely on one or the other shape.

    Precedence is otherwise unchanged from before: quiz, then submission,
    then video, for whichever case the submission-recency check above
    doesn't resolve (e.g. no submission at all, or a submission that
    exists but isn't yet validly graded).
    """
    quiz_graded = is_quiz_graded(row)
    submission = row.submission if hasattr(row, "submission") else row.get("submission")
    video_watched = row.video_watched if hasattr(row, "video_watched") else row.get("video_watched")

    if submission and is_submission_valid(row):
        row_modified = row.modified if hasattr(row, "modified") else row.get("modified")
        sub_modified = frappe.db.get_value("Submission", submission, "modified")
        if not row_modified or (sub_modified and sub_modified >= row_modified):
            return "submission"

    if quiz_graded:
        return "quiz"
    if submission:
        return "submission"
    if video_watched:
        return "video"
    return None


def resolve_current_unit_for_track(parent_doc, unit_type: str, table_fieldname: str = "unit_progress", fallback_resolver=None):
    rows = getattr(parent_doc, table_fieldname)
    candidates = [r for r in rows if r.unit_type == unit_type and r.unit_status != "Completed"]
    if candidates:
        candidates.sort(key=lambda r: r.idx, reverse=True)
        return candidates[0].learning_unit
    if fallback_resolver:
        return fallback_resolver(parent_doc)
    return None


def resolve_last_activity_type_for_track(parent_doc, unit_type: str, table_fieldname: str = "unit_progress") -> Optional[str]:
    """Reads last_activity_type straight off parent_doc's own child table.
    SAFE for unit_type == "program": now that
    shared.enrollment.enrollment.create_enrollment guarantees exactly one
    ProgramEnrollment per (student, course_level) for life, a program-context
    row always lives on that one, lifelong doc, which is exactly what
    get_active_program_enrollment loads.

    NOT safe for unit_type == "event" in general -- an event's Unit Progress
    row is not guaranteed to live on the currently-active enrollment. Use
    resolve_last_activity_type(..., unit_type="event", event_id=...) for
    that case instead; it resolves the row the same way
    shared.events.enrollment.is_enrolled does.
    """
    rows = [r for r in getattr(parent_doc, table_fieldname) if r.unit_type == unit_type]
    if not rows:
        return None
    rows.sort(key=lambda r: r.idx, reverse=True)
    return infer_last_activity_type(rows[0])


def resolve_last_activity_type(student_id: str, program_enrollment_doc, unit_type: str,
                                event_id: str | None = None, table_fieldname: str = "unit_progress") -> Optional[str]:
    """
    The one correct entrypoint for "what did this student last do",
    covering BOTH tracks:

    - unit_type == "program": delegates to resolve_last_activity_type_for_track
      on program_enrollment_doc's own unit_progress table. Safe because a
      program-context row always lives on the student's one, lifelong
      ProgramEnrollment (see that function's docstring).

    - unit_type == "event": program_enrollment_doc.unit_progress is NOT a
      safe source -- an event's Unit Progress row can live on a
      ProgramEnrollment that is no longer the student's active one (see
      shared/progress/activities.py's _resolve_event_unit_progress_row
      docstring for the full reasoning). This branch instead resolves
      the row exactly the way shared.events.enrollment.is_enrolled does:
      find the student's Student Event Enrollment row for event_id, take
      its stored unit_progress pointer, and resolve that globally via
      find_unit_progress_row_by_name_global. event_id is required here.

    Returns None if there is no row yet for that track (student hasn't
    started), not an error -- "no activity yet" is a valid, common state.
    """
    if unit_type not in VALID_UNIT_TYPES:
        raise InvalidInput(f"unit_type must be one of {VALID_UNIT_TYPES}")

    if unit_type == "program":
        return resolve_last_activity_type_for_track(program_enrollment_doc, "program", table_fieldname)

    if not event_id:
        raise InvalidInput("event_id is required to resolve last_activity_type for unit_type='event'")

    event_row = frappe.db.sql(
        """
        SELECT unit_progress
          FROM "tabStudent Event Enrollment"
         WHERE parent = %(student_id)s AND event = %(event_id)s
         ORDER BY idx DESC
         LIMIT 1
        """,
        {"student_id": student_id, "event_id": event_id},
        as_dict=True,
    )
    if not event_row or not event_row[0].get("unit_progress"):
        return None

    up_row = find_unit_progress_row_by_name_global(event_row[0]["unit_progress"])
    if not up_row:
        return None

    return infer_last_activity_type(up_row)