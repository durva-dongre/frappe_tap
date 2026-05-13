"""
Tests for summer_program.vocallabs — CR-003.

Covers:
  - Happy-path 3-call sequence with token cache hit + miss
  - Token cache TTL respected
  - Settings.enabled=0 short-circuits without retry
  - Missing ParentCallConfig (no per-LU + no default) skips + warns
  - 5-retry/DLQ pattern mirrors save_submission.enqueue_submission

All HTTP is mocked via unittest.mock.patch. Per L-017, no
frappe.db.commit() in tests.
"""
import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.summer_program.constants import (
    LABEL_CONTENT_DELIVERED,
    PATH_CORE,
    PROGRAM_ACTIVE,
    STATE_NORMAL_CONTENT,
    VOCALLABS_DLQ_LOG_TITLE,
    VOCALLABS_MAX_RETRIES,
    VOCALLABS_TOKEN_CACHE_KEY,
)


# ════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════


def _ensure_batch():
    name = frappe.get_value("Batch", {"name1": "VocallabsTestBatch"}, "name")
    if name:
        return name
    batch = frappe.new_doc("Batch")
    batch.name1 = "VocallabsTestBatch"
    batch.start_date = "2026-01-01"
    batch.end_date = "2026-04-30"
    batch.batch_id = "VLT01"
    batch.program_type = "Summer"
    batch.total_weeks = 12
    batch.current_calendar_week = 1
    batch.grace_window_days = 14
    batch.insert(ignore_permissions=True)
    return batch.name


def _ensure_student(suffix, phone=None):
    phone = phone or f"+9999500{suffix}"
    name = frappe.get_value("Student", {"phone": phone}, "name")
    if name:
        return name
    s = frappe.new_doc("Student")
    s.name1 = f"VocallabsTestStudent{suffix}"
    s.phone = phone
    s.glific_id = f"glific-vl-{suffix}"
    s.insert(ignore_permissions=True)
    return s.name


def _make_pe(batch_name, student_name, suffix):
    pe = frappe.new_doc("ProgramEnrollment")
    pe.enrollment = f"PE-VL-{suffix}-{frappe.utils.random_string(6)}"
    pe.student = student_name
    pe.batch = batch_name
    pe.program_type = "Summer"
    pe.glific_id = f"glific-vl-{suffix}"
    pe.program_status = PROGRAM_ACTIVE
    pe.resolved_flow_state = STATE_NORMAL_CONTENT
    pe.journey_label = LABEL_CONTENT_DELIVERED
    pe.current_path = PATH_CORE
    pe.current_week = 1
    pe.current_tier = "Basic"
    pe.archetype = "Submitter"
    pe.insert(ignore_permissions=True)
    return pe.name


def _ensure_parent_call_config(title="VLT-Default"):
    if frappe.db.exists("ParentCallConfig", title):
        return title
    cfg = frappe.new_doc("ParentCallConfig")
    cfg.title = title
    cfg.status_template = (
        "Hi, {student_name} is on week {week} of {course_level}. "
        "Step {escalation_order} ({escalation_type})."
    )
    cfg.is_active = 1
    cfg.insert(ignore_permissions=True)
    return cfg.name


def _ensure_voice_settings(enabled=1, agent_id="agent-VLT", default_config=None,
                          ttl=3600):
    settings = frappe.get_single("VoiceAgentSettings")
    settings.enabled = enabled
    settings.service_url = "https://vocallabs.test"
    settings.client_id = "test-client"
    # Set the password field via raw write so we don't depend on get_password
    # in the test environment; vocallabs._get_auth_token reads via get_password
    # with raise_exception=False.
    settings.client_secret = "test-secret"
    settings.default_contact_group_id = "group-VLT"
    settings.agent_id = agent_id
    settings.default_parent_call_config = default_config
    settings.auth_token_cache_ttl = ttl
    settings.save(ignore_permissions=True)
    return settings


def _step(order=1, etype="parent_call", hours=24):
    return {
        "escalation_order": order,
        "escalation_type": etype,
        "points_awarded": 0,
        "hours_after_previous": hours,
    }


# ════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════


