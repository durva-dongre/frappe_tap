"""
shared/db_retry.py

Generic retry wrapper for transient Postgres errors (deadlock / serialization
failure) on raw SQL, plus thin helpers used throughout shared/.
"""

from __future__ import annotations

import time
import functools
from typing import Callable, TypeVar

import frappe

T = TypeVar("T")

_RETRYABLE_SQLSTATES = {"40001", "40P01"}  # serialization_failure, deadlock_detected


def _is_retryable(exc: Exception) -> bool:
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(exc, "pgcode", None)
    if sqlstate and str(sqlstate) in _RETRYABLE_SQLSTATES:
        return True
    text = str(exc).lower()
    return "deadlock" in text or "could not serialize access" in text


def with_retry(fn: Callable[[], T], attempts: int = 3, backoff_ms: int = 50) -> T:
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
    read-modify-write (enrollment.py, unit_rotation.py)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return with_retry(lambda: fn(*args, **kwargs))
    return wrapper


def run_sql_all(query: str, params: dict | tuple | None = None) -> list[dict]:
    return with_retry(lambda: frappe.db.sql(query, params or {}, as_dict=True))


def run_sql_one(query: str, params: dict | tuple | None = None) -> dict | None:
    rows = run_sql_all(query, params)
    return rows[0] if rows else None