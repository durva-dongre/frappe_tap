"""
shared/config/secrets_cache.py

Generic accessors for secrets and TapApp configuration. Most secrets live on
the Shared Settings singleton (Password/Data/Int fields), rotatable from the
doctype UI with no deploy. GCS credentials are the one exception: they live
on the GCS Settings doctype (not Shared Settings) since GCS supports multiple
bucket configs (Authenticated / Public) as separate rows.

SINGLETON-DEFAULT GAP
----------------------
Shared Settings is a Frappe Singleton ("issingle": 1): a field's `"default"`
in the doctype JSON only applies on save -- it does not retroactively
backfill a Singleton row that predates the field being added to the
schema. On a site where the Singleton has never been re-saved since a
field was introduced, frappe.get_single(...).<field> reads back as None,
not the schema default.

get_magic_link_ttl treats a stored value of `None` as "use the documented
default" rather than as a configuration error, and reserves InvalidInput
for a stored value that is explicitly non-positive (0 or negative) -- an
operator actively setting a zero/negative TTL is a real misconfiguration
worth failing loudly on, since minting a link with a dead-on-arrival TTL
would otherwise succeed silently with no indication why the link never
verifies. This None-handling is what keeps mint_magic_link functional
across every dest_type on a site that has never had Shared Settings
manually re-saved since these fields were introduced, rather than having
the whole magic-link-minting path 400 until someone opens and saves the
doctype once in the UI. The permanent fix for the underlying gap is a
migration patch that force-saves the Shared Settings singleton once after
any doctype field addition; the None-handling here is defense in depth
underneath that, not a replacement for it.

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
phone_token_ttl_seconds, by contrast, do have documented, schema-matching
defaults (HS256 / 7776000 seconds) and go through the generic
settings_cache.get/get_int accessors with those defaults supplied inline
-- the same "safe fallback for a non-secret, loud failure for a secret"
split used throughout this file.

get_worker_internal_api_timeout_seconds and get_db_retry_settings follow
the same "safe fallback" shape as the TTL accessors -- a stale/unsaved
Singleton must not make an HTTP call hang forever or make a transient
Postgres error retry logic silently misbehave, so both fall back to their
documented schema defaults (15 seconds; 3 attempts / 50ms backoff) rather
than raising or defaulting to 0.

GCS CREDENTIALS
-----------------
get_gcs_credentials reads from the GCS Settings doctype (not Shared
Settings): the row where bucket_type="Authenticated" and enabled=1.
This is a deliberate cutover -- GCS Settings supports multiple named
bucket configs (Authenticated vs Public), which a flat set of
Shared Settings fields (gcs_bucket / gcs_project_id /
gcs_service_account_json) couldn't express cleanly. There is no fallback
to the old Shared Settings fields: if no enabled Authenticated GCS
Settings row exists, this raises InvalidInput loudly -- exactly the same
"no safe default for a credential" policy used for every other secret
accessor in this file.
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
# field was added -- see module docstring). A site that has saved Shared
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

# Mirrors db_retry_attempts / db_retry_backoff_ms's own doctype-JSON
# "default"s.
_DEFAULT_DB_RETRY_ATTEMPTS = 3
_DEFAULT_DB_RETRY_BACKOFF_MS = 50

# Mirrors upload_put_url_ttl_seconds's own doctype-JSON "default".
_DEFAULT_UPLOAD_PUT_URL_TTL_SECONDS = 600

# Mirrors r2_sweep_batch_size / gallery_sweep_lookback_days /
# gallery_index_chunk_size's own doctype-JSON "default"s.
_DEFAULT_R2_SWEEP_BATCH_SIZE = 500
_DEFAULT_GALLERY_SWEEP_LOOKBACK_DAYS = 14
_DEFAULT_GALLERY_INDEX_CHUNK_SIZE = 100
_DEFAULT_SHARED_LOGS_RETENTION_DAYS = 90


def get_worker_internal_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).get_password("worker_internal_api_secret")


def get_worker_internal_api_url(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).worker_internal_api_url


def get_worker_internal_api_timeout_seconds(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """HTTP timeout (connect + read, passed straight to requests.post(...,
    timeout=...)) used by shared/storage/gallery_promotion.py for every
    Worker-internal-API call (/internal/gallery/index,
    /internal/gallery/visibility, /internal/gallery/known_ids).
    Configurable so an operator can loosen or tighten it without a deploy
    if the Worker's own response time characteristics change. Falls back
    to the documented default (15 seconds) only if the Singleton has
    never been saved since this field was added -- see module docstring."""
    return get_int("worker_internal_api_timeout_seconds", _DEFAULT_WORKER_INTERNAL_API_TIMEOUT_SECONDS, doctype)


def get_db_retry_settings(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> dict:
    """Returns {"attempts": int, "backoff_ms": int} for
    shared/db_retry.py::with_retry's retryable-Postgres-error handling.
    Both fields are configurable (Shared Settings.db_retry_attempts /
    db_retry_backoff_ms) so an operator can tune retry behavior without a
    deploy; both fall back to their documented schema defaults (3
    attempts, 50ms fixed backoff) only if the Singleton has never been
    saved since these fields were added -- see module docstring. attempts
    is clamped to a minimum of 1 (the doctype's own field description
    already states "must be at least 1"; this clamp is defense in depth
    against a misconfigured 0 or negative value silently turning every
    retryable-SQL call into a guaranteed hard failure with no attempt at
    all)."""
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


def get_gcs_credentials() -> dict:
    """Reads the enabled Authenticated GCS Settings row: {"bucket":
    bucket_name, "project_id": project_id, "service_account_json":
    credentials_json}. Not Shared Settings-backed (see module docstring)
    -- GCS Settings is its own doctype with one row per (bucket_type,
    enabled) config, since GCS needs more than one named bucket config
    (Authenticated vs Public) that a flat field set can't express.

    Raises InvalidInput if no enabled "Authenticated" row exists -- same
    "no safe default for a credential" policy as every other secret
    accessor in this file. No fallback to any Shared Settings field."""
    import frappe

    rows = frappe.get_all(
        "GCS Settings",
        filters={"bucket_type": "Authenticated", "enabled": 1},
        fields=["name", "bucket_name", "project_id"],
        limit_page_length=1,
    )
    if not rows:
        raise InvalidInput(
            "No enabled GCS Settings row found for bucket_type=Authenticated; "
            "configure one before using any GCS-backed feature"
        )
    row = rows[0]
    doc = frappe.get_doc("GCS Settings", row["name"])
    return {
        "bucket": row["bucket_name"],
        "project_id": row["project_id"],
        "service_account_json": doc.get_password("credentials_json"),
    }


def get_magic_link_shared_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """HMAC secret for magic links, verified by the Worker. Configured as
    Shared Settings.magic_link_shared_secret (a Password field), not in
    site_config.json -- this keeps every TapApp secret on one consistent
    configuration surface, rotatable from the Shared Settings doctype UI
    with no deploy and no bench console access.

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
    (the Shared Settings singleton has never been saved since this field
    was added to the schema) is treated as "use the documented default"
    instead of an error -- see module docstring."""
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
    -- one consistent, no-deploy-required configuration surface.

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


def get_r2_sweep_enabled(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> bool:
    """Kill switch for the nightly gallery R2-promotion sweep (Shared
    Settings.r2_sweep_enabled, Check, default 1/on). When off, the night's
    sweep is skipped entirely -- nothing is lost, since pending submissions
    are re-derived fresh from the D1 set-difference on the next run that
    does execute. Falls back to enabled (True) only if the Singleton has
    never been saved since this field was added -- see module docstring."""
    val = get_shared_settings(doctype).r2_sweep_enabled
    return bool(val) if val is not None else True


def get_r2_sweep_batch_size(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """Max submissions pulled per night for R2 promotion (Shared
    Settings.r2_sweep_batch_size, Int, default 500). Bounds one night's
    sweep so a large backlog can't turn into an hours-long run; any
    overflow is simply picked up by a later night's run."""
    return get_int("r2_sweep_batch_size", _DEFAULT_R2_SWEEP_BATCH_SIZE, doctype)


