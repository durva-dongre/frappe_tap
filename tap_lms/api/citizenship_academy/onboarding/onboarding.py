import frappe
import jwt
import datetime
import hashlib
import random
import string
import requests

from frappe.utils.password import update_password, check_password

JWT_EXPIRY_HOURS = 72
REGISTRATION_TOKEN_EXPIRY_MINUTES = 30
OTP_EXPIRY_MINUTES = 10
HARDCODED_OTP = "000000"

VALID_GENDERS = {"Male", "Female", "Others", "Not Available"}
VALID_SCHOOL_TYPES = {"APS", "GOVT", "NGO", "PPP", "PMC", "PVT", "GOVT. Aided", "ORG"}
VALID_AVATARS = {f"avatar_{i:02d}" for i in range(1, 31)}
AVATAR_DEFAULTS = sorted(VALID_AVATARS)


def _get_secret(key):
    cache = frappe.cache()
    cached = cache.get_value(f"secret::{key}")
    if cached:
        return cached
    secret_doc = frappe.get_doc("Secrets", key)
    value = secret_doc.get_password("value")
    cache.set_value(f"secret::{key}", value)
    return value


def _get_jwt_secret():
    return _get_secret("jwt_secret")


def _get_reg_secret():
    return _get_secret("registration_secret")


def _generate_jwt(phone, student_ids):
    payload = {
        "phone": phone,
        "students": student_ids,
        "type": "access",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def _generate_registration_token(phone):
    payload = {
        "phone": phone,
        "type": "registration",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=REGISTRATION_TOKEN_EXPIRY_MINUTES),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, _get_reg_secret(), algorithm="HS256")


def _decode_jwt(token, secret):
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None


def _decode_registration_token(token):
    payload = _decode_jwt(token, _get_reg_secret())
    if not payload or payload.get("type") != "registration":
        return None
    return payload


def _decode_access_token(token):
    payload = _decode_jwt(token, _get_jwt_secret())
    if not payload or payload.get("type") != "access":
        return None
    return payload


def _extract_bearer_token():
    for header in ("X-Flutter-Authorization", "Authorization"):
        value = frappe.get_request_header(header, "")
        if value.startswith("Bearer "):
            return value[7:]
    return None


def _require_registration_token():
    token = _extract_bearer_token()
    if not token:
        frappe.throw("Missing registration token", frappe.AuthenticationError)
    payload = _decode_registration_token(token)
    if not payload:
        frappe.throw("Invalid or expired registration token", frappe.AuthenticationError)
    return payload


def _require_access_token():
    token = _extract_bearer_token()
    if not token:
        frappe.throw("Missing token", frappe.AuthenticationError)
    payload = _decode_access_token(token)
    if not payload:
        frappe.throw("Invalid or expired token", frappe.AuthenticationError)
    return payload


def _store_otp(phone):
    cache = frappe.cache()
    cache.set_value(f"otp::{phone}", HARDCODED_OTP, expires_in_sec=OTP_EXPIRY_MINUTES * 60)


def _verify_otp_peek(phone, otp):
    cache = frappe.cache()
    stored = cache.get_value(f"otp::{phone}")
    if not stored:
        return False, "otp_expired"
    if stored != otp:
        return False, "otp_invalid"
    return True, None


def _verify_otp(phone, otp):
    valid, reason = _verify_otp_peek(phone, otp)
    if valid:
        frappe.cache().delete_value(f"otp::{phone}")
    return valid, reason


def _random_avatar():
    return random.choice(AVATAR_DEFAULTS)


