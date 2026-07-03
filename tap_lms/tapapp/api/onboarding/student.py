import frappe
from tap_lms.ca_api.auth.tapapp_auth import (
    _generate_access_token,
    _decode_token,
    _bearer_token,
    _require_access_token,
    _require_access_token_with_refresh,
    _fetch_profiles_sql,
    _ensure_tapapp_auth,
)

# ---------------------------------------------------------------------------
# Onboarding — creates Student + Tapapp Learner + the mirrored
# Tapapp Auth Profile row. Nothing here touches Teacher/Guardian/mentor
# doctypes because this app has none.
# ---------------------------------------------------------------------------


def _require_registration_token():
    token = _bearer_token()
    if not token:
        frappe.throw("Missing token", frappe.AuthenticationError)
    payload = _decode_token(token, "registration")
    if not payload:
        frappe.throw("Invalid or expired registration token", frappe.AuthenticationError)
    return payload


def _resolve_language(language_code):
    if not language_code:
        return None
    name = frappe.db.get_value("TAP Language", {"language_code": language_code}, "name")
    if name:
        return name
    if frappe.db.exists("TAP Language", language_code):
        return language_code
    frappe.throw(f"Unsupported language: {language_code}", frappe.ValidationError)


def _fetch_school_geo(school_id):
    """Returns (district, state) for a School, or (None, None) if no school given."""
    if not school_id:
        return None, None
    row = frappe.db.sql(
        "SELECT district, state FROM \"tabSchool\" WHERE name=%s LIMIT 1",
        school_id,
        as_dict=True,
    )
    if not row:
        return None, None
    return row[0].district, row[0].state


def _insert_student(display_name, phone, grade, school_id, language, dob=None):
    """Creates the base Student doctype record (external to Tapapp), if your
    install uses a shared Student doctype the same way Tapapp Learner links to."""
    language_name = _resolve_language(language)
    district, state = _fetch_school_geo(school_id)
    doc_data = {
        "doctype": "Student",
        "name1": display_name,
        "phone": phone,
        "grade": grade,
        "language": language_name,
        "status": "active",
        "dob": dob,
    }
    if school_id:
        doc_data["school_id"] = school_id
        doc_data["district"] = district
        doc_data["state"] = state
    doc = frappe.get_doc(doc_data)
    doc.insert(ignore_permissions=True)
    return doc.name


