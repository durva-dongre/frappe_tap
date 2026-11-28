# Copyright (c) 2026, Techt4dev and contributors
# For license information, please see license.txt

"""
tap_lms/shared/internal/magic_link.py

Part of tap_lms.shared.internal -- the folder for internal, non-doctype
whitelisted endpoints (ops/automation hooks called from Apps Script, a
reminder/notification job, or similar external/internal scripts), as
opposed to doctype controller logic or the TapApp Worker's own API surface
(tap_lms/tap_app/api/*.py).

This file is the one place that MINTS a magic link from outside the
TapApp Worker request path. It exposes two whitelisted endpoints:

  - mint_magic_link
        General-purpose magic-link minting for a given phone + dest_type
        (home/feedback/submit/later/gallery), with an optional dest_id.
        This is the exact function that used to live at
        tap_lms.tap_app.api.auth.mint_magic_link -- moved here verbatim
        (same behavior, same return shape) because it is an internal/
        operational surface (e.g. a WhatsApp-reminder job), never a route
        the TapApp Worker calls on a student's behalf, and tap_app/api/*
        is reserved for Worker-facing routes only. See that function's
        own docstring below for the full access-scope and secret-rotation
        notes, carried over unchanged.

  - mint_magic_link_for_last_submission
        New. Given a phone number alone, resolves the single most
        recently updated submission across every student on that phone
        (reusing the exact same "last submission" scoping
        shared.profile.sync._find_last_submission_row already uses for
        /progress/sync: scoped to that student's own ACTIVE
        ProgramEnrollment, ordered by `modified desc`), classifies its
        status as one of "valid" / "invalid" / "pending" / "not_submitted",
        marks the owning enrollment's stage "feedback_viewed" if it was
        "feedback_tobe_viewed" (the exact same side effect
        shared.profile.sync._mark_feedback_viewed_if_pending performs on
        every sync/last_submission read), and mints a magic link (dest_type
        "feedback", dest_id the submission's own name) pointing a
        caller (e.g. a WhatsApp "your feedback is ready" message) at that
        submission.

        A phone can have more than one Student (siblings) -- see
        shared.auth.roster.get_students_for_phone. This function looks at
        EVERY student on the phone and returns the single most recently
        updated submission across all of them (the same "whichever
        sibling has the freshest update" shape already implied by this
        phone-scoped login flow), not just the first student's.

Auth: like student_handling.py, both endpoints here are plain
@frappe.whitelist() methods relying on standard Frappe API key/secret auth
(Authorization: token <key>:<secret>) -- NOT the tap_app_method decorator
(tap_lms.tap_app.api), which is reserved for TapApp Worker-facing routes
and requires a full authenticated Frappe session. Create a dedicated
Frappe User for whatever internal caller needs this (a reminder job, Apps
Script, etc.) and grant it read permission on Student/ProgramEnrollment/
Submission -- no write permission is needed by this file, since
mint_magic_link_for_last_submission's one write (the feedback_viewed
stage flip) goes through frappe.db.set_value with
ignore_permissions=True), exactly like the sync-path helper it mirrors.

Both endpoints accept and return plain JSON-serializable data only, and
never leak Shared Settings secrets or raw exceptions back to the caller --
a SharedError (NotFound/InvalidInput/etc, from shared/errors.py) is
caught and reported as a plain {"ok": False, "error": ...} dict rather
than an uncaught 500, consistent with student_handling.py's own
per-row error reporting style (though these two endpoints operate on a
single phone/call, not a batch of rows).
"""

from __future__ import annotations

import frappe

from shared.auth.magic_link import create_magic_link_v2
from shared.auth.roster import get_students_for_phone
from shared.config.secrets_cache import (
    get_magic_link_shared_secret,
    get_magic_link_ttl,
    get_magic_link_base_url,
)
from shared.enrollment.active_batch import get_active_program_enrollment_name
from shared.errors import InvalidInput, SharedError
from shared.submission.status import is_submission_complete

_VALID_DEST_TYPES = ("home", "feedback", "submit", "later", "gallery")

