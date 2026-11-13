"""
shared/submission/lifecycle.py

check_attempt_cap + submit_artwork: the two Worker-facing operations that
gate/create a Submission row. Reattempt rule: only allowed if attempts are
left AND a prior submission exists AND that prior submission is terminal
(Completed/Failed) -- never while one is still Pending/Processing.

Row lock via shared.submission.locks around the cap re-check + write so two
concurrent submit_artwork calls for the same (student, unit, context) can't
both pass.

submit_artwork does NOT create the Submission row itself -- it delegates
that to tap_lms.imgana.submission.submit_artwork, the same pipeline used by
the WhatsApp channel (RabbitMQ enqueue, Gemini/AI feedback generation,
Glific flow delivery). imgana's function takes a plain, already-public
submission URL and handles its own media detection; this module is
responsible for everything imgana's function doesn't do: attempt-cap
enforcement, the video prerequisite gate, the Unit Progress row write
(submission link, attempt count, unit_status recompute), and the
first-attempt points award.

imgana.submit_artwork is called as a plain Python function call (not over
HTTP), so this module's own tap_app_method-enforced auth is what gates the
Worker-facing surface -- imgana.submit_artwork's own allow_guest=True is
irrelevant here since it is never reached directly by an unauthenticated
caller through this path.

Worker route wiring: tap_app/api/submission.py::submit_artwork is the only
whitelisted entrypoint the Worker calls for this. Do not point the Worker
directly at tap_lms.imgana.submission.submit_artwork -- it has no attempt-cap
or Unit Progress awareness of its own, so calling it directly would skip the
cap check and leave Unit Progress (and therefore unit_status/points/resume
state) never updated.

submit_artwork returns only `submission_id` as the identifier -- never a
bare `name` field alongside it. Every other submission-shaped response in
this API (tap_app/api/submission.py's list/get, shared/profile/sync.py's
sync/last_submission) emits only submission_id for the same reason:
submission_id alone carries the exact same value Frappe's own document
name holds for this source, so producing `name` as a second key would only
give a caller two ways to read one value, which is exactly the kind of
ambiguity the contract's single-identifier rule exists to avoid. Fixing
this at the source, here, means no caller downstream -- Worker or
otherwise -- has to remember to strip the field itself.

resolve_learning_unit_for_assignment's primary lookup queries
tabUnitContentItem.content_type / tabUnitContentItem.content -- the actual
schema for that doctype, the same shape every other resolver in this
codebase queries against (e.g.
shared/progress/activities.py::resolve_video_id_for_unit /
resolve_quiz_id_for_unit). That query is wrapped in a savepoint
(release/rollback) as defense in depth: because Postgres (unlike MySQL)
aborts the entire transaction on any SQL error until an explicit ROLLBACK,
a savepoint here means a future schema mismatch on this query degrades to
the documented fallback paths (and ultimately NOT_FOUND) instead of
poisoning the whole surrounding transaction -- every later query in the
same request, including the caller's own error-logging write, would
otherwise fail with "current transaction is aborted" until the request
unwound.
"""

from __future__ import annotations

import frappe

from shared.errors import CapReached, InvalidInput, NotFound
from shared.enrollment.active_batch import get_active_program_enrollment_name
from shared.progress.unit_progress import get_or_create_unit_progress_row, recompute_unit_status
from shared.progress.rewards import award_points, points_for_submission_first_attempt, max_submission_attempts
from shared.submission.locks import lock_program_enrollment_row


def resolve_learning_unit_for_assignment(assignment_id: str, context: str, student_id: str) -> str:
    """Resolves which LearningUnit an assignment_id belongs to, for cap
    checking and Unit Progress bookkeeping. Tries a direct UnitContentItem
    link first (content_type == 'Assignment', content == assignment_id --
    see module docstring for the schema this relies on), then falls back
    to event/assignment-vertical resolution. The savepoint around the
    primary query means a schema mismatch here degrades to the fallback
    paths below (and ultimately NOT_FOUND, a documented error) instead of
    aborting the whole surrounding transaction.
    """
    try:
        frappe.db.sql("SAVEPOINT resolve_unit_for_assignment")
        row = frappe.db.sql(
            """
            SELECT parent FROM "tabUnitContentItem"
            WHERE content_type = 'Assignment' AND content = %s
            LIMIT 1
            """,
            (assignment_id,),
        )
        frappe.db.sql("RELEASE SAVEPOINT resolve_unit_for_assignment")
    except Exception:
        frappe.db.sql("ROLLBACK TO SAVEPOINT resolve_unit_for_assignment")
        frappe.logger().warning(
            "resolve_learning_unit_for_assignment: tabUnitContentItem lookup "
            "failed -- falling back to event/assignment resolution",
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


def _require_video_done(unit_progress_row) -> None:
    """Within-unit guard: video must be watched before any submission, in
    both program and event contexts. Quiz is independent of submission --
    a student can submit before, after, or without ever taking the quiz."""
    if not unit_progress_row.video_watched:
        raise InvalidInput("video must be completed before submitting for this unit")


def check_attempt_cap(student_id: str, assignment_id: str, context: str = "program") -> dict:
    """Reports the student's current attempt number and how many attempts
    remain for this assignment, without creating anything. Also enforces
    the video prerequisite and the cap itself."""
    pe_name = get_active_program_enrollment_name(student_id)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)
    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = get_or_create_unit_progress_row(pe, unit, context)

    _require_video_done(row)

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


