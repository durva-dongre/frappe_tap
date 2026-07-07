import frappe
import jwt
import datetime
import uuid
from frappe.utils.password import check_password, update_password
from tap_lms.tapapp.api.progress.learner import learner_full_state

OTP_EXPIRY_SECONDS = 600
REGISTRATION_TOKEN_EXPIRY_SECONDS = 1800
RESET_TOKEN_EXPIRY_SECONDS = 600
ACCESS_TOKEN_EXPIRY_SECONDS = 60 * 60 * 24 * 90
HARDCODED_OTP = "000000"
TOKEN_REFRESH_THRESHOLD_DAYS = 30
LOGIN_PROFILES_PAGE_SIZE = 10


def _get_jwt_secret():
    cache = frappe.cache()
    cached = cache.get_value("secret::tapapp_jwt_secret")
    if cached:
        return cached
    value = frappe.get_doc("Secrets", "tapapp_jwt_secret").get_password("value")
    cache.set_value("secret::tapapp_jwt_secret", value, expires_in_sec=3600)
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
    return datetime.datetime.utcfromtimestamp(exp) < (
        datetime.datetime.utcnow() + datetime.timedelta(days=TOKEN_REFRESH_THRESHOLD_DAYS)
    )


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
    new_token = _generate_access_token(phone) if _token_needs_refresh(payload) else None
    return payload, new_token


def _password_exists(phone):
    return bool(frappe.db.sql(
        "SELECT 1 FROM \"__Auth\" WHERE doctype='Tapapp Auth' AND name=%s AND fieldname='password'",
        phone,
    ))


def _use_hardcoded_otp():
    return frappe.conf.get("use_hardcoded_otp", True)


def _make_otp():
    if _use_hardcoded_otp():
        return HARDCODED_OTP
    import random
    return str(random.randint(100000, 999999))


def _ensure_tapapp_auth(phone, password=None):
    frappe.db.sql(
        """
        INSERT INTO "tabTapapp Auth" (name, phone, creation, modified, modified_by, owner)
        VALUES (%s, %s, NOW(), NOW(), 'Administrator', 'Administrator')
        ON CONFLICT (name) DO NOTHING
        """,
        (phone, phone),
    )
    frappe.db.commit()
    if password and not _password_exists(phone):
        update_password(phone, password, doctype="Tapapp Auth", fieldname="password")
        frappe.db.commit()


