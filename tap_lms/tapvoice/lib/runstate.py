import frappe

from tap_lms.tapvoice.constants import (
    RUN_DOCTYPE,
    STATUS_COMPLETED,
    STATUS_COMPLETED_WITH_FAILURES,
    STATUS_DEPLOY_FAILED,
    STATUS_DEPLOYING,
    STATUS_DRAFT,
    STATUS_FAILED,
    STATUS_LOST,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    STATUS_STARTING,
    STATUS_STOPPED,
    STATUS_STOPPING,
    STATUS_TIMED_OUT,
    TERMINAL_STATUSES,
)

ALLOWED_TRANSITIONS = {
    STATUS_DRAFT: {STATUS_DEPLOYING, STATUS_SKIPPED},
    STATUS_DEPLOYING: {STATUS_STARTING, STATUS_DEPLOY_FAILED, STATUS_SKIPPED},
    STATUS_STARTING: {STATUS_RUNNING, STATUS_STOPPING, STATUS_TIMED_OUT, STATUS_LOST, STATUS_FAILED},
    STATUS_RUNNING: {
        STATUS_STOPPING,
        STATUS_COMPLETED,
        STATUS_COMPLETED_WITH_FAILURES,
        STATUS_TIMED_OUT,
        STATUS_LOST,
        STATUS_FAILED,
    },
    STATUS_STOPPING: {
        STATUS_STOPPED,
        STATUS_COMPLETED,
        STATUS_COMPLETED_WITH_FAILURES,
        STATUS_TIMED_OUT,
        STATUS_FAILED,
    },
}

# Whitelist of counter fields that may be incremented from pod-facing endpoints.
# Never build the column name from unvalidated input.
INCREMENTABLE_FIELDS = frozenset(
    {
        "written",
        "already_set",
        "stale",
        "hash_mismatch",
        "not_in_manifest",
        "changed_during_write",
        "pod_failed",
        "bad_url",
    }
)


def can_transition(current, target):
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, set())


def is_terminal(status):
    return status in TERMINAL_STATUSES


def get_for_update(run_name):
    rows = frappe.db.sql(
        f'select * from "tab{RUN_DOCTYPE}" where name=%s for update',
        run_name,
        as_dict=True,
    )
    return rows[0] if rows else None


def set_fields(run_name, fields):
    if not fields:
        return
    frappe.db.set_value(RUN_DOCTYPE, run_name, fields, update_modified=False)


def transition(run_name, current_status, target_status, extra_fields=None):
    if not can_transition(current_status, target_status):
        raise ValueError(f"illegal transition {current_status} -> {target_status}")
    fields = dict(extra_fields or {})
    fields["status"] = target_status
    set_fields(run_name, fields)


def increment(run_name, fieldname, amount=1):
    if fieldname not in INCREMENTABLE_FIELDS:
        frappe.throw(f"Field '{fieldname}' is not whitelisted for increment")
    frappe.db.sql(
        f'update "tab{RUN_DOCTYPE}" set "{fieldname}" = coalesce("{fieldname}", 0) + %s where name = %s',
        (amount, run_name),
    )


def conditional_write_url(submission_id, url, content_hash_value, expected_modified):
    """Writes the URL only if the row is still exactly as read (optimistic concurrency).

    Uses the DB-API cursor's own `rowcount` attribute, which both the MariaDB and
    Postgres backends in Frappe expose consistently after a write, instead of a
    vendor-specific SQL function like MySQL's ROW_COUNT() (which does not exist on
    Postgres) or a private, undocumented attribute.
    """
    frappe.db.sql(
        """
        update "tabSubmission"
        set audio_feedback_url = %(url)s
        where name = %(id)s
          and (audio_feedback_url is null or audio_feedback_url = '')
          and status != 'Failed'
          and modified = %(expected_modified)s
        """,
        {
            "url": url,
            "id": submission_id,
            "expected_modified": expected_modified,
        },
    )
    cursor = frappe.db._cursor
    return cursor.rowcount if cursor is not None and cursor.rowcount is not None else 0