def _insert_learner(student_name, language, district, state, school):
    """Creates a Tapapp Learner row using ONLY fields present on that doctype."""
    doc = frappe.get_doc({
        "doctype": "Tapapp Learner",
        "student_name": student_name,
        "language": language,
        "district": district,
        "state": state,
        "school": school,
        "xp": 0,
        "last_activity_xp": 0,
        "level": "Level 1",
        "streak": 0,
        "longest_streak": 0,
        "activities_watched_this_week": 0,
        "max_weekly_activities": 2,
        "is_bingeing": 0,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _append_profile_row(auth_phone, learner_id, student_id, display_name, grade, avatar, roll_number=None):
    frappe.db.sql(
        """
        INSERT INTO "tabTapapp Auth Profile"
            (name, parent, parenttype, parentfield,
             tapapp_learner, student, student_name, grade, avatar, roll_number,
             creation, modified, modified_by, owner, idx)
        VALUES
            (MD5(RANDOM()::TEXT), %s, 'Tapapp Auth', 'students',
             %s, %s, %s, %s, %s, %s,
             NOW(), NOW(), 'Administrator', 'Administrator',
             COALESCE((SELECT MAX(idx) FROM "tabTapapp Auth Profile" WHERE parent=%s), 0) + 1)
        """,
        (auth_phone, learner_id, student_id, display_name, grade, avatar or "1", roll_number, auth_phone),
    )
    frappe.db.commit()


def _truthy(value):
    return str(value).lower() in ("true", "1", "yes")


@frappe.whitelist(allow_guest=True)
def create_first_profile(
    display_name=None, grade=None, school_id=None,
    language=None, avatar=None, password=None, dob=None, roll_number=None,
):
    """Registration step 2: phone verified via OTP -> create first student profile."""
    fd = frappe.form_dict
    display_name = display_name or fd.get("display_name")
    grade = grade or fd.get("grade")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar", "1")
    password = password or fd.get("password")
    dob = dob or fd.get("dob")
    roll_number = roll_number or fd.get("roll_number")

    payload = _require_registration_token()
    phone = payload["phone"]

    if not password or len(password) < 6:
        frappe.throw("password must be at least 6 characters", frappe.ValidationError)
    if not display_name or not grade:
        frappe.throw("display_name and grade are required", frappe.ValidationError)

    _ensure_tapapp_auth(phone, password)

    existing = frappe.db.sql(
        "SELECT tapapp_learner FROM \"tabTapapp Auth Profile\" WHERE parent=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    if existing:
        profiles, has_more = _fetch_profiles_sql(phone)
        return {
            "success": True, "token": _generate_access_token(phone), "phone": phone,
            "profiles": profiles, "profiles_has_more": has_more,
        }

    district, state = _fetch_school_geo(school_id)
    student_id = _insert_student(display_name, phone, grade, school_id, language, dob)
    learner_id = _insert_learner(display_name, _resolve_language(language), district, state, school_id)
    _append_profile_row(phone, learner_id, student_id, display_name, grade, avatar, roll_number)

    profiles, has_more = _fetch_profiles_sql(phone)
    return {
        "success": True, "token": _generate_access_token(phone), "phone": phone,
        "learner_id": learner_id, "profiles": profiles, "profiles_has_more": has_more,
    }


@frappe.whitelist(allow_guest=True)
def add_profile(
    phone=None, display_name=None, grade=None, school_id=None,
    language=None, avatar=None, dob=None, roll_number=None,
):
    """Adds another student profile under an already-registered phone
    (e.g. a sibling). Requires a fresh OTP-backed registration token
    (X-Registration-Token header) in addition to the normal access token,
    so an existing session can't silently attach unrelated students."""
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    display_name = display_name or fd.get("display_name")
    grade = grade or fd.get("grade")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar", "1")
    dob = dob or fd.get("dob")
    roll_number = roll_number or fd.get("roll_number")

    _require_access_token(phone)

    reg_token = frappe.get_request_header("X-Registration-Token", "")
    if not reg_token:
        frappe.throw("Missing registration token", frappe.AuthenticationError)
    reg_payload = _decode_token(reg_token, "registration")
    if not reg_payload or reg_payload.get("phone") != phone:
        frappe.throw("Invalid registration token", frappe.AuthenticationError)

    if not display_name or not grade:
        frappe.throw("display_name and grade are required", frappe.ValidationError)

    district, state = _fetch_school_geo(school_id)
    student_id = _insert_student(display_name, phone, grade, school_id, language, dob)
    learner_id = _insert_learner(display_name, _resolve_language(language), district, state, school_id)
    _append_profile_row(phone, learner_id, student_id, display_name, grade, avatar, roll_number)

    profiles, has_more = _fetch_profiles_sql(phone)
    return {"success": True, "phone": phone, "learner_id": learner_id, "profiles": profiles, "profiles_has_more": has_more}


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, learner_id=None, fields=None, include_enrollments=None, page=None, page_size=None):
    """Switch active profile + return that learner's state in one call."""
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")
    include_enrollments = include_enrollments if include_enrollments is not None else fd.get("include_enrollments")
    page = int(page or fd.get("page", 1))
    page_size = min(int(page_size or fd.get("page_size", 20)), 100)

    payload, new_token = _require_access_token_with_refresh(phone)

    row = frappe.db.sql(
        """
        SELECT tap.tapapp_learner, tap.student_name, tap.grade, tap.avatar, tap.roll_number
        FROM "tabTapapp Auth Profile" tap
        WHERE tap.parent=%s AND tap.tapapp_learner=%s
        LIMIT 1
        """,
        (phone, learner_id),
        as_dict=True,
    )
    if not row:
        frappe.throw("Profile not linked to this account", frappe.AuthenticationError)

    from tap_lms.ca_api.progress.learner import _learner_full_state
    state = _learner_full_state(learner_id, fields=fields, include_enrollments=_truthy(include_enrollments) if include_enrollments is not None else False, page=page, page_size=page_size)

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
        UPDATE "tabTapapp Auth Profile"
        SET avatar=%s, modified=NOW()
        WHERE parent=%s AND tapapp_learner=%s
        """,
        (avatar, phone, learner_id),
    )
    frappe.db.commit()
    return {"success": True, "avatar": avatar}


@frappe.whitelist(allow_guest=True)
def update_student_details(
    phone=None, learner_id=None,
    display_name=None, grade=None, language=None,
    school_id=None, birthdate=None, roll_number=None, avatar=None,
):
    """
    Single edit endpoint for a student's own details. Only the fields the
    caller actually passes are updated (partial update) — this keeps the
    request flexible and cheap. Keeps Tapapp Learner and the mirrored
    Tapapp Auth Profile row in sync in one transaction, and returns the
    fresh state so no follow-up GET is needed.
    """
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    display_name = display_name if display_name is not None else fd.get("display_name")
    grade = grade if grade is not None else fd.get("grade")
    language = language if language is not None else fd.get("language")
    school_id = school_id if school_id is not None else fd.get("school_id")
    birthdate = birthdate if birthdate is not None else fd.get("birthdate")
    roll_number = roll_number if roll_number is not None else fd.get("roll_number")
    avatar = avatar if avatar is not None else fd.get("avatar")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    _require_access_token(phone)

    owns = frappe.db.sql(
        "SELECT 1 FROM \"tabTapapp Auth Profile\" WHERE parent=%s AND tapapp_learner=%s LIMIT 1",
        (phone, learner_id),
    )
    if not owns:
        frappe.throw("Profile not linked to this account", frappe.AuthenticationError)

    learner_updates = {}
    profile_updates = {}

    if display_name:
        learner_updates["student_name"] = display_name
        profile_updates["student_name"] = display_name
    if language:
        resolved = _resolve_language(language)
        learner_updates["language"] = resolved
    if school_id:
        district, state = _fetch_school_geo(school_id)
        learner_updates["school"] = school_id
        learner_updates["district"] = district
        learner_updates["state"] = state
    if birthdate:
        learner_updates["birthdate"] = birthdate
    if grade:
        profile_updates["grade"] = grade
    if roll_number is not None:
        profile_updates["roll_number"] = roll_number
    if avatar:
        profile_updates["avatar"] = avatar

    if not learner_updates and not profile_updates:
        frappe.throw("No fields provided to update", frappe.ValidationError)

    if learner_updates:
        set_clause = ", ".join(f"{k}=%s" for k in learner_updates)
        frappe.db.sql(
            f'UPDATE "tabTapapp Learner" SET {set_clause}, modified=NOW() WHERE name=%s',
            (*learner_updates.values(), learner_id),
        )

    if profile_updates:
        set_clause = ", ".join(f"{k}=%s" for k in profile_updates)
        frappe.db.sql(
            f'UPDATE "tabTapapp Auth Profile" SET {set_clause}, modified=NOW() WHERE parent=%s AND tapapp_learner=%s',
            (*profile_updates.values(), phone, learner_id),
        )

    frappe.db.commit()

    from tap_lms.ca_api.progress.learner import _learner_full_state
    return {"success": True, "learner_id": learner_id, **_learner_full_state(learner_id)}