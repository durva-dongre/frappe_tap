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


def _mentor_school_id(phone):
    row = frappe.db.sql(
        "SELECT mentor_type, mentor FROM \"tabCitizenship Auth\" WHERE phone=%s LIMIT 1",
        phone,
        as_dict=True,
    )
    if not row or row[0].mentor_type != "Teacher":
        return None
    mentor_ref = row[0].mentor
    school_row = frappe.db.sql(
        "SELECT school_id FROM \"tabTeacher\" WHERE name=%s LIMIT 1",
        mentor_ref,
        as_dict=True,
    )
    return school_row[0].school_id if school_row else None


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
    if mentor_type == "Teacher" and not language:
        frappe.throw("language is required", frappe.ValidationError)
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
            "language": language_name,
        }
        if last_name:
            doc_data["last_name"] = last_name
        if gender:
            doc_data["gender"] = gender
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
def get_class_roster(phone=None, grade=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    grade = grade or fd.get("grade")
    page = int(fd.get("page", 1))
    page_size = min(int(fd.get("page_size", 50)), 100)
    offset = (page - 1) * page_size

    _require_access_token(phone)
    mentor_row = _require_mentor(phone)

    if mentor_row.mentor_type != "Teacher":
        frappe.throw("Class roster is only available for teachers", frappe.AuthenticationError)

    school_id = _mentor_school_id(phone)
    if not school_id:
        frappe.throw("Could not determine school for this teacher", frappe.ValidationError)

    rows = frappe.db.sql(
        """
        SELECT cap.citizenship_learner AS learner_id,
               cap.student_name, cap.grade, cap.avatar, cap.roll_number
        FROM "tabCitizenship Auth Profile" cap
        JOIN "tabCitizenship Learner" cl ON cl.name = cap.citizenship_learner
        WHERE cl.school = %s AND cap.grade = %s
        ORDER BY cap.roll_number ASC, cap.student_name ASC
        LIMIT %s OFFSET %s
        """,
        (school_id, grade, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    data = [
        {
            "learner_id": r.learner_id,
            "student_name": r.student_name,
            "grade": r.grade,
            "avatar": r.avatar,
            "roll_number": r.roll_number,
        }
        for r in rows[:page_size]
    ]
    return {"data": data, "has_more": has_more, "page": page, "page_size": page_size}


@frappe.whitelist(allow_guest=True)
def get_all_students(phone=None, grade=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    grade = grade or fd.get("grade")
    page = int(fd.get("page", 1))
    page_size = min(int(fd.get("page_size", 50)), 100)
    offset = (page - 1) * page_size

    _require_access_token(phone)
    mentor_row = _require_mentor(phone)
    mentor_type = mentor_row.mentor_type

    if mentor_type == "Teacher":
        school_id = _mentor_school_id(phone)
        if not school_id:
            frappe.throw("Could not determine school for this teacher", frappe.ValidationError)

        conditions = ["cl.school = %s"]
        params = [school_id]
        if grade:
            conditions.append("cap.grade = %s")
            params.append(grade)

        where_clause = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT cap.citizenship_learner AS learner_id,
                   cap.student_name, cap.grade, cap.avatar, cap.roll_number
            FROM "tabCitizenship Auth Profile" cap
            JOIN "tabCitizenship Learner" cl ON cl.name = cap.citizenship_learner
            WHERE {where_clause}
            ORDER BY cap.grade ASC, cap.roll_number ASC, cap.student_name ASC
            LIMIT %s OFFSET %s
            """,
            (*params, page_size + 1, offset),
            as_dict=True,
        )
    else:
        conditions = ["cap.parent = %s"]
        params = [phone]
        if grade:
            conditions.append("cap.grade = %s")
            params.append(grade)

        where_clause = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT cap.citizenship_learner AS learner_id,
                   cap.student_name, cap.grade, cap.avatar, cap.roll_number
            FROM "tabCitizenship Auth Profile" cap
            WHERE {where_clause}
            ORDER BY cap.grade ASC, cap.idx ASC
            LIMIT %s OFFSET %s
            """,
            (*params, page_size + 1, offset),
            as_dict=True,
        )

    has_more = len(rows) > page_size
    data = [
        {
            "learner_id": r.learner_id,
            "student_name": r.student_name,
            "grade": r.grade,
            "avatar": r.avatar,
            "roll_number": r.roll_number,
        }
        for r in rows[:page_size]
    ]
    return {"data": data, "has_more": has_more, "page": page, "page_size": page_size}


@frappe.whitelist(allow_guest=True)
def get_student_detail(phone=None, learner_id=None, fields=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    _require_access_token(phone)
    _require_mentor(phone)

    from tap_lms.ca.api.progress.learner import _learner_xp_state, _parse_optional
    optional = _parse_optional(fields)
    include_daily = optional is None or "xp_daily" in optional
    return _learner_xp_state(learner_id, include_daily=include_daily)


@frappe.whitelist(allow_guest=True)
def search_students(phone=None, query=None, grade=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    query = query or fd.get("query")
    grade = grade or fd.get("grade")
    page = int(fd.get("page", 1))
    page_size = min(int(fd.get("page_size", 50)), 100)
    offset = (page - 1) * page_size

    _require_access_token(phone)
    mentor_row = _require_mentor(phone)
    mentor_type = mentor_row.mentor_type

    if mentor_type == "Teacher":
        school_id = _mentor_school_id(phone)
        if not school_id:
            frappe.throw("Could not determine school for this teacher", frappe.ValidationError)

        conditions = ["cl.school = %s"]
        params = [school_id]
        if grade:
            conditions.append("cap.grade = %s")
            params.append(grade)
        if query:
            conditions.append("cap.student_name ILIKE %s")
            params.append(f"%{query}%")

        where_clause = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT cap.citizenship_learner AS learner_id,
                   cap.student_name, cap.grade, cap.avatar, cap.roll_number
            FROM "tabCitizenship Auth Profile" cap
            JOIN "tabCitizenship Learner" cl ON cl.name = cap.citizenship_learner
            WHERE {where_clause}
            ORDER BY cap.grade ASC, cap.roll_number ASC, cap.student_name ASC
            LIMIT %s OFFSET %s
            """,
            (*params, page_size + 1, offset),
            as_dict=True,
        )
    else:
        conditions = ["cap.parent = %s"]
        params = [phone]
        if grade:
            conditions.append("cap.grade = %s")
            params.append(grade)
        if query:
            conditions.append("cap.student_name ILIKE %s")
            params.append(f"%{query}%")

        where_clause = " AND ".join(conditions)
        rows = frappe.db.sql(
            f"""
            SELECT cap.citizenship_learner AS learner_id,
                   cap.student_name, cap.grade, cap.avatar, cap.roll_number
            FROM "tabCitizenship Auth Profile" cap
            WHERE {where_clause}
            ORDER BY cap.grade ASC, cap.idx ASC
            LIMIT %s OFFSET %s
            """,
            (*params, page_size + 1, offset),
            as_dict=True,
        )

    has_more = len(rows) > page_size
    data = [
        {
            "learner_id": r.learner_id,
            "student_name": r.student_name,
            "grade": r.grade,
            "avatar": r.avatar,
            "roll_number": r.roll_number,
        }
        for r in rows[:page_size]
    ]
    return {"data": data, "has_more": has_more, "page": page, "page_size": page_size}


@frappe.whitelist(allow_guest=True)
def add_student_profile(phone=None, display_name=None, grade=None, school_id=None,
                        language=None, avatar=None, dob=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    display_name = display_name or fd.get("display_name")
    grade = grade or fd.get("grade")
    school_id = school_id or fd.get("school_id")
    language = language or fd.get("language")
    avatar = avatar or fd.get("avatar", "1")
    dob = dob or fd.get("dob")

    _require_access_token(phone)
    _require_mentor(phone)

    if not display_name or not grade or not school_id or not language:
        frappe.throw("display_name, grade, school_id, language are required", frappe.ValidationError)

    student_id = _insert_student(display_name, phone, grade, school_id, language, dob)
    learner_id = _insert_learner(student_id, display_name, grade, school_id, language)
    _append_profile_row(phone, learner_id, student_id, display_name, grade, avatar)
    _sync_leaderboard_async(student_id, display_name, school_id)

    return {"success": True, "learner_id": learner_id}


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
def select_profile(phone=None, learner_id=None, include_enrollments=None, page=None, page_size=None):
    from tap_lms.ca.api.onboarding.student import select_profile as _select
    return _select(phone=phone, learner_id=learner_id, include_enrollments=include_enrollments, page=page, page_size=page_size)


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, learner_id=None, avatar=None):
    from tap_lms.ca.api.onboarding.student import update_avatar as _update
    return _update(phone=phone, learner_id=learner_id, avatar=avatar)