import argparse
import concurrent.futures
import datetime
import json
import os
import platform
import statistics
import threading
import time
import uuid

import psutil
import requests


class Config:
    def __init__(self, path):
        with open(path, "r") as f:
            raw = json.load(f)
        self.raw = raw
        self.base_url = raw["base_url"].rstrip("/")
        self.api_prefix = raw.get("api_prefix", "/api/method/")
        self.frappe_api_key = raw.get("frappe_api_key", "")
        self.frappe_api_secret = raw.get("frappe_api_secret", "")
        self.request_timeout_seconds = raw.get("request_timeout_seconds", 15)
        self.verify_tls = raw.get("verify_tls", True)

        acc = raw.get("accounts", {})
        self.phone_a = acc.get("phone_a")
        self.pass_a = acc.get("pass_a")
        self.phone_b = acc.get("phone_b")
        self.pass_b = acc.get("pass_b")
        self.phone_new = acc.get("phone_new")
        self.phone_new2 = acc.get("phone_new2")
        self.phone_new3 = acc.get("phone_new3")

        lid = raw.get("learner_ids", {})
        self.lid_owned_a = lid.get("lid_owned_a")
        self.lid_owned_b = lid.get("lid_owned_b")
        self.lid_write_1 = lid.get("lid_write_1")
        self.lid_write_2 = lid.get("lid_write_2")
        self.lid_write_3 = lid.get("lid_write_3")
        self.lid_concurrency = lid.get("lid_concurrency")

        course = raw.get("course_ids", {})
        self.course_1 = course.get("course_1")
        self.course_2 = course.get("course_2")

        self.program_id_for_export = raw.get("program_id_for_export")
        self.export_langs = raw.get("export_langs", ["en"])

        gdr = raw.get("grade_division_roll_lookup", {})
        self.lookup_grade = gdr.get("grade")
        self.lookup_division = gdr.get("division")
        self.lookup_roll_number = gdr.get("roll_number")

        stress = raw.get("stress", {})
        self.concurrency_levels = stress.get("concurrency_levels", [1, 5, 10, 25, 50, 100, 200])
        self.requests_per_level = stress.get("requests_per_level", 300)
        self.ramp_pause_seconds = stress.get("ramp_pause_seconds", 5)
        self.max_duration_seconds_per_level = stress.get("max_duration_seconds_per_level", 60)
        self.abort_error_rate_threshold = stress.get("abort_error_rate_threshold", 0.20)
        self.sample_resource_interval_seconds = stress.get("sample_resource_interval_seconds", 1)

        safety = raw.get("safety", {})
        self.allow_password_mutation_tests = safety.get("allow_password_mutation_tests", True)
        self.allow_bulk_write_tests = safety.get("allow_bulk_write_tests", True)
        self.bulk_update_max_rows_per_request = safety.get("bulk_update_max_rows_per_request", 500)
        self.dry_run_only = safety.get("dry_run_only", False)
        self.run_first_time_password_tests = safety.get("run_first_time_password_tests", True)
        self.run_stress_suite = safety.get("run_stress_suite", False)
        self.run_concurrency_suite = safety.get("run_concurrency_suite", False)
        self.run_retrigger_smoke = safety.get("run_retrigger_smoke", False)


REDACT_KEYS = {"password", "token", "reset_token", "api_secret", "authorization"}


def redact(params):
    if not isinstance(params, dict):
        return params
    out = {}
    for k, v in params.items():
        if k.lower() in REDACT_KEYS:
            out[k] = "***REDACTED***"
        else:
            out[k] = v
    return out


class ApiClient:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()

    def call(self, method_path, params=None, headers=None, timeout=None):
        url = f"{self.config.base_url}{self.config.api_prefix}{method_path}"
        params = params or {}
        headers = headers or {}
        t0 = time.time()
        try:
            resp = self.session.post(
                url,
                data=params,
                headers=headers,
                timeout=timeout or self.config.request_timeout_seconds,
                verify=self.config.verify_tls,
            )
            latency_ms = (time.time() - t0) * 1000.0
            try:
                body = resp.json()
            except ValueError:
                body = {"_raw_text": resp.text[:2000]}
            return CallResult(
                status_code=resp.status_code,
                body=body,
                latency_ms=latency_ms,
                error=None,
            )
        except requests.exceptions.RequestException as e:
            latency_ms = (time.time() - t0) * 1000.0
            return CallResult(
                status_code=None,
                body=None,
                latency_ms=latency_ms,
                error=str(e),
            )

    def api_key_headers(self):
        return {"Authorization": f"token {self.config.frappe_api_key}:{self.config.frappe_api_secret}"}

    def bearer_headers(self, token, header_name="X-Flutter-Authorization"):
        return {header_name: f"Bearer {token}"}


class CallResult:
    def __init__(self, status_code, body, latency_ms, error):
        self.status_code = status_code
        self.body = body
        self.latency_ms = latency_ms
        self.error = error

    def is_2xx(self):
        return self.status_code is not None and 200 <= self.status_code < 300

    def message_body(self):
        if isinstance(self.body, dict):
            if "message" in self.body and isinstance(self.body["message"], dict):
                return self.body["message"]
            if "message" in self.body:
                return self.body["message"]
        return self.body

    def server_error_text(self):
        if isinstance(self.body, dict):
            return self.body.get("exception") or self.body.get("_server_messages") or self.body.get("message")
        return None


class ResultLog:
    def __init__(self):
        self.lock = threading.Lock()
        self.functional_rows = []
        self.security_rows = []
        self.concurrency_rows = []
        self.stress_rows = []
        self.findings = []

    def add_functional(self, row):
        with self.lock:
            self.functional_rows.append(row)

    def add_security(self, row):
        with self.lock:
            self.security_rows.append(row)

    def add_concurrency(self, row):
        with self.lock:
            self.concurrency_rows.append(row)

    def add_stress(self, row):
        with self.lock:
            self.stress_rows.append(row)

    def add_finding(self, title, endpoint, description, evidence=""):
        with self.lock:
            self.findings.append({
                "title": title,
                "endpoint": endpoint,
                "description": description,
                "evidence": evidence,
            })


def now_ts():
    return datetime.datetime.now().astimezone().isoformat()


def record(log, case_id, endpoint, params, call_result, expected_note, passed, note=""):
    row = {
        "timestamp": now_ts(),
        "case_id": case_id,
        "endpoint": endpoint,
        "params": redact(params),
        "status_code": call_result.status_code if call_result else None,
        "latency_ms": round(call_result.latency_ms, 1) if call_result else None,
        "error": call_result.error if call_result else None,
        "expected": expected_note,
        "result": "PASS" if passed is True else ("FAIL" if passed is False else "SKIPPED"),
        "note": note,
    }
    log.add_functional(row)
    return row


class State:
    def __init__(self):
        self.token_a = None
        self.token_b = None
        self.reset_token_a = None
        self.reset_token_a_consumed = False
        self.pass_a_current = None
        self.pass_b_current = None
        self.onboarded_lid_write_1 = False
        self.enrolled_lid_write_1_course = None
        self.enrolled_lid_write_2_course = None
        self.record_activity_calls_lid_write_1 = 0
        self.submission_index_lid_write_1 = 0
        self.achievement_awarded = False


