import frappe

from tap_lms.tapvoice.constants import MAX_URL_LENGTH, SETTINGS_DOCTYPE

SNAPSHOT_FIELDS = (
    "enabled",
    "allow_force_start",
    "skip_flagged",
    "window_hours",
    "window_basis",
    "max_clips_per_run",
    "min_items_to_deploy",
    "run_interval_hours",
    "urgent_margin_hours",
    "max_chars_per_text",
    "over_length_policy",
    "max_runs_per_day",
    "min_minutes_between_runs",
    "skip_recent_failures_runs",
    "fallback_hourly_rate_usd",
    "est_startup_seconds",
    "est_seconds_per_clip",
    "estimate_safety_factor",
    "max_cost_per_run_usd",
    "max_cost_per_day_usd",
    "max_cost_per_month_usd",
    "pod_limit_max_seconds",
    "startup_deadline_minutes",
    "heartbeat_timeout_minutes",
    "stopping_grace_minutes",
    "token_buffer_minutes",
    "termination_check_delay_seconds",
    "capacity_retry_interval_minutes",
    "capacity_retry_max_minutes",
    "max_consecutive_bad_runs",
    "bad_run_success_floor_percent",
    "alert_email",
    "runpod_api_base",
    "image_name",
    "registry_auth_id",
    "gpu_type_ids",
    "gpu_count",
    "cloud_type",
    "interruptible",
    "container_disk_gb",
    "volume_gb",
    "data_center_ids",
    "allowed_cuda_versions",
    "http_timeout_seconds",
    "public_base_url",
    "api_module_path",
    "gcs_bucket",
    "gcs_prefix",
    "cdn_base_url",
    "model_revision",
    "verify_urls_on_write",
    "max_num_seqs",
    "decode_microbatch",
    "gpu_memory_utilization",
    "seconds_per_item_cap",
)

_LIST_FIELDS = ("gpu_type_ids", "data_center_ids", "allowed_cuda_versions")


def _split_lines(value):
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class Settings:
    def __init__(self, doc):
        for field in SNAPSHOT_FIELDS:
            setattr(self, field, doc.get(field))
        self.public_base_url = (self.public_base_url or "").rstrip("/")
        self.cdn_base_url = (self.cdn_base_url or "").rstrip("/")
        self.gcs_prefix = (self.gcs_prefix or "tts").strip("/")
        for field in _LIST_FIELDS:
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, _split_lines(value))
            elif value is None:
                setattr(self, field, [])

    def kill_switch_on(self):
        return bool(self.enabled)

    def max_text_chars(self):
        return int(self.max_chars_per_text or 0)

    def max_url_length(self):
        return MAX_URL_LENGTH

    def snapshot(self):
        out = {}
        for field in SNAPSHOT_FIELDS:
            value = getattr(self, field)
            if isinstance(value, (list, tuple)):
                out[field] = "\n".join(str(item) for item in value)
            else:
                out[field] = value
        return out


def load():
    doc = frappe.get_single(SETTINGS_DOCTYPE)
    return Settings(doc)


def load_fresh():
    frappe.clear_cache(doctype=SETTINGS_DOCTYPE)
    doc = frappe.get_single(SETTINGS_DOCTYPE)
    return Settings(doc)


def api_path_prefix(settings):
    module_path = (settings.api_module_path or "tap_lms.tapvoice.api.pod").strip(".")
    return f"/api/method/{module_path}."