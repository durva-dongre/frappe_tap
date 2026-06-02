import frappe

@frappe.whitelist(allow_guest=True)
def get_videos_for_unit(unit_id: str, language: str = None):
    # Get content items of type VideoClass from the unit
    unit = frappe.get_doc("LearningUnit", unit_id)
    video_ids = [
        row.content for row in (unit.content_items or [])
        if (row.content_type or "").lower() == "videoclass" and row.content
    ]
    if not video_ids:
        return {"unit_id": unit_id, "videos": [], "total": 0}

    videos = []
    for vid_id in video_ids:
        try:
            doc = frappe.get_doc("VideoClass", vid_id)
            videos.append({
                "id":                doc.name,
                "title":             getattr(doc, "video_name", None),
                "video_url":         getattr(doc, "video_youtube_url", None),
                "video_youtube_url": getattr(doc, "video_youtube_url", None),
                "description":       getattr(doc, "description", None),
                "duration":          str(getattr(doc, "duration", None) or ""),
                "difficulty_tier":   getattr(doc, "difficulty_tier", None),
            })
        except Exception:
            continue

    return {"unit_id": unit_id, "videos": videos, "total": len(videos)}


@frappe.whitelist(allow_guest=True)
def get_video(video_id: str):
    doc = frappe.get_doc("VideoClass", video_id)
    return {
        "id":                doc.name,
        "title":             getattr(doc, "video_name", None),
        "video_url":         getattr(doc, "video_youtube_url", None),
        "video_youtube_url": getattr(doc, "video_youtube_url", None),
        "description":       getattr(doc, "description", None),
        "duration":          str(getattr(doc, "duration", None) or ""),
        "difficulty_tier":   getattr(doc, "difficulty_tier", None),
    }
