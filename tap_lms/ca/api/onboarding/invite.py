import frappe
from tap_lms.ca.api.auth.citizenship_auth import (
    _require_access_token,
    _generate_access_token,
    _fetch_profiles_sql,
    _ensure_citizenship_auth,
)
from tap_lms.ca.api.onboarding.student import (
    _insert_student,
    _insert_learner,
    _append_profile_row,
    _sync_leaderboard_async,
)


def _require_worker(secret=None):
    if frappe.get_request_header("X-Worker-Secret", "") != frappe.get_doc("Secrets", "cf_worker_secret").get_password("value"):
        frappe.throw("unauthorized", frappe.AuthenticationError)


def _require_teacher(phone):
    row = frappe.db.sql(
        "SELECT mentor_type, mentor FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    if not row or row[0].mentor_type != "Teacher":
        frappe.throw("Teacher account required", frappe.AuthenticationError)
    return row[0].mentor


@frappe.whitelist(allow_guest=True)
def get_school_meta(school_id=None):
    school_id = school_id or frappe.form_dict.get("school_id")
    if not school_id:
        frappe.throw("school_id is required", frappe.ValidationError)
    _require_worker()
    row = frappe.db.sql(
        """
        SELECT sc.name AS school_id, sc.name1 AS school_name,
               sc.district AS district_id, d.district_name,
               d.state AS state_id, s.state_name
          FROM "tabSchool" sc
          JOIN "tabDistrict" d ON d.name = sc.district
          JOIN "tabState" s    ON s.name  = d.state
         WHERE sc.name = %s
         LIMIT 1
        """,
        school_id,
        as_dict=True,
    )
    if not row:
        frappe.throw("School not found", frappe.DoesNotExistError)
    return row[0]


@frappe.whitelist(allow_guest=True)
def finalize_join(
    phone=None, display_name=None, grade=None,
    school_id=None, language=None, avatar=None,
    password=None, dob=None, roll_number=None,
):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    display_name = display_name or fd.get("display_name")
    grade = grade or fd.get("grade")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar", "1")
    password = password or fd.get("password")
    dob = dob or fd.get("dob")
    roll_number = roll_number or fd.get("roll_number")

    if not phone or not display_name or not grade or not school_id or not language:
        frappe.throw("phone, display_name, grade, school_id, language are required", frappe.ValidationError)

    _require_access_token(phone)

    _ensure_citizenship_auth(phone, password if password and len(password) >= 6 else None)

    student_id = _insert_student(display_name, phone, grade, school_id, language, dob)
    learner_id = _insert_learner(student_id, display_name, grade, school_id, language)
    _append_profile_row(phone, learner_id, student_id, display_name, grade, avatar, roll_number)
    _sync_leaderboard_async(student_id, display_name, school_id)

    profiles, has_more = _fetch_profiles_sql(phone)
    return {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "learner_id": learner_id,
        "profiles": profiles,
        "profiles_has_more": has_more,
        "school_id": school_id,
    }