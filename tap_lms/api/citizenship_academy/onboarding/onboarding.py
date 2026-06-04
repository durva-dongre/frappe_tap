import frappe
import jwt
import datetime
import requests
from frappe.utils.password import update_password

REGISTRATION_TOKEN_EXPIRY_MINUTES = 30
OTP_EXPIRY_MINUTES = 10
HARDCODED_OTP = "000000"
VALID_GENDERS = {"Male", "Female", "Others", "Not Available"}
VALID_SCHOOL_TYPES = {"APS", "GOVT", "NGO", "PPP", "PMC", "PVT", "GOVT. Aided", "ORG"}
JWT_EXPIRY_HOURS = 72


def _get_secret(key):
	cache = frappe.cache()
	cached = cache.get_value(f"secret::{key}")
	if cached:
		return cached
	value = frappe.get_doc("Secrets", key).get_password("value")
	cache.set_value(f"secret::{key}", value, expires_in_sec=3600)
	return value


def _get_jwt_secret():
	return _get_secret("jwt_secret")


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


def _generate_registration_token(phone):
	now = datetime.datetime.utcnow()
	return jwt.encode(
		{
			"phone": phone,
			"type": "registration",
			"exp": now + datetime.timedelta(minutes=REGISTRATION_TOKEN_EXPIRY_MINUTES),
			"iat": now,
		},
		_get_jwt_secret(),
		algorithm="HS256",
	)


def _decode_token(token, expected_type):
	try:
		payload = jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
		return payload if payload.get("type") == expected_type else None
	except Exception:
		return None


def _bearer_token():
	for header in ("X-Flutter-Authorization", "Authorization"):
		value = frappe.get_request_header(header, "")
		if value.startswith("Bearer "):
			return value[7:]
	return None


def _require_token(expected_type):
	token = _bearer_token()
	if not token:
		frappe.throw("Missing token", frappe.AuthenticationError)
	payload = _decode_token(token, expected_type)
	if not payload:
		if expected_type == "registration":
			payload = _decode_token(token, "access")
		if not payload:
			frappe.throw("Invalid or expired token", frappe.AuthenticationError)
	return payload


def _avatar_path(avatar_key):
	if not avatar_key:
		return "assets/avatars/avatar_01.png"
	return frappe.db.get_value("Student Avatar", avatar_key, "avatar_path") or "assets/avatars/avatar_01.png"


def _resolve_avatar(avatar_key):
	if avatar_key and frappe.db.exists("Student Avatar", avatar_key):
		return avatar_key
	fallback = frappe.get_all("Student Avatar", fields=["avatar_key"], order_by="avatar_key asc", limit=1)
	return fallback[0].avatar_key if fallback else "avatar_01"


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


def _ensure_student_auth(phone, raw_password):
	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")

	if auth_name:
		if not _password_exists(auth_name):
			update_password(auth_name, raw_password, doctype="Student Auth", fieldname="password")
			frappe.db.commit()
		return auth_name

	doc = frappe.new_doc("Student Auth")
	doc.phone = phone
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	update_password(doc.name, raw_password, doctype="Student Auth", fieldname="password")
	frappe.db.commit()
	return doc.name


def _complete_profile_response(phone, student_id):
	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	doc = frappe.get_doc("Student Auth", auth_name)
	token = _generate_access_token(phone, [row.student for row in doc.students])
	return {
		"success": True,
		"token": token,
		"phone": phone,
		"new_student_id": student_id,
		"profiles": _profiles_for_phone(phone),
	}


def _validate_profile_fields(gender, state, district, school_id, language):
	if gender not in VALID_GENDERS:
		frappe.throw("Invalid gender value")
	if not frappe.db.exists("State", state):
		frappe.throw("State not found")
	if not frappe.db.exists("District", district):
		frappe.throw("District not found")
	if not frappe.db.exists("School", school_id):
		frappe.throw("School not found")
	if not frappe.db.exists("TAP Language", language):
		frappe.throw("Language not found")


def _link_student(phone, student_id, avatar_key):
	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	doc = frappe.get_doc("Student Auth", auth_name)
	if student_id not in [row.student for row in doc.students]:
		doc.append("students", {"student": student_id, "avatar": avatar_key})
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
	frappe.db.commit()


def _insert_student(display_name, phone, gender, grade, school_id, language, dob):
	student = frappe.get_doc({
		"doctype": "Student",
		"name1": display_name,
		"phone": phone,
		"gender": gender,
		"grade": grade,
		"school_id": school_id,
		"language": language,
		"status": "active",
		**({"dob": dob} if dob else {}),
	})
	student.insert(ignore_permissions=True)
	return student.name


