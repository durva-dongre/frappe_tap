from __future__ import annotations

import frappe

from tap_lms.tap_app.api import tap_app_method
from shared.auth.roster import get_students_for_phone, student_belongs_to_phone
from shared.auth.magic_link import create_magic_link_v2
from shared.config.secrets_cache import get_magic_link_shared_secret
from shared.enrollment.active_batch import get_active_program_enrollment
from shared.profile.student import get_profile_fields
from shared.progress.unit_progress import resolve_current_unit_for_track, resolve_last_activity_type_for_track
from shared.enrollment.unit_rotation import next_unit_for
from shared.errors import StudentNotFound, InvalidInput

_VALID_DEST_TYPES = ("home", "feedback", "submit", "later", "gallery")

_DEFAULT_TTL_SECONDS = {
    "home": 90 * 24 * 3600,
    "feedback": 30 * 24 * 3600,
    "gallery": 30 * 24 * 3600,
    "submit": 14 * 24 * 3600,
    "later": 14 * 24 * 3600,
}


def _build_resume_payload(student_id: str) -> dict:
    pe = get_active_program_enrollment(student_id)
    profile = get_profile_fields(student_id)
    current_unit = resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for)
    last_activity = resolve_last_activity_type_for_track(pe, "program")
    return {
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


@tap_app_method
def redeem_magic_link(phone: str):
    """FIX: get_students_for_phone returns every Student row for this phone
    regardless of enrollment status -- a sibling with zero enrollments, or
    only a dropped/completed one, would previously make it past the initial
    `if not students` check and then crash the ENTIRE request inside
    _build_resume_payload -> get_active_program_enrollment, which raises
    StudentNotFound for that one sibling. That exception propagated past
    this function (it is not caught here), producing a confusing failure for
    the whole phone's redeem call instead of the clean STUDENT_NOT_FOUND the
    contract describes for "no student with an active enrollment" -- and,
    worse, it meant ANY OTHER SIBLING ON THE SAME PHONE who DOES have a valid
    active enrollment was also denied a successful login, purely because one
    of their siblings didn't.

    Now each sibling's payload is built independently; a sibling with no
    active enrollment is simply left out of the roster rather than failing
    the whole call. Only if EVERY sibling lacks an active enrollment does
    this raise StudentNotFound, matching the contract's documented error
    case exactly."""
    students = get_students_for_phone(phone)
    payloads = []
    for s in students:
        try:
            payloads.append(_build_resume_payload(s["name"]))
        except StudentNotFound:
            continue
    if not payloads:
        raise StudentNotFound("no student with an active enrollment for this phone")
    return {"students": payloads}


@tap_app_method
def select_profile(phone: str, student_id: str):
    if not student_belongs_to_phone(student_id, phone):
        raise StudentNotFound("student does not belong to this phone")
    return _build_resume_payload(student_id)


@tap_app_method
def mint_magic_link(phone: str, dest_type: str = "home", dest_id: str | None = None,
                     ttl_seconds: int | None = None):
    """SECURITY NOTE (audit finding, not yet remediated by this patch --
    flagged for an operational decision rather than silently "fixed" code,
    since the right fix depends on how this method is actually meant to be
    reached):

    1. This method is reachable by ANY authenticated Frappe API key holder
       (tap_app_method only requires allow_guest=False), with no role check,
       no rate limiting, and no audit trail -- it can mint a valid,
       Worker-verifiable login link for ANY phone number on demand. If this
       method is only ever meant to be called by trusted internal automation
       (e.g. a WhatsApp-reminder job), it should be restricted further, e.g.:

           if "System Manager" not in frappe.get_roles(frappe.session.user):
               raise PermissionError_("mint_magic_link requires elevated access")

       or moved behind a dedicated internal-only doctype/role so it is not
       reachable via the same API-key surface every tap_app_method endpoint
       shares with the public-facing app.

    2. The secret this function reads (get_magic_link_shared_secret(), from
       site_config.json's tapapp_magic_link_secret) MUST be byte-identical
       to the Worker's own MAGIC_LINK_SECRET (set via `wrangler secret put`
       per deploy_worker.sh). There is no automated mechanism anywhere in
       this codebase that keeps these two independently-configured secrets
       in sync. If the Worker's secret is ever rotated without updating this
       site_config.json value (or vice versa), every link minted by this
       function becomes silently unverifiable -- every redeem attempt using
       such a link will fail with UNAUTHORIZED, with nothing in Frappe's own
       logs to explain why (the failure happens entirely inside the Worker's
       verifyMagicLinkV2, which Frappe never sees). Document this coupling
       explicitly in the ops runbook for secret rotation, and/or add a
       `bench execute tap_lms.tap_app.api.auth.selfcheck_magic_link_roundtrip`
       command (mint + immediately locally verify) to at least catch
       Python-side packing regressions, even though it cannot detect a
       cross-service secret mismatch with the Worker.
    """
    if dest_type not in _VALID_DEST_TYPES:
        raise InvalidInput("dest_type must be one of: " + ", ".join(_VALID_DEST_TYPES))
    if dest_type in ("feedback", "submit") and not dest_id:
        raise InvalidInput(f"dest_id is required for dest_type={dest_type}")

    ttl = ttl_seconds or _DEFAULT_TTL_SECONDS[dest_type]
    secret = get_magic_link_shared_secret()
    if not secret:
        frappe.throw("tapapp_magic_link_secret is not configured in site_config.json")

    link = create_magic_link_v2(secret, phone, dest_type, dest_id, ttl)
    return {"magic_link": link, "dest_type": dest_type, "dest_id": dest_id, "expires_in": ttl}