"""
shared/config/secrets_cache.py

Generic accessors for secrets and TapApp configuration that live either on
the shared settings singleton (Password/Data/Int fields) or in Frappe's site
config (secrets with no natural doctype field, e.g. a cross-service HMAC
secret).

Magic-link TTLs (get_magic_link_ttl) and the magic-link base URL
(get_magic_link_base_url) live here, alongside get_magic_link_shared_secret,
so every magic-link-related config accessor stays in one file. The TTLs are
Shared Settings fields (magic_link_ttl_home/feedback/gallery/submit/later)
rather than a hardcoded Python dict, so an operator can change e.g. the
"feedback" link's lifetime from the Shared Settings doctype UI with no
deploy; the base URL is a Shared Settings field for the same reason --
it differs by environment (staging vs. production) and can change
independently of a Frappe deploy.

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

get_magic_link_base_url has no such None-handling: unlike a TTL, there is
no safe numeric default to fall back to for a base URL, so an unconfigured
or blank value is always a real misconfiguration and is raised as
InvalidInput, not silently defaulted. mint_magic_link (tap_app/api/auth.py)
relies on this function raising loudly rather than returning an empty
string, since a magic link built from an empty base URL would silently
produce an unusable link rather than a clear error at mint time.
"""
from __future__ import annotations

from typing import Optional

import frappe

from shared.config.settings_cache import DEFAULT_SETTINGS_DOCTYPE, get_shared_settings
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


def get_worker_internal_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).get_password("worker_internal_api_secret")


def get_worker_internal_api_url(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).worker_internal_api_url


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


def get_magic_link_shared_secret() -> Optional[str]:
    """HMAC secret for magic links, verified by the Worker. Lives in
    site_config.json (not a doctype field):
        bench --site <site> set-config tapapp_magic_link_secret "<secret>"
    """
    return frappe.conf.get("tapapp_magic_link_secret")


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