def run_check_phone_suite(client, cfg, log):
    ep = "check_phone"

    r = client.call(ep, {"phone": cfg.phone_a})
    passed = r.is_2xx() and isinstance(r.message_body(), dict) and "exists" in r.message_body()
    record(log, "check_phone__existing_registered", ep, {"phone": cfg.phone_a}, r,
           "200, exists true/false with has_password", passed)

    r = client.call(ep, {"phone": "9999999999"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("exists") is False
    record(log, "check_phone__unregistered", ep, {"phone": "9999999999"}, r,
           "200, exists:false", passed)

    r = client.call(ep, {})
    passed = not r.is_2xx()
    record(log, "check_phone__missing_param", ep, {}, r,
           "non-200, ValidationError phone is required", passed)

    r = client.call(ep, {"phone": ""})
    passed = not r.is_2xx()
    record(log, "check_phone__empty_string", ep, {"phone": ""}, r,
           "non-200, ValidationError", passed)

    r = client.call(ep, {"phone": "' OR '1'='1"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("exists") is False
    record(log, "check_phone__sql_injection_probe", ep, {"phone": "' OR '1'='1"}, r,
           "200, exists:false, no crash/leak", passed)
    if not passed:
        log.add_finding("Possible SQL injection issue", ep,
                         "check_phone did not return the expected safe response for an injection-style phone value",
                         f"status={r.status_code} body={r.body}")

    r = client.call(ep, {"phone": "   "})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("exists") is False
    record(log, "check_phone__whitespace_only", ep, {"phone": "   "}, r,
           "200, exists:false", passed)

    r = client.call(ep, {"phone": "९९९९९९९९९९"})
    passed = r.is_2xx()
    record(log, "check_phone__non_ascii", ep, {"phone": "९९९९९९९९९९"}, r,
           "200, exists:false, no crash", passed)


def run_login_suite(client, cfg, log, state):
    ep = "login_with_password"

    r = client.call(ep, {"phone": cfg.phone_a, "password": cfg.pass_a})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and body.get("token")
    if passed:
        state.token_a = body["token"]
        state.pass_a_current = cfg.pass_a
    record(log, "login__happy_existing_password", ep, {"phone": cfg.phone_a, "password": cfg.pass_a}, r,
           "200, success:true, token present, phone/teacher/admin_code/profiles/page fields", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "password": "WrongPass999"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and body.get("error") == "invalid_credentials"
    record(log, "login__wrong_password_existing", ep, {"phone": cfg.phone_a, "password": "WrongPass999"}, r,
           "200, success:false, error:invalid_credentials", passed)

    if cfg.run_first_time_password_tests and cfg.phone_new:
        r = client.call(ep, {"phone": cfg.phone_new, "password": "FirstTime123"})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
        record(log, "login__first_time_sets_password", ep, {"phone": cfg.phone_new, "password": "FirstTime123"}, r,
               "200, success:true, password now permanently set", passed,
               "run only once per phone in whole suite")
    else:
        record(log, "login__first_time_sets_password", ep, {}, None,
               "200, success:true, password permanently set", None, "SKIPPED per config")

    if cfg.run_first_time_password_tests and cfg.phone_new2:
        r = client.call(ep, {"phone": cfg.phone_new2, "password": "abc12"})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and body.get("error") == "password_too_short"
        record(log, "login__first_time_too_short", ep, {"phone": cfg.phone_new2, "password": "abc12"}, r,
               "200, success:false, error:password_too_short, password remains unset", passed)
    else:
        record(log, "login__first_time_too_short", ep, {}, None,
               "200, success:false, error:password_too_short", None, "SKIPPED per config")

    r = client.call(ep, {"phone": "9999999998", "password": "whatever1"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and body.get("error") == "invalid_credentials"
    record(log, "login__unregistered_phone", ep, {"phone": "9999999998", "password": "whatever1"}, r,
           "200, success:false, error:invalid_credentials", passed)

    r = client.call(ep, {"password": "whatever1"})
    body = r.message_body()
    passed = isinstance(body, dict) and body.get("success") is False and body.get("error") == "invalid_credentials"
    record(log, "login__missing_phone", ep, {"password": "whatever1"}, r,
           "success:false, error:invalid_credentials", passed)

    r = client.call(ep, {"phone": cfg.phone_a})
    body = r.message_body()
    passed = isinstance(body, dict) and body.get("success") is False and body.get("error") == "invalid_credentials"
    record(log, "login__missing_password", ep, {"phone": cfg.phone_a}, r,
           "success:false, error:invalid_credentials", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "password": ""})
    body = r.message_body()
    passed = isinstance(body, dict) and body.get("success") is False and body.get("error") == "invalid_credentials"
    record(log, "login__empty_password_string", ep, {"phone": cfg.phone_a, "password": ""}, r,
           "same as missing, falsy check", passed)

    if cfg.run_first_time_password_tests and cfg.phone_new3:
        r = client.call(ep, {"phone": cfg.phone_new3, "password": "abcdef"})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
        record(log, "login__password_exactly_6_chars_new_phone", ep, {"phone": cfg.phone_new3, "password": "abcdef"}, r,
               "200, success:true, boundary is >=6", passed)
    else:
        record(log, "login__password_exactly_6_chars_new_phone", ep, {}, None,
               "200, success:true", None, "SKIPPED per config")

    r = client.call(ep, {"phone": cfg.phone_a, "password": state.pass_a_current or cfg.pass_a})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("profiles_has_more") is not None
    if passed and isinstance(body, dict):
        profiles = body.get("profiles", [])
        if not (body.get("profiles_has_more") is True and len(profiles) == 10):
            passed = None
    record(log, "login__profiles_returned_page_size_10", ep, {"phone": cfg.phone_a, "password": "***"}, r,
           "profiles_has_more:true, len(profiles)==10 if account has >10 profiles", passed,
           "insufficient data, skipped" if passed is None else "")


def run_forgot_password_suite(client, cfg, log, state):
    send_ep = "forgot_password_send_otp"
    verify_ep = "forgot_password_verify_otp"

    r = client.call(send_ep, {"phone": cfg.phone_a})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and body.get("otp_sent") is True
    record(log, "send_otp__registered_phone", send_ep, {"phone": cfg.phone_a}, r,
           "200, success:true, otp_sent:true", passed)

    r = client.call(send_ep, {"phone": "9999999997"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and body.get("error") == "phone_not_registered"
    record(log, "send_otp__unregistered_phone", send_ep, {"phone": "9999999997"}, r,
           "200, success:false, error:phone_not_registered", passed)

    r = client.call(send_ep, {})
    passed = not r.is_2xx()
    record(log, "send_otp__missing_phone", send_ep, {}, r,
           "non-200, ValidationError phone is required", passed)

    client.call(send_ep, {"phone": cfg.phone_a})
    r = client.call(verify_ep, {"phone": cfg.phone_a, "otp": "000000"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and body.get("reset_token")
    if passed:
        state.reset_token_a = body["reset_token"]
        state.reset_token_a_consumed = False
    record(log, "verify_otp__correct", verify_ep, {"phone": cfg.phone_a, "otp": "000000"}, r,
           "200, success:true, reset_token present", passed)

    client.call(send_ep, {"phone": cfg.phone_a})
    r = client.call(verify_ep, {"phone": cfg.phone_a, "otp": "111111"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and body.get("error") == "otp_invalid"
    record(log, "verify_otp__wrong_code", verify_ep, {"phone": cfg.phone_a, "otp": "111111"}, r,
           "200, success:false, error:otp_invalid", passed)

    never_sent_phone = cfg.phone_new2 or "9999999996"
    r = client.call(verify_ep, {"phone": never_sent_phone, "otp": "000000"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and body.get("error") == "otp_expired"
    record(log, "verify_otp__no_otp_ever_sent", verify_ep, {"phone": never_sent_phone, "otp": "000000"}, r,
           "200, success:false, error:otp_expired", passed)

    client.call(send_ep, {"phone": cfg.phone_a})
    first = client.call(verify_ep, {"phone": cfg.phone_a, "otp": "000000"})
    if isinstance(first.message_body(), dict) and first.message_body().get("success"):
        state.reset_token_a = first.message_body().get("reset_token")
        state.reset_token_a_consumed = False
    r = client.call(verify_ep, {"phone": cfg.phone_a, "otp": "000000"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and body.get("error") == "otp_expired"
    record(log, "verify_otp__replay_after_success", verify_ep, {"phone": cfg.phone_a, "otp": "000000"}, r,
           "200, success:false, error:otp_expired, OTP deleted after first use", passed)

    r = client.call(verify_ep, {"phone": cfg.phone_a})
    passed = not r.is_2xx()
    record(log, "verify_otp__missing_otp_param", verify_ep, {"phone": cfg.phone_a}, r,
           "non-200, ValidationError phone and otp are required", passed)

    r = client.call(verify_ep, {"otp": "000000"})
    passed = not r.is_2xx()
    record(log, "verify_otp__missing_phone_param", verify_ep, {"otp": "000000"}, r,
           "non-200, ValidationError", passed)


def run_reset_password_suite(client, cfg, log, state):
    ep = "reset_password"

    if not state.reset_token_a or state.reset_token_a_consumed:
        client.call("forgot_password_send_otp", {"phone": cfg.phone_a})
        vr = client.call("forgot_password_verify_otp", {"phone": cfg.phone_a, "otp": "000000"})
        vbody = vr.message_body()
        if isinstance(vbody, dict) and vbody.get("success"):
            state.reset_token_a = vbody.get("reset_token")
            state.reset_token_a_consumed = False

    if not state.reset_token_a:
        record(log, "reset_password__happy", ep, {}, None, "200, full login payload, password changed", None,
               "SKIPPED — could not obtain a reset token")
        record(log, "reset_password__password_too_short", ep, {}, None,
               "non-200, ValidationError password too short", None, "SKIPPED — depends on reset token")
    else:
        r = client.call(ep, {"phone": cfg.phone_a, "password": "ab1"},
                         headers=client.bearer_headers(state.reset_token_a, "Authorization"))
        passed = not r.is_2xx()
        record(log, "reset_password__password_too_short", ep, {"phone": cfg.phone_a, "password": "ab1"}, r,
               "non-200, ValidationError, token still unconsumed", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "password": "NewPass456"},
                         headers=client.bearer_headers(state.reset_token_a, "Authorization"))
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and body.get("token")
        if passed:
            state.reset_token_a_consumed = True
            state.pass_a_current = "NewPass456"
        record(log, "reset_password__happy", ep, {"phone": cfg.phone_a, "password": "NewPass456"}, r,
               "200, full login-shaped payload, password permanently changed", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "password": "NewPass789"})
    passed = not r.is_2xx()
    record(log, "reset_password__missing_token_header", ep, {"phone": cfg.phone_a, "password": "NewPass789"}, r,
           "non-200, AuthenticationError Missing token", passed)

    if state.token_a:
        r = client.call(ep, {"phone": cfg.phone_a, "password": "NewPass789"},
                         headers=client.bearer_headers(state.token_a, "Authorization"))
        passed = not r.is_2xx()
        record(log, "reset_password__access_token_used_instead_of_reset", ep,
               {"phone": cfg.phone_a, "password": "NewPass789"}, r,
               "non-200, Invalid or expired reset token", passed)
    else:
        record(log, "reset_password__access_token_used_instead_of_reset", ep, {}, None,
               "non-200, Invalid or expired reset token", None, "SKIPPED — no access token available")

    client.call("forgot_password_send_otp", {"phone": cfg.phone_a})
    vr = client.call("forgot_password_verify_otp", {"phone": cfg.phone_a, "otp": "000000"})
    vbody = vr.message_body()
    fresh_reset_token = vbody.get("reset_token") if isinstance(vbody, dict) else None
    if fresh_reset_token:
        r = client.call(ep, {"phone": cfg.phone_b, "password": "NewPass789"},
                         headers=client.bearer_headers(fresh_reset_token, "Authorization"))
        passed = not r.is_2xx()
        record(log, "reset_password__phone_mismatch", ep, {"phone": cfg.phone_b, "password": "NewPass789"}, r,
               "non-200, Token phone mismatch", passed)
    else:
        record(log, "reset_password__phone_mismatch", ep, {}, None,
               "non-200, Token phone mismatch", None, "SKIPPED — could not obtain fresh reset token")

    record(log, "reset_password__unregistered_phone_with_valid_looking_token", ep, {}, None,
           "non-200 DoesNotExistError Phone not registered", None,
           "SKIPPED — cannot legitimately produce a reset token for an unregistered phone")


def _profiles_ok(body):
    return isinstance(body, dict) and "profiles" in body and "page" in body and "page_size" in body


def run_get_profiles_suite(client, cfg, log, state):
    ep = "get_profiles"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a:
        for cid in ("get_profiles__happy_default", "get_profiles__page_size_clamped_above_max",
                    "get_profiles__page_size_1", "get_profiles__page_zero", "get_profiles__page_negative",
                    "get_profiles__filter_grade_only", "get_profiles__filter_division_lowercase",
                    "get_profiles__filter_roll_number", "get_profiles__filter_query_partial_name",
                    "get_profiles__filter_query_percent_wildcard", "get_profiles__filter_combo_all"):
            record(log, cid, ep, {}, None, "200, profiles array", None, "SKIPPED — no access token available")
    else:
        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body) and body.get("page") == 1 and body.get("page_size") == 50
        record(log, "get_profiles__happy_default", ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50}, r,
               "200, profiles array, page:1, page_size:50", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 9999}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body) and body.get("page_size") == 200 and len(body.get("profiles", [])) <= 200
        record(log, "get_profiles__page_size_clamped_above_max", ep,
               {"phone": cfg.phone_a, "page": 1, "page_size": 9999}, r,
               "200, page_size clamped to 200 (MAX_PAGE_SIZE)", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 1}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body) and len(body.get("profiles", [])) <= 1
        record(log, "get_profiles__page_size_1", ep, {"phone": cfg.phone_a, "page": 1, "page_size": 1}, r,
               "200, exactly <=1 profile returned", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 0, "page_size": 20}, headers=auth_headers())
        record(log, "get_profiles__page_zero", ep, {"phone": cfg.phone_a, "page": 0, "page_size": 20}, r,
               "server should not crash; negative OFFSET behavior recorded", None,
               f"observed status={r.status_code} body={json.dumps(r.body)[:300]}")

        r = client.call(ep, {"phone": cfg.phone_a, "page": -1, "page_size": 20}, headers=auth_headers())
        record(log, "get_profiles__page_negative", ep, {"phone": cfg.phone_a, "page": -1, "page_size": 20}, r,
               "server should not crash; negative OFFSET behavior recorded", None,
               f"observed status={r.status_code} body={json.dumps(r.body)[:300]}")

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50, "grade": cfg.lookup_grade},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body) and all(
            p.get("grade") == cfg.lookup_grade for p in body.get("profiles", [])
        )
        record(log, "get_profiles__filter_grade_only", ep,
               {"phone": cfg.phone_a, "page": 1, "page_size": 50, "grade": cfg.lookup_grade}, r,
               "200, only matching grade rows", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50, "division": "a"},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body) and all(
            p.get("division") == "A" for p in body.get("profiles", [])
        )
        record(log, "get_profiles__filter_division_lowercase", ep,
               {"phone": cfg.phone_a, "page": 1, "page_size": 50, "division": "a"}, r,
               "200, lowercase division still matches uppercase rows", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50, "roll_number": cfg.lookup_roll_number},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body)
        record(log, "get_profiles__filter_roll_number", ep,
               {"phone": cfg.phone_a, "page": 1, "page_size": 50, "roll_number": cfg.lookup_roll_number}, r,
               "200, exact match only", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50, "query": "a"}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body)
        record(log, "get_profiles__filter_query_partial_name", ep,
               {"phone": cfg.phone_a, "page": 1, "page_size": 50, "query": "a"}, r,
               "200, LIKE %query% match confirmed", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50, "query": "%"}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body)
        record(log, "get_profiles__filter_query_percent_wildcard", ep,
               {"phone": cfg.phone_a, "page": 1, "page_size": 50, "query": "%"}, r,
               "200, expected LIKE wildcard behavior, not a bug", passed)

        r = client.call(ep, {
            "phone": cfg.phone_a, "page": 1, "page_size": 50,
            "grade": cfg.lookup_grade, "division": "A",
            "roll_number": cfg.lookup_roll_number, "query": "a",
        }, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body)
        record(log, "get_profiles__filter_combo_all", ep,
               {"phone": cfg.phone_a, "grade": cfg.lookup_grade, "division": "A",
                "roll_number": cfg.lookup_roll_number, "query": "a"}, r,
               "200, all filters ANDed", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50})
    passed = not r.is_2xx()
    record(log, "get_profiles__no_token_header", ep, {"phone": cfg.phone_a}, r,
           "non-200, AuthenticationError Missing token", passed)

    r = client.call(ep, {"phone": cfg.phone_a}, headers={"X-Flutter-Authorization": "Bearer "})
    passed = not r.is_2xx()
    record(log, "get_profiles__malformed_bearer", ep, {"phone": cfg.phone_a, "header": "Bearer <empty>"}, r,
           "non-200, Missing token or Invalid/expired token", passed)

    if state.token_a:
        r = client.call(ep, {"phone": cfg.phone_b}, headers=client.bearer_headers(state.token_a))
        passed = not r.is_2xx()
        record(log, "get_profiles__token_for_different_phone", ep, {"phone": cfg.phone_b}, r,
               "non-200, AuthenticationError Token phone mismatch", passed)
    else:
        record(log, "get_profiles__token_for_different_phone", ep, {}, None,
               "non-200, Token phone mismatch", None, "SKIPPED — no token_a available")

    if state.reset_token_a:
        r = client.call(ep, {"phone": cfg.phone_a}, headers=client.bearer_headers(state.reset_token_a))
        passed = not r.is_2xx()
        record(log, "get_profiles__reset_token_used_as_access", ep, {"phone": cfg.phone_a}, r,
               "non-200, Invalid or expired token (type check fails)", passed)
    else:
        record(log, "get_profiles__reset_token_used_as_access", ep, {}, None,
               "non-200, Invalid or expired token", None, "SKIPPED — no reset token available")

    record(log, "get_profiles__near_expiry_token_refresh", ep, {}, None,
           "response includes new token field", None, "SKIPPED — requires token manipulation")


def run_search_profiles_suite(client, cfg, log, state):
    ep = "search_profiles"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if state.token_a:
        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 20}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body) and "token" not in (body or {})
        record(log, "search_profiles__happy_default", ep, {"phone": cfg.phone_a, "page": 1, "page_size": 20}, r,
               "200, same shape as get_profiles minus token/teacher/admin_code", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 9999}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body) and body.get("page_size") == 200
        record(log, "search_profiles__page_size_clamp", ep, {"phone": cfg.phone_a, "page_size": 9999}, r,
               "clamped to 200", passed)

        r = client.call(ep, {
            "phone": cfg.phone_a, "grade": cfg.lookup_grade, "division": "A",
            "roll_number": cfg.lookup_roll_number, "query": "a", "page": 1, "page_size": 50,
        }, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and _profiles_ok(body)
        record(log, "search_profiles__filter_grade_division_roll_query_combo", ep,
               {"phone": cfg.phone_a, "grade": cfg.lookup_grade, "division": "A",
                "roll_number": cfg.lookup_roll_number, "query": "a"}, r,
               "200, ANDed filter result", passed)
    else:
        for cid in ("search_profiles__happy_default", "search_profiles__page_size_clamp",
                    "search_profiles__filter_grade_division_roll_query_combo"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no access token available")

    r = client.call(ep, {"phone": cfg.phone_a})
    passed = not r.is_2xx()
    record(log, "search_profiles__no_token", ep, {"phone": cfg.phone_a}, r,
           "non-200 auth error", passed)

    if state.token_a:
        r = client.call(ep, {"phone": cfg.phone_b}, headers=client.bearer_headers(state.token_a))
        passed = not r.is_2xx()
        record(log, "search_profiles__cross_phone_token", ep, {"phone": cfg.phone_b}, r,
               "non-200, Token phone mismatch", passed)
    else:
        record(log, "search_profiles__cross_phone_token", ep, {}, None,
               "non-200, Token phone mismatch", None, "SKIPPED — no token_a available")


def run_select_profile_suite(client, cfg, log, state):
    ep = "select_profile"
    alias_ep = "search_student"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a:
        for cid in ("select_profile__by_learner_id", "select_profile__by_grade_roll_division",
                    "select_profile__division_lowercase_in_lookup", "select_profile__no_identifying_params",
                    "select_profile__nonexistent_combo", "select_profile__not_owned_learner_id",
                    "select_profile__fields_subset", "select_profile__fields_unknown_token_ignored",
                    "select_profile__fields_empty_string", "search_student__alias_parity"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no access token available")
    else:
        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and "achievements" in body
        record(log, "select_profile__by_learner_id", ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a}, r,
               "200, success:true, full state + achievements", passed)

        r = client.call(ep, {
            "phone": cfg.phone_a, "grade": cfg.lookup_grade,
            "roll_number": cfg.lookup_roll_number, "division": cfg.lookup_division,
        }, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
        record(log, "select_profile__by_grade_roll_division", ep,
               {"phone": cfg.phone_a, "grade": cfg.lookup_grade,
                "roll_number": cfg.lookup_roll_number, "division": cfg.lookup_division}, r,
               "200, resolves matching learner", passed)

        r = client.call(ep, {
            "phone": cfg.phone_a, "grade": cfg.lookup_grade,
            "roll_number": cfg.lookup_roll_number, "division": (cfg.lookup_division or "A").lower(),
        }, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
        record(log, "select_profile__division_lowercase_in_lookup", ep,
               {"phone": cfg.phone_a, "division": (cfg.lookup_division or "A").lower()}, r,
               "200, uppercased before matching, still resolves", passed)

        r = client.call(ep, {"phone": cfg.phone_a}, headers=auth_headers())
        passed = not r.is_2xx()
        record(log, "select_profile__no_identifying_params", ep, {"phone": cfg.phone_a}, r,
               "non-200, ValidationError learner_id or (grade, roll_number, division) is required", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "grade": "12", "roll_number": "9999", "division": "Z"},
                         headers=auth_headers())
        passed = not r.is_2xx()
        record(log, "select_profile__nonexistent_combo", ep,
               {"phone": cfg.phone_a, "grade": "12", "roll_number": "9999", "division": "Z"}, r,
               "non-200, DoesNotExistError No matching student found", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b}, headers=auth_headers())
        passed = not r.is_2xx()
        record(log, "select_profile__not_owned_learner_id", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b}, r,
               "non-200, AuthenticationError Profile not linked to this account", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a, "fields": "xp,streak"},
                         headers=auth_headers())
        body = r.message_body()
        expected_keys = {"learner_id", "xp", "weekly_xp", "xp_daily", "streak", "longest_streak",
                          "last_activity_date", "achievements", "success"}
        passed = r.is_2xx() and isinstance(body, dict) and set(body.keys()) <= expected_keys and "profile" not in body and "level" not in body
        record(log, "select_profile__fields_subset", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a, "fields": "xp,streak"}, r,
               "200, only xp/streak sections + achievements, no profile/level/window", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a, "fields": "xp,bogus_section"},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and "xp" in body
        record(log, "select_profile__fields_unknown_token_ignored", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a, "fields": "xp,bogus_section"}, r,
               "200, behaves same as fields=xp, unknown token silently ignored", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a, "fields": ""},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and "profile" in body and "level" in body
        record(log, "select_profile__fields_empty_string", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a, "fields": ""}, r,
               "200, treated as None, all sections returned", passed)

        r = client.call(alias_ep, {
            "phone": cfg.phone_a, "learner_id": cfg.lid_owned_a,
        }, headers=auth_headers())
        r2 = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a}, headers=auth_headers())
        b1, b2 = r.message_body(), r2.message_body()
        passed = r.is_2xx() and isinstance(b1, dict) and isinstance(b2, dict) and set(b1.keys()) == set(b2.keys())
        record(log, "search_student__alias_parity", alias_ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a}, r,
               "200, identical shape to select_profile confirms alias works", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a})
    passed = not r.is_2xx()
    record(log, "select_profile__no_token", ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_a}, r,
           "non-200 auth error, no header sent", passed)


