import frappe
from frappe.model.document import Document

MAX_URL_LENGTH = 140
MAX_TEXT_CHARS_HARD_LIMIT = 300
POD_MAX_ITEMS = 5000
MUTABLE_TAGS = ("", "stable", "latest")


class TapVoiceSettings(Document):
    def validate(self):
        self._validate_text_limit()
        self._validate_batch_caps()
        self._validate_cost_caps()
        self._validate_https()
        self._validate_gpu_list()
        self._validate_window()
        self._validate_image_name()
        self._validate_alert_email_required()
        self._validate_url_length()
        self._validate_capacity_retry()
        self._warn_model_revision_change()

    def _validate_text_limit(self):
        if (self.max_chars_per_text or 0) > MAX_TEXT_CHARS_HARD_LIMIT:
            frappe.throw(f"Max Chars Per Text cannot exceed {MAX_TEXT_CHARS_HARD_LIMIT}")

    def _validate_batch_caps(self):
        if (self.min_items_to_deploy or 0) > (self.max_clips_per_run or 0):
            frappe.throw("Min Items To Deploy must be less than or equal to Max Clips Per Run")
        if (self.max_clips_per_run or 0) > POD_MAX_ITEMS:
            frappe.throw(f"Max Clips Per Run cannot exceed {POD_MAX_ITEMS}")
        if (self.window_hours or 0) > 72:
            frappe.throw("Window Hours cannot exceed 72")

    def _validate_cost_caps(self):
        if (self.max_cost_per_run_usd or 0) > (self.max_cost_per_day_usd or 0):
            frappe.throw("Max Cost Per Run must be less than or equal to Max Cost Per Day")
        if (self.max_cost_per_day_usd or 0) > (self.max_cost_per_month_usd or 0):
            frappe.throw("Max Cost Per Day must be less than or equal to Max Cost Per Month")

    def _validate_https(self):
        if self.public_base_url and not self.public_base_url.startswith("https://"):
            frappe.throw("Public Base URL must use HTTPS")

    def _validate_gpu_list(self):
        if not (self.gpu_type_ids or "").strip():
            frappe.throw("GPU Type Ids cannot be empty")

    def _validate_window(self):
        if (self.window_hours or 0) <= 0:
            frappe.throw("Window Hours must be positive")

    def _validate_image_name(self):
        name = (self.image_name or "").strip().lower()
        if not name or "@sha256:" in name:
            return
        last_part = name.rsplit("/", 1)[-1]
        tag = last_part.split(":", 1)[1] if ":" in last_part else ""
        if tag in MUTABLE_TAGS:
            frappe.throw(
                "Image Name needs an immutable tag (such as a short SHA) or a digest, "
                "not 'stable', 'latest' or no tag"
            )

    def _validate_alert_email_required(self):
        if self.enabled and not (self.alert_email or "").strip():
            frappe.throw("Alert Email is required before Enabled can be turned on")

    def _validate_url_length(self):
        cdn = self.cdn_base_url or ""
        prefix = self.gcs_prefix or ""
        longest_language = "marathi"
        max_len = len(cdn) + 1 + len(prefix) + 1 + len(longest_language) + 1 + 32 + 4
        if max_len > MAX_URL_LENGTH:
            frappe.throw(
                f"Longest possible clip URL is {max_len} chars, exceeds the {MAX_URL_LENGTH} char field limit"
            )

    def _validate_capacity_retry(self):
        if (self.capacity_retry_interval_minutes or 0) < 1:
            frappe.throw("Capacity Retry Interval Minutes must be at least 1")
        if (self.capacity_retry_max_minutes or 0) < (self.capacity_retry_interval_minutes or 0):
            frappe.throw("Capacity Retry Max Minutes must be at least the retry interval")

    def _warn_model_revision_change(self):
        if self.is_new():
            return
        previous = frappe.db.get_single_value("Tap Voice Settings", "model_revision")
        if previous and self.model_revision and previous != self.model_revision:
            frappe.msgprint(
                "Model Revision changed: all future audio will regenerate and existing URLs will no longer match.",
                indicator="orange",
            )