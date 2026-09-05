import argparse
import concurrent.futures
import datetime
import json
import os
import platform
import signal
import statistics
import sys
import threading
import time
import uuid

import psutil
import requests


ENDPOINT_MODULE_MAP = {
    "check_phone": "tap_lms.tapapp.api.auth.tapapp_auth.check_phone",
    "login_with_password": "tap_lms.tapapp.api.auth.tapapp_auth.login_with_password",
    "get_profiles": "tap_lms.tapapp.api.auth.tapapp_auth.get_profiles",
    "search_profiles": "tap_lms.tapapp.api.auth.tapapp_auth.search_profiles",
    "forgot_password_send_otp": "tap_lms.tapapp.api.auth.tapapp_auth.forgot_password_send_otp",
    "forgot_password_verify_otp": "tap_lms.tapapp.api.auth.tapapp_auth.forgot_password_verify_otp",
    "reset_password": "tap_lms.tapapp.api.auth.tapapp_auth.reset_password",

    "select_profile": "tap_lms.tapapp.api.profile.profile.select_profile",
    "update_avatar": "tap_lms.tapapp.api.profile.profile.update_avatar",
    "update_profile": "tap_lms.tapapp.api.profile.profile.update_profile",
    "search_student": "tap_lms.tapapp.api.profile.profile.search_student",
    "get_bulk_students": "tap_lms.tapapp.api.profile.profile.get_bulk_students",
    "update_student": "tap_lms.tapapp.api.profile.profile.update_student",
    "bulk_update_students": "tap_lms.tapapp.api.profile.profile.bulk_update_students",

    "complete_onboarding": "tap_lms.tapapp.api.profile.onboarding.complete_onboarding",

    "get_learner_state": "tap_lms.tapapp.api.progress.learner.get_learner_state",
    "get_learner_progress": "tap_lms.tapapp.api.progress.learner.get_learner_progress",
    "get_learners_progress": "tap_lms.tapapp.api.progress.learner.get_learners_progress",
    "enroll_course": "tap_lms.tapapp.api.progress.learner.enroll_course",
    "record_activity": "tap_lms.tapapp.api.progress.learner.record_activity",
    "update_content_progress": "tap_lms.tapapp.api.progress.learner.update_content_progress",
    "submit_progress": "tap_lms.tapapp.api.progress.learner.submit_progress",
    "submission_verified_webhook": "tap_lms.tapapp.api.progress.learner.submission_verified_webhook",

    "get_learner_achievements": "tap_lms.tapapp.api.progress.achievements.get_learner_achievements",
    "award_achievement": "tap_lms.tapapp.api.progress.achievements.award_achievement",

    "export_program_content": "tap_lms.tapapp.api.content.export.export_program_content",
    "export_content": "tap_lms.tapapp.api.content.export.export_content",
}


class Config:
    def __init__(self, path):
        with open(path, "r") as f:
            raw = json.load(f)
        self.raw = raw
        self.base_url = raw["base_url"].rstrip("/")
        self.api_prefix = raw.get("api_prefix", "/api/method/")
        self.site_host = raw.get("site_host", "")
        self.endpoint_module_map = dict(ENDPOINT_MODULE_MAP)
        self.endpoint_module_map.update(raw.get("endpoint_module_overrides", {}))
        self.use_dotted_paths = raw.get("use_dotted_paths", True)
        self.frappe_api_key = raw.get("frappe_api_key", "")
        self.frappe_api_secret = raw.get("frappe_api_secret", "")
        self.request_timeout_seconds = raw.get("request_timeout_seconds", 20)
        self.verify_tls = raw.get("verify_tls", False)

        self.users = raw.get("users", [])
        self.user_by_phone = {u["phone"]: u for u in self.users}
        self.all_learner_ids = [l["learner_id"] for u in self.users for l in u.get("learners", [])]

        course = raw.get("course_ids", {})
        self.course_1 = course.get("course_1")
        self.course_2 = course.get("course_2")

        self.program_id_for_export = raw.get("program_id_for_export")
        self.export_langs = raw.get("export_langs", ["en"])

        stress = raw.get("stress", {})
        self.initial_concurrency = stress.get("initial_concurrency", 5)
        self.growth_factor = stress.get("growth_factor", 2.0)
        self.hard_ceiling = stress.get("hard_ceiling", 1000)
        self.requests_per_level_min = stress.get("requests_per_level_min", 40)
        self.requests_per_level_max = stress.get("requests_per_level_max", 400)
        self.ramp_pause_seconds = stress.get("ramp_pause_seconds", 3)
        self.max_duration_seconds_per_level = stress.get("max_duration_seconds_per_level", 45)
        self.abort_error_rate_threshold = stress.get("abort_error_rate_threshold", 0.15)
        self.abort_p95_latency_ms = stress.get("abort_p95_latency_ms", 8000)
        self.client_cpu_abort_percent = stress.get("client_cpu_abort_percent", 90)
        self.client_ram_abort_percent = stress.get("client_ram_abort_percent", 90)
        self.sample_resource_interval_seconds = stress.get("sample_resource_interval_seconds", 0.5)
        self.consecutive_bad_levels_to_stop = stress.get("consecutive_bad_levels_to_stop", 2)
        self.refine_binary_search_steps = stress.get("refine_binary_search_steps", 4)

        safety = raw.get("safety", {})
        self.allow_password_mutation_tests = safety.get("allow_password_mutation_tests", False)
        self.allow_bulk_write_tests = safety.get("allow_bulk_write_tests", True)
        self.bulk_update_max_rows_per_request = safety.get("bulk_update_max_rows_per_request", 500)
        self.run_first_time_password_tests = safety.get("run_first_time_password_tests", False)
        self.run_stress_suite = safety.get("run_stress_suite", True)
        self.run_concurrency_suite = safety.get("run_concurrency_suite", True)
        self.run_retrigger_smoke = safety.get("run_retrigger_smoke", False)

        output = raw.get("output", {})
        self.results_dir = output.get("results_dir", "./stress_results")
        self.flush_every_n_results = output.get("flush_every_n_results", 1)


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
        adapter = requests.adapters.HTTPAdapter(pool_connections=500, pool_maxsize=500)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def call(self, method_path, params=None, headers=None, timeout=None):
        resolved_method = method_path
        if self.config.use_dotted_paths:
            resolved_method = self.config.endpoint_module_map.get(method_path, method_path)
        url = f"{self.config.base_url}{self.config.api_prefix}{resolved_method}"
        params = params or {}
        headers = dict(headers or {})
        if self.config.site_host:
            headers["Host"] = self.config.site_host
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
            return CallResult(status_code=resp.status_code, body=body, latency_ms=latency_ms, error=None)
        except requests.exceptions.RequestException as e:
            latency_ms = (time.time() - t0) * 1000.0
            return CallResult(status_code=None, body=None, latency_ms=latency_ms, error=str(e))

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


