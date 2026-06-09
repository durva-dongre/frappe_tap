import frappe
import jwt
import datetime
import uuid
from frappe.utils.password import check_password, update_password

OTP_EXPIRY_SECONDS = 600
REGISTRATION_TOKEN_EXPIRY_SECONDS = 1800
RESET_TOKEN_EXPIRY_SECONDS = 600
INVITE_TOKEN_EXPIRY_SECONDS = 604800
ACCESS_TOKEN_EXPIRY_SECONDS = 60 * 60 * 24 * 90
HARDCODED_OTP = "000000"
TOKEN_REFRESH_THRESHOLD_DAYS = 30


def _get_jwt_secret():
    cache = frappe.cache()
    cached = cache.get_value("secret::jwt_secret")
    if cached:
        return cached
    value = frappe.get_doc("Secrets", "jwt_secret").get_password("value")
    cache.set_value("secret::jwt_secret", value, expires_in_sec=3600)
    return value


def _generate_access_token(phone):
    now = datetime.datetime.utcnow()
    return jwt.encode(
        {
            "phone": phone,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + datetime.timedelta(seconds=ACCESS_TOKEN_EXPIRY_SECONDS),
        },
        _get_jwt_secret(),
        algorithm="HS256",
    )


def _generate_registration_token(phone):
    now = datetime.datetime.utcnow()
    return jwt.encode(
        {
            "phone": phone,
            "type": "registration",
            "exp": now + datetime.timedelta(seconds=REGISTRATION_TOKEN_EXPIRY_SECONDS),
            "iat": now,
        },
        _get_jwt_secret(),
        algorithm="HS256",
    )


def _generate_reset_token(phone):
    now = datetime.datetime.utcnow()
    return jwt.encode(
        {
            "phone": phone,
            "type": "reset",
            "exp": now + datetime.timedelta(seconds=RESET_TOKEN_EXPIRY_SECONDS),
            "iat": now,
        },
        _get_jwt_secret(),
        algorithm="HS256",
    )


def _generate_invite_token(teacher_auth_name, grade, class_id, start_roll, end_roll):
    now = datetime.datetime.utcnow()
    return jwt.encode(
        {
            "teacher_auth_name": teacher_auth_name,
            "grade": grade,
            "class_id": class_id,
            "start_roll": start_roll,
            "end_roll": end_roll,
            "type": "invite",
            "exp": now + datetime.timedelta(seconds=INVITE_TOKEN_EXPIRY_SECONDS),
            "iat": now,
        },
        _get_jwt_secret(),
        algorithm="HS256",
    )


def _decode_token(token, expected_type):
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
        return payload if payload.get("type") == expected_type else None
    except Exception:
        return None


def _bearer_token():
    for header in ("X-Flutter-Authorization", "Authorization"):
        value = frappe.get_request_header(header, "")
        if value.startswith("Bearer "):
            return value[7:]
    return None


def _token_needs_refresh(payload):
    exp = payload.get("exp")
    if not exp:
        return False
    exp_dt = datetime.datetime.utcfromtimestamp(exp)
    threshold = datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_REFRESH_THRESHOLD_DAYS)
    return exp_dt < threshold


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


def _require_access_token_with_refresh(phone):
    payload = _require_access_token(phone)
    new_token = None
    if _token_needs_refresh(payload):
        new_token = _generate_access_token(phone)
    return payload, new_token


def _password_exists(auth_name):
    result = frappe.db.sql(
        "SELECT 1 FROM \"__Auth\" WHERE doctype='Citizenship Auth' AND name=%s AND fieldname='password'",
        auth_name,
    )
    return bool(result)


def _use_hardcoded_otp():
    return frappe.conf.get("use_hardcoded_otp", True)


def _make_otp():
    if _use_hardcoded_otp():
        return HARDCODED_OTP
    import random
    return str(random.randint(100000, 999999))


