import frappe


@frappe.whitelist(allow_guest=True)
def get_learner_achievements(learner_id=None):
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    rows = frappe.db.sql(
        """
        SELECT achievement, level
        FROM "tabCitizenship Learner Achievement"
        WHERE parent=%s
        ORDER BY level DESC
        """,
        learner_id,
        as_dict=True,
    )
    return {
        "learner_id": learner_id,
        "achievements": [{"achievement": r.achievement, "level": r.level} for r in rows],
    }


@frappe.whitelist()
def award_achievement(learner_id=None, achievement=None, level=None):
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    achievement = achievement or frappe.form_dict.get("achievement")
    level = level if level is not None else frappe.form_dict.get("level")

    if not learner_id or not achievement or level is None:
        frappe.throw("learner_id, achievement, and level are required", frappe.ValidationError)

    level = int(level)

    frappe.db.sql(
        """
        INSERT INTO "tabCitizenship Learner Achievement"
            (name, parent, parenttype, parentfield,
             achievement, level,
             creation, modified, modified_by, owner)
        VALUES
            (%s, %s, 'Citizenship Learner', 'achievements',
             %s, %s,
             NOW(), NOW(), 'Administrator', 'Administrator')
        ON CONFLICT (parent, achievement)
        DO UPDATE
           SET level    = EXCLUDED.level,
               modified = NOW()
         WHERE "tabCitizenship Learner Achievement".level < EXCLUDED.level
        """,
        (frappe.generate_hash(length=10), learner_id, achievement, level),
    )
    frappe.db.commit()

    current = frappe.db.sql(
        "SELECT level FROM \"tabCitizenship Learner Achievement\" WHERE parent=%s AND achievement=%s LIMIT 1",
        (learner_id, achievement),
        as_dict=True,
    )
    current_level = current[0].level if current else level
    return {"awarded": current_level == level, "achievement": achievement, "level": current_level}