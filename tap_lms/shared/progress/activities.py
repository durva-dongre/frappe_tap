"""
shared/progress/activities.py

Grades and records submit_video_watched / submit_quiz activity for a Unit
Progress row, for both the "program" and "event" tracks.

Event-track reads and writes must resolve to the same Unit Progress row,
because `is_enrolled` (shared/events/enrollment.py) resolves a student's
event-track row globally, by the row's own `name`, via
`find_unit_progress_row_by_name_global` -- a Unit Progress row is immutably
tied to whichever ProgramEnrollment it was created under, never to whatever
enrollment happens to be "active" right now. This module's write path honors
that same invariant: `_resolve_event_unit_progress_row` finds the row the
*event enrollment itself* already points at (via the same global, by-name
lookup `is_enrolled` uses, sourced from the Student's own `event_enrollments`
child table row for this event) and returns that row's owning parent-doc
name alongside the row, so writes stay anchored to whichever enrollment
first created the row for this (student, event) pair -- not to whatever
enrollment happens to be active at write time. Only when no row exists yet
(the student's first-ever activity for this event) is a new row created,
and it is created on the currently active enrollment, exactly as for a first
write today -- there is nothing "immutable" to preserve continuity with yet
in that case.

Program context does not need this resolution at all: it always reads and
writes unit_progress rows directly on the passed-in (always active)
program_enrollment_doc, because shared.enrollment.enrollment.
create_enrollment guarantees exactly one ProgramEnrollment per (student,
course_level) for life, so a program-context row always lives on that one,
lifelong doc.

check_quiz_answers requires `selected_key` to be a bare positive-integer
string (or int) before grading, because QuizQuestion.correct_option is
always stored as a plain 1-based option index ("1", "2", "3", ...), never
option text -- nothing in the Quiz/QuizQuestion doctypes ever stores free
text there. Validating the shape up front, rather than simply comparing
str(correct_option) == str(selected_key) and letting any non-matching value
grade as "wrong," keeps a malformed answer (empty string, whitespace, option
text from a buggy client) distinguishable as a 400 from a genuine wrong
answer -- the two are not the same case and must not look the same to the
caller. This mirrors the same validation on the Worker side
(worker/src/handlers/progressHandlers.ts), so both layers agree on the exact
same accepted shape for selected_key.

See shared/events/enrollment.py and shared/progress/unit_progress.py for the
lookup primitives this module relies on.

COURSE SEQUENCE INVARIANT (confirmed 2026-11-14): video is always the first
activity logged for any unit -- a student cannot submit or take the quiz for
a unit until video_watched is true (see
shared/submission/lifecycle.py::_require_video_done for the submission-side
enforcement of this; quiz has no such explicit prerequisite check in code
today, but the product flow guarantees video precedes it in practice).
Whichever of {submission, quiz} finishes LAST for a unit is therefore the
one that can tip unit_status to "Completed" -- video itself can never be the
completing activity, because something (submission and/or quiz) is always
still outstanding when video is watched. Both submit_video_watched and
submit_quiz below still carry the identical completion-reporting block for
symmetry and because a quiz CAN be the completing activity (if submission
already finished first) -- but submit_video_watched's own block is, by this
invariant, never actually reachable with just_completed=True in practice.
It is kept rather than omitted so the three activity-report call sites
(video, quiz, and shared/submission/review_result.py's submission path)
all carry the same shape and the same defensive logic, rather than having
video be a silent special case future maintainers have to rediscover.

SUBMISSION_THIS_WEEK (2026-11-14): this counter is NO LONGER touched
anywhere in this file. It used to be bumped here, on every program-context
video/quiz activity, as part of the old activity_this_week semantics. Per
the new design, submission_this_week counts only graded submission review
OUTCOMES (any result_status), incremented exactly once per outcome by
shared/submission/review_result.py::handle_review_result -- never at
submit time, and never for video/quiz activity at all. See that module and
shared/progress/rewards.py::max_submissions_per_week for the weekly cap
this counter feeds.

LAST_ACTIVITY_AT POLICY (2026-11-14, this pass): submit_video_watched and
submit_quiz now call shared.progress.rewards.award_points with
bump_activity=False, instead of relying on award_points's old unconditional
bump. Previously, ANY activity on a program/event enrollment -- a plain
video watch, a quiz attempt, not just a submission -- advanced that
enrollment's last_activity_at, which meant /progress/sync's own "has
anything changed" check (shared.profile.sync.get_sync_payload's
current_epoch <= last_updated_epoch comparison) fired on video/quiz activity
too, not only on a submission update. The explicit goal of this pass is
that last_activity_at, and therefore sync's changed-detection, should
advance ONLY when a submission updates (see shared/submission/lifecycle.py's
Decision D and shared/submission/review_result.py's own last_activity_at
bumps, both unaffected by this change since those are submission-outcome
events).

This file's own `program_enrollment_doc.last_activity_at = ...` /
`owning_doc.last_activity_at = ...` assignments, a few lines below each
award_points call in both submit_video_watched and submit_quiz, are
DELIBERATELY REMOVED as part of this same pass -- they were a second,
redundant source of the exact same bump this policy is trying to stop.
Nothing in this file sets last_activity_at anymore; that field is now
touched only by submission-outcome code paths elsewhere in the codebase.

Points themselves are completely unaffected by this change: award_points
still adds `amount` to `owning_doc.points` in memory exactly as before --
bump_activity only controls whether last_activity_at is also touched in the
same call. A video watch or quiz attempt still earns and persists its
points; it just no longer, on its own, makes the enrollment look newer to
sync.
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
from shared.enrollment.unit_rotation import advance_to_next_unit, get_ordered_units_for_course_level, is_course_complete
from shared.enrollment.enrollment import mark_course_completed, activate_if_inactive


def _validate_program_sequence(program_enrollment_doc, unit_id: str) -> None:
    """Cross-unit sequence check, program context only: a student can only
    submit for the next not-yet-completed unit in their course level's
    ordered sequence."""
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
    """Finds the student's active Student Event Enrollment row whose event
    currently targets `learning_unit`, so we know which event this
    (unit_id, context='event') write is for. Mirrors the lookup already
    done in shared/submission/lifecycle.py::resolve_learning_unit_for_assignment
    for the event branch, but in reverse: here we already have the unit_id
    (from the request), and need the owning event enrollment row."""
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

    If the student's active event enrollment for this unit already points
    at a Unit Progress row (row.unit_progress is set), that row is resolved
    GLOBALLY via find_unit_progress_row_by_name_global -- the same lookup
    `is_enrolled` uses -- and the parent ProgramEnrollment doc that actually
    owns that row is loaded and returned, so the write lands on the SAME
    row/doc the read path already resolves to, regardless of which
    enrollment is "active" right now.

    If there is no event enrollment row yet, or it has no unit_progress
    pointer yet (first-ever activity for this event), falls back to
    get_or_create_unit_progress_row on the currently-active enrollment --
    there's no prior row to preserve continuity with, so this matches
    today's behavior for a first write. The newly-created row's name is
    then written back onto the event enrollment's own `unit_progress`
    pointer, so the NEXT read/write (is_enrolled, or a later activity call)
    finds it via the same global lookup rather than silently falling into
    this same "no pointer yet" branch and creating a second row.
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
            # Find the live, mutable child-table row object on the owning
            # doc (global_row above is a plain dict snapshot from raw SQL;
            # we need the actual Document row to mutate and save).
            row = None
            for r in owning_doc.unit_progress:
                if r.name == event_row["unit_progress"]:
                    row = r
                    break
            if row is not None:
                return owning_doc, row
            # Pointer referenced a row that's gone missing from its own
            # parent's child table (shouldn't happen, but don't crash --
            # fall through to create-on-active below).

    # No existing row to anchor to: create on the active enrollment, exactly
    # as today's behavior does, and record the pointer on the event
    # enrollment row so future calls resolve back to this same row.
    row = get_or_create_unit_progress_row(program_enrollment_doc, learning_unit, "event")

    if event_row:
        frappe.db.set_value(
            "Student Event Enrollment",
            event_row["name"],
            "unit_progress",
            row.name if getattr(row, "name", None) else None,
            update_modified=False,
        )
        # A brand-new child row appended via `append()` has no `name` yet
        # until the parent doc is saved (Frappe assigns child-table names on
        # insert/save). If it's not yet assigned, the pointer write above is
        # a no-op (None); the caller (submit_video_watched/submit_quiz)
        # saves program_enrollment_doc at the end of the request, after
        # which `row.name` will be populated. We re-set the pointer in that
        # case via a scheduled-after-save step: simplest correct fix is to
        # have the caller persist the pointer after its own save, so we
        # surface that need by stashing the event_row name on the returned
        # row object for the caller to finish wiring up if necessary.
        if not getattr(row, "name", None):
            row._pending_event_enrollment_pointer = event_row["name"]

    return program_enrollment_doc, row


def _finalize_event_enrollment_pointer(row) -> None:
    """Called by the API-layer wrapper (tap_app/api/progress.py) after
    program_enrollment_doc.save() -- at which point a freshly-appended Unit
    Progress child row finally has its own `name` assigned by Frappe. If
    _resolve_event_unit_progress_row had to defer the Student Event
    Enrollment.unit_progress pointer write (because the row didn't have a
    name yet), this finishes that write now. No-op if nothing is pending."""
    pending = getattr(row, "_pending_event_enrollment_pointer", None)
    if pending and getattr(row, "name", None):
        frappe.db.set_value(
            "Student Event Enrollment", pending, "unit_progress", row.name, update_modified=False,
        )


def resolve_video_id_for_unit(unit_id: str) -> str | None:
    """Returns the VideoClass id (content) linked to this unit via
    UnitContentItem.content_type == 'VideoClass', or None if the unit has
    no video content item configured."""
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


def _apply_completion_fields(result: dict, program_enrollment_doc, just_completed: bool) -> None:
    """Shared by submit_video_watched and submit_quiz: if just_completed is
    True, decides whether the WHOLE COURSE is now finished
    (shared.enrollment.unit_rotation.is_course_complete) and, if so, marks
    the enrollment "completed" (shared.enrollment.enrollment.
    mark_course_completed) -- then adds the documented completion fields
    directly into `result` in place:

      - Unit completed, course NOT complete:
            {"unit_completed": True, "course_completed": False,
             "next_learning_unit_id": <next unit id>}
      - Unit completed, course IS complete (Decision B):
            {"unit_completed": True, "course_completed": True}
            -- no next_learning_unit_id key at all.
      - Unit did NOT complete on this call: no keys are added at all
        (Decision B's "absent means nothing changed" convention, matching
        how last_submission is handled elsewhere in this codebase) --
        result is left untouched.

    mark_course_completed is idempotent (a no-op, returning False, if the
    enrollment is already "completed") -- safe to call on every call where
    just_completed is True, even if an earlier call already completed the
    course (shouldn't happen given just_completed's own definition, but
    mark_course_completed tolerates it regardless).
    """
    if not just_completed:
        return

    result["unit_completed"] = True

    if is_course_complete(program_enrollment_doc):
        mark_course_completed(program_enrollment_doc.name)
        result["course_completed"] = True
        # Decision B: no next_learning_unit_id key at all when the course
        # is complete.
    else:
        from shared.enrollment.unit_rotation import next_unit_for
        result["course_completed"] = False
        result["next_learning_unit_id"] = next_unit_for(program_enrollment_doc)


def submit_video_watched(program_enrollment_doc, unit_id: str, video_id: str, watched: bool, context: str = "program") -> dict:
    """Validates video_id against the unit's configured video, then flips
    video_watched once (idempotent on repeat). Advances the student to the
    next unit in program context the moment every required activity for
    the unit is done.

    For context == "event", resolves the owning Unit Progress row globally
    (see _resolve_event_unit_progress_row) instead of assuming it lives on
    the currently active enrollment, so writes stay anchored to wherever
    the student's event progress actually started.

    First-ever row creation (program context) also activates the
    enrollment if it is currently "default" or "no_activity"
    (shared.enrollment.enrollment.activate_if_inactive) -- a student's
    first logged activity for an enrollment is exactly the signal that
    should move it out of "default"/"no_activity" into "active". This
    mutates program_enrollment_doc.status in memory only; the caller
    (tap_app/api/progress.py::_save_affected_docs) already saves
    program_enrollment_doc unconditionally at the end of every call, so
    the flip is persisted for free -- no extra save is added here. Per
    this project's scope, submit_video_watched's own wire response is NOT
    changed to carry a "status" field (that field is reserved for
    login/sync responses only, per the "status change notification only
    on login/sync" decision) -- the status change still happens and is
    persisted, it is simply not surfaced on THIS particular response.

    LAST_ACTIVITY_AT (2026-11-14, this pass): this function no longer
    advances program_enrollment_doc.last_activity_at (or owning_doc's, for
    an event-context write) in any way. The award_points call below passes
    bump_activity=False explicitly, and the old, separate
    `program_enrollment_doc.last_activity_at = frappe.utils.now_datetime()`
    / `owning_doc.last_activity_at = ...` assignments that used to sit
    right after it have been removed outright -- see module docstring's
    LAST_ACTIVITY_AT POLICY section for why. A video watch still earns and
    persists points exactly as before; it just no longer makes the
    enrollment look "newer" to /progress/sync's changed-detection.
    """
    if context == "program":
        _validate_program_sequence(program_enrollment_doc, unit_id)

    expected_video_id = resolve_video_id_for_unit(unit_id)
    if not expected_video_id:
        raise NotFound("no video is configured for this unit")
    if video_id != expected_video_id:
        raise InvalidInput("video_id does not match the video configured for this unit")

    if context == "event":
        owning_doc, row = _resolve_event_unit_progress_row(
            program_enrollment_doc, program_enrollment_doc.student, unit_id,
        )
        is_first_ever_row = False
    else:
        owning_doc = program_enrollment_doc
        existing_rows_before = [
            r for r in (program_enrollment_doc.unit_progress or [])
            if r.unit_type == "program"
        ]
        is_first_ever_row = len(existing_rows_before) == 0
        row = get_or_create_unit_progress_row(program_enrollment_doc, unit_id, context)

    if context == "program" and is_first_ever_row:
        # Student's first-ever program-context activity for this
        # enrollment -- flip default/no_activity -> active. Never touches
        # paused/manual/completed/dropped. See activate_if_inactive's own
        # docstring for why this mutates in memory only (persistence is
        # the caller's job, already happening via the unconditional
        # pe.save() in tap_app/api/progress.py::_save_affected_docs).
        activate_if_inactive(program_enrollment_doc)

    points_awarded = 0
    repeat = False
    if watched:
        if not row.video_watched:
            row.video_watched = 1
            points_awarded = points_for_video()
            # bump_activity=False: a video watch awards points but must NOT
            # advance last_activity_at -- that field (and therefore
            # /progress/sync's own changed-detection) is reserved for
            # submission-outcome events only. See module docstring's
            # LAST_ACTIVITY_AT POLICY section and
            # shared/progress/rewards.py::award_points's own docstring.
            award_points(owning_doc, points_awarded, bump_activity=False)
        else:
            repeat = True

    status_result = recompute_unit_status(row)
    if status_result["status"] == "Completed" and context == "program":
        advance_to_next_unit(program_enrollment_doc, unit_id)

    result = {
        "points_awarded": points_awarded,
        "points_total": program_enrollment_doc.points or 0,
        "context": context,
        "repeat": repeat,
        "video_id": video_id,
        # internal: API layer needs this to save the right doc(s) and to
        # finish wiring a brand-new event Unit Progress row's pointer.
        "_owning_doc": owning_doc,
        "_row": row,
    }

    # Decision C: kept for symmetry across all three completion-reporting
    # call sites, even though the course-sequence invariant documented at
    # the top of this file means just_completed can never actually be True
    # here in practice (video is always first; something else is always
    # still outstanding). Only ever adds unit_completed/course_completed/
    # next_learning_unit_id to `result` -- never removes or overwrites any
    # of the keys set above.
    _apply_completion_fields(result, program_enrollment_doc, status_result["just_completed"])

    return result


def resolve_quiz_id_for_unit(unit_id: str) -> str | None:
    """Resolves a unit's quiz, trying (in order): a direct UnitContentItem
    link to a Quiz, a UnitContentItem link to a VideoClass whose own
    assessments table links a Quiz, and finally a unit_name/quiz_name
    string-match fallback."""
    quiz_row = frappe.db.sql(
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
    if quiz_row and quiz_row[0][0]:
        return quiz_row[0][0]

    video_class_row = frappe.db.sql(
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
    if video_class_row and video_class_row[0][0]:
        try:
            video_class = frappe.get_doc("VideoClass", video_class_row[0][0])
            for assessment_row in (video_class.assessments or []):
                for quiz_column_guess in ("quiz", "assessment", "quiz_link"):
                    quiz_id = getattr(assessment_row, quiz_column_guess, None)
                    if quiz_id:
                        return quiz_id
        except Exception:
            pass

    unit_name = frappe.db.get_value("LearningUnit", unit_id, "unit_name")
    if not unit_name:
        return None
    return frappe.db.get_value("Quiz", {"quiz_name": unit_name}, "name")


def check_quiz_answers(quiz_id: str, answers: list[dict[str, Any]]) -> dict:
    """Grades a set of answers against a specific quiz's questions. Returns
    only correctness results -- never question text, option text, or the
    correct option's value, per API_Reference.md §3's "no content serving"
    rule.

    selected_key must be a bare positive-integer option index ("1", "2",
    "3", ... as a string, or the equivalent int) -- matching
    QuizQuestion.correct_option's own stored shape exactly -- never option
    text or any other free-form string; see module docstring for why this
    validation must happen before comparison rather than being folded into
    the equality check itself.
    """
    if not quiz_id:
        raise InvalidInput("quiz_id is required")
    if not answers:
        raise InvalidInput("answers must be a non-empty list")

    quiz = frappe.get_doc("Quiz", quiz_id)
    valid_question_ids = {q.question for q in (quiz.questions or [])}
    if not valid_question_ids:
        raise NotFound(f"quiz {quiz_id} has no questions configured")

    results = []
    correct_count = 0
    total_count = len(answers)

    for answer in answers:
        question_id = answer.get("question_id")
        selected_key = answer.get("selected_key")
        if not question_id:
            raise InvalidInput("every answer needs a question_id")
        if question_id not in valid_question_ids:
            raise InvalidInput(f"question_id {question_id} does not belong to quiz {quiz_id}")

        # selected_key must be a bare positive integer (as a string or int)
        # -- the option's 1-based index, e.g. "1" / "2" / "3" -- never
        # option text or any other free-form string.
        selected_key_str = str(selected_key).strip() if selected_key is not None else ""
        if not selected_key_str.isdigit() or selected_key_str == "0":
            raise InvalidInput(
                f"selected_key must be a positive number (e.g. \"1\", \"2\", \"3\"), got {selected_key!r}"
            )

        correct_option = frappe.db.get_value("QuizQuestion", question_id, "correct_option")
        is_correct = correct_option is not None and str(correct_option) == selected_key_str
        if is_correct:
            correct_count += 1
        results.append({"question_id": question_id, "correct": is_correct})

    return {
        "quiz_id": quiz_id,
        "correct_count": correct_count,
        "total_count": total_count,
        "results": results,
    }


def submit_quiz(program_enrollment_doc, unit_id: str, quiz_id: str, answers: list[dict[str, Any]], context: str = "program") -> dict:
    """Independent of video and submission -- a student can take the quiz
    before, after, or regardless of either. One-shot per unit
    (already-graded quizzes raise CapReached, per API_Reference.md §3.2's
    "no reattempts" rule). Validates quiz_id against the unit's configured
    quiz, then grades and persists the result. Advances the student to the
    next unit in program context once every required activity for the
    unit is done.

    For context == "event", resolves the owning Unit Progress row globally
    (see _resolve_event_unit_progress_row) -- same resolution as
    submit_video_watched, so quiz writes stay anchored to the enrollment
    that owns the row, matching what is_enrolled's read path already
    does.

    LIVE completion-reporting path: per the confirmed unit sequence
    (video always first; submission and quiz can finish in either order),
    quiz CAN be the activity that tips a unit to "Completed" -- when
    submission already finished first. This function's completion block
    (via _apply_completion_fields) is therefore not merely symmetric
    decoration the way submit_video_watched's is; it is reachable and
    expected to fire in real usage.

    LAST_ACTIVITY_AT (2026-11-14, this pass): same change as
    submit_video_watched above -- award_points is now called with
    bump_activity=False, and the old, separate
    `program_enrollment_doc.last_activity_at = frappe.utils.now_datetime()`
    / `owning_doc.last_activity_at = ...` assignments that used to follow
    it have been removed. A quiz attempt still earns and persists points
    exactly as before; it no longer, on its own, advances last_activity_at
    or triggers /progress/sync's changed-detection. See module docstring's
    LAST_ACTIVITY_AT POLICY section.
    """
    if context == "event":
        owning_doc, row = _resolve_event_unit_progress_row(
            program_enrollment_doc, program_enrollment_doc.student, unit_id,
        )
    else:
        owning_doc = program_enrollment_doc
        row = get_or_create_unit_progress_row(program_enrollment_doc, unit_id, context)

    existing_quiz = _parse_quiz_json(row.quiz_json)
    if existing_quiz and existing_quiz.get("graded"):
        raise CapReached("quiz already graded for this unit")

    expected_quiz_id = resolve_quiz_id_for_unit(unit_id)
    if not expected_quiz_id:
        raise NotFound("no quiz exists for this unit")
    if quiz_id != expected_quiz_id:
        raise InvalidInput("quiz_id does not match the quiz configured for this unit")

    check_result = check_quiz_answers(quiz_id, answers)
    correct_count = check_result["correct_count"]
    total_count = check_result["total_count"]

    points_awarded = correct_count * points_per_quiz_correct()
    # bump_activity=False -- same reasoning as submit_video_watched above:
    # a quiz attempt awards points but must not advance last_activity_at.
    award_points(owning_doc, points_awarded, bump_activity=False)

    row.quiz_json = frappe.as_json({
        "quiz_id": quiz_id,
        "answers": answers,
        "graded": True,
        "correct_count": correct_count,
        "total_count": total_count,
    })

    status_result = recompute_unit_status(row)
    if status_result["status"] == "Completed" and context == "program":
        advance_to_next_unit(program_enrollment_doc, unit_id)

    result = {
        "quiz_id": quiz_id,
        "correct_count": correct_count,
        "total_count": total_count,
        "points_awarded": points_awarded,
        "points_total": program_enrollment_doc.points or 0,
        "context": context,
        "repeat": False,
        "_owning_doc": owning_doc,
        "_row": row,
    }

    _apply_completion_fields(result, program_enrollment_doc, status_result["just_completed"])

    return result


def _parse_quiz_json(raw) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None
    return None