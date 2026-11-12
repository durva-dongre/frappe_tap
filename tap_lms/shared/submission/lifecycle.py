"""
shared/submission/lifecycle.py

check_attempt_cap + submit_artwork: the two Worker-facing operations that
create/gate a Submission row. Reattempt rule: only allowed if attempts are
left AND a prior submission exists AND that prior submission is terminal
(Completed/Failed) -- never while one is still Pending/Processing.

Direct SQL for the hot-path reads/writes; row lock via
shared.submission.locks around the cap re-check + insert so two concurrent
submit_artwork calls for the same (student, unit, context) can't both pass.

Worker route wiring: tap_app/api/submission.py::submit_artwork is the only
whitelisted entrypoint that calls this module's submit_artwork. Do not point
any Worker route at tap_lms.imgana.submission.submit_artwork or
tap_lms.imgana.demo_submission.submit_artwork instead -- those are the
WhatsApp/Glific-channel submission pipelines, with a completely different
signature, no attempt-cap enforcement, and no Unit Progress writes. They are
intentionally separate and must stay that way.
"""

from __future__ import annotations

import frappe

from shared.errors import CapReached, InvalidInput, NotFound
from shared.enrollment.active_batch import get_active_program_enrollment_name
from shared.progress.unit_progress import get_or_create_unit_progress_row, recompute_unit_status, is_quiz_graded
from shared.progress.rewards import award_points, points_for_submission_first_attempt, max_submission_attempts
from shared.submission.locks import lock_program_enrollment_row
from shared.submission.object_naming import parse_object_key, submission_type_from_ext


def resolve_learning_unit_for_assignment(assignment_id: str, context: str, student_id: str) -> str:
    """NOTE: the "tabUnitContentItem" columns queried here (content_reference,
    assignment) are not independently verified against that doctype's own
    JSON in this pass -- UnitContentItem's schema was not available for
    review. shared/progress/activities.py::resolve_quiz_id_for_unit already
    treats this same table's column names as uncertain (it tries several
    candidate column names and swallows exceptions). Until UnitContentItem's
    real schema is confirmed, this query is wrapped the same defensive way:
    if the column names are wrong, we fall through to the event/assignment
    resolution paths below rather than letting a raw "column does not exist"
    SQL error escape as an unmapped 500. tap_app/api/__init__.py's catch-all
    handler is a second safety net for this same risk, but failing over
    cleanly here means a schema mismatch degrades to NOT_FOUND (a documented,
    expected error code) instead of SERVER_ERROR.

    ACTION ITEM: once UnitContentItem's doctype JSON is available, replace
    this try/except with a direct, verified column reference and remove the
    defensive fallback.
    """
    try:
        row = frappe.db.sql(
            """
            SELECT parent FROM "tabUnitContentItem"
            WHERE content_reference = %s OR assignment = %s
            LIMIT 1
            """,
            (assignment_id, assignment_id),
        )
    except Exception:
        frappe.logger().warning(
            "resolve_learning_unit_for_assignment: tabUnitContentItem lookup "
            "failed (unverified column names) -- falling back to "
            "event/assignment resolution",
            exc_info=True,
        )
        row = None

    if row:
        return row[0][0]

    if context == "event":
        enrollment = frappe.db.sql(
            """
            SELECT ec.learning_unit
            FROM "tabStudent Event Enrollment" see
            JOIN "tabEvent Campaign" ec ON ec.name = see.event
            WHERE see.parent = %s AND see.status = 'active'
            ORDER BY see.idx DESC
            LIMIT 1
            """,
            (student_id,),
        )
        if enrollment:
            return enrollment[0][0]
        raise NotFound("no active event enrollment for this student")

    assignment = frappe.db.get_value("Assignment", assignment_id, ["vertical", "level"], as_dict=True)
    if not assignment:
        raise NotFound("assignment does not exist")

    unit = frappe.db.sql(
        """
        SELECT name FROM "tabLearningUnit"
        WHERE course_vertical = %s
        ORDER BY modified DESC
        LIMIT 1
        """,
        (assignment.vertical,),
    )
    if not unit:
        raise NotFound("could not resolve a learning unit for this assignment")
    return unit[0][0]


def _require_video_and_quiz_done(unit_progress_row) -> None:
    """§8.2 within-unit guard: video + quiz must be done before any
    submission, in both program and event contexts."""
    if not unit_progress_row.video_watched or not is_quiz_graded(unit_progress_row):
        raise InvalidInput("video and quiz must be completed before submitting for this unit")


