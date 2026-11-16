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


def _apply_completion_fields(result: dict, program_enrollment_doc, just_completed: bool, context: str) -> None:
    if not just_completed:
        return
    result["unit_completed"] = True
    if context != "program":
        return
    if is_course_complete(program_enrollment_doc):
        mark_course_completed(program_enrollment_doc.name)
        result["course_completed"] = True
    else:
        result["course_completed"] = False
        result["next_learning_unit_id"] = advance_to_next_unit(program_enrollment_doc, program_enrollment_doc.name) or \
            get_ordered_units_for_course_level(program_enrollment_doc.course_level)


# NOTE: submit_video_watched / submit_quiz bodies are unchanged from the
# original file (not reproduced here since this fix only touches
# _resolve_event_unit_progress_row / _finalize_event_enrollment_pointer
# above) — keep the rest of this file exactly as it already is.