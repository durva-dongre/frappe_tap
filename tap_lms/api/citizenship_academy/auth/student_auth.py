import frappe
import jwt
import datetime
from frappe.utils.password import check_password, update_password

JWT_EXPIRY_HOURS = 72
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


def _normalize_phone(phone):
	if not phone:
		return ""
	digits = "".join(c for c in str(phone) if c.isdigit())
	if len(digits) == 12 and digits.startswith("91"):
		digits = digits[2:]
	return digits


def _get_secret(key):
	cache = frappe.cache()
	cached = cache.get_value(f"secret::{key}")
	if cached:
		return cached
	secret_doc = frappe.get_doc("Secrets", key)
	value = secret_doc.get_password("value")
	cache.set_value(f"secret::{key}", value)
	return value


def _get_jwt_secret():
	return _get_secret("jwt_secret")


def _generate_access_token(phone, student_ids):
	payload = {
		"phone": phone,
		"students": student_ids,
		"type": "access",
		"exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
		"iat": datetime.datetime.utcnow(),
	}
	return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def _decode_access_token(token):
	try:
		payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
		if payload.get("type") != "access":
			return None
		return payload
	except Exception:
		return None


def _extract_bearer_token():
	for header in ("X-Flutter-Authorization", "Authorization"):
		value = frappe.get_request_header(header, "")
		if value.startswith("Bearer "):
			return value[7:]
	return None


def _get_avatar_path(avatar_key):
	if not avatar_key:
		return "assets/avatars/avatar_01.png"
	path = frappe.db.get_value("Student Avatar", avatar_key, "avatar_path")
	return path or "assets/avatars/avatar_01.png"


def _get_profiles_for_phone(phone):
	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	if not auth_name:
		return []
	doc = frappe.get_doc("Student Auth", auth_name)
	profiles = []
	for row in doc.students:
		student_data = frappe.db.get_value(
			"Student",
			row.student,
			["name1", "gender", "grade", "school_id", "language", "status"],
			as_dict=True,
		)
		profiles.append({
			"student_id": row.student,
			"name": student_data.name1 if student_data else row.student,
			"avatar": _get_avatar_path(row.avatar),
			"gender": student_data.gender if student_data else None,
			"grade": student_data.grade if student_data else None,
			"status": student_data.status if student_data else None,
		})
	return profiles


def _is_account_locked(doc):
	if not doc.is_locked:
		return False
	if doc.locked_until and frappe.utils.now_datetime() > doc.locked_until:
		doc.is_locked = 0
		doc.failed_attempts = 0
		doc.locked_until = None
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return False
	return True


def _increment_failed_attempts(doc):
	doc.failed_attempts = (doc.failed_attempts or 0) + 1
	if doc.failed_attempts >= MAX_ATTEMPTS:
		doc.is_locked = 1
		doc.locked_until = frappe.utils.add_to_date(
			frappe.utils.now_datetime(), minutes=LOCKOUT_MINUTES
		)
	doc.flags.ignore_mandatory = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def _reset_failed_attempts(doc):
	doc.failed_attempts = 0
	doc.is_locked = 0
	doc.locked_until = None
	doc.flags.ignore_mandatory = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def _password_exists(auth_name):
	"""Check whether a password row exists for this Student Auth record."""
	result = frappe.db.sql(
		"SELECT 1 FROM `__Auth` WHERE doctype='Student Auth' AND name=%s AND fieldname='password'",
		auth_name,
	)
	return bool(result)


@frappe.whitelist(allow_guest=True)
def check_phone(phone=None):
	phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
	if not phone:
		frappe.throw("phone is required", frappe.ValidationError)
	return {"exists": bool(frappe.db.exists("Student Auth", {"phone": phone}))}


@frappe.whitelist(allow_guest=True)
def login_with_password(phone=None, password=None):
	phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))
	password = password or frappe.form_dict.get("password")

	if not phone or not password:
		return {"success": False, "error": "invalid_credentials"}

	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	if not auth_name:
		return {"success": False, "error": "invalid_credentials"}

	# Safety: if somehow the password row is missing, treat as invalid
	if not _password_exists(auth_name):
		frappe.log_error(
			title="Login: missing password row",
			message=f"Student Auth {auth_name} has no password row in __Auth",
		)
		return {"success": False, "error": "invalid_credentials"}

	doc = frappe.get_doc("Student Auth", auth_name)

	if _is_account_locked(doc):
		return {
			"success": False,
			"error": "account_locked",
			"locked_until": str(doc.locked_until),
		}

	try:
		check_password(auth_name, password, doctype="Student Auth", fieldname="password")
	except frappe.AuthenticationError:
		_increment_failed_attempts(doc)
		remaining = max(0, MAX_ATTEMPTS - doc.failed_attempts)
		return {
			"success": False,
			"error": "invalid_credentials",
			"attempts_remaining": remaining,
		}

	_reset_failed_attempts(doc)
	all_students = [row.student for row in doc.students]
	token = _generate_access_token(phone, all_students)
	profiles = _get_profiles_for_phone(phone)

	return {"success": True, "token": token, "phone": phone, "profiles": profiles}


@frappe.whitelist(allow_guest=True)
def get_profiles(phone=None):
	phone = _normalize_phone(phone or frappe.form_dict.get("phone", ""))

	token = _extract_bearer_token()
	if not token:
		frappe.throw("Missing token", frappe.AuthenticationError)

	payload = _decode_access_token(token)
	if not payload:
		frappe.throw("Invalid or expired token", frappe.AuthenticationError)

	if payload.get("phone") != phone:
		frappe.throw("Token phone mismatch", frappe.AuthenticationError)

	if not frappe.db.exists("Student Auth", {"phone": phone}):
		frappe.throw("Phone not registered", frappe.DoesNotExistError)

	return {"phone": phone, "profiles": _get_profiles_for_phone(phone)}