def _sync_student_to_leaderboard(student_id, display_name, state, district, school_id):
    try:
        worker_url = _get_secret("cf_worker_url")
        worker_secret = _get_secret("cf_worker_secret")

        school_data = frappe.db.get_value(
            "School",
            school_id,
            ["name1", "city", "type"],
            as_dict=True,
        )

        state_data = frappe.db.get_value("State", state, "state_name", as_dict=True)
        district_data = frappe.db.get_value("District", district, "district_name", as_dict=True)

        payload = {
            "student_id": student_id,
            "name": display_name,
            "state_id": state,
            "state_name": state_data.state_name if state_data else state,
            "district_id": district,
            "district_name": district_data.district_name if district_data else district,
            "school_id": school_id,
            "school_name": school_data.name1 if school_data else school_id,
            "city": school_data.city if school_data else None,
        }

        headers = {
            "Content-Type": "application/json",
            "X-Worker-Secret": worker_secret,
        }

        response = requests.post(
            f"{worker_url}/students/register",
            json=payload,
            headers=headers,
            timeout=5,
        )

        if not response.ok:
            frappe.log_error(
                title="Leaderboard Sync Failed",
                message=f"Student: {student_id} | Status: {response.status_code} | Body: {response.text}",
            )

    except Exception:
        frappe.log_error(
            title="Leaderboard Sync Error",
            message=frappe.get_traceback(),
        )


@frappe.whitelist(allow_guest=True)
def check_phone(phone=None):
    phone = phone or frappe.form_dict.get("phone")
    exists = frappe.db.exists("Student Auth", phone)
    return {"exists": bool(exists)}


@frappe.whitelist(allow_guest=True)
def register_send_otp(phone=None, password=None):
    phone    = phone    or frappe.form_dict.get("phone")
    password = password or frappe.form_dict.get("password")

    if not password:
        frappe.throw("Password is required")
    exists = frappe.db.exists("Student Auth", phone)
    if exists:
        return {"success": False, "error": "phone_already_registered"}

    cache = frappe.cache()
    cache.set_value(f"pending_reg_raw::{phone}", password, expires_in_sec=OTP_EXPIRY_MINUTES * 60)
    _store_otp(phone)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def register_verify_otp(phone=None, otp=None):
    phone = phone or frappe.form_dict.get("phone")
    otp   = otp   or frappe.form_dict.get("otp")

    cache = frappe.cache()
    raw_pass = cache.get_value(f"pending_reg_raw::{phone}")
    if not raw_pass:
        return {"success": False, "error": "registration_session_expired"}

    valid, reason = _verify_otp_peek(phone, otp)
    if not valid:
        return {"success": False, "error": reason}

    if not frappe.db.exists("Student Auth", phone):
        doc = frappe.get_doc({
            "doctype": "Student Auth",
            "phone": phone,
            "failed_attempts": 0,
            "is_locked": 0,
        })
        doc.insert(ignore_permissions=True, ignore_mandatory=True)
        update_password(phone, raw_pass, doctype="Student Auth", fieldname="password")
        frappe.db.commit()

    cache.delete_value(f"otp::{phone}")
    cache.delete_value(f"pending_reg_raw::{phone}")

    reg_token = _generate_registration_token(phone)
    return {"success": True, "registration_token": reg_token, "phone": phone}


@frappe.whitelist(allow_guest=True)
def login_send_otp(phone=None):
    phone = phone or frappe.form_dict.get("phone")
    if not frappe.db.exists("Student Auth", phone):
        return {"success": False, "error": "phone_not_found"}
    _store_otp(phone)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def login_verify_otp(phone=None, otp=None):
    phone = phone or frappe.form_dict.get("phone")
    otp   = otp   or frappe.form_dict.get("otp")

    if not frappe.db.exists("Student Auth", phone):
        return {"success": False, "error": "phone_not_found"}

    valid, reason = _verify_otp(phone, otp)
    if not valid:
        return {"success": False, "error": reason}

    reg_token = _generate_registration_token(phone)
    return {"success": True, "registration_token": reg_token, "phone": phone}


