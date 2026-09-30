import frappe

from tap_lms.tapvoice.constants import (
    BAD_RUN_STATUSES,
    RUN_DOCTYPE,
    SETTINGS_DOCTYPE,
    STATUS_COMPLETED_WITH_FAILURES,
    STATUS_SKIPPED,
    STATUS_STOPPED,
)


def _success_percent(run):
    total = (run.written or 0) + (run.pod_failed or 0) + (run.not_processed or 0)
    if not total:
        return 100
    return int(round(100.0 * (run.written or 0) / total))


def _is_bad(run, settings_doc):
    if run.status in BAD_RUN_STATUSES:
        return True
    if run.status == STATUS_COMPLETED_WITH_FAILURES:
        return _success_percent(run) < settings_doc.bad_run_success_floor_percent
    return False


def evaluate(latest_run_name):
    settings_doc = frappe.get_single(SETTINGS_DOCTYPE)
    recent = frappe.get_all(
        RUN_DOCTYPE,
        filters={"status": ["not in", ["Draft", STATUS_SKIPPED, STATUS_STOPPED]]},
        fields=[
            "name",
            "status",
            "written",
            "pod_failed",
            "not_processed",
        ],
        order_by="creation desc",
        limit_page_length=settings_doc.max_consecutive_bad_runs,
    )
    if len(recent) < settings_doc.max_consecutive_bad_runs:
        return False
    if all(_is_bad(run, settings_doc) for run in recent):
        _trip(settings_doc)
        return True
    return False


def _trip(settings_doc):
    if not settings_doc.enabled:
        return
    frappe.db.set_value("Tap Voice Settings", None, "enabled", 0)
    frappe.db.commit()
    if settings_doc.alert_email:
        frappe.sendmail(
            recipients=[settings_doc.alert_email],
            subject="TapVoice circuit breaker tripped",
            message=(
                "TapVoice has been disabled automatically after consecutive bad runs. "
                "Check the Tap Voice Run list and re-enable in Tap Voice Settings once resolved."
            ),
        )