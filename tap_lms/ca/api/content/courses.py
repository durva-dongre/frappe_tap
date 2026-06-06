import frappe

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 50

_COURSE_BASE_FIELDS = [
    "name as id",
    "name1",
    "vertical",
    "level",
    "stage",
    "color_code",
]


def _clamp_limit(limit):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = PAGE_SIZE_DEFAULT
    return max(1, min(limit, PAGE_SIZE_MAX))


def _parse_fields(fields_param):
    if not fields_param:
        return set()
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


def _apply_translation(base_name1, trans_map, doc_id):
    t = trans_map.get(doc_id)
    translated = t.translated_name if t and t.translated_name else None
    return translated or base_name1, base_name1


@frappe.whitelist(allow_guest=True)
def get_course_verticals():
    cache_key = "content::course_verticals"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return frappe.parse_json(cached)

    verticals = frappe.get_all(
        "Course Verticals",
        fields=["name as id", "vertical_name as name"],
        order_by="vertical_name asc",
    )
    result = {"verticals": verticals}
    frappe.cache().set_value(cache_key, frappe.as_json(result), expires_in_sec=86400)
    return result


@frappe.whitelist(allow_guest=True)
def get_courses(
    lang=None,
    limit=PAGE_SIZE_DEFAULT,
    after=None,
    vertical=None,
    level=None,
    stage=None,
    search=None,
    fields=None,
):
    limit = _clamp_limit(limit)
    optional = _parse_fields(fields)
    want_icon = "icon" in optional
    want_image = "image" in optional

    select_fields = list(_COURSE_BASE_FIELDS)
    if want_icon:
        select_fields.append("icon")
    if want_image:
        select_fields.append("course_image")

    base_filters = {}
    if vertical:
        base_filters["vertical"] = vertical
    if level:
        base_filters["level"] = level
    if stage:
        base_filters["stage"] = stage

    if search:
        filters_a = dict(base_filters)
        filters_a["name1"] = ["like", f"%{search}%"]
        if after:
            filters_a["name"] = [">", after]

        phase_a = frappe.get_all(
            "Course Level",
            filters=filters_a,
            fields=["name"],
            order_by="name asc",
            limit=limit + 1,
        )
        id_set = {r.name for r in phase_a}

        if lang and lang.lower() not in ("en", "english"):
            trans_filters = {"language": lang, "translated_name": ["like", f"%{search}%"]}
            if base_filters.get("vertical") or base_filters.get("level") or base_filters.get("stage"):
                phase_b_ids_raw = frappe.get_all(
                    "Course_LevelTranslation",
                    filters=trans_filters,
                    fields=["parent"],
                )
                candidate_parents = [r.parent for r in phase_b_ids_raw]
                if candidate_parents:
                    scope_filters = dict(base_filters)
                    scope_filters["name"] = ["in", candidate_parents]
                    scoped = frappe.get_all("Course Level", filters=scope_filters, fields=["name"])
                    for r in scoped:
                        id_set.add(r.name)
            else:
                phase_b = frappe.get_all(
                    "Course_LevelTranslation",
                    filters=trans_filters,
                    fields=["parent"],
                )
                for r in phase_b:
                    id_set.add(r.parent)

        if not id_set:
            return {"courses": [], "count": 0, "has_more": False, "next_cursor": None}

        valid_ids = sorted([i for i in id_set if not after or i > after])
        paginated_ids = valid_ids[:limit + 1]

        if not paginated_ids:
            return {"courses": [], "count": 0, "has_more": False, "next_cursor": None}

        has_more = len(paginated_ids) > limit
        if has_more:
            paginated_ids = paginated_ids[:limit]

        courses_raw = frappe.get_all(
            "Course Level",
            filters={"name": ["in", paginated_ids]},
            fields=select_fields,
            order_by="name asc",
        )
    else:
        filters = dict(base_filters)
        if after:
            filters["name"] = [">", after]
        courses_raw = frappe.get_all(
            "Course Level",
            filters=filters,
            fields=select_fields,
            order_by="name asc",
            limit=limit + 1,
        )
        has_more = len(courses_raw) > limit
        if has_more:
            courses_raw = courses_raw[:limit]

    if not courses_raw:
        return {"courses": [], "count": 0, "has_more": False, "next_cursor": None}

    trans_map = {}
    if lang and lang.lower() not in ("en", "english"):
        ids = [r.id for r in courses_raw]
        trans_rows = frappe.get_all(
            "Course_LevelTranslation",
            filters={"parent": ["in", ids], "language": lang},
            fields=["parent", "translated_name"],
        )
        trans_map = {r.parent: r for r in trans_rows}

    courses = []
    for r in courses_raw:
        title, eng_name = _apply_translation(r.name1, trans_map, r.id)
        item = {
            "id": r.id,
            "title": title,
            "eng_name": eng_name,
            "vertical": r.vertical,
            "level": r.level,
            "stage": r.stage,
            "color_code": r.color_code,
        }
        if want_icon:
            item["icon"] = r.get("icon")
        if want_image:
            item["course_image"] = r.get("course_image")
        courses.append(item)

    return {
        "courses": courses,
        "count": len(courses),
        "has_more": has_more,
        "next_cursor": courses[-1]["id"] if has_more else None,
    }


