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

    Returns the same bool activate_if_inactive returned (True iff the
    status actually changed), so both callers can use it to decide
    whether to add the new, documented "status" field to their response
    -- only when this call just flipped it, never otherwise, per the
    "absent means unchanged" convention this project uses for last_submission
    and is now extending to this status-change notification."""
    changed = activate_if_inactive(pe_doc)
    if changed:
        frappe.db.set_value(
            "ProgramEnrollment", pe_doc.name, "status", pe_doc.status, update_modified=False,
        )
    return changed


def _find_last_submission_row(student_id: str, program_enrollment_name: str, last_updated_epoch: int) -> dict | None:
    """Returns the student's most recently UPDATED submission that (a)
    belongs to the CURRENTLY ACTIVE ProgramEnrollment, and (b) has actually
    changed since last_updated_epoch -- not just the newest-modified
    Submission row for this student_id across all history.

    Both conditions are required:

    - Scoping to program_enrollment_name excludes submissions left over
      from a prior/inactive enrollment (a dropped-and-reenrolled student, a
      course-level change, stale/test rows, etc.). Without this, a
      long-dead submission belonging to a different enrollment could be
      reported as "the last submission" for the student's current session,
      which makes no sense to a client resuming the student's CURRENT
      enrollment.

    - Filtering `modified > last_updated_epoch` directly in SQL means this
      function only ever returns a row that is genuinely newer than what
      the caller already has. Previously this filtering did not happen
      here at all -- the caller (get_sync_payload) learned a submission had
      "changed" purely by comparing the enrollment's own last_activity_at
      against last_updated_epoch, which can advance for reasons that have
      nothing to do with a submission (e.g. a video-watch or quiz call).
      That let an old, previously-seen submission be reported as new over
      and over, each time re-stamped with the enrollment's current epoch
      instead of its own. Gating directly on the submission's own
      `modified` here removes that possibility: a row is only ever
      returned once, the first time its own modified timestamp crosses
      last_updated_epoch.

    `modified` is Frappe's own standard last-write timestamp, bumped on
    every `doc.save()` -- including every grading-pipeline update
    (feedback_processor.py, review_result.py's status/reward writes) -- so
    ordering by `modified desc` within the filtered set still reliably
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
    """Derives (points_awarded, gems_awarded) for THIS submission's grading
    bonus. There is no dedicated storage column for this on Submission, by
    design (no doctype change needed) -- the amount is recovered from what
    already exists:

      - shared.submission.status.is_reward_eligible(sub.result_status) tells
        us whether this particular submission's result ever qualifies for
        the grading-time bonus at all ("Success - Original" only -- a
        "Success - Flagged" result is complete but never earns this, per
        shared/submission/status.py's own completion-vs-reward distinction);
      - sub.feedback_ready_processed_at being set tells us the one-time
        award for this submission has actually been granted -- this is the
        exact same guard shared.submission.review_result.handle_review_result
        uses itself, via _already_rewarded, to avoid a double award;
      - the amount itself is always the CURRENT Shared Settings configured
        value (points_submission_review_valid / gems_submission_review_valid
        -- 10 points / 1 gem as configured today).

    Returns (0, 0) for a submission that is not reward-eligible, or is
    reward-eligible but not yet actually rewarded.

    Read ONLY by get_sync_payload / get_last_submission_payload /
    get_profile_select_payload below -- all of which are gated (sync/
    last_submission by an updated_at/last_updated epoch comparison;
    get_profile_select_payload by being a one-shot call on login, not a
    repeatable historical read) -- so a given award is only ever surfaced
    to the app a bounded number of times, never on every page view of
    submission history. submission.list / submission.get do NOT call this
    -- see tap_app/api/submission.py's module docstring for why a one-time
    award field has no place on an ungated historical read.
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
    completed it" after the fact -- the two are not always
    distinguishable long after the fact (another activity could have
    independently touched the same row later), but reporting "this unit
    is Completed" on every subsequent read of a submission belonging to
    an already-completed unit is the documented, intentional behavior:
    the client needs to know the unit/course state, and repeating it on
    every sync call that surfaces this submission is consistent with how
    this file already reports points/gems/current_learning_unit on every
    call rather than only once.

    Returns {} (no keys at all) when the owning Unit Progress row can't
    be resolved, or its unit_status is not "Completed" -- matching the
    "absent means nothing changed" convention used elsewhere for
    last_submission's own presence/absence.
    """
    row = find_unit_progress_row_for_submission(last_submission.name)
    if not row or row.get("unit_status") != "Completed":
        return {}

    fields = {"unit_completed": True}
    if is_course_complete(pe):
        fields["course_completed"] = True
        # Decision B: no next_learning_unit_id key at all when the course
        # is complete.
    else:
        fields["course_completed"] = False
        fields["next_learning_unit_id"] = next_unit_for(pe)
    return fields


def _build_submission_block(last_submission: dict, pe) -> dict:
    """Builds the last_submission wire shape. submission_id is recovered via
    shared.submission.object_naming.resolve_wire_submission_id -- NOT
    last_submission.name directly -- so the client sees the Worker-shaped
    id (e.g. "k3f9a2b7x1") once imgana's async upload job has populated this
    row's submission_url, falling back to the Frappe autoname only for a
    row whose submission_url hasn't been populated yet or never matches the
    expected tapapp shape. No schema change, no write -- pure computation
    over an already-persisted field. See that module's docstring for the
    full reasoning.

    Also threads in unit_completed/course_completed/[next_learning_unit_id]
    via _completion_fields_for_submission (new) -- same "compute live on
    read" style as points_awarded/gems_awarded just below it. `pe` (the
    owning ProgramEnrollment doc) is required here, not just a name,
    because is_course_complete needs the live doc's course_level and
    unit_progress table.
    """
    attempt_number, attempts_remaining = attempt_info_for_submission(last_submission.name)
    points_awarded, gems_awarded = _grading_award_for_submission(last_submission)
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
    }
    block.update(_completion_fields_for_submission(last_submission, pe))
    return block


