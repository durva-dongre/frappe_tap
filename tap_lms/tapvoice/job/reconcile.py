import frappe

from tap_lms.tapvoice.constants import RUN_DOCTYPE, SETTINGS_DOCTYPE


def monthly_reconcile(actual_spend_usd):
    start = frappe.utils.get_first_day(frappe.utils.now_datetime())
    rows = frappe.get_all(
        RUN_DOCTYPE,
        filters={"creation": [">=", start]},
        fields=["estimated_cost_usd_final", "estimated_cost_usd"],
    )
    estimated = sum((r.estimated_cost_usd_final or r.estimated_cost_usd or 0.0) for r in rows)
    delta = actual_spend_usd - estimated
    note = (
        f"\n[{frappe.utils.now()}] reconcile: estimated=${estimated:.2f} "
        f"actual=${actual_spend_usd:.2f} delta=${delta:.2f}"
    )
    doc = frappe.get_single(SETTINGS_DOCTYPE)
    doc.db_set("operator_notes", (doc.operator_notes or "") + note, update_modified=False)
    frappe.db.commit()
    return {"estimated": estimated, "actual": actual_spend_usd, "delta": delta}