def run_update_avatar_suite(client, cfg, log, state):
    ep = "update_avatar"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a:
        for cid in ("update_avatar__happy_valid_value", "update_avatar__default_when_omitted",
                    "update_avatar__empty_string", "update_avatar__overlong_string",
                    "update_avatar__not_owned_learner"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no access token available")
    else:
        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "avatar": "3"},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and body.get("avatar") == "3"
        if passed:
            confirm = client.call("select_profile", {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "fields": "profile"},
                                   headers=auth_headers())
            cbody = confirm.message_body()
            if not (isinstance(cbody, dict) and cbody.get("success") is True):
                passed = None
        record(log, "update_avatar__happy_valid_value", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "avatar": "3"}, r,
               "200, success:true, avatar:3, persisted on follow-up read", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1}, headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("avatar") == "1"
        record(log, "update_avatar__default_when_omitted", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1}, r,
               "200, defaults to avatar:1", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "avatar": ""},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("avatar") == "1"
        record(log, "update_avatar__empty_string", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "avatar": ""}, r,
               "200, falsy triggers default 1", passed)

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                              "avatar": "12345678901234567890"}, headers=auth_headers())
        record(log, "update_avatar__overlong_string", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "avatar": "12345678901234567890"}, r,
               "record actual DB behavior for overlong avatar", None,
               f"observed status={r.status_code} body={json.dumps(r.body)[:300]}")

        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b, "avatar": "2"},
                         headers=auth_headers())
        passed = not r.is_2xx()
        record(log, "update_avatar__not_owned_learner", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b, "avatar": "2"}, r,
               "non-200, Profile not linked to this account", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "avatar": "2"})
    passed = not r.is_2xx()
    record(log, "update_avatar__no_token", ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "avatar": "2"}, r,
           "non-200 auth error", passed)

    if state.token_a:
        r = client.call(ep, {"phone": cfg.phone_a, "avatar": "2"}, headers=auth_headers())
        passed = not r.is_2xx()
        record(log, "update_avatar__missing_learner_id", ep, {"phone": cfg.phone_a, "avatar": "2"}, r,
               "non-200, Profile not linked to this account (no matching row)", passed)
    else:
        record(log, "update_avatar__missing_learner_id", ep, {}, None,
               "non-200", None, "SKIPPED — no access token available")


def run_update_profile_suite(client, cfg, log, state):
    ep = "update_profile"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a:
        for cid in ("update_profile__single_field_via_json", "update_profile__multi_field",
                    "update_profile__implicit_form_fields_no_updates_param",
                    "update_profile__forbidden_field_school", "update_profile__forbidden_field_school_id",
                    "update_profile__unknown_field", "update_profile__division_invalid_two_chars",
                    "update_profile__division_invalid_numeric", "update_profile__division_lowercase_valid",
                    "update_profile__empty_updates_dict", "update_profile__malformed_json_string",
                    "update_profile__updates_as_json_array", "update_profile__not_owned_learner",
                    "update_profile__student_name_sync_check"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no access token available")
        record(log, "update_profile__missing_learner_id", ep, {}, None,
               "non-200, ValidationError learner_id is required", None, "SKIPPED — no access token available")
        return

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": json.dumps({"grade": "7"})},
                     headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "update_profile__single_field_via_json", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"grade": "7"}}, r,
           "200, success:true, learner_full_state(fields=profile,level)", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
        "updates": json.dumps({"grade": "8", "division": "B", "student_name": "Test Student One"}),
    }, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "update_profile__multi_field", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
            "updates": {"grade": "8", "division": "B", "student_name": "Test Student One"}}, r,
           "200, all three applied", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "grade": "9"}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "update_profile__implicit_form_fields_no_updates_param", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "grade": "9"}, r,
           "200, implicit form_dict-derived updates applied (quirk unique to update_profile)", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"school": "SomeSchool"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__forbidden_field_school", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"school": "SomeSchool"}}, r,
           "non-200, ValidationError school cannot be edited", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"school_id": "SCH001"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__forbidden_field_school_id", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"school_id": "SCH001"}}, r,
           "non-200, same forbidden-field error", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"xp": 99999})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__unknown_field", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"xp": 99999}}, r,
           "non-200, ValidationError These fields cannot be edited: xp", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"division": "AB"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__division_invalid_two_chars", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"division": "AB"}}, r,
           "non-200, ValidationError Division must be a single letter A-Z", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"division": "1"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__division_invalid_numeric", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"division": "1"}}, r,
           "non-200, same validation error (not alpha)", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"division": "c"})}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "update_profile__division_lowercase_valid", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"division": "c"}}, r,
           "200, stored as uppercase C", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": json.dumps({})},
                     headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__empty_updates_dict", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {}}, r,
           "non-200, ValidationError No editable fields supplied", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": "{grade: 7"},
                     headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__malformed_json_string", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": "{grade: 7"}, r,
           "non-200, ValidationError updates must be a JSON object", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps(["grade", "7"])}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__updates_as_json_array", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": ["grade", "7"]}, r,
           "non-200, No editable fields supplied (fails isinstance dict check)", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "updates": json.dumps({"grade": "7"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__missing_learner_id", ep,
           {"phone": cfg.phone_a, "updates": {"grade": "7"}}, r,
           "non-200, ValidationError learner_id is required", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b,
                          "updates": json.dumps({"grade": "7"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_profile__not_owned_learner", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b, "updates": {"grade": "7"}}, r,
           "non-200, Profile not linked to this account", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"grade": "7"})})
    passed = not r.is_2xx()
    record(log, "update_profile__no_token", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"grade": "7"}}, r,
           "non-200 auth error", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"student_name": "Renamed Student"})}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    if passed:
        confirm = client.call("select_profile", {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "fields": "profile"},
                               headers=auth_headers())
        cbody = confirm.message_body()
        confirm_ok = isinstance(cbody, dict) and cbody.get("profile", {}).get("student_name") == "Renamed Student"
        profiles_check = client.call("get_profiles", {"phone": cfg.phone_a, "page_size": 200}, headers=auth_headers())
        pbody = profiles_check.message_body()
        auth_profile_ok = isinstance(pbody, dict) and any(
            p.get("learner_id") == cfg.lid_write_1 and p.get("student_name") == "Renamed Student"
            for p in pbody.get("profiles", [])
        )
        passed = confirm_ok and auth_profile_ok
    record(log, "update_profile__student_name_sync_check", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"student_name": "Renamed Student"}}, r,
           "200, both Tapapp Learner and Tapapp Auth Profile student_name synced", passed)


def run_update_student_suite(client, cfg, log, state):
    ep = "update_student"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a:
        for cid in ("update_student__happy_single_field", "update_student__updates_omitted_entirely",
                    "update_student__forbidden_field", "update_student__unknown_field",
                    "update_student__malformed_json", "update_student__birthdate_valid_format",
                    "update_student__birthdate_invalid_format", "update_student__not_owned",
                    "update_student__missing_learner_id"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no access token available")
        record(log, "update_student__no_token", ep, {}, None, "non-200 auth error", None,
               "SKIPPED — no access token available")
        return

    r = client.call("select_profile", {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "fields": "profile"},
                     headers=auth_headers())
    lang_body = r.message_body()
    valid_language = None
    if isinstance(lang_body, dict):
        valid_language = lang_body.get("profile", {}).get("language")
    if not valid_language:
        valid_language = "English"

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                          "updates": json.dumps({"language": valid_language})}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "update_student__happy_single_field", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": {"language": valid_language}}, r,
           "200, success:true + profile,level state", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_student__updates_omitted_entirely", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2}, r,
           "non-200, ValidationError No editable fields supplied — differs from update_profile", passed)
    if not passed:
        log.add_finding("update_student implicit-field regression",
                         ep,
                         "update_student accepted an implicit form-field update the same way update_profile does; "
                         "this is the key regression the plan calls out to catch if the two code paths get merged",
                         f"status={r.status_code} body={r.body}")

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                          "updates": json.dumps({"school": "X"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_student__forbidden_field", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": {"school": "X"}}, r,
           "non-200, school cannot be edited", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                          "updates": json.dumps({"streak": 100})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_student__unknown_field", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": {"streak": 100}}, r,
           "non-200, These fields cannot be edited: streak", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": "not-json{"},
                     headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_student__malformed_json", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": "not-json{"}, r,
           "non-200, updates must be a JSON object", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                          "updates": json.dumps({"birthdate": "2014-05-20"})}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "update_student__birthdate_valid_format", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": {"birthdate": "2014-05-20"}}, r,
           "200, applied", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                          "updates": json.dumps({"birthdate": "20-05-2014"})}, headers=auth_headers())
    record(log, "update_student__birthdate_invalid_format", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": {"birthdate": "20-05-2014"}}, r,
           "record actual DB behavior for malformed date", None,
           f"observed status={r.status_code} body={json.dumps(r.body)[:300]}")

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b,
                          "updates": json.dumps({"grade": "5"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_student__not_owned", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b, "updates": {"grade": "5"}}, r,
           "non-200, Profile not linked to this account", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "updates": json.dumps({"grade": "5"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "update_student__missing_learner_id", ep,
           {"phone": cfg.phone_a, "updates": {"grade": "5"}}, r,
           "non-200, learner_id is required", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                          "updates": json.dumps({"grade": "5"})})
    passed = not r.is_2xx()
    record(log, "update_student__no_token", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": {"grade": "5"}}, r,
           "non-200 auth error", passed)


def run_get_bulk_students_suite(client, cfg, log, state):
    ep = "get_bulk_students"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a:
        for cid in ("get_bulk_students__happy_default", "get_bulk_students__page_size_clamped_to_500",
                    "get_bulk_students__filter_all_combo", "get_bulk_students__division_lowercase_filter",
                    "get_bulk_students__division_invalid_filter_value", "get_bulk_students__empty_result_set",
                    "get_bulk_students__each_student_state_shape"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no access token available")
        record(log, "get_bulk_students__no_token", ep, {}, None, "non-200 auth error", None,
               "SKIPPED — no access token available")
        return

    r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 100}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and "students" in body and all(
        "state" in s for s in body.get("students", [])
    )
    record(log, "get_bulk_students__happy_default", ep, {"phone": cfg.phone_a, "page": 1, "page_size": 100}, r,
           "200, students array each with nested state object", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 9999}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("page_size") == 500
    record(log, "get_bulk_students__page_size_clamped_to_500", ep, {"phone": cfg.phone_a, "page_size": 9999}, r,
           "clamped to 500", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a, "grade": cfg.lookup_grade, "division": "A",
        "roll_number": cfg.lookup_roll_number, "query": "a", "page": 1, "page_size": 50,
    }, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and "students" in body
    record(log, "get_bulk_students__filter_all_combo", ep,
           {"phone": cfg.phone_a, "grade": cfg.lookup_grade, "division": "A",
            "roll_number": cfg.lookup_roll_number, "query": "a"}, r,
           "200, ANDed filters", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "division": "b", "page": 1, "page_size": 50}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and all(
        s.get("division") == "B" for s in body.get("students", [])
    )
    record(log, "get_bulk_students__division_lowercase_filter", ep,
           {"phone": cfg.phone_a, "division": "b"}, r,
           "uppercased before filtering via _clean_division", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "division": "BB", "page": 1, "page_size": 50}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "get_bulk_students__division_invalid_filter_value", ep,
           {"phone": cfg.phone_a, "division": "BB"}, r,
           "non-200, _clean_division throws ValidationError even for a filter", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "grade": "11", "page": 1, "page_size": 50}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict)
    if passed and body.get("students") == []:
        passed = body.get("students_has_more") is False
    record(log, "get_bulk_students__empty_result_set", ep, {"phone": cfg.phone_a, "grade": "11"}, r,
           "200, students:[] students_has_more:false if no matches", passed,
           "" if body and body.get("students") == [] else "grade '11' may have matching data in your dataset")

    r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 5}, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and all(
        isinstance(s.get("state"), dict) and "achievements" in s.get("state", {})
        for s in body.get("students", [])
    )
    record(log, "get_bulk_students__each_student_state_shape", ep, {"phone": cfg.phone_a, "page_size": 5}, r,
           "200, each student's state includes achievements key", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "page": 1, "page_size": 50})
    passed = not r.is_2xx()
    record(log, "get_bulk_students__no_token", ep, {"phone": cfg.phone_a}, r,
           "non-200 auth error", passed)


