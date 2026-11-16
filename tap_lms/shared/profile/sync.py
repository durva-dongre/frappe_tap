from __future__ import annotations

import frappe

from shared.enrollment.active_batch import get_active_program_enrollment
from shared.enrollment.enrollment import activate_if_inactive
from shared.progress.unit_progress import (
    resolve_current_unit_for_track,
    resolve_last_activity_type_for_track,
    attempt_info_for_submission,
    find_unit_progress_row_for_submission,
)
from shared.enrollment.unit_rotation import next_unit_for, is_course_complete
from shared.progress.rewards import points_for_submission_review_valid, gems_for_submission_review_valid
from shared.submission.status import is_reward_eligible, is_submission_complete
from shared.submission.object_naming import resolve_wire_submission_id
from shared.profile.student import get_profile_fields


def _mark_feedback_viewed_if_pending(pe_doc) -> None:
    if pe_doc.stage == "feedback_tobe_viewed":
        pe_doc.stage = "feedback_viewed"
        pe_doc.save(ignore_permissions=True)


def _activate_if_inactive_and_persist(pe_doc) -> bool:
    """Wraps shared.enrollment.enrollment.activate_if_inactive for the two
    read-path callers in this file (get_sync_payload,
    get_profile_select_payload), neither of which otherwise calls
    pe_doc.save() as part of its normal flow (unlike
    shared/progress/activities.py's callers, which always save pe via
    tap_app/api/progress.py::_save_affected_docs). activate_if_inactive
    itself only mutates pe_doc.status in memory and explicitly documents
    that persistence is the caller's responsibility -- this helper is
    that persistence step, using frappe.db.set_value directly (not a full
    pe_doc.save()) so a read-only call site doesn't pick up an unrelated,
    accidental full-document save as a side effect of this one status
    flip.

    Note: activate_if_inactive only ever flips "default"/"no_activity" ->
    "active" -- it never touches "completed", so calling this on an
    already-completed pe_doc (now resolvable for reads, per
    shared.enrollment.active_batch's fallback -- see that module) is a
    safe no-op, correctly returning False.

    Returns the same bool activate_if_inactive returned (True iff the
    status actually changed), so both callers can use it to decide
    whether to add the "status" field to their response -- only when this
    call just flipped it, never otherwise, per the "absent means
    unchanged" convention this project uses for last_submission and
    extends to this status-change notification."""
    changed = activate_if_inactive(pe_doc)
    if changed:
        frappe.db.set_value(
            "ProgramEnrollment", pe_doc.name, "status", pe_doc.status, update_modified=False,
        )
    return changed


