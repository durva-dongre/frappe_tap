import frappe


def _fetch_achievements_sql(learner_id):
    rows = frappe.db.sql(
        """
        SELECT achievement, level
        FROM "tabTapapp Learner Achievements"
        WHERE parent=%s
        ORDER BY idx ASC
        """,
        learner_id,
        as_dict=True,
    )
    return [{"achievement": r.achievement, "level": r.level} for r in rows]


@frappe.whitelist(allow_guest=True)
def get_learner_achievements(learner_id=None):
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)
    return {"learner_id": learner_id, "achievements": _fetch_achievements_sql(learner_id)}


@frappe.whitelist()
def award_achievement(learner_id=None, achievement=None, level=None):
    """
    Tapapp Learner Achievements has no unique constraint defined in the
    doctype json (unlike a hypothetical (parent, achievement) unique key),
    so we look the row up manually and update-or-insert rather than relying
    on ON CONFLICT, to stay strictly compatible with the schema as given.
    """
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    achievement = achievement or frappe.form_dict.get("achievement")
    level = level if level is not None else frappe.form_dict.get("level")

    if not learner_id or not achievement or level is None:
        frappe.throw("learner_id, achievement, and level are required", frappe.ValidationError)

    level = frappe.utils.cstr(level)

    existing = frappe.db.sql(
        'SELECT name, level FROM "tabTapapp Learner Achievements" WHERE parent=%s AND achievement=%s LIMIT 1',
        (learner_id, achievement),
        as_dict=True,
    )

    if existing:
        # Only "upgrade" — never downgrade an achievement level.
        if str(existing[0].level) < level:
            frappe.db.sql(
                'UPDATE "tabTapapp Learner Achievements" SET level=%s, modified=NOW() WHERE name=%s',
                (level, existing[0].name),
            )
            frappe.db.commit()
            current_level = level
            awarded = True
        else:
            current_level = existing[0].level
            awarded = False
    else:
        frappe.db.sql(
            """
            INSERT INTO "tabTapapp Learner Achievements"
                (name, parent, parenttype, parentfield, achievement, level,
                 creation, modified, modified_by, owner, idx)
            VALUES
                (%s, %s, 'Tapapp Learner', 'achievements', %s, %s,
                 NOW(), NOW(), 'Administrator', 'Administrator',
                 COALESCE((SELECT MAX(idx) FROM "tabTapapp Learner Achievements" WHERE parent=%s), 0) + 1)
            """,
            (frappe.generate_hash(length=10), learner_id, achievement, level, learner_id),
        )
        frappe.db.commit()
        current_level = level
        awarded = True

    return {"awarded": awarded, "achievement": achievement, "level": current_level}