import frappe
from frappe.model.document import Document

JOB_DISPATCH = {
    "XP Window Rotate": "tap_lms.ca.jobs.xp_window_rotate.run_xp_window_rotate",
    "Leaderboard Build": "tap_lms.ca.jobs.leaderboard_build.run_leaderboard_build",
    "Analytics Report": "tap_lms.ca.jobs.analytics_report.run_analytics_report",
}


class CitizenshipTasks(Document):
    @frappe.whitelist()
    def retrigger(self):
        method = JOB_DISPATCH.get(self.job_key)
        if not method:
            frappe.throw(f"No job registered for job_key '{self.job_key}'")
        frappe.enqueue(method, queue="short")
        return {"queued": True, "job_key": self.job_key}