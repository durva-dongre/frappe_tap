import frappe
from frappe.model.document import Document


class SubmissionMediaLink(Document):
	def validate(self):
		self.validate_url()

	def validate_url(self):
		if self.url and not (
			self.url.startswith("http://") or self.url.startswith("https://")
		):
			frappe.throw(
				frappe._("URL must start with http:// or https:// in row {0}").format(self.idx)
			)