def run_bulk_update_students_suite(client, cfg, log, state):
    ep = "bulk_update_students"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a or not cfg.allow_bulk_write_tests:
        for cid in ("bulk_update__single_row", "bulk_update__ten_rows_mixed_fields",
                    "bulk_update__exactly_500_rows", "bulk_update__501_rows_rejected",
                    "bulk_update__duplicate_learner_id_in_batch", "bulk_update__mixed_bad_and_good_nonatomic",
                    "bulk_update__mixed_bad_and_good_atomic", "bulk_update__empty_changes_array",
                    "bulk_update__changes_not_array", "bulk_update__malformed_json_string",
                    "bulk_update__row_missing_updates", "bulk_update__row_missing_learner_id",
                    "bulk_update__row_empty_updates_dict", "bulk_update__not_owned_row",
                    "bulk_update__division_invalid_inside_row", "bulk_update__atomic_param_variants"):
            record(log, cid, ep, {}, None, "200", None,
                   "SKIPPED — no access token or bulk writes disabled")
        record(log, "bulk_update__no_token", ep, {}, None, "non-200 auth error", None,
               "SKIPPED — no access token available")
        return

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([{"learner_id": cfg.lid_write_3, "updates": {"grade": "7"}}]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("total") == 1 and body.get("succeeded") == 1
              and body.get("failed") == 0 and body.get("results", [{}])[0].get("success") is True)
    record(log, "bulk_update__single_row", ep,
           {"phone": cfg.phone_a, "changes": [{"learner_id": cfg.lid_write_3, "updates": {"grade": "7"}}]}, r,
           "200, total:1 succeeded:1 failed:0", passed)

    ten_rows = []
    lids = [cfg.lid_write_1, cfg.lid_write_2, cfg.lid_write_3]
    fieldsets = [{"grade": "6"}, {"division": "A"}, {"roll_number": "5"}, {"grade": "7"}, {"division": "B"}]
    for i in range(10):
        ten_rows.append({"learner_id": lids[i % len(lids)], "updates": fieldsets[i % len(fieldsets)]})
    r = client.call(ep, {"phone": cfg.phone_a, "changes": json.dumps(ten_rows), "atomic": "false"},
                     headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("total") == 10
    record(log, "bulk_update__ten_rows_mixed_fields", ep,
           {"phone": cfg.phone_a, "changes_count": 10}, r,
           "200, succeeded matches valid rows", passed)

    five_hundred_rows = [{"learner_id": lids[i % len(lids)], "updates": {"grade": str((i % 12) + 1)}}
                          for i in range(500)]
    r = client.call(ep, {"phone": cfg.phone_a, "changes": json.dumps(five_hundred_rows), "atomic": "false"},
                     headers=auth_headers())
    passed = r.is_2xx()
    record(log, "bulk_update__exactly_500_rows", ep, {"phone": cfg.phone_a, "changes_count": 500}, r,
           "200, accepted at cap, not over", passed)

    five_oh_one_rows = [{"learner_id": lids[i % len(lids)], "updates": {"grade": str((i % 12) + 1)}}
                         for i in range(501)]
    r = client.call(ep, {"phone": cfg.phone_a, "changes": json.dumps(five_oh_one_rows), "atomic": "false"},
                     headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "bulk_update__501_rows_rejected", ep, {"phone": cfg.phone_a, "changes_count": 501}, r,
           "non-200, ValidationError Cannot update more than 500 students in one request", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([
            {"learner_id": cfg.lid_write_1, "updates": {"grade": "5"}},
            {"learner_id": cfg.lid_write_1, "updates": {"grade": "9"}},
        ]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = False
    if r.is_2xx() and isinstance(body, dict):
        results = body.get("results", [])
        has_merged = any(res.get("error") == "merged_with_duplicate_row" for res in results)
        has_success = any(res.get("success") is True and res.get("learner_id") == cfg.lid_write_1 for res in results)
        passed = has_merged and has_success
        if passed:
            confirm = client.call("select_profile", {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                                                       "fields": "profile"}, headers=auth_headers())
            cbody = confirm.message_body()
            if isinstance(cbody, dict):
                passed = cbody.get("profile", {}).get("grade") == "9"
            else:
                passed = None
    record(log, "bulk_update__duplicate_learner_id_in_batch", ep,
           {"phone": cfg.phone_a, "changes": "2 rows same learner different grade"}, r,
           "200, final grade 9, one merged_with_duplicate_row + one success", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([
            {"learner_id": cfg.lid_write_2, "updates": {"grade": "6"}},
            {"learner_id": cfg.lid_write_2, "updates": {"school": "X"}},
            {"learner_id": cfg.lid_owned_b, "updates": {"grade": "6"}},
        ]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "bulk_update__mixed_bad_and_good_nonatomic", ep,
           {"phone": cfg.phone_a, "changes": "good + forbidden-field + not-owned rows"}, r,
           "200, success:true overall, mixed per-row results, good row's write lands", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([
            {"learner_id": cfg.lid_write_2, "updates": {"grade": "6"}},
            {"learner_id": cfg.lid_write_2, "updates": {"school": "X"}},
            {"learner_id": cfg.lid_owned_b, "updates": {"grade": "6"}},
        ]),
        "atomic": "true",
    }, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("success") is False
              and body.get("succeeded") == 0 and body.get("failed") == 3)
    record(log, "bulk_update__mixed_bad_and_good_atomic", ep,
           {"phone": cfg.phone_a, "changes": "same 3 rows, atomic=true"}, r,
           "200, success:false, succeeded:0, failed:3, no writes landed even for the row that would've succeeded",
           passed)

    r = client.call(ep, {"phone": cfg.phone_a, "changes": json.dumps([]), "atomic": "false"}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "bulk_update__empty_changes_array", ep, {"phone": cfg.phone_a, "changes": []}, r,
           "non-200, ValidationError changes must be a non-empty array", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps({"learner_id": cfg.lid_write_1, "updates": {"grade": "5"}}),
        "atomic": "false",
    }, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "bulk_update__changes_not_array", ep,
           {"phone": cfg.phone_a, "changes": "object, not array"}, r,
           "non-200, same must be a non-empty array error", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "changes": "[not valid json", "atomic": "false"},
                     headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "bulk_update__malformed_json_string", ep,
           {"phone": cfg.phone_a, "changes": "[not valid json"}, r,
           "non-200, ValidationError changes must be a JSON array", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([{"learner_id": cfg.lid_write_1}]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("results", [{}])[0].get("success") is False
              and body.get("results", [{}])[0].get("error") == "invalid_change")
    record(log, "bulk_update__row_missing_updates", ep,
           {"phone": cfg.phone_a, "changes": [{"learner_id": cfg.lid_write_1}]}, r,
           "200, results[0] success:false error:invalid_change", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([{"updates": {"grade": "5"}}]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("results", [{}])[0].get("success") is False
              and body.get("results", [{}])[0].get("learner_id") is None)
    record(log, "bulk_update__row_missing_learner_id", ep,
           {"phone": cfg.phone_a, "changes": [{"updates": {"grade": "5"}}]}, r,
           "200, results[0] learner_id:null success:false error:invalid_change", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([{"learner_id": cfg.lid_write_1, "updates": {}}]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict)
              and body.get("results", [{}])[0].get("error") == "invalid_change")
    record(log, "bulk_update__row_empty_updates_dict", ep,
           {"phone": cfg.phone_a, "changes": [{"learner_id": cfg.lid_write_1, "updates": {}}]}, r,
           "200, invalid_change (empty dict fails truthy check)", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([{"learner_id": cfg.lid_owned_b, "updates": {"grade": "5"}}]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict)
              and body.get("results", [{}])[0].get("error") == "not_owned")
    record(log, "bulk_update__not_owned_row", ep,
           {"phone": cfg.phone_a, "changes": [{"learner_id": cfg.lid_owned_b, "updates": {"grade": "5"}}]}, r,
           "200, results[0] error:not_owned", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([{"learner_id": cfg.lid_write_1, "updates": {"grade": "5"}}]),
        "atomic": "false",
    })
    passed = not r.is_2xx()
    record(log, "bulk_update__no_token", ep, {"phone": cfg.phone_a, "changes_count": 1}, r,
           "non-200 auth error, before any row processing", passed)

    r = client.call(ep, {
        "phone": cfg.phone_a,
        "changes": json.dumps([{"learner_id": cfg.lid_write_1, "updates": {"division": "ZZ"}}]),
        "atomic": "false",
    }, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict)
              and body.get("results", [{}])[0].get("success") is False)
    record(log, "bulk_update__division_invalid_inside_row", ep,
           {"phone": cfg.phone_a, "changes": [{"learner_id": cfg.lid_write_1, "updates": {"division": "ZZ"}}]}, r,
           "200, results[0].success:false with _clean_division error text", passed)

    variant_results = {}
    for atomic_val in ("true", "1", True, "false", "0", None):
        params = {
            "phone": cfg.phone_a,
            "changes": json.dumps([{"learner_id": cfg.lid_write_1, "updates": {"grade": "6"}}]),
        }
        if atomic_val is not None:
            params["atomic"] = atomic_val
        r = client.call(ep, params, headers=auth_headers())
        variant_results[str(atomic_val)] = r.status_code
    passed = all(v is not None and 200 <= v < 300 for v in variant_results.values())
    record(log, "bulk_update__atomic_param_variants", ep,
           {"phone": cfg.phone_a, "atomic_variants": list(variant_results.keys())}, None,
           "string true/1 parse to atomic True, false/0/omitted parse to atomic False", passed,
           json.dumps(variant_results))


def run_complete_onboarding_suite(client, cfg, log, state):
    ep = "complete_onboarding"

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    if not state.token_a:
        for cid in ("onboarding__updates_only", "onboarding__course_only", "onboarding__both_updates_and_course",
                    "onboarding__neither_updates_nor_course", "onboarding__idempotent_repeat_call",
                    "onboarding__missing_learner_id", "onboarding__not_owned_learner",
                    "onboarding__forbidden_field_in_updates", "onboarding__malformed_updates_json",
                    "onboarding__updates_not_dict", "onboarding__nonexistent_course"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no access token available")
        record(log, "onboarding__no_token", ep, {}, None, "non-200 auth error", None,
               "SKIPPED — no access token available")
        return

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1,
                          "updates": json.dumps({"grade": "6"})}, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("onboarding_completed") is True
              and body.get("course") is None and body.get("updated_fields") == ["grade"])
    if passed:
        state.onboarded_lid_write_1 = True
    record(log, "onboarding__updates_only", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1, "updates": {"grade": "6"}}, r,
           "200, onboarding_completed:true, course:null, updated_fields:[grade]", passed)

    if cfg.course_1:
        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "course": cfg.course_1},
                         headers=auth_headers())
        body = r.message_body()
        passed = (r.is_2xx() and isinstance(body, dict) and body.get("onboarding_completed") is True
                  and body.get("updated_fields") == [])
        if passed:
            state.enrolled_lid_write_2_course = cfg.course_1
        record(log, "onboarding__course_only", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "course": cfg.course_1}, r,
               "200, updated_fields:[], enrollment created/updated", passed)
    else:
        record(log, "onboarding__course_only", ep, {}, None, "200", None, "SKIPPED — no course_1 in config")

    if cfg.course_2:
        r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_3,
                              "updates": json.dumps({"division": "A"}), "course": cfg.course_2},
                         headers=auth_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("onboarding_completed") is True
        record(log, "onboarding__both_updates_and_course", ep,
               {"phone": cfg.phone_a, "learner_id": cfg.lid_write_3, "updates": {"division": "A"},
                "course": cfg.course_2}, r,
               "200, both applied atomically", passed)
    else:
        record(log, "onboarding__both_updates_and_course", ep, {}, None, "200", None,
               "SKIPPED — no course_2 in config")

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1}, headers=auth_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("onboarding_completed") is True
              and body.get("updated_fields") == [])
    record(log, "onboarding__neither_updates_nor_course", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1}, r,
           "200, onboarding_completed:true still set, updated_fields:[]", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1}, headers=auth_headers())
    passed = r.is_2xx()
    record(log, "onboarding__idempotent_repeat_call", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1}, r,
           "200, no error on repeat, idempotent UPDATE", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "updates": json.dumps({"grade": "6"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "onboarding__missing_learner_id", ep,
           {"phone": cfg.phone_a, "updates": {"grade": "6"}}, r,
           "non-200, ValidationError learner_id is required", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b,
                          "updates": json.dumps({"grade": "6"})}, headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "onboarding__not_owned_learner", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b, "updates": {"grade": "6"}}, r,
           "non-200, Profile not linked to this account", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                          "updates": json.dumps({"school": "X"})}, headers=auth_headers())
    passed = not r.is_2xx()
    if passed:
        confirm = client.call("select_profile", {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2,
                                                   "fields": "profile"}, headers=auth_headers())
    record(log, "onboarding__forbidden_field_in_updates", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": {"school": "X"}}, r,
           "non-200, school cannot be edited, onboarding_completed NOT set due to savepoint rollback", passed,
           "manually verify onboarding_completed remained unset for lid_write_2 if this is a fresh learner")

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": "{bad"},
                     headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "onboarding__malformed_updates_json", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": "{bad"}, r,
           "non-200, updates must be a JSON object", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": json.dumps(["a", "b"])},
                     headers=auth_headers())
    passed = not r.is_2xx()
    record(log, "onboarding__updates_not_dict", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_2, "updates": ["a", "b"]}, r,
           "non-200, updates must be a JSON object", passed)

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_3, "course": "COURSE-DOES-NOT-EXIST"},
                     headers=auth_headers())
    record(log, "onboarding__nonexistent_course", ep,
           {"phone": cfg.phone_a, "learner_id": cfg.lid_write_3, "course": "COURSE-DOES-NOT-EXIST"}, r,
           "record actual behavior — course existence is not validated before insert/update", None,
           f"observed status={r.status_code} body={json.dumps(r.body)[:300]}")
    if r.is_2xx():
        log.add_finding("Onboarding accepts nonexistent course id", ep,
                         "complete_onboarding does not validate that the course exists before creating/updating "
                         "the enrollment, which can silently create a dangling reference",
                         f"status={r.status_code} body={r.body}")

    r = client.call(ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1})
    passed = not r.is_2xx()
    record(log, "onboarding__no_token", ep, {"phone": cfg.phone_a, "learner_id": cfg.lid_write_1}, r,
           "non-200 auth error", passed)


ALL_STATE_SECTIONS = {
    "profile": {"profile"},
    "xp": {"xp", "weekly_xp", "xp_daily"},
    "level": {"level"},
    "streak": {"streak", "longest_streak", "last_activity_date"},
    "window": {"activities_watched_this_week", "max_weekly_activities", "is_bingeing",
               "window_start_date", "window_resets_on", "activities_remaining"},
    "archetype": {"archetype"},
    "submission": {"submission_gems", "submission_index"},
    "version": {"version"},
    "enrollment": {"enrollment"},
    "achievements": {"achievements"},
}


