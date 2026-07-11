import frappe


def fetch_achievements(learner_id):
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


def fetch_achievements_bulk(learner_ids):
    if not learner_ids:
        return {}
    placeholders = ",".join(["%s"] * len(learner_ids))
    rows = frappe.db.sql(
        f"""
        SELECT parent, achievement, level
        FROM "tabTapapp Learner Achievements"
        WHERE parent IN ({placeholders})
        ORDER BY parent, idx ASC
        """,
        tuple(learner_ids),
        as_dict=True,
    )
    result = {lid: [] for lid in learner_ids}
    for r in rows:
        result[r.parent].append({"achievement": r.achievement, "level": r.level})
    return result


@frappe.whitelist(allow_guest=True)
def get_learner_achievements(learner_id=None):
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)
    return {"learner_id": learner_id, "achievements": fetch_achievements(learner_id)}


@frappe.whitelist()
def award_achievement(learner_id=None, achievement=None, level=None):
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    achievement = achievement or frappe.form_dict.get("achievement")
    level = level if level is not None else frappe.form_dict.get("level")

    if not learner_id or not achievement or level is None:
        frappe.throw("learner_id, achievement, and level are required", frappe.ValidationError)

    level_str = frappe.utils.cstr(level)
    try:
        level_int = int(level_str)
    except (TypeError, ValueError):
        frappe.throw("level must be numeric", frappe.ValidationError)

    row = frappe.db.sql(
        """
        INSERT INTO "tabTapapp Learner Achievements"
            (name, parent, parenttype, parentfield, achievement, level,
             creation, modified, modified_by, owner, idx)
        VALUES
            (%(name)s, %(parent)s, 'Tapapp Learner', 'achievements', %(achievement)s, %(level)s,
             NOW(), NOW(), 'Administrator', 'Administrator',
             COALESCE((SELECT MAX(idx) FROM "tabTapapp Learner Achievements" WHERE parent=%(parent)s), 0) + 1)
        ON CONFLICT (parent, achievement) DO UPDATE
           SET level = GREATEST(
                   CAST("tabTapapp Learner Achievements".level AS INTEGER),
                   CAST(EXCLUDED.level AS INTEGER)
               )::text,
               modified = NOW()
        RETURNING level, (xmax = 0) AS inserted
        """,
        {
            "name": frappe.generate_hash(length=10),
            "parent": learner_id,
            "achievement": achievement,
            "level": level_str,
        },
        as_dict=True,
    )[0]

    current_level = row.level
    awarded = row.inserted or int(current_level) == level_int

    return {"awarded": awarded, "achievement": achievement, "level": current_level}