def _sync_leaderboard(student_id, display_name, state, district, school_id):
	try:
		worker_url = _get_secret("cf_worker_url")
		worker_secret = _get_secret("cf_worker_secret")

		school_data = frappe.db.get_value("School", school_id, ["name1", "city"], as_dict=True)
		state_name = frappe.db.get_value("State", state, "state_name")
		district_name = frappe.db.get_value("District", district, "district_name")

		requests.post(
			f"{worker_url}/students/register",
			json={
				"student_id": student_id,
				"name": display_name,
				"state_id": state,
				"state_name": state_name or state,
				"district_id": district,
				"district_name": district_name or district,
				"school_id": school_id,
				"school_name": school_data.name1 if school_data else school_id,
				"city": school_data.city if school_data else None,
			},
			headers={"Content-Type": "application/json", "X-Worker-Secret": worker_secret},
			timeout=5,
		)
	except Exception:
		frappe.log_error(title="Leaderboard Sync Error", message=frappe.get_traceback())


@frappe.whitelist(allow_guest=True)
def register_send_otp(phone=None):
	phone = phone or frappe.form_dict.get("phone", "")
	if not phone:
		frappe.throw("phone is required", frappe.ValidationError)
	if frappe.db.exists("Student Auth", {"phone": phone}):
		return {"success": False, "error": "phone_already_registered"}
	frappe.cache().set_value(f"otp::{phone}", HARDCODED_OTP, expires_in_sec=OTP_EXPIRY_MINUTES * 60)
	return {"success": True, "otp_sent": True}


@frappe.whitelist(allow_guest=True)
def register_verify_otp(phone=None, otp=None):
	phone = phone or frappe.form_dict.get("phone", "")
	otp = otp or frappe.form_dict.get("otp")
	if not phone or not otp:
		frappe.throw("phone and otp are required", frappe.ValidationError)

	stored = frappe.cache().get_value(f"otp::{phone}")
	if not stored:
		return {"success": False, "error": "otp_expired"}
	if stored != otp:
		return {"success": False, "error": "otp_invalid"}

	frappe.cache().delete_value(f"otp::{phone}")
	return {"success": True, "registration_token": _generate_registration_token(phone), "phone": phone}


@frappe.whitelist(allow_guest=True)
def create_profile(
	display_name=None, gender=None, grade=None, state=None, district=None,
	school_id=None, language=None, avatar=None, password=None, dob=None, migrate_student_id=None,
):
	display_name     = display_name     or frappe.form_dict.get("display_name")
	gender           = gender           or frappe.form_dict.get("gender")
	grade            = grade            or frappe.form_dict.get("grade")
	state            = state            or frappe.form_dict.get("state")
	district         = district         or frappe.form_dict.get("district")
	school_id        = school_id        or frappe.form_dict.get("school_id")
	language         = language         or frappe.form_dict.get("language")
	avatar           = avatar           or frappe.form_dict.get("avatar")
	password         = password         or frappe.form_dict.get("password")
	dob              = dob              or frappe.form_dict.get("dob")
	migrate_student_id = migrate_student_id or frappe.form_dict.get("migrate_student_id")

	payload = _require_token("registration")
	phone = payload["phone"]

	if not password or len(password) < 6:
		frappe.throw("password must be at least 6 characters", frappe.ValidationError)

	_validate_profile_fields(gender, state, district, school_id, language)
	avatar_key = _resolve_avatar(avatar)
	_ensure_student_auth(phone, password)

	if migrate_student_id:
		if not frappe.db.exists("Student", migrate_student_id):
			frappe.throw("Student to migrate not found")
		_link_student(phone, migrate_student_id, avatar_key)
		_sync_leaderboard(migrate_student_id, display_name, state, district, school_id)
		return _complete_profile_response(phone, migrate_student_id)

	student_id = _insert_student(display_name, phone, gender, grade, school_id, language, dob)
	_link_student(phone, student_id, avatar_key)
	_sync_leaderboard(student_id, display_name, state, district, school_id)
	return _complete_profile_response(phone, student_id)


@frappe.whitelist(allow_guest=True)
def add_profile(
	phone=None, display_name=None, gender=None, grade=None, state=None,
	district=None, school_id=None, language=None, avatar=None, dob=None, migrate_student_id=None,
):
	phone            = phone            or frappe.form_dict.get("phone", "")
	display_name     = display_name     or frappe.form_dict.get("display_name")
	gender           = gender           or frappe.form_dict.get("gender")
	grade            = grade            or frappe.form_dict.get("grade")
	state            = state            or frappe.form_dict.get("state")
	district         = district         or frappe.form_dict.get("district")
	school_id        = school_id        or frappe.form_dict.get("school_id")
	language         = language         or frappe.form_dict.get("language")
	avatar           = avatar           or frappe.form_dict.get("avatar")
	dob              = dob              or frappe.form_dict.get("dob")
	migrate_student_id = migrate_student_id or frappe.form_dict.get("migrate_student_id")

	payload = _require_token("access")
	if payload["phone"] != phone:
		frappe.throw("Token phone mismatch", frappe.AuthenticationError)

	_validate_profile_fields(gender, state, district, school_id, language)
	avatar_key = _resolve_avatar(avatar)

	if migrate_student_id:
		if not frappe.db.exists("Student", migrate_student_id):
			frappe.throw("Student to migrate not found")
		_link_student(phone, migrate_student_id, avatar_key)
		_sync_leaderboard(migrate_student_id, display_name, state, district, school_id)
		return _complete_profile_response(phone, migrate_student_id)

	student_id = _insert_student(display_name, phone, gender, grade, school_id, language, dob)
	_link_student(phone, student_id, avatar_key)
	_sync_leaderboard(student_id, display_name, state, district, school_id)
	return _complete_profile_response(phone, student_id)


