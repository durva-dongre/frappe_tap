from __future__ import annotations

from shared.enrollment.active_batch import get_active_program_enrollment
from shared.progress.unit_progress import (
    resolve_current_unit_for_track,
    resolve_last_activity_type_for_track,
    attempt_info_for_submission,
)
from shared.enrollment.unit_rotation import next_unit_for


def _mark_feedback_viewed_if_pending(pe_doc) -> None:
    if pe_doc.stage == "feedback_tobe_viewed":
        pe_doc.stage = "feedback_viewed"
        pe_doc.save(ignore_permissions=True)


def _find_last_submission_row(student_id: str) -> dict | None:
    import frappe
    rows = frappe.get_all(
        "Submission",
        filters={"student_id": student_id},
        fields=["name", "assignment_id_link", "status", "result_status", "submission_url", "grade",
                "overall_feedback_translated", "audio_feedback_url",
                "program_enrollment", "created_at"],
        order_by="created_at desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None


def get_sync_payload(student_id: str, last_updated_epoch: int) -> dict:
    pe = get_active_program_enrollment(student_id)
    current_epoch = int(pe.last_activity_at.timestamp()) if pe.last_activity_at else 0

    if current_epoch <= (last_updated_epoch or 0):
        return {"changed": False, "updated_at": last_updated_epoch or current_epoch}

    last_submission = _find_last_submission_row(student_id)
    payload = {
        "changed": True,
        "updated_at": current_epoch,
        "points": pe.points or 0,
        "gems": pe.gems or 0,
        "current_learning_unit": resolve_current_unit_for_track(pe, "program", fallback_resolver=next_unit_for),
        "last_activity_type": resolve_last_activity_type_for_track(pe, "program"),
    }
    if last_submission:
        # FIX: previously called a local _attempt_info_for_submission(pe, ...)
        # that only searched pe.unit_progress (the student's CURRENTLY ACTIVE
        # enrollment). If the most recent Submission row happened to belong
        # to a past enrollment (e.g. the student just renewed/changed
        # enrollment and hasn't submitted anything new under the new one
        # yet), that search would silently miss the row and report a wrong
        # attempt_number=1 / attempts_remaining=cap, even if the real
        # submission was, say, attempt 2 of 2. attempt_info_for_submission
        # (shared/progress/unit_progress.py) resolves the owning row
        # globally, by submission name, with no dependency on "active
        # enrollment" being the right scope.
        attempt_number, attempts_remaining = attempt_info_for_submission(last_submission.name)
        # Frappe forwards the submission's own stored URLs (submission_url,
        # audio_feedback_url) directly, under "view_url" and
        # "overall_feedback_audio_url" -- the Worker is responsible for
        # signing/sharing these on to the frontend (it parses the object
        # key back out of the URL it already recognizes and signs a fresh,
        # time-limited GET URL for the authenticated GCS bucket; the audio
        # URL points at the public bucket and needs no signing). Frappe does
        # not need to know the object-key shape to do this.
        payload["last_submission"] = {
            "name": last_submission.name,
            "assignment_id_link": last_submission.assignment_id_link,
            "status": last_submission.status,
            "result_status": last_submission.result_status,
            "view_url": last_submission.submission_url,
            "score": last_submission.grade,
            "overall_feedback_translated": last_submission.overall_feedback_translated,
            "overall_feedback_audio_url": last_submission.audio_feedback_url,
            "attempt_number": attempt_number,
            "attempts_remaining": attempts_remaining,
            "updated_at": current_epoch,
        }
        _mark_feedback_viewed_if_pending(pe)
    return payload


def get_last_submission_payload(student_id: str, last_updated_epoch: int) -> dict:
    pe = get_active_program_enrollment(student_id)
    base = {"points": pe.points or 0, "gems": pe.gems or 0}

    last_submission = _find_last_submission_row(student_id)
    if not last_submission:
        return {"has_update": False, **base}

    sub_epoch = int(last_submission.created_at.timestamp()) if last_submission.created_at else 0
    if sub_epoch <= (last_updated_epoch or 0):
        return {"has_update": False, **base}

    attempt_number, attempts_remaining = attempt_info_for_submission(last_submission.name)
    _mark_feedback_viewed_if_pending(pe)
    return {
        "has_update": True,
        **base,
        "last_submission": {
            "name": last_submission.name,
            "assignment_id_link": last_submission.assignment_id_link,
            "status": last_submission.status,
            "result_status": last_submission.result_status,
            "view_url": last_submission.submission_url,
            "score": last_submission.grade,
            "overall_feedback_translated": last_submission.overall_feedback_translated,
            "overall_feedback_audio_url": last_submission.audio_feedback_url,
            "attempt_number": attempt_number,
            "attempts_remaining": attempts_remaining,
            "updated_at": sub_epoch,
        },
    }