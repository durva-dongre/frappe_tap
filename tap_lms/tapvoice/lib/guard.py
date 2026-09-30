import frappe

from tap_lms.tapvoice.constants import BODY_SIZE_CAP_BYTES, SECRET_TTS_POD_SHARED_SECRET
from tap_lms.tapvoice.lib import runstate, tokens
from tap_lms.tapvoice.lib.secrets import get as get_secret

GENERIC_AUTH_ERROR = "unauthorized"

RATE_LIMITS = {
    "progress": (120, 60),
    "beat": (30, 60),
    "manifest": (10, 60),
    "complete": (10, 60),
}


class GuardStop(Exception):
    def __init__(self, http_code, message=GENERIC_AUTH_ERROR):
        super().__init__(message)
        self.http_code = http_code
        self.message = message


def _client_ip():
    return frappe.local.request_ip or "unknown"


def _incr(cache, key, window):
    try:
        count = cache.incrby(key, 1)
    except AttributeError:
        current = cache.get_value(key)
        count = (int(current) if current else 0) + 1
        cache.set_value(key, count)
    if count == 1:
        try:
            cache.expire(key, window)
        except Exception:
            pass
    return count


def _check_rate_limit(endpoint, key):
    limit, window = RATE_LIMITS.get(endpoint, (60, 60))
    cache_key = f"tapvoice:rate:{endpoint}:{key}"
    count = _incr(frappe.cache(), cache_key, window)
    if count > limit:
        raise GuardStop(429, "rate_limited")


def _check_body_size():
    content_length = frappe.request.content_length or 0
    if content_length > BODY_SIZE_CAP_BYTES:
        raise GuardStop(413, "body_too_large")


def _bad_auth_throttle(ip):
    cache_key = f"tapvoice:badauth:{ip}"
    count = _incr(frappe.cache(), cache_key, 300)
    if count > 20:
        raise GuardStop(429, "rate_limited")


def enter(endpoint):
    if frappe.request.method != "POST":
        raise GuardStop(405, "post_only")

    _check_body_size()

    run_id = frappe.get_request_header("X-Run-Id")
    token = frappe.get_request_header("X-Run-Token")
    ip = _client_ip()

    if not run_id or not token:
        _bad_auth_throttle(ip)
        raise GuardStop(401, GENERIC_AUTH_ERROR)

    try:
        secret = get_secret(SECRET_TTS_POD_SHARED_SECRET)
        tokens.verify(run_id, token, secret)
    except Exception:
        _bad_auth_throttle(ip)
        raise GuardStop(401, GENERIC_AUTH_ERROR)

    _check_rate_limit(endpoint, run_id)

    run = runstate.get_for_update(run_id)
    if run is None:
        raise GuardStop(401, GENERIC_AUTH_ERROR)

    if runstate.is_terminal(run.status):
        raise GuardStop(409, "run_terminal")

    return run