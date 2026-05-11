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


# ════════════════════════════════════════════════════════════
# Task #54 — bulk UPDATE in _seed_pe_actions
# ════════════════════════════════════════════════════════════
#
# These tests verify the structural correctness of the bulk-update SQL
# (Postgres VALUES pattern) without requiring real PE records — PE has many
# Link dependencies (Student, Course Level, Batch, Glific contact) that would
# bloat the test setup. The actual SQL-against-PG smoke test happens when the
# bench runs the test suite on real PG via `bench run-tests`.

from unittest.mock import patch, MagicMock


class TestSeedPeActionsBulkUpdate(FrappeTestCase):
    """Task #54: bulk UPDATE shape contract for _seed_pe_actions.

    Uses FrappeTestCase (not plain unittest.TestCase) so `bench run-tests`
    auto-discovers these tests. All DB calls are mocked, so the FrappeTestCase
    transaction wrapper is unused — but inheriting from it is the safest way
    to guarantee discovery.
    """

    def _fake_pe_list(self, n):
        """Build n MagicMock PE rows that look like frappe.db.get_all output.

        Note: MagicMock(name=...) sets the mock's repr label, NOT a .name
        attribute on the mock. We need pe_row.name to return the actual string,
        because staggered_action_time hashes it and the bulk SQL uses it as
        the WHERE-key. Set .name explicitly via assignment.
        """
        pes = []
        for i in range(n):
            m = MagicMock()
            m.name = f"PE-T54-{i:05d}"
            pes.append(m)
        return pes

    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_returns_zero_when_no_pes(self, mock_db):
        """Empty pe_list → no SQL, returns 0."""
        from tap_lms.summer_program.batch_activation import _seed_pe_actions

        mock_db.get_all.return_value = []
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        result = _seed_pe_actions(bpr, batch)

        self.assertEqual(result, 0)
        mock_db.sql.assert_not_called()

    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_single_chunk_emits_one_bulk_update(self, mock_db):
        """A chunk of N PEs should produce exactly ONE frappe.db.sql call
        (was N calls with the old per-row set_value loop)."""
        from tap_lms.summer_program.batch_activation import _seed_pe_actions

        # 3 PEs — well under the 5000 chunk size, so one chunk total
        mock_db.get_all.return_value = self._fake_pe_list(3)
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        result = _seed_pe_actions(bpr, batch)

        # Exactly one bulk UPDATE call (not 3)
        self.assertEqual(mock_db.sql.call_count, 1)
        self.assertEqual(result, 3)

    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_bulk_sql_uses_values_pattern_with_correct_placeholder_count(self, mock_db):
        """SQL should use Postgres VALUES pattern with 2 placeholders per PE
        (name + action_time::timestamp). Parameter list should be flat with
        action_type prepended, so total params = 1 + 2*N."""
        from tap_lms.summer_program.batch_activation import _seed_pe_actions

        mock_db.get_all.return_value = self._fake_pe_list(5)
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        _seed_pe_actions(bpr, batch)

        # Inspect the actual call
        call_args = mock_db.sql.call_args
        sql_text = call_args[0][0]
        params = call_args[0][1]

        # 5 PEs × 2 placeholders = 10, plus 1 for action_type = 11 total params
        self.assertEqual(len(params), 11)

        # SQL uses VALUES pattern with the right number of tuples
        self.assertIn("VALUES", sql_text)
        # Five "(%s, %s)" tuples (no ::timestamp cast — Frappe's PG driver
        # binds Python datetime natively)
        self.assertEqual(sql_text.count("(%s, %s)"), 5)
        # UPDATE...FROM pattern (Postgres-specific)
        self.assertIn("UPDATE `tabProgramEnrollment`", sql_text)
        self.assertIn("FROM (VALUES", sql_text)
        self.assertIn("WHERE pe.name = v.name", sql_text)
        # H1 idempotency guard
        self.assertIn("pe.next_action_at IS NULL", sql_text)

    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_chunks_at_5000_emits_one_sql_per_chunk(self, mock_db):
        """7500 PEs → 2 chunks (5000 + 2500) → exactly 2 SQL calls.

        This is the property that makes the bulk pattern actually win at scale:
        at 100K students, the old loop did ~200K queries; the new one does ~20."""
        from tap_lms.summer_program.batch_activation import _seed_pe_actions

        mock_db.get_all.return_value = self._fake_pe_list(7500)
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        result = _seed_pe_actions(bpr, batch)

        self.assertEqual(mock_db.sql.call_count, 2)
        self.assertEqual(result, 7500)

        # First chunk has 5000 tuples → 1 + 2*5000 = 10001 params
        first_call_params = mock_db.sql.call_args_list[0][0][1]
        self.assertEqual(len(first_call_params), 10001)

        # Second chunk has 2500 tuples → 1 + 2*2500 = 5001 params
        second_call_params = mock_db.sql.call_args_list[1][0][1]
        self.assertEqual(len(second_call_params), 5001)

    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_action_type_is_first_param(self, mock_db):
        """The constant action_type (content_delivery) must be the FIRST param
        because it's referenced before the VALUES placeholders in the SQL.
        Swapping the order silently corrupts every UPDATE."""
        from tap_lms.summer_program.batch_activation import _seed_pe_actions
        from tap_lms.summer_program.constants import ACTION_CONTENT_DELIVERY

        mock_db.get_all.return_value = self._fake_pe_list(2)
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        _seed_pe_actions(bpr, batch)

        params = mock_db.sql.call_args[0][1]
        self.assertEqual(params[0], ACTION_CONTENT_DELIVERY)

    @patch("tap_lms.summer_program.batch_activation.now_datetime")
    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_staggered_times_are_deterministic_per_pe_name(self, mock_db, mock_now):
        """Same PE name + same base_time must produce identical action_times.

        With now_datetime frozen, the entire parameter list must be byte-for-byte
        equal across two calls — proving the schedule isn't scrambled on retry.
        """
        from datetime import datetime
        from tap_lms.summer_program.batch_activation import _seed_pe_actions

        # Freeze "now" so base_time doesn't advance between calls
        mock_now.return_value = datetime(2026, 6, 1, 9, 0, 0)
        mock_db.get_all.return_value = self._fake_pe_list(3)
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        # First call
        _seed_pe_actions(bpr, batch)
        first_params = list(mock_db.sql.call_args[0][1])

        # Reset and second call with same PE list + same frozen time
        mock_db.sql.reset_mock()
        _seed_pe_actions(bpr, batch)
        second_params = list(mock_db.sql.call_args[0][1])

        # Full parameter list must be byte-for-byte identical. If the schedule
        # were scrambled (e.g. random jitter instead of deterministic hash),
        # the timestamps would differ even with frozen clock.
        self.assertEqual(first_params, second_params)

    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_bulk_sql_carries_idempotency_guard(self, mock_db):
        """L-018 / H1: the bulk UPDATE must include `pe.next_action_at IS NULL`
        in its WHERE so concurrent activations don't scramble already-seeded
        PEs. The get_all filter alone is not enough — between the SELECT and
        the UPDATE, another worker could have seeded the same PEs."""
        from tap_lms.summer_program.batch_activation import _seed_pe_actions

        mock_db.get_all.return_value = self._fake_pe_list(2)
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        _seed_pe_actions(bpr, batch)

        sql_text = mock_db.sql.call_args[0][0]
        self.assertIn(
            "pe.next_action_at IS NULL",
            sql_text,
            "bulk UPDATE must guard against concurrent seeders overwriting next_action_at",
        )

    @patch("tap_lms.summer_program.batch_activation.frappe.db")
    def test_commit_per_chunk(self, mock_db):
        """Each chunk commits before moving on, so a mid-batch failure leaves
        completed chunks durable. Verify commit is called once per chunk."""
        from tap_lms.summer_program.batch_activation import _seed_pe_actions

        mock_db.get_all.return_value = self._fake_pe_list(7500)
        bpr = MagicMock(batch="BATCH-TEST")
        batch = MagicMock(start_date=None)

        _seed_pe_actions(bpr, batch)

        # 7500 PEs → 2 chunks → 2 commits
        self.assertEqual(mock_db.commit.call_count, 2)