# Submission.status values that mean "still being worked on" -- see
# tap_lms/tap_lms/doctype/submission/submission.json's own Select options
# and shared/submission/status.py's SUBMISSION_STATUS_OPTIONS.
_IN_PROGRESS_STATUSES = ("Pending", "Processing")


def _mint_link(phone: str, dest_type: str, dest_id: str | None, ttl_seconds: int | None) -> dict:
    """Shared minting core used by both endpoints below -- builds the
    V2 token (shared.auth.magic_link.create_magic_link_v2) and the full,
    shareable URL (Shared Settings.magic_link_base_url +
    token, with no separator inserted -- see
    get_magic_link_base_url's own docstring for why the stored base URL
    must already end in whatever the receiving endpoint expects).

    Raises InvalidInput (mapped by each endpoint's own try/except, see
    below) if dest_type is invalid, if a required dest_id is missing, or
    if either Shared Settings.magic_link_shared_secret or
    Shared Settings.magic_link_base_url has never been configured --
    both of those raise loudly from their own accessors, with no silent
    default, exactly as before this move.
    """
    if dest_type not in _VALID_DEST_TYPES:
        raise InvalidInput("dest_type must be one of: " + ", ".join(_VALID_DEST_TYPES))
    if dest_type in ("feedback", "submit") and not dest_id:
        raise InvalidInput(f"dest_id is required for dest_type={dest_type}")

    ttl = ttl_seconds or get_magic_link_ttl(dest_type)

    # get_magic_link_shared_secret raises InvalidInput itself if Shared
    # Settings.magic_link_shared_secret has never been configured -- no
    # separate guard needed here.
    secret = get_magic_link_shared_secret()

    link = create_magic_link_v2(secret, phone, dest_type, dest_id, ttl)
    base_url = get_magic_link_base_url()
    magic_link_url = f"{base_url}{link}"

    return {
        "magic_link": link,
        "magic_link_url": magic_link_url,
        "dest_type": dest_type,
        "dest_id": dest_id,
        "expires_in": ttl,
    }


@frappe.whitelist()
def mint_magic_link(phone: str, dest_type: str = "home", dest_id: str | None = None,
                     ttl_seconds: int | None = None):
    """Mints a V2 magic link (shared.auth.magic_link.create_magic_link_v2)
    for a given phone and dest_type, and returns it both as the bare token
    (`magic_link`, for any caller that only needs the token itself) and as
    a full, shareable URL (`magic_link_url`).

    MOVED from tap_lms.tap_app.api.auth.mint_magic_link verbatim (same
    signature, same behavior, same return shape) -- this is an internal/
    operational surface (e.g. a WhatsApp-reminder job), not a route the
    TapApp Worker itself calls on a student's behalf, so it has no
    business under tap_app/api/*.py, which is reserved for Worker-facing
    routes guarded by tap_app_method's full-session auth. It now relies on
    plain Frappe API key/secret auth instead (see module docstring).

    Standing considerations, carried over unchanged from the original:

    1. Access scope: this endpoint requires only an authenticated Frappe
       API key, with no additional role check of its own, so any key
       holder permitted to call it can mint a login link for any phone
       number. Whether that is acceptable depends entirely on who holds
       credentials for the dedicated internal User this is meant to run
       as (see module docstring) -- if broader restriction is needed, add
       a role check here or move this behind a narrower-scoped user.

    2. Secret agreement: the secret read here
       (get_magic_link_shared_secret(), from Shared Settings.
       magic_link_shared_secret) must be byte-identical to the Worker's
       own MAGIC_LINK_SECRET (set via `wrangler secret put`). Rotating one
       without the other makes every link minted here fail verification
       on the Worker side with UNAUTHORIZED, with nothing in Frappe's own
       logs to explain why -- an operational/runbook concern for secret
       rotation, external to this file.

    Per-dest_type default TTLs are Shared Settings fields
    (magic_link_ttl_home/feedback/gallery/submit/later), read via
    shared.config.secrets_cache.get_magic_link_ttl, so an operator can
    change e.g. the "feedback" link's lifetime from the Shared Settings
    doctype UI with no deploy. An explicit ttl_seconds argument from the
    caller always wins over the configured default.

    Returns: {"magic_link": ..., "magic_link_url": ..., "dest_type": ...,
    "dest_id": ..., "expires_in": ...} on success, or
    {"ok": False, "error_code": ..., "error": ...} if dest_type is
    invalid, dest_id is missing where required, or either secret/base-url
    Shared Settings field has never been configured.
    """
    try:
        return {"ok": True, **_mint_link(phone, dest_type, dest_id, ttl_seconds)}
    except SharedError as e:
        frappe.log_error(title="mint_magic_link failed", message=f"phone={phone} dest_type={dest_type} error={e}")
        return {"ok": False, "error_code": e.code, "error": e.message}


