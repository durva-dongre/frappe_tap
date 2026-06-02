import frappe

PAGE_SIZE_DEFAULT = 10
PAGE_SIZE_MAX = 50


def _clamp_limit(limit):
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = PAGE_SIZE_DEFAULT
    return max(1, min(limit, PAGE_SIZE_MAX))


@frappe.whitelist(allow_guest=True)
def get_units_for_course(course_id: str, limit=PAGE_SIZE_DEFAULT, after_index=None):
    limit = _clamp_limit(limit)
    filters = {"parent": course_id, "parenttype": "Course Level"}
    if after_index:
        try:
            filters["idx"] = [">", int(after_index)]
        except (TypeError, ValueError):
            pass

    rows = frappe.get_all(
        "LearningUnitList",
        filters=filters,
        fields=["learning_unit", "idx", "week_no"],
        order_by="idx asc",
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    if not rows:
        return {
            "course_id": course_id,
            "units": [],
            "count": 0,
            "has_more": False,
            "next_cursor": None,
        }

    unit_ids = [r.learning_unit for r in rows if r.learning_unit]
    units_data = frappe.get_all(
        "LearningUnit",
        filters={"name": ["in", unit_ids]},
        fields=[
            "name", "unit_name", "unit_type", "activity_type", "difficulty_tier",
            "order", "completion_criteria", "estimated_duration", "status",
            "certificate_on_completion",
        ],
    )
    by_name = {u.name: u for u in units_data}

    units = []
    for r in rows:
        u = by_name.get(r.learning_unit)
        if not u:
            continue
        units.append({
            "index":                  r.idx,
            "week_no":                r.get("week_no") or r.idx,
            "unit_id":                u.name,
            "title":                  u.unit_name,
            "unit_type":              u.unit_type,
            "activity_type":          u.activity_type,
            "difficulty_tier":        u.difficulty_tier,
            "order":                  u.order,
            "completion_criteria":    u.completion_criteria,
            "estimated_duration":     u.estimated_duration,
            "status":                 u.status,
            "certificate_on_completion": bool(u.certificate_on_completion),
        })

    return {
        "course_id":   course_id,
        "units":       units,
        "count":       len(units),
        "has_more":    has_more,
        "next_cursor": rows[-1]["idx"] if has_more else None,
    }


def _resolve_content_id(row):
    """
    Try every plausible field name on a UnitContentItem child row.
    Also does a targeted DB lookup by content_type if the direct
    field approach returns nothing.
    """
    # -- Direct field probes (add more as you discover them) --
    candidates = [
        "content_id", "content", "link",
        "video_class", "video", "videoclass",
        "quiz", "quiz_id",
        "reference", "reference_name", "item",
    ]
    for field in candidates:
        val = getattr(row, field, None)
        if val:
            return str(val)

    # -- Fallback: look up via the child table's own `name` in the DB --
    # This exposes ALL columns so we can see the real field name once.
    content_type = getattr(row, "content_type", None) or ""
    row_name     = getattr(row, "name", None)
    if row_name:
        try:
            raw = frappe.db.get_value(
                "UnitContentItem", row_name, "*", as_dict=True
            )
            if raw:
                frappe.logger().warning(
                    f"[get_unit] UnitContentItem {row_name} full row: {dict(raw)}"
                )
                # Try the same candidates on the raw dict
                for field in candidates:
                    val = raw.get(field)
                    if val:
                        return str(val)
                # Last resort: any non-empty Link-type value in the dict
                skip = {
                    "name", "owner", "creation", "modified", "modified_by",
                    "docstatus", "idx", "parent", "parentfield", "parenttype",
                    "content_type",
                }
                for k, v in raw.items():
                    if k not in skip and v and isinstance(v, str) and v.strip():
                        frappe.logger().warning(
                            f"[get_unit] fallback content_id from field '{k}' = '{v}'"
                        )
                        return v
        except Exception as e:
            frappe.logger().error(f"[get_unit] DB lookup failed for {row_name}: {e}")

    return None


@frappe.whitelist(allow_guest=True)
def get_unit(unit_id: str):
    doc = frappe.get_doc("LearningUnit", unit_id)
    content_items = [
        {
            "idx":          row.idx,
            "content_type": getattr(row, "content_type", None) or "",
            "content_id":   getattr(row, "content", None) or "",
            "is_optional":  bool(getattr(row, "is_optional", False)),
        }
        for row in (doc.content_items or [])
    ]
    return {
        "unit_id":                   doc.name,
        "title":                     doc.unit_name,
        "unit_type":                 doc.unit_type,
        "order":                     doc.order,
        "completion_criteria":       doc.completion_criteria,
        "estimated_duration":        doc.estimated_duration,
        "status":                    doc.status,
        "certificate_on_completion": bool(doc.certificate_on_completion),
        "content_items":             content_items,
        "total_content":             len(content_items),
    }