def submit_artwork(student_id: str, assignment_id: str, submission_url: str, context: str = "program") -> dict:
    """Re-checks the attempt cap and video prerequisite under a row lock,
    then hands off the actual Submission creation to imgana's
    submit_artwork pipeline. submission_url is a plain, already-public URL
    the caller provides directly -- not signed or validated against any
    object-key shape here; it is passed straight through to imgana, which
    handles its own media-type detection and storage for the "tapapp"
    source. tap_app/api/submission.py::submit_artwork is responsible for
    building this URL from the Worker's object_key before calling here;
    see that file's docstring for why the object_key -> URL conversion
    lives there and not in this module.

    Returns the created submission's id as `submission_id` -- the only
    identifier key in this response. Frappe's own document name is the
    same value under the hood, but is never returned as a separate `name`
    field (see module docstring); client code, Worker-side and anywhere
    else, should read submission_id exclusively.
    """
    if not submission_url or not isinstance(submission_url, str):
        raise InvalidInput("submission_url missing")

    pe_name = get_active_program_enrollment_name(student_id)
    lock_program_enrollment_row(pe_name)
    pe = frappe.get_doc("ProgramEnrollment", pe_name)

    unit = resolve_learning_unit_for_assignment(assignment_id, context, student_id)
    row = get_or_create_unit_progress_row(pe, unit, context)

    _require_video_done(row)

    cap = max_submission_attempts()
    if row.submission_attempts >= cap:
        raise CapReached("submission attempt cap already reached")
    if row.submission and row.submission_attempts > 0:
        prior_status = frappe.db.get_value("Submission", row.submission, "status")
        if prior_status not in ("Completed", "Failed"):
            raise CapReached("previous submission still being reviewed")

    is_first_attempt = row.submission_attempts == 0

    from tap_lms.imgana.submission import submit_artwork as _imgana_submit_artwork

    # imgana.submit_artwork reports failure via frappe.local.response rather
    # than raising, so a plain call returns None on failure instead of
    # throwing. Capture and inspect frappe.local.response explicitly to
    # detect that case and surface it as a normal SharedError.
    frappe.local.response.pop("success", None)
    frappe.local.response.pop("status", None)
    frappe.local.response.pop("error_detail", None)

    imgana_result = _imgana_submit_artwork(
        assignment_id=assignment_id,
        student_id=student_id,
        submission=submission_url,
        source="tapapp",
    )

    if not imgana_result or not imgana_result.get("success"):
        failure_status = (imgana_result or {}).get("status") or frappe.local.response.get("status")
        failure_detail = (imgana_result or {}).get("error_detail") or frappe.local.response.get("error_detail")
        frappe.local.response.pop("success", None)
        frappe.local.response.pop("status", None)
        frappe.local.response.pop("error_detail", None)
        if failure_status == "not_found":
            raise NotFound(failure_detail or "assignment not found")
        raise InvalidInput(failure_detail or "submission could not be created")

    sub_name = imgana_result["submission_id"]

    row.submission = sub_name
    row.submission_attempts += 1
    recompute_unit_status(row)

    points_awarded = 0
    if is_first_attempt:
        points_awarded = points_for_submission_first_attempt()
        award_points(pe, points_awarded)

    pe.save(ignore_permissions=True)

    attempts_remaining = max(cap - row.submission_attempts, 0)
    sub_status = frappe.db.get_value("Submission", sub_name, "status") or "Pending"
    sub_created_at = frappe.db.get_value("Submission", sub_name, "created_at")

    return {
        "submission_id": sub_name,
        "status": sub_status,
        "created_at": (sub_created_at or frappe.utils.now_datetime()).isoformat(),
        "assignment_id_link": assignment_id,
        "attempt_number": row.submission_attempts,
        "attempts_remaining": attempts_remaining,
        "points_awarded": points_awarded,
        "points_total": pe.points,
        "context": context,
        "updated_at": int(pe.last_activity_at.timestamp()) if pe.last_activity_at else int(frappe.utils.now_datetime().timestamp()),
    }