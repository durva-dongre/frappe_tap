import frappe

from tap_lms.ca.api.auth.student_auth import (
    _generate_access_token,
    _decode_token,
    _bearer_token,
    _avatar_path,
    _profiles_for_phone,
)
from tap_lms.ca.api.onboarding.registration import _do_profile


def _require_access_token(phone):
    token = _bearer_token()
    if not token:
        frappe.throw("Missing token", frappe.AuthenticationError)
    payload = _decode_token(token, "access")
    if not payload:
        frappe.throw("Invalid or expired token", frappe.AuthenticationError)
    if payload.get("phone") != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)
    return payload


@frappe.whitelist(allow_guest=True)
def add_profile(
    phone=None, display_name=None, gender=None, grade=None, state=None,
    district=None, school_id=None, language=None, avatar=None, dob=None,
    migrate_student_id=None,
):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    display_name = display_name or fd.get("display_name")
    gender = gender or fd.get("gender")
    grade = grade or fd.get("grade")
    state = state or fd.get("state")
    district = district or fd.get("district")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar")
    dob = dob or fd.get("dob")
    migrate_student_id = migrate_student_id or fd.get("migrate_student_id")

    _require_access_token(phone)
    return _do_profile(phone, display_name, gender, grade, state, district,
                       school_id, language, avatar, dob, migrate_student_id)


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, student_id=None):
    phone = phone or frappe.form_dict.get("phone", "")
    student_id = student_id or frappe.form_dict.get("student_id")
    _require_access_token(phone)

    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    if not auth_name:
        frappe.throw("Phone not registered", frappe.DoesNotExistError)
    doc = frappe.get_doc("Student Auth", auth_name)
    linked_ids = [row.student for row in doc.students]

    if student_id not in linked_ids:
        frappe.throw("Profile not linked to this phone", frappe.AuthenticationError)

    profiles = _profiles_for_phone(phone)
    return {
        "success": True,
        "token": _generate_access_token(phone, linked_ids),
        "phone": phone,
        "active_profile": next((p for p in profiles if p["student_id"] == student_id), None),
        "profiles": profiles,
    }


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, student_id=None, avatar=None):
    phone = phone or frappe.form_dict.get("phone", "")
    student_id = student_id or frappe.form_dict.get("student_id")
    avatar = avatar or frappe.form_dict.get("avatar")
    _require_access_token(phone)

    if not frappe.db.exists("Student Avatar", avatar):
        frappe.throw("Invalid avatar", frappe.ValidationError)

    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    doc = frappe.get_doc("Student Auth", auth_name)

    for row in doc.students:
        if row.student == student_id:
            row.avatar = avatar
            doc.flags.ignore_mandatory = True
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.cache().delete_value(f"profiles::{phone}")
            return {"success": True, "avatar": _avatar_path(avatar)}

    frappe.throw("Profile not found on this account", frappe.DoesNotExistError)