@frappe.whitelist(allow_guest=True)
def get_course(course_id=None, lang=None, fields=None):
    course_id = course_id or frappe.form_dict.get("course_id")
    if not course_id:
        frappe.throw("course_id is required", frappe.ValidationError)

    optional = _parse_fields(fields) if fields else None
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    doc = frappe.get_doc("Course Level", course_id)

    trans = None
    if lang and lang.lower() not in ("en", "english"):
        t_row = frappe.db.get_value(
            "Course_LevelTranslation",
            {"parent": course_id, "language": lang},
            [
                "translated_name",
                "translated_course_summary",
                "translated_course_description",
                "translated_course_objectives",
                "translated_prerequisite_knowledge",
                "translated_download_url",
            ],
            as_dict=True,
        )
        trans = t_row

    def _t(translated_val, fallback):
        return (translated_val or fallback) if trans else fallback

    learning_units = [
        {"index": row.idx, "unit_id": row.learning_unit}
        for row in (doc.learning_units or [])
        if row.learning_unit
    ]

    title = _t(trans.translated_name if trans else None, doc.name1)

    response = {
        "id": doc.name,
        "title": title,
        "eng_name": doc.name1,
        "vertical": doc.vertical,
        "level": doc.level,
        "icon": doc.icon,
        "color_code": doc.color_code,
        "course_image": doc.course_image,
        "learning_units": learning_units,
    }

    if _want("summary"):
        response["summary"] = _t(
            trans.translated_course_summary if trans else None, doc.course_summary
        )
    if _want("description"):
        response["description"] = _t(
            trans.translated_course_description if trans else None, doc.course_description
        )
    if _want("objectives"):
        response["objectives"] = _t(
            trans.translated_course_objectives if trans else None, doc.course_objectives
        )
    if _want("prerequisite_knowledge"):
        response["prerequisite_knowledge"] = _t(
            trans.translated_prerequisite_knowledge if trans else None,
            doc.prerequisite_knowledge,
        )
    if _want("download_url"):
        response["download_url"] = _t(
            trans.translated_download_url if trans else None, doc.download_url
        )
    if _want("outcomes"):
        response["learning_outcomes"] = [
            {"objective": row.objective}
            for row in (doc.learning_outcomes or [])
            if getattr(row, "objective", None)
        ]

    return response


@frappe.whitelist(allow_guest=True)
def get_course_download_url(course_id=None, lang=None):
    course_id = course_id or frappe.form_dict.get("course_id")
    if not course_id:
        frappe.throw("course_id is required", frappe.ValidationError)

    eng_url = frappe.db.get_value("Course Level", course_id, "download_url")

    if lang and lang.lower() not in ("en", "english"):
        translated_url = frappe.db.get_value(
            "Course_LevelTranslation",
            {"parent": course_id, "language": lang},
            "translated_download_url",
        )
        if translated_url:
            return {"download_url": translated_url}

    return {"download_url": eng_url}