def _fetch_profiles_with_state(phone, page=1, page_size=50):
    offset = (page - 1) * page_size
    rows = frappe.db.sql(
        """
        SELECT tapapp_learner, student_name, roll_number, grade, avatar, student
        FROM "tabTapapp Auth Profile"
        WHERE parent = %s
        ORDER BY idx ASC
        LIMIT %s OFFSET %s
        """,
        (phone, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    profiles = []
    for r in rows[:page_size]:
        state = learner_full_state(r.tapapp_learner) if r.tapapp_learner else None
        profiles.append({
            "learner_id": r.tapapp_learner,
            "student_name": r.student_name,
            "grade": r.grade,
            "avatar": r.avatar,
            "roll_number": r.roll_number,
            "state": state,
        })
    return profiles, has_more


@frappe.whitelist(allow_guest=True)
def check_phone(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    row = frappe.db.sql(
        """
        SELECT phone,
               (SELECT 1 FROM "__Auth"
                WHERE doctype='Tapapp Auth'
                  AND name=ta.phone
                  AND fieldname='password'
                LIMIT 1) AS has_password
        FROM "tabTapapp Auth" ta
        WHERE phone = %s
        LIMIT 1
        """,
        phone,
        as_dict=True,
    )
    if not row:
        return {"exists": False, "has_password": False}
    return {"exists": True, "has_password": bool(row[0].has_password)}


@frappe.whitelist(allow_guest=True)
def send_otp(phone=None, context=None):
    phone = phone or frappe.form_dict.get("phone", "")
    context = context or frappe.form_dict.get("context", "register")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)

    if context == "register":
        if frappe.db.sql("SELECT 1 FROM \"tabTapapp Auth\" WHERE phone=%s LIMIT 1", phone):
            return {"success": False, "error": "phone_already_registered"}
    elif context == "add_profile":
        _require_access_token(phone)
    else:
        frappe.throw("Invalid context", frappe.ValidationError)

    otp = _make_otp()
    frappe.cache().set_value(f"tapapp_otp::{phone}", otp, expires_in_sec=OTP_EXPIRY_SECONDS)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def verify_otp(phone=None, otp=None):
    phone = phone or frappe.form_dict.get("phone", "")
    otp = otp or frappe.form_dict.get("otp")
    if not phone or not otp:
        frappe.throw("phone and otp are required", frappe.ValidationError)
    stored = frappe.cache().get_value(f"tapapp_otp::{phone}")
    if not stored:
        return {"success": False, "error": "otp_expired"}
    if stored != otp:
        return {"success": False, "error": "otp_invalid"}
    frappe.cache().delete_value(f"tapapp_otp::{phone}")
    return {"success": True, "registration_token": _generate_registration_token(phone), "phone": phone}


@frappe.whitelist(allow_guest=True)
def login_with_password(phone=None, password=None):
    phone = phone or frappe.form_dict.get("phone", "")
    password = password or frappe.form_dict.get("password")

    if not phone or not password:
        return {"success": False, "error": "invalid_credentials"}

    if not frappe.db.sql("SELECT 1 FROM \"tabTapapp Auth\" WHERE phone=%s LIMIT 1", phone) or not _password_exists(phone):
        return {"success": False, "error": "invalid_credentials"}

    try:
        check_password(phone, password, doctype="Tapapp Auth", fieldname="password")
    except frappe.AuthenticationError:
        return {"success": False, "error": "invalid_credentials"}

    profiles, has_more = _fetch_profiles_with_state(phone, page=1, page_size=LOGIN_PROFILES_PAGE_SIZE)
    return {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "profiles": profiles,
        "profiles_has_more": has_more,
        "page": 1,
        "page_size": LOGIN_PROFILES_PAGE_SIZE,
    }


@frappe.whitelist(allow_guest=True)
def get_profiles(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    fd = frappe.form_dict
    page = int(fd.get("page", 1))
    page_size = min(int(fd.get("page_size", 50)), 50)

    payload, new_token = _require_access_token_with_refresh(phone)

    if not frappe.db.sql("SELECT 1 FROM \"tabTapapp Auth\" WHERE phone=%s LIMIT 1", phone):
        frappe.throw("Phone not registered", frappe.DoesNotExistError)

    profiles, has_more = _fetch_profiles_with_state(phone, page=page, page_size=page_size)
    result = {
        "phone": phone,
        "profiles": profiles,
        "profiles_has_more": has_more,
        "page": page,
        "page_size": page_size,
    }
    if new_token:
        result["token"] = new_token
    return result


@frappe.whitelist(allow_guest=True)
def search_profiles(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    fd = frappe.form_dict
    grade = fd.get("grade")
    roll_number = fd.get("roll_number")
    query = fd.get("query")
    page = int(fd.get("page", 1))
    page_size = min(int(fd.get("page_size", 20)), 50)
    offset = (page - 1) * page_size

    _require_access_token(phone)

    conditions = ["parent = %s"]
    params = [phone]
    if grade:
        conditions.append("grade = %s")
        params.append(grade)
    if roll_number:
        conditions.append("roll_number = %s")
        params.append(roll_number)
    if query:
        conditions.append("student_name LIKE %s")
        params.append(f"%{query}%")

    where_clause = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT tapapp_learner, student_name, roll_number, grade, avatar, student
        FROM "tabTapapp Auth Profile"
        WHERE {where_clause}
        ORDER BY idx ASC
        LIMIT %s OFFSET %s
        """,
        (*params, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    profiles = [
        {
            "learner_id": r.tapapp_learner,
            "student_name": r.student_name,
            "grade": r.grade,
            "avatar": r.avatar,
            "roll_number": r.roll_number,
        }
        for r in rows[:page_size]
    ]
    return {
        "phone": phone,
        "profiles": profiles,
        "profiles_has_more": has_more,
        "page": page,
        "page_size": page_size,
    }


@frappe.whitelist(allow_guest=True)
def forgot_password_send_otp(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    if not frappe.db.sql("SELECT 1 FROM \"tabTapapp Auth\" WHERE phone=%s LIMIT 1", phone):
        return {"success": False, "error": "phone_not_registered"}
    otp = _make_otp()
    frappe.cache().set_value(f"tapapp_otp_reset::{phone}", otp, expires_in_sec=OTP_EXPIRY_SECONDS)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def forgot_password_verify_otp(phone=None, otp=None):
    phone = phone or frappe.form_dict.get("phone", "")
    otp = otp or frappe.form_dict.get("otp")
    if not phone or not otp:
        frappe.throw("phone and otp are required", frappe.ValidationError)
    stored = frappe.cache().get_value(f"tapapp_otp_reset::{phone}")
    if not stored:
        return {"success": False, "error": "otp_expired"}
    if stored != otp:
        return {"success": False, "error": "otp_invalid"}
    frappe.cache().delete_value(f"tapapp_otp_reset::{phone}")
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
    if not frappe.db.sql("SELECT 1 FROM \"tabTapapp Auth\" WHERE phone=%s LIMIT 1", phone):
        frappe.throw("Phone not registered", frappe.DoesNotExistError)
    update_password(phone, password, doctype="Tapapp Auth", fieldname="password")
    frappe.db.commit()
    profiles, has_more = _fetch_profiles_with_state(phone)
    return {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "profiles": profiles,
        "profiles_has_more": has_more,
    }
