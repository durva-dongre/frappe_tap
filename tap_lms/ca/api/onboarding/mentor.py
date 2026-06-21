import frappe
from tap_lms.ca.api.auth.citizenship_auth import (
    _generate_access_token,
    _decode_token,
    _require_access_token,
    _require_access_token_with_refresh,
    _fetch_profiles_sql,
    _ensure_citizenship_auth,
    _bearer_token,
)
from tap_lms.ca.api.onboarding.student import (
    _insert_student,
    _insert_learner,
    _append_profile_row,
    _sync_leaderboard_async,
    _resolve_language,
)


def _require_mentor(phone):
    row = frappe.db.sql(
        "SELECT mentor_type, mentor FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    if not row or not row[0].mentor_type:
        frappe.throw("Not a mentor account", frappe.AuthenticationError)
    return row[0]


def _fetch_school_geo(school_id):
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


def _get_mentor_school_geo(mentor_ref, mentor_type):
    table = "tabTeacher" if mentor_type == "Teacher" else "tabGuardian"
    row = frappe.db.sql(
        f'SELECT district, state FROM "{table}" WHERE name=%s LIMIT 1',
        mentor_ref,
        as_dict=True,
    )
    if not row:
        return None, None
    return row[0].district, row[0].state


def _mentor_school_context(mentor_ref, mentor_type):
    if mentor_type == "Teacher":
        row = frappe.db.sql(
            "SELECT school_id, district, state, language FROM \"tabTeacher\" WHERE name=%s LIMIT 1",
            mentor_ref,
            as_dict=True,
        )
        if not row:
            return {}
        return {
            "school_id": row[0].school_id,
            "district": row[0].district,
            "state": row[0].state,
            "language": row[0].language,
        }
    if mentor_type == "Guardian":
        row = frappe.db.sql(
            "SELECT district, state, language FROM \"tabGuardian\" WHERE name=%s LIMIT 1",
            mentor_ref,
            as_dict=True,
        )
        if not row:
            return {}
        return {
            "district": row[0].district,
            "state": row[0].state,
            "language": row[0].language,
        }
    return {}


@frappe.whitelist(allow_guest=True)
def create_mentor_profile(
    display_name=None, mentor_type=None, avatar=None,
    password=None, admin_code=None, school_id=None,
    gender=None, state=None, district=None, language=None,
):
    fd = frappe.form_dict
    display_name = display_name or fd.get("display_name")
    last_name = fd.get("last_name")
    mentor_type = mentor_type or fd.get("mentor_type")
    avatar = avatar or fd.get("avatar", "1")
    password = password or fd.get("password")
    admin_code = admin_code or fd.get("admin_code")
    school_id = school_id or fd.get("school_id")
    gender = gender or fd.get("gender")
    state = state or fd.get("state")
    district = district or fd.get("district")
    language = language or fd.get("language")

    token = _bearer_token()
    if not token:
        frappe.throw("Missing registration token", frappe.AuthenticationError)
    payload = _decode_token(token, "registration")
    if not payload:
        frappe.throw("Invalid or expired registration token", frappe.AuthenticationError)
    phone = payload["phone"]

    if mentor_type not in ("Teacher", "Guardian"):
        frappe.throw("mentor_type must be Teacher or Guardian", frappe.ValidationError)
    if not password or len(password) < 6:
        frappe.throw("password must be at least 6 characters", frappe.ValidationError)
    if not display_name:
        frappe.throw("display_name is required", frappe.ValidationError)
    if mentor_type == "Teacher" and not school_id:
        frappe.throw("school_id is required", frappe.ValidationError)
    if mentor_type == "Guardian" and (not state or not district):
        frappe.throw("state and district are required", frappe.ValidationError)
    if mentor_type == "Guardian" and not language:
        frappe.throw("language is required", frappe.ValidationError)

    language_name = _resolve_language(language) if language else None

    _ensure_citizenship_auth(phone, password)

    if mentor_type == "Teacher":
        teacher_district, teacher_state = _fetch_school_geo(school_id)
        doc_data = {
            "doctype": "Teacher",
            "first_name": display_name,
            "phone_number": phone,
            "school_id": school_id,
            "district": teacher_district,
            "state": teacher_state,
        }
        if last_name:
            doc_data["last_name"] = last_name
        if gender:
            doc_data["gender"] = gender
        if language_name:
            doc_data["language"] = language_name
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=True)
        mentor_ref = doc.name
    else:
        doc_data = {
            "doctype": "Guardian",
            "name1": display_name,
            "phone": phone,
            "state": state,
            "district": district,
            "language": language_name,
        }
        if gender:
            doc_data["gender"] = gender
        doc = frappe.get_doc(doc_data)
        doc.insert(ignore_permissions=True)
        mentor_ref = doc.name

    frappe.db.sql(
        """
        UPDATE "tabCitizenship Auth"
        SET mentor_type=%s, mentor=%s, mentor_avatar=%s,
            admin_code=COALESCE(%s, admin_code), modified=NOW()
        WHERE phone=%s
        """,
        (mentor_type, mentor_ref, avatar, admin_code, phone),
    )
    frappe.db.commit()

    result = {
        "success": True,
        "token": _generate_access_token(phone),
        "phone": phone,
        "mentor_type": mentor_type,
        "profiles": [],
        "profiles_has_more": False,
    }
    result.update(_mentor_school_context(mentor_ref, mentor_type))
    return result


