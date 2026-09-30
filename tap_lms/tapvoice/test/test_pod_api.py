import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.api import pod as pod_api
from tap_lms.tapvoice.constants import (
    RUN_DOCTYPE,
    STATUS_COMPLETED,
    STATUS_RUNNING,
    STATUS_STARTING,
)
from tap_lms.tapvoice.lib import contract, tokens
from tap_lms.tapvoice.lib.secrets import SECRETS_DOCTYPE

SHARED_SECRET = "test-shared-secret-value"


class PodApiTestBase(FrappeTestCase):
    def setUp(self):
        self._ensure_secret()
        self.run_doc = self._make_run()
        self._patch_request(self.run_doc.name, self._issue_token(self.run_doc.name))

    def tearDown(self):
        frappe.local.request = None
        frappe.db.rollback()

    def _ensure_secret(self):
        if not frappe.db.exists(SECRETS_DOCTYPE, "tts_pod_shared_secret"):
            doc = frappe.get_doc(
                {
                    "doctype": SECRETS_DOCTYPE,
                    "key": "tts_pod_shared_secret",
                    "value": SHARED_SECRET,
                    "enabled": 1,
                }
            )
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

    def _issue_token(self, run_name):
        return tokens.issue(run_name, SHARED_SECRET, 60)

    def _make_run(self, status=STATUS_STARTING, manifest_items=None):
        manifest_items = manifest_items if manifest_items is not None else []
        doc = frappe.get_doc(
            {
                "doctype": RUN_DOCTYPE,
                "status": status,
                "trigger_type": "Manual",
                "triggered_by": "Administrator",
                "created_at": frappe.utils.now_datetime(),
                "manifest_json": frappe.as_json(manifest_items),
                "manifest_count": len(manifest_items),
                "termination_status": "Not Needed",
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    def _patch_request(self, run_id, token, method="POST", body=None):
        class FakeRequest:
            def __init__(self):
                self.method = method
                self.content_length = 10

        class FakeLocal:
            def __init__(self):
                self.request_ip = "127.0.0.1"
                self.response = frappe._dict()
                self.form_dict = frappe._dict(body or {})

        frappe.request = FakeRequest()
        frappe.local.request = frappe.request
        frappe.local.request_ip = "127.0.0.1"
        frappe.local.response = frappe._dict()
        frappe.local.form_dict = frappe._dict(body or {})
        frappe.local.request_headers = {"X-Run-Id": run_id, "X-Run-Token": token}

        original_get_header = frappe.get_request_header

        def fake_get_request_header(name, default=None):
            return frappe.local.request_headers.get(name, default)

        frappe.get_request_header = fake_get_request_header
        self.addCleanup(lambda: setattr(frappe, "get_request_header", original_get_header))


class TestManifestEndpoint(PodApiTestBase):
    def test_generic_401_on_bad_token(self):
        self._patch_request(self.run_doc.name, "garbage-token")
        result = pod_api.manifest()
        self.assertEqual(frappe.local.response.http_status_code, 401)
        self.assertEqual(result["error"], "unauthorized")

    def test_409_when_terminal(self):
        run = self._make_run(status=STATUS_COMPLETED)
        self._patch_request(run.name, self._issue_token(run.name))
        result = pod_api.manifest()
        self.assertEqual(frappe.local.response.http_status_code, 409)

    def test_empty_manifest_returns_empty_items(self):
        result = pod_api.manifest()
        self.assertEqual(result["items"], [])

    def test_manifest_moves_starting_to_running(self):
        pod_api.manifest()
        status = frappe.db.get_value(RUN_DOCTYPE, self.run_doc.name, "status")
        self.assertEqual(status, STATUS_RUNNING)


class TestProgressEndpoint(PodApiTestBase):
    def _make_submission(self, language="english", text="Hello world test"):
        doc = frappe.get_doc(
            {
                "doctype": "Submission",
                "status": "Completed",
                "overall_feedback_translated": text,
                "translation_language": language,
                "audio_feedback_url": "",
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    def test_not_in_manifest_outcome(self):
        self._patch_request(
            self.run_doc.name,
            self._issue_token(self.run_doc.name),
            body={"records": [{"id": "not-real", "status": "done", "url": "x", "content_hash": "x"}]},
        )
        result = pod_api.progress()
        self.assertEqual(result["results"][0]["outcome"], "not_in_manifest")

    def test_written_outcome_on_valid_record(self):
        settings = frappe.get_single("Tap Voice Settings")
        settings.cdn_base_url = "https://cdn.example.com"
        settings.gcs_prefix = "tts"
        settings.model_revision = "rev1"
        settings.verify_urls_on_write = 0
        settings.save(ignore_permissions=True)
        frappe.db.commit()

        sub = self._make_submission()
        from tap_lms.tapvoice.lib.text import prepare as prepare_text

        prepared = prepare_text(sub.overall_feedback_translated, sub.translation_language, 300, "truncate")
        manifest_items = [
            {"id": sub.name, "language": prepared.language, "fingerprint": prepared.fingerprint, "text": prepared.text}
        ]
        run = self._make_run(status=STATUS_RUNNING, manifest_items=manifest_items)
        self._patch_request(run.name, self._issue_token(run.name))

        expected_hash = contract.expected_hash(prepared.text, prepared.language, "rev1")
        expected_url = contract.expected_url(prepared.text, prepared.language, "rev1", "tts", "https://cdn.example.com")

        self._patch_request(
            run.name,
            self._issue_token(run.name),
            body={
                "records": [
                    {"id": sub.name, "status": "done", "url": expected_url, "content_hash": expected_hash}
                ]
            },
        )
        result = pod_api.progress()
        self.assertEqual(result["results"][0]["outcome"], "written")
        refreshed = frappe.db.get_value("Submission", sub.name, "audio_feedback_url")
        self.assertEqual(refreshed, expected_url)

    def test_hash_mismatch_does_not_write(self):
        sub = self._make_submission()
        from tap_lms.tapvoice.lib.text import prepare as prepare_text

        prepared = prepare_text(sub.overall_feedback_translated, sub.translation_language, 300, "truncate")
        manifest_items = [
            {"id": sub.name, "language": prepared.language, "fingerprint": prepared.fingerprint, "text": prepared.text}
        ]
        run = self._make_run(status=STATUS_RUNNING, manifest_items=manifest_items)
        self._patch_request(
            run.name,
            self._issue_token(run.name),
            body={"records": [{"id": sub.name, "status": "done", "url": "https://x/y.ogg", "content_hash": "wronghash"}]},
        )
        result = pod_api.progress()
        self.assertEqual(result["results"][0]["outcome"], "hash_mismatch")
        refreshed = frappe.db.get_value("Submission", sub.name, "audio_feedback_url")
        self.assertFalse(refreshed)

    def test_recorded_failure_does_not_touch_submission(self):
        sub = self._make_submission()
        manifest_items = [{"id": sub.name, "language": "english", "fingerprint": "fp", "text": "Hello"}]
        run = self._make_run(status=STATUS_RUNNING, manifest_items=manifest_items)
        self._patch_request(
            run.name,
            self._issue_token(run.name),
            body={"records": [{"id": sub.name, "status": "failed", "error": "silent"}]},
        )
        result = pod_api.progress()
        self.assertEqual(result["results"][0]["outcome"], "recorded_failure")


class TestBeatEndpoint(PodApiTestBase):
    def test_beat_moves_starting_to_running(self):
        self._patch_request(self.run_doc.name, self._issue_token(self.run_doc.name), body={"phase": "generating", "remaining": 5})
        result = pod_api.beat()
        self.assertFalse(result["stop"])
        status = frappe.db.get_value(RUN_DOCTYPE, self.run_doc.name, "status")
        self.assertEqual(status, STATUS_RUNNING)

    def test_beat_signals_stop_when_disabled(self):
        settings = frappe.get_single("Tap Voice Settings")
        settings.enabled = 0
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        self._patch_request(self.run_doc.name, self._issue_token(self.run_doc.name), body={"phase": "generating", "remaining": 5})
        result = pod_api.beat()
        self.assertTrue(result["stop"])


class TestCompleteEndpoint(PodApiTestBase):
    def test_complete_is_idempotent(self):
        run = self._make_run(status=STATUS_RUNNING)
        self._patch_request(run.name, self._issue_token(run.name), body={"reason": "completed", "gpu_seconds": 10, "stats": {}})
        first = pod_api.complete()
        self.assertTrue(first["accepted"])
        status = frappe.db.get_value(RUN_DOCTYPE, run.name, "status")
        self.assertEqual(status, STATUS_COMPLETED)

    def test_complete_maps_timeout(self):
        run = self._make_run(status=STATUS_RUNNING)
        self._patch_request(run.name, self._issue_token(run.name), body={"reason": "timeout", "gpu_seconds": 10, "stats": {}})
        pod_api.complete()
        status = frappe.db.get_value(RUN_DOCTYPE, run.name, "status")
        self.assertEqual(status, "Timed Out")

    def test_complete_maps_breaker_reason_to_failed(self):
        run = self._make_run(status=STATUS_RUNNING)
        self._patch_request(
            run.name, self._issue_token(run.name), body={"reason": "breaker_idle_timeout", "gpu_seconds": 10, "stats": {}}
        )
        pod_api.complete()
        status = frappe.db.get_value(RUN_DOCTYPE, run.name, "status")
        self.assertEqual(status, "Failed")
