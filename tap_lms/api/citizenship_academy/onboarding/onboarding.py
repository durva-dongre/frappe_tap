import frappe
import jwt
import datetime
import requests
from frappe.utils.password import update_password

REGISTRATION_TOKEN_EXPIRY_MINUTES = 30
OTP_EXPIRY_MINUTES = 10
HARDCODED_OTP = "000000"
VALID_GENDERS = {"Male", "Female", "Others", "Not Available"}
VALID_SCHOOL_TYPES = {"APS", "GOVT", "NGO", "PPP", "PMC", "PVT", "GOVT. Aided", "ORG"}
JWT_EXPIRY_HOURS = 72


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
    secret_doc = frappe.get_doc("Secrets", key)
    value = secret_doc.get_password("value")
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


def _generate_registration_token(phone):
    payload = {
        "phone": phone,
        "type": "registration",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=REGISTRATION_TOKEN_EXPIRY_MINUTES),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def _decode_jwt(token, secret):
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None


def _decode_registration_token(token):
    payload = _decode_jwt(token, _get_jwt_secret())
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


def _require_any_token():
    token = _extract_bearer_token()
    if not token:
        frappe.throw("Missing token", frappe.AuthenticationError)
    payload = _decode_registration_token(token) or _decode_access_token(token)
    if not payload:
        frappe.throw("Invalid or expired token", frappe.AuthenticationError)
    return payload


def _store_otp(phone):
    frappe.cache().set_value(
        f"otp::{phone}",
        HARDCODED_OTP,
        expires_in_sec=OTP_EXPIRY_MINUTES * 60,
    )


def _verify_otp(phone, otp):
    stored = frappe.cache().get_value(f"otp::{phone}")
    if not stored:
        return False, "otp_expired"
    if stored != otp:
        return False, "otp_invalid"
    frappe.cache().delete_value(f"otp::{phone}")
    return True, None


def _resolve_avatar(avatar_key):
    if avatar_key and frappe.db.exists("Student Avatar", avatar_key):
        return avatar_key
    fallback = frappe.get_all(
        "Student Avatar",
        fields=["avatar_key"],
        order_by="avatar_key asc",
        limit=1,
    )
    return fallback[0].avatar_key if fallback else "avatar_01"


def _get_avatar_path(avatar_key):
    if not avatar_key:
        return "assets/avatars/avatar_01.png"
    path = frappe.db.get_value("Student Avatar", avatar_key, "avatar_path")
    return path or "assets/avatars/avatar_01.png"


def _ensure_student_auth(phone, raw_password):
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    if auth_name:
        return auth_name

    doc = frappe.new_doc("Student Auth")
    doc.phone = phone
    doc.failed_attempts = 0
    doc.is_locked = 0
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    update_password(doc.name, raw_password, doctype="Student Auth", fieldname="password")
    frappe.db.commit()
    return doc.name


def _append_student_to_auth(auth_doc, student_id, avatar_key):
    auth_doc.append("students", {"student": student_id, "avatar": avatar_key})


def _save_auth_doc(auth_doc):
    auth_doc.flags.ignore_mandatory = True
    auth_doc.save(ignore_permissions=True)


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
            ["name1", "gender", "grade", "school_id", "language", "status"],
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


def _sync_student_to_leaderboard(student_id, display_name, state, district, school_id):
    try:
        worker_url = _get_secret("cf_worker_url")
        worker_secret = _get_secret("cf_worker_secret")
        school_data = frappe.db.get_value("School", school_id, ["name1", "city", "type"], as_dict=True)
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
        response = requests.post(
            f"{worker_url}/students/register",
            json=payload,
            headers={"Content-Type": "application/json", "X-Worker-Secret": worker_secret},
            timeout=5,
        )
        if not response.ok:
            frappe.log_error(
                title="Leaderboard Sync Failed",
                message=f"Student: {student_id} | Status: {response.status_code} | Body: {response.text}",
            )
    except Exception:
        frappe.log_error(title="Leaderboard Sync Error", message=frappe.get_traceback())


def _complete_profile_response(phone, student_id):
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    auth_doc = frappe.get_doc("Student Auth", auth_name)
    all_students = [row.student for row in auth_doc.students]
    token = _generate_access_token(phone, all_students)
    profiles = _get_profiles_for_phone(phone)
    return {
        "success": True,
        "token": token,
        "phone": phone,
        "new_student_id": student_id,
        "profiles": profiles,
    }


