import frappe

RUN_DOCTYPE = "Tap Voice Run"

TRANSITIONS = {
    "Draft": {"Deploying"},
    "Deploying": {"Starting", "Deploy Failed", "Skipped"},
    "Starting": {"Running", "Timed Out", "Deploy Failed", "Stopping"},
    "Running": {"Stopping", "Completed", "Completed With Failures", "Failed", "Timed Out", "Lost"},
    "Stopping": {"Stopped", "Timed Out"},
}

TERMINAL_STATUSES = frozenset(
    {
        "Completed",
        "Completed With Failures",
        "Stopped",
        "Failed",
        "Timed Out",
        "Lost",
        "Deploy Failed",
        "Skipped",
    }
)

INT_FIELDS = frozenset(
    {
        "eligible_found",
        "urgent_count",
        "truncated_count",
        "manifest_count",
        "served_count",
        "skipped_unsupported_language",
        "skipped_empty_text",
        "skipped_recent_failure",
        "skipped_flagged",
        "deferred_over_budget",
        "written",
        "already_set",
        "stale",
        "hash_mismatch",
        "not_in_manifest",
        "changed_during_write",
        "pod_failed",
        "not_processed",
        "pod_uploaded",
        "pod_generated",
        "pod_decoded",
        "pod_truncated",
        "pod_retried",
        "pod_tokens",
        "pod_skipped_existing",
        "remaining_reported",
        "termination_attempts",
    }
)

FLOAT_FIELDS = frozenset(
    {
        "pod_audio_seconds",
        "pod_startup_seconds",
        "pod_run_seconds",
        "pod_tokens_per_second",
        "pod_gpu_sec_per_audio_min",
        "pod_reported_gpu_seconds",
        "billed_seconds",
        "overhead_seconds",
        "cost_per_clip_usd",
        "gpu_sec_per_audio_min",
    }
)

CURRENCY_FIELDS = frozenset(
    {
        "estimated_cost_usd",
        "hourly_rate",
        "estimated_cost_usd_final",
        "pod_cost_proxy_usd",
        "cost_per_1000_usd",
    }
)


def can_transition(from_status, to_status):
    return to_status in TRANSITIONS.get(from_status, set())


def is_terminal(status):
    return status in TERMINAL_STATUSES


def _sanitize(fields):
    clean = dict(fields)
    for key in INT_FIELDS:
        if key in clean and clean[key] is None:
            clean[key] = 0
    for key in FLOAT_FIELDS:
        if key in clean and clean[key] is None:
            clean[key] = 0.0
    for key in CURRENCY_FIELDS:
        if key in clean and clean[key] is None:
            clean[key] = 0
    return clean


def set_fields(run_name, fields):
    clean = _sanitize(fields)
    frappe.db.set_value(RUN_DOCTYPE, run_name, clean, update_modified=False)


def transition(run_name, from_status, to_status, extra_fields=None):
    if not can_transition(from_status, to_status):
        frappe.throw(f"Cannot transition Tap Voice Run from {from_status} to {to_status}")
    fields = dict(extra_fields or {})
    fields["status"] = to_status
    set_fields(run_name, fields)


def conditional_write_url(run_name, item_id, url, content_hash, expected_modified):
    result = frappe.db.sql(
        """
        update `tabTap Voice Run`
        set manifest_json = manifest_json
        where name = %(name)s
        """,
        {"name": run_name},
    )
    cursor = frappe.db._cursor
    return getattr(cursor, "rowcount", 0)