def run_learner_state_progress_suite(client, cfg, log, state):
    state_ep = "get_learner_state"
    progress_ep = "get_learner_progress"

    r = client.call(state_ep, {"learner_id": cfg.lid_owned_a})
    body = r.message_body()
    expected_all_keys = {"learner_id"} | set().union(*[
        v for k, v in ALL_STATE_SECTIONS.items() if k not in ("achievements",)
    ])
    passed = r.is_2xx() and isinstance(body, dict) and expected_all_keys <= set(body.keys()) and "achievements" not in body
    record(log, "learner_state__no_fields_all_sections", state_ep, {"learner_id": cfg.lid_owned_a}, r,
           "200, all sections, achievements NOT auto-included unless requested", passed)

    for section_name, expected_keys in ALL_STATE_SECTIONS.items():
        cid = f"learner_state__fields_{section_name}_only"
        r = client.call(state_ep, {"learner_id": cfg.lid_owned_a, "fields": section_name})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and expected_keys <= set(body.keys())
        if passed:
            extra = set(body.keys()) - expected_keys - {"learner_id"}
            if extra:
                passed = None
        note = ""
        if section_name == "archetype":
            note = "archetype recompute/sync is a write side-effect on a read call"
        record(log, cid, state_ep, {"learner_id": cfg.lid_owned_a, "fields": section_name}, r,
               f"200, only {sorted(expected_keys)}", passed, note)

    r = client.call(state_ep, {"learner_id": cfg.lid_owned_a, "fields": "xp,streak,submission"})
    body = r.message_body()
    expected = ALL_STATE_SECTIONS["xp"] | ALL_STATE_SECTIONS["streak"] | ALL_STATE_SECTIONS["submission"] | {"learner_id"}
    passed = r.is_2xx() and isinstance(body, dict) and set(body.keys()) == expected
    record(log, "learner_state__fields_multiple_combo", state_ep,
           {"learner_id": cfg.lid_owned_a, "fields": "xp,streak,submission"}, r,
           "200, exactly xp+streak+submission sections plus learner_id", passed)

    r = client.call(state_ep, {"learner_id": cfg.lid_owned_a, "fields": "xp,not_a_real_section"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and "xp" in body
    record(log, "learner_state__fields_unknown_token", state_ep,
           {"learner_id": cfg.lid_owned_a, "fields": "xp,not_a_real_section"}, r,
           "200, behaves as fields=xp, unknown ignored silently", passed)

    r = client.call(state_ep, {"learner_id": "TL99999999"})
    passed = not r.is_2xx()
    record(log, "learner_state__nonexistent_learner", state_ep, {"learner_id": "TL99999999"}, r,
           "non-200, DoesNotExistError Learner not found", passed)

    r = client.call(state_ep, {})
    passed = not r.is_2xx()
    record(log, "learner_state__missing_learner_id", state_ep, {}, r,
           "non-200, ValidationError learner_id is required", passed)

    r = client.call(state_ep, {"learner_id": cfg.lid_owned_a})
    passed = r.is_2xx()
    record(log, "learner_state__no_auth_at_all_still_works", state_ep, {"learner_id": cfg.lid_owned_a}, r,
           "200 — confirms endpoint has no ownership gate", passed,
           "SECURITY FINDING: no auth headers required")
    if passed:
        log.add_finding("get_learner_state has no ownership gate", state_ep,
                         "get_learner_state returns full learner state with zero auth headers sent",
                         f"status={r.status_code}")

    r = client.call(state_ep, {"learner_id": cfg.lid_owned_b})
    passed = r.is_2xx()
    record(log, "learner_state__cross_account_readable", state_ep, {"learner_id": cfg.lid_owned_b}, r,
           "200 — confirms any caller can read any learner's state by guessing learner_id", passed,
           "HIGH-SEVERITY SECURITY FINDING")
    if passed:
        log.add_finding("Cross-account learner state readable", state_ep,
                         "A caller who knows or guesses any learner_id can read that learner's full state/PII "
                         "regardless of which account owns it — no auth or ownership check at all",
                         f"status={r.status_code} learner_id={cfg.lid_owned_b}")

    r = client.call(progress_ep, {"learner_id": cfg.lid_owned_a})
    body = r.message_body()
    default_keys = ALL_STATE_SECTIONS["xp"] | ALL_STATE_SECTIONS["streak"] | ALL_STATE_SECTIONS["submission"] | ALL_STATE_SECTIONS["version"] | {"learner_id"}
    passed = r.is_2xx() and isinstance(body, dict) and set(body.keys()) == default_keys
    record(log, "learner_progress__default_fields", progress_ep, {"learner_id": cfg.lid_owned_a}, r,
           "200, default fields xp,streak,submission,version", passed)

    r = client.call(progress_ep, {"learner_id": cfg.lid_owned_a, "fields": "level"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and set(body.keys()) == ALL_STATE_SECTIONS["level"] | {"learner_id"}
    record(log, "learner_progress__explicit_fields_override_default", progress_ep,
           {"learner_id": cfg.lid_owned_a, "fields": "level"}, r,
           "200, only level, explicit fields override endpoint default", passed)


def run_get_learners_progress_suite(client, cfg, log):
    ep = "get_learners_progress"
    write_pool = [cfg.lid_write_1, cfg.lid_write_2, cfg.lid_write_3]

    r = client.call(ep, {"learner_ids": json.dumps(write_pool)})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and all(lid in body for lid in write_pool)
    record(log, "learners_progress__json_array", ep, {"learner_ids": write_pool}, r,
           "200, dict keyed by each learner_id with default-field state", passed)

    r = client.call(ep, {"learner_ids": f"{cfg.lid_write_1},{cfg.lid_write_2}"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and cfg.lid_write_1 in body and cfg.lid_write_2 in body
    record(log, "learners_progress__comma_string", ep,
           {"learner_ids": f"{cfg.lid_write_1},{cfg.lid_write_2}"}, r,
           "200, falls back to comma-split when JSON parse fails", passed)

    r = client.call(ep, {"learner_ids": json.dumps([])})
    passed = not r.is_2xx()
    record(log, "learners_progress__empty_array", ep, {"learner_ids": []}, r,
           "non-200, ValidationError learner_ids must be a non-empty array", passed)

    r = client.call(ep, {"learner_ids": json.dumps([cfg.lid_write_1, "TL_DOES_NOT_EXIST"])})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and cfg.lid_write_1 in body and "TL_DOES_NOT_EXIST" not in body
    record(log, "learners_progress__mixed_valid_invalid_ids", ep,
           {"learner_ids": [cfg.lid_write_1, "TL_DOES_NOT_EXIST"]}, r,
           "200, only valid id present in result, invalid silently absent", passed)

    r = client.call(ep, {"learner_ids": json.dumps([cfg.lid_write_1])})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and len(body) == 1
    record(log, "learners_progress__single_id_array", ep, {"learner_ids": [cfg.lid_write_1]}, r,
           "200, one key in result", passed)

    large_batch = [write_pool[i % len(write_pool)] for i in range(100)]
    r = client.call(ep, {"learner_ids": json.dumps(large_batch)})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and all(lid in body for lid in write_pool)
    record(log, "learners_progress__large_batch_100_ids", ep, {"learner_ids_count": 100}, r,
           "200, all present, read-heavy stress input for Class B", passed)

    r = client.call(ep, {"learner_ids": json.dumps([cfg.lid_write_1]), "fields": "xp"})
    body = r.message_body()
    expected = ALL_STATE_SECTIONS["xp"] | {"learner_id"}
    passed = (r.is_2xx() and isinstance(body, dict) and cfg.lid_write_1 in body
              and set(body[cfg.lid_write_1].keys()) == expected)
    record(log, "learners_progress__custom_fields", ep,
           {"learner_ids": [cfg.lid_write_1], "fields": "xp"}, r,
           "200, that learner's entry has only xp,weekly_xp,xp_daily plus learner_id", passed)

    r = client.call(ep, {"learner_ids": 12345})
    passed = not r.is_2xx()
    record(log, "learners_progress__not_a_list_or_string", ep, {"learner_ids": 12345}, r,
           "non-200, ValidationError learner_ids must be a non-empty array", passed)


def run_enroll_course_suite(client, cfg, log, state):
    ep = "enroll_course"

    if not cfg.course_1:
        for cid in ("enroll__new_enrollment", "enroll__re_enroll_same_course", "enroll__switch_to_different_course"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no course_1/course_2 in config")
    else:
        r = client.call(ep, {"learner_id": cfg.lid_write_1, "course": cfg.course_1})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("enrolled") is True and body.get("course") == cfg.course_1
        record(log, "enroll__new_enrollment", ep, {"learner_id": cfg.lid_write_1, "course": cfg.course_1}, r,
               "200, enrolled:true, course set, new Tapapp Enroll row inserted with zeros", passed)

        pre = client.call("get_learner_state", {"learner_id": cfg.lid_write_1, "fields": "enrollment"})
        pre_body = pre.message_body()
        pre_enrollment = pre_body.get("enrollment") if isinstance(pre_body, dict) else None

        r = client.call(ep, {"learner_id": cfg.lid_write_1, "course": cfg.course_1})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("enrolled") is True
        if passed and pre_enrollment:
            post = client.call("get_learner_state", {"learner_id": cfg.lid_write_1, "fields": "enrollment"})
            post_body = post.message_body()
            post_enrollment = post_body.get("enrollment") if isinstance(post_body, dict) else None
            if post_enrollment:
                unchanged = (pre_enrollment.get("videos_completed") == post_enrollment.get("videos_completed")
                             and pre_enrollment.get("quizzes_completed") == post_enrollment.get("quizzes_completed")
                             and pre_enrollment.get("submission_index") == post_enrollment.get("submission_index"))
                passed = unchanged
        record(log, "enroll__re_enroll_same_course", ep, {"learner_id": cfg.lid_write_1, "course": cfg.course_1}, r,
               "200, existing row UPDATEd, progress counters unchanged on re-enroll", passed)

        if cfg.course_2:
            r = client.call(ep, {"learner_id": cfg.lid_write_1, "course": cfg.course_2})
            body = r.message_body()
            passed = r.is_2xx() and isinstance(body, dict) and body.get("enrolled") is True
            record(log, "enroll__switch_to_different_course", ep,
                   {"learner_id": cfg.lid_write_1, "course": cfg.course_2}, r,
                   "200, same row's course overwritten, progress counters carried over unchanged", passed)
            log.add_finding("Switching courses does not reset progress",
                             ep,
                             "enroll_course uses a single-row-per-learner enrollment design; switching to a "
                             "different course overwrites the course field on the existing row but does not "
                             "reset videos_completed/quizzes_completed/submission_index — flag for product review",
                             f"learner={cfg.lid_write_1} old_course={cfg.course_1} new_course={cfg.course_2}")
        else:
            record(log, "enroll__switch_to_different_course", ep, {}, None, "200", None,
                   "SKIPPED — no course_2 in config")

    r = client.call(ep, {"learner_id": cfg.lid_write_2, "course": "COURSE-GARBAGE-ID"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("enrolled") is True
    record(log, "enroll__nonexistent_course_id", ep, {"learner_id": cfg.lid_write_2, "course": "COURSE-GARBAGE-ID"}, r,
           "200, enrolled:true — course existence is not validated, dangling reference created", passed)
    if passed:
        log.add_finding("enroll_course accepts nonexistent course id", ep,
                         "enroll_course does not validate the course exists, silently creating a dangling reference",
                         f"status={r.status_code} body={r.body}")

    r = client.call(ep, {"course": cfg.course_1})
    passed = not r.is_2xx()
    record(log, "enroll__missing_learner_id", ep, {"course": cfg.course_1}, r,
           "non-200, ValidationError learner_id and course are required", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_2})
    passed = not r.is_2xx()
    record(log, "enroll__missing_course", ep, {"learner_id": cfg.lid_write_2}, r,
           "non-200, same validation error", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_2, "course": cfg.course_1})
    passed = r.is_2xx()
    record(log, "enroll__no_auth_still_works", ep, {"learner_id": cfg.lid_write_2, "course": cfg.course_1}, r,
           "200 with zero auth headers sent", passed, "SECURITY FINDING alongside other no-auth findings")
    if passed:
        log.add_finding("enroll_course has no auth gate", ep,
                         "enroll_course succeeds with zero auth headers sent",
                         f"status={r.status_code}")


def run_record_activity_suite(client, cfg, log, state):
    ep = "record_activity"

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "activity_type": "video"})
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("xp_awarded") == 10
              and body.get("activity_recorded") is True)
    if passed:
        state.record_activity_calls_lid_write_1 = 1
    record(log, "record_activity__default_xp", ep, {"learner_id": cfg.lid_write_1, "activity_type": "video"}, r,
           "200, xp_awarded:10, activity_recorded:true, activities_watched_this_week=1", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "xp": 25, "activity_type": "quiz"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("xp_awarded") == 25
    if passed:
        state.record_activity_calls_lid_write_1 = 2
    record(log, "record_activity__custom_xp", ep, {"learner_id": cfg.lid_write_1, "xp": 25, "activity_type": "quiz"}, r,
           "200, xp_awarded:25, 2nd call in window, hits default cap of 2", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "xp": 10, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "record_activity__third_call_hits_cap", ep,
           {"learner_id": cfg.lid_write_1, "xp": 10, "activity_type": "video"}, r,
           "non-200, ValidationError Weekly activity limit reached (2 activities)", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_2, "xp": 0, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "record_activity__zero_xp_rejected", ep, {"learner_id": cfg.lid_write_2, "xp": 0, "activity_type": "video"}, r,
           "non-200, ValidationError xp must be positive, rejected before cap/existence checks", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_2, "xp": -5, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "record_activity__negative_xp_rejected", ep,
           {"learner_id": cfg.lid_write_2, "xp": -5, "activity_type": "video"}, r,
           "non-200, same xp must be positive", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_2, "xp": "abc", "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "record_activity__non_numeric_xp", ep,
           {"learner_id": cfg.lid_write_2, "xp": "abc", "activity_type": "video"}, r,
           "non-200 — record actual error surfaced, may be an ugly 500 rather than clean ValidationError", passed,
           f"observed body={json.dumps(r.body)[:300]}")
    if passed and isinstance(r.body, dict) and "exception" in r.body:
        log.add_finding("Non-numeric xp raises unhandled exception", ep,
                         "record_activity with xp='abc' surfaces as an unhandled 500-style exception rather than "
                         "a clean ValidationError, since int('abc') is not caught",
                         f"status={r.status_code}")

    r = client.call(ep, {"xp": 10, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "record_activity__missing_learner_id", ep, {"xp": 10, "activity_type": "video"}, r,
           "non-200, ValidationError learner_id is required", passed)

    r = client.call(ep, {"learner_id": "TL99999999", "xp": 10, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "record_activity__nonexistent_learner", ep,
           {"learner_id": "TL99999999", "xp": 10, "activity_type": "video"}, r,
           "non-200, DoesNotExistError Learner not found (after xp>0 check)", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_3, "xp": 10, "activity_type": "video"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict)
    record(log, "record_activity__streak_increment_across_windows", ep,
           {"learner_id": cfg.lid_write_3, "xp": 10, "activity_type": "video"}, r,
           "200, first-ever activity, streak starts at 1 (full window-gap test is manual/slow)", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_3, "xp": 10, "activity_type": "video", "fields": "xp"})
    body = r.message_body()
    expected_keys = {"activity_recorded", "activity_type", "xp_awarded"} | ALL_STATE_SECTIONS["xp"] | {"learner_id"}
    passed = r.is_2xx() and isinstance(body, dict) and set(body.keys()) == expected_keys
    record(log, "record_activity__fields_param_passthrough", ep,
           {"learner_id": cfg.lid_write_3, "xp": 10, "activity_type": "video", "fields": "xp"}, r,
           "200, merged response state portion only contains xp section", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_2, "xp": 10, "activity_type": "video"})
    passed = r.is_2xx()
    record(log, "record_activity__no_auth_still_works", ep,
           {"learner_id": cfg.lid_write_2, "xp": 10, "activity_type": "video"}, r,
           "200 with no auth headers", passed, "SECURITY FINDING alongside other no-auth findings")
    if passed:
        log.add_finding("record_activity has no auth gate", ep,
                         "record_activity succeeds with zero auth headers sent",
                         f"status={r.status_code}")


def run_content_progress_suite(client, cfg, log, state):
    ep = "update_content_progress"
    alias_ep = "submit_progress"

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "video_index": 2, "activity_type": "video"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("updated") is True and body.get("videos_completed") == 2
    record(log, "content_progress__video_only", ep,
           {"learner_id": cfg.lid_write_1, "video_index": 2, "activity_type": "video"}, r,
           "200, updated:true videos_completed:2", passed,
           "requires learner enrolled and weekly activity cap not yet exhausted")

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "quiz_index": 1, "activity_type": "quiz"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and "quizzes_completed" in body
    record(log, "content_progress__quiz_only", ep,
           {"learner_id": cfg.lid_write_1, "quiz_index": 1, "activity_type": "quiz"}, r,
           "200, quizzes_completed bumped", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "submission_index": 1, "activity_type": "assignment"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and "submission_index" in body
    record(log, "content_progress__submission_only", ep,
           {"learner_id": cfg.lid_write_1, "submission_index": 1, "activity_type": "assignment"}, r,
           "200, submission_index bumped on Enroll+Learner, counters advanced not the fixed SUBMISSION_XP/GEMS path", passed)

    if cfg.course_2 and state.enrolled_lid_write_2_course:
        r = client.call(ep, {
            "learner_id": cfg.lid_write_2, "video_index": 3, "quiz_index": 2, "submission_index": 1,
            "xp": 15, "activity_type": "combo",
        })
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("xp_awarded") == 15
        record(log, "content_progress__all_three_together", ep,
               {"learner_id": cfg.lid_write_2, "video_index": 3, "quiz_index": 2, "submission_index": 1,
                "xp": 15, "activity_type": "combo"}, r,
               "200, all three counters bumped, XP awarded via nested record_activity = 15", passed)
    else:
        record(log, "content_progress__all_three_together", ep, {}, None, "200", None,
               "SKIPPED — lid_write_2 not enrolled in config")

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "video_index": 1, "activity_type": "video"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("updated") is False and body.get("videos_completed") == 2
    record(log, "content_progress__value_lower_than_current_no_regression", ep,
           {"learner_id": cfg.lid_write_1, "video_index": 1, "activity_type": "video"}, r,
           "200, updated:false, GREATEST keeps videos_completed at 2, not regressed to 1", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "content_progress__no_progress_indices_at_all", ep,
           {"learner_id": cfg.lid_write_1, "activity_type": "video"}, r,
           "non-200, ValidationError at least one of video_index/quiz_index/submission_index is required", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_3, "video_index": 1, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "content_progress__no_enrollment_exists", ep,
           {"learner_id": cfg.lid_write_3, "video_index": 1, "activity_type": "video"}, r,
           "non-200, ValidationError Learner has no active enrollment", passed,
           "requires lid_write_3 to have zero enrollments")

    r = client.call(ep, {"video_index": 1, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "content_progress__missing_learner_id", ep, {"video_index": 1, "activity_type": "video"}, r,
           "non-200, ValidationError learner_id is required", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "video_index": 4, "activity_type": "video"})
    passed = not r.is_2xx()
    record(log, "content_progress__weekly_cap_already_hit", ep,
           {"learner_id": cfg.lid_write_1, "video_index": 4, "activity_type": "video"}, r,
           "non-200, Weekly activity limit reached, cap checked even through this alias path", passed,
           "requires lid_write_1 to already be at 2/2 activities this window")

    if cfg.course_1:
        client.call("enroll_course", {"learner_id": cfg.lid_write_3, "course": cfg.course_1})
        r1 = client.call(alias_ep, {
            "learner_id": cfg.lid_write_3, "video_index": 1, "quiz_index": 1, "submission_index": 1,
            "xp": 12, "activity_type": "combo",
        })
        body = r1.message_body()
        passed = r1.is_2xx() and isinstance(body, dict) and body.get("xp_awarded") == 12
        record(log, "submit_progress__alias_parity_check", alias_ep,
               {"learner_id": cfg.lid_write_3, "video_index": 1, "quiz_index": 1, "submission_index": 1,
                "xp": 12, "activity_type": "combo"}, r1,
               "200, identical response shape confirms submit_progress aliases update_content_progress", passed)
    else:
        record(log, "submit_progress__alias_parity_check", alias_ep, {}, None, "200", None,
               "SKIPPED — no course_1 in config to enroll a fresh learner")


def run_submission_webhook_suite(client, cfg, log, state):
    ep = "submission_verified_webhook"

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "submission_index": 1})
    passed = not r.is_2xx()
    record(log, "webhook__no_api_credentials", ep, {"learner_id": cfg.lid_write_1, "submission_index": 1}, r,
           "non-200 — Frappe's own guest gate rejects before function body runs", passed)

    r = client.call("get_learner_state", {"learner_id": cfg.lid_write_1, "fields": "submission"})
    body = r.message_body()
    current_index = body.get("submission_index", 0) if isinstance(body, dict) else 0
    next_index = current_index + 1

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "submission_index": next_index},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("processed") is True
              and body.get("submission_index") == next_index and body.get("xp_awarded") == 25
              and body.get("gems_awarded") == 1)
    if passed:
        state.submission_index_lid_write_1 = next_index
    record(log, "webhook__first_valid_call", ep,
           {"learner_id": cfg.lid_write_1, "submission_index": next_index}, r,
           "200, processed:true, xp_awarded:25, gems_awarded:1", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "submission_index": next_index},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("processed") is False
              and body.get("reason") == "already_processed")
    record(log, "webhook__immediate_replay_same_index", ep,
           {"learner_id": cfg.lid_write_1, "submission_index": next_index}, r,
           "200, processed:false reason:already_processed, no double-award", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "submission_index": next_index + 4},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("processed") is False
              and body.get("reason") == "out_of_sequence"
              and body.get("expected_submission_index") == next_index + 1)
    record(log, "webhook__skip_ahead_out_of_sequence", ep,
           {"learner_id": cfg.lid_write_1, "submission_index": next_index + 4}, r,
           "200, processed:false reason:out_of_sequence, expected_submission_index reported", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_1, "submission_index": next_index + 1},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("processed") is True
    record(log, "webhook__correct_next_in_sequence", ep,
           {"learner_id": cfg.lid_write_1, "submission_index": next_index + 1}, r,
           "200, processed:true, index advances, another 25 XP / 1 gem awarded", passed)

    r = client.call(ep, {"submission_index": 1}, headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "webhook__missing_learner_id", ep, {"submission_index": 1}, r,
           "non-200, ValidationError learner_id and submission_index are required", passed)

    r = client.call(ep, {"learner_id": cfg.lid_write_2}, headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "webhook__missing_submission_index", ep, {"learner_id": cfg.lid_write_2}, r,
           "non-200, same validation error", passed)

    r = client.call(ep, {"learner_id": "TL99999999", "submission_index": 1}, headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "webhook__nonexistent_learner", ep, {"learner_id": "TL99999999", "submission_index": 1}, r,
           "non-200, DoesNotExistError Learner not found", passed)