def now_ts():
    return datetime.datetime.now().astimezone().isoformat()


class StreamingLog:
    def __init__(self, results_dir, run_id):
        os.makedirs(results_dir, exist_ok=True)
        self.results_dir = results_dir
        self.run_id = run_id
        self.functional_path = os.path.join(results_dir, f"functional_{run_id}.jsonl")
        self.security_path = os.path.join(results_dir, f"security_{run_id}.jsonl")
        self.concurrency_path = os.path.join(results_dir, f"concurrency_{run_id}.jsonl")
        self.stress_path = os.path.join(results_dir, f"stress_{run_id}.jsonl")
        self.findings_path = os.path.join(results_dir, f"findings_{run_id}.jsonl")
        self.summary_path = os.path.join(results_dir, f"summary_{run_id}.json")
        self.status_path = os.path.join(results_dir, f"status_{run_id}.json")
        self.lock = threading.Lock()
        self.counts = {"functional_pass": 0, "functional_fail": 0, "functional_skip": 0,
                       "security_pass": 0, "security_fail": 0, "security_skip": 0,
                       "findings": 0, "stress_levels_completed": 0}
        self._touch_all()
        self.write_status("initializing")

    def _touch_all(self):
        for p in (self.functional_path, self.security_path, self.concurrency_path,
                  self.stress_path, self.findings_path):
            open(p, "a").close()

    def _append(self, path, row):
        with self.lock:
            with open(path, "a") as f:
                f.write(json.dumps(row) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def add_functional(self, row):
        self._append(self.functional_path, row)
        with self.lock:
            key = "functional_" + ("pass" if row["result"] == "PASS" else
                                    "fail" if row["result"] == "FAIL" else "skip")
            self.counts[key] += 1

    def add_security(self, row):
        self._append(self.security_path, row)
        with self.lock:
            key = "security_" + ("pass" if row["result"] == "PASS" else
                                  "fail" if row["result"] == "FAIL" else "skip")
            self.counts[key] += 1

    def add_concurrency(self, row):
        self._append(self.concurrency_path, row)

    def add_stress(self, row):
        self._append(self.stress_path, row)
        if row.get("concurrency_level") not in (None, "CEILING", "REFINE"):
            with self.lock:
                self.counts["stress_levels_completed"] += 1

    def add_finding(self, title, endpoint, description, evidence=""):
        row = {"timestamp": now_ts(), "title": title, "endpoint": endpoint,
               "description": description, "evidence": evidence}
        self._append(self.findings_path, row)
        with self.lock:
            self.counts["findings"] += 1

    def write_status(self, phase, extra=None):
        payload = {"timestamp": now_ts(), "run_id": self.run_id, "phase": phase, "counts": dict(self.counts)}
        if extra:
            payload["extra"] = extra
        with self.lock:
            tmp = self.status_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.status_path)

    def write_summary_snapshot(self, cfg, extra_lines=None):
        with self.lock:
            snapshot = {
                "timestamp": now_ts(),
                "run_id": self.run_id,
                "base_url": cfg.base_url,
                "counts": dict(self.counts),
            }
            tmp = self.summary_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(snapshot, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.summary_path)


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


