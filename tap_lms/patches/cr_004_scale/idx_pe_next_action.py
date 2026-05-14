"""
CR-004 scale: partial index on ProgramEnrollment.next_action_at.

Drives `process_program_actions` to <50ms at 100K-row PE table sizes by
indexing only the rows actually due ("WHERE next_action_at IS NOT NULL").
Without this, the dispatcher's SELECT does a full table scan every minute
at 100K scale.

Idempotency: `CREATE INDEX IF NOT EXISTS` is a no-op when the index exists.

Postgres-only (L-002). The Frappe field-level `index: 1` JSON setting
can't express the WHERE clause; needs a manual patch.
"""
import frappe


def execute():
    frappe.db.sql("""
        CREATE INDEX IF NOT EXISTS idx_pe_next_action
        ON "tabProgramEnrollment" (next_action_at, program_status)
        WHERE next_action_at IS NOT NULL;
    """)
    frappe.db.commit()
