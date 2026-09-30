import frappe

from tap_lms.tapvoice.constants import TRIGGER_CRON


def start_batch(trigger):
    job_id = "tapvoice-deploy"
    frappe.enqueue(
        "tap_lms.tapvoice.job.deploy.deploy_new",
        queue="long",
        job_id=job_id,
        deduplicate=True,
        trigger=trigger,
        enqueue_after_commit=True,
    )
    return {"queued": True}


def scheduled_start():
    start_batch(TRIGGER_CRON)