import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class Program(Document):

    def validate(self):
        self.validate_dates()
        self.validate_registration_end_date()

    def before_insert(self):
        self.validate_duplicate_batch()

    def after_insert(self):
        frappe.msgprint(
            frappe._("Program {0} created successfully.").format(self.name),
            indicator="green",
            alert=True,
        )

    def validate_dates(self):
        if self.start and self.end:
            if getdate(self.start) >= getdate(self.end):
                frappe.throw(frappe._("End date must be after Start date."))

    def validate_registration_end_date(self):
        if self.reg_end_date and self.start:
            if getdate(self.reg_end_date) > getdate(self.start):
                frappe.throw(
                    frappe._("Registration End Date must be on or before the Start date.")
                )

    def validate_duplicate_batch(self):
        existing = frappe.db.exists(
            "Program",
            {
                "batch_id": self.batch_id,
                "name": ("!=", self.name),
            },
        )
        if existing:
            frappe.throw(
                frappe._("A Program with Batch ID {0} already exists.").format(self.batch_id)
            )


@frappe.whitelist()
def get_program_summary(program_name):
    doc = frappe.get_doc("Program", program_name)
    return {
        "program": doc.program,
        "batch_id": doc.batch_id,
        "batch": doc.batch,
        "course_level": doc.course_level,
        "start": doc.start,
        "end": doc.end,
        "reg_end_date": doc.reg_end_date,
    }


@frappe.whitelist()
def get_active_programs():
    today = nowdate()
    return frappe.get_all(
        "Program",
        filters={
            "start": ("<=", today),
            "end": (">=", today),
        },
        fields=["name", "program", "batch_id", "batch", "course_level", "start", "end"],
        order_by="start asc",
    )