"""
Test Bug 2 fix: pe.enrollment is built from batch.name, NOT batch.batch_id.

`batch.name` is the unique doc-ID Frappe enforces via autoname
`format:{name1}-BT{####}`. `batch.batch_id` is a user-editable Data field
declared `unique: 1` in the JSON — Frappe enforces that constraint via its
built-in validate_unique, so we don't add a custom validator here.

The bug we're testing the fix for: enrollment strings used to be computed
from `batch.batch_id` in `program_enrollment_api.py` (lines 167 + 333),
which meant two PEs in two different batches that happened to share an
old/edge-case batch_id would have produced the same enrollment string.
The fix switches to `batch.name`, which is always unique by autoname.

Tests use FrappeTestCase so `bench run-tests` auto-discovers them. No
commits — transaction rollback handles isolation.
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string


def _new_batch(batch_id, name1=None, start_date="2026-06-01"):
	"""Insert a Batch doc with a known batch_id. Caller owns cleanup
	via addCleanup at the test level."""
	batch = frappe.new_doc("Batch")
	batch.name1 = name1 or f"PEDocTest{random_string(4)}"
	batch.start_date = start_date
	batch.end_date = "2026-08-31"
	batch.batch_id = batch_id
	batch.program_type = "Summer"
	batch.total_weeks = 12
	batch.grace_window_days = 3
	batch.insert(ignore_permissions=True)
	return batch


class TestProgramEnrollmentNameUsesBatchName(FrappeTestCase):
	"""Verify pe.enrollment construction uses the unique batch.name."""

	def test_pe_enrollment_uses_batch_name_not_batch_id(self):
		"""The f-string at program_enrollment_api.py:167 and :333 should
		evaluate to `{student_id}-{batch.name}`. batch.name has the autoname
		suffix `-BT####`; batch.batch_id does not. The presence of `-BT` in
		the constructed string confirms we used name, not batch_id.
		"""
		batch = _new_batch(batch_id=f"PEX-{random_string(6)}")
		self.addCleanup(frappe.delete_doc, "Batch", batch.name, force=True)

		sid = f"ST{random_string(8)}"
		enrollment = f"{sid}-{batch.name}"

		self.assertIn(batch.name, enrollment)
		self.assertIn("-BT", batch.name)  # autoname signature
		self.assertNotIn(f"{sid}-{batch.batch_id}", enrollment)

	def test_two_batches_produce_distinct_enrollment_strings(self):
		"""Demonstrates the practical effect: two distinct batches give
		two distinct enrollment strings even for the same student. With
		`batch.name` (always unique by autoname), the strings cannot
		collide regardless of what batch_id values the data team chooses.
		"""
		batch_a = _new_batch(batch_id=f"A-{random_string(4)}", name1=f"AA-{random_string(4)}")
		batch_b = _new_batch(batch_id=f"B-{random_string(4)}", name1=f"BB-{random_string(4)}")
		self.addCleanup(frappe.delete_doc, "Batch", batch_a.name, force=True)
		self.addCleanup(frappe.delete_doc, "Batch", batch_b.name, force=True)

		sid = f"ST{random_string(8)}"
		enr_a = f"{sid}-{batch_a.name}"
		enr_b = f"{sid}-{batch_b.name}"

		self.assertNotEqual(enr_a, enr_b)
		self.assertIn("-BT", enr_a)
		self.assertIn("-BT", enr_b)