def _find_last_submission_row(student_id: str, program_enrollment_name: str, last_updated_epoch: int) -> dict | None:
    """Returns the student's most recently UPDATED submission that (a)
    belongs to the CURRENTLY ACTIVE ProgramEnrollment, and (b) has
    actually changed since last_updated_epoch -- not just the
    newest-modified Submission row for this student_id across all
    history.

    Both conditions are required:

    - Scoping to program_enrollment_name excludes submissions left over
      from a prior/inactive enrollment (a dropped-and-reenrolled student,
      a course-level change, stale/test rows, etc.). Without this, a
      long-dead submission belonging to a different enrollment could be
      reported as "the last submission" for the student's current
      session, which makes no sense to a client resuming the student's
      CURRENT enrollment. Note: this scoping means a submission that
      belongs to a DIFFERENT (non-active, e.g. rotated-away) enrollment --
      including an event-track submission anchored to a past enrollment
      via shared.progress.activities._resolve_event_unit_progress_row --
      is never surfaced via sync's own last_submission block; event-track
      resume state is intentionally reported exclusively via
      shared.events.enrollment.is_enrolled (API_Reference.md §8.2).

    - Filtering `modified > last_updated_epoch` directly in SQL means
      this function only ever returns a row that is genuinely newer than
      what the caller already has. The enrollment's own last_activity_at
      is NOT used for this comparison, since that field can advance for
      reasons that have nothing to do with a submission (e.g. a
      video-watch or quiz call) -- comparing against it instead would let
      an old, previously-seen submission be reported as new over and
      over, each time re-stamped with the enrollment's current epoch
      instead of its own. Gating directly on the submission's own
      `modified` here means a row is only ever returned once, the first
      time its own modified timestamp crosses last_updated_epoch.

    `modified` is Frappe's own standard last-write timestamp, bumped on
    every `doc.save()` -- including every grading-pipeline update
    (feedback_processor.py, review_result.py's status/reward writes) --
    so ordering by `modified desc` within the filtered set still reliably
    surfaces whichever submission's state most recently changed.
    created_at is kept as a tiebreaker for the rare case of two rows with
    an identical modified timestamp.
    """
    from datetime import datetime

    filters = {"program_enrollment": program_enrollment_name}
    if last_updated_epoch:
        cutoff = datetime.fromtimestamp(last_updated_epoch)
        filters["modified"] = [">", cutoff]

    rows = frappe.get_all(
        "Submission",
        filters=filters,
        fields=["name", "assignment_id_link", "status", "result_status", "submission_url", "grade",
                "overall_feedback_translated", "audio_feedback_url",
                "program_enrollment", "created_at", "modified", "feedback_ready_processed_at"],
        order_by="modified desc, created_at desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


def _grading_award_for_submission(sub: dict) -> tuple[int, int]:
    """Derives (points_awarded, gems_awarded) for THIS submission's
    grading bonus. There is no dedicated storage column for this on
    Submission, by design (no doctype change needed) -- the amount is
    recovered from what already exists:

      - shared.submission.status.is_reward_eligible(sub.result_status)
        tells us whether this particular submission's result ever
        qualifies for the grading-time bonus at all ("Success - Original"
        only -- a "Success - Flagged" result is complete but never earns
        this, per shared/submission/status.py's own completion-vs-reward
        distinction);
      - sub.feedback_ready_processed_at being set tells us the one-time
        award for this submission has actually been granted -- this is
        the exact same guard shared.submission.review_result.
        handle_review_result uses itself, via _already_rewarded, to avoid
        a double award;
      - the amount itself is always the CURRENT Shared Settings
        configured value (points_submission_review_valid /
        gems_submission_review_valid).

    Returns (0, 0) for a submission that is not reward-eligible, or is
    reward-eligible but not yet actually rewarded.

    Read ONLY by get_sync_payload / get_last_submission_payload /
    get_profile_select_payload below -- all of which are gated (sync/
    last_submission by an updated_at/last_updated epoch comparison;
    get_profile_select_payload by being a one-shot call on login, not a
    repeatable historical read) -- so a given award is only ever surfaced
    to the app a bounded number of times, never on every page view of
    submission history. submission.list / submission.get do NOT call
    this -- see tap_app/api/submission.py's module docstring for why a
    one-time award field has no place on an ungated historical read.
    """
    result_status = sub.get("result_status")
    if not is_reward_eligible(result_status):
        return 0, 0
    if not sub.get("feedback_ready_processed_at"):
        return 0, 0
    return points_for_submission_review_valid(), gems_for_submission_review_valid()


def _completion_fields_for_submission(last_submission: dict, pe) -> dict:
    """Derives unit_completed / course_completed / next_learning_unit_id
    for THIS submission block, computed LIVE on read -- no stored flag,
    same "compute on read" style this file already uses for
    points_awarded/gems_awarded above (_grading_award_for_submission).

    A submission's own grading is what actually drives
    shared/submission/review_result.py::handle_review_result's completion
    detection (via recompute_unit_status_by_name's just_completed signal)
    at the time grading happened -- but that moment-in-time signal is not
    persisted anywhere (by design: no new doctype field). For a sync/
    last_submission READ happening some time after grading, this function
    re-derives "is the unit this submission belongs to currently
    Completed" from the Unit Progress row's CURRENT unit_status, rather
    than trying to recover "was this submission specifically what
    completed it" after the fact.

    COURSE-COMPLETION SCOPING: course_completed / next_learning_unit_id
    are only meaningful for a PROGRAM-track row, and only when that row's
    owning enrollment is the SAME enrollment as `pe` (the currently active
    one passed in by the caller). Two distinct problems are guarded
    against here:

      1. unit_type != "program": an event-track submission's owning Unit
         Progress row completing has no course-level meaning at all (see
         shared/progress/activities.py's module docstring for the full
         reasoning) -- reporting course_completed for an event submission
         would be simply wrong.

      2. row["parent"] != pe.name: even for a program-track row, if its
         owning enrollment differs from `pe` (the currently ACTIVE
         enrollment this function was called with), evaluating
         is_course_complete(pe) would describe a DIFFERENT course level's
         completion state than the one this submission actually belongs
         to -- a stale cross-enrollment read, not a lie about THIS
         submission's own unit, but still describing the wrong course.
         This can happen for a submission whose owning enrollment has
         since been superseded as "active" (e.g. the student started a
         new course-level enrollment after this submission was made, but
         before this sync call); _find_last_submission_row's own
         `program_enrollment: pe.name` filter (see that function's
         docstring) already prevents SYNC from ever selecting such a
         submission as `last_submission` in practice, but
         get_last_submission_payload below calls this same helper and
         this guard is kept here too as defense in depth, not relying
         solely on the caller's own filtering.

    In either guarded case, the submission is still reported as
    unit_completed (the unit itself genuinely finished), but
    course_completed / next_learning_unit_id are simply absent --
    consistent with this file's existing "absent means nothing to add"
    convention for last_submission's own presence/absence.

    Returns {} (no keys at all) when the owning Unit Progress row can't
    be resolved, or its unit_status is not "Completed".
    """
    row = find_unit_progress_row_for_submission(last_submission.name)
    if not row or row.get("unit_status") != "Completed":
        return {}

    if row.get("unit_type") != "program" or row.get("parent") != pe.name:
        return {"unit_completed": True}

    fields = {"unit_completed": True}
    if is_course_complete(pe):
        fields["course_completed"] = True
        # No next_learning_unit_id key at all when the course is complete.
    else:
        fields["course_completed"] = False
        fields["next_learning_unit_id"] = next_unit_for(pe)
    return fields


def _resolve_last_completed_unit_for_track(pe, table_fieldname: str = "unit_progress") -> str | None:
    """Returns the learning_unit of the most recently completed
    PROGRAM-track Unit Progress row on `pe`, or None if no program-track
    unit has ever been completed on it.

    This exists so a client can still show "the last thing you finished"
    once a course is fully complete: resolve_current_unit_for_track's own
    fallback (next_unit_for) returns None once every unit is Completed,
    since there genuinely is no "current" (in-progress) unit left --
    correct for its own purpose, but it means current_learning_unit goes
    to None forever once a course finishes, with nothing in the payload
    identifying which unit was last worked on. This function is called
    ONLY when the course is actually complete (see its call sites in
    get_sync_payload and get_profile_select_payload below), so it never
    shadows or conflicts with the normal in-progress current_learning_unit
    value.

    Ties (more than one row completed at the exact same recorded moment)
    are broken by child-table idx, taking the highest -- the same
    tiebreak resolve_current_unit_for_track already uses elsewhere in
    this codebase, kept consistent rather than introducing a second,
    different ordering rule.
    """
    rows = [
        r for r in getattr(pe, table_fieldname)
        if r.unit_type == "program" and r.unit_status == "Completed"
    ]
    if not rows:
        return None
    rows.sort(key=lambda r: (r.completed_at or r.modified, r.idx), reverse=True)
    return rows[0].learning_unit


def get_sync_payload(student_id: str, last_updated_epoch: int) -> dict:
    """
    Status auto-activation: every call to this function (i.e. every
    /progress/sync call) checks whether pe.status is currently "default"
    or "no_activity" and, if so, flips it to "active"
    (shared.enrollment.enrollment.activate_if_inactive, persisted via
    _activate_if_inactive_and_persist). This happens BEFORE the
    changed/unchanged short-circuit below, so a sync call that would
    otherwise report changed: false still performs the activation check
    and persists it if it fires -- the student's enrollment status is
    allowed to become visibly "active" purely from a login/sync read,
    independent of whether there happens to be new submission/points
    state to report in the same call. For a "completed" pe, this check is
    a no-op (activate_if_inactive never touches "completed" -- see that
    function's docstring), which is correct: sync must keep working for a
    completed enrollment without ever resurrecting its status.

    The "status" field is added to the returned payload ONLY when this
    call's activation check just flipped the status (never otherwise) --
    the "absent means unchanged" convention this file already uses for
    last_submission is extended to this field. A sync call that finds the
    enrollment already active/paused/manual/completed/dropped reports no
    "status" key at all.

    COMPLETED-ENROLLMENT BEHAVIOR: get_active_program_enrollment (via
    shared.enrollment.active_batch's read fallback) now successfully
    resolves a student's enrollment even when it is the only one and it
    is "completed" -- previously this raised StudentNotFound and sync
    stopped working entirely the moment a student's course finished. With
    that fixed, this function's normal flow (points/gems/
    current_learning_unit/last_activity_type/last_submission) all
    continue to work unchanged for a completed enrollment: points/gems
    are still real, current fields on the doc; last_submission lookups
    are unaffected by pe.status. The one field that changes behavior is
    current_learning_unit, which goes to None once every unit is
    Completed (next_unit_for's own, correct behavior) -- so this function
    additionally populates last_completed_unit (via
    _resolve_last_completed_unit_for_track) whenever the course is fully
    complete, so a client can still show which unit the student finished
    last, even though there is no "current" unit left to report.
    """
    pe = get_active_program_enrollment(student_id)

    status_just_changed = _activate_if_inactive_and_persist(pe)

    current_epoch = int(pe.last_activity_at.timestamp()) if pe.last_activity_at else 0

    if current_epoch <= (last_updated_epoch or 0):
        payload = {"changed": False, "updated_at": last_updated_epoch or current_epoch}
        if status_just_changed:
            payload["status"] = pe.status
        return payload

    course_complete = is_course_complete(pe)
    current_learning_unit = resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for)

    payload = {
        "changed": True,
        "updated_at": current_epoch,
        "points": pe.points or 0,
        "gems": pe.gems or 0,
        "current_learning_unit": current_learning_unit,
        "last_activity_type": resolve_last_activity_type_for_track(pe, "program"),
    }
    if course_complete:
        # current_learning_unit is None here (every program-track unit is
        # Completed) -- surface the last completed unit instead, so the
        # client still has a unit identifier to show even though the
        # course is finished. See _resolve_last_completed_unit_for_track's
        # own docstring.
        payload["course_completed"] = True
        payload["last_completed_unit"] = _resolve_last_completed_unit_for_track(pe)
    if status_just_changed:
        payload["status"] = pe.status
    if last_submission := _find_last_submission_row(student_id, pe.name, last_updated_epoch or 0):
        # attempt_info_for_submission (shared/progress/unit_progress.py)
        # resolves the owning Unit Progress row globally, by submission
        # name, with no dependency on "active enrollment" being the right
        # scope -- harmless here since _find_last_submission_row is now
        # itself scoped to the active enrollment's own name, so the
        # submission it returns always belongs to pe.
        #
        # Frappe forwards the submission's own stored URLs (submission_url,
        # audio_feedback_url) directly, under "view_url" and
        # "overall_feedback_audio_url" -- the Worker is responsible for
        # signing/sharing these on to the frontend. Frappe does not need to
        # know the object-key shape to do this.
        #
        # Identifier: submission_id is recovered via resolve_wire_submission_id
        # (see _build_submission_block) -- never a bare `name` field.
        #
        # Score: the submission's numeric mark is returned as `points`, not
        # `score` -- Submission.grade is the underlying stored field, but
        # the wire field name is `points` everywhere a submission's mark is
        # reported, matching how the rest of this API already talks about
        # points (points_total, points_awarded, points_tier).
        #
        # updated_at here is the submission's OWN modified epoch (set
        # below), not pe's current_epoch -- see that assignment for why.
        own_epoch = int(last_submission.modified.timestamp()) if last_submission.modified else current_epoch
        payload["last_submission"] = {
            **_build_submission_block(last_submission, pe),
            # The submission's own last-modified epoch, not the enrollment's
            # current_epoch -- current_epoch can advance for reasons
            # unrelated to this submission (a video watch, a quiz), and
            # stamping an unrelated epoch onto this block would make an
            # already-seen submission look freshly changed on every such
            # call. _find_last_submission_row already guarantees own_epoch
            # is newer than last_updated_epoch whenever a row is returned
            # at all, so this is always a genuine, bounded "newly changed"
            # signal for this specific submission.
            "updated_at": own_epoch,
        }
        _mark_feedback_viewed_if_pending(pe)
    return payload


