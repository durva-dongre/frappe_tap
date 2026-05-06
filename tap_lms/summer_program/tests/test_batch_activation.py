"""
Tests for batch_activation module
Uses FrappeTestCase for database access.
"""
import frappe
import json
from frappe.tests.utils import FrappeTestCase

from tap_lms.summer_program.constants import (
    BPR_DRAFT,
    BPR_COLLECTIONS_READY,
    BPR_ACTIVE,
    VALIDATION_PASSED,
    VALIDATION_FAILED,
)


class TestBatchActivation(FrappeTestCase):

    def setUp(self):
        # Create test batch
        if not frappe.db.exists("Batch", {"name1": "TestSPBatch"}):
            batch = frappe.new_doc("Batch")
            batch.name1 = "TestSPBatch"
            batch.start_date = "2026-06-01"
            batch.end_date = "2026-08-31"
            batch.batch_id = "SPTEST01"
            batch.program_type = "Summer"
            batch.total_weeks = 12
            batch.grace_window_days = 3
            batch.insert(ignore_permissions=True)

        self.batch_name = frappe.get_value("Batch", {"name1": "TestSPBatch"}, "name")

    def _create_test_bpr(self, status=BPR_COLLECTIONS_READY, with_flows=True):
        bpr = frappe.new_doc("BatchProgramRun")
        bpr.batch = self.batch_name
        bpr.status = status
        bpr.total_imported = 100
        bpr.total_enrolled = 100
        if with_flows:
            bpr.content_delivery_flow = 101
            bpr.escalation_flow = 102
        bpr.insert(ignore_permissions=True)
        return bpr

    def test_validate_fails_wrong_status(self):
        from tap_lms.summer_program.batch_activation import validate_bpr

        bpr = self._create_test_bpr(status=BPR_DRAFT)
        report = validate_bpr(bpr.name)

        self.assertFalse(report["passed"])
        self.assertTrue(any("status must be" in e for e in report["errors"]))

    def test_validate_fails_no_collections(self):
        from tap_lms.summer_program.batch_activation import validate_bpr

        bpr = self._create_test_bpr()
        report = validate_bpr(bpr.name)

        self.assertFalse(report["passed"])
        self.assertTrue(any("collection" in e.lower() for e in report["errors"]))

    def test_validate_fails_no_enrollment(self):
        from tap_lms.summer_program.batch_activation import validate_bpr

        bpr = self._create_test_bpr()
        bpr.total_enrolled = 0
        bpr.save(ignore_permissions=True)

        report = validate_bpr(bpr.name)
        self.assertFalse(report["passed"])

    def test_activate_requires_validation(self):
        from tap_lms.summer_program.batch_activation import activate_bpr

        bpr = self._create_test_bpr()
        bpr.validation_status = "not_run"
        bpr.save(ignore_permissions=True)

        result = activate_bpr(bpr.name)
        self.assertFalse(result["success"])

    def test_activate_after_validation(self):
        from tap_lms.summer_program.batch_activation import activate_bpr

        bpr = self._create_test_bpr()
        bpr.validation_status = VALIDATION_PASSED
        bpr.save(ignore_permissions=True)

        result = activate_bpr(bpr.name)
        self.assertTrue(result["success"])

        bpr.reload()
        self.assertEqual(bpr.status, BPR_ACTIVE)
        self.assertIsNotNone(bpr.activated_at)

    def tearDown(self):
        # Clean up test BPRs
        for bpr in frappe.get_all("BatchProgramRun", filters={"batch": self.batch_name}):
            frappe.delete_doc("BatchProgramRun", bpr.name, force=True)
