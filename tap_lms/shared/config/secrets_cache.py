"""
shared/config/secrets_cache.py

Generic accessors for secrets that live either on the shared settings
singleton (Password/Data fields) or in Frappe's site config (secrets with no
natural doctype field, e.g. a cross-service HMAC secret).
"""
from __future__ import annotations

from typing import Optional

import frappe

from shared.config.settings_cache import DEFAULT_SETTINGS_DOCTYPE, get_shared_settings


def get_worker_internal_secret(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).get_password("worker_internal_api_secret")


def get_worker_internal_api_url(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> str:
    return get_shared_settings(doctype).worker_internal_api_url


def get_r2_credentials(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> dict:
    settings = get_shared_settings(doctype)
    return {
        "account_id": settings.r2_account_id,
        "access_key_id": settings.r2_access_key_id,
        "secret_access_key": settings.get_password("r2_secret_access_key"),
        "bucket": settings.r2_bucket,
    }


def get_gcs_credentials(doctype: str = DEFAULT_SETTINGS_DOCTYPE) -> dict:
    settings = get_shared_settings(doctype)
    return {
        "bucket": settings.gcs_bucket,
        "project_id": settings.gcs_project_id,
        "service_account_json": settings.get_password("gcs_service_account_json"),
    }


def get_magic_link_shared_secret() -> Optional[str]:
    """HMAC secret for magic links, verified by the Worker. Lives in
    site_config.json (not a doctype field):
        bench --site <site> set-config tapapp_magic_link_secret "<secret>"
    """
    return frappe.conf.get("tapapp_magic_link_secret")