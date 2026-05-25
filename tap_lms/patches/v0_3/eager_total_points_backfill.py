"""
CR-011 (2026-05-25) — one-time backfill bringing existing PEs from the
lazy-rollup design to the eager-totals design.

Background
==========

Pre-CR-011, per-event handlers (`quiz_points.py`, `activity_points.py`,
`feedback_consumer_hook.py`) only bumped `weekly_*` columns. Cumulative
totals (`total_activity_points`, `total_quiz_points`,
`total_submission_points`, `total_points`) were rolled up lazily at T14
(week advance). Mid-week state was incoherent: a student who earned 3 quiz
points saw `weekly_quiz_points=3` but `total_quiz_points=0` and
`total_points=0`, and Glific contact fields reflected the same incoherent
view.

Post-CR-011, totals are updated **eagerly** in the same atomic SQL that
bumps weekly_*. T14 only resets weekly_* — totals stay coherent at all
times.

What this patch does
====================

For every active or paused PE, adds the current `weekly_*` values into the
corresponding `total_*` columns, and adds (`weekly_activity_points`
+ `weekly_quiz_points` + `weekly_submission_points` + `bonus_quiz_points`)
into `total_points`. This brings the totals in line with the points that
the student has already earned mid-week but which the lazy rollup hadn't
yet folded into the totals.

After this patch runs, future per-event handler invocations keep totals
coherent via the new eager SQL in CR-011. T14 will not re-add weekly_* to
total_* (the rollup helper now returns totals as pass-through — see
`weekly_rollup.calculate_week_advance_rollup`).

Idempotency (L-021)
===================

Run-once semantics come from `patches.txt` — Frappe records this patch's
module path in `tabPatch Log` after a successful execute. Re-runs are
blocked unless the row is manually deleted or `bench migrate --force` is
used. As an extra defense, we use COALESCE in the UPDATE so the math is
safe against NULL columns; we do not, however, gate on a sentinel field
because the math is **not safe to re-run** — re-running would double-add
the weekly_* into the totals. If a re-run is needed (e.g. after a partial
failure mid-UPDATE), the operator must first reverse the partial effect
manually or trust the `tabPatch Log` to keep this patch from re-firing.

Postgres-only (L-002). Per CLAUDE.md txn hygiene, calls
`frappe.db.rollback()` up-front to release any poisoned txn state from
earlier patches in the chain.
"""
import frappe


def execute():
    # PG txn hygiene — clear any poisoned txn state from earlier patches.
    frappe.db.rollback()

    # L-036: reload the doctype so the columns we reference are guaranteed
    # live in the schema. Idempotent + cheap.
    frappe.reload_doc("tap_lms", "doctype", "programenrollment")

    # Backfill: roll the current weekly_* buckets into total_* for every PE
    # that is still in play (active or paused). Dropped/completed PEs are
    # frozen and don't need their totals updated.
    #
    # NOTE on idempotency: this UPDATE is **not** safe to re-run as-is
    # (would double-count). Frappe's patch-log mechanism is the run-once
    # guard. We rely on that rather than adding a sentinel column. See the
    # module docstring for the rationale.
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET total_activity_points    = COALESCE(total_activity_points,    0)
                                         + COALESCE(weekly_activity_points,   0),
               total_quiz_points        = COALESCE(total_quiz_points,        0)
                                         + COALESCE(weekly_quiz_points,       0),
               total_submission_points  = COALESCE(total_submission_points,  0)
                                         + COALESCE(weekly_submission_points, 0),
               total_points             = COALESCE(total_points,             0)
                                         + COALESCE(weekly_activity_points,   0)
                                         + COALESCE(weekly_quiz_points,       0)
                                         + COALESCE(weekly_submission_points, 0)
                                         + COALESCE(bonus_quiz_points,        0)
         WHERE program_status IN ('active', 'paused')
        """
    )

    # Count what we touched for the audit log.
    row_count = frappe.db.sql(
        """
        SELECT COUNT(*) FROM "tabProgramEnrollment"
         WHERE program_status IN ('active', 'paused')
        """
    )[0][0]

    frappe.db.commit()

    # L-035: structured success log so ops can confirm the patch ran and
    # see how many rows were touched.
    frappe.logger().info(
        f"CR-011 eager-total-points backfill complete: "
        f"updated {row_count} PEs (program_status IN ('active','paused')). "
        f"Future per-event handlers will keep totals coherent eagerly; "
        f"T14 no longer rolls weekly_*→total_*."
    )
    print(
        f"CR-011 eager-total-points backfill complete: {row_count} PEs updated."
    )
