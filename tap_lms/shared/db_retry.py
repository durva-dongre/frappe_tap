"""
shared/db_retry.py

Generic retry wrapper for transient Postgres errors (deadlock / serialization
failure) on raw SQL, plus thin helpers used throughout shared/.

Retry tuning (attempts, backoff_ms) is configurable via Shared Settings
(db_retry_attempts, db_retry_backoff_ms -- see
shared/config/secrets_cache.py::get_db_retry_settings) rather than
hardcoded constants here. `with_retry`'s own `attempts`/`backoff_ms`
parameters default to `None`, meaning "use whatever Shared Settings is
currently configured with" -- resolved fresh on every call (so a change
to either Shared Settings field takes effect immediately, no process
restart, consistent with every other Shared Settings-backed value in this
codebase), not baked in at import time. A caller can still pass an
explicit `attempts=`/`backoff_ms=` to override the configured value for
that one call site; none currently do, but the parameters remain fully
functional for any future caller that needs a different policy than the
global default.
"""

from __future__ import annotations

import time
import functools
from typing import Callable, Optional, TypeVar

import frappe

from shared.config.secrets_cache import get_db_retry_settings

T = TypeVar("T")

_RETRYABLE_SQLSTATES = {"40001", "40P01"}  # serialization_failure, deadlock_detected


def _is_retryable(exc: Exception) -> bool:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(exc, "pgcode", None)
    if sqlstate and str(sqlstate) in _RETRYABLE_SQLSTATES:
        return True
    text = str(exc).lower()
    return "deadlock" in text or "could not serialize access" in text


def with_retry(fn: Callable[[], T], attempts: Optional[int] = None, backoff_ms: Optional[int] = None) -> T:
    """Runs fn(), retrying on a retryable Postgres error up to `attempts`
    times total, sleeping `backoff_ms` milliseconds between attempts.

    attempts/backoff_ms default to None, meaning "read the current value
    from Shared Settings (db_retry_attempts / db_retry_backoff_ms) on this
    call" -- see module docstring. Pass explicit values to override the
    configured default for a specific call site."""
    if attempts is None or backoff_ms is None:
        configured = get_db_retry_settings()
        if attempts is None:
            attempts = configured["attempts"]
        if backoff_ms is None:
            backoff_ms = configured["backoff_ms"]

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised below
            last_exc = exc
            if not _is_retryable(exc) or attempt == attempts:
                raise
            frappe.logger().warning(
                f"with_retry: attempt {attempt}/{attempts} hit a retryable error "
                f"({exc}); backing off {backoff_ms}ms"
            )
            time.sleep(backoff_ms / 1000.0)
    raise last_exc  # type: ignore[misc]


def with_serialization_retry(fn: Callable[..., T]) -> Callable[..., T]:
    """Decorator form of with_retry, for functions that do a locked
    read-modify-write (enrollment.py, unit_rotation.py). Uses the
    currently configured Shared Settings retry policy on every call (see
    with_retry's own docstring) -- not a fixed policy baked in at decorator
    application time."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return with_retry(lambda: fn(*args, **kwargs))
    return wrapper


def run_sql_all(query: str, params: dict | tuple | None = None) -> list[dict]:
    return with_retry(lambda: frappe.db.sql(query, params or {}, as_dict=True))


def run_sql_one(query: str, params: dict | tuple | None = None) -> dict | None:
    rows = run_sql_all(query, params)
    return rows[0] if rows else None