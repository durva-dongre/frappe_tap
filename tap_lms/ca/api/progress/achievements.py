import frappe
from .learner import (
    _get_or_create_learner,
    _get_learner_name,
)


def _bulk_achievement_translations(achievement_ids: list, lang) -> tuple:
    if not achievement_ids or not lang or lang.lower() in ("en", "english"):
        return {}, {}
    rows = frappe.get_all(
        "Citizenship Achievement Translation",
        filters={"parent": ["in", achievement_ids], "language": lang},
        fields=["parent", "translated_name", "translated_description"],
    )
    names = {r.parent: r.translated_name for r in rows}
    descs = {r.parent: r.translated_description for r in rows}
    return names, descs


@frappe.whitelist(allow_guest=True)
def get_learner_achievements(student_id=None, lang=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    lang = lang or frappe.form_dict.get("lang")
    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)

    learner_name = _get_or_create_learner(student_id)

    earned_rows = frappe.get_all(
        "Citizenship Learner Achievement",
        filters={"parent": learner_name},
        fields=["achievement", "achievement_type", "level"],
        order_by="level desc",
    )

    if not earned_rows:
        return {"student_id": student_id, "achievements": []}

    achievement_ids = [r.achievement for r in earned_rows]

    meta_rows = frappe.get_all(
        "Citizenship Achievement",
        filters={"name": ["in", achievement_ids]},
        fields=["name", "name1", "achievement_type", "color_code", "file_url"],
    )
    meta_map = {r.name: r for r in meta_rows}

    trans_names, trans_descs = _bulk_achievement_translations(achievement_ids, lang)

    achievements = []
    for row in earned_rows:
        meta = meta_map.get(row.achievement)
        eng_name = (meta.name1 if meta else None) or row.achievement
        title = trans_names.get(row.achievement) or eng_name
        achievements.append({
            "achievement": row.achievement,
            "name": title,
            "eng_name": eng_name,
            "achievement_type": row.achievement_type or (meta.achievement_type if meta else None),
            "level": row.level,
            "color_code": meta.color_code if meta else None,
            "file_url": meta.file_url if meta else None,
        })

    return {"student_id": student_id, "achievements": achievements}


@frappe.whitelist(allow_guest=True)
def get_achievement_detail(achievement=None, lang=None):
    achievement = achievement or frappe.form_dict.get("achievement")
    lang = lang or frappe.form_dict.get("lang")
    if not achievement:
        frappe.throw("achievement is required", frappe.ValidationError)

    meta = frappe.db.get_value(
        "Citizenship Achievement",
        achievement,
        ["name1", "achievement_type", "description", "color_code", "file_url"],
        as_dict=True,
    )
    if not meta:
        frappe.throw("Achievement not found", frappe.DoesNotExistError)

    eng_name = meta.name1 or achievement
    eng_desc = meta.description or ""
    title = eng_name
    desc = eng_desc

    if lang and lang.lower() not in ("en", "english"):
        trans = frappe.db.get_value(
            "Citizenship Achievement Translation",
            {"parent": achievement, "language": lang},
            ["translated_name", "translated_description"],
            as_dict=True,
        )
        if trans:
            title = trans.translated_name or eng_name
            desc = trans.translated_description or eng_desc

    return {
        "achievement": achievement,
        "name": title,
        "eng_name": eng_name,
        "achievement_type": meta.achievement_type,
        "description": desc,
        "eng_description": eng_desc,
        "color_code": meta.color_code,
        "file_url": meta.file_url,
    }


@frappe.whitelist()
def award_achievement(student_id=None, achievement=None, level=None):
    student_id = student_id or frappe.form_dict.get("student_id")
    achievement = achievement or frappe.form_dict.get("achievement")
    level = level if level is not None else frappe.form_dict.get("level")

    if not student_id or not achievement or level is None:
        frappe.throw("student_id, achievement, and level are required", frappe.ValidationError)

    level = int(level)

    if not frappe.db.exists("Citizenship Achievement", achievement):
        frappe.throw("Achievement not found", frappe.DoesNotExistError)

    learner_name = _get_or_create_learner(student_id)
    achievement_type = frappe.db.get_value("Citizenship Achievement", achievement, "achievement_type")

    # Single atomic upsert using PostgreSQL INSERT … ON CONFLICT.
    # Requires a unique constraint on (parent, achievement) on the child table.
    # If the row does not exist it is inserted.
    # If it exists and the new level is higher, we update.
    # If it exists and the new level is not higher, we do nothing.
    # All three cases are handled in one round-trip — no race condition.
    frappe.db.sql(
        """
        INSERT INTO "tabCitizenship Learner Achievement"
            (name, parent, parenttype, parentfield,
             achievement, achievement_type, level,
             creation, modified, modified_by, owner)
        VALUES
            (%s, %s, 'Citizenship Learner', 'achievements',
             %s, %s, %s,
             NOW(), NOW(), 'Administrator', 'Administrator')
        ON CONFLICT (parent, achievement)
        DO UPDATE
           SET level    = EXCLUDED.level,
               modified = NOW()
         WHERE "tabCitizenship Learner Achievement".level < EXCLUDED.level
        """,
        (
            frappe.generate_hash(length=10),
            learner_name,
            achievement,
            achievement_type,
            level,
        ),
    )
    frappe.db.commit()

    # Read back to determine what actually happened
    current = frappe.db.get_value(
        "Citizenship Learner Achievement",
        {"parent": learner_name, "achievement": achievement},
        ["level"],
        as_dict=True,
    )

    current_level = current.level if current else level
    awarded = current_level == level  # True if our value is now stored

    return {
        "awarded": awarded,
        "achievement": achievement,
        "level": current_level,
    }