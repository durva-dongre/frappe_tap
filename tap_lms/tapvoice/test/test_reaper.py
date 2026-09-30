from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.constants import RUN_DOCTYPE, STATUS_LOST, STATUS_RUNNING, STATUS_STARTING, STATUS_TIMED_OUT
from tap_lms.tapvoice.job import reaper as reaper_job
from tap_lms.tapvoice.lib.secrets import SECRETS_DOCTYPE


def _ensure_secret():
    if not frappe.db.exists(SECRETS_DOCTYPE, "runpod_api_key"):
        frappe.get_doc(
            {"doctype": SECRETS_DOCTYPE, "key": "runpod_api_key", "value": "fake-key", "enabled": 1}
        ).insert(ignore_permissions=True)
    frappe.db.commit()


class TestReaper(FrappeTestCase):
    def setUp(self):
        _ensure_secret()
        settings = frappe.get_single("Tap Voice Settings")
        settings.startup_deadline_minutes = 15
        settings.heartbeat_timeout_minutes = 6
        settings.pod_limit_max_seconds = 7200
        settings.token_buffer_minutes = 30
        settings.stopping_grace_minutes = 5
        settings.save(ignore_permissions=True)
        frappe.db.commit()

    def tearDown(self):
        frappe.db.rollback()

    def _make_run(self, status, **fields):
        base = {
            "doctype": RUN_DOCTYPE,
            "status": status,
            "trigger_type": "Manual",
            "triggered_by": "Administrator",
            "created_at": frappe.utils.now_datetime(),
            "termination_status": "Not Needed",
        }
        base.update(fields)
        doc = frappe.get_doc(base)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    @patch("tap_lms.tapvoice.job.reaper.RunPodClient")
    def test_startup_deadline_exceeded(self, mock_client_cls):
        old_time = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-20)
        run = self._make_run(STATUS_STARTING, pod_id="pod-1", pod_created_at=old_time, hourly_rate=0.34)
        instance = mock_client_cls.return_value
        instance.delete_pod.return_value = True
        acted = reaper_job.reap_one(run.name)
        self.assertTrue(acted)
        status = frappe.db.get_value(RUN_DOCTYPE, run.name, "status")
        self.assertEqual(status, STATUS_TIMED_OUT)

    @patch("tap_lms.tapvoice.job.reaper.RunPodClient")
    def test_heartbeat_timeout(self, mock_client_cls):
        old_beat = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-10)
        run = self._make_run(
            STATUS_RUNNING,
            pod_id="pod-1",
            pod_created_at=frappe.utils.now_datetime(),
            last_beat_at=old_beat,
            hourly_rate=0.34,
        )
        instance = mock_client_cls.return_value
        instance.delete_pod.return_value = True
        acted = reaper_job.reap_one(run.name)
        self.assertTrue(acted)
        status = frappe.db.get_value(RUN_DOCTYPE, run.name, "status")
        self.assertEqual(status, STATUS_LOST)

    @patch("tap_lms.tapvoice.job.reaper.RunPodClient")
    def test_no_action_when_healthy(self, mock_client_cls):
        run = self._make_run(
            STATUS_RUNNING,
            pod_id="pod-1",
            pod_created_at=frappe.utils.now_datetime(),
            last_beat_at=frappe.utils.now_datetime(),
            hourly_rate=0.34,
        )
        acted = reaper_job.reap_one(run.name)
        self.assertFalse(acted)

    @patch("tap_lms.tapvoice.job.reaper.RunPodClient")
    def test_deploying_orphan_adopted(self, mock_client_cls):
        old_time = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=-10)
        from tap_lms.tapvoice.constants import STATUS_DEPLOYING

        run = self._make_run(STATUS_DEPLOYING, creation=old_time)
        frappe.db.set_value(RUN_DOCTYPE, run.name, "creation", old_time, update_modified=False)
        instance = mock_client_cls.return_value
        instance.find_by_name.return_value = {"id": "pod-found"}
        acted = reaper_job.reap_one(run.name)
        self.assertTrue(acted)
        status = frappe.db.get_value(RUN_DOCTYPE, run.name, "status")
        self.assertEqual(status, STATUS_STARTING)