@frappe.whitelist(allow_guest=True)
def login_with_password(phone=None, password=None):
    phone    = phone    or frappe.form_dict.get("phone")
    password = password or frappe.form_dict.get("password")

    from tap_lms.api.citizenship_academy.auth.student_auth import MAX_ATTEMPTS
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
        check_password(phone, password, doctype="Student Auth", fieldname="password")
    except frappe.AuthenticationError:
        doc.increment_failed()
        remaining = max(0, MAX_ATTEMPTS - doc.failed_attempts)
        return {"success": False, "error": "invalid_credentials", "attempts_remaining": remaining}

    doc.reset_lock()

    profiles = _get_profiles_for_phone(phone)
    students = [p["student_id"] for p in profiles]
    token = _generate_jwt(phone, students)

    return {"success": True, "token": token, "phone": phone, "profiles": profiles}


def _get_profiles_for_phone(phone):
    doc = frappe.get_doc("Student Auth", phone)
    profiles = []
    for row in doc.students:
        student_data = frappe.db.get_value(
            "Student",
            row.student,
            ["name1", "gender", "grade", "school_id", "language", "status"],
            as_dict=True,
        )
        profiles.append({
            "student_id": row.student,
            "name":       student_data.name1   if student_data else row.student_name,
            "avatar":     row.avatar or "avatar_01",
            "gender":     student_data.gender  if student_data else None,
            "grade":      student_data.grade   if student_data else None,
            "status":     student_data.status  if student_data else None,
        })
    return profiles


@frappe.whitelist(allow_guest=True)
def get_profiles(phone=None):
    phone = phone or frappe.form_dict.get("phone")

    token          = _extract_bearer_token()
    reg_payload    = _decode_registration_token(token) if token else None
    access_payload = _decode_access_token(token)       if token else None

    if not reg_payload and not access_payload:
        frappe.throw("Invalid or missing token", frappe.AuthenticationError)

    authenticated_phone = (reg_payload or access_payload).get("phone")
    if authenticated_phone != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)

    if not frappe.db.exists("Student Auth", phone):
        frappe.throw("Phone not registered", frappe.DoesNotExistError)

    profiles = _get_profiles_for_phone(phone)
    return {"phone": phone, "profiles": profiles}


@frappe.whitelist(allow_guest=True)
def create_profile(
    display_name=None,
    gender=None,
    grade=None,
    state=None,
    district=None,
    school_id=None,
    language=None,
    avatar=None,
    dob=None,
    migrate_student_id=None,
):
    display_name       = display_name       or frappe.form_dict.get("display_name")
    gender             = gender             or frappe.form_dict.get("gender")
    grade              = grade              or frappe.form_dict.get("grade")
    state              = state              or frappe.form_dict.get("state")
    district           = district           or frappe.form_dict.get("district")
    school_id          = school_id          or frappe.form_dict.get("school_id")
    language           = language           or frappe.form_dict.get("language")
    avatar             = avatar             or frappe.form_dict.get("avatar")
    dob                = dob                or frappe.form_dict.get("dob")
    migrate_student_id = migrate_student_id or frappe.form_dict.get("migrate_student_id")

    payload = _require_registration_token()
    phone = payload["phone"]

    if not frappe.db.exists("Student Auth", phone):
        frappe.throw("Phone not registered")

    if gender not in VALID_GENDERS:
        frappe.throw("Invalid gender value")

    if not frappe.db.exists("State", state):
        frappe.throw("State not found")

    if not frappe.db.exists("District", district):
        frappe.throw("District not found")

    if not frappe.db.exists("School", school_id):
        frappe.throw("School not found")

    if not frappe.db.exists("TAP Language", language):
        frappe.throw("Language not found")

    resolved_avatar = avatar if avatar in VALID_AVATARS else _random_avatar()

    if migrate_student_id:
        student_id = _migrate_student(phone, migrate_student_id, resolved_avatar)
        _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)
        return _complete_profile_response(phone, student_id)

    student = frappe.get_doc({
        "doctype": "Student",
        "name1":     display_name,
        "phone":     phone,
        "gender":    gender,
        "grade":     grade,
        "school_id": school_id,
        "language":  language,
        "status":    "active",
        **({"dob": dob} if dob else {}),
    })
    student.insert(ignore_permissions=True)
    student_id = student.name

    auth_doc = frappe.get_doc("Student Auth", phone)
    existing_ids = [row.student for row in auth_doc.students]
    if student_id not in existing_ids:
        auth_doc.append("students", {
            "student": student_id,
            "avatar":  resolved_avatar,
        })
        auth_doc.save(ignore_permissions=True)

    frappe.db.commit()

    _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)

    return _complete_profile_response(phone, student_id)


