"""
shared/config/secrets_cache.py

Generic accessors for secrets and TapApp configuration that live on the
shared settings singleton (Password/Data/Int fields).

Every secret used anywhere in the TapApp path -- GCS, R2, the Worker
internal API, the JWT signing secret, and the magic-link HMAC secret -- is
configured exactly the same way: as a field on the Shared Settings
doctype, readable/writable from the Shared Settings UI with no deploy and
no bench console access. There is deliberately no secret anywhere in this
module that is instead read out of Frappe's site_config.json; a single,
consistent configuration surface (Shared Settings) means an operator never
has to remember "which secrets live in the doctype vs. which ones live in
site_config.json" -- they are all in the doctype.

Magic-link TTLs (get_magic_link_ttl), the magic-link base URL
(get_magic_link_base_url), and the magic-link shared secret
(get_magic_link_shared_secret) all live here, alongside each other, so
every magic-link-related config accessor stays in one file. The TTLs and
the secret are Shared Settings fields (magic_link_ttl_home/feedback/
gallery/submit/later, magic_link_shared_secret) rather than hardcoded
Python values or site_config.json entries, so an operator can change e.g.
the "feedback" link's lifetime, or rotate the HMAC secret itself, from the
Shared Settings doctype UI with no deploy; the base URL is a Shared
Settings field for the same reason -- it differs by environment (staging
vs. production) and can change independently of a Frappe deploy.

get_magic_link_ttl treats a stored value of `None` as "the Shared Settings
singleton has never been saved since this field was added to the schema,
use the documented default" rather than as a configuration error, and
reserves InvalidInput for a stored value that is explicitly non-positive
(0 or negative) -- an operator actively setting a zero/negative TTL is a
real misconfiguration worth failing loudly on, since minting a link with a
dead-on-arrival TTL would otherwise succeed silently with no indication
why the link never verifies.

This distinction matters because Shared Settings is a Frappe Singleton: a
field's doctype-JSON "default" only applies on save, and does not
retroactively backfill a Singleton row that predates the field being added
to the schema. On such a site, every magic_link_ttl_* field reads back as
None, not its schema default -- so get_magic_link_ttl's None-handling is
what keeps mint_magic_link functional across every dest_type on a site
that has never had Shared Settings manually re-saved since these fields
were introduced, rather than having the whole magic-link-minting path 400
until someone opens and saves the doctype once in the UI. The permanent
fix for that underlying gap is a migration patch that force-saves the
Shared Settings singleton once after any doctype field addition; the
None-handling here is defense in depth underneath that, not a replacement
for it.

get_magic_link_base_url and get_magic_link_shared_secret have no such
None-handling: unlike a TTL, there is no safe default to fall back to for
either a base URL or an HMAC secret, so an unconfigured or blank value is
always a real misconfiguration and is raised as InvalidInput, not
silently defaulted or defaulted to an empty string. mint_magic_link
(tap_app/api/auth.py) relies on both functions raising loudly rather than
returning an empty string, since a magic link built from an empty base
URL, or signed with an empty secret, would silently produce a broken or
insecure link rather than a clear error at mint time.

get_jwt_secret follows the exact same "no safe fallback" reasoning as
get_magic_link_shared_secret: a signing secret has no sane default, so an
unconfigured Shared Settings.jwt_secret raises InvalidInput rather than
silently signing phone tokens with an empty key. jwt_algorithm and
phone_token_ttl_seconds, by contrast, DO have documented, schema-matching
defaults (HS256 / 7776000 seconds) and go through the generic
settings_cache.get/get_int accessors with those defaults supplied inline,
the same "safe fallback for a non-secret, loud failure for a secret"
split used throughout this file.

get_worker_internal_api_timeout_seconds and get_db_retry_settings follow
the same "safe fallback" shape as the TTL accessors -- a stale/unsaved
Singleton must not make an HTTP call hang forever or make a transient
Postgres error retry logic silently misbehave, so both fall back to their
documented schema defaults (15 seconds; 3 attempts / 50ms backoff) rather
than raising or defaulting to 0.
"""
from __future__ import annotations

from typing import Optional

from shared.config.settings_cache import DEFAULT_SETTINGS_DOCTYPE, get_shared_settings, get, get_int
from shared.errors import InvalidInput

_MAGIC_LINK_TTL_FIELD_FOR_DEST_TYPE = {
    "home": "magic_link_ttl_home",
    "feedback": "magic_link_ttl_feedback",
    "gallery": "magic_link_ttl_gallery",
    "submit": "magic_link_ttl_submit",
    "later": "magic_link_ttl_later",
}

