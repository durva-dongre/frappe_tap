import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class Course_LevelTranslation(Document):
    def validate(self):
        self.validate_unique_language()
        self.update_zip_last_modified()

    def validate_unique_language(self):
        parent = self.parent
        if not parent:
            return
        siblings = frappe.get_doc("Course Level", parent).translations
        seen = [
            row.language
            for row in siblings
            if row.name != self.name and row.language == self.language
        ]
        if seen:
            frappe.throw(
                frappe._("A translation for language {0} already exists on this Course Level.").format(
                    self.language
                )
            )

    def update_zip_last_modified(self):
        if self.zip_created and self.has_value_changed("zip_created"):
            self.zip_last_modified = now_datetime()