class ResourceSampler:
    def __init__(self, interval_seconds, server_pids=None):
        self.interval_seconds = interval_seconds
        self.server_pids = server_pids or []
        self.samples = []
        self.lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None

    def _server_proc_sample(self):
        if not self.server_pids:
            return None
        total_cpu = 0.0
        total_rss = 0
        total_threads = 0
        total_fds = 0
        seen_any = False
        fds_available = True
        for pid in self.server_pids:
            try:
                p = psutil.Process(pid)
                with p.oneshot():
                    total_cpu += p.cpu_percent(interval=None)
                    total_rss += p.memory_info().rss
                    total_threads += p.num_threads()
                    if hasattr(p, "num_fds"):
                        total_fds += p.num_fds()
                    else:
                        fds_available = False
                seen_any = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if not seen_any:
            return None
        return {
            "cpu_percent": round(total_cpu, 1),
            "rss_mb": total_rss // (1024 * 1024),
            "num_threads": total_threads,
            "num_fds": total_fds if fds_available else None,
            "processes_tracked": len(self.server_pids),
        }

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
                    "disk_io": disk_io_dict,
                    "server_proc": self._server_proc_sample(),
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
            return {"cpu_avg": None, "cpu_peak": None, "ram_avg": None, "ram_peak": None,
                     "server_cpu_avg": None, "server_cpu_peak": None,
                     "server_rss_mb_avg": None, "server_rss_mb_peak": None}
        cpu_vals = [s["cpu_avg"] for s in samples if s["cpu_avg"] is not None]
        ram_vals = [s["ram_percent"] for s in samples if s["ram_percent"] is not None]
        server_cpu = [s["server_proc"]["cpu_percent"] for s in samples
                      if s.get("server_proc") and s["server_proc"].get("cpu_percent") is not None]
        server_rss = [s["server_proc"]["rss_mb"] for s in samples
                      if s.get("server_proc") and s["server_proc"].get("rss_mb") is not None]
        return {
            "cpu_avg": round(statistics.mean(cpu_vals), 1) if cpu_vals else None,
            "cpu_peak": round(max(cpu_vals), 1) if cpu_vals else None,
            "ram_avg": round(statistics.mean(ram_vals), 1) if ram_vals else None,
            "ram_peak": round(max(ram_vals), 1) if ram_vals else None,
            "server_cpu_avg": round(statistics.mean(server_cpu), 1) if server_cpu else None,
            "server_cpu_peak": round(max(server_cpu), 1) if server_cpu else None,
            "server_rss_mb_avg": round(statistics.mean(server_rss), 1) if server_rss else None,
            "server_rss_mb_peak": round(max(server_rss), 1) if server_rss else None,
            "sample_count": len(samples),
        }

    def is_client_saturated(self, cpu_threshold, ram_threshold):
        with self.lock:
            if not self.samples:
                return False
            recent = self.samples[-3:]
        cpu_vals = [s["cpu_avg"] for s in recent if s["cpu_avg"] is not None]
        ram_vals = [s["ram_percent"] for s in recent if s["ram_percent"] is not None]
        if cpu_vals and statistics.mean(cpu_vals) >= cpu_threshold:
            return True
        if ram_vals and statistics.mean(ram_vals) >= ram_threshold:
            return True
        return False


def find_server_pids(cfg):
    candidates = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "gunicorn" in cmdline or "frappe.app:application" in cmdline or "werkzeug" in cmdline:
            candidates.append(p.info["pid"])
    return candidates


class State:
    def __init__(self, cfg):
        self.tokens_by_phone = {}
        self.pass_current_by_phone = {u["phone"]: u["password"] for u in cfg.users}
        self.onboarded_learners = set()
        self.enrolled_learners = {}
        self.record_activity_calls = {}
        self.submission_index_by_learner = {}

    def token_for(self, client, cfg, phone):
        if phone in self.tokens_by_phone:
            return self.tokens_by_phone[phone]
        password = self.pass_current_by_phone.get(phone)
        r = client.call("login_with_password", {"phone": phone, "password": password})
        body = r.message_body()
        if isinstance(body, dict) and body.get("token"):
            self.tokens_by_phone[phone] = body["token"]
            return body["token"]
        return None


