from __future__ import annotations

from tap_lms.tap_app.api import tap_app_method
from shared.events.enrollment import enroll_student_in_event, is_enrolled as _is_enrolled


@tap_app_method
def enroll_event(student_id: str, event_id: str):
    """Worker route: POST /events/enroll -> FRAPPE_METHODS.enrollEvent
    ("tap_lms.tap_app.api.events.enroll_event"). The Worker wraps this call
    in its own idempotency cache (withIdempotency), so no idempotency_key
    needs to reach Frappe at all -- enroll_student_in_event is itself
    naturally idempotent for a repeat call against an already-active
    enrollment (it does not double-increment Event Campaign.enrolled_count)."""
    return enroll_student_in_event(student_id, event_id)


@tap_app_method
def is_enrolled(student_id: str, event_id: str):
    """Worker route: POST /events/is_enrolled -> FRAPPE_METHODS.isEnrolled
    ("tap_lms.tap_app.api.events.is_enrolled"). This is the sole source of
    event-track resume state in the whole API (API_Reference.md §8.2) -- no
    resume payload from /auth/redeem or /auth/select_profile ever carries
    current_event_learning_unit; that field is scoped exclusively to this
    endpoint, per event_id."""
    return _is_enrolled(student_id, event_id)