def _validate_profile_fields(gender, state, district, school_id, language):
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


def _migrate_student(phone, student_id, avatar_key):
    if not frappe.db.exists("Student", student_id):
        frappe.throw("Student to migrate not found")
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    auth_doc = frappe.get_doc("Student Auth", auth_name)
    existing_ids = [row.student for row in auth_doc.students]
    if student_id not in existing_ids:
        _append_student_to_auth(auth_doc, student_id, avatar_key)
        _save_auth_doc(auth_doc)
        frappe.db.commit()
    return student_id


def _insert_student(display_name, phone, gender, grade, school_id, language, dob):
    student = frappe.get_doc({
        "doctype": "Student",
        "name1": display_name,
        "phone": phone,
        "gender": gender,
        "grade": grade,
        "school_id": school_id,
        "language": language,
        "status": "active",
        **({"dob": dob} if dob else {}),
    })
    student.insert(ignore_permissions=True)
    return student.name


def _link_student_to_auth(phone, student_id, avatar_key):
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    auth_doc = frappe.get_doc("Student Auth", auth_name)
    existing_ids = [row.student for row in auth_doc.students]
    if student_id not in existing_ids:
        _append_student_to_auth(auth_doc, student_id, avatar_key)
        _save_auth_doc(auth_doc)
    frappe.db.commit()


@frappe.whitelist(allow_guest=True)
def register_send_otp(phone=None):
    phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    if frappe.db.exists("Student Auth", {"phone": phone}):
        return {"success": False, "error": "phone_already_registered"}
    _store_otp(phone)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def register_verify_otp(phone=None, otp=None):
    phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
    otp = otp or frappe.form_dict.get("otp")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    if not otp:
        frappe.throw("otp is required", frappe.ValidationError)
    valid, reason = _verify_otp(phone, otp)
    if not valid:
        return {"success": False, "error": reason}
    return {"success": True, "registration_token": _generate_registration_token(phone), "phone": phone}


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
    password=None,
    dob=None,
    migrate_student_id=None,
):
    display_name = display_name or frappe.form_dict.get("display_name")
    gender = gender or frappe.form_dict.get("gender")
    grade = grade or frappe.form_dict.get("grade")
    state = state or frappe.form_dict.get("state")
    district = district or frappe.form_dict.get("district")
    school_id = school_id or frappe.form_dict.get("school_id")
    language = language or frappe.form_dict.get("language")
    avatar = avatar or frappe.form_dict.get("avatar")
    password = password or frappe.form_dict.get("password")
    dob = dob or frappe.form_dict.get("dob")
    migrate_student_id = migrate_student_id or frappe.form_dict.get("migrate_student_id")

    payload = _require_registration_token()
    phone = payload["phone"]

    if not password:
        frappe.throw("password is required", frappe.ValidationError)
    if len(password) < 6:
        frappe.throw("password must be at least 6 characters", frappe.ValidationError)

    _validate_profile_fields(gender, state, district, school_id, language)
    resolved_avatar_key = _resolve_avatar(avatar)

    _ensure_student_auth(phone, password)

    if migrate_student_id:
        student_id = _migrate_student(phone, migrate_student_id, resolved_avatar_key)
        _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)
        return _complete_profile_response(phone, student_id)

    student_id = _insert_student(display_name, phone, gender, grade, school_id, language, dob)
    _link_student_to_auth(phone, student_id, resolved_avatar_key)
    _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)
    return _complete_profile_response(phone, student_id)


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
    phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
    display_name = display_name or frappe.form_dict.get("display_name")
    gender = gender or frappe.form_dict.get("gender")
    grade = grade or frappe.form_dict.get("grade")
    state = state or frappe.form_dict.get("state")
    district = district or frappe.form_dict.get("district")
    school_id = school_id or frappe.form_dict.get("school_id")
    language = language or frappe.form_dict.get("language")
    avatar = avatar or frappe.form_dict.get("avatar")
    dob = dob or frappe.form_dict.get("dob")
    migrate_student_id = migrate_student_id or frappe.form_dict.get("migrate_student_id")

    payload = _require_access_token()
    if payload["phone"] != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)

    _validate_profile_fields(gender, state, district, school_id, language)
    resolved_avatar_key = _resolve_avatar(avatar)

    if migrate_student_id:
        student_id = _migrate_student(phone, migrate_student_id, resolved_avatar_key)
        _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)
        return _complete_profile_response(phone, student_id)

    student_id = _insert_student(display_name, phone, gender, grade, school_id, language, dob)
    _link_student_to_auth(phone, student_id, resolved_avatar_key)
    _sync_student_to_leaderboard(student_id, display_name, state, district, school_id)
    return _complete_profile_response(phone, student_id)


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, student_id=None):
    phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
    student_id = student_id or frappe.form_dict.get("student_id")

    payload = _require_any_token()
    if payload.get("phone") != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)

    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    doc = frappe.get_doc("Student Auth", auth_name)
    linked_ids = [row.student for row in doc.students]

    if student_id not in linked_ids:
        frappe.throw("Profile not linked to this phone", frappe.AuthenticationError)

    new_token = _generate_access_token(phone, linked_ids)
    profiles = _get_profiles_for_phone(phone)
    current = next((p for p in profiles if p["student_id"] == student_id), None)

    return {
        "success": True,
        "token": new_token,
        "phone": phone,
        "active_profile": current,
        "profiles": profiles,
    }


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, student_id=None, avatar=None):
    phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
    student_id = student_id or frappe.form_dict.get("student_id")
    avatar = avatar or frappe.form_dict.get("avatar")

    payload = _require_access_token()
    if payload["phone"] != phone:
        frappe.throw("Token phone mismatch", frappe.AuthenticationError)

    if not frappe.db.exists("Student Avatar", avatar):
        frappe.throw("Invalid avatar")

    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    doc = frappe.get_doc("Student Auth", auth_name)

    updated = False
    for row in doc.students:
        if row.student == student_id:
            row.avatar = avatar
            updated = True
            break

    if not updated:
        frappe.throw("Profile not found on this account")

    _save_auth_doc(doc)
    frappe.db.commit()
    return {"success": True, "avatar": _get_avatar_path(avatar)}


