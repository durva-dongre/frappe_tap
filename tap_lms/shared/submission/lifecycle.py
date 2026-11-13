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
(submission link, attempt count, unit_status recompute), the first-attempt
points award, AND -- critically -- making the canonical submission_id
actually line up between the Worker's object key and the Frappe row.

Worker route wiring: tap_app/api/submission.py::submit_artwork is the only
whitelisted entrypoint the Worker calls for this. Do not point the Worker
directly at tap_lms.imgana.submission.submit_artwork -- it has no attempt-cap
or Unit Progress awareness of its own, so calling it directly would skip the
cap check and leave Unit Progress (and therefore unit_status/points/resume
state) never updated.

v-fix (this revision) -- canonical submission_id, end to end:

imgana.submit_artwork creates the Submission row under its OWN Frappe
autoname (e.g. "SUB-0503"), not the Worker-minted id embedded in object_key
(tapapp/{assignment_id}/{student_id}/{submission_id}-{attempt}.{ext}).
Previously nothing ever read that id back out of object_key, so the
"submission_id" the client got back from submit_artwork/sync/list/get
(Frappe's own `name`) never matched the id embedded in the GCS key the file
was actually uploaded to -- and shared/storage/gallery_promotion.py's
fallback to submission_doc.name always failed its own
^[a-z2-7]{6,16}$ regex (a Frappe autoname doesn't match that shape), so
notify_worker_gallery_index skipped every submission, forever.

Fixed here: immediately after imgana.submit_artwork creates the row, this
module parses the Worker-minted id back out of the SAME object_key it just
handed to imgana (via shared.submission.object_naming.parse_object_key,
the single source of truth for this key shape, matching the Worker's own
storage/keys.ts byte-for-byte), sets it on the created Submission doc as
`worker_submission_id`, and returns THAT value as `submission_id` in this
function's own response -- never `sub_name` (the Frappe autoname). Every
other submission-shaped read in this codebase (shared/profile/sync.py,
tap_app/api/submission.py's list/get) already prefers
`worker_submission_id` when present (falling back to `name` only for
legacy/non-TapApp submissions that have no object_key to parse one from),
so fixing the value at the point of creation, here, is what makes every
downstream read -- and shared/storage/gallery_promotion.py's gallery-index
notify -- agree on one consistent id for a TapApp-sourced submission.

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
from shared.submission.object_naming import parse_object_key


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
    the video prerequisite and the cap itself.

    v-fix: attempts_remaining is now computed against the UPCOMING attempt
    number (row.submission_attempts + 1) -- matching submit_artwork's own
    post-increment computation for the same (student, assignment, context)
    pair -- instead of against the pre-increment count still sitting in
    row.submission_attempts. Previously, for the Reference §4.1 example
    (cap = 2, attempt_number returned = 2), this function returned
    attempts_remaining = max(2 - 1, 0) = 1, while submit_artwork -- called
    moments later for that same attempt -- returns max(2 - 2, 0) = 0. That
    mismatch meant request_upload's attempts_remaining was always exactly
    one higher than submit_artwork's for the identical attempt, a
    client-visible inconsistency. Both functions now agree because both
    compute attempts_remaining from the SAME attempt_number (the one about
    to be/just made), not from two different counters.
    """
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

    # The attempt this call to request_upload is about to issue a key for.
    # submit_artwork will, moments later, increment row.submission_attempts
    # to this exact same number -- see submit_artwork below, where
    # attempts_remaining is derived from the POST-increment
    # row.submission_attempts, i.e. this same attempt_number. Computing
    # attempts_remaining here off of attempt_number (not the still-
    # pre-increment row.submission_attempts) is what keeps the two
    # functions' attempts_remaining in agreement for the same attempt.
    attempt_number = row.submission_attempts + 1
    attempts_remaining = max(cap - attempt_number, 0)

    pe.save(ignore_permissions=True)

    return {"attempt_number": attempt_number, "attempts_remaining": attempts_remaining}


def submit_artwork(student_id: str, assignment_id: str, submission_url: str, object_key: str | None = None,
                    context: str = "program") -> dict:
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

    object_key is the SAME Worker-issued key submission_url was built from
    (tap_app/api/submission.py passes both through unchanged). It is used
    here, after imgana creates the row, purely to recover the Worker-minted
    submission_id and persist it onto the new Submission doc as
    `worker_submission_id` -- see module docstring ("v-fix") for the full
    rationale. object_key is optional only so this function's signature
    stays backward compatible with any caller that has no key to pass (none
    exist in this codebase today; the TapApp wrapper always passes one) --
    submission_id then falls back to the Frappe autoname (`sub_name`) in
    that case, exactly as before this fix, and the row is simply not
    gallery-eligible under its own Worker-shaped id (gallery_promotion.py
    already treats "no worker_submission_id, and name doesn't match the
    Worker's shape" as "skip gallery indexing for this one").

    Returns the created submission's id as `submission_id` -- the Worker-
    minted id recovered from object_key when available, else the Frappe
    autoname. This is the ONLY identifier key in this response; `name` is
    deliberately never returned as a second key alongside it (see module
    docstring and tap_app/api/submission.py's own docstring for why one
    canonical identifier field removes a class of client-side bugs where
    the wrong field gets read for the same underlying value).
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

    # ------------------------------------------------------------------
    # v-fix: recover the Worker-minted submission_id from object_key (the
    # exact same key the Worker's request_upload issued and submit_artwork
    # confirmed on GCS before ever calling here) and persist it onto the
    # just-created Submission doc as `worker_submission_id`. This is the
    # ONE place that field is ever set for a TapApp-sourced submission --
    # shared/storage/gallery_promotion.py reads it back on the gallery-
    # index path, and every other submission-shaped read in this codebase
    # (shared/profile/sync.py, tap_app/api/submission.py) already prefers
    # it over `name` when present. Doing this immediately after imgana
    # creates the row, in the same request/transaction, means there is no
    # window where the row exists without its worker_submission_id set.
    #
    # object_key's shape is validated via parse_object_key (shared/
    # submission/object_naming.py), the single source of truth for this
    # key's byte-for-byte shape (matches the Worker's own storage/keys.ts).
    # A malformed/missing object_key is a plain, locally-detected bug in
    # the caller (the Worker always sends one from its own request_upload
    # issuance, confirmed on GCS) -- it does NOT roll back or fail the
    # whole submit_artwork call, since the Submission row itself was
    # already successfully created and must not be lost over a secondary,
    # recoverable bookkeeping field. It is logged loudly instead, and
    # submission_id for THIS response falls back to the Frappe autoname.
    # ------------------------------------------------------------------
    worker_submission_id: str | None = None
    if object_key:
        try:
            parsed = parse_object_key(object_key)
            worker_submission_id = parsed["submission_id"]
            frappe.db.set_value(
                "Submission",
                sub_name,
                "worker_submission_id",
                worker_submission_id,
                update_modified=False,
            )
        except InvalidInput:
            frappe.logger().error(
                f"submit_artwork: object_key={object_key!r} for newly created "
                f"Submission {sub_name} does not match the expected "
                f"tapapp/{{assignment_id}}/{{student_id}}/{{submission_id}}-"
                f"{{attempt}}.{{ext}} shape -- worker_submission_id will NOT be "
                f"set for this submission, so it will not be gallery-eligible "
                f"under a Worker-shaped id until backfilled. The Submission "
                f"row itself was created successfully and is not affected."
            )
    else:
        frappe.logger().warning(
            f"submit_artwork: no object_key supplied for newly created "
            f"Submission {sub_name} -- worker_submission_id will NOT be set. "
            f"The TapApp Worker path always supplies one; this indicates a "
            f"caller other than the documented Worker route."
        )

    # The canonical identifier returned to every caller (Worker included)
    # is the Worker-minted id when we were able to recover one, else the
    # Frappe autoname -- never both, and never a separate `name` key.
    canonical_submission_id = worker_submission_id or sub_name

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
        "submission_id": canonical_submission_id,
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