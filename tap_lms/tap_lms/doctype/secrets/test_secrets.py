import frappe
from frappe.tests.utils import FrappeTestCase


class TestSecrets(FrappeTestCase):
    def test_secret_creation(self):
        if frappe.db.exists("Secrets", "test_secret"):
            frappe.delete_doc("Secrets", "test_secret")

        doc = frappe.get_doc({
            "doctype": "Secrets",
            "key": "test_secret",
            "value": "secret_value"
        })

        doc.insert()

        self.assertTrue(
            frappe.db.exists("Secrets", "test_secret")
        )