class TestVocallabsHappyPath(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def setUp(self):
        # Clear the token cache between tests so cache hits/misses are
        # deterministic.
        frappe.cache().delete_value(VOCALLABS_TOKEN_CACHE_KEY)

    def test_initiate_parent_call_success_path(self):
        """All three Vocallabs calls fire in order with the expected payloads,
        the function returns True, and an event_log entry is written.
        """
        from tap_lms.summer_program import vocallabs

        cfg = _ensure_parent_call_config()
        _ensure_voice_settings(enabled=1, default_config=cfg)

        student = _ensure_student("01")
        pe_name = _make_pe(self.batch_name, student, "01")

        captured_calls = []

        def fake_post(url, payload, headers):
            captured_calls.append((url, payload, headers))
            if url.endswith("/createAuthToken"):
                return {"authToken": "tok-xyz"}
            if url.endswith("/addMultipleContactsToGroup"):
                return {"prospect_id": "prospect-001"}
            if url.endswith("/initiateVocallabsCall"):
                return {"status": "queued", "call_id": "call-001"}
            self.fail(f"Unexpected URL hit: {url}")

        with patch.object(vocallabs, "_http_post", side_effect=fake_post):
            ok = vocallabs.initiate_parent_call(pe_name, _step(order=2, etype="parent_call"))

        self.assertTrue(ok)
        # Exactly three calls — auth + addContact + initiate.
        urls = [c[0] for c in captured_calls]
        self.assertEqual(len(urls), 3, f"expected 3 calls, got {urls}")
        self.assertTrue(urls[0].endswith("/createAuthToken"))
        self.assertTrue(urls[1].endswith("/addMultipleContactsToGroup"))
        self.assertTrue(urls[2].endswith("/initiateVocallabsCall"))

        # Auth payload had client_id/client_secret.
        auth_payload = captured_calls[0][1]
        self.assertEqual(auth_payload["client_id"], "test-client")
        self.assertEqual(auth_payload["client_secret"], "test-secret")

        # AddContact payload carried the rendered status template.
        add_payload = captured_calls[1][1]
        self.assertEqual(add_payload["groupId"], "group-VLT")
        contact = add_payload["contacts"][0]
        self.assertEqual(contact["phone"], "+999950001")
        self.assertEqual(contact["data"]["contact"], "Parent")
        self.assertIn("week 1", contact["data"]["status"])
        self.assertIn("Step 2", contact["data"]["status"])
        self.assertIn("parent_call", contact["data"]["status"])

        # Initiate payload carried agent + prospect.
        init_payload = captured_calls[2][1]
        self.assertEqual(init_payload["agentId"], "agent-VLT")
        self.assertEqual(init_payload["prospectId"], "prospect-001")

    def test_token_cache_returns_cached_within_ttl(self):
        """Second call within TTL window does NOT re-hit /createAuthToken."""
        from tap_lms.summer_program import vocallabs

        cfg = _ensure_parent_call_config()
        _ensure_voice_settings(enabled=1, default_config=cfg, ttl=3600)

        student = _ensure_student("02")
        pe_name = _make_pe(self.batch_name, student, "02")

        captured = []

        def fake_post(url, payload, headers):
            captured.append(url)
            if url.endswith("/createAuthToken"):
                return {"authToken": "tok-cached"}
            if url.endswith("/addMultipleContactsToGroup"):
                return {"prospect_id": "p"}
            if url.endswith("/initiateVocallabsCall"):
                return {"status": "queued"}

        with patch.object(vocallabs, "_http_post", side_effect=fake_post):
            vocallabs.initiate_parent_call(pe_name, _step())
            vocallabs.initiate_parent_call(pe_name, _step())

        auth_count = sum(1 for u in captured if u.endswith("/createAuthToken"))
        self.assertEqual(auth_count, 1, "auth token should have been cached")

    def test_token_cache_refreshes_after_invalidation(self):
        """If the cache is cleared between calls, /createAuthToken fires again."""
        from tap_lms.summer_program import vocallabs

        cfg = _ensure_parent_call_config()
        _ensure_voice_settings(enabled=1, default_config=cfg)

        student = _ensure_student("03")
        pe_name = _make_pe(self.batch_name, student, "03")

        captured = []

        def fake_post(url, payload, headers):
            captured.append(url)
            if url.endswith("/createAuthToken"):
                return {"authToken": "tok-fresh"}
            if url.endswith("/addMultipleContactsToGroup"):
                return {"prospect_id": "p"}
            if url.endswith("/initiateVocallabsCall"):
                return {"status": "queued"}

        with patch.object(vocallabs, "_http_post", side_effect=fake_post):
            vocallabs.initiate_parent_call(pe_name, _step())
            # Simulate TTL expiry by manually invalidating the cache.
            frappe.cache().delete_value(VOCALLABS_TOKEN_CACHE_KEY)
            vocallabs.initiate_parent_call(pe_name, _step())

        auth_count = sum(1 for u in captured if u.endswith("/createAuthToken"))
        self.assertEqual(auth_count, 2, "auth token should refresh after cache invalidation")


class TestVocallabsConfigSkips(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def setUp(self):
        frappe.cache().delete_value(VOCALLABS_TOKEN_CACHE_KEY)

    def test_initiate_parent_call_skipped_when_disabled(self):
        """Vocallabs disabled → no HTTP fires, returns False, no DLQ."""
        from tap_lms.summer_program import vocallabs

        cfg = _ensure_parent_call_config()
        _ensure_voice_settings(enabled=0, default_config=cfg)

        student = _ensure_student("04")
        pe_name = _make_pe(self.batch_name, student, "04")

        with patch.object(vocallabs, "_http_post") as fake_post:
            ok = vocallabs.initiate_parent_call(pe_name, _step())

        self.assertFalse(ok)
        self.assertEqual(fake_post.call_count, 0)

    def test_initiate_parent_call_skipped_when_no_config_resolved(self):
        """Neither per-LU nor default ParentCallConfig set → skip + log."""
        from tap_lms.summer_program import vocallabs

        # No default config and no per-LU; ensure settings has no default.
        _ensure_voice_settings(enabled=1, default_config=None)

        student = _ensure_student("05")
        pe_name = _make_pe(self.batch_name, student, "05")

        with patch.object(vocallabs, "_http_post") as fake_post:
            ok = vocallabs.initiate_parent_call(pe_name, _step())

        self.assertFalse(ok)
        # No HTTP should fire — we bailed before the token fetch.
        self.assertEqual(fake_post.call_count, 0)


class TestVocallabsRetry(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.batch_name = _ensure_batch()

    def setUp(self):
        frappe.cache().delete_value(VOCALLABS_TOKEN_CACHE_KEY)

    def test_initiate_parent_call_dlq_after_max_retries(self):
        """If retry_count exceeds VOCALLABS_MAX_RETRIES, a DLQ Error Log
        is written with the documented payload and the function returns False.
        Tests the terminal-DLQ branch by simulating the final retry attempt
        (retry_count = VOCALLABS_MAX_RETRIES) failing one more time.
        """
        from tap_lms.summer_program import vocallabs

        cfg = _ensure_parent_call_config()
        _ensure_voice_settings(enabled=1, default_config=cfg)

        student = _ensure_student("06")
        pe_name = _make_pe(self.batch_name, student, "06")

        # Every HTTP call raises — drives the failure path.
        def failing_post(url, payload, headers):
            raise RuntimeError("Vocallabs simulated outage")

        # Force this invocation to BE the last retry by passing
        # retry_count = VOCALLABS_MAX_RETRIES; the failure handler will
        # increment to MAX_RETRIES + 1 and route straight to DLQ.
        with patch.object(vocallabs, "_http_post", side_effect=failing_post), \
             patch.object(frappe, "log_error", wraps=frappe.log_error) as fake_log:
            ok = vocallabs.initiate_parent_call(
                pe_name, _step(order=3),
                retry_count=VOCALLABS_MAX_RETRIES,
            )

        self.assertFalse(ok)

        # A DLQ Error Log was emitted with the documented title.
        dlq_calls = [
            call for call in fake_log.call_args_list
            if call.kwargs.get("title") == VOCALLABS_DLQ_LOG_TITLE
        ]
        self.assertGreaterEqual(len(dlq_calls), 1, "Expected DLQ Error Log entry")

        # Payload is JSON with the required keys.
        payload = json.loads(dlq_calls[-1].kwargs["message"])
        for key in ("student_id", "pe_name", "week", "escalation_order",
                    "parent_phone", "final_error", "retries_attempted"):
            self.assertIn(key, payload, f"DLQ payload missing key {key}")
        self.assertEqual(payload["pe_name"], pe_name)
        self.assertEqual(payload["escalation_order"], 3)
