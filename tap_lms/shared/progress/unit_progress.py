"""
shared/progress/unit_progress.py

Generic helpers around a "Unit Progress" child table living on some parent
enrollment-shaped document (ProgramEnrollment.unit_progress). Any app with a
similar (student, unit, track) -> {video, quiz, submission} progress shape
can reuse this unchanged, as long as its child table has the same field
names (learning_unit, unit_type, video_watched, submission,
submission_attempts, quiz_json, unit_status, completed_at).

Every mutating path across every app goes through
get_or_create_unit_progress_row so "exactly one row per (learning_unit,
unit_type)" is enforced in exactly one place.

A Unit Progress row is immutably tied to whichever ProgramEnrollment it was
created under -- it is NOT guaranteed to live under whatever enrollment is
currently "active" for a student (an enrollment can be renewed/replaced
while an old submission's or old event's progress row still points at the
previous one). find_unit_progress_row_for_submission and
find_unit_progress_row_by_name_global below are the two sanctioned ways to
look up a Unit Progress row without depending on "the active enrollment"
being the right scope -- they query the child table directly, by submission
or by the row's own global `name`, the same way
shared/jobs/event_maintenance.py does it. New code should prefer these two
over "load active enrollment, then search its rows" whenever the row being
searched for might not belong to the student's *current* active enrollment.

resolve_last_activity_type is the single entrypoint for "what did this
student last do" across both tracks. Program context is safe to read
straight off the active ProgramEnrollment's own unit_progress table because
shared.enrollment.enrollment.create_enrollment guarantees exactly one
ProgramEnrollment per (student, course_level) for life -- see that module's
docstring. Event context is NOT safe to read that way, for the same reason
find_unit_progress_row_by_name_global exists: an event's Unit Progress row
can live on a ProgramEnrollment that is no longer the student's active one.
resolve_last_activity_type's event branch mirrors exactly what
shared.events.enrollment.is_enrolled already does to resolve that row
correctly, so both reads agree.
"""

from __future__ import annotations

import json
from typing import Optional

import frappe

from shared.errors import InvalidInput
from shared.submission.status import is_submission_complete

VALID_UNIT_TYPES = ("program", "event")
UNIT_PROGRESS_CHILD_TABLE = "tabUnit Progress"


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
    parent_doc is known to be the doc that actually owns the row (e.g. right
    after get_or_create_unit_progress_row returned it on the same request).
    For a row that might belong to a different/older enrollment than the
    student's current active one, use find_unit_progress_row_by_name_global
    instead."""
    for row in getattr(parent_doc, table_fieldname):
        if row.name == row_name:
            return row
    return None


def find_unit_progress_row_by_name_global(row_name: str) -> Optional[dict]:
    """Direct, global lookup of a Unit Progress child row by its own `name`,
    independent of which parent (ProgramEnrollment) currently owns it or
    whether that parent is the student's currently-active enrollment. A Unit
    Progress row's `name` is unique across the whole child table, so this is
    always safe and correct, unlike loading "the active enrollment" and
    hoping the row is still there."""
    if not row_name:
        return None
    rows = frappe.db.sql(
        f"""
        SELECT name, parent, unit_type, learning_unit, video_watched,
               quiz_json, submission, submission_attempts, unit_status
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
               quiz_json, submission, submission_attempts, unit_status
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

    Callers: tap_app/api/submission.py (list_submissions, get_submission) and
    shared/profile/sync.py (get_sync_payload, get_last_submission_payload)
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
    shared.submission.status.is_submission_complete -- the single place that
    set of values is defined -- instead of re-inlining the tuple here."""
    submission = row.submission if hasattr(row, "submission") else row.get("submission")
    if not submission:
        return False
    sub = frappe.db.get_value("Submission", submission, ["status", "result_status"], as_dict=True)
    if not sub:
        return False
    return sub.status == "Completed" and is_submission_complete(sub.result_status)


def recompute_unit_status_by_name(unit_progress_row_name: str) -> str:
    row = frappe.db.sql(
        f"""
        SELECT video_watched, quiz_json, submission, unit_status, completed_at
        FROM "{UNIT_PROGRESS_CHILD_TABLE}"
        WHERE name = %s
        LIMIT 1
        """,
        (unit_progress_row_name,),
        as_dict=True,
    )
    if not row:
        return "Not Started"
    row = row[0]

    quiz_graded = is_quiz_graded(row)
    submission_valid = is_submission_valid(row)
    any_touch = bool(row.video_watched) or quiz_graded or bool(row.submission)

    new_status = row.unit_status
    set_completed_at = False

    if row.video_watched and quiz_graded and submission_valid:
        new_status = "Completed"
        if not row.completed_at:
            set_completed_at = True
    elif any_touch and row.unit_status == "Not Started":
        new_status = "In Progress"

    if new_status != row.unit_status or set_completed_at:
        if set_completed_at:
            frappe.db.sql(
                f"""
                UPDATE "{UNIT_PROGRESS_CHILD_TABLE}"
                SET unit_status = %s, completed_at = NOW(), modified = NOW()
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
    return new_status


def recompute_unit_status(row) -> str:
    quiz_graded = is_quiz_graded(row)
    submission_valid = is_submission_valid(row)
    any_touch = bool(row.video_watched) or quiz_graded or bool(row.submission)

    if row.video_watched and quiz_graded and submission_valid:
        row.unit_status = "Completed"
        if not row.completed_at:
            row.completed_at = frappe.utils.now_datetime()
    elif any_touch and row.unit_status == "Not Started":
        row.unit_status = "In Progress"
    return row.unit_status


def infer_last_activity_type(row) -> Optional[str]:
    if is_quiz_graded(row):
        return "quiz"
    submission = row.submission if hasattr(row, "submission") else row.get("submission")
    if submission:
        return "submission"
    video_watched = row.video_watched if hasattr(row, "video_watched") else row.get("video_watched")
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