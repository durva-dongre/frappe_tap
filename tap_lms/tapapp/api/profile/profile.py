import frappe
import json
from tap_lms.tapapp.api.auth.tapapp_auth import (
    _require_access_token,
    _require_access_token_with_refresh,
    _require_admin_unlocked,
    _get_teacher_auth_row,
)
from tap_lms.tapapp.api.progress.learner import learner_full_state, learner_bulk_state

EDITABLE_LEARNER_FIELDS = {"student_name", "language", "district", "state", "birthdate"}
EDITABLE_PROFILE_FIELDS = {"roll_number", "grade", "division", "avatar"}
BULK_EDIT_MAX_ROWS = 500


def _owned_learner_id(phone, learner_id):
    row = frappe.db.sql(
        'SELECT tapapp_learner FROM "tabTapapp Auth Profile" WHERE parent=%s AND tapapp_learner=%s LIMIT 1',
        (phone, learner_id),
    )
    if not row:
        frappe.throw("Profile not linked to this account", frappe.AuthenticationError)
    return learner_id


def _owned_learner_ids(phone, learner_ids):
    if not learner_ids:
        return set()
    placeholders = ",".join(["%s"] * len(learner_ids))
    rows = frappe.db.sql(
        f'SELECT tapapp_learner FROM "tabTapapp Auth Profile" WHERE parent=%s AND tapapp_learner IN ({placeholders})',
        (phone, *learner_ids),
    )
    return {r[0] for r in rows}


def _clean_division(value):
    value = value.strip().upper()
    if len(value) != 1 or not value.isalpha():
        frappe.throw("Division must be a single letter A-Z", frappe.ValidationError)
    return value


def _apply_updates(phone, learner_id, updates):
    if "school" in updates or "school_id" in updates:
        frappe.throw("school cannot be edited", frappe.ValidationError)

    if "division" in updates and updates["division"]:
        updates["division"] = _clean_division(str(updates["division"]))

    learner_set = {k: v for k, v in updates.items() if k in EDITABLE_LEARNER_FIELDS}
    profile_set = {k: v for k, v in updates.items() if k in EDITABLE_PROFILE_FIELDS}

    unknown = set(updates.keys()) - EDITABLE_LEARNER_FIELDS - EDITABLE_PROFILE_FIELDS
    if unknown:
        frappe.throw(f"These fields cannot be edited: {', '.join(sorted(unknown))}", frappe.ValidationError)

    if learner_set:
        set_clause = ", ".join(f"{k}=%s" for k in learner_set)
        frappe.db.sql(
            f'UPDATE "tabTapapp Learner" SET {set_clause}, modified=NOW() WHERE name=%s',
            (*learner_set.values(), learner_id),
        )
        if "student_name" in learner_set:
            frappe.db.sql(
                """
                UPDATE "tabTapapp Auth Profile"
                   SET student_name=%s, modified=NOW()
                 WHERE parent=%s AND tapapp_learner=%s
                """,
                (learner_set["student_name"], phone, learner_id),
            )

    if profile_set:
        set_clause = ", ".join(f"{k}=%s" for k in profile_set)
        frappe.db.sql(
            f"""
            UPDATE "tabTapapp Auth Profile"
               SET {set_clause}, modified=NOW()
             WHERE parent=%s AND tapapp_learner=%s
            """,
            (*profile_set.values(), phone, learner_id),
        )

    return bool(learner_set or profile_set)


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, learner_id=None, fields=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    payload, new_token = _require_access_token_with_refresh(phone)
    _owned_learner_id(phone, learner_id)

    state = learner_full_state(learner_id, fields=fields, include_achievements=True)
    if state is None:
        frappe.throw("Learner not found", frappe.DoesNotExistError)

    result = {"success": True, **state}
    if new_token:
        result["token"] = new_token
    return result


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, learner_id=None, avatar=None):
    phone = phone or frappe.form_dict.get("phone", "")
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    avatar = avatar or frappe.form_dict.get("avatar", "1")

    _require_access_token(phone)
    _owned_learner_id(phone, learner_id)

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
def update_profile(phone=None, learner_id=None, updates=None, **kwargs):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    _require_access_token(phone)
    _owned_learner_id(phone, learner_id)

    if updates is None:
        updates = {k: v for k, v in fd.items() if k not in ("phone", "learner_id", "cmd")}

    if isinstance(updates, str):
        try:
            updates = json.loads(updates)
        except Exception:
            frappe.throw("updates must be a JSON object", frappe.ValidationError)

    if not isinstance(updates, dict) or not updates:
        frappe.throw("No editable fields supplied", frappe.ValidationError)

    _apply_updates(phone, learner_id, updates)
    frappe.db.commit()

    return {"success": True, **learner_full_state(learner_id, fields="profile,level")}