def _migrate_student(phone, student_id, avatar):
    if not frappe.db.exists("Student", student_id):
        frappe.throw("Student to migrate not found")

    auth_doc = frappe.get_doc("Student Auth", phone)
    existing_ids = [row.student for row in auth_doc.students]
    if student_id not in existing_ids:
        auth_doc.append("students", {
            "student": student_id,
            "avatar":  avatar,
        })
        auth_doc.save(ignore_permissions=True)
        frappe.db.commit()

    return student_id


def _complete_profile_response(phone, student_id):
    auth_doc = frappe.get_doc("Student Auth", phone)
    all_students = [row.student for row in auth_doc.students]
    token = _generate_jwt(phone, all_students)
    profiles = _get_profiles_for_phone(phone)

    return {
        "success":        True,
        "token":          token,
        "phone":          phone,
        "new_student_id": student_id,
        "profiles":       profiles,
    }


@frappe.whitelist(allow_guest=True)
def add_profile(
    phone=None,
    display_name=None,
    gender=None,
    grade=None,
    state=None,
    district=None,
    school_id=None,
    language=None,
    avatar=None,
    dob=None,
    migrate_student_id=None,
):
    phone              = phone              or frappe.form_dict.get("phone")
    display_name       = display_name       or frappe.form_dict.get("display_name")
    gender             = gender             or frappe.form_dict.get("gender")
    grade              = grade              or frappe.form_dict.get("grade")
    state              = state              or frappe.form_dict.get("state")
    district           = district           or frappe.form_dict.get("district")
    school_id          = school_id          or frappe.form_dict.get("school_id")
    language           = language           or frappe.form_dict.get("language")
    avatar             = avatar             or frappe.form_dict.get("avatar")
    dob                = dob                or frappe.form_dict.get("dob")
    migrate_student_id = migrate_student_id or frappe.form_dict.get("migrate_student_id")

    payload = _require_access_token()
    if payload["phone"] != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)

    if gender not in VALID_GENDERS:
        frappe.throw("Invalid gender value")

    if not frappe.db.exists("School", school_id):
        frappe.throw("School not found")

    if not frappe.db.exists("TAP Language", language):
        frappe.throw("Language not found")

    resolved_avatar = avatar if avatar in VALID_AVATARS else _random_avatar()

    if migrate_student_id:
        student_id = _migrate_student(phone, migrate_student_id, resolved_avatar)
        _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)
        return _complete_profile_response(phone, student_id)

    student = frappe.get_doc({
        "doctype": "Student",
        "name1":     display_name,
        "phone":     phone,
        "gender":    gender,
        "grade":     grade,
        "school_id": school_id,
        "language":  language,
        "status":    "active",
        **({"dob": dob} if dob else {}),
    })
    student.insert(ignore_permissions=True)
    student_id = student.name

    auth_doc = frappe.get_doc("Student Auth", phone)
    existing_ids = [row.student for row in auth_doc.students]
    if student_id not in existing_ids:
        auth_doc.append("students", {
            "student": student_id,
            "avatar":  resolved_avatar,
        })
        auth_doc.save(ignore_permissions=True)

    frappe.db.commit()

    _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)

    return _complete_profile_response(phone, student_id)


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, student_id=None):
    phone      = phone      or frappe.form_dict.get("phone")
    student_id = student_id or frappe.form_dict.get("student_id")

    token          = _extract_bearer_token()
    reg_payload    = _decode_registration_token(token) if token else None
    access_payload = _decode_access_token(token)       if token else None

    payload = reg_payload or access_payload
    if not payload:
        frappe.throw("Invalid or missing token", frappe.AuthenticationError)
    if payload.get("phone") != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)

    doc = frappe.get_doc("Student Auth", phone)
    linked_ids = [row.student for row in doc.students]
    if student_id not in linked_ids:
        frappe.throw("Profile not linked to this phone", frappe.AuthenticationError)

    token = _generate_jwt(phone, linked_ids)
    profiles = _get_profiles_for_phone(phone)
    current = next((p for p in profiles if p["student_id"] == student_id), None)

    return {
        "success":        True,
        "token":          token,
        "phone":          phone,
        "active_profile": current,
        "profiles":       profiles,
    }


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, student_id=None, avatar=None):
    phone      = phone      or frappe.form_dict.get("phone")
    student_id = student_id or frappe.form_dict.get("student_id")
    avatar     = avatar     or frappe.form_dict.get("avatar")

    payload = _require_access_token()
    if payload["phone"] != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)

    if avatar not in VALID_AVATARS:
        frappe.throw("Invalid avatar")

    doc = frappe.get_doc("Student Auth", phone)
    updated = False
    for row in doc.students:
        if row.student == student_id:
            row.avatar = avatar
            updated = True
            break

    if not updated:
        frappe.throw("Profile not found on this account")

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "avatar": avatar}