def _fetch_profiles_sql(phone, page=1, page_size=50):
    offset = (page - 1) * page_size
    rows = frappe.db.sql(
        """
        SELECT citizenship_learner, student_name, roll_number, grade, avatar, student
        FROM "tabCitizenship Auth Profile"
        WHERE parent = %s
        ORDER BY idx ASC
        LIMIT %s OFFSET %s
        """,
        (phone, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    profiles = [
        {
            "learner_id": r.citizenship_learner,
            "student_name": r.student_name,
            "grade": r.grade,
            "avatar": r.avatar,
            "roll_number": r.roll_number,
        }
        for r in rows[:page_size]
    ]
    return profiles, has_more


def _ensure_citizenship_auth(phone, password=None):
    frappe.db.sql(
        """
        INSERT INTO "tabCitizenship Auth" (name, phone, creation, modified, modified_by, owner)
        VALUES (%s, %s, NOW(), NOW(), 'Administrator', 'Administrator')
        ON CONFLICT (name) DO NOTHING
        """,
        (phone, phone),
    )
    frappe.db.commit()
    if password and not _password_exists(phone):
        update_password(phone, password, doctype="Citizenship Auth", fieldname="password")
        frappe.db.commit()


@frappe.whitelist(allow_guest=True)
def check_phone(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    row = frappe.db.sql(
        """
        SELECT phone, admin_code, mentor_type, mentor,
               (SELECT 1 FROM "__Auth"
                WHERE doctype='Citizenship Auth'
                  AND name=ca.phone
                  AND fieldname='password'
                LIMIT 1) AS has_password
        FROM "tabCitizenship Auth" ca
        WHERE phone = %s
        LIMIT 1
        """,
        phone,
        as_dict=True,
    )
    if not row:
        return {"exists": False, "has_password": False, "has_mentor": False, "mentor_type": None, "admin_code_set": False}
    r = row[0]
    return {
        "exists": True,
        "has_password": bool(r.has_password),
        "has_mentor": bool(r.mentor),
        "mentor_type": r.mentor_type,
        "admin_code_set": bool(r.admin_code),
    }


@frappe.whitelist(allow_guest=True)
def send_otp(phone=None, context=None):
    phone = phone or frappe.form_dict.get("phone", "")
    context = context or frappe.form_dict.get("context", "register")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)

    if context == "register":
        exists = frappe.db.sql("SELECT 1 FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1", phone)
        if exists:
            return {"success": False, "error": "phone_already_registered"}
    elif context == "add_profile":
        _require_access_token(phone)
    else:
        frappe.throw("Invalid context", frappe.ValidationError)

    otp = _make_otp()
    frappe.cache().set_value(f"otp::{phone}", otp, expires_in_sec=OTP_EXPIRY_SECONDS)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def verify_otp(phone=None, otp=None):
    phone = phone or frappe.form_dict.get("phone", "")
    otp = otp or frappe.form_dict.get("otp")
    if not phone or not otp:
        frappe.throw("phone and otp are required", frappe.ValidationError)
    stored = frappe.cache().get_value(f"otp::{phone}")
    if not stored:
        return {"success": False, "error": "otp_expired"}
    if stored != otp:
        return {"success": False, "error": "otp_invalid"}
    frappe.cache().delete_value(f"otp::{phone}")
    return {"success": True, "registration_token": _generate_registration_token(phone), "phone": phone}


@frappe.whitelist(allow_guest=True)
def login_with_password(phone=None, password=None, admin_code=None):
    phone = phone or frappe.form_dict.get("phone", "")
    password = password or frappe.form_dict.get("password")
    admin_code = admin_code or frappe.form_dict.get("admin_code")

    if not phone or not password:
        return {"success": False, "error": "invalid_credentials"}

    row = frappe.db.sql(
        "SELECT phone, admin_code, mentor_type, mentor FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    if not row:
        return {"success": False, "error": "invalid_credentials"}

    r = row[0]
    if r.admin_code and admin_code != r.admin_code:
        return {"success": False, "error": "invalid_admin_code"}

    if not _password_exists(phone):
        return {"success": False, "error": "invalid_credentials"}

    try:
        check_password(phone, password, doctype="Citizenship Auth", fieldname="password")
    except frappe.AuthenticationError:
        return {"success": False, "error": "invalid_credentials"}

    profiles, has_more = _fetch_profiles_sql(phone)
    return {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "mentor_type": r.mentor_type,
        "profiles": profiles,
        "profiles_has_more": has_more,
    }


@frappe.whitelist(allow_guest=True)
def get_profiles(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    fd = frappe.form_dict
    page = int(fd.get("page", 1))
    page_size = min(int(fd.get("page_size", 50)), 50)

    payload, new_token = _require_access_token_with_refresh(phone)

    row = frappe.db.sql("SELECT mentor_type FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1", phone, as_dict=True)
    if not row:
        frappe.throw("Phone not registered", frappe.DoesNotExistError)

    profiles, has_more = _fetch_profiles_sql(phone, page=page, page_size=page_size)
    result = {
        "phone": phone,
        "mentor_type": row[0].mentor_type,
        "profiles": profiles,
        "profiles_has_more": has_more,
        "page": page,
        "page_size": page_size,
    }
    if new_token:
        result["token"] = new_token
    return result


@frappe.whitelist(allow_guest=True)
def forgot_password_send_otp(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    exists = frappe.db.sql("SELECT 1 FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1", phone)
    if not exists:
        return {"success": False, "error": "phone_not_registered"}
    otp = _make_otp()
    frappe.cache().set_value(f"otp_reset::{phone}", otp, expires_in_sec=OTP_EXPIRY_SECONDS)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def forgot_password_verify_otp(phone=None, otp=None):
    phone = phone or frappe.form_dict.get("phone", "")
    otp = otp or frappe.form_dict.get("otp")
    if not phone or not otp:
        frappe.throw("phone and otp are required", frappe.ValidationError)
    stored = frappe.cache().get_value(f"otp_reset::{phone}")
    if not stored:
        return {"success": False, "error": "otp_expired"}
    if stored != otp:
        return {"success": False, "error": "otp_invalid"}
    frappe.cache().delete_value(f"otp_reset::{phone}")
    return {"success": True, "reset_token": _generate_reset_token(phone), "phone": phone}


@frappe.whitelist(allow_guest=True)
def reset_password(phone=None, password=None):
    phone = phone or frappe.form_dict.get("phone", "")
    password = password or frappe.form_dict.get("password")
    if not password or len(password) < 6:
        frappe.throw("password must be at least 6 characters", frappe.ValidationError)
    token = _bearer_token()
    if not token:
        frappe.throw("Missing token", frappe.AuthenticationError)
    payload = _decode_token(token, "reset")
    if not payload:
        frappe.throw("Invalid or expired reset token", frappe.AuthenticationError)
    if payload.get("phone") != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)
    exists = frappe.db.sql("SELECT 1 FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1", phone)
    if not exists:
        frappe.throw("Phone not registered", frappe.DoesNotExistError)
    update_password(phone, password, doctype="Citizenship Auth", fieldname="password")
    frappe.db.commit()
    profiles, has_more = _fetch_profiles_sql(phone)
    mentor_type = frappe.db.get_value("Citizenship Auth", phone, "mentor_type")
    return {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "mentor_type": mentor_type,
        "profiles": profiles,
        "profiles_has_more": has_more,
    }