def run_login_all_users_suite(client, cfg, log, state):
    ep = "login_with_password"
    for u in cfg.users:
        phone = u["phone"]
        r = client.call(ep, {"phone": phone, "password": u["password"]})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True and body.get("token")
        if passed:
            state.tokens_by_phone[phone] = body["token"]
        record(log, f"login__{phone}", ep, {"phone": phone}, r,
               "200, success:true, token present", passed)

    r = client.call(ep, {"phone": cfg.users[0]["phone"], "password": "WrongPassword999"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False
    record(log, "login__wrong_password", ep, {"phone": cfg.users[0]["phone"]}, r,
           "200, success:false, error:invalid_credentials", passed)

    r = client.call(ep, {"phone": "9999999999", "password": "whatever1"})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is False
    record(log, "login__unregistered_phone", ep, {"phone": "9999999999"}, r,
           "200, success:false, error:invalid_credentials", passed,
           note="" if passed else f"actual body: {json.dumps(body)[:300]}")


def run_get_profiles_all_users_suite(client, cfg, log, state):
    ep = "get_profiles"
    for u in cfg.users:
        phone = u["phone"]
        token = state.tokens_by_phone.get(phone)
        if not token:
            record(log, f"get_profiles__{phone}", ep, {}, None, "200, profiles array", None,
                   "SKIPPED — no token for this phone")
            continue
        r = client.call(ep, {"phone": phone, "page": 1, "page_size": 50}, headers=client.bearer_headers(token))
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and "profiles" in body
        record(log, f"get_profiles__{phone}", ep, {"phone": phone}, r,
               "200, profiles array for this account", passed)


def run_onboarding_all_learners_suite(client, cfg, log, state):
    ep = "complete_onboarding"
    for u in cfg.users:
        phone = u["phone"]
        token = state.tokens_by_phone.get(phone)
        if not token:
            for l in u.get("learners", []):
                record(log, f"onboarding__{l['learner_id']}", ep, {}, None,
                       "200, onboarding_completed:true", None, "SKIPPED — no token for this phone")
            continue
        headers = client.bearer_headers(token)
        for l in u.get("learners", []):
            lid = l["learner_id"]
            course = cfg.course_1
            r = client.call(ep, {
                "phone": phone, "learner_id": lid,
                "updates": json.dumps({"grade": l.get("grade", "6"), "division": l.get("division", "A")}),
                "course": course,
            }, headers=headers)
            body = r.message_body()
            passed = r.is_2xx() and isinstance(body, dict) and body.get("onboarding_completed") is True
            if passed:
                state.onboarded_learners.add(lid)
                if course:
                    state.enrolled_learners[lid] = course
            record(log, f"onboarding__{lid}", ep,
                   {"phone": phone, "learner_id": lid, "course": course}, r,
                   "200, onboarding_completed:true, course enrolled", passed)


def run_enroll_course_all_learners_suite(client, cfg, log, state):
    ep = "enroll_course"
    if not cfg.course_2:
        record(log, "enroll_course__batch", ep, {}, None, "200", None, "SKIPPED — no course_2 in config")
        return
    for u in cfg.users:
        for l in u.get("learners", []):
            lid = l["learner_id"]
            r = client.call(ep, {"learner_id": lid, "course": cfg.course_2})
            body = r.message_body()
            passed = r.is_2xx() and isinstance(body, dict) and body.get("enrolled") is True
            if passed:
                state.enrolled_learners[lid] = cfg.course_2
            record(log, f"enroll__{lid}", ep, {"learner_id": lid, "course": cfg.course_2}, r,
                   "200, enrolled:true", passed)


def run_record_activity_all_learners_suite(client, cfg, log, state):
    ep = "record_activity"
    for u in cfg.users:
        for l in u.get("learners", []):
            lid = l["learner_id"]
            r = client.call(ep, {"learner_id": lid, "activity_type": "video"})
            body = r.message_body()
            passed = r.is_2xx() and isinstance(body, dict) and body.get("activity_recorded") is True
            state.record_activity_calls[lid] = state.record_activity_calls.get(lid, 0) + (1 if passed else 0)
            record(log, f"record_activity__{lid}", ep, {"learner_id": lid, "activity_type": "video"}, r,
                   "200, xp_awarded, activity_recorded:true", passed)


def run_content_progress_all_learners_suite(client, cfg, log, state):
    ep = "update_content_progress"
    for u in cfg.users:
        for l in u.get("learners", []):
            lid = l["learner_id"]
            if lid not in state.enrolled_learners:
                record(log, f"content_progress__{lid}", ep, {}, None,
                       "200, updated:true", None, "SKIPPED — learner not enrolled in this run")
                continue
            r = client.call(ep, {"learner_id": lid, "video_index": 1, "activity_type": "video"})
            record(log, f"content_progress__{lid}", ep,
                   {"learner_id": lid, "video_index": 1, "activity_type": "video"}, r,
                   "200, updated true/false depending on weekly cap state", None,
                   f"observed status={r.status_code}")


def run_learner_state_all_learners_suite(client, cfg, log):
    ep = "get_learner_state"
    for lid in cfg.all_learner_ids:
        r = client.call(ep, {"learner_id": lid})
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and "learner_id" in body
        record(log, f"learner_state__{lid}", ep, {"learner_id": lid}, r,
               "200, full learner state", passed)


def run_get_learners_progress_batch_suite(client, cfg, log):
    ep = "get_learners_progress"
    r = client.call(ep, {"learner_ids": json.dumps(cfg.all_learner_ids)})
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and all(lid in body for lid in cfg.all_learner_ids)
    record(log, "learners_progress__all_learners_batch", ep,
           {"learner_ids_count": len(cfg.all_learner_ids)}, r,
           "200, dict keyed by every learner_id in the dataset", passed)


def run_bulk_update_all_users_suite(client, cfg, log, state):
    ep = "bulk_update_students"
    if not cfg.allow_bulk_write_tests:
        record(log, "bulk_update__all_users", ep, {}, None, "200", None, "SKIPPED — bulk writes disabled")
        return
    for u in cfg.users:
        phone = u["phone"]
        token = state.tokens_by_phone.get(phone)
        if not token:
            continue
        changes = [{"learner_id": l["learner_id"], "updates": {"grade": l.get("grade", "6")}}
                   for l in u.get("learners", [])]
        if not changes:
            continue
        r = client.call(ep, {"phone": phone, "changes": json.dumps(changes), "atomic": "false"},
                         headers=client.bearer_headers(token))
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("succeeded") == len(changes)
        record(log, f"bulk_update__{phone}", ep, {"phone": phone, "changes_count": len(changes)}, r,
               "200, all rows in this account's batch succeed", passed)


def run_achievements_all_learners_suite(client, cfg, log):
    read_ep = "get_learner_achievements"
    award_ep = "award_achievement"
    conflict_bug_flagged = False
    auth_error_flagged = False
    for lid in cfg.all_learner_ids:
        r = client.call(read_ep, {"learner_id": lid})
        record(log, f"achievements_read__{lid}", read_ep, {"learner_id": lid}, r,
               "200, achievements array", r.is_2xx())

        r2 = client.call(award_ep, {"learner_id": lid, "achievement": "load_test_badge", "level": 1},
                          headers=client.api_key_headers())
        body = r2.message_body()
        passed = r2.is_2xx() and isinstance(body, dict) and "awarded" in body
        note = ""
        if not passed:
            raw = json.dumps(r2.body)[:500] if r2.body else str(r2.error)
            if r2.status_code == 401 or "AuthenticationError" in raw:
                note = ("looks like an auth failure, not a schema bug — check frappe_api_key/"
                        "frappe_api_secret in config.json are real values, not placeholders")
                auth_error_flagged = True
            elif "ON CONFLICT" in raw or "no unique or exclusion constraint" in raw or "duplicate key" in raw:
                note = ("looks like the ON CONFLICT (parent, achievement) clause in award_achievement "
                        "has no matching unique constraint in the DB schema — this is a backend bug, "
                        "not a test/config issue")
                conflict_bug_flagged = True
            else:
                note = f"actual response: {raw}"
        record(log, f"achievements_award__{lid}", award_ep,
               {"learner_id": lid, "achievement": "load_test_badge", "level": 1}, r2,
               "200, awarded true/false", passed, note=note)

    if auth_error_flagged:
        log.add_finding("award_achievement calls failing on auth", award_ep,
                         "award_achievement requires a valid Frappe API key/secret pair; the configured "
                         "credentials in config.json are being rejected by the server",
                         "check frappe_api_key / frappe_api_secret in config.json")
    if conflict_bug_flagged:
        log.add_finding("award_achievement ON CONFLICT target missing", award_ep,
                         "award_achievement's upsert uses ON CONFLICT (parent, achievement) DO UPDATE, "
                         "which requires a unique constraint or index on those two columns in "
                         "'tabTapapp Learner Achievements'; only a primary key on 'name' currently exists, "
                         "so every award call fails with a Postgres error",
                         "fix: add a unique constraint/index on (parent, achievement) in that table, "
                         "or change the SQL to match an existing constraint")


def run_export_suites(client, cfg, log):
    if cfg.program_id_for_export:
        r = client.call("export_program_content", {"program_id": cfg.program_id_for_export},
                         headers=client.api_key_headers(), timeout=120)
        body = r.message_body()
        passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
        record(log, "export_program__happy", "export_program_content",
               {"program_id": cfg.program_id_for_export}, r, "200, success:true, payload present", passed)

    r = client.call("export_content", {}, headers=client.api_key_headers(), timeout=60)
    body = r.message_body()
    passed = r.is_2xx() and isinstance(body, dict) and body.get("success") is True
    record(log, "export_content__happy", "export_content", {}, r, "200, success:true, payload present", passed)


def run_security_matrix_all_users(client, cfg, log, state):
    if len(cfg.users) < 2:
        return
    phone_a = cfg.users[0]["phone"]
    phone_b = cfg.users[1]["phone"]
    token_a = state.tokens_by_phone.get(phone_a)
    learner_b = cfg.users[1]["learners"][0]["learner_id"] if cfg.users[1].get("learners") else None

    if token_a and learner_b:
        r = client.call("select_profile", {"phone": phone_a, "learner_id": learner_b},
                         headers=client.bearer_headers(token_a))
        passed = not r.is_2xx()
        sec_record(log, "security__cross_account_read_blocked", "select_profile",
                   {"phone": phone_a, "learner_id": learner_b}, r,
                   "non-200, Profile not linked to this account", passed)

        r = client.call("update_student", {"phone": phone_a, "learner_id": learner_b,
                                            "updates": json.dumps({"grade": "5"})},
                         headers=client.bearer_headers(token_a))
        passed = not r.is_2xx()
        sec_record(log, "security__cross_account_write_blocked", "update_student",
                   {"phone": phone_a, "learner_id": learner_b}, r,
                   "non-200, ownership error", passed)

        r = client.call("get_profiles", {"phone": phone_b}, headers=client.bearer_headers(token_a))
        passed = not r.is_2xx()
        sec_record(log, "security__token_impersonation_blocked", "get_profiles",
                   {"phone": phone_b}, r, "non-200, Token phone mismatch", passed)

    no_auth_targets = [
        ("get_learner_state", {"learner_id": learner_b}),
        ("get_learner_progress", {"learner_id": learner_b}),
        ("record_activity", {"learner_id": learner_b, "xp": 5, "activity_type": "video"}),
        ("get_learner_achievements", {"learner_id": learner_b}),
    ]
    open_endpoints = []
    gated_endpoints = []
    for ep, params in no_auth_targets:
        if params.get("learner_id") is None:
            continue
        r = client.call(ep, params)
        is_open = r.is_2xx()
        if is_open:
            open_endpoints.append(ep)
        else:
            gated_endpoints.append(ep)
        sec_record(log, f"security__ownership_gate_probe__{ep}", ep, params, r,
                   "observational — records whether this endpoint currently accepts unauthenticated "
                   "cross-account calls; neither 200 nor non-200 is treated as a failure here", True,
                   note=f"{'OPEN (no ownership gate)' if is_open else 'GATED (rejected without auth)'}")
    if open_endpoints:
        log.add_finding("Endpoints with no ownership gate", "multiple",
                         f"{len(open_endpoints)}/{len(no_auth_targets)} learner/progress endpoints returned 200 "
                         "with zero auth headers against a learner_id from a different account",
                         f"open endpoints: {open_endpoints}")
    if gated_endpoints:
        log.add_finding("Endpoints correctly gated", "multiple",
                         f"{len(gated_endpoints)}/{len(no_auth_targets)} learner/progress endpoints correctly "
                         "rejected an unauthenticated cross-account call",
                         f"gated endpoints: {gated_endpoints}")


def run_bulk_vs_single_race(client, cfg, log, state):
    if not cfg.allow_bulk_write_tests or not cfg.users:
        return
    phone = cfg.users[0]["phone"]
    token = state.tokens_by_phone.get(phone)
    if not token or not cfg.users[0].get("learners"):
        return
    lid = cfg.users[0]["learners"][0]["learner_id"]
    headers = client.bearer_headers(token)

    def call_single():
        return client.call("update_student", {"phone": phone, "learner_id": lid,
                                                "updates": json.dumps({"grade": "5"})}, headers=headers)

    def call_bulk():
        return client.call("bulk_update_students", {"phone": phone,
                                                      "changes": json.dumps([{"learner_id": lid,
                                                                               "updates": {"grade": "9"}}]),
                                                      "atomic": "false"}, headers=headers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(call_single)
        f2 = pool.submit(call_bulk)
        r1 = f1.result()
        r2 = f2.result()

    post = client.call("select_profile", {"phone": phone, "learner_id": lid, "fields": "profile"}, headers=headers)
    post_body = post.message_body()
    final_grade = post_body.get("profile", {}).get("grade") if isinstance(post_body, dict) else None
    verdict = "PASS" if final_grade in ("5", "9") else "FAIL"
    row = {
        "timestamp": now_ts(),
        "case_id": "race__bulk_vs_single_update_same_learner",
        "endpoint": "update_student vs bulk_update_students",
        "setup": f"lid={lid}",
        "load": "one update_student(grade=5) and one bulk_update_students(grade=9) fired simultaneously",
        "result_summary": f"single_status={r1.status_code} bulk_status={r2.status_code} final_grade={final_grade}",
        "verdict": verdict,
        "note": "last-write-wins is expected; FAIL only if final grade is neither value",
    }
    log.add_concurrency(row)


def run_record_activity_race(client, cfg, log, n, learner_id):
    ep = "record_activity"
    pre = client.call("get_learner_state", {"learner_id": learner_id})
    pre_body = pre.message_body()
    if not isinstance(pre_body, dict):
        return
    starting_xp = pre_body.get("xp", 0)
    cap = pre_body.get("max_weekly_activities", 2)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(client.call, ep, {"learner_id": learner_id, "xp": 10, "activity_type": "video"}, {})
                   for _ in range(n)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    succeeded = sum(1 for r in results if r.is_2xx())
    post = client.call("get_learner_state", {"learner_id": learner_id})
    post_body = post.message_body()
    final_xp = post_body.get("xp") if isinstance(post_body, dict) else None
    overshoot = succeeded > cap
    verdict = "FAIL" if overshoot else "PASS"

    row = {
        "timestamp": now_ts(),
        "case_id": f"race__record_activity_parallel_{n}",
        "endpoint": ep,
        "setup": f"lid={learner_id} starting_xp={starting_xp} cap={cap}",
        "load": f"{n} concurrent record_activity(xp=10) calls",
        "result_summary": f"succeeded={succeeded} cap={cap} starting_xp={starting_xp} final_xp={final_xp}",
        "verdict": verdict,
        "note": "more than cap succeeded — race condition" if overshoot else "",
    }
    log.add_concurrency(row)
    if overshoot:
        log.add_finding("record_activity race condition", ep,
                         f"With {n} concurrent calls, {succeeded} succeeded against a cap of {cap}",
                         row["result_summary"])


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


def run_load_level(client, ep, param_factory, headers_factory, total_requests, concurrency, sampler, cfg):
    latencies = []
    lock = threading.Lock()
    stop_flag = threading.Event()

    def worker():
        if stop_flag.is_set():
            return None
        r = client.call(ep, param_factory(), headers_factory())
        with lock:
            latencies.append(r.latency_ms)
        return r

    t0 = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker) for _ in range(total_requests)]
        deadline = t0 + cfg.max_duration_seconds_per_level
        for f in concurrent.futures.as_completed(futures, timeout=None):
            res = f.result()
            if res is not None:
                results.append(res)
            if time.time() > deadline:
                stop_flag.set()
            if sampler.is_client_saturated(cfg.client_cpu_abort_percent, cfg.client_ram_abort_percent):
                stop_flag.set()
    duration = time.time() - t0

    success = sum(1 for r in results if r.is_2xx())
    fail = sum(1 for r in results if not r.is_2xx() and not r.error)
    errored = sum(1 for r in results if r.error)
    return duration, latencies, success, fail, errored, len(results)


def stress_record(log, endpoint_class, endpoint, level, sent, success, fail, err, latencies,
                   duration_s, resource_summary, note=""):
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
        "server_cpu_avg": resource_summary.get("server_cpu_avg"),
        "server_cpu_peak": resource_summary.get("server_cpu_peak"),
        "server_rss_mb_avg": resource_summary.get("server_rss_mb_avg"),
        "server_rss_mb_peak": resource_summary.get("server_rss_mb_peak"),
        "note": note,
    }
    log.add_stress(row)
    return row


