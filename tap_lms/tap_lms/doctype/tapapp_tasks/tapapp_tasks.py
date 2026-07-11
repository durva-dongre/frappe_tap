import frappe
from frappe.model.document import Document

JOB_DISPATCH = {
    "Nightly Window Maintenance": "tap_lms.tapapp.jobs.nightly_window_maintenance.run_nightly_window_maintenance",
    "Analytics Report": "tap_lms.tapapp.jobs.tapapp_analytics_report.run_tapapp_analytics_report",
}


class TapappTasks(Document):
    @frappe.whitelist()
    def retrigger(self):
        method = JOB_DISPATCH.get(self.job_key)
        if not method:
            frappe.throw(f"No job registered for job_key '{self.job_key}'")
        frappe.enqueue(method, queue="short")
        return {"queued": True, "job_key": self.job_key}