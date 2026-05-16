import frappe
import unittest
from frappe.utils import add_days, nowdate


class TestProgram(unittest.TestCase):

    def setUp(self):
        self.base_data = {
            "doctype": "Program",
            "program": "Test Program",
            "batch_id": "BATCH-TEST-001",
            "batch": "Batch A",
            "start": nowdate(),
            "end": add_days(nowdate(), 30),
            "reg_end_date": add_days(nowdate(), -1),
        }

    def tearDown(self):
        frappe.db.rollback()

    def make_program(self, **overrides):
        data = {**self.base_data, **overrides}
        doc = frappe.get_doc(data)
        doc.insert(ignore_permissions=True)
        return doc

    def test_program_creation(self):
        doc = self.make_program()
        self.assertTrue(frappe.db.exists("Program", doc.name))

    def test_end_date_must_be_after_start(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self.make_program(
                start=nowdate(),
                end=add_days(nowdate(), -5),
            )

    def test_start_and_end_same_date_raises(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self.make_program(
                start=nowdate(),
                end=nowdate(),
            )

    def test_reg_end_date_before_start(self):
        doc = self.make_program(
            reg_end_date=add_days(nowdate(), -2),
        )
        self.assertEqual(doc.reg_end_date, add_days(nowdate(), -2))

    def test_reg_end_date_after_start_raises(self):
        with self.assertRaises(frappe.exceptions.ValidationError):
            self.make_program(
                reg_end_date=add_days(nowdate(), 5),
                start=nowdate(),
            )

    def test_duplicate_batch_id_raises(self):
        self.make_program(batch_id="BATCH-DUPE-001")
        with self.assertRaises(frappe.exceptions.ValidationError):
            self.make_program(batch_id="BATCH-DUPE-001")

    def test_unique_batch_ids_allowed(self):
        doc1 = self.make_program(batch_id="BATCH-UNIQUE-001")
        doc2 = self.make_program(batch_id="BATCH-UNIQUE-002")
        self.assertNotEqual(doc1.name, doc2.name)

    def test_get_program_summary_whitelisted(self):
        doc = self.make_program()
        result = frappe.call(
            "tap_lms.tap_lms.doctype.program.program.get_program_summary",
            program_name=doc.name,
        )
        self.assertEqual(result["batch_id"], doc.batch_id)
        self.assertEqual(result["program"], doc.program)

    def test_get_active_programs_returns_list(self):
        self.make_program(
            batch_id="BATCH-ACTIVE-001",
            start=add_days(nowdate(), -1),
            end=add_days(nowdate(), 10),
            reg_end_date=add_days(nowdate(), -2),
        )
        result = frappe.call(
            "tap_lms.tap_lms.doctype.program.program.get_active_programs"
        )
        self.assertIsInstance(result, list)
        batch_ids = [r["batch_id"] for r in result]
        self.assertIn("BATCH-ACTIVE-001", batch_ids)

    def test_course_level_link_is_optional(self):
        doc = self.make_program(course_level=None)
        self.assertIsNone(doc.course_level)

    def test_batch_field_is_optional(self):
        doc = self.make_program(batch=None)
        self.assertIsNone(doc.batch)