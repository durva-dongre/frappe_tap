import frappe

ROTATE_JOB_KEY = "XP Window Rotate"


def rotation_succeeded_today() -> bool:
    if not frappe.db.exists("Citizenship Tasks", ROTATE_JOB_KEY):
        return False
    last_success_at = frappe.db.get_value("Citizenship Tasks", ROTATE_JOB_KEY, "last_success_at")
    if not last_success_at:
        return False
    return frappe.utils.getdate(last_success_at) == frappe.utils.getdate(frappe.utils.now_datetime())