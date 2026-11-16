"""
tap_lms/tap_app/api/__init__.py
Decorator applied to every TapApp-facing Worker route: requires an
authenticated Frappe session/API key, maps any SharedError onto the
{http_status, error_code, message} shape the Worker's frappe/client.ts
expects, and clears frappe.local.response on every branch so no prior
call's fields can leak into this call's result within the same process.

FIX (error_code collision): _error_code_for used to slugify the message
and truncate to 60 chars for any error with no explicit error_code — two
distinct messages identical only in their first 60 chars collapsed onto
the same code again, reintroducing the exact collision problem this
function exists to solve. Long messages now get a short hash of the FULL
message appended, so distinct long messages can never collide.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

import functools

import frappe

from shared.errors import SharedError

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SLUG_MAX_LEN = 60

_GENERIC_DEFAULT_CODES = {"invalid_input", "not_found", "conflict", "forbidden", "unauthorized", "server_error"}


def _error_code_for(e: SharedError) -> str:
    """Returns e.code if a real, specific error_code was supplied by the
    raise site. Otherwise derives a stable slug from e.message. Messages
    that fit within _SLUG_MAX_LEN after slugifying are returned as-is;
    longer messages get a short hash of the FULL message appended, so two
    long messages identical only in their first 60 characters can never
    collapse onto the same code (the original bug this truncation caused)."""
    if e.code not in _GENERIC_DEFAULT_CODES:
        return e.code

    slug = _SLUG_RE.sub("_", e.message.strip().lower()).strip("_")
    if not slug:
        return e.code
    if len(slug) <= _SLUG_MAX_LEN:
        return slug

    digest = hashlib.sha1(e.message.encode("utf-8")).hexdigest()[:8]
    return f"{slug[:50]}_{digest}"


def tap_app_method(fn):
    @frappe.whitelist(allow_guest=False)
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except SharedError as e:
            frappe.local.response.pop("error_code", None)
            frappe.local.response.pop("message", None)
            frappe.local.response.http_status_code = e.http_status
            frappe.local.response["error_code"] = _error_code_for(e)
            frappe.local.response["message"] = e.message
            return None
        except Exception:
            frappe.log_error(title="TapApp API unhandled error", message=frappe.get_traceback())
            frappe.local.response.pop("error_code", None)
            frappe.local.response.pop("message", None)
            frappe.local.response.http_status_code = 500
            frappe.local.response["error_code"] = "server_error"
            frappe.local.response["message"] = "Internal server error"
            return None

        frappe.local.response.pop("error_code", None)
        frappe.local.response.pop("message", None)
        frappe.local.response.http_status_code = 200
        return result

    return wrapper