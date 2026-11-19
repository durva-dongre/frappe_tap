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
    if not just_completed:
        return
    result["unit_completed"] = True
    if context != "program":
        return

    advance_to_next_unit(program_enrollment_doc, unit_id)

    if is_course_complete(program_enrollment_doc):
        mark_course_completed(program_enrollment_doc.name)
        result["course_completed"] = True
    else:
        result["course_completed"] = False
        result["next_learning_unit_id"] = next_unit_for(program_enrollment_doc)


def submit_video_watched(program_enrollment_doc, unit_id: str, video_id: str, watched: bool, context: str = "program") -> dict:
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