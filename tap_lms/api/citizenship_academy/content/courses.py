import frappe

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 50


def _clamp_limit(limit):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = PAGE_SIZE_DEFAULT
    return max(1, min(limit, PAGE_SIZE_MAX))


@frappe.whitelist(allow_guest=True)
def get_courses(limit=PAGE_SIZE_DEFAULT, after=None, vertical=None, level=None, stage=None):
    limit = _clamp_limit(limit)

    filters = {}
    if vertical:
        filters["vertical"] = vertical
    if level:
        filters["level"] = level
    if stage:
        filters["stage"] = stage
    if after:
        filters["name"] = [">", after]

    courses = frappe.get_all(
        "Course Level",
        filters=filters,
        fields=[
            "name as id", "name1 as title", "vertical", "level", "stage",
            "course_summary", "course_image", "icon", "color_code",
        ],
        order_by="name asc",
        limit=limit + 1,
    )

    has_more = len(courses) > limit
    if has_more:
        courses = courses[:limit]

    return {
        "courses": courses,
        "count": len(courses),
        "has_more": has_more,
        "next_cursor": courses[-1]["id"] if has_more else None,
    }


@frappe.whitelist(allow_guest=True)
def get_course(course_id: str):
    doc = frappe.get_doc("Course Level", course_id)
    units = [
        {"index": i + 1, "unit_id": row.learning_unit}
        for i, row in enumerate(doc.learning_units or [])
        if row.learning_unit
    ]
    outcomes = [
        {"objective": row.objective}
        for row in (doc.learning_outcomes or [])
        if getattr(row, "objective", None)
    ]
    return {
        "id": doc.name,
        "title": doc.name1,
        "vertical": doc.vertical,
        "level": doc.level,
        "stage": doc.stage,
        "icon": doc.icon,
        "color_code": doc.color_code,
        "course_summary": doc.course_summary,
        "course_image": doc.course_image,
        "course_description": doc.course_description,
        "course_objectives": doc.course_objectives,
        "prerequisite_knowledge": doc.prerequisite_knowledge,
        "learning_outcomes": outcomes,
        "learning_units": units,
        "total_units": len(units),
    }