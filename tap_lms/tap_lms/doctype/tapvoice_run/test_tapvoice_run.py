import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.lib import runstate


class TestTapVoiceRun(FrappeTestCase):
    def _make_run(self):
        doc = frappe.get_doc(
            {
                "doctype": "Tap Voice Run",
                "status": "Draft",
                "trigger_type": "Manual",
                "triggered_by": "Administrator",
                "created_at": frappe.utils.now_datetime(),
            }
        )
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc

    def tearDown(self):
        frappe.db.rollback()

    def test_cannot_edit_directly(self):
        doc = self._make_run()
        doc.status_reason = "tampering"
        with self.assertRaises(frappe.ValidationError):
            doc.save()

    def test_cannot_delete(self):
        doc = self._make_run()
        with self.assertRaises(frappe.ValidationError):
            doc.delete()

    def test_internal_write_via_runstate_allowed(self):
        doc = self._make_run()
        runstate.set_fields(doc.name, {"status_reason": "internal update"})
        refreshed = frappe.get_doc("Tap Voice Run", doc.name)
        self.assertEqual(refreshed.status_reason, "internal update")

    def test_transition_table(self):
        self.assertTrue(runstate.can_transition("Draft", "Deploying"))
        self.assertTrue(runstate.can_transition("Deploying", "Starting"))
        self.assertTrue(runstate.can_transition("Starting", "Running"))
        self.assertTrue(runstate.can_transition("Running", "Completed"))
        self.assertFalse(runstate.can_transition("Draft", "Running"))
        self.assertFalse(runstate.can_transition("Completed", "Running"))
        self.assertFalse(runstate.can_transition("Skipped", "Deploying"))

    def test_terminal_statuses(self):
        self.assertTrue(runstate.is_terminal("Completed"))
        self.assertTrue(runstate.is_terminal("Failed"))
        self.assertFalse(runstate.is_terminal("Running"))
        self.assertFalse(runstate.is_terminal("Draft"))