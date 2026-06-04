import frappe
import jwt
import datetime
from frappe.utils.password import check_password, update_password

JWT_EXPIRY_HOURS = 72
OTP_EXPIRY_MINUTES = 10
HARDCODED_OTP = "000000"


def _get_jwt_secret():
	cache = frappe.cache()
	cached = cache.get_value("secret::jwt_secret")
	if cached:
		return cached
	value = frappe.get_doc("Secrets", "jwt_secret").get_password("value")
	cache.set_value("secret::jwt_secret", value, expires_in_sec=3600)
	return value


def _generate_access_token(phone, student_ids):
	now = datetime.datetime.utcnow()
	return jwt.encode(
		{
			"phone": phone,
			"students": student_ids,
			"type": "access",
			"exp": now + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
			"iat": now,
		},
		_get_jwt_secret(),
		algorithm="HS256",
	)


def _generate_reset_token(phone):
	now = datetime.datetime.utcnow()
	return jwt.encode(
		{
			"phone": phone,
			"type": "reset",
			"exp": now + datetime.timedelta(minutes=OTP_EXPIRY_MINUTES),
			"iat": now,
		},
		_get_jwt_secret(),
		algorithm="HS256",
	)


def _decode_access_token(token):
	try:
		payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
		return payload if payload.get("type") == "access" else None
	except Exception:
		return None


def _decode_reset_token(token):
	try:
		payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
		return payload if payload.get("type") == "reset" else None
	except Exception:
		return None


def _bearer_token():
	for header in ("X-Flutter-Authorization", "Authorization"):
		value = frappe.get_request_header(header, "")
		if value.startswith("Bearer "):
			return value[7:]
	return None


def _avatar_path(avatar_key):
	if not avatar_key:
		return "assets/avatars/avatar_01.png"
	return frappe.db.get_value("Student Avatar", avatar_key, "avatar_path") or "assets/avatars/avatar_01.png"


def _profiles_for_phone(phone):
	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	if not auth_name:
		return []

	doc = frappe.get_doc("Student Auth", auth_name)
	if not doc.students:
		return []

	student_ids = [row.student for row in doc.students]
	avatar_map = {row.student: row.avatar for row in doc.students}

	students = frappe.get_all(
		"Student",
		filters={"name": ["in", student_ids]},
		fields=["name", "name1", "gender", "grade", "status"],
	)
	student_map = {s.name: s for s in students}

	return [
		{
			"student_id": sid,
			"name": student_map[sid].name1 if sid in student_map else sid,
			"avatar": _avatar_path(avatar_map.get(sid)),
			"gender": student_map[sid].gender if sid in student_map else None,
			"grade": student_map[sid].grade if sid in student_map else None,
			"status": student_map[sid].status if sid in student_map else None,
		}
		for sid in student_ids
	]


def _password_exists(auth_name):
	return bool(frappe.db.sql(
		'SELECT 1 FROM "__Auth" WHERE doctype=\'Student Auth\' AND name=%s AND fieldname=\'password\'',
		auth_name,
	))


@frappe.whitelist(allow_guest=True)
def check_phone(phone=None):
	phone = phone or frappe.form_dict.get("phone", "")
	if not phone:
		frappe.throw("phone is required", frappe.ValidationError)
	return {"exists": bool(frappe.db.exists("Student Auth", {"phone": phone}))}


@frappe.whitelist(allow_guest=True)
def login_with_password(phone=None, password=None):
	phone    = phone    or frappe.form_dict.get("phone", "")
	password = password or frappe.form_dict.get("password")

	if not phone or not password:
		return {"success": False, "error": "invalid_credentials"}

	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	if not auth_name or not _password_exists(auth_name):
		return {"success": False, "error": "invalid_credentials"}

	try:
		check_password(auth_name, password, doctype="Student Auth", fieldname="password")
	except frappe.AuthenticationError:
		return {"success": False, "error": "invalid_credentials"}

	doc = frappe.get_doc("Student Auth", auth_name)
	token = _generate_access_token(phone, [row.student for row in doc.students])
	return {"success": True, "token": token, "phone": phone, "profiles": _profiles_for_phone(phone)}


@frappe.whitelist(allow_guest=True)
def get_profiles(phone=None):
	phone = phone or frappe.form_dict.get("phone", "")

	token = _bearer_token()
	if not token:
		frappe.throw("Missing token", frappe.AuthenticationError)

	payload = _decode_access_token(token)
	if not payload:
		frappe.throw("Invalid or expired token", frappe.AuthenticationError)

	if payload.get("phone") != phone:
		frappe.throw("Token phone mismatch", frappe.AuthenticationError)

	if not frappe.db.exists("Student Auth", {"phone": phone}):
		frappe.throw("Phone not registered", frappe.DoesNotExistError)

	return {"phone": phone, "profiles": _profiles_for_phone(phone)}


@frappe.whitelist(allow_guest=True)
def forgot_password_send_otp(phone=None):
	phone = phone or frappe.form_dict.get("phone", "")
	if not phone:
		frappe.throw("phone is required", frappe.ValidationError)

	if not frappe.db.exists("Student Auth", {"phone": phone}):
		return {"success": False, "error": "phone_not_registered"}

	frappe.cache().set_value(f"reset_otp::{phone}", HARDCODED_OTP, expires_in_sec=OTP_EXPIRY_MINUTES * 60)
	return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def forgot_password_verify_otp(phone=None, otp=None):
	phone = phone or frappe.form_dict.get("phone", "")
	otp   = otp   or frappe.form_dict.get("otp")

	if not phone or not otp:
		frappe.throw("phone and otp are required", frappe.ValidationError)

	stored = frappe.cache().get_value(f"reset_otp::{phone}")
	if not stored:
		return {"success": False, "error": "otp_expired"}
	if stored != otp:
		return {"success": False, "error": "otp_invalid"}

	frappe.cache().delete_value(f"reset_otp::{phone}")
	return {"success": True, "reset_token": _generate_reset_token(phone), "phone": phone}


@frappe.whitelist(allow_guest=True)
def reset_password(phone=None, password=None):
	phone    = phone    or frappe.form_dict.get("phone", "")
	password = password or frappe.form_dict.get("password")

	if not password or len(password) < 6:
		frappe.throw("password must be at least 6 characters", frappe.ValidationError)

	token = _bearer_token()
	if not token:
		frappe.throw("Missing token", frappe.AuthenticationError)

	payload = _decode_reset_token(token)
	if not payload:
		frappe.throw("Invalid or expired reset token", frappe.AuthenticationError)

	if payload.get("phone") != phone:
		frappe.throw("Token phone mismatch", frappe.AuthenticationError)

	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	if not auth_name:
		frappe.throw("Phone not registered", frappe.DoesNotExistError)

	update_password(auth_name, password, doctype="Student Auth", fieldname="password")
	frappe.db.commit()

	doc = frappe.get_doc("Student Auth", auth_name)
	token = _generate_access_token(phone, [row.student for row in doc.students])
	return {"success": True, "token": token, "phone": phone, "profiles": _profiles_for_phone(phone)}
