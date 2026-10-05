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
        "capacity_retry_count",
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


def get_for_update(run_name):
    rows = frappe.db.sql(
        "select * from `tabTap Voice Run` where name = %(name)s for update",
        {"name": run_name},
        as_dict=True,
    )
    return frappe._dict(rows[0]) if rows else None


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


def increment(run_name, field, amount=1):
    current = frappe.db.get_value(RUN_DOCTYPE, run_name, field) or 0
    set_fields(run_name, {field: current + amount})


def transition(run_name, from_status, to_status, extra_fields=None):
    if not can_transition(from_status, to_status):
        frappe.throw(f"Cannot transition Tap Voice Run from {from_status} to {to_status}")
    fields = dict(extra_fields or {})
    fields["status"] = to_status
    set_fields(run_name, fields)


def conditional_write_url(item_id, url, content_hash, expected_modified):
    frappe.db.sql(
        """
        update `tabSubmission`
        set audio_feedback_url = %(url)s
        where name = %(name)s
          and (audio_feedback_url is null or audio_feedback_url = '')
          and (status is null or status != 'Failed')
          and modified = %(expected_modified)s
        """,
        {"name": item_id, "url": url, "expected_modified": expected_modified},
    )
    cursor = frappe.db._cursor
    return getattr(cursor, "rowcount", 0)