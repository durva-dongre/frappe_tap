import frappe
from frappe.utils import now_datetime, add_to_date

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


class StudentAuth(frappe.model.document.Document):
    def before_save(self):
        if (self.failed_attempts or 0) >= MAX_ATTEMPTS and not self.locked_until:
            self.is_locked = 1
            self.locked_until = add_to_date(now_datetime(), minutes=LOCKOUT_MINUTES)

    def reset_lock(self):
        self.is_locked = 0
        self.failed_attempts = 0
        self.locked_until = None
        self.flags.ignore_mandatory = True
        self.flags.ignore_save_passwords = True
        self.save(ignore_permissions=True)
        frappe.db.commit()

    def increment_failed(self):
        self.failed_attempts = (self.failed_attempts or 0) + 1
        if self.failed_attempts >= MAX_ATTEMPTS:
            self.is_locked = 1
            self.locked_until = add_to_date(now_datetime(), minutes=LOCKOUT_MINUTES)
        self.flags.ignore_mandatory = True
        self.flags.ignore_save_passwords = True
        self.save(ignore_permissions=True)
        frappe.db.commit()

    def is_currently_locked(self):
        if not self.is_locked:
            return False
        if self.locked_until and now_datetime() > frappe.utils.get_datetime(self.locked_until):
            self.reset_lock()
            return False
        return True
