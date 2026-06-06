import frappe


def _parse_fields(fields_param):
    if not fields_param:
        return None
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


@frappe.whitelist(allow_guest=True)
def get_video(video_id=None, lang=None, mode="stream", fields=None):
    video_id = video_id or frappe.form_dict.get("video_id")
    if not video_id:
        frappe.throw("video_id is required", frappe.ValidationError)

    mode = (mode or frappe.form_dict.get("mode", "stream")).lower()
    optional = _parse_fields(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    doc = frappe.get_doc("VideoClass", video_id)

    trans = None
    if lang and lang.lower() not in ("en", "english"):
        for row in (doc.video_translations or []):
            if row.language == lang:
                trans = row
                break

    def _t(trans_val, fallback):
        return (trans_val or fallback) if trans else fallback

    if mode == "download":
        url = _t(
            trans.video_url if trans else None,
            doc.video_url,
        )
    else:
        url = _t(
            trans.video_youtube_url if trans else None,
            doc.video_youtube_url,
        )

    response = {
        "id": doc.name,
        "title": _t(trans.translated_name if trans else None, doc.video_name),
        "eng_name": doc.video_name,
        "url": url,
        "duration": str(doc.duration or ""),
        "points": doc.points or 10,
    }

    if _want("description"):
        response["description"] = _t(
            trans.translated_description if trans else None, doc.description
        )
    if _want("subtitle"):
        response["subtitle_file"] = _t(
            trans.subtitle_file if trans else None, doc.subtitle_file
        )
    if _want("transcript"):
        response["video_transcript"] = _t(
            trans.video_transcript if trans else None, doc.video_transcript
        )

    return response