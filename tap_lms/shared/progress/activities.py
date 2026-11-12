"""
shared/progress/activities.py

Generic, reusable activity handlers for a Unit Progress row:
  - submit_video:            flips video_watched, one-shot, awards
                              points_for_video()
  - resolve_quiz_id_for_unit: resolves a unit_id to the quiz_id it's backed
                              by (UnitContentItem's Dynamic Link -> Quiz, or
                              UnitContentItem -> VideoClass -> AssessmentList
                              -> Quiz, with a unit_name/quiz_name fallback)
  - check_quiz_answers:      the standalone quiz-id-keyed correctness
                              checker -- takes an explicit quiz_id, grades
                              each answer against QuizQuestion.correct_option,
                              never returns the correct option's value
  - submit_quiz:             orchestrates the two above into the one-shot,
                              reward-granting activity: resolve quiz_id once,
                              check answers, award points, persist quiz_json

Every function here takes an already-loaded ProgramEnrollment doc rather
than a student_id -- the thin student_id-based wrapper lives in
tap_lms/tap_app/api/progress.py, which resolves the doc once via
shared.enrollment.active_batch.get_active_program_enrollment and passes it
down. Each function mutates the doc and its unit_progress rows in memory;
the CALLER saves exactly once per request, after calling whichever of these
it needs -- this keeps a single submit_video/submit_quiz call to one UPDATE
statement's worth of writes instead of several.

Neither function ever returns question text, option text, or the correct
option's value anywhere in its return dict -- only comparison results
(correct_count, total_count, points_awarded, and a per-question boolean).

FIX (resolve_quiz_id_for_unit): UnitContentItem is a Dynamic Link child
table -- content_type (Select: VideoClass/NoteContent/Quiz/Assignment/
CourseProject/TextMessageContent/VoiceNoteContent/ParentCallConfig) names
the doctype, and content (Dynamic Link, linked via content_type) holds that
doctype's document name. The previous version guessed at column names that
do not exist on this table (content_reference, assignment, videoclass,
video_class), which always failed -- and, worse, poisoned the open Postgres
transaction on the first failed query, so even the unit_name/quiz_name
fallback below it would then also raise InFailedSqlTransaction and never
run. This version queries content_type/content directly, so a quiz can
actually be resolved both when a unit's content item points straight at a
Quiz and when it points at a VideoClass whose own assessments table links a
Quiz.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from shared.errors import CapReached, InvalidInput, NotFound
from shared.progress.unit_progress import get_or_create_unit_progress_row, recompute_unit_status
from shared.progress.rewards import award_points, points_for_video, points_per_quiz_correct
from shared.enrollment.unit_rotation import advance_to_next_unit, get_ordered_units_for_course_level


def _validate_program_sequence(program_enrollment_doc, unit_id: str) -> None:
    """Cross-unit sequence check, program context only (§8.1 of the plan)."""
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


def submit_video(program_enrollment_doc, unit_id: str, watched: bool, context: str = "program") -> dict:
    if context == "program":
        _validate_program_sequence(program_enrollment_doc, unit_id)

    row = get_or_create_unit_progress_row(program_enrollment_doc, unit_id, context)

    points_awarded = 0
    repeat = False
    if watched:
        if not row.video_watched:
            row.video_watched = 1
            points_awarded = points_for_video()
            award_points(program_enrollment_doc, points_awarded)
        else:
            repeat = True

    recompute_unit_status(row)
    if row.unit_status == "Completed" and context == "program":
        advance_to_next_unit(program_enrollment_doc, unit_id)

    if context == "program":
        program_enrollment_doc.activity_this_week = (program_enrollment_doc.activity_this_week or 0) + 1

    program_enrollment_doc.last_activity_at = frappe.utils.now_datetime()

    return {
        "points_awarded": points_awarded,
        "points_total": program_enrollment_doc.points or 0,
        "context": context,
        "repeat": repeat,
    }


def resolve_quiz_id_for_unit(unit_id: str) -> str | None:
    # UnitContentItem is a Dynamic Link table: content_type names the
    # doctype, content holds that doctype's document name. A unit's content
    # item can point straight at a Quiz...
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

    # ...or at a VideoClass, whose own `assessments` child table (AssessmentList)
    # links a Quiz. Column name on that child row is unverified beyond
    # "quiz" (shared/submission/lifecycle.py notes the same uncertainty for
    # UnitContentItem itself), so the same defensive multi-guess is kept
    # here, scoped to just that one child row rather than the whole query.
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

        correct_option = frappe.db.get_value("QuizQuestion", question_id, "correct_option")
        is_correct = correct_option is not None and str(correct_option) == str(selected_key)
        if is_correct:
            correct_count += 1
        results.append({"question_id": question_id, "correct": is_correct})

    return {
        "quiz_id": quiz_id,
        "correct_count": correct_count,
        "total_count": total_count,
        "results": results,
    }


def submit_quiz(program_enrollment_doc, unit_id: str, answers: list[dict[str, Any]], context: str = "program") -> dict:
    row = get_or_create_unit_progress_row(program_enrollment_doc, unit_id, context)

    if not row.video_watched:
        raise InvalidInput("video must be watched before attempting the quiz for this unit")

    existing_quiz = _parse_quiz_json(row.quiz_json)
    if existing_quiz and existing_quiz.get("graded"):
        raise CapReached("quiz already graded for this unit")

    quiz_id = resolve_quiz_id_for_unit(unit_id)
    if not quiz_id:
        raise NotFound("no quiz exists for this unit")

    check_result = check_quiz_answers(quiz_id, answers)
    correct_count = check_result["correct_count"]
    total_count = check_result["total_count"]

    points_awarded = correct_count * points_per_quiz_correct()
    award_points(program_enrollment_doc, points_awarded)

    row.quiz_json = frappe.as_json({
        "quiz_id": quiz_id,
        "answers": answers,
        "graded": True,
        "correct_count": correct_count,
        "total_count": total_count,
    })

    recompute_unit_status(row)
    if row.unit_status == "Completed" and context == "program":
        advance_to_next_unit(program_enrollment_doc, unit_id)

    if context == "program":
        program_enrollment_doc.activity_this_week = (program_enrollment_doc.activity_this_week or 0) + 1

    program_enrollment_doc.last_activity_at = frappe.utils.now_datetime()

    return {
        "quiz_id": quiz_id,
        "correct_count": correct_count,
        "total_count": total_count,
        "points_awarded": points_awarded,
        "points_total": program_enrollment_doc.points or 0,
        "context": context,
        "repeat": False,
    }


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