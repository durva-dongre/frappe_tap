import frappe

VALID_SCHOOL_TYPES = {"APS", "GOVT", "NGO", "PPP", "PMC", "PVT", "GOVT. Aided", "ORG"}


@frappe.whitelist(allow_guest=True)
def get_states():
    cache_key = "lookup::states"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return frappe.parse_json(cached)
    result = {
        "states": frappe.get_all(
            "State",
            fields=["name as id", "state_name as name"],
            order_by="state_name asc",
        )
    }
    frappe.cache().set_value(cache_key, frappe.as_json(result), expires_in_sec=86400)
    return result


@frappe.whitelist(allow_guest=True)
def get_districts(state=None):
    state = state or frappe.form_dict.get("state")
    if not state:
        frappe.throw("state is required", frappe.ValidationError)
    if not frappe.db.exists("State", state):
        frappe.throw("State not found", frappe.DoesNotExistError)

    cache_key = f"lookup::districts::{state}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return frappe.parse_json(cached)

    result = {
        "state": state,
        "districts": frappe.get_all(
            "District",
            filters={"state": state},
            fields=["name as id", "district_name as name"],
            order_by="district_name asc",
        ),
    }
    frappe.cache().set_value(cache_key, frappe.as_json(result), expires_in_sec=3600)
    return result


@frappe.whitelist(allow_guest=True)
def get_schools(district=None, search=None):
    district = district or frappe.form_dict.get("district")
    search = search or frappe.form_dict.get("search", "")
    if not district:
        frappe.throw("district is required", frappe.ValidationError)
    if not frappe.db.exists("District", district):
        frappe.throw("District not found", frappe.DoesNotExistError)

    if not search:
        cache_key = f"lookup::schools::{district}"
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return frappe.parse_json(cached)

    filters = {"district": district}
    if search:
        filters["name1"] = ["like", f"%{search}%"]

    result = {
        "district": district,
        "schools": frappe.get_all(
            "School",
            filters=filters,
            fields=["name as id", "name1 as name", "type", "city"],
            order_by="name1 asc",
            limit=50,
        ),
    }

    if not search:
        frappe.cache().set_value(cache_key, frappe.as_json(result), expires_in_sec=3600)

    return result


@frappe.whitelist(allow_guest=True)
def create_school(name=None, district=None, type="GOVT"):
    name = name or frappe.form_dict.get("name")
    district = district or frappe.form_dict.get("district")
    type = type or frappe.form_dict.get("type", "GOVT")

    if type not in VALID_SCHOOL_TYPES:
        frappe.throw("Invalid school type", frappe.ValidationError)
    if not frappe.db.exists("District", district):
        frappe.throw("District not found", frappe.DoesNotExistError)

    existing = frappe.db.get_value("School", {"name1": name, "district": district}, "name")
    if existing:
        return {"school_id": existing, "name": name, "created": False}

    doc = frappe.new_doc("School")
    doc.name1 = name
    doc.district = district
    doc.type = type
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    frappe.cache().delete_value(f"lookup::schools::{district}")

    return {"school_id": doc.name, "name": name, "created": True}


@frappe.whitelist(allow_guest=True)
def get_languages():
    cache_key = "lookup::languages"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return frappe.parse_json(cached)
    result = {
        "languages": frappe.get_all(
            "TAP Language",
            fields=["name as id", "language_name as name"],
            order_by="language_name asc",
        )
    }
    frappe.cache().set_value(cache_key, frappe.as_json(result), expires_in_sec=86400)
    return result