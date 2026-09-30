import frappe

from tap_lms.tapvoice.constants import REQUIRED_SECRET_KEYS, SECRET_RUNPOD_API_KEY, SECRET_RUNPOD_POD_API_KEY

SECRETS_DOCTYPE = "Secrets"


class SecretMissing(Exception):
    def __init__(self, key):
        super().__init__(f"secret_missing:{key}")
        self.key = key


def get(key):
    if not frappe.db.exists(SECRETS_DOCTYPE, key):
        raise SecretMissing(key)
    doc = frappe.get_doc(SECRETS_DOCTYPE, key)
    if not doc.enabled:
        raise SecretMissing(key)
    value = doc.get_password("value")
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