# Mirrors each field's own doctype-JSON "default" exactly (shared_settings.json).
# Used ONLY when the stored value is None (singleton never saved since the
# field was added) -- see module docstring. A site that has saved Shared
# Settings at least once always reads its real, persisted value instead.
_MAGIC_LINK_TTL_DEFAULT_FOR_DEST_TYPE = {
    "home": 7776000,      # 90 days
    "feedback": 2592000,  # 30 days
    "gallery": 2592000,   # 30 days
    "submit": 1209600,    # 14 days
    "later": 1209600,     # 14 days
}

# Mirrors jwt_algorithm / phone_token_ttl_seconds's own doctype-JSON
# "default" exactly. Used only when the Singleton has never been saved
# since those fields were added -- see module docstring.
_DEFAULT_JWT_ALGORITHM = "HS256"
_DEFAULT_PHONE_TOKEN_TTL_SECONDS = 7776000  # 90 days

# Mirrors worker_internal_api_timeout_seconds's own doctype-JSON "default".
_DEFAULT_WORKER_INTERNAL_API_TIMEOUT_SECONDS = 15

# Mirror db_retry_attempts / db_retry_backoff_ms's own doctype-JSON
# "default"s.
_DEFAULT_DB_RETRY_ATTEMPTS = 3
_DEFAULT_DB_RETRY_BACKOFF_MS = 50

# Mirrors upload_put_url_ttl_seconds's own doctype-JSON "default".
_DEFAULT_UPLOAD_PUT_URL_TTL_SECONDS = 600


def get_worker_internal_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).get_password("worker_internal_api_secret")


def get_worker_internal_api_url(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).worker_internal_api_url


