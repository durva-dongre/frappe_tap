from __future__ import annotations

import frappe

from tap_lms.tap_app.api import tap_app_method
from shared.errors import NotFound
from shared.submission.review_result import handle_review_result


@tap_app_method
def review_result_webhook(submission_id: str):
    """Entrypoint for an external grading/review pipeline that updates a
    Submission's own status/result_status fields directly (rather than
    through the RabbitMQ feedback_consumer path) and then needs the reward
    side-effects (points/gems/gallery notification) applied.

    FIX: this file previously existed but was completely empty -- nothing
    anywhere called shared.submission.review_result.handle_review_result,
    so the submission-review points/gems reward path was dead code in
    production. feedback_handler/feedback_consumer.py's RabbitMQ path is the
    other, primary entrypoint into handle_review_result (see that module);
    this webhook exists for any reviewer/grading system that writes directly
    to the Submission doctype instead of going through RabbitMQ.

    _already_rewarded's feedback_ready_processed_at guard inside
    handle_review_result makes this safe to call more than once for the same
    submission (e.g. once from this webhook and, redundantly, once from the
    RabbitMQ consumer) -- only the first call that observes a rewardable,
    not-yet-rewarded submission actually grants points/gems.
    """
    try:
        sub = frappe.get_doc("Submission", submission_id)
    except frappe.DoesNotExistError:
        raise NotFound()
    return handle_review_result(sub)