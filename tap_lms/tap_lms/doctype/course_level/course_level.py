import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class CourseLevel(Document):
    def before_save(self):
        if self.zip_created and self.has_value_changed("zip_created"):
            self.zip_last_modified = now_datetime()