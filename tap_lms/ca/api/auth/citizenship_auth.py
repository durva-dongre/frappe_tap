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
LOGIN_PROFILES_PAGE_SIZE = 10


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


def _password_exists(auth_name):
    return bool(frappe.db.sql(
        "SELECT 1 FROM \"__Auth\" WHERE doctype='Citizenship Auth' AND name=%s AND fieldname='password'",
        auth_name,
    ))


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


def _fetch_mentor_details(mentor_ref, mentor_type):
    if not mentor_ref or not mentor_type:
        return {"mentor_name": None}
    try:
        if mentor_type == "Teacher":
            row = frappe.db.sql(
                "SELECT first_name, last_name, school_id, district, state, language FROM \"tabTeacher\" WHERE name=%s LIMIT 1",
                mentor_ref,
                as_dict=True,
            )
            if not row:
                return {"mentor_name": None}
            parts = [row[0].first_name or "", row[0].last_name or ""]
            name = " ".join(p for p in parts if p).strip() or None
            return {
                "mentor_name": name,
                "school_id": row[0].school_id,
                "district_id": row[0].district,
                "state_id": row[0].state,
                "language": row[0].language,
            }
        row = frappe.db.sql(
            "SELECT name1, district, state, language FROM \"tabGuardian\" WHERE name=%s LIMIT 1",
            mentor_ref,
            as_dict=True,
        )
        if not row:
            return {"mentor_name": None}
        return {
            "mentor_name": row[0].name1,
            "district_id": row[0].district,
            "state_id": row[0].state,
            "language": row[0].language,
        }
    except Exception:
        return {"mentor_name": None}


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
        if frappe.db.sql("SELECT 1 FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1", phone):
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
def login_with_password(phone=None, password=None):
    phone = phone or frappe.form_dict.get("phone", "")
    password = password or frappe.form_dict.get("password")

    if not phone or not password:
        return {"success": False, "error": "invalid_credentials"}

    row = frappe.db.sql(
        "SELECT phone, admin_code, mentor_type, mentor FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    if not row or not _password_exists(phone):
        return {"success": False, "error": "invalid_credentials"}

    try:
        check_password(phone, password, doctype="Citizenship Auth", fieldname="password")
    except frappe.AuthenticationError:
        return {"success": False, "error": "invalid_credentials"}

    r = row[0]
    profiles, has_more = _fetch_profiles_sql(phone, page=1, page_size=LOGIN_PROFILES_PAGE_SIZE)
    result = {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "mentor_type": r.mentor_type,
        "profiles": profiles,
        "profiles_has_more": has_more,
        "page": 1,
        "page_size": LOGIN_PROFILES_PAGE_SIZE,
    }
    result.update(_fetch_mentor_details(r.mentor, r.mentor_type))
    if r.mentor:
        result["admin_code"] = r.admin_code
    return result


@frappe.whitelist(allow_guest=True)
def get_profiles(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    fd = frappe.form_dict
    page = int(fd.get("page", 1))
    page_size = min(int(fd.get("page_size", 50)), 50)

    payload, new_token = _require_access_token_with_refresh(phone)

    row = frappe.db.sql(
        "SELECT mentor_type, mentor FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1",
        phone,
        as_dict=True,
    )
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
    result.update(_fetch_mentor_details(row[0].mentor, row[0].mentor_type))
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
        SELECT citizenship_learner, student_name, roll_number, grade, avatar, student
        FROM "tabCitizenship Auth Profile"
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
            "learner_id": r.citizenship_learner,
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
    if not frappe.db.sql("SELECT 1 FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1", phone):
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
    if not frappe.db.sql("SELECT 1 FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1", phone):
        frappe.throw("Phone not registered", frappe.DoesNotExistError)
    update_password(phone, password, doctype="Citizenship Auth", fieldname="password")
    frappe.db.commit()
    profiles, has_more = _fetch_profiles_sql(phone)
    row = frappe.db.sql(
        "SELECT mentor_type, mentor FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    mentor_type = row[0].mentor_type if row else None
    mentor_ref = row[0].mentor if row else None
    result = {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "mentor_type": mentor_type,
        "profiles": profiles,
        "profiles_has_more": has_more,
    }
    result.update(_fetch_mentor_details(mentor_ref, mentor_type))
    return result