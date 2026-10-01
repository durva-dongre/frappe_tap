import frappe
from frappe.utils.password import decrypt

from tap_lms.tapvoice.constants import REQUIRED_SECRET_KEYS, SECRET_RUNPOD_API_KEY, SECRET_RUNPOD_POD_API_KEY

SECRETS_DOCTYPE = "Secrets"
ENC_PREFIX = "enc:"


class SecretMissing(Exception):
    def __init__(self, key):
        super().__init__(f"secret_missing:{key}")
        self.key = key


def get(key):
    if not frappe.db.exists(SECRETS_DOCTYPE, key):
        raise SecretMissing(key)
    row = frappe.db.get_value(SECRETS_DOCTYPE, key, ["value", "enabled"], as_dict=True)
    if not row or not row.enabled:
        raise SecretMissing(key)
    raw = (row.value or "").strip()
    if raw.startswith(ENC_PREFIX):
        try:
            value = decrypt(raw[len(ENC_PREFIX):])
        except Exception:
            raise SecretMissing(key)
    else:
        value = raw
    value = (value or "").strip()
    if not value:
        raise SecretMissing(key)
    return value


def is_present(key):
    try:
        get(key)
        return True
    except SecretMissing:
        return False


def check_all_present():
    return [key for key in REQUIRED_SECRET_KEYS if not is_present(key)]


def runpod_api_key():
    return get(SECRET_RUNPOD_API_KEY)


def runpod_pod_api_key():
    try:
        return get(SECRET_RUNPOD_POD_API_KEY)
    except SecretMissing:
        return runpod_api_key()