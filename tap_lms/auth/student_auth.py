import frappe
import jwt
import datetime
from frappe.utils.password import check_password, update_password


JWT_EXPIRY_HOURS = 72
MAX_ATTEMPTS = 5


def get_secret(key):
    cache = frappe.cache()

    cached = cache.get_value(f"secret::{key}")
    if cached:
        return cached

    secret_doc = frappe.get_doc("Secrets", key)
    value = secret_doc.get_password("value")

    cache.set_value(f"secret::{key}", value)

    return value


def get_jwt_secret():
    return get_secret("jwt_secret")


@frappe.whitelist(allow_guest=True)
def login(phone, password):
    auth = frappe.db.get_value(
        "Student Auth",
        {"phone": phone},
        [
            "name",
            "is_locked",
            "failed_attempts",
            "locked_until"
        ],
        as_dict=True
    )

    if not auth:
        return {
            "success": False,
            "error": "invalid_credentials"
        }

    doc = frappe.get_doc("Student Auth", auth.name)

    if doc.is_currently_locked():
        return {
            "success": False,
            "error": "account_locked",
            "locked_until": str(doc.locked_until)
        }

    try:
        check_password(
            "Student Auth",
            phone,
            password,
            fieldname="password"
        )

    except frappe.AuthenticationError:
        doc.increment_failed()

        remaining = max(
            0,
            MAX_ATTEMPTS - doc.failed_attempts
        )

        return {
            "success": False,
            "error": "invalid_credentials",
            "attempts_remaining": remaining
        }

    doc.reset_lock()

    students = [
        {
            "student_id": row.student,
            "name": row.student_name
        }
        for row in doc.students
    ]

    token = _generate_jwt(
        phone,
        [s["student_id"] for s in students]
    )

    return {
        "success": True,
        "token": token,
        "phone": phone,
        "profiles": students
    }


@frappe.whitelist()
def set_password(phone, new_password):
    if not frappe.db.exists("Student Auth", phone):
        frappe.throw("No auth record found")

    update_password(
        "Student Auth",
        phone,
        new_password,
        fieldname="password"
    )

    return {
        "success": True
    }


@frappe.whitelist(allow_guest=True)
def verify_token(token):
    payload = _decode_jwt(token)

    if not payload:
        return {
            "valid": False
        }

    return {
        "valid": True,
        "phone": payload.get("phone"),
        "students": payload.get("students")
    }


def _generate_jwt(phone, student_ids):
    payload = {
        "phone": phone,
        "students": student_ids,
        "exp": datetime.datetime.utcnow()
        + datetime.timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.datetime.utcnow()
    }

    return jwt.encode(
        payload,
        get_jwt_secret(),
        algorithm="HS256"
    )


def _decode_jwt(token):
    try:
        return jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=["HS256"]
        )

    except Exception:
        return None


def link_student_to_phone(phone, student_id):
    if not frappe.db.exists("Student Auth", phone):
        frappe.throw(f"No Student Auth record for {phone}")

    doc = frappe.get_doc("Student Auth", phone)

    existing = [
        row.student
        for row in doc.students
    ]

    if student_id not in existing:
        doc.append(
            "students",
            {
                "student": student_id
            }
        )

        doc.save(ignore_permissions=True)


def bulk_create_auth(students_data):
    for entry in students_data:
        phone = entry["phone"]
        password = entry["password"]
        student_id = entry["student_id"]

        if not frappe.db.exists("Student Auth", phone):
            doc = frappe.get_doc({
                "doctype": "Student Auth",
                "phone": phone,
                "failed_attempts": 0,
                "is_locked": 0,
                "students": [
                    {
                        "student": student_id
                    }
                ]
            })

            doc.insert(ignore_permissions=True)

            update_password(
                "Student Auth",
                phone,
                password,
                fieldname="password"
            )

        else:
            link_student_to_phone(
                phone,
                student_id
            )

    frappe.db.commit()