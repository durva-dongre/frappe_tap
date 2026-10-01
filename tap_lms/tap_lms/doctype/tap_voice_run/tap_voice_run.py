import frappe
from frappe.model.document import Document

ALLOWED_INTERNAL_FLAG = "_tapvoice_internal_write"


class TapVoiceRun(Document):
    def before_insert(self):
        self.flags[ALLOWED_INTERNAL_FLAG] = True

    def after_insert(self):
        self.flags.pop(ALLOWED_INTERNAL_FLAG, None)

    def validate(self):
        if self.flags.get(ALLOWED_INTERNAL_FLAG):
            return
        if not self.is_new():
            frappe.throw("Tap Voice Run records cannot be edited directly")

    def before_save(self):
        if not self.flags.get(ALLOWED_INTERNAL_FLAG) and not self.is_new():
            frappe.throw("Tap Voice Run records cannot be edited directly")

    def on_trash(self):
        frappe.throw("Tap Voice Run records cannot be deleted")