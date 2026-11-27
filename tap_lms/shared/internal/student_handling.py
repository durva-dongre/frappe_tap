# Copyright (c) 2026, Techt4dev and contributors
# For license information, please see license.txt

"""
Part of tap_lms.internal -- the shared folder for internal, non-doctype
whitelisted endpoints (ops/automation hooks called from Apps Script and
similar external scripts, as opposed to doctype controller logic). Add
further internal endpoints as new files in this same folder.

This file (student_handling.py) covers student bulk-onboarding and the
test-student reset flow. It exposes two whitelisted endpoints:

  - onboard_students : create/update Student records, their Student Enrollment
    child rows and ProgramEnrollment documents, in bulk, from a list of
    row dicts (e.g. one row per spreadsheet line).

  - reset_students : for a list of existing Student IDs, delete their
    Submission records and clear (but not delete) the unit_progress table
    on every ProgramEnrollment belonging to that student.

  - get_student_details : for a list of existing Student IDs, return one
    flattened row per student with Student fields, their (single, active)
    ProgramEnrollment fields, and a submission count. Read-only.

Auth: all endpoints are plain @frappe.whitelist() methods and rely on
standard Frappe API key/secret auth (Authorization: token <key>:<secret>).
Create a dedicated Frappe User for Apps Script and grant it a role with
create/write permission on Student, ProgramEnrollment and Submission, plus
delete permission on Submission for reset_students to work.

Both endpoints accept and return plain JSON-serializable data only, and
never raise on a per-row failure -- each row's outcome is reported back
so the caller (a spreadsheet script) can mark successes/failures per line
without the whole batch aborting.
"""

import frappe
from frappe.utils import cstr


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@frappe.whitelist()
def onboard_students(rows):
    """
    Bulk create/update students with enrollment + program enrollment.

    `rows` is a list of dicts (or a JSON string of such a list). Each row
    may contain:

        name1            (required) student's display name
        phone            (required) phone number, any of the accepted formats
        school_keyword   school's `keyword` field (preferred way to find a School)
        school           School doc name, used if school_keyword is not given
        grade
        gender
        language         TAP Language doc name
        preferred_day
        preferred_time
        batch            Batch doc name, used for the Student Enrollment child row
        course_level     Course Level doc name, used for ProgramEnrollment
        level            optional override; derived from grade if omitted
        status           Student.status, defaults to "active"
        row_ref          anything the caller wants echoed back (e.g. a sheet
                          row number) to make matching results to rows easy

    Returns a dict:
        {
            "summary": {"total": N, "created": N, "updated": N, "failed": N},
            "results": [
                {
                    "row_ref": ...,
                    "ok": true/false,
                    "student": "ST00000123" or null,
                    "program_enrollment": "..." or null,
                    "action": "created" | "updated" | null,
                    "error": null or "message"
                },
                ...
            ]
        }
    """
    rows = _as_list(rows)

    results = []
    created = updated = failed = 0

    for row in rows:
        row = row or {}
        row_ref = row.get("row_ref")
        try:
            student_name, action, program_enrollment_name = _onboard_one_student(row)
            if action == "created":
                created += 1
            else:
                updated += 1
            results.append({
                "row_ref": row_ref,
                "ok": True,
                "student": student_name,
                "program_enrollment": program_enrollment_name,
                "action": action,
                "error": None,
            })
            frappe.db.commit()
        except Exception as err:
            failed += 1
            frappe.db.rollback()
            frappe.log_error(
                title="onboard_students row failed",
                message=f"row_ref={row_ref} row={row} error={err}",
            )
            results.append({
                "row_ref": row_ref,
                "ok": False,
                "student": None,
                "program_enrollment": None,
                "action": None,
                "error": str(err),
            })

    return {
        "summary": {
            "total": len(rows),
            "created": created,
            "updated": updated,
            "failed": failed,
        },
        "results": results,
    }


def _onboard_one_student(row):
    """Create or update a single Student + enrollment + ProgramEnrollment.

    Returns (student_name, "created"|"updated", program_enrollment_name_or_None).
    Raises on any validation problem; caller is responsible for catching.
    """
    name1 = (row.get("name1") or "").strip()
    phone = (row.get("phone") or "").strip()
    if not name1:
        frappe.throw("name1 (student name) is required")
    if not phone:
        frappe.throw("phone is required")

    canonical_phone = _canonicalize_phone(phone)

    school_id = _resolve_school(row.get("school_keyword"), row.get("school"))

    grade = row.get("grade")
    level = row.get("level") or _get_level_for_grade(grade)

    existing_name = frappe.db.get_value(
        "Student", {"phone": canonical_phone, "name1": name1}, "name"
    )

    if existing_name:
        doc = frappe.get_doc("Student", existing_name)
        action = "updated"
    else:
        doc = frappe.new_doc("Student")
        doc.phone = canonical_phone
        action = "created"

    doc.name1 = name1
    if grade:
        doc.grade = grade
    if row.get("gender"):
        doc.gender = row.get("gender")
    if row.get("language"):
        doc.language = row.get("language")
    if row.get("preferred_day"):
        doc.preferred_day = row.get("preferred_day")
    if row.get("preferred_time"):
        doc.preferred_time = row.get("preferred_time")
    if level:
        doc.level = level
    doc.status = row.get("status") or doc.status or "active"
    if school_id:
        doc.school_id = school_id

    batch = row.get("batch")
    if batch:
        already_enrolled = any(
            cstr(en.get("batch")) == cstr(batch) for en in (doc.enrollment or [])
        )
        if not already_enrolled:
            doc.append("enrollment", {
                "batch": batch,
                "grade": grade,
                "level": level,
            })

    if action == "created":
        doc.insert(ignore_permissions=False)
    else:
        doc.save(ignore_permissions=False)

    program_enrollment_name = None
    course_level = row.get("course_level")
    if batch and course_level:
        program_enrollment_name = _get_or_create_program_enrollment(
            student=doc.name, batch=batch, course_level=course_level
        )

    return doc.name, action, program_enrollment_name


