from __future__ import annotations

from shared.auth import magic_link, jwt_tokens, roster
from shared.errors import Forbidden, NotFound
from shared.profile import sync

# DEPENDENCY NOTE: Forbidden is not currently in shared/errors.py (which
# defines SharedError, NotFound, InvalidInput, StudentNotFound,
# ConflictError, PermissionError_), and sync.get_profile_select_payload is
# not currently exported by shared/profile/sync.py (which exports
# get_sync_payload and get_last_submission_payload). This module depends
# on auth primitives (magic_link.py, jwt_tokens.py) that carry their own
# dependency notes; resolving those additions is outside this module's
# scope, and callers should confirm the symbols exist in their target
# shared/ package before relying on this file.


def redeem_magic_link(token: str) -> dict:
    """
    Single entrypoint for every tap of the magic link -- the 1st time or the
    5000th. Always issues the same shape of token regardless of sibling count:
    a phone token. The frontend always then calls select_profile with the
    chosen student_id, even in the single-student case -- this keeps the
    contract uniform (one token type, one follow-up call) instead of branching
    the client on sibling count. 1 query total here (roster lookup).
    """
    phone = magic_link.verify_magic_link(token)
    students = roster.get_students_for_phone(phone)

    if not students:
        raise NotFound("no student found for this phone", error_code="no_student_for_phone")

    phone_token = jwt_tokens.issue_phone_token(phone)

    return {
        "token": phone_token,
        "students": students,
        "mode": "single" if len(students) == 1 else "picker",
    }


def select_profile(phone: str, student_id: str) -> dict:
    """
    The one ownership check per session. Everything downstream (submit, enroll,
    progress, refresh) trusts the student_id the caller supplies alongside the
    phone token without re-querying Student -- this is intentional: re-checking
    ownership on every hot-path call would mean a DB round trip on every single
    request at million-request scale. The tradeoff is explicit: ownership is
    verified once, here, and tap_app's endpoint layer is responsible for not
    letting a request swap student_id after this point without calling this
    again.
    """
    if not roster.student_belongs_to_phone(student_id, phone):
        raise Forbidden("student does not belong to this phone", error_code="student_ownership")
    return sync.get_profile_select_payload(student_id)