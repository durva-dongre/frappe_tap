from __future__ import annotations

from tap_lms.tap_app.api import tap_app_method
from shared.auth.roster import get_students_for_phone, student_belongs_to_phone
from shared.auth.magic_link import create_magic_link_v2
from shared.config.secrets_cache import get_magic_link_shared_secret, get_magic_link_ttl, get_magic_link_base_url
from shared.profile.sync import get_profile_select_payload
from shared.errors import StudentNotFound, InvalidInput

_VALID_DEST_TYPES = ("home", "feedback", "submit", "later", "gallery")


def _build_resume_payload(student_id: str) -> dict:
    """Delegates to shared.profile.sync.get_profile_select_payload --
    the exact same resume-payload shape /auth/redeem, /auth/select_profile,
    and shared.auth.login.select_profile all now share, with exactly one
    implementation. Previously this function duplicated get_profile_select_payload's
    logic inline; it is now a thin pass-through so this file, sync.py, and
    shared/auth/login.py all stay in agreement by construction rather than
    by three independently-maintained copies.

    STATUS AUTO-ACTIVATION (new, 2026-11-14): because this now calls
    get_profile_select_payload directly, every /auth/redeem and
    /auth/select_profile response gets the same status auto-activation
    (default/no_activity -> active) and conditional "status" field
    get_sync_payload already carries -- this is the "notify this status
    and status change to frontend login or sync" requirement's auth-side
    half. See shared/profile/sync.py::get_profile_select_payload and
    shared.enrollment.enrollment.activate_if_inactive for the full
    behavior and persistence details.
    """
    return get_profile_select_payload(student_id)


@tap_app_method
def redeem_magic_link(phone: str):
    """Builds and returns the full resume-payload roster for a phone
    (API_Reference.md §1.1 / Contract §4.2). get_students_for_phone returns
    every Student row for this phone regardless of enrollment status, so
    each sibling's resume payload is built independently here: a sibling
    with no active enrollment (StudentNotFound from
    _build_resume_payload -> get_active_program_enrollment) is simply left
    out of the roster, rather than that one sibling's failure aborting the
    whole phone's login. This is the invariant this function relies on
    going forward -- one sibling's enrollment state must never gate
    whether any other sibling on the same phone can log in. Only when
    EVERY sibling lacks an active enrollment does this raise
    StudentNotFound, which matches the documented "no student with an
    active-batch enrollment" error case exactly.

    Each sibling's own payload may or may not carry a "status" key,
    independently -- whichever siblings' enrollments happened to be
    "default" or "no_activity" at the moment of this call get activated
    and get the key; siblings already active/paused/manual/completed/
    dropped do not. This is a per-student signal, not a per-phone one.
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


@tap_app_method
def mint_magic_link(phone: str, dest_type: str = "home", dest_id: str | None = None,
                     ttl_seconds: int | None = None):
    """Mints a V2 magic link (shared.auth.magic_link.create_magic_link_v2)
    for a given phone and dest_type, and returns it both as the bare token
    (`magic_link`, unchanged, for any existing caller that only needs the
    token itself) and as a full, shareable URL (`magic_link_url`), built by
    appending the token directly to Shared Settings.magic_link_base_url
    (shared.config.secrets_cache.get_magic_link_base_url). The base URL is
    configuration, not a constant here, because it differs by environment
    (staging vs. production) and can change independently of a Frappe
    deploy -- see that function's own docstring for why it has no silent
    default the way the TTL accessors do, and why an unconfigured base URL
    must fail loudly at mint time rather than produce a link missing its
    host. The token is appended as-is, with no separator inserted on this
    side, so the configured base URL itself must already end in whatever
    the receiving endpoint expects (a trailing '/', or a '?token=' style
    prefix) -- this function does no URL-joining logic of its own.

    This is an internal/operational surface (e.g. a WhatsApp-reminder job),
    not a route the TapApp Worker itself calls on a student's behalf, so it
    carries two standing considerations for whoever operates or extends it:

    1. Access scope: tap_app_method only requires an authenticated Frappe
       API key (allow_guest=False), with no role check of its own, so any
       key holder on this surface can mint a login link for any phone
       number. Whether that is acceptable depends entirely on who is
       permitted to call this method in deployment -- if it is meant to be
       reachable only by trusted internal automation, that restriction
       (a role check, or moving this behind a dedicated internal-only
       surface) is a deployment/operational decision, not something this
       function enforces on its own.

    2. Secret agreement: the secret read here
       (get_magic_link_shared_secret(), from Shared Settings.
       magic_link_shared_secret -- a Password field, configurable from the
       Shared Settings doctype UI, alongside every other TapApp secret
       such as the GCS/R2 credentials and the Worker Internal API secret)
       must be byte-identical to the Worker's own MAGIC_LINK_SECRET (set
       via `wrangler secret put`). Nothing in this codebase keeps the two
       independently-configured secrets in sync automatically; rotating
       one without the other makes every link minted here fail
       verification on the Worker side with UNAUTHORIZED, with nothing in
       Frappe's own logs to explain why. This coupling is an
       operational/runbook concern for secret rotation, external to this
       file. get_magic_link_shared_secret itself raises InvalidInput
       (mapped to a 400 by tap_app_method) if the field has never been
       configured, so an unset secret fails loudly and immediately rather
       than minting a token that can never verify.

    Per-dest_type default TTLs are Shared Settings fields
    (magic_link_ttl_home/feedback/gallery/submit/later), read via
    shared.config.secrets_cache.get_magic_link_ttl, so an operator can
    change e.g. the "feedback" link's lifetime from the Shared Settings
    doctype UI with no deploy; see that function's own docstring for how it
    resolves an unsaved-singleton default. An explicit ttl_seconds argument
    from the caller always wins over the configured default.
    """
    if dest_type not in _VALID_DEST_TYPES:
        raise InvalidInput("dest_type must be one of: " + ", ".join(_VALID_DEST_TYPES))
    if dest_type in ("feedback", "submit") and not dest_id:
        raise InvalidInput(f"dest_id is required for dest_type={dest_type}")

    ttl = ttl_seconds or get_magic_link_ttl(dest_type)

    # get_magic_link_shared_secret raises InvalidInput itself (mapped to a
    # clean 400 by tap_app_method) if Shared Settings.magic_link_shared_secret
    # has never been configured -- no separate frappe.throw guard is needed
    # here, unlike the old site_config.json-backed accessor this replaces.
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