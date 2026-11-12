"""
shared/submission/locks.py

Row-lock helper used around any read-modify-write that must not race with a
concurrent writer for the same parent row (e.g. two submit_artwork calls for
the same student+unit landing at once). Takes the lock on the PARENT row
("tabProgram Enrollment") so every child-table write for that student inside
the same request is serialized behind one lock. Caller is already inside the
whitelisted method's implicit request transaction -- this just adds a
FOR UPDATE row lock mid-transaction, not a new one.
"""

from __future__ import annotations

import frappe


def lock_program_enrollment_row(name: str) -> None:
    frappe.db.sql(
        """SELECT name FROM "tabProgramEnrollment" WHERE name = %s FOR UPDATE""",
        (name,),
    )