def get_sync_payload(student_id: str, last_updated_epoch: int) -> dict:
    """
    STATUS AUTO-ACTIVATION (new, 2026-11-14): every call to this function
    -- i.e. every /progress/sync call -- checks whether pe.status is
    currently "default" or "no_activity" and, if so, flips it to "active"
    (shared.enrollment.enrollment.activate_if_inactive, persisted via
    _activate_if_inactive_and_persist). This happens BEFORE the
    changed/unchanged short-circuit below, so a sync call that would
    otherwise report changed: false still performs the activation check
    and persists it if it fires -- the student's enrollment status is
    allowed to become visibly "active" purely from a login/sync read,
    independent of whether there happens to be new submission/points
    state to report in the same call.

    The new "status" field is added to the returned payload ONLY when
    this call's activation check just flipped the status (never
    otherwise) -- the "absent means unchanged" convention this file
    already uses for last_submission is extended to this field. A sync
    call that finds the enrollment already active/paused/manual/completed/
    dropped reports no "status" key at all, exactly as it did before this
    change.
    """
    pe = get_active_program_enrollment(student_id)

    status_just_changed = _activate_if_inactive_and_persist(pe)

    current_epoch = int(pe.last_activity_at.timestamp()) if pe.last_activity_at else 0

    if current_epoch <= (last_updated_epoch or 0):
        payload = {"changed": False, "updated_at": last_updated_epoch or current_epoch}
        if status_just_changed:
            payload["status"] = pe.status
        return payload

    last_submission = _find_last_submission_row(student_id, pe.name, last_updated_epoch or 0)
    payload = {
        "changed": True,
        "updated_at": current_epoch,
        "points": pe.points or 0,
        "gems": pe.gems or 0,
        "current_learning_unit": resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for),
        "last_activity_type": resolve_last_activity_type_for_track(pe, "program"),
    }
    if status_just_changed:
        payload["status"] = pe.status
    if last_submission:
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
        # updated_at here is the submission's OWN modified epoch (set by
        # _build_submission_block's caller below), not pe's current_epoch --
        # see that assignment for why.
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
    """Built for shared.auth.login.select_profile -- the one ownership-
    checked follow-up call after redeem_magic_link, per that module's
    docstring. Reuses the exact same resume-payload shape
    tap_app/api/auth.py::_build_resume_payload already returns from
    /auth/redeem and /auth/select_profile, so a client sees an identical
    shape regardless of which login entrypoint it came through.

    STATUS AUTO-ACTIVATION (new, 2026-11-14): same activation check as
    get_sync_payload above -- every call here (i.e. every /auth/redeem and
    /auth/select_profile resume-payload build, since tap_app/api/auth.py's
    _build_resume_payload now calls this function directly, see that
    module) flips pe.status from "default"/"no_activity" to "active" if
    applicable, persists it, and adds a "status" key to the returned
    payload ONLY when this call just flipped it.
    """
    pe = get_active_program_enrollment(student_id)

    status_just_changed = _activate_if_inactive_and_persist(pe)

    profile = get_profile_fields(student_id)
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
    if status_just_changed:
        payload["status"] = pe.status
    return payload