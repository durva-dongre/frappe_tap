from __future__ import annotations

import frappe

from shared.errors import StudentNotFound


def get_profile_fields(student_id: str) -> dict:
    student = frappe.db.get_value(
        "Student",
        student_id,
        ["name1", "gender", "grade", "language", "state_id", "district_id", "school_id"],
        as_dict=True,
    )
    if not student:
        raise StudentNotFound(f"Student {student_id} not found")

    state_name = frappe.db.get_value("State", student.state_id, "state_name") if student.state_id else None
    district_name = frappe.db.get_value("District", student.district_id, "district_name") if student.district_id else None
    school_name = frappe.db.get_value("School", student.school_id, "name1") if student.school_id else None

    language_code = student.language
    if student.language:
        try:
            resolved_code = frappe.db.get_value("TAP Language", student.language, "language_code")
            if resolved_code:
                language_code = resolved_code
        except Exception:
            pass

    return {
        "student_id": student_id,
        "name1": student.name1,
        "gender": student.gender,
        "grade": student.grade,
        "language_code": language_code,
        "state_id": student.state_id,
        "district_id": student.district_id,
        "school_id": student.school_id,
        "state_name": state_name,
        "district_name": district_name,
        "school_name": school_name,
    }


def _resolve_assignment_id_for_unit(learning_unit: str) -> str | None:
    """Resolves a learning unit's own default assignment, for the gallery's
    assignment-id scope level (worker/src/storage/profileScope.ts's v6
    assignmentId field, worker/src/handlers/galleryHandlers.ts's default
    scope). This is the exact reverse of
    shared.submission.lifecycle.resolve_learning_unit_for_assignment's
    primary lookup (assignment_id -> learning_unit via UnitContentItem),
    querying the same UnitContentItem.content_type/.content shape in the
    other direction: given a unit, find the Assignment content item it
    owns, if any. Returns None if the unit has no assignment content item
    configured -- a unit backed only by a video/quiz (no submission
    activity) legitimately has no assignment, and this is not an error."""
    if not learning_unit:
        return None
    row = frappe.db.sql(
        """
        SELECT uci.content
          FROM "tabUnitContentItem" uci
         WHERE uci.parent = %s
           AND uci.content_type = 'Assignment'
           AND uci.content IS NOT NULL AND uci.content != ''
         LIMIT 1
        """,
        (learning_unit,),
    )
    if row and row[0][0]:
        return row[0][0]
    return None


def get_profile_scope(student_id: str) -> dict:
    """Returns the student's gallery-scoping fields, read by the Worker's
    storage/profileScope.ts (GET /gallery's scope resolution, cached and
    minted into scope_cache_token). Besides location/grade, this now also
    resolves and returns assignment_id: the student's current program-track
    learning unit's own default Assignment, if that unit has one
    configured.

    v-fix: assignment_id was previously entirely absent from this
    function's return dict, even though profileScope.ts's own v6 docstring
    (and galleryHandlers.ts's default-scope logic) already expected Frappe
    to supply it -- "the student's current/default assignment, resolved
    server-side by Frappe ... from their current learning unit." Without
    it, the Worker's gallery cascade could never start at its narrowest,
    most relevant level (assignment_id) for any student, and silently fell
    straight through to school/district/state scoping (or an empty page)
    on every request, regardless of whether the student actually had a
    current, gallery-eligible assignment. This resolves the student's
    current unit exactly the way auth's resume payload does (via
    get_active_program_enrollment + resolve_current_unit_for_track, using
    next_unit_for as the fallback for a student with no in-progress unit),
    then looks up that unit's own Assignment content item
    (_resolve_assignment_id_for_unit, the reverse of
    shared.submission.lifecycle.resolve_learning_unit_for_assignment's
    forward lookup). A student with no active enrollment, no resolvable
    current unit, or whose current unit has no Assignment content item
    configured gets assignment_id: None here -- the gallery's own cascade
    already treats that as "skip this level," which is the correct
    behavior, not an error.
    """
    student = frappe.db.get_value(
        "Student", student_id,
        ["grade", "state_id", "district_id", "school_id"], as_dict=True,
    )
    if not student:
        raise StudentNotFound(f"Student {student_id} not found")

    assignment_id = None
    try:
        from shared.enrollment.active_batch import get_active_program_enrollment
        from shared.enrollment.unit_rotation import next_unit_for
        from shared.progress.unit_progress import resolve_current_unit_for_track

        pe = get_active_program_enrollment(student_id)
        current_unit = resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for)
        assignment_id = _resolve_assignment_id_for_unit(current_unit)
    except StudentNotFound:
        # No active enrollment -- a student in this state legitimately has
        # no current unit to resolve an assignment from. Not an error for
        # gallery scoping purposes: assignment_id simply stays None, and
        # the gallery cascade moves on to its next configured level.
        pass

    return {
        "state_id": student.state_id,
        "district_id": student.district_id,
        "school_id": student.school_id,
        "grade": student.grade,
        "assignment_id": assignment_id,
    }