@frappe.whitelist(allow_guest=True)
def get_states():
    states = frappe.get_all(
        "State",
        fields=["name as id", "state_name as name"],
        order_by="state_name asc",
    )
    return {"states": states}


@frappe.whitelist(allow_guest=True)
def get_districts(state=None):
    state = state or frappe.form_dict.get("state")
    if not state:
        frappe.throw("state is required", frappe.ValidationError)
    if not frappe.db.exists("State", state):
        frappe.throw("State not found", frappe.DoesNotExistError)
    districts = frappe.get_all(
        "District",
        filters={"state": state},
        fields=["name as id", "district_name as name"],
        order_by="district_name asc",
    )
    return {"state": state, "districts": districts}


@frappe.whitelist(allow_guest=True)
def get_schools(district=None, search=None):
    district = district or frappe.form_dict.get("district")
    search   = search   or frappe.form_dict.get("search", "")
    if not district:
        frappe.throw("district is required", frappe.ValidationError)
    if not frappe.db.exists("District", district):
        frappe.throw("District not found", frappe.DoesNotExistError)
    filters = {"district": district}
    if search:
        filters["name1"] = ["like", f"%{search}%"]
    schools = frappe.get_all(
        "School",
        filters=filters,
        fields=["name as id", "name1 as name", "type", "city"],
        order_by="name1 asc",
        limit=50,
    )
    return {"district": district, "schools": schools}


@frappe.whitelist(allow_guest=True)
def create_school(name=None, district=None, type="GOVT"):
    name     = name     or frappe.form_dict.get("name")
    district = district or frappe.form_dict.get("district")
    type     = type     or frappe.form_dict.get("type", "GOVT")

    if type not in VALID_SCHOOL_TYPES:
        frappe.throw("Invalid school type")
    if not frappe.db.exists("District", district):
        frappe.throw("District not found")
    existing = frappe.db.get_value("School", {"name1": name, "district": district}, "name")
    if existing:
        return {"school_id": existing, "name": name, "created": False}
    doc = frappe.new_doc("School")
    doc.name1    = name
    doc.district = district
    doc.type     = type
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"school_id": doc.name, "name": name, "created": True}


@frappe.whitelist(allow_guest=True)
def get_languages():
    languages = frappe.get_all(
        "TAP Language",
        fields=["name as id", "language_name as name"],
        order_by="language_name asc",
    )
    return {"languages": languages}


@frappe.whitelist(allow_guest=True)
def get_avatars():
    return {"avatars": AVATAR_DEFAULTS}