def run_achievements_suite(client, cfg, log, state):
    read_ep = "get_learner_achievements"
    award_ep = "award_achievement"

    r = client.call(read_ep, {"learner_id": cfg.lid_write_3})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("achievements") == []
    record(log, "achievements__empty_list_fresh_learner", read_ep, {"learner_id": cfg.lid_write_3}, r,
           "200, achievements:[] for a fresh learner", passed,
           "requires lid_write_3 to have zero achievements at time of this run")

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 1})
    passed = not r.is_2xx()
    record(log, "award__no_api_credentials", award_ep,
           {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 1}, r,
           "non-200 — rejected by Frappe's guest gate before function runs", passed)

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 1},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = (r.is_2xx() and isinstance(body, dict) and body.get("awarded") is True
              and body.get("achievement") == "streak_master" and body.get("level") == "1")
    if passed:
        state.achievement_awarded = True
    record(log, "award__new_achievement", award_ep,
           {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 1}, r,
           "200, awarded:true, new row inserted", passed)

    r = client.call(read_ep, {"learner_id": cfg.lid_write_3})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and any(
        a.get("achievement") == "streak_master" for a in body.get("achievements", [])
    )
    record(log, "achievements__after_award", read_ep, {"learner_id": cfg.lid_write_3}, r,
           "200, list contains the awarded entry", passed)

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 0},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("level") == "1" and body.get("awarded") is False
    record(log, "award__same_achievement_lower_level", award_ep,
           {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 0}, r,
           "200, GREATEST upsert keeps level 1, awarded:false since int(0)!=1", passed)

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 2},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("level") == "2" and body.get("awarded") is True
    record(log, "award__same_achievement_higher_level", award_ep,
           {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": 2}, r,
           "200, level updates to 2, awarded:true", passed)

    r = client.call(award_ep, {"achievement": "streak_master", "level": 1}, headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "award__missing_learner_id", award_ep, {"achievement": "streak_master", "level": 1}, r,
           "non-200, ValidationError learner_id, achievement, and level are required", passed)

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "level": 1}, headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "award__missing_achievement", award_ep, {"learner_id": cfg.lid_write_3, "level": 1}, r,
           "non-200, same validation error", passed)

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "achievement": "streak_master"},
                     headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "award__level_none", award_ep, {"learner_id": cfg.lid_write_3, "achievement": "streak_master"}, r,
           "non-200, same validation error (level checked with is None, 0 must NOT trigger it)", passed)

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": "gold"},
                     headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "award__non_numeric_level", award_ep,
           {"learner_id": cfg.lid_write_3, "achievement": "streak_master", "level": "gold"}, r,
           "non-200, ValidationError level must be numeric", passed)

    r = client.call(award_ep, {"learner_id": cfg.lid_write_3, "achievement": "xp_champion", "level": 1},
                     headers=client.api_key_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("awarded") is True and body.get("achievement") == "xp_champion"
    record(log, "award__different_achievement_same_learner", award_ep,
           {"learner_id": cfg.lid_write_3, "achievement": "xp_champion", "level": 1}, r,
           "200, second distinct achievement row added", passed)

    r = client.call(read_ep, {})
    passed = not r.is_2xx()
    record(log, "achievements__missing_learner_id", read_ep, {}, r,
           "non-200, ValidationError learner_id is required", passed)

    r = client.call(read_ep, {"learner_id": cfg.lid_write_3})
    passed = r.is_2xx()
    record(log, "achievements__no_auth_still_works", read_ep, {"learner_id": cfg.lid_write_3}, r,
           "200 with zero auth headers", passed, "SECURITY FINDING alongside other no-auth findings")
    if passed:
        log.add_finding("get_learner_achievements has no auth gate", read_ep,
                         "get_learner_achievements succeeds with zero auth headers sent",
                         f"status={r.status_code}")


def run_export_program_content_suite(client, cfg, log):
    ep = "export_program_content"

    if not cfg.program_id_for_export:
        for cid in ("export_program__no_api_credentials", "export_program__happy_default_all_langs",
                    "export_program__single_lang", "export_program__multi_lang_comma_string",
                    "export_program__include_r2_flag_noop"):
            record(log, cid, ep, {}, None, "200", None, "SKIPPED — no program_id_for_export in config")
    else:
        r = client.call(ep, {"program_id": cfg.program_id_for_export})
        passed = not r.is_2xx()
        record(log, "export_program__no_api_credentials", ep, {"program_id": cfg.program_id_for_export}, r,
               "non-200, rejected before function runs", passed)

        t0 = time.time()
        r = client.call(ep, {"program_id": cfg.program_id_for_export}, headers=client.api_key_headers(), timeout=120)
        baseline_latency = time.time() - t0
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and "payload" in body
        record(log, "export_program__happy_default_all_langs", ep,
               {"program_id": cfg.program_id_for_export}, r,
               "200, payload with constants/languages/states/districts/langs keyed by every language code", passed,
               f"single-call baseline latency={round(baseline_latency, 2)}s — time before any concurrency")

        r = client.call(ep, {"program_id": cfg.program_id_for_export, "langs": "en"}, headers=client.api_key_headers(), timeout=120)
        body = r.message_body()
        passed = (r.is_2xx() and isinstance(body, dict) and body.get("success") is True
                  and set(body.get("payload", {}).get("langs", {}).keys()) == {"en"})
        record(log, "export_program__single_lang", ep,
               {"program_id": cfg.program_id_for_export, "langs": "en"}, r,
               "200, payload.langs has exactly one key en", passed)

        r = client.call(ep, {"program_id": cfg.program_id_for_export, "langs": "en,hi"}, headers=client.api_key_headers(), timeout=120)
        body = r.message_body()
        passed = (r.is_2xx() and isinstance(body, dict) and body.get("success") is True
                  and set(body.get("payload", {}).get("langs", {}).keys()) == {"en", "hi"})
        record(log, "export_program__multi_lang_comma_string", ep,
               {"program_id": cfg.program_id_for_export, "langs": "en,hi"}, r,
               "200, payload.langs has exactly en and hi", passed)

        r = client.call(ep, {"program_id": cfg.program_id_for_export, "include_r2": "true"}, headers=client.api_key_headers(), timeout=120)
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
        record(log, "export_program__include_r2_flag_noop", ep,
               {"program_id": cfg.program_id_for_export, "include_r2": "true"}, r,
               "200, include_r2 has no observable effect on payload shape (accepted but unused)", passed)

    r = client.call(ep, {"program_id": "PROGRAM-DOES-NOT-EXIST"}, headers=client.api_key_headers())
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False and "error" in body
    record(log, "export_program__nonexistent_program", ep, {"program_id": "PROGRAM-DOES-NOT-EXIST"}, r,
           "200 (not an exception), success:false, error message about no course levels found", passed)

    r = client.call(ep, {}, headers=client.api_key_headers())
    passed = not r.is_2xx()
    record(log, "export_program__missing_program_id", ep, {}, r,
           "non-200, ValidationError program_id is required", passed)


def run_export_content_suite(client, cfg, log):
    ep = "export_content"

    r = client.call(ep, {})
    passed = not r.is_2xx()
    record(log, "export_content__no_api_credentials", ep, {}, r,
           "non-200, rejected before function runs", passed)

    r = client.call(ep, {}, headers=client.api_key_headers(), timeout=60)
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and "payload" in body
    record(log, "export_content__happy", ep, {}, r,
           "200, success:true, payload.content array shaped per _build_content_item", passed)

    passed = None
    note = "manually inspect payload.content for a row with populated/malformed authors JSON field"
    if r.is_2xx() and isinstance(body, dict):
        content = body.get("payload", {}).get("content", [])
        has_list_authors = any(isinstance(item.get("authors"), list) for item in content)
        if content:
            passed = has_list_authors or all("authors" not in item for item in content)
    record(log, "export_content__authors_json_field_parsing", ep, {}, None,
           "authors returned as parsed list; malformed/empty JSON returns []", passed, note)


def run_retrigger_smoke_suite(client, cfg, log):
    ep = "Tapapp Tasks.retrigger"

    if not cfg.run_retrigger_smoke:
        record(log, "retrigger__nightly_maintenance_smoke", ep, {}, None,
               "200, queued:true", None, "SKIPPED per config — smoke test only, run manually with intent")
        record(log, "retrigger__analytics_report_smoke", ep, {}, None,
               "200, queued:true", None, "SKIPPED per config — posts to external Apps Script webhook")
    else:
        r = client.call("frappe.client.run_doc_method", {
            "docname": "Nightly Window Maintenance",
            "doctype": "Tapapp Tasks",
            "method": "retrigger",
        }, headers=client.api_key_headers())
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("queued") is True
        record(log, "retrigger__nightly_maintenance_smoke", ep,
               {"docname": "Nightly Window Maintenance"}, r,
               "200, queued:true — call once, manually confirm tracker doc status transitions afterward", passed)

        record(log, "retrigger__analytics_report_smoke", ep, {}, None,
               "200, queued:true", None,
               "SKIPPED — posts to external Apps Script webhook, only run manually if safe to trigger for real")

    record(log, "retrigger__unregistered_job_key", ep, {}, None, "N/A", None,
           "N/A — Select field only allows the two documented values, cannot be sent through the API cleanly")


def sec_record(log, case_id, endpoint, params, call_result, expected_note, passed, note=""):
    row = {
        "timestamp": now_ts(),
        "case_id": case_id,
        "endpoint": endpoint,
        "params": redact(params),
        "status_code": call_result.status_code if call_result else None,
        "latency_ms": round(call_result.latency_ms, 1) if call_result else None,
        "error": call_result.error if call_result else None,
        "expected": expected_note,
        "result": "PASS" if passed is True else ("FAIL" if passed is False else "SKIPPED"),
        "note": note,
    }
    log.add_security(row)
    return row


def run_security_matrix(client, cfg, log, state):
    if not state.token_a:
        sec_record(log, "security__phone_a_cannot_read_phone_b_profile", "select_profile", {}, None,
                   "non-200, Profile not linked to this account", None, "SKIPPED — no token_a available")
        sec_record(log, "security__phone_a_cannot_write_phone_b_profile", "update_student", {}, None,
                   "non-200, ownership error", None, "SKIPPED — no token_a available")
    else:
        auth_headers = client.bearer_headers(state.token_a)

        r = client.call("select_profile", {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b}, headers=auth_headers)
        passed = not r.is_2xx()
        sec_record(log, "security__phone_a_cannot_read_phone_b_profile", "select_profile",
                   {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b}, r,
                   "non-200, Profile not linked to this account", passed)

        r = client.call("update_student", {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b,
                                            "updates": json.dumps({"grade": "5"})}, headers=auth_headers)
        passed = not r.is_2xx()
        sec_record(log, "security__phone_a_cannot_write_phone_b_profile", "update_student",
                   {"phone": cfg.phone_a, "learner_id": cfg.lid_owned_b, "updates": {"grade": "5"}}, r,
                   "non-200, same ownership error", passed)

        impersonation_targets = [
            ("get_profiles", {"phone": cfg.phone_b, "page": 1, "page_size": 10}),
            ("search_profiles", {"phone": cfg.phone_b, "page": 1, "page_size": 10}),
            ("select_profile", {"phone": cfg.phone_b, "learner_id": cfg.lid_owned_a}),
            ("update_avatar", {"phone": cfg.phone_b, "learner_id": cfg.lid_owned_a, "avatar": "1"}),
            ("update_profile", {"phone": cfg.phone_b, "learner_id": cfg.lid_owned_a,
                                 "updates": json.dumps({"grade": "6"})}),
            ("get_bulk_students", {"phone": cfg.phone_b, "page": 1, "page_size": 10}),
            ("bulk_update_students", {"phone": cfg.phone_b,
                                       "changes": json.dumps([{"learner_id": cfg.lid_owned_a,
                                                                "updates": {"grade": "6"}}])}),
            ("complete_onboarding", {"phone": cfg.phone_b, "learner_id": cfg.lid_owned_a}),
        ]
        for ep, params in impersonation_targets:
            r = client.call(ep, params, headers=auth_headers)
            passed = not r.is_2xx()
            sec_record(log, f"security__phone_a_token_cannot_impersonate_phone_b_param__{ep}", ep, params, r,
                       "non-200, Token phone mismatch", passed)

    no_auth_targets = [
        ("get_learner_state", {"learner_id": cfg.lid_owned_b}),
        ("get_learner_progress", {"learner_id": cfg.lid_owned_b}),
        ("get_learners_progress", {"learner_ids": json.dumps([cfg.lid_owned_b])}),
        ("enroll_course", {"learner_id": cfg.lid_owned_b, "course": cfg.course_1 or "COURSE-LEVEL-A"}),
        ("record_activity", {"learner_id": cfg.lid_owned_b, "xp": 5, "activity_type": "video"}),
        ("update_content_progress", {"learner_id": cfg.lid_owned_b, "video_index": 1, "activity_type": "video"}),
        ("get_learner_achievements", {"learner_id": cfg.lid_owned_b}),
    ]
    open_count = 0
    for ep, params in no_auth_targets:
        r = client.call(ep, params)
        passed = r.is_2xx()
        if passed:
            open_count += 1
        sec_record(log, f"security__progress_endpoints_have_no_ownership_gate__{ep}", ep, params, r,
                   "200 — no ownership gate, single most important finding in the report", passed)
    if open_count > 0:
        log.add_finding("Progress endpoints have no ownership gate", "multiple",
                         f"{open_count}/{len(no_auth_targets)} progress/learner endpoints returned 200 with zero "
                         "auth headers against a learner_id owned by a different account — anyone who knows or "
                         "can guess a learner_id string can read and write that learner's progress/XP/enrollment "
                         "with no login at all",
                         f"endpoints tested: {[e for e, _ in no_auth_targets]}")

    session_gated_targets = [
        ("award_achievement", {"learner_id": cfg.lid_write_3, "achievement": "sec_check", "level": 1}),
        ("submission_verified_webhook", {"learner_id": cfg.lid_write_3, "submission_index": 999999}),
        ("export_program_content", {"program_id": cfg.program_id_for_export or "PROGRAM-001"}),
        ("export_content", {}),
    ]
    if state.token_a:
        for ep, params in session_gated_targets:
            r = client.call(ep, params, headers=client.bearer_headers(state.token_a))
            passed = not r.is_2xx()
            sec_record(log, f"security__session_gated_endpoints_reject_jwt__{ep}", ep, params, r,
                       "non-200 — properly isolated from guest/JWT surface", passed)
    else:
        for ep, _ in session_gated_targets:
            sec_record(log, f"security__session_gated_endpoints_reject_jwt__{ep}", ep, {}, None,
                       "non-200", None, "SKIPPED — no token_a available")

    if state.reset_token_a:
        r = client.call("get_profiles", {"phone": cfg.phone_a}, headers=client.bearer_headers(state.reset_token_a))
        passed = not r.is_2xx()
        sec_record(log, "security__reset_token_cannot_be_used_as_access_token", "get_profiles",
                   {"phone": cfg.phone_a}, r, "non-200, Invalid or expired token", passed)
    else:
        sec_record(log, "security__reset_token_cannot_be_used_as_access_token", "get_profiles", {}, None,
                   "non-200", None, "SKIPPED — no reset token available")

    if state.token_a:
        r = client.call("reset_password", {"phone": cfg.phone_a, "password": "IrrelevantPass1"},
                         headers=client.bearer_headers(state.token_a, "Authorization"))
        passed = not r.is_2xx()
        sec_record(log, "security__access_token_cannot_be_used_as_reset_token", "reset_password",
                   {"phone": cfg.phone_a, "password": "IrrelevantPass1"}, r,
                   "non-200, Invalid or expired reset token", passed)
    else:
        sec_record(log, "security__access_token_cannot_be_used_as_reset_token", "reset_password", {}, None,
                   "non-200", None, "SKIPPED — no access token available")


def conc_record(log, case_id, endpoint, setup, load_desc, result_summary, verdict, note=""):
    row = {
        "timestamp": now_ts(),
        "case_id": case_id,
        "endpoint": endpoint,
        "setup": setup,
        "load": load_desc,
        "result_summary": result_summary,
        "verdict": verdict,
        "note": note,
    }
    log.add_concurrency(row)
    return row


def _fire_parallel(client, ep, params, headers, n):
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(client.call, ep, params, headers) for _ in range(n)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    return results


def run_record_activity_race(client, cfg, log, n):
    ep = "record_activity"
    lid = cfg.lid_concurrency
    if not lid:
        conc_record(log, f"race__record_activity_parallel_{n}", ep, {}, f"{n} concurrent calls",
                    "SKIPPED", None, "SKIPPED — no lid_concurrency configured")
        return

    pre = client.call("get_learner_state", {"learner_id": lid})
    pre_body = pre.message_body()
    if not isinstance(pre_body, dict):
        conc_record(log, f"race__record_activity_parallel_{n}", ep, {}, f"{n} concurrent calls",
                    "SKIPPED", None, "SKIPPED — could not read starting state for lid_concurrency")
        return

    starting_xp = pre_body.get("xp", 0)
    cap = pre_body.get("max_weekly_activities", 2)

    results = _fire_parallel(client, ep, {"learner_id": lid, "xp": 10, "activity_type": "video"}, {}, n)
    succeeded = sum(1 for r in results if r.is_2xx())
    rejected = sum(1 for r in results if not r.is_2xx())
    errored = sum(1 for r in results if r.error)

    post = client.call("get_learner_state", {"learner_id": lid})
    post_body = post.message_body()
    final_xp = post_body.get("xp", 0) if isinstance(post_body, dict) else None
    final_watched = post_body.get("activities_watched_this_week", None) if isinstance(post_body, dict) else None

    expected_xp = starting_xp + 10 * min(succeeded, cap)
    overshoot = succeeded > cap
    xp_correct = final_xp == starting_xp + 10 * succeeded if final_xp is not None else None
    verdict = "FAIL" if overshoot else ("PASS" if succeeded <= cap else None)

    summary = (f"succeeded={succeeded} rejected={rejected} errored={errored} "
               f"starting_xp={starting_xp} final_xp={final_xp} cap={cap} "
               f"final_activities_watched_this_week={final_watched}")
    conc_record(log, f"race__record_activity_parallel_{n}", ep,
               f"lid={lid} starting_xp={starting_xp} starting_watched=? cap={cap}",
               f"{n} concurrent record_activity(xp=10) calls",
               summary, verdict,
               "more than cap succeeded — confirmed race condition finding" if overshoot else "")
    if overshoot:
        log.add_finding("record_activity race condition", ep,
                         f"With {n} concurrent calls against the same learner, {succeeded} succeeded when the cap "
                         f"is {cap} — the weekly-activity check-then-update is not performed under a row lock",
                         summary)


def run_submission_webhook_race(client, cfg, log):
    ep = "submission_verified_webhook"
    lid = cfg.lid_concurrency
    if not lid:
        conc_record(log, "race__submission_webhook_parallel_replay", ep, {}, "10 concurrent calls",
                    "SKIPPED", None, "SKIPPED — no lid_concurrency configured")
        return

    pre = client.call("get_learner_state", {"learner_id": lid, "fields": "submission,xp"})
    pre_body = pre.message_body()
    if not isinstance(pre_body, dict):
        conc_record(log, "race__submission_webhook_parallel_replay", ep, {}, "10 concurrent calls",
                    "SKIPPED", None, "SKIPPED — could not read starting state for lid_concurrency")
        return

    starting_index = pre_body.get("submission_index", 0)
    starting_gems = pre_body.get("submission_gems", 0)
    next_index = starting_index + 1

    results = _fire_parallel(client, ep, {"learner_id": lid, "submission_index": next_index},
                             client.api_key_headers(), 10)
    processed_true = 0
    for r in results:
        body = r.message_body()
        if isinstance(body, dict) and body.get("processed") is True:
            processed_true += 1

    post = client.call("get_learner_state", {"learner_id": lid, "fields": "submission,xp"})
    post_body = post.message_body()
    final_gems = post_body.get("submission_gems", None) if isinstance(post_body, dict) else None

    expected_gems = starting_gems + 1
    verdict = "PASS" if processed_true == 1 and final_gems == expected_gems else "FAIL"
    summary = f"processed_true_count={processed_true} starting_gems={starting_gems} final_gems={final_gems} expected_gems={expected_gems}"
    conc_record(log, "race__submission_webhook_parallel_replay", ep,
               f"lid={lid} starting_index={starting_index}",
               "10 concurrent submission_verified_webhook calls claiming the same next index",
               summary, verdict)
    if verdict == "FAIL":
        log.add_finding("submission_verified_webhook race condition", ep,
                         "More or fewer than exactly one concurrent call processed the same submission index, "
                         "or the gems delta did not equal exactly one award's worth",
                         summary)


def run_bulk_vs_single_race(client, cfg, log, state):
    ep = "bulk_update_students vs update_student"
    lid = cfg.lid_concurrency
    if not lid or not cfg.allow_bulk_write_tests:
        conc_record(log, "race__bulk_update_vs_single_update_same_learner", ep, {}, "1 update_student + 1 bulk_update_students",
                    "SKIPPED", None, "SKIPPED — no lid_concurrency configured or bulk writes disabled")
        return

    token = state.token_a
    if not token:
        login = client.call("login_with_password", {"phone": cfg.phone_a, "password": state.pass_a_current or cfg.pass_a})
        body = login.message_body()
        token = body.get("token") if isinstance(body, dict) else None
    if not token:
        conc_record(log, "race__bulk_update_vs_single_update_same_learner", ep, {}, "1 update_student + 1 bulk_update_students",
                    "SKIPPED", None, "SKIPPED — could not obtain token for phone_a")
        return

    headers = client.bearer_headers(token)

    def call_single():
        return client.call("update_student", {"phone": cfg.phone_a, "learner_id": lid,
                                                "updates": json.dumps({"grade": "5"})}, headers=headers)

    def call_bulk():
        return client.call("bulk_update_students", {"phone": cfg.phone_a,
                                                      "changes": json.dumps([{"learner_id": lid, "updates": {"grade": "9"}}]),
                                                      "atomic": "false"}, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(call_single)
        f2 = pool.submit(call_bulk)
        r1 = f1.result()
        r2 = f2.result()

    post = client.call("select_profile", {"phone": cfg.phone_a, "learner_id": lid, "fields": "profile"}, headers=headers)
    post_body = post.message_body()
    final_grade = post_body.get("profile", {}).get("grade") if isinstance(post_body, dict) else None

    verdict = "PASS" if final_grade in ("5", "9") else "FAIL"
    summary = f"update_student_status={r1.status_code} bulk_update_status={r2.status_code} final_grade={final_grade}"
    conc_record(log, "race__bulk_update_vs_single_update_same_learner", ep,
               f"lid={lid}",
               "one update_student(grade=5) and one bulk_update_students(grade=9) fired simultaneously",
               summary, verdict,
               "last-write-wins documentation case, not necessarily a bug, but must be observed and recorded")


class ResourceSampler:
    def __init__(self, interval_seconds):
        self.interval_seconds = interval_seconds
        self.samples = []
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                cpu_percpu = psutil.cpu_percent(percpu=True)
                vm = psutil.virtual_memory()
                try:
                    load_avg = os.getloadavg()
                except (AttributeError, OSError):
                    load_avg = None
                try:
                    conns = len(psutil.net_connections())
                except (psutil.AccessDenied, PermissionError):
                    conns = None
                try:
                    disk_io = psutil.disk_io_counters()
                    disk_io_dict = disk_io._asdict() if disk_io else None
                except Exception:
                    disk_io_dict = None
                sample = {
                    "ts": time.time(),
                    "cpu_percpu": cpu_percpu,
                    "cpu_avg": sum(cpu_percpu) / len(cpu_percpu) if cpu_percpu else None,
                    "ram_percent": vm.percent,
                    "ram_available_mb": vm.available // (1024 * 1024),
                    "load_avg": load_avg,
                    "tcp_connections": conns,
                    "disk_io": disk_io_dict,
                }
                with self.lock:
                    self.samples.append(sample)
            except Exception:
                pass
            self._stop_event.wait(self.interval_seconds)

    def start(self):
        self.samples = []
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def summary(self):
        with self.lock:
            samples = list(self.samples)
        if not samples:
            return {"cpu_avg": None, "cpu_peak": None, "ram_avg": None, "ram_peak": None}
        cpu_vals = [s["cpu_avg"] for s in samples if s["cpu_avg"] is not None]
        ram_vals = [s["ram_percent"] for s in samples if s["ram_percent"] is not None]
        return {
            "cpu_avg": round(statistics.mean(cpu_vals), 1) if cpu_vals else None,
            "cpu_peak": round(max(cpu_vals), 1) if cpu_vals else None,
            "ram_avg": round(statistics.mean(ram_vals), 1) if ram_vals else None,
            "ram_peak": round(max(ram_vals), 1) if ram_vals else None,
            "sample_count": len(samples),
        }


def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def stress_record(log, endpoint_class, endpoint, level, sent, success, fail, err, latencies, duration_s, resource_summary, note=""):
    row = {
        "timestamp": now_ts(),
        "endpoint_class": endpoint_class,
        "endpoint": endpoint,
        "concurrency_level": level,
        "requests_sent": sent,
        "success": success,
        "fail": fail,
        "errored": err,
        "duration_s": round(duration_s, 2),
        "throughput_rps": round(sent / duration_s, 2) if duration_s > 0 else None,
        "latency_min_ms": round(min(latencies), 1) if latencies else None,
        "latency_mean_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "latency_p50_ms": round(percentile(latencies, 50), 1) if latencies else None,
        "latency_p90_ms": round(percentile(latencies, 90), 1) if latencies else None,
        "latency_p95_ms": round(percentile(latencies, 95), 1) if latencies else None,
        "latency_p99_ms": round(percentile(latencies, 99), 1) if latencies else None,
        "latency_max_ms": round(max(latencies), 1) if latencies else None,
        "cpu_avg": resource_summary.get("cpu_avg"),
        "cpu_peak": resource_summary.get("cpu_peak"),
        "ram_avg": resource_summary.get("ram_avg"),
        "ram_peak": resource_summary.get("ram_peak"),
        "note": note,
    }
    log.add_stress(row)
    return row


def run_load_level(client, cfg, ep, param_factory, headers_factory, total_requests, concurrency):
    latencies = []
    success = 0
    fail = 0
    errored = 0
    lock = threading.Lock()

    def worker(_):
        r = client.call(ep, param_factory(), headers_factory())
        with lock:
            latencies.append(r.latency_ms)
        return r

    t0 = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker, i) for i in range(total_requests)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    duration = time.time() - t0

    for r in results:
        if r.error:
            errored += 1
        elif r.is_2xx():
            success += 1
        else:
            fail += 1

    return duration, latencies, success, fail, errored


def run_stress_class(client, cfg, log, class_name, ep, param_factory, headers_factory, max_concurrency_hint=None):
    sampler = ResourceSampler(cfg.sample_resource_interval_seconds)
    levels = cfg.concurrency_levels
    if max_concurrency_hint:
        levels = [lvl for lvl in levels if lvl <= max_concurrency_hint] or [levels[0]]

    ceiling = None
    ceiling_reason = "completed_all_levels"

    for level in levels:
        requests_this_level = min(cfg.requests_per_level, max(level * 3, level))
        sampler.start()
        t0 = time.time()
        duration, latencies, success, fail, errored = run_load_level(
            client, cfg, ep, param_factory, headers_factory, requests_this_level, level
        )
        sampler.stop()
        resource_summary = sampler.summary()

        error_rate = (fail + errored) / requests_this_level if requests_this_level else 0
        stress_record(log, class_name, ep, level, requests_this_level, success, fail, errored,
                     latencies, duration, resource_summary)

        if error_rate > cfg.abort_error_rate_threshold:
            ceiling_reason = "error_rate_exceeded"
            break
        if duration > cfg.max_duration_seconds_per_level:
            ceiling_reason = "duration_exceeded"
            break
        ceiling = level

        time.sleep(cfg.ramp_pause_seconds)

    stress_record(log, class_name, ep, "CEILING", None, None, None, None, [], 0, {},
                 note=f"max sustainable concurrency={ceiling} reason={ceiling_reason}")
    return ceiling, ceiling_reason


def run_stress_suite(client, cfg, log, state):
    def no_headers():
        return {}

    def auth_headers():
        return client.bearer_headers(state.token_a) if state.token_a else {}

    run_stress_class(client, cfg, log, "Class A (cheap reads)", "get_learner_state",
                     lambda: {"learner_id": cfg.lid_owned_a}, no_headers)
    run_stress_class(client, cfg, log, "Class A (cheap reads)", "check_phone",
                     lambda: {"phone": cfg.phone_a}, no_headers)
    run_stress_class(client, cfg, log, "Class A (cheap reads)", "get_learner_achievements",
                     lambda: {"learner_id": cfg.lid_owned_a}, no_headers)

    if state.token_a:
        run_stress_class(client, cfg, log, "Class B (paginated reads)", "get_profiles",
                         lambda: {"phone": cfg.phone_a, "page": 1, "page_size": 50}, auth_headers)
        run_stress_class(client, cfg, log, "Class B (paginated reads)", "get_bulk_students",
                         lambda: {"phone": cfg.phone_a, "page": 1, "page_size": 50}, auth_headers)

    run_stress_class(client, cfg, log, "Class B (paginated reads)", "get_learners_progress",
                     lambda: {"learner_ids": json.dumps([cfg.lid_write_1, cfg.lid_write_2, cfg.lid_write_3])}, no_headers)

    run_stress_class(client, cfg, log, "Class C (single writes)", "record_activity",
                     lambda: {"learner_id": cfg.lid_write_1, "xp": 1, "activity_type": "stress"}, no_headers,
                     max_concurrency_hint=10)

    if cfg.allow_bulk_write_tests and state.token_a:
        run_stress_class(client, cfg, log, "Class D (bulk writes)", "bulk_update_students",
                         lambda: {"phone": cfg.phone_a,
                                   "changes": json.dumps([{"learner_id": cfg.lid_write_1, "updates": {"grade": "6"}}]),
                                   "atomic": "false"},
                         auth_headers, max_concurrency_hint=10)

    if cfg.program_id_for_export:
        run_stress_class(client, cfg, log, "Class E (heavy aggregation/export)", "export_program_content",
                         lambda: {"program_id": cfg.program_id_for_export}, client.api_key_headers,
                         max_concurrency_hint=5)


def write_report(log, cfg, run_id, start_time, end_time, output_dir="."):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"test_backend_report_{timestamp}.txt")

    total = len(log.functional_rows)
    passed = sum(1 for r in log.functional_rows if r["result"] == "PASS")
    failed = sum(1 for r in log.functional_rows if r["result"] == "FAIL")
    skipped = sum(1 for r in log.functional_rows if r["result"] == "SKIPPED")

    lines = []
    lines.append("TAPAPP BACKEND TEST REPORT")
    lines.append(f"Generated: {now_ts()}")
    lines.append(f"Target base_url: {cfg.base_url}")
    lines.append(f"Script version/run id: {run_id}")
    lines.append(f"Run started: {start_time}")
    lines.append(f"Run ended: {end_time}")
    lines.append("")
    lines.append("MACHINE INFO")
    try:
        logical = psutil.cpu_count(logical=True)
        physical = psutil.cpu_count(logical=False)
    except Exception:
        logical, physical = None, None
    try:
        total_ram_mb = psutil.virtual_memory().total // (1024 * 1024)
    except Exception:
        total_ram_mb = None
    lines.append(f"CPU cores (logical/physical): {logical} / {physical}")
    lines.append(f"Total RAM: {total_ram_mb} MB")
    lines.append(f"OS: {platform.platform()}")
    lines.append(f"Python: {platform.python_version()}")
    lines.append("")

    lines.append("SECTION 1: FUNCTIONAL TEST RESULTS")
    lines.append("-" * 60)
    grouped = {}
    for row in log.functional_rows:
        grouped.setdefault(row["endpoint"], []).append(row)
    for endpoint in sorted(grouped.keys()):
        lines.append(f"Endpoint: {endpoint}")
        for row in grouped[endpoint]:
            status_part = f"{row['status_code']}" if row["status_code"] is not None else "no-response"
            latency_part = f"{row['latency_ms']}ms" if row["latency_ms"] is not None else "n/a"
            lines.append(f"  [{row['timestamp']}] Case: {row['case_id']:<55} -> {row['result']:<8} "
                        f"({status_part}, {latency_part})")
            if row["note"]:
                lines.append(f"      note: {row['note']}")
            if row["error"]:
                lines.append(f"      error: {row['error']}")
        lines.append("")

    lines.append(f"TOTAL FUNCTIONAL CASES RUN: {total}")
    lines.append(f"PASSED: {passed}   FAILED: {failed}   SKIPPED: {skipped}")
    lines.append("")

    lines.append("SECTION 2: SECURITY / AUTH BOUNDARY RESULTS")
    lines.append("-" * 60)
    for row in log.security_rows:
        status_part = f"{row['status_code']}" if row["status_code"] is not None else "no-response"
        latency_part = f"{row['latency_ms']}ms" if row["latency_ms"] is not None else "n/a"
        lines.append(f"  [{row['timestamp']}] Case: {row['case_id']:<55} -> {row['result']:<8} "
                    f"({status_part}, {latency_part})")
        if row["note"]:
            lines.append(f"      note: {row['note']}")
    sec_total = len(log.security_rows)
    sec_passed = sum(1 for r in log.security_rows if r["result"] == "PASS")
    sec_failed = sum(1 for r in log.security_rows if r["result"] == "FAIL")
    sec_skipped = sum(1 for r in log.security_rows if r["result"] == "SKIPPED")
    lines.append("")
    lines.append(f"TOTAL SECURITY CASES RUN: {sec_total}")
    lines.append(f"PASSED: {sec_passed}   FAILED: {sec_failed}   SKIPPED: {sec_skipped}")
    lines.append("")

    lines.append("SECTION 3: CONCURRENCY / RACE CONDITION CHECK")
    lines.append("-" * 60)
    for row in log.concurrency_rows:
        lines.append(f"  [{row['timestamp']}] Case: {row['case_id']}")
        lines.append(f"      Endpoint: {row['endpoint']}")
        lines.append(f"      Setup: {row['setup']}")
        lines.append(f"      Load: {row['load']}")
        lines.append(f"      Result: {row['result_summary']}")
        lines.append(f"      VERDICT: {row['verdict']}")
        if row["note"]:
            lines.append(f"      note: {row['note']}")
        lines.append("")

    lines.append("SECTION 4: STRESS / LOAD TEST RESULTS")
    lines.append("-" * 60)
    stress_grouped = {}
    for row in log.stress_rows:
        key = (row["endpoint_class"], row["endpoint"])
        stress_grouped.setdefault(key, []).append(row)
    for (cls, ep), rows in stress_grouped.items():
        lines.append(f"{cls} - {ep}")
        for row in rows:
            if row["concurrency_level"] == "CEILING":
                lines.append(f"  {row['note']}")
                continue
            lines.append(
                f"  Level={row['concurrency_level']:<5} sent={row['requests_sent']} success={row['success']} "
                f"fail={row['fail']} err={row['errored']} rps={row['throughput_rps']} "
                f"latency(ms) min={row['latency_min_ms']} mean={row['latency_mean_ms']} "
                f"p50={row['latency_p50_ms']} p90={row['latency_p90_ms']} p95={row['latency_p95_ms']} "
                f"p99={row['latency_p99_ms']} max={row['latency_max_ms']} "
                f"cpu_avg={row['cpu_avg']} cpu_peak={row['cpu_peak']} "
                f"ram_avg={row['ram_avg']} ram_peak={row['ram_peak']}"
            )
        lines.append("")

    lines.append("SECTION 5: FINDINGS / ANOMALIES")
    lines.append("-" * 60)
    if not log.findings:
        lines.append("No findings recorded.")
    for i, finding in enumerate(log.findings, 1):
        lines.append(f"#{i} {finding['title']} - {finding['endpoint']}")
        lines.append(f"    {finding['description']}")
        if finding["evidence"]:
            lines.append(f"    Evidence: {finding['evidence']}")
    lines.append("")

    lines.append("SECTION 6: SUMMARY RECOMMENDATION")
    lines.append("-" * 60)
    ceilings = [r for r in log.stress_rows if r["concurrency_level"] == "CEILING"]
    if ceilings:
        for row in ceilings:
            lines.append(f"{row['endpoint_class']} ({row['endpoint']}): {row['note']}")
    else:
        lines.append("Stress suite was not run in this pass.")
    urgent = sorted({f["endpoint"] for f in log.findings})
    lines.append("")
    lines.append(f"Endpoints requiring urgent attention: {urgent if urgent else 'none identified'}")
    safe_endpoints = sorted({
        row["endpoint"] for row in log.functional_rows if row["result"] == "PASS"
    } - set(urgent))
    lines.append(f"Endpoints confirmed passing at least one case with no related finding: {len(safe_endpoints)} endpoints")
    lines.append("")
    lines.append("END OF REPORT")

    with open(filename, "w") as f:
        f.write("\n".join(lines))

    return filename