def get_gallery_sweep_lookback_days(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """Ceiling, in days, on how far back the nightly sweep ever looks for
    eligible submissions (Shared Settings.gallery_sweep_lookback_days,
    Int, default 14). Used as the FALLBACK window only -- on a normal
    night the sweep anchors to its own last successful run instead (see
    shared/jobs/gallery_promotion_sweep.py::_resolve_sweep_window); this
    ceiling only matters on the very first run ever, or when the gap
    since the last success exceeds it."""
    return get_int("gallery_sweep_lookback_days", _DEFAULT_GALLERY_SWEEP_LOOKBACK_DAYS, doctype)


def get_gallery_index_chunk_size(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """Rows per /internal/gallery/index call during the nightly sweep
    (Shared Settings.gallery_index_chunk_size, Int, default 100) -- should
    match the Worker's own INDEX_BATCH_MAX. This is the API-layer chunk
    size; the Worker's own D1_BATCH_HARD_CAP (a Worker-code constant, not
    configurable here) re-chunks independently on its side for D1's own
    batch-size safety."""
    return get_int("gallery_index_chunk_size", _DEFAULT_GALLERY_INDEX_CHUNK_SIZE, doctype)


def get_shared_logs_retention_days(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """How many days of Shared Logs rows survive the nightly cleanup pass
    (Shared Settings.shared_logs_retention_days, Int, default 90). The
    cleanup always runs after every other job has already written its own
    log row for tonight, so tonight's own rows are never at risk."""
    return get_int("shared_logs_retention_days", _DEFAULT_SHARED_LOGS_RETENTION_DAYS, doctype)


def get_analytics_apps_script_url(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """URL of the deployed Google Apps Script Web App that writes each
    night's analytics row to the spreadsheet (Shared Settings.
    analytics_apps_script_url). Raises InvalidInput if unset -- no safe
    default for an external endpoint URL."""
    url = get_shared_settings(doctype).analytics_apps_script_url
    if not url:
        raise InvalidInput(
            "Shared Settings.analytics_apps_script_url is not configured; "
            "set it to the deployed Apps Script Web App URL"
        )
    return url


def get_analytics_apps_script_shared_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """Shared secret sent in the body of every call to the Apps Script
    endpoint (Shared Settings.analytics_apps_script_shared_secret) --
    separate from worker_internal_api_secret, since the Apps Script
    endpoint is a different external system (Google's infrastructure, not
    the Worker); reusing the Worker's own internal secret here would mean
    a leak of either credential compromises both systems. Raises
    InvalidInput if unset."""
    secret = get_shared_settings(doctype).get_password("analytics_apps_script_shared_secret")
    if not secret:
        raise InvalidInput(
            "Shared Settings.analytics_apps_script_shared_secret is not configured; "
            "set it to the shared secret the Apps Script endpoint expects"
        )
    return secret


def get_analytics_sheet_tab_name(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    """Target tab/sheet name within the analytics spreadsheet (Shared
    Settings.analytics_sheet_tab_name, Data, default "Daily Analytics")."""
    return get("analytics_sheet_tab_name", "Daily Analytics", doctype)