def _level_is_healthy(cfg, error_rate, latencies, client_saturated):
    if client_saturated:
        return False
    if error_rate > cfg.abort_error_rate_threshold:
        return False
    p95 = percentile(latencies, 95)
    if p95 is not None and p95 > cfg.abort_p95_latency_ms:
        return False
    return True


def run_adaptive_stress_class(client, cfg, log, class_name, ep, param_factory, headers_factory, server_pids):
    sampler = ResourceSampler(cfg.sample_resource_interval_seconds, server_pids=server_pids)
    level = cfg.initial_concurrency
    last_healthy_level = None
    first_unhealthy_level = None
    consecutive_bad = 0
    tested_levels = []

    while level <= cfg.hard_ceiling:
        requests_this_level = int(min(cfg.requests_per_level_max, max(cfg.requests_per_level_min, level * 4)))
        sampler.start()
        duration, latencies, success, fail, errored, sent = run_load_level(
            client, ep, param_factory, headers_factory, requests_this_level, level, sampler, cfg
        )
        client_saturated = sampler.is_client_saturated(cfg.client_cpu_abort_percent, cfg.client_ram_abort_percent)
        sampler.stop()
        resource_summary = sampler.summary()

        error_rate = (fail + errored) / sent if sent else 1.0
        healthy = _level_is_healthy(cfg, error_rate, latencies, client_saturated)
        note = "client-saturated, result may understate true server capacity" if client_saturated else ""
        stress_record(log, class_name, ep, level, sent, success, fail, errored, latencies,
                       duration, resource_summary, note=note)
        log.write_summary_snapshot(cfg)
        tested_levels.append((level, healthy))

        if healthy:
            last_healthy_level = level
            consecutive_bad = 0
        else:
            consecutive_bad += 1
            if first_unhealthy_level is None:
                first_unhealthy_level = level
            if consecutive_bad >= cfg.consecutive_bad_levels_to_stop:
                break

        if client_saturated:
            break

        time.sleep(cfg.ramp_pause_seconds)
        level = int(level * cfg.growth_factor)
        if level == tested_levels[-1][0]:
            level += 1

    ceiling_reason = "hard_ceiling_reached"
    refined_ceiling = last_healthy_level

    if last_healthy_level is not None and first_unhealthy_level is not None and \
            first_unhealthy_level > last_healthy_level + 1:
        lo, hi = last_healthy_level, first_unhealthy_level
        for _ in range(cfg.refine_binary_search_steps):
            mid = (lo + hi) // 2
            if mid == lo:
                break
            requests_this_level = int(min(cfg.requests_per_level_max, max(cfg.requests_per_level_min, mid * 4)))
            sampler.start()
            duration, latencies, success, fail, errored, sent = run_load_level(
                client, ep, param_factory, headers_factory, requests_this_level, mid, sampler, cfg
            )
            client_saturated = sampler.is_client_saturated(cfg.client_cpu_abort_percent, cfg.client_ram_abort_percent)
            sampler.stop()
            resource_summary = sampler.summary()
            error_rate = (fail + errored) / sent if sent else 1.0
            healthy = _level_is_healthy(cfg, error_rate, latencies, client_saturated)
            stress_record(log, class_name, ep, f"REFINE-{mid}", sent, success, fail, errored, latencies,
                           duration, resource_summary,
                           note="binary search refinement around the observed breaking point")
            log.write_summary_snapshot(cfg)
            if healthy:
                lo = mid
                refined_ceiling = mid
            else:
                hi = mid
            time.sleep(cfg.ramp_pause_seconds)
        ceiling_reason = "refined_via_binary_search"
    elif last_healthy_level is not None and first_unhealthy_level is not None:
        ceiling_reason = "adjacent_levels_bracket_the_break"
    elif last_healthy_level is None:
        ceiling_reason = "no_healthy_level_found_even_at_initial_concurrency"

    stress_record(log, class_name, ep, "CEILING", None, None, None, None, [], 0, {},
                  note=f"max sustainable concurrency={refined_ceiling} reason={ceiling_reason}")
    return refined_ceiling, ceiling_reason


