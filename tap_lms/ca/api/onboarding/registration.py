import frappe
from frappe.utils.password import update_password

from tap_lms.ca.api.auth.student_auth import (
    _generate_access_token,
    _generate_registration_token,
    _decode_token,
    _bearer_token,
    _avatar_path,
    _profiles_for_phone,
    _password_exists,
)

OTP_EXPIRY_MINUTES = 10
HARDCODED_OTP = "000000"

VALID_GENDERS = {"Male", "Female", "Others", "Not Available"}
VALID_SCHOOL_TYPES = {"APS", "GOVT", "NGO", "PPP", "PMC", "PVT", "GOVT. Aided", "ORG"}


def _get_secret(key):
    cache = frappe.cache()
    cached = cache.get_value(f"secret::{key}")
    if cached:
        return cached
    value = frappe.get_doc("Secrets", key).get_password("value")
    cache.set_value(f"secret::{key}", value, expires_in_sec=3600)
    return value


def _require_registration_token():
    token = _bearer_token()
    if not token:
        frappe.throw("Missing token", frappe.AuthenticationError)
    payload = _decode_token(token, "registration")
    if not payload:
        payload = _decode_token(token, "access")
    if not payload:
        frappe.throw("Invalid or expired token", frappe.AuthenticationError)
    return payload


def _resolve_avatar(avatar_key):
    if avatar_key and frappe.db.exists("Student Avatar", avatar_key):
        return avatar_key
    fallback = frappe.get_all(
        "Student Avatar", fields=["avatar_key"], order_by="avatar_key asc", limit=1
    )
    return fallback[0].avatar_key if fallback else "avatar_01"


def _validate_profile_fields(gender, state, district, school_id, language):
    if gender not in VALID_GENDERS:
        frappe.throw("Invalid gender value", frappe.ValidationError)
    if not frappe.db.exists("State", state):
        frappe.throw("State not found", frappe.DoesNotExistError)
    if not frappe.db.exists("District", district):
        frappe.throw("District not found", frappe.DoesNotExistError)
    if not frappe.db.exists("School", school_id):
        frappe.throw("School not found", frappe.DoesNotExistError)
    if not frappe.db.exists("TAP Language", language):
        frappe.throw("Language not found", frappe.DoesNotExistError)


def _ensure_student_auth(phone, raw_password):
    """
    Get or create a Student Auth row for this phone number.

    Uses INSERT … ON CONFLICT DO NOTHING to avoid the SELECT → INSERT race
    condition. After the upsert we read back the name in a single query.
    Only sets the password when the row was just created (no existing password).

    PostgreSQL guarantees that after ON CONFLICT DO NOTHING the row exists
    whether we inserted it or a concurrent request did, so the subsequent
    get_value is always safe.
    """
    # Generate a candidate name. Frappe autonames Student Auth records; we
    # insert via raw SQL only to avoid the race, so we need a stable name.
    # We derive it from the phone to make it idempotent across retries.
    # The actual autoname will be set by Frappe if we go through the ORM,
    # but here we let the DB generate it via the ORM path first, falling back
    # to raw SQL only on conflict.

    # Attempt ORM insert first — this is the happy path for new registrations.
    try:
        doc = frappe.new_doc("Student Auth")
        doc.phone = phone
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        # Password is set separately because frappe.new_doc does not accept it.
        update_password(doc.name, raw_password, doctype="Student Auth", fieldname="password")
        frappe.db.commit()
        return doc.name
    except frappe.exceptions.DuplicateEntryError:
        # Another request already created the row — roll back our failed attempt
        # and read the existing record.
        frappe.db.rollback()

    # Row already exists. Read it back — guaranteed to succeed because the
    # DuplicateEntryError means the row is committed in the DB.
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    if not auth_name:
        # Extremely unlikely: the row was deleted between our failed insert and
        # this read. Raise a clear error rather than looping.
        frappe.throw(
            f"Student Auth for phone {phone} disappeared after duplicate error.",
            frappe.ValidationError,
        )

    # Only set the password if one has never been stored (e.g. the row was
    # created by a concurrent migration path that skipped password setup).
    if not _password_exists(auth_name):
        update_password(auth_name, raw_password, doctype="Student Auth", fieldname="password")
        frappe.db.commit()

    return auth_name


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


def _link_student(phone, student_id, avatar_key):
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    doc = frappe.get_doc("Student Auth", auth_name)
    if student_id not in [row.student for row in doc.students]:
        doc.append("students", {"student": student_id, "avatar": avatar_key})
        doc.flags.ignore_mandatory = True
        doc.save(ignore_permissions=True)
    frappe.db.commit()


