from __future__ import annotations

import frappe

from tap_lms.tap_app.api import tap_app_method
from shared.errors import NotFound
from shared.submission.review_result import handle_review_result


@tap_app_method
def review_result_webhook(submission_id: str):
    """Entrypoint for an external grading/review pipeline that writes a
    Submission's status/result_status fields directly (rather than through
    the RabbitMQ feedback_consumer path) and then needs the reward
    side-effects (points/gems/gallery notification) applied via
    shared.submission.review_result.handle_review_result. See that
    module's docstring for the full reward/gallery eligibility rules and
    why its reward branch is safe to invoke more than once per submission
    (handle_review_result's own feedback_ready_processed_at guard makes
    repeat calls for the same submission a no-op on the reward side,
    whether this webhook and the RabbitMQ consumer both fire for the same
    grading event or this endpoint is retried).
    """
    try:
        sub = frappe.get_doc("Submission", submission_id)
    except frappe.DoesNotExistError:
        raise NotFound()
    return handle_review_result(sub)