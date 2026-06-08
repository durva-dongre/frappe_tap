import frappe
import unittest
from unittest.mock import patch, MagicMock
from frappe.utils import add_to_date, now_datetime
from tap_lms.api.auth import login, set_password, link_student_to_phone, bulk_create_auth


class TestCitizenshipAuth(unittest.TestCase):

    def setUp(self):
        frappe.set_user("Administrator")
        self._cleanup()

        self.auth_doc = frappe.get_doc({
            "doctype": "Citizenship Auth",
            "phone": "9999900000",
            "failed_attempts": 0,
            "is_locked": 0,
            "students": [
                {"citizenship_learner": "ST00000001"},
                {"citizenship_learner": "ST00000002"}
            ]
        })
        self.auth_doc.insert(ignore_permissions=True)

        from frappe.utils.password import update_password
        update_password("9999900000", "test@1234", doctype="Citizenship Auth", fieldname="password")

        frappe.db.commit()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        if frappe.db.exists("Citizenship Auth", "9999900000"):
            frappe.delete_doc("Citizenship Auth", "9999900000", force=True)
            frappe.db.commit()

    def test_login_success(self):
        result = login("9999900000", "test@1234")
        self.assertTrue(result["success"])
        self.assertIn("token", result)
        self.assertEqual(len(result["profiles"]), 2)

    def test_login_wrong_password(self):
        result = login("9999900000", "wrongpassword")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "invalid_credentials")
        self.assertEqual(result["attempts_remaining"], 4)

    def test_login_nonexistent_phone(self):
        result = login("0000000000", "anypassword")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "invalid_credentials")

    def test_account_locks_after_max_attempts(self):
        for _ in range(5):
            login("9999900000", "wrongpassword")

        doc = frappe.get_doc("Citizenship Auth", "9999900000")
        self.assertEqual(doc.is_locked, 1)
        self.assertIsNotNone(doc.locked_until)

    def test_locked_account_rejects_correct_password(self):
        doc = frappe.get_doc("Citizenship Auth", "9999900000")
        doc.is_locked = 1
        doc.failed_attempts = 5
        doc.locked_until = add_to_date(now_datetime(), minutes=30)
        doc.save(ignore_permissions=True)

        result = login("9999900000", "test@1234")
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "account_locked")

    def test_lock_resets_after_expiry(self):
        doc = frappe.get_doc("Citizenship Auth", "9999900000")
        doc.is_locked = 1
        doc.failed_attempts = 5
        doc.locked_until = add_to_date(now_datetime(), minutes=-1)
        doc.save(ignore_permissions=True)

        result = login("9999900000", "test@1234")
        self.assertTrue(result["success"])

    def test_successful_login_resets_failed_attempts(self):
        doc = frappe.get_doc("Citizenship Auth", "9999900000")
        doc.failed_attempts = 3
        doc.save(ignore_permissions=True)

        login("9999900000", "test@1234")

        doc.reload()
        self.assertEqual(doc.failed_attempts, 0)

    def test_link_student_to_phone(self):
        link_student_to_phone("9999900000", "ST00000003")
        doc = frappe.get_doc("Citizenship Auth", "9999900000")
        linked = [r.citizenship_learner for r in doc.students]
        self.assertIn("ST00000003", linked)

    def test_link_student_no_duplicate(self):
        link_student_to_phone("9999900000", "ST00000001")
        doc = frappe.get_doc("Citizenship Auth", "9999900000")
        linked = [r.citizenship_learner for r in doc.students]
        self.assertEqual(linked.count("ST00000001"), 1)

    def test_bulk_create_creates_new_record(self):
        if frappe.db.exists("Citizenship Auth", "8888800000"):
            frappe.delete_doc("Citizenship Auth", "8888800000", force=True)

        bulk_create_auth([
            {"phone": "8888800000", "password": "bulk@pass", "student_id": "ST00000010"}
        ])

        self.assertTrue(frappe.db.exists("Citizenship Auth", "8888800000"))

        frappe.delete_doc("Citizenship Auth", "8888800000", force=True)
        frappe.db.commit()

    def test_bulk_create_links_to_existing(self):
        bulk_create_auth([
            {"phone": "9999900000", "password": "test@1234", "student_id": "ST00000004"}
        ])

        doc = frappe.get_doc("Citizenship Auth", "9999900000")
        linked = [r.citizenship_learner for r in doc.students]
        self.assertIn("ST00000004", linked)

    def test_token_returned_on_login(self):
        result = login("9999900000", "test@1234")
        self.assertIn("token", result)
        self.assertIsInstance(result["token"], str)
        self.assertGreater(len(result["token"]), 20)

    def test_set_password(self):
        result = set_password("9999900000", "newpass@5678")
        self.assertTrue(result["success"])

        result2 = login("9999900000", "newpass@5678")
        self.assertTrue(result2["success"])


if __name__ == "__main__":
    unittest.main()