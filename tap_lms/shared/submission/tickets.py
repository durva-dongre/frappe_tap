from __future__ import annotations

import uuid

import frappe

from shared.config.secrets_cache import get_upload_put_url_ttl_seconds
from shared.errors import NotFound

TICKET_KEY_PREFIX = "tap_upload_ticket:"

# assignment_id_link is the only scoping key carried through from
# request_upload to confirm_upload to finalize_submission. event_id is
# validated transiently in lifecycle.py before a ticket is ever created
# (see _validate_context) and is never part of what gets persisted here.
#
# TTL: get_upload_put_url_ttl_seconds() reads Shared Settings.
# upload_put_url_ttl_seconds (Int, default 600 = 10 minutes), the same
# "configurable field with a safe, schema-matching default" pattern used
# throughout shared/config/secrets_cache.py -- an operator can lengthen
# or shorten the client's upload window without a deploy.


def create_ticket(student_id: str, enrollment_name: str, assignment_id_link: str, submission_context: str,
                   submission_type: str, object_key: str, max_size_bytes: int, content_type: str,
                   attempt_number: int, source: str, submission_name: str | None = None) -> tuple[str, dict]:
    ticket_id = str(uuid.uuid4())
    payload = {
        "student_id": student_id, "enrollment_name": enrollment_name,
        "assignment_id_link": assignment_id_link, "submission_context": submission_context,
        "submission_type": submission_type, "object_key": object_key, "max_size_bytes": max_size_bytes,
        "content_type": content_type, "attempt_number": attempt_number,
        "submission_name": submission_name, "source": source,
    }
    ttl = get_upload_put_url_ttl_seconds()
    frappe.cache().set_value(f"{TICKET_KEY_PREFIX}{ticket_id}", payload, expires_in_sec=ttl)
    return ticket_id, payload


def get_ticket(ticket_id: str) -> dict:
    payload = frappe.cache().get_value(f"{TICKET_KEY_PREFIX}{ticket_id}")
    if payload is None:
        raise NotFound("upload ticket not found or expired", error_code="ticket_not_found")
    return payload


def delete_ticket(ticket_id: str) -> None:
    frappe.cache().delete_value(f"{TICKET_KEY_PREFIX}{ticket_id}")