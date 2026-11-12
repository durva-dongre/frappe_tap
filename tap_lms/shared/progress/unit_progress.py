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

FIX: a Unit Progress row is immutably tied to whichever ProgramEnrollment it
was created under -- it is NOT guaranteed to live under whatever enrollment
is currently "active" for a student (an enrollment can be renewed/replaced
while an old submission's or old event's progress row still points at the
previous one). Several call sites across the codebase used to resolve a row
by first loading get_active_program_enrollment(student_id) and then
searching that one doc's child table -- which silently misses any row that
belongs to a *different* (older) enrollment, producing wrong attempt counts
or wrongly "reset" event progress. find_unit_progress_row_for_submission and
the new find_unit_progress_row_by_name_global below are the two sanctioned
ways to look up a Unit Progress row without depending on "the active
enrollment" being the right scope -- they query the child table directly, by
submission or by the row's own global `name`, exactly the way
shared/jobs/event_maintenance.py already (correctly) does it. New code
should prefer these two over "load active enrollment, then search its
rows" whenever the row being searched for might not belong to the student's
*current* active enrollment.
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
    """The ONE correct implementation of "how many attempts has this
    submission used, and how many remain." Resolves the owning Unit Progress
    row directly (via find_unit_progress_row_for_submission), so it works
    correctly even when the submission belongs to a past/inactive
    enrollment -- unlike the three previous duplicated copies of this logic
    that only searched the student's *currently active* enrollment's
    unit_progress table and silently fell back to a wrong (1, cap) for any
    submission outside that scope.

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
    rows = [r for r in getattr(parent_doc, table_fieldname) if r.unit_type == unit_type]
    if not rows:
        return None
    rows.sort(key=lambda r: r.idx, reverse=True)
    return infer_last_activity_type(rows[0])