"""
shared/progress/activities.py
Grades/records submit_video_watched / submit_quiz for both "program" and
"event" tracks. Event-track reads and writes must resolve to the same Unit
Progress row (is_enrolled resolves it globally by name); this module's
write path (_resolve_event_unit_progress_row) honors that by finding the
row the event enrollment already points at, so writes stay anchored to
whichever enrollment first created the row for this (student, event) pair.

FIX (TOCTOU race): _resolve_event_unit_progress_row's pointer write used to
be an unconditional frappe.db.set_value — check_attempt_cap calls this
same path despite being documented as read-only and NOT wrapped in
with_serialization_retry, so a concurrent submit_artwork call that set the
real pointer between check_attempt_cap's read and this write could get
silently clobbered back to None. The write below is now a conditional
UPDATE (only writes if the pointer column is still NULL/empty), so two
racing writers can no longer stomp on each other — the first write wins,
the second is a safe no-op.

FIX (missing functions / deploy-breaking ImportError): a prior edit to
this file, made to land the TOCTOU fix above, replaced the whole file but
only pasted the two helpers that were actually being changed
(_resolve_event_unit_progress_row, _finalize_event_enrollment_pointer),
dropping submit_video_watched and submit_quiz entirely. That broke
tap_lms/tap_app/api/progress.py's top-level import of this module:

    from shared.progress.activities import (
        submit_video_watched as _submit_video_watched,
        submit_quiz as _submit_quiz,
        _finalize_event_enrollment_pointer,
    )

An ImportError at module-import time (as opposed to inside a request
handler) is never caught by tap_app_method's own try/except -- Frappe's
own command dispatcher (frappe/handler.py::get_attr) fails before
tap_app_method ever runs, surfacing as a raw HTTP 417 "Failed to get
method for command ... cannot import name 'submit_video_watched' from
'shared.progress.activities'" instead of a clean, logged 500. Both
functions are restored below, now built on top of the TOCTOU-safe
_resolve_event_unit_progress_row so a future edit to this file does not
have to choose between "paste the whole file" and "keep both fixes" again
-- everything that must stay in sync lives in one file, in full.

FIX (next_learning_unit_id / advance_to_next_unit misuse in
_apply_completion_fields): two bugs, found together, in the helper that
derives unit_completed/course_completed/next_learning_unit_id for the
video/quiz completion response:

  1. advance_to_next_unit's own docstring states plainly that it performs
     "bookkeeping-only sanity logging and no mutation of its own" and
     ALWAYS returns None -- "advancing" to the next unit is a live read
     (next_unit_for), computed fresh on every call, not a write. The
     previous code treated its return value as if it could be a real
     next-unit id:

         result["next_learning_unit_id"] = advance_to_next_unit(...) or \\
             get_ordered_units_for_course_level(program_enrollment_doc.course_level)

     Since advance_to_next_unit(...) is always None, this ALWAYS fell
     through to get_ordered_units_for_course_level(...), which returns a
     LIST of every unit in the course level -- not a single next-unit id.
     Every other call site in this codebase that reports
     next_learning_unit_id (shared/profile/sync.py::
     _completion_fields_for_submission, shared/submission/lifecycle.py::
     submit_artwork) reports a single string or None, matching the
     Worker's own RawSubmission.next_learning_unit_id: string | null type.
     Serializing a whole unit list into that field silently breaks every
     client that expects a scalar.

  2. Even setting aside (1), the call passed
     program_enrollment_doc.name (the ENROLLMENT's own name, e.g.
     "ST00034562-LVL2") as advance_to_next_unit's `completed_unit_id`
     parameter -- which expects a LEARNING UNIT id, not an enrollment
     name. advance_to_next_unit's own body logs a warning whenever its
     completed_unit_id argument isn't found in the course's ordered unit
     sequence, which a bare enrollment name never is -- so this
     unconditionally emitted a spurious warning on every single unit
     completion, pointing at the wrong "unit."

  Fixed by calling next_unit_for(program_enrollment_doc) directly --
  the same, correct function every other completion-fields call site in
  this codebase already uses -- instead of going through
  advance_to_next_unit at all. advance_to_next_unit is still called, once,
  purely for its own documented bookkeeping/sanity-logging side effect
  (passing the actual completed unit id, not the enrollment name), since
  removing that call entirely would silently drop whatever diagnostic
  value that logging provides; its return value is simply no longer used
  for anything.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from shared.errors import CapReached, InvalidInput, NotFound
from shared.progress.unit_progress import (
    get_or_create_unit_progress_row,
    recompute_unit_status,
    find_unit_progress_row_by_name_global,
)
from shared.progress.rewards import award_points, points_for_video, points_per_quiz_correct
from shared.enrollment.unit_rotation import advance_to_next_unit, get_ordered_units_for_course_level, is_course_complete, next_unit_for
from shared.enrollment.enrollment import mark_course_completed, activate_if_inactive
from shared.submission.lifecycle import require_video_done as _require_video_done
from shared.submission.locks import lock_program_enrollment_row
from shared.db_retry import with_serialization_retry


def _validate_program_sequence(program_enrollment_doc, unit_id: str) -> None:
    ordered = get_ordered_units_for_course_level(program_enrollment_doc.course_level)
    if unit_id not in ordered:
        raise InvalidInput("unit does not belong to this student's course level")
    idx = ordered.index(unit_id)
    progress_by_unit = {
        row.learning_unit: row
        for row in (program_enrollment_doc.unit_progress or [])
        if row.unit_type == "program"
    }
    for earlier_unit in ordered[:idx]:
        row = progress_by_unit.get(earlier_unit)
        if row is None or row.unit_status != "Completed":
            raise InvalidInput("unit_id is not the next unit in sequence for this student")


def _find_active_event_enrollment_row(student_id: str, learning_unit: str):
    rows = frappe.db.sql(
        """
        SELECT see.name, see.parent AS student_id, see.event, see.unit_progress
          FROM "tabStudent Event Enrollment" see
          JOIN "tabEvent Campaign" ec ON ec.name = see.event
         WHERE see.parent = %(student_id)s
           AND see.status = 'active'
           AND ec.learning_unit = %(learning_unit)s
         ORDER BY see.idx DESC
         LIMIT 1
        """,
        {"student_id": student_id, "learning_unit": learning_unit},
        as_dict=True,
    )
    return rows[0] if rows else None


def _resolve_event_unit_progress_row(program_enrollment_doc, student_id: str, learning_unit: str):
    """Returns (owning_parent_doc, row) for an event-context write.

    If the student's active event enrollment already points at a Unit
    Progress row, that row is resolved globally and the parent doc that
    actually owns it is loaded and returned — so writes land on the same
    row the read path (is_enrolled) already resolves to, regardless of
    which enrollment is "active" right now.

    If there is no pointer yet (first-ever activity for this event),
    creates a row on the currently-active enrollment and writes the
    pointer back — RACE-SAFELY: the UPDATE only applies if the column is
    still NULL/empty, so a concurrent caller (e.g. check_attempt_cap vs.
    submit_artwork landing at nearly the same time) can never overwrite a
    pointer the other caller already set.
    """
    event_row = _find_active_event_enrollment_row(student_id, learning_unit)

    if event_row and event_row.get("unit_progress"):
        global_row = find_unit_progress_row_by_name_global(event_row["unit_progress"])
        if global_row:
            owning_enrollment_name = global_row["parent"]
            if owning_enrollment_name == program_enrollment_doc.name:
                owning_doc = program_enrollment_doc
            else:
                owning_doc = frappe.get_doc("ProgramEnrollment", owning_enrollment_name)
            row = None
            for r in owning_doc.unit_progress:
                if r.name == event_row["unit_progress"]:
                    row = r
                    break
            if row is not None:
                return owning_doc, row
            frappe.logger().error(
                f"_resolve_event_unit_progress_row: Student Event Enrollment "
                f"{event_row['name']} points at unit_progress="
                f"{event_row['unit_progress']!r}, resolved globally to "
                f"parent={owning_enrollment_name}, but no matching child row "
                f"was found there. Falling back to create-on-active-enrollment."
            )
        else:
            frappe.logger().error(
                f"_resolve_event_unit_progress_row: Student Event Enrollment "
                f"{event_row['name']} points at unit_progress="
                f"{event_row['unit_progress']!r}, which does not resolve to "
                f"any Unit Progress row. Falling back to create-on-active-enrollment."
            )

    row = get_or_create_unit_progress_row(program_enrollment_doc, learning_unit, "event")

    if event_row:
        new_name = row.name if getattr(row, "name", None) else None
        if new_name:
            # FIX: conditional write — only claims the pointer if it is
            # still unset, closing the race window a plain set_value left
            # open for check_attempt_cap (no row lock, no serialization
            # retry) against a concurrent submit_artwork write.
            frappe.db.sql(
                """
                UPDATE "tabStudent Event Enrollment"
                   SET unit_progress = %(new_name)s
                 WHERE name = %(event_row_name)s
                   AND (unit_progress IS NULL OR unit_progress = '')
                """,
                {"new_name": new_name, "event_row_name": event_row["name"]},
            )
        else:
            row._pending_event_enrollment_pointer = event_row["name"]

    return program_enrollment_doc, row


def _finalize_event_enrollment_pointer(row) -> None:
    pending = getattr(row, "_pending_event_enrollment_pointer", None)
    if pending and getattr(row, "name", None):
        # Same race-safe conditional write as above — a deferred pointer
        # finalize must not clobber a pointer another writer already set
        # between this row's creation and its parent doc being saved.
        frappe.db.sql(
            """
            UPDATE "tabStudent Event Enrollment"
               SET unit_progress = %(new_name)s
             WHERE name = %(pending)s
               AND (unit_progress IS NULL OR unit_progress = '')
            """,
            {"new_name": row.name, "pending": pending},
        )


def resolve_video_id_for_unit(unit_id: str) -> str | None:
    video_row = frappe.db.sql(
        """
        SELECT uci.content
          FROM "tabUnitContentItem" uci
         WHERE uci.parent = %s
           AND uci.content_type = 'VideoClass'
           AND uci.content IS NOT NULL AND uci.content != ''
         LIMIT 1
        """,
        (unit_id,),
    )
    if video_row and video_row[0][0]:
        return video_row[0][0]
    return None


def _apply_completion_fields(result: dict, program_enrollment_doc, just_completed: bool, context: str, unit_id: str) -> None:
    """Adds unit_completed / course_completed / next_learning_unit_id to
    `result` when this call's own write just completed the unit.

    FIX: previously called advance_to_next_unit(doc, doc.name) and used
    its return value (always None -- see module docstring) with an `or`
    fallback to get_ordered_units_for_course_level(...), which returns a
    LIST of every unit in the course, not a single next-unit id, and was
    also passed the enrollment's own name instead of the completed unit's
    id. Fixed to call next_unit_for(program_enrollment_doc) directly for
    the actual next-unit id -- the same function every other completion-
    fields call site in this codebase uses (shared/profile/sync.py::
    _completion_fields_for_submission, shared/submission/lifecycle.py::
    submit_artwork) -- and to call advance_to_next_unit separately, with
    the real completed unit_id, purely for its own documented
    bookkeeping/sanity-logging side effect; its return value is not used.
    """
    if not just_completed:
        return
    result["unit_completed"] = True
    if context != "program":
        return

    # Bookkeeping/sanity-logging only (see advance_to_next_unit's own
    # docstring: it mutates nothing and always returns None). Passed the
    # actual completed unit id, not the enrollment name, so its own
    # "is this unit in the ordered sequence" warning check is meaningful
    # instead of spuriously firing on every completion.
    advance_to_next_unit(program_enrollment_doc, unit_id)

    if is_course_complete(program_enrollment_doc):
        mark_course_completed(program_enrollment_doc.name)
        result["course_completed"] = True
    else:
        result["course_completed"] = False
        result["next_learning_unit_id"] = next_unit_for(program_enrollment_doc)


def submit_video_watched(program_enrollment_doc, unit_id: str, video_id: str, watched: bool, context: str = "program") -> dict:
    """Records a video-watched event for (unit_id, video_id) under
    `context` ("program" | "event"), awarding points_for_video() the
    first time `watched` is recorded True for this unit (a repeat call
    reporting watched=True again, or any call reporting watched=False,
    awards nothing and reports repeat=True/False accordingly).

    For context == "program": validates unit_id is the student's actual
    next unit in sequence (_validate_program_sequence) before anything
    else -- a program-track write must stay in strict unit order.
    For context == "event": no such sequence validation applies; the
    Unit Progress row is resolved via _resolve_event_unit_progress_row,
    anchored to whichever enrollment actually owns the event's progress
    row (see that function's own docstring), not necessarily
    program_enrollment_doc itself.

    Returns a dict with points_awarded, points_total (computed off the
    OWNING doc for this write, never unconditionally program_enrollment_doc),
    context, repeat, video_id, and -- via _apply_completion_fields --
    unit_completed / course_completed / next_learning_unit_id when this
    call's own write just completed the unit. The owning doc is returned
    under "_owning_doc" and the mutated row under "_row", both popped by
    the caller (tap_app/api/progress.py::_save_affected_docs) before the
    rest of this dict is used to build the wire response -- see that
    file's own docstring for why.
    """
    watched = bool(watched)

    if context == "program":
        _validate_program_sequence(program_enrollment_doc, unit_id)
        owning_doc, row = program_enrollment_doc, get_or_create_unit_progress_row(program_enrollment_doc, unit_id, "program")
    else:
        owning_doc, row = _resolve_event_unit_progress_row(program_enrollment_doc, program_enrollment_doc.student, unit_id)

    already_watched = bool(row.video_watched)
    repeat = already_watched

    points_awarded = 0
    if watched and not already_watched:
        row.video_watched = 1
        points_awarded = points_for_video()
        award_points(owning_doc, points_awarded, bump_activity=False)
        activate_if_inactive(owning_doc)
    elif not watched:
        # Explicitly reporting watched=False never un-sets a previously
        # recorded watch, and never awards/deducts points -- this is a
        # report of the current playback state, not a toggle.
        repeat = already_watched

    status_result = recompute_unit_status(row)

    result = {
        "points_awarded": points_awarded,
        "points_total": owning_doc.points or 0,
        "context": context,
        "repeat": repeat,
        "video_id": video_id,
        "_owning_doc": owning_doc,
        "_row": row,
    }
    _apply_completion_fields(result, owning_doc, status_result["just_completed"], context, unit_id)
    return result


def submit_quiz(program_enrollment_doc, unit_id: str, quiz_id: str, answers: list[dict], context: str = "program") -> dict:
    """Grades a quiz attempt for (unit_id, quiz_id) under `context`
    ("program" | "event"). A quiz may only be graded ONCE per unit -- a
    second attempt (quiz_json already marked graded) raises CapReached
    rather than re-grading or re-awarding.

    Requires the unit's video to already be watched
    (shared.submission.lifecycle.require_video_done), matching the same
    within-unit prerequisite submit_artwork enforces for a submission.

    `answers` is a list of {"question_id": str, "selected_key": str}.
    Correctness is resolved per-question via the UnitContentItem Quiz
    content's own stored correct_key; a question_id with no resolvable
    quiz content is treated as incorrect (not an error) rather than
    aborting the whole grading pass.

    Returns a dict with quiz_id, correct_count, total_count,
    points_awarded (points_per_quiz_correct() * correct_count),
    points_total (off the owning doc), context, repeat (always False --
    a quiz can only ever be graded once, so a second call always raises
    CapReached before reaching this return), and -- via
    _apply_completion_fields -- unit_completed / course_completed /
    next_learning_unit_id when this call's own write just completed the
    unit. "_owning_doc" / "_row" are popped by the caller, same as
    submit_video_watched above.
    """
    if context == "program":
        _validate_program_sequence(program_enrollment_doc, unit_id)
        owning_doc, row = program_enrollment_doc, get_or_create_unit_progress_row(program_enrollment_doc, unit_id, "program")
    else:
        owning_doc, row = _resolve_event_unit_progress_row(program_enrollment_doc, program_enrollment_doc.student, unit_id)

    _require_video_done(row)

    existing_quiz = row.quiz_json
    if isinstance(existing_quiz, str):
        try:
            existing_quiz = json.loads(existing_quiz)
        except (TypeError, ValueError):
            existing_quiz = None
    if existing_quiz and isinstance(existing_quiz, dict) and existing_quiz.get("graded"):
        raise CapReached("quiz has already been graded for this unit")

    quiz_rows = frappe.db.sql(
        """
        SELECT uci.content
          FROM "tabUnitContentItem" uci
         WHERE uci.parent = %s
           AND uci.content_type = 'Quiz'
           AND uci.content IS NOT NULL AND uci.content != ''
         LIMIT 1
        """,
        (unit_id,),
    )
    if not quiz_rows or not quiz_rows[0][0]:
        raise NotFound("no quiz configured for this unit")
    resolved_quiz_id = quiz_rows[0][0]

    correct_keys: dict[str, str] = {}
    question_rows = frappe.db.sql(
        """
        SELECT name, correct_key FROM "tabQuizQuestion" WHERE parent = %s
        """,
        (resolved_quiz_id,),
        as_dict=True,
    )
    for q in question_rows:
        if q.get("name") and q.get("correct_key"):
            correct_keys[q["name"]] = str(q["correct_key"])

    correct_count = 0
    for a in answers:
        qid = a.get("question_id")
        selected = a.get("selected_key")
        if qid in correct_keys and str(selected) == correct_keys[qid]:
            correct_count += 1
    total_count = len(answers)

    row.quiz_json = json.dumps({
        "quiz_id": resolved_quiz_id,
        "graded": True,
        "correct_count": correct_count,
        "total_count": total_count,
        "answers": answers,
    })

    points_awarded = points_per_quiz_correct() * correct_count
    award_points(owning_doc, points_awarded, bump_activity=False)
    activate_if_inactive(owning_doc)

    status_result = recompute_unit_status(row)

    result = {
        "quiz_id": resolved_quiz_id,
        "correct_count": correct_count,
        "total_count": total_count,
        "points_awarded": points_awarded,
        "points_total": owning_doc.points or 0,
        "context": context,
        "repeat": False,
        "_owning_doc": owning_doc,
        "_row": row,
    }
    _apply_completion_fields(result, owning_doc, status_result["just_completed"], context, unit_id)
    return result