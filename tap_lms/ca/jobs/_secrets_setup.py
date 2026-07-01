import frappe


def create_ca_secrets(
    *,
    r2_account_id: str,
    r2_access_key: str,
    r2_secret_key: str,
    r2_bucket: str,
    appsheet_webapp_url: str,
    appsheet_webapp_secret: str,
):
    for name, value in (
        ("r2_account_id", r2_account_id),
        ("r2_access_key", r2_access_key),
        ("r2_secret_key", r2_secret_key),
        ("r2_bucket", r2_bucket),
        ("appsheet_webapp_url", appsheet_webapp_url),
        ("appsheet_webapp_secret", appsheet_webapp_secret),
    ):
        if frappe.db.exists("Secrets", name):
            continue
        doc = frappe.get_doc({
            "doctype": "Secrets",
            "name": name,
            "value": value,
        })
        doc.insert(ignore_permissions=True)
    frappe.db.commit()