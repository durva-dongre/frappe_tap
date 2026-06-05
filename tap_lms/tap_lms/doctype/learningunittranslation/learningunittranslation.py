import frappe
from frappe.model.document import Document


class LearningUnitTranslation(Document):
    def validate(self):
        self.validate_unique_language()

    def validate_unique_language(self):
        parent = self.parent
        if not parent:
            return
        siblings = frappe.get_doc("LearningUnit", parent).translations
        seen = [
            row.language
            for row in siblings
            if row.name != self.name and row.language == self.language
        ]
        if seen:
            frappe.throw(
                frappe._("A translation for language {0} already exists on this Learning Unit.").format(
                    self.language
                )
            )