@frappe.whitelist(allow_guest=True)
def get_states():
    return {
        "states": frappe.get_all(
            "State",
            fields=["name as id", "state_name as name"],
            order_by="state_name asc",
        )
    }


@frappe.whitelist(allow_guest=True)
def get_districts(state=None):
    state = state or frappe.form_dict.get("state")
    if not state:
        frappe.throw("state is required", frappe.ValidationError)
    if not frappe.db.exists("State", state):
        frappe.throw("State not found", frappe.DoesNotExistError)
    return {
        "state": state,
        "districts": frappe.get_all(
            "District",
            filters={"state": state},
            fields=["name as id", "district_name as name"],
            order_by="district_name asc",
        ),
    }


@frappe.whitelist(allow_guest=True)
def get_schools(district=None, search=None):
    district = district or frappe.form_dict.get("district")
    search = search or frappe.form_dict.get("search", "")
    if not district:
        frappe.throw("district is required", frappe.ValidationError)
    if not frappe.db.exists("District", district):
        frappe.throw("District not found", frappe.DoesNotExistError)
    filters = {"district": district}
    if search:
        filters["name1"] = ["like", f"%{search}%"]
    return {
        "district": district,
        "schools": frappe.get_all(
            "School",
            filters=filters,
            fields=["name as id", "name1 as name", "type", "city"],
            order_by="name1 asc",
            limit=50,
        ),
    }


@frappe.whitelist(allow_guest=True)
def create_school(name=None, district=None, type="GOVT"):
    name = name or frappe.form_dict.get("name")
    district = district or frappe.form_dict.get("district")
    type = type or frappe.form_dict.get("type", "GOVT")
    if type not in VALID_SCHOOL_TYPES:
        frappe.throw("Invalid school type")
    if not frappe.db.exists("District", district):
        frappe.throw("District not found")
    existing = frappe.db.get_value("School", {"name1": name, "district": district}, "name")
    if existing:
        return {"school_id": existing, "name": name, "created": False}
    doc = frappe.new_doc("School")
    doc.name1 = name
    doc.district = district
    doc.type = type
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"school_id": doc.name, "name": name, "created": True}


@frappe.whitelist(allow_guest=True)
def get_languages():
    return {
        "languages": frappe.get_all(
            "TAP Language",
            fields=["name as id", "language_name as name"],
            order_by="language_name asc",
        )
    }


@frappe.whitelist(allow_guest=True)
def get_avatars():
    rows = frappe.get_all(
        "Student Avatar",
        fields=["avatar_key", "avatar_path"],
        order_by="avatar_key asc",
    )
    return {"avatars": [{"key": r.avatar_key, "path": r.avatar_path} for r in rows]}