def _classify_submission_status(sub: dict | None) -> str:
    """Classifies a submission row dict (as returned by
    _find_last_submission_row's own query shape -- needs at least
    `status` and `result_status`) into one of:

      - "not_submitted": sub is None -- no submission exists at all for
        this student's active enrollment.
      - "pending": sub.status is "Pending" or "Processing" -- still being
        worked on (upload, grading, or review in flight).
      - "valid": sub.status == "Completed" and
        shared.submission.status.is_submission_complete(result_status) is
        True (i.e. result_status is "Success - Original" or
        "Success - Flagged" -- both count as a genuine, scored
        submission; see that module's own docstring for why a flagged
        submission is still "valid" here even though it is not
        reward-eligible).
      - "invalid": sub.status == "Completed" with result_status "Failed",
        or sub.status == "Failed" outright.

    Any other combination (e.g. status == "Completed" with
    result_status == "Pending", which should not occur in practice) falls
    through to "pending" rather than raising -- a transient/unexpected
    state is safer reported as "still in progress" than misreported as
    either a false "valid" or a false "invalid".
    """
    if not sub:
        return "not_submitted"

    status = sub.get("status")
    result_status = sub.get("result_status")

    if status in _IN_PROGRESS_STATUSES:
        return "pending"
    if status == "Failed":
        return "invalid"
    if status == "Completed":
        if is_submission_complete(result_status):
            return "valid"
        return "invalid"
    return "pending"


def _find_last_submission_for_student(student_id: str) -> dict | None:
    """Resolves (student's active ProgramEnrollment, that enrollment's own
    most recently modified Submission row), reusing the exact same
    scoping shared.profile.sync._find_last_submission_row already uses
    for /progress/sync and /progress/last_submission: scoped to the
    student's currently ACTIVE enrollment only (never a stale submission
    left over from a dropped/superseded enrollment), ordered by
    `modified desc, created_at desc` so the most recently changed
    submission wins.

    Unlike sync.py's own version, this has no `last_updated_epoch` cutoff
    -- this endpoint always wants the single latest submission regardless
    of whether the caller has already seen it, since its whole purpose is
    to report "what is your last submission's status right now," not
    "has anything changed since you last checked."

    Returns (program_enrollment_name, submission_row_dict_or_None). A
    student with an active enrollment but no submissions at all returns
    (pe_name, None) -- NOT an error; that is exactly the "not_submitted"
    case _classify_submission_status handles.
    """
    pe_name = get_active_program_enrollment_name(student_id)

    rows = frappe.get_all(
        "Submission",
        filters={"program_enrollment": pe_name},
        fields=["name", "status", "result_status", "modified", "created_at",
                "assign_id", "assignment_id_link"],
        order_by="modified desc, created_at desc",
        limit_page_length=1,
    )
    return pe_name, (rows[0] if rows else None)