@frappe.whitelist(allow_guest=True)
def get_class_roster(phone=None, grade=None, page=1, page_size=50):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    grade = grade or fd.get("grade")
    page = int(fd.get("page", page))
    page_size = min(int(fd.get("page_size", page_size)), 100)

    _require_access_token(phone)
    mentor = _require_mentor(phone)

    if not grade:
        frappe.throw("grade is required", frappe.ValidationError)

    offset = (page - 1) * page_size

    rows = frappe.db.sql(
        """
        SELECT citizenship_learner, student_name,
               roll_number, grade, avatar
        FROM "tabCitizenship Auth Profile"
        WHERE parent=%s AND grade=%s
        ORDER BY roll_number ASC
        LIMIT %s OFFSET %s
        """,
        (phone, grade, page_size + 1, offset),
        as_dict=True,
    )

    has_more = len(rows) > page_size
    result = {
        "data": rows[:page_size],
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }
    result.update(_mentor_school_context(mentor.mentor, mentor.mentor_type))
    return result


@frappe.whitelist(allow_guest=True)
def get_student_detail(phone=None, learner_id=None, fields=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")

    _require_access_token(phone)
    _require_mentor(phone)

    owns = frappe.db.sql(
        "SELECT 1 FROM \"tabCitizenship Auth Profile\" WHERE parent=%s AND citizenship_learner=%s LIMIT 1",
        (phone, learner_id),
    )
    if not owns:
        frappe.throw("Learner not in your roster", frappe.AuthenticationError)

    from tap_lms.ca.api.progress.learner import _learner_xp_state, _parse_optional
    optional = _parse_optional(fields)
    include_daily = optional is None or "xp_daily" in optional
    return _learner_xp_state(learner_id, include_daily=include_daily)


@frappe.whitelist(allow_guest=True)
def search_students(phone=None, query=None, grade=None, page=1, page_size=20):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    query = query or fd.get("query", "")
    grade = grade or fd.get("grade")
    page = int(fd.get("page", page))
    page_size = min(int(fd.get("page_size", page_size)), 100)

    _require_access_token(phone)
    mentor = _require_mentor(phone)

    offset = (page - 1) * page_size
    rows = frappe.db.sql(
        """
        SELECT citizenship_learner, student_name, roll_number, grade, avatar
        FROM "tabCitizenship Auth Profile"
        WHERE parent=%s
          AND student_name ILIKE %s
          AND (%s IS NULL OR grade=%s)
        ORDER BY student_name ASC
        LIMIT %s OFFSET %s
        """,
        (phone, f"%{query}%", grade, grade, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    result = {
        "data": rows[:page_size],
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }
    result.update(_mentor_school_context(mentor.mentor, mentor.mentor_type))
    return result


@frappe.whitelist(allow_guest=True)
def add_student_profile(
    phone=None, display_name=None, grade=None, school_id=None,
    language=None, avatar=None, dob=None, roll_number=None,
):
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
    _require_mentor(phone)

    if not display_name or not grade or not school_id or not language:
        frappe.throw("display_name, grade, school_id, language are required", frappe.ValidationError)

    student_id = _insert_student(display_name, phone, grade, school_id, language, dob)
    learner_id = _insert_learner(student_id, display_name, grade, school_id, language)
    _append_profile_row(phone, learner_id, student_id, display_name, grade, avatar, roll_number)
    _sync_leaderboard_async(student_id, display_name, school_id)

    profiles, has_more = _fetch_profiles_sql(phone)
    return {"success": True, "phone": phone, "profiles": profiles, "profiles_has_more": has_more}


@frappe.whitelist(allow_guest=True)
def get_all_students(phone=None, grade=None, page=1, page_size=50):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    grade = grade or fd.get("grade")
    page = int(fd.get("page", page))
    page_size = min(int(fd.get("page_size", page_size)), 50)

    _require_access_token(phone)
    mentor = _require_mentor(phone)

    offset = (page - 1) * page_size

    rows = frappe.db.sql(
        """
        SELECT citizenship_learner, student_name, roll_number, grade, avatar
        FROM "tabCitizenship Auth Profile"
        WHERE parent=%s
          AND (%s IS NULL OR grade=%s)
        ORDER BY idx ASC
        LIMIT %s OFFSET %s
        """,
        (phone, grade, grade, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    result = {
        "data": rows[:page_size],
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }
    result.update(_mentor_school_context(mentor.mentor, mentor.mentor_type))
    return result


@frappe.whitelist(allow_guest=True)
def get_student_profiles_bulk(phone=None, learner_ids=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_ids = learner_ids or fd.get("learner_ids")

    _require_access_token(phone)
    _require_mentor(phone)

    if not learner_ids:
        frappe.throw("learner_ids is required", frappe.ValidationError)

    if isinstance(learner_ids, str):
        import json
        try:
            learner_ids = json.loads(learner_ids)
        except Exception:
            learner_ids = [x.strip() for x in learner_ids.split(",") if x.strip()]

    if len(learner_ids) > 100:
        frappe.throw("Maximum 100 learner_ids per request", frappe.ValidationError)

    placeholders = ",".join(["%s"] * len(learner_ids))

    owned = frappe.db.sql(
        f"""
        SELECT citizenship_learner
        FROM "tabCitizenship Auth Profile"
        WHERE parent=%s AND citizenship_learner IN ({placeholders})
        """,
        (phone, *learner_ids),
        as_dict=True,
    )
    owned_set = {r.citizenship_learner for r in owned}
    requested = [lid for lid in learner_ids if lid in owned_set]

    if not requested:
        return {"data": []}

    req_placeholders = ",".join(["%s"] * len(requested))
    rows = frappe.db.sql(
        f"""
        SELECT cl.name AS learner_id, cl.student_name, cl.xp, cl.weekly_xp,
               cl.streak, cl.level, cl.school, cl.language,
               sap.avatar, sap.grade, sap.roll_number
        FROM "tabCitizenship Learner" cl
        LEFT JOIN LATERAL (
            SELECT avatar, grade, roll_number
            FROM "tabCitizenship Auth Profile"
            WHERE citizenship_learner = cl.name
            LIMIT 1
        ) sap ON true
        WHERE cl.name IN ({req_placeholders})
        """,
        tuple(requested),
        as_dict=True,
    )
    return {"data": rows}


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, learner_id=None):
    from tap_lms.ca.api.onboarding.student import select_profile as _select
    return _select(phone=phone, learner_id=learner_id)


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, learner_id=None, avatar=None):
    from tap_lms.ca.api.onboarding.student import update_avatar as _update
    return _update(phone=phone, learner_id=learner_id, avatar=avatar)