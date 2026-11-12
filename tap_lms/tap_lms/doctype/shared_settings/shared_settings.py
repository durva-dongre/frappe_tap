import frappe
from frappe.model.document import Document


class SharedSettings(Document):
    def on_update(self):
        from shared.config.settings_cache import invalidate_config_cache
        invalidate_config_cache()