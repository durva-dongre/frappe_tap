from __future__ import annotations

import os
import sys

# Make the sibling `shared/` package (tap_lms/shared/) resolvable as a bare
# top-level `shared` import. Every module in `shared/` and every API module
# in `tap_app/` does `from shared.X import Y` rather than
# `from tap_lms.shared.X import Y`, but nothing in this app's own __init__.py
# chain adds tap_lms/ itself to sys.path -- confirmed via the editable-install
# finder's MAPPING (only 'tap_lms' and 'scripts' are registered) and via
# grepping the whole app for any existing sys.path manipulation (none found).
# Without this, `import shared` raises ModuleNotFoundError the instant any
# TapApp endpoint is hit by a real request (masked by tap_app_method's own
# catch-all below as a clean-looking {"error_code": "server_error"}).
# This file is the first thing imported on every call path into TapApp
# (`from tap_lms.tap_app.api import auth/profile/progress/submission/events`),
# so patching sys.path here, before the shared import below, is sufficient.
#
# NOTE: this patch only fires once something under tap_app.api is actually
# imported. Shared Settings.on_update also calls
# `from shared.config.settings_cache import invalidate_config_cache`
# directly, with no dependency on tap_app.api -- so any process that saves
# Shared Settings without ever importing tap_app.api first (a bare bench
# console session, a migration, the desk UI) needs `shared` importable on
# its own. shared_settings.py carries the identical sys.path patch for
# exactly that reason; the two patches insert the same directory and are
# idempotent with each other regardless of which one runs first.
_APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

import functools

import frappe

from shared.errors import SharedError


def tap_app_method(fn):
    """Decorator applied to every TapApp-facing Worker route. Requires an
    authenticated Frappe session/API key (allow_guest=False), and maps any
    SharedError subclass onto the exact {http_status, error_code, message}
    shape the Worker's frappe/client.ts::mapFrappeError expects to parse --
    this is the single point of translation between shared/'s error
    vocabulary (shared/errors.py) and the Worker's wire contract, so every
    route gets identical error handling without repeating it per-endpoint.

    Any exception that is not a SharedError (a bug, an unverified doctype
    field, anything not already modeled) is still caught and reported as a
    clean {error_code: "server_error", message: "Internal server error"}
    body, with the real traceback sent to frappe.log_error for debugging.
    This matters because mapFrappeError's own res.json() parse of a raw,
    unmapped Frappe error page silently fails and falls through to
    upstreamError("Upstream service error — safe to retry"), which is the
    wrong signal for a bug that will fail identically on every retry: the
    Worker (and any caller watching for UPSTREAM_ERROR) needs a real 500
    with a parseable body, not a retry-safe-looking failure.

    frappe.local.response is a plain mutable dict that persists across
    calls within the same process/thread -- true for a bench console
    session, a test suite, or any caller that invokes more than one
    tap_app_method-wrapped function back-to-back without an intervening
    real HTTP request boundary (a real deployed HTTP request gets its own
    fresh frappe.local, so this is invisible there). Because of that, this
    wrapper explicitly clears error_code/message at the top of both
    exception branches before writing its own error fields, and clears them
    again on the success path before returning -- so no branch can ever
    leave a previous call's error_code/message sitting next to this call's
    actual result. Every exit path (success, SharedError, unmodeled
    exception) owns its own response state outright; none of them assumes
    anything about what a prior call left behind.
    """

    @frappe.whitelist(allow_guest=False)
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except SharedError as e:
            frappe.local.response.pop("error_code", None)
            frappe.local.response.pop("message", None)
            frappe.local.response.http_status_code = e.http_status
            frappe.local.response["error_code"] = e.code
            frappe.local.response["message"] = e.message
            return None
        except Exception:
            # Never let an unmodeled bug leak out as a bare, unparseable 500.
            # Log the real traceback for debugging, then return the same
            # {error_code, message} shape every other error on this surface
            # returns, so mapFrappeError can always parse a response body.
            frappe.log_error(
                title="TapApp API unhandled error",
                message=frappe.get_traceback(),
            )
            frappe.local.response.pop("error_code", None)
            frappe.local.response.pop("message", None)
            frappe.local.response.http_status_code = 500
            frappe.local.response["error_code"] = "server_error"
            frappe.local.response["message"] = "Internal server error"
            return None

        # Success path: explicitly clear any error_code/message a PRIOR call
        # on this same frappe.local may have left behind, so a stale error
        # never survives alongside this call's real, successful result.
        frappe.local.response.pop("error_code", None)
        frappe.local.response.pop("message", None)
        frappe.local.response.http_status_code = 200
        return result

    return wrapper