# Change to tap_lms/shared/profile/sync.py::_build_submission_block
#
# What changed: this function previously built the last_submission block with
# no "context" key at all, while tap_app/api/submission.py's
# _submission_wire_shape (used by list_submissions/get_submission) always
# includes it. The Worker's own resign.ts carried a doc-comment claiming
# context was "sent on every submission-shaped response (list/get/sync/
# last_submission)" -- true for list/get, false for sync/last_submission,
# since both of those go through this exact function. Fixed by resolving the
# owning Unit Progress row's unit_type the same way list/get derive context,
# and adding it to the returned dict as "context".
#
# find_unit_progress_row_for_submission is already imported at the top of
# sync.py; no new import is needed for this specific change (it's used
# elsewhere in the same file already). row["unit_type"] is "program"|"event"
# when a row resolves, or this block reports None when it doesn't -- an
# unresolved context is a real, legitimate value (see resign.ts's updated
# RawSubmission.context type), not an error.

def _build_submission_block(last_submission: dict, pe) -> dict:
    """Builds the last_submission wire shape. submission_id is recovered via
    resolve_wire_submission_id -- NOT last_submission.name directly. Also
    threads in unit_completed/course_completed/[next_learning_unit_id] via
    _completion_fields_for_submission, and now "context" (program|event|None),
    matching tap_app/api/submission.py's list/get shape exactly."""
    attempt_number, attempts_remaining = attempt_info_for_submission(last_submission.name)
    points_awarded, gems_awarded = _grading_award_for_submission(last_submission)
    row = find_unit_progress_row_for_submission(last_submission.name)
    block = {
        "submission_id": resolve_wire_submission_id(last_submission),
        "assignment_id_link": last_submission.assignment_id_link,
        "status": last_submission.status,
        "result_status": last_submission.result_status,
        "view_url": last_submission.submission_url,
        "points": last_submission.grade,
        "overall_feedback_translated": last_submission.overall_feedback_translated,
        "overall_feedback_audio_url": last_submission.audio_feedback_url,
        "attempt_number": attempt_number,
        "attempts_remaining": attempts_remaining,
        "points_awarded": points_awarded,
        "gems_awarded": gems_awarded,
        "context": row["unit_type"] if row else None,
    }
    block.update(_completion_fields_for_submission(last_submission, pe))
    return block

