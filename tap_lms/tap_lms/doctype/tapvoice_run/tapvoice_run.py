import frappe
from frappe.model.document import Document

ALLOWED_INTERNAL_FLAG = "_tapvoice_internal_write"


class TapVoiceRun(Document):
    def before_insert(self):
        setattr(self.flags, ALLOWED_INTERNAL_FLAG, True)

    def validate(self):
        if self.flags.get(ALLOWED_INTERNAL_FLAG):
            return
        if not self.is_new():
            frappe.throw("Tap Voice Run records cannot be edited directly")

    def on_trash(self):
        frappe.throw("Tap Voice Run records cannot be deleted")