@frappe.whitelist(allow_guest=True)
def select_profile(phone=None, student_id=None):
	phone      = phone      or frappe.form_dict.get("phone", "")
	student_id = student_id or frappe.form_dict.get("student_id")

	payload = _require_token("access")
	if payload.get("phone") != phone:
		frappe.throw("Token phone mismatch", frappe.AuthenticationError)

	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	doc = frappe.get_doc("Student Auth", auth_name)
	linked_ids = [row.student for row in doc.students]

	if student_id not in linked_ids:
		frappe.throw("Profile not linked to this phone", frappe.AuthenticationError)

	profiles = _profiles_for_phone(phone)
	return {
		"success": True,
		"token": _generate_access_token(phone, linked_ids),
		"phone": phone,
		"active_profile": next((p for p in profiles if p["student_id"] == student_id), None),
		"profiles": profiles,
	}


@frappe.whitelist(allow_guest=True)
def update_avatar(phone=None, student_id=None, avatar=None):
	phone      = phone      or frappe.form_dict.get("phone", "")
	student_id = student_id or frappe.form_dict.get("student_id")
	avatar     = avatar     or frappe.form_dict.get("avatar")

	payload = _require_token("access")
	if payload["phone"] != phone:
		frappe.throw("Token phone mismatch", frappe.AuthenticationError)

	if not frappe.db.exists("Student Avatar", avatar):
		frappe.throw("Invalid avatar")

	auth_name = frappe.db.get_value("Student Auth", {"phone": phone}, "name")
	doc = frappe.get_doc("Student Auth", auth_name)

	for row in doc.students:
		if row.student == student_id:
			row.avatar = avatar
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			return {"success": True, "avatar": _avatar_path(avatar)}

	frappe.throw("Profile not found on this account")


@frappe.whitelist(allow_guest=True)
def get_states():
	return {
		"states": frappe.get_all("State", fields=["name as id", "state_name as name"], order_by="state_name asc")
	}


@frappe.whitelist(allow_guest=True)
def get_districts(state=None):
	state = state or frappe.form_dict.get("state")
	if not state:
		frappe.throw("state is required", frappe.ValidationError)
	if not frappe.db.exists("State", state):
		frappe.throw("State not found", frappe.DoesNotExistError)
	return {
		"state": state,
		"districts": frappe.get_all(
			"District",
			filters={"state": state},
			fields=["name as id", "district_name as name"],
			order_by="district_name asc",
		),
	}


@frappe.whitelist(allow_guest=True)
def get_schools(district=None, search=None):
	district = district or frappe.form_dict.get("district")
	search   = search   or frappe.form_dict.get("search", "")
	if not district:
		frappe.throw("district is required", frappe.ValidationError)
	if not frappe.db.exists("District", district):
		frappe.throw("District not found", frappe.DoesNotExistError)
	filters = {"district": district}
	if search:
		filters["name1"] = ["like", f"%{search}%"]
	return {
		"district": district,
		"schools": frappe.get_all(
			"School",
			filters=filters,
			fields=["name as id", "name1 as name", "type", "city"],
			order_by="name1 asc",
			limit=50,
		),
	}


@frappe.whitelist(allow_guest=True)
def create_school(name=None, district=None, type="GOVT"):
	name     = name     or frappe.form_dict.get("name")
	district = district or frappe.form_dict.get("district")
	type     = type     or frappe.form_dict.get("type", "GOVT")
	if type not in VALID_SCHOOL_TYPES:
		frappe.throw("Invalid school type")
	if not frappe.db.exists("District", district):
		frappe.throw("District not found")
	existing = frappe.db.get_value("School", {"name1": name, "district": district}, "name")
	if existing:
		return {"school_id": existing, "name": name, "created": False}
	doc = frappe.new_doc("School")
	doc.name1    = name
	doc.district = district
	doc.type     = type
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"school_id": doc.name, "name": name, "created": True}


@frappe.whitelist(allow_guest=True)
def get_languages():
	return {
		"languages": frappe.get_all("TAP Language", fields=["name as id", "language_name as name"], order_by="language_name asc")
	}


@frappe.whitelist(allow_guest=True)
def get_avatars():
	rows = frappe.get_all("Student Avatar", fields=["avatar_key", "avatar_path"], order_by="avatar_key asc")
	return {"avatars": [{"key": r.avatar_key, "path": r.avatar_path} for r in rows]}
