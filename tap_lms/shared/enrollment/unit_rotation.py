from __future__ import annotations

import frappe


def get_ordered_units_for_course_level(course_level: str) -> list[str]:
    """Course Level.learning_units is a Table -> LearningUnitList, each row
    {learning_unit, week_no}. This is the single source of truth for
    program-track unit sequencing - never LearningUnit.order/course_vertical
    guessing."""
    if not course_level:
        return []
    doc = frappe.get_doc("Course Level", course_level)
    rows = list(doc.learning_units or [])
    rows.sort(key=lambda r: (r.week_no if r.week_no is not None else 0, r.idx))
    return [r.learning_unit for r in rows if r.learning_unit]


def next_unit_for(program_enrollment_doc) -> str | None:
    """First/next unit for this student: walks the ordered sequence and
    returns the first unit that has no program-context Unit Progress row yet,
    or whose row isn't Completed. None if every unit is done or the course
    has no units configured."""
    ordered = get_ordered_units_for_course_level(program_enrollment_doc.course_level)
    if not ordered:
        return None

    progress_by_unit = {
        row.learning_unit: row
        for row in (program_enrollment_doc.unit_progress or [])
        if row.unit_type == "program"
    }

    for unit in ordered:
        row = progress_by_unit.get(unit)
        if row is None or row.unit_status != "Completed":
            return unit
    return None


def advance_to_next_unit(program_enrollment_doc, completed_unit_id: str) -> None:
    """No current_learning_unit field exists on ProgramEnrollment to mutate.
    "Advancing" to the next unit is a live read (next_unit_for), computed
    fresh on every call, not a write anywhere on this doc. This function is
    kept only so existing call sites (shared/progress/activities.py) don't
    need to be deleted; it does bookkeeping-only sanity logging and performs
    no mutation of its own.

    (An earlier design here used a two-phase CLEAR/ASSIGN write pattern
    against a current_learning_unit field that no longer exists on this
    doctype. That field was removed in favor of always resolving "what's
    next" lazily via resolve_current_unit_for_track / next_unit_for on every
    read, which is simpler and race-free by construction -- there's no
    window where a stale write could be read, because nothing is ever
    written here. This docstring previously still described the old
    CLEAR/ASSIGN behavior; it no longer applies and has been removed to
    avoid confusing future readers into thinking this function mutates
    anything.)"""
    ordered = get_ordered_units_for_course_level(program_enrollment_doc.course_level)
    if completed_unit_id not in ordered:
        frappe.logger().warning(
            f"advance_to_next_unit: unit {completed_unit_id} is not in the "
            f"ordered sequence for course_level={program_enrollment_doc.course_level}"
        )
        return
    # No further action needed - resolve_current_unit_for_track /
    # next_unit_for recompute the next unit lazily on every read.