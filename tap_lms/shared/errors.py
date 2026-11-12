"""
shared/errors.py

The one error contract every app built on top of `shared` raises through.
Nothing in `shared/` calls `frappe.throw()` directly -- it raises one of these,
and the caller's own API layer (e.g. tap_app's route decorator) maps `.code`
and `.http_status` onto whatever wire shape that app's own clients expect.

Kept free of any app-specific vocabulary so a second app can reuse the same
primitives (enrollment, progress, submission) without inheriting tap_app's
error strings.
"""

from __future__ import annotations


class SharedError(Exception):
    http_status: int = 500
    code: str = "server_error"

    def __init__(self, message: str = "", error_code: str | None = None):
        self.message = message or self.code
        if error_code:
            self.code = error_code
        super().__init__(self.message)


class NotFound(SharedError):
    http_status = 404
    code = "not_found"

    def __init__(self, message: str = "Not found", error_code: str | None = None):
        super().__init__(message, error_code)


class InvalidInput(SharedError):
    http_status = 400
    code = "invalid_input"

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message, error_code)


class StudentNotFound(SharedError):
    http_status = 400
    code = "student_not_found"

    def __init__(self, message: str = "Student not found"):
        super().__init__(message)


class ConflictError(SharedError):
    http_status = 409
    code = "conflict"

    def __init__(self, message: str = "Conflict", error_code: str | None = None):
        super().__init__(message, error_code)


class CapReached(ConflictError):
    def __init__(self, message: str = "Cap already reached"):
        super().__init__(message)


class PermissionError_(SharedError):
    http_status = 403
    code = "forbidden"

    def __init__(self, message: str = "Forbidden"):
        super().__init__(message)


class ValidationFailed(InvalidInput):
    """Used by enrollment.py's state-machine validation (invalid_transition,
    enrollment_not_found) — a thin, named alias of InvalidInput so those call
    sites can raise with an explicit error_code."""

    def __init__(self, message: str, error_code: str = "invalid_input"):
        super().__init__(message, error_code)