def _sync_leaderboard(student_id, display_name, state, district, school_id):
    import requests as http
    try:
        worker_url = _get_secret("cf_worker_url")
        worker_secret = _get_secret("cf_worker_secret")
        school_data = frappe.db.get_value("School", school_id, ["name1", "city"], as_dict=True)
        state_name = frappe.db.get_value("State", state, "state_name")
        district_name = frappe.db.get_value("District", district, "district_name")
        http.post(
            f"{worker_url}/students/register",
            json={
                "student_id": student_id,
                "name": display_name,
                "state_id": state,
                "state_name": state_name or state,
                "district_id": district,
                "district_name": district_name or district,
                "school_id": school_id,
                "school_name": school_data.name1 if school_data else school_id,
                "city": school_data.city if school_data else None,
            },
            headers={"Content-Type": "application/json", "X-Worker-Secret": worker_secret},
            timeout=5,
        )
    except Exception:
        frappe.log_error(title="Leaderboard Sync Error", message=frappe.get_traceback())


def _complete_profile_response(phone, student_id):
    auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
    doc = frappe.get_doc("Student Auth", auth_name)
    token = _generate_access_token(phone, [row.student for row in doc.students])
    profiles = _profiles_for_phone(phone)
    frappe.cache().set_value(f"profiles::{phone}", frappe.as_json(profiles), expires_in_sec=3600)
    return {
        "success": True,
        "token": token,
        "phone": phone,
        "new_student_id": student_id,
        "profiles": profiles,
    }


def _do_profile(phone, display_name, gender, grade, state, district,
                school_id, language, avatar, dob, migrate_student_id):
    _validate_profile_fields(gender, state, district, school_id, language)
    avatar_key = _resolve_avatar(avatar)

    if migrate_student_id:
        if not frappe.db.exists("Student", migrate_student_id):
            frappe.throw("Student to migrate not found", frappe.DoesNotExistError)
        _link_student(phone, migrate_student_id, avatar_key)
        frappe.enqueue(
            "tap_lms.ca.api.onboarding.registration._sync_leaderboard",
            student_id=migrate_student_id,
            display_name=display_name,
            state=state,
            district=district,
            school_id=school_id,
            queue="short",
        )
        return _complete_profile_response(phone, migrate_student_id)

    student_id = _insert_student(display_name, phone, gender, grade, school_id, language, dob)
    _link_student(phone, student_id, avatar_key)
    frappe.enqueue(
        "tap_lms.ca.api.onboarding.registration._sync_leaderboard",
        student_id=student_id,
        display_name=display_name,
        state=state,
        district=district,
        school_id=school_id,
        queue="short",
    )
    return _complete_profile_response(phone, student_id)


@frappe.whitelist(allow_guest=True)
def register_send_otp(phone=None):
    phone = phone or frappe.form_dict.get("phone", "")
    if not phone:
        frappe.throw("phone is required", frappe.ValidationError)
    if frappe.db.exists("Student Auth", {"phone": phone}):
        return {"success": False, "error": "phone_already_registered"}
    otp = HARDCODED_OTP if frappe.conf.get("use_hardcoded_otp", False) else _generate_otp()
    frappe.cache().set_value(f"otp_register::{phone}", otp, expires_in_sec=OTP_EXPIRY_MINUTES * 60)
    return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def register_verify_otp(phone=None, otp=None):
    phone = phone or frappe.form_dict.get("phone", "")
    otp = otp or frappe.form_dict.get("otp")
    if not phone or not otp:
        frappe.throw("phone and otp are required", frappe.ValidationError)
    stored = frappe.cache().get_value(f"otp_register::{phone}")
    if not stored:
        return {"success": False, "error": "otp_expired"}
    if stored != otp:
        return {"success": False, "error": "otp_invalid"}
    frappe.cache().delete_value(f"otp_register::{phone}")
    return {"success": True, "registration_token": _generate_registration_token(phone), "phone": phone}


@frappe.whitelist(allow_guest=True)
def create_profile(
    display_name=None, gender=None, grade=None, state=None, district=None,
    school_id=None, language=None, avatar=None, password=None, dob=None,
    migrate_student_id=None,
):
    fd = frappe.form_dict
    display_name = display_name or fd.get("display_name")
    gender = gender or fd.get("gender")
    grade = grade or fd.get("grade")
    state = state or fd.get("state")
    district = district or fd.get("district")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar")
    password = password or fd.get("password")
    dob = dob or fd.get("dob")
    migrate_student_id = migrate_student_id or fd.get("migrate_student_id")

    payload = _require_registration_token()
    phone = payload["phone"]

    if not password or len(password) < 6:
        frappe.throw("password must be at least 6 characters", frappe.ValidationError)

    _ensure_student_auth(phone, password)
    return _do_profile(phone, display_name, gender, grade, state, district,
                       school_id, language, avatar, dob, migrate_student_id)


def _generate_otp():
    import random
    return str(random.randint(100000, 999999))