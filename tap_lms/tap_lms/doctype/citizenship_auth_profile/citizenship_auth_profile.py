import frappe
from frappe.model.document import Document

class CitizenshipAuthProfile(Document):
    def validate(self):
        if self.avatar:
            val = str(self.avatar).strip()
            if not val.isdigit() or not (1 <= int(val) <= 99):
                frappe.throw("Avatar must be a number between 1 and 99")
            self.avatar = val