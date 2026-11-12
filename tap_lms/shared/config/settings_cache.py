"""
shared/config/settings_cache.py

Short-TTL cache in front of a single Frappe Singleton ("Single") doctype that
holds shared, cross-app configuration (reward amounts, caps, storage
credentials, internal-API secrets). Not hardcoded to one doctype name, so a
second app sharing this package can point it at its own settings singleton.

`Shared Settings`'s own `on_update` hook calls `invalidate_config_cache()` so
an edit takes effect within the TTL without a process restart -- that hook
already imports this exact function name/signature; keep it stable.
"""

from __future__ import annotations

import time

import frappe

DEFAULT_SETTINGS_DOCTYPE = "Shared Settings"
CACHE_TTL_SECONDS = 60

_CACHE: dict[str, dict] = {}


def get_shared_settings(doctype: str = DEFAULT_SETTINGS_DOCTYPE):
    slot = _CACHE.get(doctype)
    now = time.time()
    if slot is None or (now - slot["loaded_at"]) > CACHE_TTL_SECONDS:
        doc = frappe.get_single(doctype)
        slot = {"doc": doc, "loaded_at": now}
        _CACHE[doctype] = slot
    return slot["doc"]


def invalidate_config_cache(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> None:
    _CACHE.pop(doctype, None)


def invalidate_all() -> None:
    _CACHE.clear()