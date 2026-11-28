from __future__ import annotations

from tap_lms.tap_app.api import tap_app_method
from shared.auth.roster import get_students_for_phone, student_belongs_to_phone
from shared.profile.sync import get_profile_select_payload
from shared.errors import StudentNotFound

# NOTE: mint_magic_link used to live here. It has been MOVED to
# tap_lms/shared/internal/magic_link.py (mint_magic_link +
# mint_magic_link_for_last_submission), because it is an internal/
# operational surface (e.g. a WhatsApp-reminder job) -- never a route the
# TapApp Worker itself calls on a student's behalf -- and tap_app/api/*.py
# is reserved exclusively for Worker-facing routes, guarded by
# tap_app_method's full authenticated-session requirement. Internal
# callers (Apps Script, reminder jobs, etc.) authenticate instead via
# plain Frappe API key/secret, same as tap_lms/shared/internal/
# student_handling.py's own endpoints. See that new module's docstring for
# the full rationale, access-scope notes, and secret-rotation caveats
# (unchanged from when this lived here).


def _build_resume_payload(student_id: str) -> dict:
    """Delegates to shared.profile.sync.get_profile_select_payload -- the
    single shared implementation of the resume-payload shape used by
    /auth/redeem, /auth/select_profile, and shared.auth.login.select_profile.
    Keeping one implementation (rather than duplicating this logic inline)
    is what keeps this file, sync.py, and shared/auth/login.py in agreement
    by construction instead of by three independently maintained copies.

    Because this calls get_profile_select_payload directly, every
    /auth/redeem and /auth/select_profile response also gets that
    function's status auto-activation behavior (default/no_activity ->
    active, with a conditional "status" field on change). See
    shared/profile/sync.py::get_profile_select_payload and
    shared.enrollment.enrollment.activate_if_inactive for the full
    behavior and persistence details.
    """
    return get_profile_select_payload(student_id)


@tap_app_method
def redeem_magic_link(phone: str):
    """Builds and returns the full resume-payload roster for a phone
    (API_Reference.md §1.1 / Contract §4.2).

    get_students_for_phone returns every Student row for this phone
    regardless of enrollment status, so each sibling's resume payload is
    built independently here: a sibling with no active enrollment
    (StudentNotFound from _build_resume_payload ->
    get_active_program_enrollment) is simply left out of the roster, rather
    than that one sibling's failure aborting the whole phone's login. One
    sibling's enrollment state must never gate whether any other sibling on
    the same phone can log in. Only when every sibling lacks an active
    enrollment does this raise StudentNotFound, matching the documented "no
    student with an active-batch enrollment" error case exactly.

    Each sibling's own payload may or may not carry a "status" key,
    independently -- whichever siblings' enrollments happened to be
    "default" or "no_activity" at the moment of this call get activated and
    get the key; siblings already active/paused/manual/completed/dropped
    do not. This is a per-student signal, not a per-phone one.
    """
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