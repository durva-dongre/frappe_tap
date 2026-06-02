import frappe
import jwt
import datetime
from frappe.utils.password import check_password, update_password

JWT_EXPIRY_HOURS = 72
MAX_ATTEMPTS = 5


def _save_auth_doc(doc):
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_save_passwords = True
    doc.save(ignore_permissions=True)


def _insert_auth_doc(doc):
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_save_passwords = True
    doc.insert(ignore_permissions=True)


def _get_avatar_for_profile_row(row):
    avatars = getattr(row, "avatars", None) or []
    if avatars:
        return avatars[0].avatar_name or "avatar_01"
    return "avatar_01"


def get_secret(key):
    cache = frappe.cache()
    cached = cache.get_value(f"secret::{key}")
    if cached:
        return cached
    secret_doc = frappe.get_doc("Secrets", key)
    value = secret_doc.get_password("value")
    cache.set_value(f"secret::{key}", value)
    return value


def get_jwt_secret():
    return get_secret("jwt_secret")


def _generate_jwt(phone, student_ids):
    payload = {
        "phone": phone,
        "students": student_ids,
        "type": "access",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def _decode_jwt(token):
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except Exception:
        return None


@frappe.whitelist(allow_guest=True)
def check_phone(phone):
    exists = frappe.db.exists("Student Auth", {"phone": phone})
    return {"exists": bool(exists)}


@frappe.whitelist(allow_guest=True)
def login_with_password(phone, password):
    auth = frappe.db.get_value(
        "Student Auth",
        {"phone": phone},
        ["name", "is_locked", "failed_attempts", "locked_until"],
        as_dict=True,
    )

    if not auth:
        return {"success": False, "error": "invalid_credentials"}

    doc = frappe.get_doc("Student Auth", auth.name)

    if doc.is_currently_locked():
        return {
            "success": False,
            "error": "account_locked",
            "locked_until": str(doc.locked_until),
        }

    try:
        check_password(auth.name, password, doctype="Student Auth", fieldname="password")
    except frappe.AuthenticationError:
        doc.increment_failed()
        remaining = max(0, MAX_ATTEMPTS - doc.failed_attempts)
        return {
            "success": False,
            "error": "invalid_credentials",
            "attempts_remaining": remaining,
        }

    doc.reset_lock()

    students = [
        {
            "student_id": row.student,
            "name": row.student_name,
            "avatar": _get_avatar_for_profile_row(row),
        }
        for row in doc.students
    ]

    token = _generate_jwt(phone, [s["student_id"] for s in students])
    return {"success": True, "token": token, "phone": phone, "profiles": students}


@frappe.whitelist()
def set_password(phone, new_password):
    if not frappe.db.exists("Student Auth", {"phone": phone}):
        frappe.throw("No auth record found")
    update_password(phone, new_password, doctype="Student Auth", fieldname="password")
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist(allow_guest=True)
def verify_token(token):
    payload = _decode_jwt(token)
    if not payload:
        return {"valid": False}
    return {
        "valid": True,
        "phone": payload.get("phone"),
        "students": payload.get("students"),
    }


def link_student_to_phone(phone, student_id, avatar=None):
    if not frappe.db.exists("Student Auth", {"phone": phone}):
        frappe.throw(f"No Student Auth record for {phone}")
    resolved_avatar = avatar or "avatar_01"
    doc = frappe.get_doc("Student Auth", phone)
    existing = [row.student for row in doc.students]
    if student_id not in existing:
        profile_row = doc.append("students", {"student": student_id})
        profile_row.append("avatars", {"avatar_name": resolved_avatar})
        _save_auth_doc(doc)


def bulk_create_auth(students_data):
    for entry in students_data:
        phone = entry["phone"]
        password = entry["password"]
        student_id = entry["student_id"]
        avatar = entry.get("avatar", "avatar_01")

        if not frappe.db.exists("Student Auth", {"phone": phone}):
            doc = frappe.new_doc("Student Auth")
            doc.phone = phone
            doc.failed_attempts = 0
            doc.is_locked = 0
            _insert_auth_doc(doc)
            frappe.db.commit()
            update_password(doc.name, password, doctype="Student Auth", fieldname="password")
            frappe.db.commit()
            doc.reload()
            profile_row = doc.append("students", {"student": student_id})
            profile_row.append("avatars", {"avatar_name": avatar})
            _save_auth_doc(doc)
        else:
            link_student_to_phone(phone, student_id, avatar)

    frappe.db.commit()import frappe
import jwt
import datetime
from frappe.utils.password import check_password, update_password

JWT_EXPIRY_HOURS = 72
MAX_ATTEMPTS = 5


def _save_auth_doc(doc):
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_save_passwords = True
    doc.save(ignore_permissions=True)


def _insert_auth_doc(doc):
    doc.flags.ignore_mandatory = True
    doc.flags.ignore_save_passwords = True
    doc.insert(ignore_permissions=True)


def _get_avatar_for_profile_row(row):
    avatars = getattr(row, "avatars", None) or []
    if avatars:
        return avatars[0].avatar_name or "avatar_01"
    return "avatar_01"


def get_secret(key):
    cache = frappe.cache()
    cached = cache.get_value(f"secret::{key}")
    if cached:
        return cached
    secret_doc = frappe.get_doc("Secrets", key)
    value = secret_doc.get_password("value")
    cache.set_value(f"secret::{key}", value)
    return value


def get_jwt_secret():
    return get_secret("jwt_secret")


@frappe.whitelist(allow_guest=True)
def check_phone(phone):
    exists = frappe.db.exists("Student Auth", {"phone": phone})
    return {"exists": bool(exists)}


@frappe.whitelist(allow_guest=True)
def login(phone, password):
    auth = frappe.db.get_value(
        "Student Auth",
        {"phone": phone},
        ["name", "is_locked", "failed_attempts", "locked_until"],
        as_dict=True,
    )

    if not auth:
        return {"success": False, "error": "invalid_credentials"}

    doc = frappe.get_doc("Student Auth", auth.name)

    if doc.is_currently_locked():
        return {
            "success": False,
            "error": "account_locked",
            "locked_until": str(doc.locked_until),
        }

    try:
        check_password(auth.name, password, doctype="Student Auth", fieldname="password")
    except frappe.AuthenticationError:
        doc.increment_failed()
        remaining = max(0, MAX_ATTEMPTS - doc.failed_attempts)
        return {
            "success": False,
            "error": "invalid_credentials",
            "attempts_remaining": remaining,
        }

    doc.reset_lock()

    students = [
        {
            "student_id": row.student,
            "name":       row.student_name,
            "avatar":     _get_avatar_for_profile_row(row),
        }
        for row in doc.students
    ]

    token = _generate_jwt(phone, [s["student_id"] for s in students])
    return {"success": True, "token": token, "phone": phone, "profiles": students}


@frappe.whitelist()
def set_password(phone, new_password):
    if not frappe.db.exists("Student Auth", {"phone": phone}):
        frappe.throw("No auth record found")
    update_password(phone, new_password, doctype="Student Auth", fieldname="password")
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist(allow_guest=True)
def verify_token(token):
    payload = _decode_jwt(token)
    if not payload:
        return {"valid": False}
    return {
        "valid":    True,
        "phone":    payload.get("phone"),
        "students": payload.get("students"),
    }


def _generate_jwt(phone, student_ids):
    payload = {
        "phone":    phone,
        "students": student_ids,
        "type":     "access",
        "exp":      datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
        "iat":      datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def _decode_jwt(token):
    try:
        return jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except Exception:
        return None


def link_student_to_phone(phone, student_id, avatar=None):
    if not frappe.db.exists("Student Auth", {"phone": phone}):
        frappe.throw(f"No Student Auth record for {phone}")
    resolved_avatar = avatar or "avatar_01"
    doc = frappe.get_doc("Student Auth", phone)
    existing = [row.student for row in doc.students]
    if student_id not in existing:
        profile_row = doc.append("students", {"student": student_id})
        profile_row.append("avatars", {"avatar_name": resolved_avatar})
        _save_auth_doc(doc)


def bulk_create_auth(students_data):
    for entry in students_data:
        phone      = entry["phone"]
        password   = entry["password"]
        student_id = entry["student_id"]
        avatar     = entry.get("avatar", "avatar_01")

        if not frappe.db.exists("Student Auth", {"phone": phone}):
            doc = frappe.new_doc("Student Auth")
            doc.phone = phone
            doc.failed_attempts = 0
            doc.is_locked = 0
            _insert_auth_doc(doc)
            frappe.db.commit()
            update_password(doc.name, password, doctype="Student Auth", fieldname="password")
            frappe.db.commit()
            doc.reload()
            profile_row = doc.append("students", {"student": student_id})
            profile_row.append("avatars", {"avatar_name": avatar})
            _save_auth_doc(doc)
        else:
            link_student_to_phone(phone, student_id, avatar)

    frappe.db.commit()
