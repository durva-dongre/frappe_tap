"""
shared/jobs/_log.py

One row per scheduled-job run, written to the existing Shared Logs doctype
(no doctype changes -- this just uses the fields that are already there:
source, log_type, status, started_at, finished_at, rows_processed, log_date,
details). Every job in shared/jobs/ calls this exactly once per run, success
or failure, so job history is auditable from one list view.
"""

from __future__ import annotations

import json

import frappe


def log_job_run(source: str, log_type: str, status: str, started_at, finished_at,
                 rows_processed: int, details: dict | None = None) -> None:
    frappe.get_doc({
        "doctype": "Shared Logs",
        "source": source,
        "log_type": log_type,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "rows_processed": rows_processed,
        "log_date": frappe.utils.today(),
        "details": json.dumps(details or {}),
    }).insert(ignore_permissions=True)
    frappe.db.commit()