def _resolve_assignment_name(sub: dict) -> str | None:
    """Resolves the clean, human-readable assignment name for a submission
    -- e.g. "Introduction to animation world" -- with NO trailing "-62633"
    style numeric suffix and no string-trimming of any kind.

    This works because Assignment.autoname is
    "format:{assignment_name}-{###}" (tap_lms/tap_lms/doctype/assignment/
    assignment.json): the numeric suffix is ONLY ever part of the
    Assignment DOCUMENT NAME (the autogenerated primary key), never part
    of Assignment.assignment_name itself, which is a separate, plain Data
    field holding just the clean display name as entered. So this
    function never needs to strip or parse anything out of a string -- it
    reads assignment_name directly off the Assignment doc.

    Resolution order, matching
    tap_app/api/submission.py::_resolve_assignment_id_link's own
    fallback: prefer sub["assignment_id_link"] (a real Link to Assignment)
    and fall back to sub["assign_id"] (older/legacy WhatsApp-sourced rows
    where only assign_id was ever populated) only if the link is empty.
    Either way, the resolved value is treated as an Assignment document
    name and looked up via frappe.db.get_value.

    Returns None if sub has neither field populated, or if the resolved
    document name doesn't actually exist as an Assignment (a stale/
    deleted reference) -- never raises, since a missing assignment name is
    not fatal to reporting a submission's status.
    """
    assignment_name_field = sub.get("assignment_id_link") or sub.get("assign_id")
    if not assignment_name_field:
        return None
    return frappe.db.get_value("Assignment", assignment_name_field, "assignment_name")