def get_last_submission_payload(student_id: str, last_updated_epoch: int) -> dict:
    pe = get_active_program_enrollment(student_id)
    base = {"points": pe.points or 0, "gems": pe.gems or 0}

    last_submission = _find_last_submission_row(student_id, pe.name, last_updated_epoch or 0)
    if not last_submission:
        return {"has_update": False, **base}

    sub_epoch = int(last_submission.modified.timestamp()) if last_submission.modified else (
        int(last_submission.created_at.timestamp()) if last_submission.created_at else 0
    )

    _mark_feedback_viewed_if_pending(pe)
    return {
        "has_update": True,
        **base,
        "last_submission": {
            **_build_submission_block(last_submission, pe),
            "updated_at": sub_epoch,
        },
    }


def get_profile_select_payload(student_id: str) -> dict:
    """Built for shared.auth.login.select_profile -- the one
    ownership-checked follow-up call after redeem_magic_link, per that
    module's docstring. Reuses the exact same resume-payload shape
    tap_app/api/auth.py::_build_resume_payload already returns from
    /auth/redeem and /auth/select_profile, so a client sees an identical
    shape regardless of which login entrypoint it came through.

    Status auto-activation: same activation check as get_sync_payload
    above -- every call here (i.e. every /auth/redeem and
    /auth/select_profile resume-payload build, since tap_app/api/auth.py's
    _build_resume_payload calls this function directly) flips pe.status
    from "default"/"no_activity" to "active" if applicable, persists it,
    and adds a "status" key to the returned payload ONLY when this call
    just flipped it. For a completed enrollment (now resolvable here too,
    per shared.enrollment.active_batch's read fallback), this is a no-op,
    same as in get_sync_payload.

    COMPLETED-ENROLLMENT BEHAVIOR: like get_sync_payload, this function
    now works for a student whose only ProgramEnrollment is "completed"
    rather than raising StudentNotFound. current_learning_unit will be
    None in that case (every unit done); last_completed_unit is populated
    instead so the resume screen can still show what the student last
    finished.
    """
    pe = get_active_program_enrollment(student_id)

    status_just_changed = _activate_if_inactive_and_persist(pe)

    profile = get_profile_fields(student_id)
    course_complete = is_course_complete(pe)
    current_unit = resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for)
    last_activity = resolve_last_activity_type_for_track(pe, "program")
    payload = {
        "student_id": student_id,
        "name": profile["name1"],
        "grade": profile["grade"],
        "points": pe.points or 0,
        "gems": pe.gems or 0,
        "current_learning_unit": current_unit,
        "last_activity_type": last_activity,
        "state_id": profile["state_id"],
        "district_id": profile["district_id"],
        "school_id": profile["school_id"],
        "state_name": profile["state_name"],
        "district_name": profile["district_name"],
        "school_name": profile["school_name"],
        "course_id": pe.course_level,
        "language": profile["language_code"],
        "updated_at": int(pe.last_activity_at.timestamp()) if pe.last_activity_at else 0,
    }
    if course_complete:
        payload["course_completed"] = True
        payload["last_completed_unit"] = _resolve_last_completed_unit_for_track(pe)
    if status_just_changed:
        payload["status"] = pe.status
    return payload