def check_attempt_cap(student_id: str, assignment_id: str, context: str = "program") -> dict:
    pe_name = get_active_program_enrollment_name(student_id)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)
    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = get_or_create_unit_progress_row(pe, unit, context)

    _require_video_and_quiz_done(row)

    cap = max_submission_attempts()
    if row.submission_attempts >= cap:
        raise CapReached("submission attempt cap already reached")
    if row.submission and row.submission_attempts > 0:
        sub_status = frappe.db.get_value("Submission", row.submission, "status")
        if sub_status not in ("Completed", "Failed"):
            raise CapReached("previous submission still being reviewed")

    attempt_number = row.submission_attempts + 1
    pe.save(ignore_permissions=True)

    attempts_remaining = max(cap - row.submission_attempts, 0)
    return {"attempt_number": attempt_number, "attempts_remaining": attempts_remaining}


def submit_artwork(student_id: str, assignment_id: str, object_key: str, submission_id: str,
                    attempt, generation, md5, context: str, gcs_url: str) -> dict:
    parsed = parse_object_key(object_key)
    if parsed["assignment_id"] != assignment_id or parsed["student_id"] != student_id:
        raise InvalidInput("object_key does not match request")
    if int(attempt) != parsed["attempt"]:
        raise InvalidInput("object_key does not match attempt")
    # FIX: previously the submission_id parameter was accepted but never
    # cross-checked against the submission_id actually embedded in
    # object_key -- a caller could send a valid object_key for one upload
    # alongside a mismatched submission_id for a different one, and Frappe
    # would silently accept it (submission_id was discarded entirely). Now
    # validated AND persisted (see sub.worker_submission_id below) so gallery
    # promotion (shared/storage/gallery_promotion.py) can report the
    # Worker-minted id -- the one actually embedded in the GCS object key --
    # rather than Frappe's own unrelated autoname hash.
    if parsed["submission_id"] != submission_id:
        raise InvalidInput("submission_id does not match the id embedded in object_key")

    pe_name = get_active_program_enrollment_name(student_id)
    lock_program_enrollment_row(pe_name)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)

    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = get_or_create_unit_progress_row(pe, unit, context)

    _require_video_and_quiz_done(row)

    cap = max_submission_attempts()
    if row.submission_attempts >= cap:
        raise CapReached("submission attempt cap already reached")
    if row.submission and row.submission_attempts > 0:
        prior_status = frappe.db.get_value("Submission", row.submission, "status")
        if prior_status not in ("Completed", "Failed"):
            raise CapReached("previous submission still being reviewed")

    is_first_attempt = row.submission_attempts == 0
    submission_type = submission_type_from_ext(parsed["ext"])

    sub = frappe.new_doc("Submission")
    sub.assign_id = assignment_id
    sub.assignment_id_link = assignment_id
    sub.student_id = student_id
    sub.program_enrollment = pe.name
    sub.source = "tapapp"
    sub.submission_type = submission_type
    sub.submission_url = gcs_url
    sub.status = "Pending"
    sub.result_status = "Pending"
    sub.is_primary = 1
    sub.created_at = frappe.utils.now_datetime()
    # Persist the Worker-minted id embedded in the object key, distinct from
    # Frappe's own autoname-generated sub.name. See
    # tap_lms/doctype/submission/submission.json's worker_submission_id
    # field and shared/storage/gallery_promotion.py, which reports this
    # value (falling back to sub.name for legacy/WhatsApp-channel rows that
    # never went through this function) as the gallery's submission_id.
    sub.worker_submission_id = submission_id
    sub.insert(ignore_permissions=True)

    row.submission = sub.name
    row.submission_attempts += 1
    recompute_unit_status(row)

    points_awarded = 0
    if is_first_attempt:
        points_awarded = points_for_submission_first_attempt()
        award_points(pe, points_awarded)

    pe.save(ignore_permissions=True)

    attempts_remaining = max(cap - row.submission_attempts, 0)
    return {
        "name": sub.name,
        "status": sub.status,
        "created_at": sub.created_at.isoformat(),
        "assignment_id_link": sub.assignment_id_link,
        "attempt_number": row.submission_attempts,
        "attempts_remaining": attempts_remaining,
        "points_awarded": points_awarded,
        "points_total": pe.points,
        "context": context,
        "updated_at": int(pe.last_activity_at.timestamp()) if pe.last_activity_at else int(frappe.utils.now_datetime().timestamp()),
    }