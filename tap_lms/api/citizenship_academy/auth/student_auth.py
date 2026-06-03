import frappe
import jwt
import datetime
from frappe.utils.password import check_password

JWT_EXPIRY_HOURS = 72
MAX_ATTEMPTS = 5


def _normalize_phone(phone):
    if not phone:
        return ""
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def _get_secret(key):
    cache = frappe.cache()
    cached = cache.get_value(f"secret::{key}")
    if cached:
        return cached
    value = frappe.get_doc("Secrets", key).get_password("value")
    cache.set_value(f"secret::{key}", value)
    return value


def _get_jwt_secret():
    return _get_secret("jwt_secret")


def _generate_access_token(phone, student_ids):
    payload = {
        "phone": phone,
        "students": student_ids,
        "type": "access",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def _extract_bearer_token():
    for header in ("X-Flutter-Authorization", "Authorization"):
        value = frappe.get_request_header(header, "")
        if value.startswith("Bearer "):
            return value[7:]
    return None


def _decode_access_token(token):
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return payload
    except Exception:
        return None


def _get_avatar_path(avatar_key):
    if not avatar_key:
        return "assets/avatars/avatar_01.png"
    path = frappe.db.get_value("Student Avatar", avatar_key, "avatar_path")
    return path or "assets/avatars/avatar_01.png"


def _get_profiles_for_phone(phone):
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    if not auth_name:
        return []
    doc = frappe.get_doc("Student Auth", auth_name)
    profiles = []
    for row in doc.students:
        student_data = frappe.db.get_value(
            "Student",
            row.student,
            ["name1", "gender", "grade", "status"],
            as_dict=True,
        )
        profiles.append({
            "student_id": row.student,
            "name": student_data.name1 if student_data else row.student,
            "avatar": _get_avatar_path(row.avatar),
            "gender": student_data.gender if student_data else None,
            "grade": student_data.grade if student_data else None,
            "status": student_data.status if student_data else None,
        })
    return profiles


@frappe.whitelist(allow_guest=True)
def check_phone(phone=None):
    phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    return {"exists": bool(frappe.db.exists("Student Auth", {"phone": phone}))}


@frappe.whitelist(allow_guest=True)
def login_with_password(phone=None, password=None):
    phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
    password = password or frappe.form_dict.get("password")
    if not phone or not password:
        return {"success": False, "error": "invalid_credentials"}

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
        return {"success": False, "error": "account_locked", "locked_until": str(doc.locked_until)}

    try:
        check_password(auth.name, password, doctype="Student Auth", fieldname="password")
    except frappe.AuthenticationError:
        doc.increment_failed()
        remaining = max(0, MAX_ATTEMPTS - doc.failed_attempts)
        return {"success": False, "error": "invalid_credentials", "attempts_remaining": remaining}

    doc.reset_lock()
    all_students = [row.student for row in doc.students]
    token = _generate_access_token(phone, all_students)
    profiles = _get_profiles_for_phone(phone)
    return {"success": True, "token": token, "phone": phone, "profiles": profiles}