def get_worker_internal_api_timeout_seconds(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """HTTP timeout (connect + read, passed straight to requests.post(...,
    timeout=...)) used by shared/storage/gallery_promotion.py for both of
    its Worker-internal-API calls (/internal/gallery/index,
    /internal/gallery/visibility). Configurable so an operator can loosen
    or tighten it without a deploy if the Worker's own response time
    characteristics change. Falls back to the documented default (15
    seconds) only if the Singleton has never been saved since this field
    was added -- see module docstring."""
    return get_int("worker_internal_api_timeout_seconds", _DEFAULT_WORKER_INTERNAL_API_TIMEOUT_SECONDS, doctype)


def get_db_retry_settings(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> dict:
    """Returns {"attempts": int, "backoff_ms": int} for
    shared/db_retry.py::with_retry's retryable-Postgres-error handling.
    Both fields are configurable (Shared Settings.db_retry_attempts /
    db_retry_backoff_ms) so an operator can tune retry behavior without a
    deploy; both fall back to their documented schema defaults (3 attempts,
    50ms fixed backoff) only if the Singleton has never been saved since
    these fields were added -- see module docstring. attempts is clamped
    to a minimum of 1 (the doctype's own field description already states
    "must be at least 1"; this clamp is defense in depth against a
    misconfigured 0 or negative value silently turning every retryable-SQL
    call into a guaranteed hard failure with no attempt at all)."""
    attempts = get_int("db_retry_attempts", _DEFAULT_DB_RETRY_ATTEMPTS, doctype)
    backoff_ms = get_int("db_retry_backoff_ms", _DEFAULT_DB_RETRY_BACKOFF_MS, doctype)
    return {"attempts": max(attempts, 1), "backoff_ms": max(backoff_ms, 0)}


def get_r2_credentials(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> dict:
    settings = get_shared_settings(doctype)
    return {
        "account_id": settings.r2_account_id,
        "access_key_id": settings.r2_access_key_id,
        "secret_access_key": settings.get_password("r2_secret_access_key"),
        "bucket": settings.r2_bucket,
    }


def get_gcs_credentials(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> dict:
    settings = get_shared_settings(doctype)
    return {
        "bucket": settings.gcs_bucket,
        "project_id": settings.gcs_project_id,
        "service_account_json": settings.get_password("gcs_service_account_json"),
    }


def get_magic_link_shared_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """HMAC secret for magic links, verified by the Worker. Configured as
    Shared Settings.magic_link_shared_secret (a Password field), not in
    site_config.json -- this keeps every TapApp secret (GCS, R2, Worker
    Internal API, JWT, and this one) on one consistent configuration
    surface, rotatable from the Shared Settings doctype UI with no deploy
    and no bench console access.

    Raises InvalidInput if the field is unset or blank: unlike a TTL,
    there is no safe default to fall back to for a signing secret, so an
    unconfigured value is always a real misconfiguration, and must be
    raised loudly rather than silently minting a link signed with an
    empty secret (which would produce a token the Worker can never
    legitimately verify, with no indication at mint time why).
    """
    secret = get_shared_settings(doctype).get_password("magic_link_shared_secret")
    if not secret:
        raise InvalidInput(
            "Shared Settings.magic_link_shared_secret is not configured; "
            "set it to the HMAC secret shared with the Worker's own "
            "MAGIC_LINK_SECRET before minting magic links"
        )
    return secret


def get_magic_link_base_url(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """Returns the configured base URL that a minted magic-link token is
    appended to, to build the full, shareable magic_link_url returned by
    mint_magic_link. Raises InvalidInput if the field is unset or blank --
    see module docstring for why this has no silent fallback the way
    get_magic_link_ttl does. The returned value is used exactly as stored,
    with the token appended directly after it and no separator inserted,
    so the stored value itself must already end in whatever the receiving
    endpoint expects (a trailing '/', or a '?token=' style prefix)."""
    base_url = get_shared_settings(doctype).magic_link_base_url
    if not base_url:
        raise InvalidInput(
            "Shared Settings.magic_link_base_url is not configured; "
            "set it to the base URL a minted magic-link token should be appended to"
        )
    return base_url


def get_magic_link_ttl(dest_type: str, doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """Returns the configured TTL, in seconds, for a magic link of this
    dest_type, read from Shared Settings. Raises InvalidInput for an
    unrecognized dest_type, or for a configured TTL that is explicitly set
    to zero or negative (a real misconfiguration). A stored value of None
    (the Shared Settings singleton has never been saved since this field was
    added to the schema) is treated as "use the documented default" instead
    of an error -- see module docstring."""
    fieldname = _MAGIC_LINK_TTL_FIELD_FOR_DEST_TYPE.get(dest_type)
    if not fieldname:
        raise InvalidInput(f"no magic_link TTL is configured for dest_type={dest_type}")

    ttl = get_shared_settings(doctype).get(fieldname)

    if ttl is None:
        return _MAGIC_LINK_TTL_DEFAULT_FOR_DEST_TYPE[dest_type]

    if ttl <= 0:
        raise InvalidInput(
            f"Shared Settings.{fieldname} is configured with a non-positive TTL ({ttl}); "
            f"set it to a positive number of seconds in Shared Settings"
        )
    return ttl


def get_jwt_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """Signing secret for the phone-scoped JWT issued by
    shared/auth/jwt_tokens.py::issue_phone_token and verified by
    verify_phone_token. Configured as Shared Settings.jwt_secret (a
    Password field), alongside every other TapApp secret on this doctype
    (GCS, R2, Worker Internal API, magic-link HMAC secret) -- one
    consistent, no-deploy-required configuration surface.

    This is a SEPARATE secret from magic_link_shared_secret: the magic
    link and the phone token are two different credential types with two
    different lifetimes and two different verifiers (the Worker verifies
    the magic link; this JWT is verified by whichever service calls
    verify_phone_token), so they must never share a secret, and this
    accessor never falls back to the magic-link secret if its own field
    is unset.

    Raises InvalidInput if the field is unset or blank -- same reasoning
    as get_magic_link_shared_secret: there is no safe default for a
    signing secret, so an unconfigured value must fail loudly, at
    issue/verify time, rather than silently signing or attempting to
    verify tokens against an empty key.
    """
    secret = get_shared_settings(doctype).get_password("jwt_secret")
    if not secret:
        raise InvalidInput(
            "Shared Settings.jwt_secret is not configured; set it to the "
            "signing secret for phone-scoped JWTs before issuing or "
            "verifying any phone token"
        )
    return secret


def get_jwt_algorithm(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """Algorithm used by jwt.encode/jwt.decode in shared/auth/jwt_tokens.py.
    Configured as Shared Settings.jwt_algorithm (a Data field, default
    "HS256"). Unlike the signing secret, this has a safe, documented
    default and falls back to it only if the Singleton has never been
    saved since this field was added to the schema -- see module
    docstring."""
    return get("jwt_algorithm", _DEFAULT_JWT_ALGORITHM, doctype)


def get_phone_token_ttl_seconds(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """How long a phone-scoped JWT stays valid after issuance, in seconds.
    Configured as Shared Settings.phone_token_ttl_seconds (Int, default
    7776000 = 90 days). A configured value of 0 is a real, supported
    setting (issue_phone_token omits the `exp` claim entirely when this is
    <= 0, minting a token with no expiry) -- it is passed through exactly
    as stored, unlike get_magic_link_ttl, which treats <= 0 as a
    misconfiguration; see shared_settings.json's own field description for
    why a 0 TTL is intentional here rather than an error."""
    return get_int("phone_token_ttl_seconds", _DEFAULT_PHONE_TOKEN_TTL_SECONDS, doctype)


def get_upload_put_url_ttl_seconds(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """How long an upload ticket created by
    shared/submission/tickets.py::create_ticket stays valid in the Frappe
    cache before expiring. Configured as Shared Settings.
    upload_put_url_ttl_seconds (Int, default 600 = 10 minutes). Falls back
    to the documented default only if the Singleton has never been saved
    since this field was added -- see module docstring."""
    return get_int("upload_put_url_ttl_seconds", _DEFAULT_UPLOAD_PUT_URL_TTL_SECONDS, doctype)