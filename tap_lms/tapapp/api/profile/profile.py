import frappe
from tap_lms.tapapp.api.auth.tapapp_auth import (
    _require_access_token,
    _require_access_token_with_refresh,
)
from tap_lms.tapapp.api.progress.learner import learner_full_state

EDITABLE_LEARNER_FIELDS = {"student_name", "language", "district", "state", "birthdate"}
EDITABLE_PROFILE_FIELDS = {"roll_number", "grade", "avatar"}


def _owned_learner_id(phone, learner_id):
    row = frappe.db.sql(
        'SELECT tapapp_learner FROM "tabTapapp Auth Profile" WHERE parent=%s AND tapapp_learner=%s LIMIT 1',
        (phone, learner_id),
    )
    if not row:
        frappe.throw("Profile not linked to this account", frappe.AuthenticationError)
    return learner_id


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, learner_id=None, fields=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    payload, new_token = _require_access_token_with_refresh(phone)
    _owned_learner_id(phone, learner_id)

    state = learner_full_state(learner_id, fields=fields, include_achievements=True)
    if state is None:
        frappe.throw("Learner not found", frappe.DoesNotExistError)

    result = {"success": True, **state}
    if new_token:
        result["token"] = new_token
    return result


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, learner_id=None, avatar=None):
    phone = phone or frappe.form_dict.get("phone", "")
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    avatar = avatar or frappe.form_dict.get("avatar", "1")

    _require_access_token(phone)
    _owned_learner_id(phone, learner_id)

    frappe.db.sql(
        """
        UPDATE "tabTapapp Auth Profile"
        SET avatar=%s, modified=NOW()
        WHERE parent=%s AND tapapp_learner=%s
        """,
        (avatar, phone, learner_id),
    )
    frappe.db.commit()
    return {"success": True, "avatar": avatar}


@frappe.whitelist(allow_guest=True)
def update_profile(phone=None, learner_id=None, updates=None, **kwargs):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    _require_access_token(phone)
    _owned_learner_id(phone, learner_id)

    if updates is None:
        updates = {k: v for k, v in fd.items() if k not in ("phone", "learner_id", "cmd")}

    if isinstance(updates, str):
        import json
        try:
            updates = json.loads(updates)
        except Exception:
            frappe.throw("updates must be a JSON object", frappe.ValidationError)

    if not isinstance(updates, dict) or not updates:
        frappe.throw("No editable fields supplied", frappe.ValidationError)

    if "school" in updates or "school_id" in updates:
        frappe.throw("school cannot be edited", frappe.ValidationError)

    learner_set = {k: v for k, v in updates.items() if k in EDITABLE_LEARNER_FIELDS}
    profile_set = {k: v for k, v in updates.items() if k in EDITABLE_PROFILE_FIELDS}

    unknown = set(updates.keys()) - EDITABLE_LEARNER_FIELDS - EDITABLE_PROFILE_FIELDS
    if unknown:
        frappe.throw(f"These fields cannot be edited: {', '.join(sorted(unknown))}", frappe.ValidationError)

    if learner_set:
        set_clause = ", ".join(f"{k}=%s" for k in learner_set)
        frappe.db.sql(
            f'UPDATE "tabTapapp Learner" SET {set_clause}, modified=NOW() WHERE name=%s',
            (*learner_set.values(), learner_id),
        )
        if "student_name" in learner_set:
            frappe.db.sql(
                """
                UPDATE "tabTapapp Auth Profile"
                   SET student_name=%s, modified=NOW()
                 WHERE parent=%s AND tapapp_learner=%s
                """,
                (learner_set["student_name"], phone, learner_id),
            )

    if profile_set:
        set_clause = ", ".join(f"{k}=%s" for k in profile_set)
        frappe.db.sql(
            f"""
            UPDATE "tabTapapp Auth Profile"
               SET {set_clause}, modified=NOW()
             WHERE parent=%s AND tapapp_learner=%s
            """,
            (*profile_set.values(), phone, learner_id),
        )

    frappe.db.commit()

    return {"success": True, **learner_full_state(learner_id, fields="profile,level")}
