import frappe


def _build_trans_map(doctype, ids, lang, fields):
    if not ids or not lang or lang.lower() in ("en", "english"):
        return {}
    rows = frappe.get_all(
        doctype,
        filters={"parent": ["in", ids], "language": lang},
        fields=["parent"] + fields,
    )
    return {r.parent: r for r in rows}


def _parse_fields(fields_param):
    if not fields_param:
        return None
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


def _resolve_videos_bulk(video_ids, lang):
    if not video_ids:
        return {}

    videos_raw = frappe.get_all(
        "VideoClass",
        filters={"name": ["in", video_ids]},
        fields=[
            "name as id",
            "video_name",
            "video_youtube_url",
            "video_url",
            "subtitle_file",
            "video_transcript",
            "duration",
            "points",
            "description",
        ],
    )

    trans_map = _build_trans_map(
        "VideoTranslation",
        video_ids,
        lang,
        ["translated_name", "translated_description", "video_youtube_url",
         "video_url", "subtitle_file", "video_transcript"],
    )

    result = {}
    for v in videos_raw:
        t = trans_map.get(v.id)
        result[v.id] = {
            "id": v.id,
            "title": (t.translated_name if t and t.translated_name else None) or v.video_name,
            "eng_name": v.video_name,
            "description": (t.translated_description if t and t.translated_description else None) or v.description,
            "url": (t.video_youtube_url if t and t.video_youtube_url else None) or v.video_youtube_url,
            "download_url": (t.video_url if t and t.video_url else None) or v.video_url,
            "subtitle_file": (t.subtitle_file if t and t.subtitle_file else None) or v.subtitle_file,
            "video_transcript": (t.video_transcript if t and t.video_transcript else None) or v.video_transcript,
            "duration": str(v.duration or ""),
            "points": v.points or 10,
        }
    return result


def _resolve_quizzes_bulk(quiz_ids, lang):
    if not quiz_ids:
        return {}

    from tap_lms.ca.api.content.quizzes import _assemble_quizzes_bulk
    return _assemble_quizzes_bulk(quiz_ids, lang)


@frappe.whitelist(allow_guest=True)
def get_unit(unit_id=None, lang=None, include_content_data=False, fields=None):
    unit_id = unit_id or frappe.form_dict.get("unit_id")
    if not unit_id:
        frappe.throw("unit_id is required", frappe.ValidationError)

    include_content_data = str(include_content_data).lower() in ("true", "1", "yes")
    optional = _parse_fields(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    doc = frappe.get_doc("LearningUnit", unit_id)

    unit_trans = None
    if lang and lang.lower() not in ("en", "english"):
        for row in (doc.translations or []):
            if row.language == lang:
                unit_trans = row
                break

    title = (unit_trans.translated_name if unit_trans and unit_trans.translated_name else None) or doc.unit_name
    description = (unit_trans.translated_description if unit_trans and unit_trans.translated_description else None) or doc.description

    video_ids = []
    quiz_ids = []
    content_items_raw = []

    for row in (doc.content_items or []):
        ct = (getattr(row, "content_type", "") or "").strip()
        cid = getattr(row, "content", None) or ""
        content_items_raw.append({
            "idx": row.idx,
            "content_type": ct,
            "content_id": cid,
            "is_optional": bool(getattr(row, "is_optional", False)),
        })
        if cid:
            ct_lower = ct.lower()
            if ct_lower == "videoclass":
                video_ids.append(cid)
            elif ct_lower == "quiz":
                quiz_ids.append(cid)

    video_title_map = {}
    if video_ids:
        v_rows = frappe.get_all(
            "VideoClass",
            filters={"name": ["in", video_ids]},
            fields=["name", "video_name"],
        )
        video_title_map = {r.name: r.video_name for r in v_rows}

    quiz_title_map = {}
    if quiz_ids:
        q_rows = frappe.get_all(
            "Quiz",
            filters={"name": ["in", quiz_ids]},
            fields=["name", "quiz_name"],
        )
        quiz_title_map = {r.name: r.quiz_name for r in q_rows}

    video_trans_map = {}
    if video_ids and lang and lang.lower() not in ("en", "english"):
        vt_rows = frappe.get_all(
            "VideoTranslation",
            filters={"parent": ["in", video_ids], "language": lang},
            fields=["parent", "translated_name"],
        )
        video_trans_map = {r.parent: r.translated_name for r in vt_rows}

    quiz_trans_map = {}
    if quiz_ids and lang and lang.lower() not in ("en", "english"):
        qt_rows = frappe.get_all(
            "QuizTranslation",
            filters={"parent": ["in", quiz_ids], "language": lang},
            fields=["parent", "translated_name"],
        )
        quiz_trans_map = {r.parent: r.translated_name for r in qt_rows}

    content_items = []
    for item in content_items_raw:
        cid = item["content_id"]
        ct_lower = item["content_type"].lower()
        if ct_lower == "videoclass":
            eng = video_title_map.get(cid, cid)
            title_item = video_trans_map.get(cid) or eng
        elif ct_lower == "quiz":
            eng = quiz_title_map.get(cid, cid)
            title_item = quiz_trans_map.get(cid) or eng
        else:
            eng = cid
            title_item = cid

        content_items.append({
            "idx": item["idx"],
            "content_type": item["content_type"],
            "content_id": cid,
            "title": title_item,
            "eng_name": eng,
            "is_optional": item["is_optional"],
        })

    response = {
        "unit_id": doc.name,
        "title": title,
        "eng_name": doc.unit_name,
        "certificate_on_completion": bool(doc.certificate_on_completion),
        "content_items": content_items,
    }

    if _want("description"):
        response["description"] = description

    if _want("sdg"):
        response["sdg_alignment"] = [
            {
                "sdg_goal": row.sdg_goal,
                "sdg_name": row.sdg_name or "",
            }
            for row in (doc.sdg_alignment or [])
            if row.sdg_goal
        ]

    if _want("objectives"):
        response["learning_objectives"] = [
            {"objective": row.objective}
            for row in (doc.learning_objectives or [])
            if getattr(row, "objective", None)
        ]

    if include_content_data:
        content_data = {}
        if video_ids:
            content_data["videos"] = _resolve_videos_bulk(video_ids, lang)
        if quiz_ids:
            content_data["quizzes"] = _resolve_quizzes_bulk(quiz_ids, lang)
        response["content_data"] = content_data

    return response