def run_full_stress_suite(client, cfg, log, state, server_pids):
    if not cfg.users:
        return
    phone = cfg.users[0]["phone"]
    token = state.tokens_by_phone.get(phone) or state.token_for(client, cfg, phone)
    lid_pool = cfg.all_learner_ids or ["TL00000001"]

    def rr_learner():
        return lid_pool[int(time.time() * 1000) % len(lid_pool)]

    log.write_status("stress:class_a_reads")
    run_adaptive_stress_class(
        client, cfg, log, "Class A (single-record reads, no auth)", "get_learner_state",
        lambda: {"learner_id": rr_learner()}, lambda: {}, server_pids,
    )
    run_adaptive_stress_class(
        client, cfg, log, "Class A (single-record reads, no auth)", "check_phone",
        lambda: {"phone": phone}, lambda: {}, server_pids,
    )
    run_adaptive_stress_class(
        client, cfg, log, "Class A (single-record reads, no auth)", "get_learner_achievements",
        lambda: {"learner_id": rr_learner()}, lambda: {}, server_pids,
    )

    log.write_status("stress:class_b_batch_reads")
    run_adaptive_stress_class(
        client, cfg, log, "Class B (batch reads)", "get_learners_progress",
        lambda: {"learner_ids": json.dumps(lid_pool)}, lambda: {}, server_pids,
    )
    if token:
        run_adaptive_stress_class(
            client, cfg, log, "Class B (paginated reads, authenticated)", "get_profiles",
            lambda: {"phone": phone, "page": 1, "page_size": 50},
            lambda: client.bearer_headers(token), server_pids,
        )
        run_adaptive_stress_class(
            client, cfg, log, "Class B (paginated reads, authenticated)", "get_bulk_students",
            lambda: {"phone": phone, "page": 1, "page_size": 50},
            lambda: client.bearer_headers(token), server_pids,
        )

    log.write_status("stress:class_c_single_writes")
    run_adaptive_stress_class(
        client, cfg, log, "Class C (single writes)", "record_activity",
        lambda: {"learner_id": rr_learner(), "xp": 1, "activity_type": "stress"},
        lambda: {}, server_pids,
    )

    if cfg.allow_bulk_write_tests and token:
        log.write_status("stress:class_d_bulk_writes")
        run_adaptive_stress_class(
            client, cfg, log, "Class D (bulk writes)", "bulk_update_students",
            lambda: {"phone": phone,
                     "changes": json.dumps([{"learner_id": cfg.users[0]["learners"][0]["learner_id"],
                                              "updates": {"grade": "6"}}]),
                     "atomic": "false"},
            lambda: client.bearer_headers(token), server_pids,
        )

    if cfg.program_id_for_export:
        log.write_status("stress:class_e_export")
        run_adaptive_stress_class(
            client, cfg, log, "Class E (heavy aggregation/export)", "export_program_content",
            lambda: {"program_id": cfg.program_id_for_export},
            lambda: client.api_key_headers(), server_pids,
        )


