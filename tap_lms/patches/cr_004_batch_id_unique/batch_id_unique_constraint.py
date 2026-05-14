"""
Ensure UNIQUE constraint exists on tabBatch.batch_id.

DocType JSON declared batch_id as unique=1, but in the live database
duplicates leaked in (one batch had SP_BATCH_01 set manually after another
batch already used it). This patch:

  1. Probes for duplicate batch_id values via SQL.
  2. If any exist: logs them to an Error Log entry titled
     'Batch.batch_id duplicate detected - manual cleanup required' with
     the offending doc names, then calls frappe.throw() to halt migration.
     Operator picks unique values, updates the rows, re-runs migrate.
  3. If no duplicates: creates the unique index if missing.

Run with: `bench --site <site> migrate`

Idempotent (L-021): `CREATE UNIQUE INDEX IF NOT EXISTS` is a no-op when
the index exists. Postgres-only (L-002).
"""
import frappe


def execute():
	# Step 1 - probe for duplicates.
	# Per CLAUDE.md: a failed query poisons the PG transaction. Roll back any
	# in-flight state before our probe so a prior failure doesn't mask our
	# SELECT result.
	frappe.db.rollback()

	duplicates = frappe.db.sql("""
		SELECT batch_id, COUNT(*) AS n, ARRAY_AGG(name ORDER BY name) AS doc_names
		  FROM "tabBatch"
		 WHERE batch_id IS NOT NULL AND batch_id != ''
		 GROUP BY batch_id
		HAVING COUNT(*) > 1
	""", as_dict=True)

	if duplicates:
		# Log the offending rows so the operator can fix them.
		msg_lines = ["Cannot add UNIQUE constraint on tabBatch.batch_id - duplicates exist:"]
		for row in duplicates:
			msg_lines.append(
				f"  batch_id={row['batch_id']!r} -> {row['n']} batches: {row['doc_names']}"
			)
		msg_lines.append("")
		msg_lines.append(
			"Resolution: update the offending Batch records to have unique batch_id values, "
			"then re-run `bench migrate`."
		)
		msg = "\n".join(msg_lines)
		frappe.log_error(
			message=msg,
			title="Batch.batch_id duplicate detected - manual cleanup required",
		)
		frappe.throw(msg)

	# Step 2 - ensure the unique index exists.
	# CREATE UNIQUE INDEX IF NOT EXISTS is idempotent; safe to re-run.
	# Frappe's auto-migrate may already have created it; this is the
	# defense-in-depth path for when that step was skipped.
	frappe.db.sql_ddl("""
		CREATE UNIQUE INDEX IF NOT EXISTS unique_tabBatch_batch_id
		  ON "tabBatch" (batch_id)
	""")

	frappe.db.commit()
	print("tabBatch.batch_id unique constraint ensured")
