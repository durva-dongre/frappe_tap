import frappe
from tap_lms.ca.api.auth.citizenship_auth import (
    _generate_access_token,
    _generate_registration_token,
    _decode_token,
    _bearer_token,
    _require_access_token,
    _require_access_token_with_refresh,
    _fetch_profiles_sql,
    _ensure_citizenship_auth,
    _password_exists,
)


def _require_registration_token():
    token = _bearer_token()
    if not token:
        frappe.throw("Missing token", frappe.AuthenticationError)
    payload = _decode_token(token, "registration")
    if not payload:
        frappe.throw("Invalid or expired registration token", frappe.AuthenticationError)
    return payload


def _insert_student(display_name, phone, grade, school_id, language, dob=None):
    doc = frappe.get_doc({
        "doctype": "Student",
        "name1": display_name,
        "phone": phone,
        "grade": grade,
        "school_id": school_id,
        "language": language,
        "status": "active",
        **({"dob": dob} if dob else {}),
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _insert_learner(student_id, display_name, grade, school_id, language):
    # CREATE SEQUENCE IF NOT EXISTS citizenship_learner_seq START 1;
    rows = frappe.db.sql(
        """
        INSERT INTO "tabCitizenship Learner"
            (name, student, student_name, school, language,
             xp, xp_d0, xp_d1, xp_d2, xp_d3, xp_d4, xp_d5, xp_d6,
             weekly_xp, streak, longest_streak, level,
             creation, modified, modified_by, owner)
        VALUES
            (CONCAT('CL', LPAD(nextval('citizenship_learner_seq')::TEXT, 8, '0')),
             %s, %s, %s, %s,
             0, 0, 0, 0, 0, 0, 0, 0,
             0, 0, 0, 'Level 1',
             NOW(), NOW(), 'Administrator', 'Administrator')
        RETURNING name
        """,
        (student_id, display_name, school_id, language),
        as_dict=True,
    )
    frappe.db.commit()
    return rows[0].name


def _append_profile_row(auth_phone, learner_id, student_id, display_name, grade, avatar, roll_number=None, division=None):
    frappe.db.sql(
        """
        INSERT INTO "tabCitizenship Auth Profile"
            (name, parent, parenttype, parentfield,
             citizenship_learner, student, student_name, grade, division, avatar, roll_number,
             creation, modified, modified_by, owner, idx)
        VALUES
            (MD5(RANDOM()::TEXT), %s, 'Citizenship Auth', 'students',
             %s, %s, %s, %s, %s, %s, %s,
             NOW(), NOW(), 'Administrator', 'Administrator',
             COALESCE((SELECT MAX(idx) FROM "tabCitizenship Auth Profile" WHERE parent=%s), 0) + 1)
        """,
        (auth_phone, learner_id, student_id, display_name, grade, division, avatar or "1", roll_number, auth_phone),
    )
    frappe.db.commit()


def _sync_leaderboard_async(student_id, display_name, school_id):
    frappe.enqueue(
        "tap_lms.ca.api.onboarding.student._sync_leaderboard",
        student_id=student_id,
        display_name=display_name,
        school_id=school_id,
        queue="short",
    )


def _sync_leaderboard(student_id, display_name, school_id):
    import requests as http
    try:
        cache = frappe.cache()
        worker_url = cache.get_value("secret::cf_worker_url") or frappe.get_doc("Secrets", "cf_worker_url").get_password("value")
        worker_secret = cache.get_value("secret::cf_worker_secret") or frappe.get_doc("Secrets", "cf_worker_secret").get_password("value")
        http.post(
            f"{worker_url}/students/register",
            json={"student_id": student_id, "name": display_name, "school_id": school_id},
            headers={"Content-Type": "application/json", "X-Worker-Secret": worker_secret},
            timeout=5,
        )
    except Exception:
        frappe.log_error(title="Leaderboard Sync Error", message=frappe.get_traceback())


@frappe.whitelist(allow_guest=True)
def create_first_profile(
    display_name=None, grade=None, school_id=None,
    language=None, avatar=None, password=None, dob=None,
):
    fd = frappe.form_dict
    display_name = display_name or fd.get("display_name")
    grade = grade or fd.get("grade")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar", "1")
    password = password or fd.get("password")
    dob = dob or fd.get("dob")

    payload = _require_registration_token()
    phone = payload["phone"]

    if not password or len(password) < 6:
        frappe.throw("password must be at least 6 characters", frappe.ValidationError)
    if not display_name or not grade or not school_id or not language:
        frappe.throw("display_name, grade, school_id, language are required", frappe.ValidationError)

    _ensure_citizenship_auth(phone, password)

    existing_profiles = frappe.db.sql(
        "SELECT citizenship_learner FROM \"tabCitizenship Auth Profile\" WHERE parent=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    if existing_profiles:
        profiles, has_more = _fetch_profiles_sql(phone)
        return {"success": True, "token": _generate_access_token(phone), "phone": phone, "profiles": profiles, "profiles_has_more": has_more}

    student_id = _insert_student(display_name, phone, grade, school_id, language, dob)
    learner_id = _insert_learner(student_id, display_name, grade, school_id, language)
    _append_profile_row(phone, learner_id, student_id, display_name, grade, avatar)
    _sync_leaderboard_async(student_id, display_name, school_id)

    profiles, has_more = _fetch_profiles_sql(phone)
    return {"success": True, "token": _generate_access_token(phone), "phone": phone, "profiles": profiles, "profiles_has_more": has_more}


@frappe.whitelist(allow_guest=True)
def add_profile(
    phone=None, display_name=None, grade=None, school_id=None,
    language=None, avatar=None, dob=None,
):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    display_name = display_name or fd.get("display_name")
    grade = grade or fd.get("grade")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar", "1")
    dob = dob or fd.get("dob")

    _require_access_token(phone)

    # KNOWN ACCEPTED RISK: registration tokens have a 30-minute expiry with no
    # one-time-use invalidation. A stolen token can be replayed within the window.
    # To close this later: add a jti claim to the token and maintain a Redis set
    # of used JTIs with 30-minute TTL, rejecting replays on first check.
    reg_token = frappe.get_request_header("X-Registration-Token", "")
    if not reg_token:
        frappe.throw("Missing registration token", frappe.AuthenticationError)
    reg_payload = _decode_token(reg_token, "registration")
    if not reg_payload or reg_payload.get("phone") != phone:
        frappe.throw("Invalid registration token", frappe.AuthenticationError)

    if not display_name or not grade or not school_id or not language:
        frappe.throw("display_name, grade, school_id, language are required", frappe.ValidationError)

    student_id = _insert_student(display_name, phone, grade, school_id, language, dob)
    learner_id = _insert_learner(student_id, display_name, grade, school_id, language)
    _append_profile_row(phone, learner_id, student_id, display_name, grade, avatar)
    _sync_leaderboard_async(student_id, display_name, school_id)

    profiles, has_more = _fetch_profiles_sql(phone)
    return {"success": True, "phone": phone, "profiles": profiles, "profiles_has_more": has_more}


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, learner_id=None):
    phone = phone or frappe.form_dict.get("phone", "")
    learner_id = learner_id or frappe.form_dict.get("learner_id")

    payload, new_token = _require_access_token_with_refresh(phone)

    row = frappe.db.sql(
        """
        SELECT citizenship_learner, student_name, grade, avatar
        FROM "tabCitizenship Auth Profile"
        WHERE parent=%s AND citizenship_learner=%s
        LIMIT 1
        """,
        (phone, learner_id),
        as_dict=True,
    )
    if not row:
        frappe.throw("Profile not linked to this account", frappe.AuthenticationError)

    from tap_lms.ca.api.progress.learner import _learner_xp_state
    state = _learner_xp_state(learner_id)
    result = {"success": True, "learner_id": learner_id, "profile": row[0], **state}
    if new_token:
        result["token"] = new_token
    return result


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, learner_id=None, avatar=None):
    phone = phone or frappe.form_dict.get("phone", "")
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    avatar = avatar or frappe.form_dict.get("avatar", "1")
    _require_access_token(phone)

    frappe.db.sql(
        """
        UPDATE "tabCitizenship Auth Profile"
        SET avatar=%s, modified=NOW()
        WHERE parent=%s AND citizenship_learner=%s
        """,
        (avatar, phone, learner_id),
    )
    frappe.db.commit()
    return {"success": True, "avatar": avatar}