def _get_or_create_program_enrollment(student, batch, course_level):
    existing = frappe.db.get_value(
        "ProgramEnrollment",
        {"student": student, "batch": batch, "course_level": course_level},
        "name",
    )
    if existing:
        return existing

    pe = frappe.new_doc("ProgramEnrollment")
    pe.student = student
    pe.batch = batch
    pe.course_level = course_level
    pe.status = "default"
    pe.stage = "no_response"
    pe.insert(ignore_permissions=False)
    return pe.name


def _resolve_school(school_keyword, school_name):
    if school_keyword:
        found = frappe.db.get_value("School", {"keyword": school_keyword}, "name")
        if not found:
            frappe.throw(f"No School found with keyword '{school_keyword}'")
        return found
    if school_name:
        if not frappe.db.exists("School", school_name):
            frappe.throw(f"No School found with name '{school_name}'")
        return school_name
    return None


# ---------------------------------------------------------------------------
# Reset (test students)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def reset_students(student_ids):
    """
    For each given Student ID: delete that student's Submission records and
    clear (not delete) the unit_progress table on every ProgramEnrollment
    belonging to them. The Student doc and ProgramEnrollment docs themselves
    are left in place.

    `student_ids` is a list of Student doc names (e.g. ["ST00000123", ...]),
    or a JSON string of such a list.

    Returns:
        {
            "summary": {"total": N, "ok": N, "failed": N},
            "results": [
                {
                    "student": "ST00000123",
                    "ok": true/false,
                    "submissions_deleted": N,
                    "program_enrollments_cleared": N,
                    "error": null or "message"
                },
                ...
            ]
        }
    """
    student_ids = _as_list(student_ids)

    results = []
    ok_count = failed = 0

    for student_id in student_ids:
        student_id = cstr(student_id).strip()
        try:
            submissions_deleted, pe_cleared = _reset_one_student(student_id)
            ok_count += 1
            results.append({
                "student": student_id,
                "ok": True,
                "submissions_deleted": submissions_deleted,
                "program_enrollments_cleared": pe_cleared,
                "error": None,
            })
            frappe.db.commit()
        except Exception as err:
            failed += 1
            frappe.db.rollback()
            frappe.log_error(
                title="reset_students row failed",
                message=f"student={student_id} error={err}",
            )
            results.append({
                "student": student_id,
                "ok": False,
                "submissions_deleted": 0,
                "program_enrollments_cleared": 0,
                "error": str(err),
            })

    return {
        "summary": {
            "total": len(student_ids),
            "ok": ok_count,
            "failed": failed,
        },
        "results": results,
    }


def _reset_one_student(student_id):
    if not student_id:
        frappe.throw("student id is required")
    if not frappe.db.exists("Student", student_id):
        frappe.throw(f"No Student found with id '{student_id}'")

    # Submission.student_id is stored as plain Data (not a Link), matching
    # how register_student/update_student_profile populate submissions today.
    submission_names = frappe.get_all(
        "Submission", filters={"student_id": student_id}, pluck="name"
    )
    for sub_name in submission_names:
        frappe.delete_doc(
            "Submission", sub_name, ignore_permissions=False, force=True
        )

    pe_names = frappe.get_all(
        "ProgramEnrollment", filters={"student": student_id}, pluck="name"
    )
    for pe_name in pe_names:
        pe = frappe.get_doc("ProgramEnrollment", pe_name)
        pe.set("unit_progress", [])
        pe.points = 0
        pe.gems = 0
        pe.submission_this_week = 0
        pe.last_activity_at = None
        pe.save(ignore_permissions=False)

    return len(submission_names), len(pe_names)


# ---------------------------------------------------------------------------
# Tracker (read-only student detail lookup)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def list_all_student_ids():
    """
    One-off/occasional full dump: returns every Student ID currently in the
    system, oldest first. Intended to be run once after setup to backfill a
    Tracker sheet with pre-existing manually-created accounts (at the time
    this was written, every account in the system is a test account, so no
    filtering is applied here -- the caller/spreadsheet owner decides later
    which rows are "real" vs "test").

    Returns:
        {"count": N, "student_ids": ["ST00000001", "ST00000002", ...]}
    """
    student_ids = frappe.get_all(
        "Student", fields=["name"], order_by="creation asc", pluck="name"
    )
    return {"count": len(student_ids), "student_ids": student_ids}


