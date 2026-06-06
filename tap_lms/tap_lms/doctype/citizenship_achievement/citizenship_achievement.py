import frappe
from frappe.model.document import Document


class CitizenshipAchievement(Document):
    def validate(self):
        self.validate_duplicate_languages()

    def validate_duplicate_languages(self):
        seen = []
        for row in self.translations:
            if row.language in seen:
                frappe.throw(
                    frappe._("Language {0} has been added more than once in Translations.").format(row.language)
                )
            seen.append(row.language)