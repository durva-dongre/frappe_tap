import frappe
import json
from tap_lms.tapapp.api.auth.tapapp_auth import _require_access_token
from tap_lms.tapapp.api.profile.profile import _owned_learner_id, _apply_updates
from tap_lms.tapapp.api.progress.learner import _enroll_course_internal


@frappe.whitelist(allow_guest=True)
def complete_onboarding(phone=None, learner_id=None, updates=None, course=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    updates = updates if updates is not None else fd.get("updates")
    course = course or fd.get("course")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    _require_access_token(phone)
    _owned_learner_id(phone, learner_id)

    if isinstance(updates, str):
        try:
            updates = json.loads(updates)
        except Exception:
            frappe.throw("updates must be a JSON object", frappe.ValidationError)

    if updates is not None and not isinstance(updates, dict):
        frappe.throw("updates must be a JSON object", frappe.ValidationError)

    savepoint = "complete_onboarding_sp"
    frappe.db.sql(f"SAVEPOINT {savepoint}")
    updated_fields = []
    try:
        if updates:
            _apply_updates(phone, learner_id, updates)
            updated_fields = list(updates.keys())

        if course:
            _enroll_course_internal(learner_id, course)

        frappe.db.sql(
            """
            UPDATE "tabTapapp Auth Profile"
               SET onboarding_completed=1, modified=NOW()
             WHERE parent=%s AND tapapp_learner=%s
            """,
            (phone, learner_id),
        )
    except Exception:
        frappe.db.sql(f"ROLLBACK TO SAVEPOINT {savepoint}")
        raise

    frappe.db.commit()

    return {
        "learner_id": learner_id,
        "onboarding_completed": True,
        "course": course,
        "updated_fields": updated_fields,
    }