def _mark_feedback_viewed_if_pending(program_enrollment_name: str) -> None:
    """Mirrors shared.profile.sync._mark_feedback_viewed_if_pending's
    exact side effect (flip stage "feedback_tobe_viewed" ->
    "feedback_viewed"), but via a direct frappe.db.set_value rather than
    loading and saving the full ProgramEnrollment document -- this
    endpoint has no other reason to load the doc at all, so a targeted
    single-field update is both cheaper and avoids any risk of this
    read-mostly, internal-auth endpoint accidentally re-saving (and thus
    re-validating/re-triggering doc-events for) the whole enrollment
    document for an unrelated reason.

    Guarded with a WHERE stage = 'feedback_tobe_viewed' clause so this is
    a safe no-op if the stage has already moved on (e.g. a concurrent
    sync call already flipped it) -- never overwrites a stage value this
    function doesn't recognize as the specific "pending view" state.
    """
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET stage = 'feedback_viewed', modified = NOW()
         WHERE name = %(enrollment)s AND stage = 'feedback_tobe_viewed'
        """,
        {"enrollment": program_enrollment_name},
    )
    frappe.db.commit()


@frappe.whitelist()
def mint_magic_link_for_last_submission(phone: str, dest_type: str = "feedback",
                                         ttl_seconds: int | None = None):
    """Given a phone number alone, resolves the single most recently
    updated submission across every student (sibling) on that phone,
    reports its status, marks the owning enrollment's feedback stage
    viewed (exactly as a real /progress/sync or /progress/last_submission
    call already would -- see
    shared.profile.sync._mark_feedback_viewed_if_pending), and mints a
    magic link pointing at that submission.

    MULTIPLE STUDENTS ON ONE PHONE: shared.auth.roster.get_students_for_phone
    can return more than one Student for a shared household phone. This
    function resolves a (ProgramEnrollment, Submission-or-None) pair for
    EVERY student on the phone (skipping a student with no active
    enrollment at all, same StudentNotFound-tolerant behavior
    tap_app/api/auth.py::redeem_magic_link already uses for its own
    per-sibling roster build), then picks whichever one has the single
    most recently modified real Submission row across all of them. If NO
    student on the phone has ever submitted anything, "not_submitted" is
    reported and no particular student/enrollment is implicated in the
    minted link's dest_id (dest_id is then omit-able -- see below).

    STATUS VALUES: see _classify_submission_status's own docstring --
    one of "valid", "invalid", "pending", "not_submitted".

    MAGIC LINK: minted with dest_type as given (default "feedback") and
    dest_id set to the resolved submission's own name, so the link, once
    redeemed by the Worker, can be resolved directly to that submission's
    feedback view. If status is "not_submitted" (no submission exists at
    all across every student on the phone), there is no submission name
    to scope the link to -- in that case this function mints a "home"
    dest_type link instead (regardless of the dest_type argument),
    since a feedback/submit link requires a real dest_id
    (shared.config.secrets_cache / the dest_type validation in
    _mint_link both require one) and there is nothing
    submission-specific yet to point at.

    FEEDBACK-VIEWED SIDE EFFECT: only applied to the one enrollment whose
    submission was actually selected (the most recent one across all
    siblings) -- not to every sibling's enrollment indiscriminately. This
    mirrors sync.py's own behavior, which only ever touches the one
    enrollment it is actively resolving a payload for.

    Returns on success:
        {
            "ok": True,
            "status": "valid" | "invalid" | "pending" | "not_submitted",
            "student_id": "ST00000123" or null (null only for
                "not_submitted" when truly no student on the phone has an
                active enrollment at all),
            "submission_name": "<Assignment.assignment_name>" or null
                (null for "not_submitted", or if the submission has no
                resolvable assignment reference) -- e.g.
                "Introduction to animation world". This is the clean,
                human-readable assignment display name, resolved from the
                Assignment doctype's own assignment_name field (see
                _resolve_assignment_name) -- it never carries a trailing
                "-<number>" suffix, since that suffix only ever exists in
                the Assignment document's own autoname, not in its
                assignment_name field.
            "magic_link": "...",
            "magic_link_url": "...",
            "dest_type": "feedback" | "home",
            "dest_id": "<tabSubmission.name -- the real Submission
                document name, NOT the same as submission_name above>" or
                null,
            "expires_in": <seconds>,
        }
    or {"ok": False, "error_code": ..., "error": ...} if no student at
    all exists for this phone, or if minting itself fails (e.g.
    unconfigured magic_link_shared_secret / magic_link_base_url).
    """
    try:
        students = get_students_for_phone(phone)
        if not students:
            raise InvalidInput("no student found for this phone", error_code="no_student_for_phone")

        best_student_id = None
        best_pe_name = None
        best_submission = None

        for s in students:
            student_id = s["name"]
            try:
                pe_name, submission = _find_last_submission_for_student(student_id)
            except SharedError:
                # No active enrollment at all for this sibling -- same
                # tolerance tap_app/api/auth.py::redeem_magic_link already
                # applies per-sibling; one sibling's missing enrollment
                # must never abort resolution for the others.
                continue

            if submission is None:
                continue

            current_modified = submission.get("modified") or submission.get("created_at")
            best_modified = (
                (best_submission.get("modified") or best_submission.get("created_at"))
                if best_submission else None
            )
            if best_submission is None or (current_modified and (not best_modified or current_modified > best_modified)):
                best_student_id = student_id
                best_pe_name = pe_name
                best_submission = submission

        status = _classify_submission_status(best_submission)

        if best_submission is not None:
            _mark_feedback_viewed_if_pending(best_pe_name)
            mint_dest_type = dest_type
            dest_id = best_submission["name"]
        else:
            # Nothing to scope a feedback/submit link to -- fall back to a
            # plain "home" link rather than raising, since "not_submitted"
            # is a legitimate, expected status for this endpoint to
            # report, not an error condition.
            mint_dest_type = "home"
            dest_id = None

        link_result = _mint_link(phone, mint_dest_type, dest_id, ttl_seconds)

        return {
            "ok": True,
            "status": status,
            "student_id": best_student_id,
            # The clean, human-readable Assignment.assignment_name this
            # submission is for (e.g. "Introduction to animation world")
            # -- resolved via _resolve_assignment_name, which reads the
            # Assignment doctype's own assignment_name field directly, so
            # it never carries the "-62633" style numeric suffix that only
            # ever lives in the Assignment DOCUMENT NAME (its autoname),
            # never in assignment_name itself. None if the submission has
            # no resolvable assignment reference at all.
            "submission_name": _resolve_assignment_name(best_submission) if best_submission else None,
            **link_result,
        }
    except SharedError as e:
        frappe.log_error(
            title="mint_magic_link_for_last_submission failed",
            message=f"phone={phone} dest_type={dest_type} error={e}",
        )
        return {"ok": False, "error_code": e.code, "error": e.message}