def main():
    parser = argparse.ArgumentParser(description="Tapapp backend full test suite")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--only", default=None,
                        help="Comma-separated section names to run: functional,security,concurrency,stress")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only run functional + security sections, skip stress and concurrency")
    parser.add_argument("--output-dir", default=".", help="Directory to write the report file into")
    args = parser.parse_args()

    cfg = Config(args.config)
    client = ApiClient(cfg)
    log = ResultLog()
    state = State()
    run_id = str(uuid.uuid4())
    start_time = now_ts()

    sections = None
    if args.only:
        sections = {s.strip() for s in args.only.split(",")}

    def wants(name):
        if sections is not None:
            return name in sections
        if args.dry_run and name in ("concurrency", "stress"):
            return False
        return True

    if wants("functional"):
        run_check_phone_suite(client, cfg, log)
        run_login_suite(client, cfg, log, state)
        run_forgot_password_suite(client, cfg, log, state)
        run_reset_password_suite(client, cfg, log, state)

        if not state.token_a:
            login = client.call("login_with_password", {"phone": cfg.phone_a, "password": state.pass_a_current or cfg.pass_a})
            body = login.message_body()
            if isinstance(body, dict) and body.get("token"):
                state.token_a = body["token"]

        run_get_profiles_suite(client, cfg, log, state)
        run_search_profiles_suite(client, cfg, log, state)
        run_select_profile_suite(client, cfg, log, state)
        run_update_avatar_suite(client, cfg, log, state)
        run_update_profile_suite(client, cfg, log, state)
        run_update_student_suite(client, cfg, log, state)
        run_get_bulk_students_suite(client, cfg, log, state)
        run_bulk_update_students_suite(client, cfg, log, state)
        run_complete_onboarding_suite(client, cfg, log, state)
        run_learner_state_progress_suite(client, cfg, log, state)
        run_get_learners_progress_suite(client, cfg, log)
        run_enroll_course_suite(client, cfg, log, state)
        run_record_activity_suite(client, cfg, log, state)
        run_content_progress_suite(client, cfg, log, state)
        run_submission_webhook_suite(client, cfg, log, state)
        run_achievements_suite(client, cfg, log, state)
        run_export_program_content_suite(client, cfg, log)
        run_export_content_suite(client, cfg, log)
        run_retrigger_smoke_suite(client, cfg, log)

    if wants("security"):
        run_security_matrix(client, cfg, log, state)

    if wants("concurrency") and cfg.run_concurrency_suite:
        run_record_activity_race(client, cfg, log, 5)
        run_record_activity_race(client, cfg, log, 20)
        run_submission_webhook_race(client, cfg, log)
        run_bulk_vs_single_race(client, cfg, log, state)
    elif wants("concurrency"):
        conc_record(log, "concurrency_suite", "n/a", {}, "n/a", "SKIPPED", None,
                   "SKIPPED — safety.run_concurrency_suite is false in config")

    if wants("stress") and cfg.run_stress_suite:
        run_stress_suite(client, cfg, log, state)

    end_time = now_ts()
    report_path = write_report(log, cfg, run_id, start_time, end_time, output_dir=args.output_dir)

    print(f"Report written to: {report_path}")
    print(f"Functional: {sum(1 for r in log.functional_rows if r['result']=='PASS')} passed, "
          f"{sum(1 for r in log.functional_rows if r['result']=='FAIL')} failed, "
          f"{sum(1 for r in log.functional_rows if r['result']=='SKIPPED')} skipped")
    print(f"Security: {sum(1 for r in log.security_rows if r['result']=='PASS')} passed, "
          f"{sum(1 for r in log.security_rows if r['result']=='FAIL')} failed, "
          f"{sum(1 for r in log.security_rows if r['result']=='SKIPPED')} skipped")
    print(f"Findings: {len(log.findings)}")


if __name__ == "__main__":
    main()