@frappe.whitelist(allow_guest=True)
def search_student(phone=None, grade=None, roll_number=None, division=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    grade = grade or fd.get("grade")
    roll_number = roll_number or fd.get("roll_number")
    division = division or fd.get("division")

    if not grade or not roll_number or not division:
        frappe.throw("grade, roll_number, and division are required", frappe.ValidationError)

    _require_access_token(phone)
    division = _clean_division(division)

    row = frappe.db.sql(
        """
        SELECT tapapp_learner, student_name, roll_number, grade, division, avatar, student
        FROM "tabTapapp Auth Profile"
        WHERE parent=%s AND grade=%s AND roll_number=%s AND division=%s
        LIMIT 1
        """,
        (phone, grade, roll_number, division),
        as_dict=True,
    )
    if not row:
        frappe.throw("No matching student found", frappe.DoesNotExistError)

    r = row[0]
    state = learner_full_state(r.tapapp_learner, include_achievements=True) if r.tapapp_learner else None
    return {
        "learner_id": r.tapapp_learner,
        "student_name": r.student_name,
        "roll_number": r.roll_number,
        "grade": r.grade,
        "division": r.division,
        "avatar": r.avatar,
        "state": state,
    }


@frappe.whitelist(allow_guest=True)
def get_bulk_students(phone=None, grade=None, division=None, page=None, page_size=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    grade = grade or fd.get("grade")
    division = division or fd.get("division")
    page = int(page or fd.get("page", 1))
    page_size = min(int(page_size or fd.get("page_size", 100)), 500)
    offset = (page - 1) * page_size

    _require_access_token(phone)

    conditions = ["parent = %s"]
    params = [phone]
    if grade:
        conditions.append("grade = %s")
        params.append(grade)
    if division:
        conditions.append("division = %s")
        params.append(_clean_division(division))

    where_clause = " AND ".join(conditions)
    rows = frappe.db.sql(
        f"""
        SELECT tapapp_learner, student_name, roll_number, grade, division, avatar, student
        FROM "tabTapapp Auth Profile"
        WHERE {where_clause}
        ORDER BY grade ASC, division ASC, roll_number ASC
        LIMIT %s OFFSET %s
        """,
        (*params, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]

    learner_ids = [r.tapapp_learner for r in page_rows if r.tapapp_learner]
    states_by_learner = learner_bulk_state(learner_ids, include_achievements=True)

    students = [
        {
            "learner_id": r.tapapp_learner,
            "student_name": r.student_name,
            "roll_number": r.roll_number,
            "grade": r.grade,
            "division": r.division,
            "avatar": r.avatar,
            "state": states_by_learner.get(r.tapapp_learner),
        }
        for r in page_rows
    ]
    return {
        "phone": phone,
        "students": students,
        "students_has_more": has_more,
        "page": page,
        "page_size": page_size,
    }


@frappe.whitelist(allow_guest=True)
def update_student(phone=None, learner_id=None, updates=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    learner_id = learner_id or fd.get("learner_id")
    updates = updates or fd.get("updates")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    _require_access_token(phone)
    _owned_learner_id(phone, learner_id)

    if isinstance(updates, str):
        try:
            updates = json.loads(updates)
        except Exception:
            frappe.throw("updates must be a JSON object", frappe.ValidationError)

    if not isinstance(updates, dict) or not updates:
        frappe.throw("No editable fields supplied", frappe.ValidationError)

    _apply_updates(phone, learner_id, updates)
    frappe.db.commit()

    return {"success": True, **learner_full_state(learner_id, fields="profile,level")}


@frappe.whitelist(allow_guest=True)
def bulk_update_students(phone=None, changes=None, admin_code=None):
    fd = frappe.form_dict
    phone = phone or fd.get("phone", "")
    changes = changes or fd.get("changes")
    admin_code = admin_code if admin_code is not None else fd.get("admin_code")

    _require_admin_unlocked(phone)

    if isinstance(changes, str):
        try:
            changes = json.loads(changes)
        except Exception:
            frappe.throw("changes must be a JSON array", frappe.ValidationError)

    if not isinstance(changes, list) or not changes:
        frappe.throw("changes must be a non-empty array of {learner_id, updates}", frappe.ValidationError)

    if len(changes) > BULK_EDIT_MAX_ROWS:
        frappe.throw(f"Cannot update more than {BULK_EDIT_MAX_ROWS} students in one request", frappe.ValidationError)

    requested_ids = [c.get("learner_id") for c in changes if c.get("learner_id")]
    owned_ids = _owned_learner_ids(phone, requested_ids)

    results = []
    applied_any = False
    for change in changes:
        learner_id = change.get("learner_id")
        updates = change.get("updates")

        if not learner_id or not isinstance(updates, dict) or not updates:
            results.append({"learner_id": learner_id, "success": False, "error": "invalid_change"})
            continue

        if learner_id not in owned_ids:
            results.append({"learner_id": learner_id, "success": False, "error": "not_owned"})
            continue

        try:
            applied = _apply_updates(phone, learner_id, dict(updates))
            applied_any = applied_any or applied
            results.append({"learner_id": learner_id, "success": True})
        except Exception as e:
            results.append({"learner_id": learner_id, "success": False, "error": str(e)})

    if applied_any:
        frappe.db.commit()

    return {
        "success": True,
        "total": len(changes),
        "succeeded": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
    }