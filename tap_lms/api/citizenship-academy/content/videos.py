import frappe


@frappe.whitelist(allow_guest=True)
def get_videos(unit_id: str, language: str = None):
    filters = {"learning_unit": unit_id}
    if language:
        filters["language"] = language
    videos = frappe.get_all(
        "Learning Unit Video",
        filters=filters,
        fields=["name as id", "title", "video_url", "index", "language", "duration"],
        order_by="index asc",
    )
    return {
        "unit_id": unit_id,
        "language": language,
        "videos": videos,
        "total": len(videos),
    }


@frappe.whitelist(allow_guest=True)
def get_video(video_id: str):
    doc = frappe.get_doc("Learning Unit Video", video_id)
    return {
        "id": doc.name,
        "title": doc.title if hasattr(doc, "title") else None,
        "video_url": doc.video_url if hasattr(doc, "video_url") else None,
        "index": doc.index if hasattr(doc, "index") else None,
        "language": doc.language if hasattr(doc, "language") else None,
        "duration": doc.duration if hasattr(doc, "duration") else None,
        "learning_unit": doc.learning_unit if hasattr(doc, "learning_unit") else None,
    }