@frappe.whitelist()
def get_student_details(student_ids):
    """
    Read-only lookup: one flattened row per Student ID, combining Student
    fields with that student's ProgramEnrollment (assumes a student has at
    most one active enrollment, per current product design) and a count of
    their Submission records.

    `student_ids` is a list of Student doc names, or a JSON string of such
    a list.

    Returns:
        {
            "results": [
                {
                    "student": "ST00000123",
                    "ok": true/false,
                    "error": null or "message",

                    # Student fields (present when ok)
                    "name1": ..., "phone": ..., "status": ..., "gender": ...,
                    "grade": ..., "language": ..., "level": ..., "rigour": ...,
                    "school_id": ..., "state_id": ..., "district_id": ...,
                    "whatsapp_consent": 0/1, "joined_on": ...,
                    "preferred_day": ..., "preferred_time": ...,
                    "glific_id": ..., "glific_sync_status": ...,
                    "profile_id": ..., "swiftchat_id": ...,
                    "access_rate": ..., "submission_rate": ...,

                    # ProgramEnrollment fields (blank if none exists)
                    "program_enrollment": ..., "batch": ...,
                    "course_level": ..., "pe_status": ..., "stage": ...,
                    "last_activity_at": ..., "points": ..., "gems": ...,
                    "submission_this_week": ..., "unit_progress_count": ...,

                    "submission_count": N
                },
                ...
            ]
        }
    """
    student_ids = _as_list(student_ids)

    results = []
    for student_id in student_ids:
        student_id = cstr(student_id).strip()
        try:
            results.append(_get_one_student_detail(student_id))
        except Exception as err:
            frappe.log_error(
                title="get_student_details row failed",
                message=f"student={student_id} error={err}",
            )
            results.append({
                "student": student_id,
                "ok": False,
                "error": str(err),
            })

    return {"results": results}


_STUDENT_DETAIL_FIELDS = [
    "name1", "phone", "status", "gender", "grade", "language", "level",
    "rigour", "school_id", "state_id", "district_id", "whatsapp_consent",
    "joined_on", "preferred_day", "preferred_time", "glific_id",
    "glific_sync_status", "profile_id", "swiftchat_id", "access_rate",
    "submission_rate",
]

_PROGRAM_ENROLLMENT_DETAIL_FIELDS = [
    "name", "batch", "course_level", "status", "stage", "last_activity_at",
    "points", "gems", "submission_this_week",
]


def _get_one_student_detail(student_id):
    if not student_id:
        frappe.throw("student id is required")

    student_row = frappe.db.get_value(
        "Student", student_id, _STUDENT_DETAIL_FIELDS, as_dict=True
    )
    if not student_row:
        frappe.throw(f"No Student found with id '{student_id}'")

    row = {"student": student_id, "ok": True, "error": None}
    row.update(student_row)

    # Per current product design a student has at most one active
    # ProgramEnrollment; if several exist, the most recently modified wins.
    pe_rows = frappe.get_all(
        "ProgramEnrollment",
        filters={"student": student_id},
        fields=_PROGRAM_ENROLLMENT_DETAIL_FIELDS,
        order_by="modified desc",
        limit=1,
    )
    if pe_rows:
        pe = pe_rows[0]
        row["program_enrollment"] = pe.get("name")
        row["batch"] = pe.get("batch")
        row["course_level"] = pe.get("course_level")
        row["pe_status"] = pe.get("status")
        row["stage"] = pe.get("stage")
        row["last_activity_at"] = pe.get("last_activity_at")
        row["points"] = pe.get("points")
        row["gems"] = pe.get("gems")
        row["submission_this_week"] = pe.get("submission_this_week")
        row["unit_progress_count"] = frappe.db.count(
            "Unit Progress", {"parent": pe.get("name")}
        )
    else:
        for key in ("program_enrollment", "batch", "course_level", "pe_status",
                    "stage", "last_activity_at", "points", "gems",
                    "submission_this_week", "unit_progress_count"):
            row[key] = None

    row["submission_count"] = frappe.db.count(
        "Submission", {"student_id": student_id}
    )

    return row


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _as_list(value):
    """Accept either a real list/tuple or a JSON-encoded string of one."""
    if value is None:
        frappe.throw("No data provided")
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        import json
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            frappe.throw("Expected a JSON list")
        return parsed
    frappe.throw("Unsupported data type; expected a list or JSON list string")


def _canonicalize_phone(phone):
    phone = cstr(phone).strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    frappe.throw(
        f"Phone '{phone}' must be exactly 10 digits, or 12 digits starting with 91"
    )


def _get_level_for_grade(grade):
    try:
        grade_num = int(cstr(grade).strip())
    except Exception:
        return ""
    if grade_num <= 3:
        return "Level 0"
    if 4 <= grade_num <= 5:
        return "Level 1"
    if 6 <= grade_num <= 8:
        return "Level 2"
    if 9 <= grade_num <= 10:
        return "Level 3"
    if 11 <= grade_num <= 12:
        return "Level 4"
    return ""