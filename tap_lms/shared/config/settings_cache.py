"""
shared/config/settings_cache.py

Short-TTL cache in front of a single Frappe Singleton ("Single") doctype that
holds shared, cross-app configuration (reward amounts, caps, storage
credentials, internal-API secrets, TapApp magic-link TTLs, JWT config,
upload-ticket TTL, worker HTTP timeout, DB retry tuning). Not hardcoded to
one doctype name, so a second app sharing this package can point it at its
own settings singleton.

`Shared Settings`'s own `on_update` hook calls `invalidate_config_cache()` so
an edit takes effect within the TTL without a process restart -- that hook
already imports this exact function name/signature; keep it stable.

The cache's own TTL is itself a Shared Settings field
(config_cache_ttl_seconds) rather than a hardcoded Python constant, so an
operator can tune it from the doctype UI with no deploy. It is read off the
doc that was just loaded into the cache slot on every load, not from a
separate always-fresh query -- so a change to config_cache_ttl_seconds takes
effect the next time the current slot expires and reloads (bounded by the
OLD ttl, at most one stale read), not instantly and not stuck forever. A
first-ever load (empty cache) has no prior TTL to go by, so it uses
_FALLBACK_TTL_SECONDS purely to size that first load -- it never silently
overrides whatever config_cache_ttl_seconds says once a doc has actually
been read.

GENERIC ACCESSORS (get / get_int)
----------------------------------
`get(fieldname, default)` and `get_int(fieldname, default)` are thin,
generic reads against the cached Shared Settings singleton, for callers
that want "whatever this field is configured as, or a documented default
if the singleton has never been saved since the field was added" without
writing a dedicated accessor function for every single field.

This is exactly the same "Singleton field default only applies on save"
gap documented at length in shared/config/secrets_cache.py (see
get_magic_link_ttl there) and shared/progress/rewards.py (see that
module's docstring): a field's doctype-JSON "default" never backfills a
Singleton row that predates the field being added to the schema, so
`frappe.get_single(...).<field>` can read back as None even though the
doctype JSON declares a default. `get`/`get_int` treat a stored value of
None as "use the caller's supplied default" rather than as an error or as
a literal None -- this is what keeps shared/auth/jwt_tokens.py and
shared/submission/tickets.py (both of which call these functions directly)
working correctly on a site that has never re-saved Shared Settings since
jwt_algorithm/phone_token_ttl_seconds/upload_put_url_ttl_seconds were added
to the schema, exactly as get_magic_link_ttl already does for the
magic-link TTL fields.

`get_int` additionally coerces whatever comes back (Frappe Int fields
normally come back as a real Python int already, but a raw/legacy value
could in principle be a numeric string) to int before returning, so a
caller doing arithmetic on the result (e.g. `ttl_seconds or
get_magic_link_ttl(...)`, or `now + ttl` in jwt_tokens.py) never has to
guard against a string creeping through.

These two are intentionally generic/untyped (unlike the dedicated,
self-documenting accessors in shared/config/secrets_cache.py and
shared/progress/rewards.py) -- use a dedicated accessor instead whenever
one already exists for the field you need; reach for `get`/`get_int`
directly only for fields that don't have one yet.
"""

from __future__ import annotations

import time
from typing import Any

import frappe

DEFAULT_SETTINGS_DOCTYPE = "Shared Settings"

# Used only to size the very first cache load, before any Shared Settings
# doc has been read at all (so there is no stored config_cache_ttl_seconds
# yet to honor). Every load after that uses the doc's own
# config_cache_ttl_seconds field -- see get_shared_settings below.
_FALLBACK_TTL_SECONDS = 60

_CACHE: dict[str, dict] = {}


def get_shared_settings(doctype: str = DEFAULT_SETTINGS_DOCTYPE):
    slot = _CACHE.get(doctype)
    now = time.time()
    if slot is None or (now - slot["loaded_at"]) > slot["ttl_seconds"]:
        doc = frappe.get_single(doctype)
        ttl_seconds = getattr(doc, "config_cache_ttl_seconds", None) or _FALLBACK_TTL_SECONDS
        slot = {"doc": doc, "loaded_at": now, "ttl_seconds": ttl_seconds}
        _CACHE[doctype] = slot
    return slot["doc"]


def get(fieldname: str, default: Any = None, doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> Any:
    """Generic read of a single Shared Settings field, off the cached
    singleton. Returns `default` if the stored value is None (field never
    saved since being added to the schema -- see module docstring) -- NOT
    if the stored value is falsy-but-real (0, "", False all pass through
    unchanged, since those are legitimate configured values, not "unset").
    """
    value = getattr(get_shared_settings(doctype), fieldname, None)
    return value if value is not None else default


def get_int(fieldname: str, default: int = 0, doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> int:
    """Generic int read of a single Shared Settings field. Same None
    handling as get() above, with the result additionally coerced to int
    so arithmetic on the caller's side never has to guard against a
    numeric-string value creeping through from a raw/legacy row."""
    value = getattr(get_shared_settings(doctype), fieldname, None)
    if value is None:
        return default
    return int(value)


def invalidate_config_cache(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> None:
    _CACHE.pop(doctype, None)


def invalidate_all() -> None:
    _CACHE.clear()