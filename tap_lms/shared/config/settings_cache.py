"""
shared/config/settings_cache.py

Short-TTL cache in front of a single Frappe Singleton ("Single") doctype that
holds shared, cross-app configuration (reward amounts, caps, storage
credentials, internal-API secrets, TapApp magic-link TTLs). Not hardcoded to
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
"""

from __future__ import annotations

import time

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


def invalidate_config_cache(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> None:
    _CACHE.pop(doctype, None)


def invalidate_all() -> None:
    _CACHE.clear()