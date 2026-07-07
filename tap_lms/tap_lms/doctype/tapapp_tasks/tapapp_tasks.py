import frappe
from frappe.model.document import Document

JOB_DISPATCH = {
    "XP Window Rotate": "tap_lms.tapapp.jobs.xp_window_rotate.run_xp_window_rotate",
    "Weekly Window Rollover": "tap_lms.tapapp.jobs.window_rollover.run_window_rollover",
    "Analytics Report": "tap_lms.tapapp.jobs.analytics_report.run_analytics_report",
}


class TapappTasks(Document):
    @frappe.whitelist()
    def retrigger(self):
        method = JOB_DISPATCH.get(self.job_key)
        if not method:
            frappe.throw(f"No job registered for job_key '{self.job_key}'")
        frappe.enqueue(method, queue="short")
        return {"queued": True, "job_key": self.job_key}