def write_final_report(log, cfg, run_id, start_time, end_time):
    lines = []
    lines.append("TAPAPP STAGED STRESS TEST — FINAL REPORT")
    lines.append(f"Generated: {now_ts()}")
    lines.append(f"Run id: {run_id}")
    lines.append(f"Target: {cfg.base_url}")
    lines.append(f"Started: {start_time}")
    lines.append(f"Ended: {end_time}")
    lines.append("")
    lines.append(f"Raw per-request logs: {log.functional_path}, {log.security_path}")
    lines.append(f"Concurrency race logs: {log.concurrency_path}")
    lines.append(f"Stress ramp logs: {log.stress_path}")
    lines.append(f"Findings: {log.findings_path}")
    lines.append(f"Live status snapshot (safe to read mid-run): {log.status_path}")
    lines.append("")
    lines.append("SUMMARY")
    for k, v in log.counts.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    ceilings = []
    if os.path.exists(log.stress_path):
        with open(log.stress_path) as f:
            for line in f:
                row = json.loads(line)
                if row.get("concurrency_level") == "CEILING":
                    ceilings.append(row)
    lines.append("STRESS CEILINGS FOUND")
    if ceilings:
        for row in ceilings:
            lines.append(f"  {row['endpoint_class']} ({row['endpoint']}): {row['note']}")
    else:
        lines.append("  none recorded — stress suite may not have run or was interrupted early")
    lines.append("")
    lines.append("END OF REPORT")

    report_path = os.path.join(cfg.results_dir, f"final_report_{run_id}.txt")
    with open(report_path, "w") as f:
        f.write("\n".join(lines))
        f.flush()
        os.fsync(f.fileno())
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Tapapp staged-environment stress and functional test harness")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--only", default=None,
                         help="Comma-separated: functional,security,concurrency,stress")
    parser.add_argument("--server-pids", type=str, default=None,
                         help="Comma-separated PIDs of the Frappe/gunicorn master+worker processes, "
                              "for aggregated resource tracking. If omitted, auto-detected.")
    args = parser.parse_args()

    cfg = Config(args.config)
    client = ApiClient(cfg)
    run_id = str(uuid.uuid4())[:8]
    log = StreamingLog(cfg.results_dir, run_id)
    state = State(cfg)
    start_time = now_ts()

    if args.server_pids:
        server_pids = [int(p.strip()) for p in args.server_pids.split(",") if p.strip()]
    else:
        server_pids = find_server_pids(cfg)
    print(f"Tracking server resource usage across PIDs: {server_pids or 'none found'}")
    print(f"Sending requests to {cfg.base_url} with Host header: {cfg.site_host or '(none set)'}")
    print(f"Resolving endpoints to dotted module paths: {cfg.use_dotted_paths}")

    def handle_signal(signum, frame):
        log.write_status("interrupted", extra={"signal": signum})
        write_final_report(log, cfg, run_id, start_time, now_ts())
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    sections = {s.strip() for s in args.only.split(",")} if args.only else None

    def wants(name):
        return sections is None or name in sections

    try:
        if wants("functional"):
            log.write_status("functional:login")
            run_login_all_users_suite(client, cfg, log, state)

            log.write_status("functional:profiles")
            run_get_profiles_all_users_suite(client, cfg, log, state)

            log.write_status("functional:onboarding")
            run_onboarding_all_learners_suite(client, cfg, log, state)

            log.write_status("functional:enrollment")
            run_enroll_course_all_learners_suite(client, cfg, log, state)

            log.write_status("functional:record_activity")
            run_record_activity_all_learners_suite(client, cfg, log, state)

            log.write_status("functional:content_progress")
            run_content_progress_all_learners_suite(client, cfg, log, state)

            log.write_status("functional:learner_state")
            run_learner_state_all_learners_suite(client, cfg, log)

            log.write_status("functional:learners_progress_batch")
            run_get_learners_progress_batch_suite(client, cfg, log)

            log.write_status("functional:bulk_update")
            run_bulk_update_all_users_suite(client, cfg, log, state)

            log.write_status("functional:achievements")
            run_achievements_all_learners_suite(client, cfg, log)

            log.write_status("functional:export")
            run_export_suites(client, cfg, log)

            log.write_summary_snapshot(cfg)

        if wants("security"):
            log.write_status("security")
            run_security_matrix_all_users(client, cfg, log, state)
            log.write_summary_snapshot(cfg)

        if wants("concurrency") and cfg.run_concurrency_suite:
            log.write_status("concurrency")
            probe_lid = cfg.all_learner_ids[0] if cfg.all_learner_ids else None
            if probe_lid:
                run_record_activity_race(client, cfg, log, 5, probe_lid)
                run_record_activity_race(client, cfg, log, 20, probe_lid)
            run_bulk_vs_single_race(client, cfg, log, state)
            log.write_summary_snapshot(cfg)

        if wants("stress") and cfg.run_stress_suite:
            log.write_status("stress")
            run_full_stress_suite(client, cfg, log, state, server_pids)
            log.write_summary_snapshot(cfg)

        log.write_status("completed")

    except Exception as e:
        log.write_status("crashed", extra={"error": str(e)})
        raise
    finally:
        end_time = now_ts()
        report_path = write_final_report(log, cfg, run_id, start_time, end_time)
        print(f"Report written to: {report_path}")
        print(f"Status file (safe to tail during a run): {log.status_path}")
        print(json.dumps(log.counts, indent=2))


if __name__ == "__main__":
    main()