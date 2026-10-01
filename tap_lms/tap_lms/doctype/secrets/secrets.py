import frappe
from frappe.model.document import Document
from frappe.utils.password import encrypt

ENC_PREFIX = "enc:"


class Secrets(Document):
    def validate(self):
        value = (self.value or "").strip()
        if value and not value.startswith(ENC_PREFIX):
            value = ENC_PREFIX + encrypt(value)
        self.value = value