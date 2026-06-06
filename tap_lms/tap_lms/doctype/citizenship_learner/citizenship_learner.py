import frappe
from frappe.model.document import Document

class CitizenshipLearner(Document):
    def validate(self):
        if self.streak > (self.longest_streak or 0):
            self.longest_streak = self.streak
        seen = []
        for row in self.achievements:
            if row.achievement in seen:
                frappe.throw(frappe._("Achievement {0} has been added more than once.").format(row.achievement))
            seen.append(row.achievement)