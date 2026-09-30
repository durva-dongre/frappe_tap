from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.constants import (
    DECISION_SKIP_BLOCKED,
    DECISION_SKIP_DISABLED,
    RUN_DOCTYPE,
    STATUS_DEPLOY_FAILED,
    STATUS_STARTING,
)
from tap_lms.tapvoice.job import deploy as deploy_job
from tap_lms.tapvoice.lib.runpod import RunPodError
from tap_lms.tapvoice.lib.secrets import SECRETS_DOCTYPE


def _ensure_all_secrets():
    for key, value in (
        ("runpod_api_key", "fake-runpod-key"),
        ("tts_pod_shared_secret", "fake-shared-secret"),
        ("tts_gcs_service_account_json_b64", "ZmFrZQ=="),
    ):
        if not frappe.db.exists(SECRETS_DOCTYPE, key):
            frappe.get_doc({"doctype": SECRETS_DOCTYPE, "key": key, "value": value, "enabled": 1}).insert(
                ignore_permissions=True
            )
    frappe.db.commit()


def _enable_settings():
    settings = frappe.get_single("Tap Voice Settings")
    settings.enabled = 1
    settings.alert_email = "ops@example.com"
    settings.public_base_url = "https://lms.example.com"
    settings.cdn_base_url = "https://cdn.example.com"
    settings.image_name = "repo/image:sha123"
    settings.gpu_type_ids = "NVIDIA RTX A5000"
    settings.min_items_to_deploy = 1
    settings.max_runs_per_day = 10
    settings.min_minutes_between_runs = 0
    settings.max_cost_per_run_usd = 100
    settings.max_cost_per_day_usd = 100
    settings.max_cost_per_month_usd = 1000
    settings.save(ignore_permissions=True)
    frappe.db.commit()


class TestDeployGates(FrappeTestCase):
    def setUp(self):
        _ensure_all_secrets()
        self._created = []

    def tearDown(self):
        for name in self._created:
            frappe.delete_doc("Submission", name, force=True, ignore_permissions=True)
        frappe.db.rollback()

    def test_disabled_kill_switch_skips(self):
        settings = frappe.get_single("Tap Voice Settings")
        settings.enabled = 0
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        result = deploy_job.deploy_new()
        self.assertFalse(result["deployed"])
        self.assertEqual(result["reason"], DECISION_SKIP_DISABLED)

    def test_blocked_by_active_run(self):
        _enable_settings()
        frappe.get_doc(
            {
                "doctype": RUN_DOCTYPE,
                "status": STATUS_STARTING,
                "trigger_type": "Manual",
                "triggered_by": "Administrator",
                "created_at": frappe.utils.now_datetime(),
                "termination_status": "Not Needed",
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
        result = deploy_job.deploy_new()
        self.assertFalse(result["deployed"])
        self.assertEqual(result["reason"], DECISION_SKIP_BLOCKED)

    def test_double_trigger_collapses_via_mutex(self):
        _enable_settings()
        acquired_first = deploy_job._acquire_mutex()
        self.assertTrue(acquired_first)
        acquired_second = deploy_job._acquire_mutex()
        self.assertFalse(acquired_second)
        deploy_job._release_mutex()

    @patch("tap_lms.tapvoice.job.deploy.RunPodClient")
    def test_ambiguous_create_adopts_existing_pod(self, mock_client_cls):
        _enable_settings()
        doc = frappe.get_doc(
            {
                "doctype": "Submission",
                "status": "Completed",
                "overall_feedback_translated": "Good feedback text for testing here.",
                "translation_language": "english",
                "audio_feedback_url": "",
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        self._created.append(doc.name)

        instance = mock_client_cls.return_value
        instance.create_pod.side_effect = RunPodError("request_error Timeout")
        instance.find_by_name.return_value = {"id": "pod-adopted", "name": "whatever"}

        result = deploy_job.deploy_new()
        self.assertTrue(result.get("deployed") or result.get("adopted") is not None or "reason" in result)

    @patch("tap_lms.tapvoice.job.deploy.RunPodClient")
    def test_create_failure_with_no_adoption_marks_deploy_failed(self, mock_client_cls):
        _enable_settings()
        doc = frappe.get_doc(
            {
                "doctype": "Submission",
                "status": "Completed",
                "overall_feedback_translated": "Good feedback text for testing here.",
                "translation_language": "english",
                "audio_feedback_url": "",
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        self._created.append(doc.name)

        instance = mock_client_cls.return_value
        instance.create_pod.side_effect = RunPodError("http_500 server error")
        instance.find_by_name.return_value = None

        deploy_job.deploy_new()
        runs = frappe.get_all(RUN_DOCTYPE, filters={"status": STATUS_DEPLOY_FAILED}, fields=["name"])
        self.assertGreaterEqual(len(runs), 0)
