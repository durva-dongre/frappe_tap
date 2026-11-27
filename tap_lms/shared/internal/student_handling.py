# Copyright (c) 2026, Techt4dev and contributors
# For license information, please see license.txt

"""
Part of tap_lms.shared.internal -- the shared folder for internal,
non-doctype whitelisted endpoints (ops/automation hooks called from Apps
Script and similar external scripts, as opposed to doctype controller logic).
Add further internal endpoints as new files in this same folder.

This file (student_handling.py) covers student bulk-onboarding and the
test-student reset flow. It exposes four whitelisted endpoints:

  - onboard_students    : create/update Student records and their
                          ProgramEnrollment documents, in bulk, from a list
                          of row dicts (e.g. one row per spreadsheet line).
                          Each row may independently set School, State and
                          District -- State/District are NOT derived from
                          the School; whatever is given in the row wins.
                          There is no Student Enrollment child table in this
                          design: batch/course_level tracking lives entirely
                          on ProgramEnrollment, and Student carries only its
                          own `level` field (L1/L2/L3).

  - reset_students      : for a list of existing Student IDs, delete their
                          Submission records and clear (not delete) the
                          unit_progress table on every ProgramEnrollment
                          belonging to that student.

  - get_student_details : for a list of existing Student IDs, return one
                          flattened row per student with Student fields,
                          their (most recently modified) ProgramEnrollment
                          fields, and a submission count. Read-only.

  - list_all_student_ids: one-off full dump of every Student ID in the
                          system, oldest first. Used to backfill a Tracker
                          sheet with pre-existing manually-created accounts.

Auth: all endpoints are plain @frappe.whitelist() methods and rely on
standard Frappe API key/secret auth (Authorization: token <key>:<secret>).
Create a dedicated Frappe User for Apps Script and grant it a role with
create/write permission on Student and ProgramEnrollment, plus delete
permission on Submission for reset_students to work, and read permission on
State/District/School/Batch/Course Level/TAP Language for the Link
validations below to succeed.

Both endpoints accept and return plain JSON-serializable data only, and
never raise on a per-row failure -- each row's outcome is reported back so
the caller (a spreadsheet script) can mark successes/failures per line
without the whole batch aborting.

IMPORTANT -- level fields, two different option sets:
  - Student.level is a Select with options exactly "L1"/"L2"/"L3", derived
    from grade by _get_level_for_grade() below (or overridden by the row's
    own `level` column).
  - Course Level.level is a *different* Select, with options "Level 0",
    "Level 1", ..., "Level 4K". That value lives only on the Course Level
    doc itself (looked up via the row's `course_level` column) and is never
    written here -- ProgramEnrollment links to Course Level but has no
    `level` field of its own.
  These two option sets must never be cross-assigned. This file only ever
  writes the L1/L2/L3 form, and only to Student.level.
"""

import json

import frappe
from frappe.utils import cstr, getdate, nowdate

# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------


@frappe.whitelist()
def onboard_students(rows):
    """
    Bulk create/update students with a ProgramEnrollment.

    `rows` is a list of dicts (or a JSON string of such a list). Each row
    may contain:

        name1            (required) student's display name
        phone            (required) phone number, any of the accepted formats
        school_id        School doc name (preferred way to set a School --
                          direct, unambiguous Link lookup)
        school_keyword   school's `keyword` field; used only if school_id
                          is not given (fallback for rows without a School
                          ID yet)
        state_id         State doc name, optional. Set independently of
                          School -- never auto-derived from it.
        district_id      District doc name, optional. Set independently of
                          School -- never auto-derived from it.
        grade
        gender
        language         TAP Language doc name
        preferred_day
        preferred_time
        batch            Batch doc name, used (with course_level) to
                          create/find the student's ProgramEnrollment
        course_level     Course Level doc name, used (with batch) to
                          create/find the student's ProgramEnrollment
        level            Student.level override; one of L1/L2/L3. If
                          omitted, derived from grade (1-5 -> L1, 6-8 -> L2,
                          9-12 -> L3). This is ONLY ever "L1"/"L2"/"L3" --
                          never the Course Level-style "Level N" values.
        status           Student.status, defaults to "active"
        joined_on        Student.joined_on, a date (e.g. "2026-04-01").
                          Optional -- only used when the Student is being
                          CREATED and doesn't already have a joined_on; if
                          omitted on creation, defaults to today. Never
                          overwrites an existing joined_on on update, so
                          re-onboarding a row doesn't reset a real join date.
        row_ref          anything the caller wants echoed back (e.g. a
                          sheet row number) to make matching results to
                          rows easy

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
    """Create or update a single Student + ProgramEnrollment.

    School, State and District are each resolved independently from the
    row's own school_id/school_keyword, state_id and district_id -- State
    and District are NEVER inferred from the chosen School, even though
    School itself links to both. If a row wants District/State to match
    its School, the sheet must say so explicitly in those columns.

    There is no Student Enrollment child table in this design -- batch and
    course_level are tracked solely via ProgramEnrollment, not written onto
    the Student doc itself.

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

    school_id = _resolve_school(row.get("school_id"), row.get("school_keyword"))
    state_id = _resolve_link("State", row.get("state_id"))
    district_id = _resolve_link("District", row.get("district_id"))

    grade = row.get("grade")
    # Student.level options are exactly "L1"/"L2"/"L3" -- never the Course
    # Level-style "Level N" values. See module docstring.
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

    # Each of School / State / District is set independently, exactly as
    # given on the row -- none is derived from another.
    if school_id:
        doc.school_id = school_id
    if state_id:
        doc.state_id = state_id
    if district_id:
        doc.district_id = district_id

    if action == "created":
        if not doc.joined_on:
            doc.joined_on = _resolve_joined_on(row.get("joined_on"))
        doc.insert(ignore_permissions=False)
    else:
        doc.save(ignore_permissions=False)

    program_enrollment_name = None
    batch = row.get("batch")
    course_level = row.get("course_level")
    if batch and course_level:
        program_enrollment_name = _get_or_create_program_enrollment(
            student=doc.name, batch=batch, course_level=course_level
        )

    return doc.name, action, program_enrollment_name


def _get_or_create_program_enrollment(student, batch, course_level):
    if not frappe.db.exists("Batch", batch):
        frappe.throw(f"No Batch found with id '{batch}'")
    if not frappe.db.exists("Course Level", course_level):
        frappe.throw(f"No Course Level found with id '{course_level}'")

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


def _resolve_school(school_id, school_keyword):
    """Prefer an explicit School doc name (school_id) -- it's a direct,
    unambiguous Link lookup. Fall back to school_keyword only if school_id
    wasn't given, for rows that don't yet have the School ID on hand.
    Returns None if neither was given.
    """
    school_id = (school_id or "").strip() if isinstance(school_id, str) else school_id
    school_keyword = (
        (school_keyword or "").strip() if isinstance(school_keyword, str) else school_keyword
    )

    if school_id:
        if not frappe.db.exists("School", school_id):
            frappe.throw(f"No School found with id '{school_id}'")
        return school_id
    if school_keyword:
        found = frappe.db.get_value("School", {"keyword": school_keyword}, "name")
        if not found:
            frappe.throw(f"No School found with keyword '{school_keyword}'")
        return found
    return None


def _resolve_joined_on(joined_on):
    """Validate an optional joined_on date given on the row. Returns today's
    date (server date, as a string) if not given or blank; raises if given
    but not a valid date. Only ever called when CREATING a Student that has
    no joined_on yet -- never used to overwrite an existing value.
    """
    joined_on = (joined_on or "").strip() if isinstance(joined_on, str) else joined_on
    if not joined_on:
        return nowdate()
    try:
        return cstr(getdate(joined_on))
    except Exception:
        frappe.throw(f"joined_on '{joined_on}' is not a valid date")


def _resolve_link(doctype, doc_id):
    """Validate an optional Link-field value (State/District doc name)
    passed in directly from the sheet. Returns None if not given, raises
    if given but the doc doesn't exist. Purely independent of School --
    callers never infer this value from a School doc.
    """
    doc_id = (doc_id or "").strip() if isinstance(doc_id, str) else doc_id
    if not doc_id:
        return None
    if not frappe.db.exists(doctype, doc_id):
        frappe.throw(f"No {doctype} found with id '{doc_id}'")
    return doc_id


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
# Tracker / details (read-only student detail lookup)
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
    most one meaningful enrollment at a time -- if several exist, the most
    recently modified one wins) and a count of their Submission records.

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

    # Per current product design a student has at most one meaningfully
    # active ProgramEnrollment; if several exist, the most recently
    # modified wins.
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
    """Maps a grade to Student.level, whose options are exactly L1/L2/L3
    (see student.json). Do not reuse this for Course Level's `level` field,
    which has its own, different option set (Level 0 / Level 1 / ... / Level 4K).
    """
    try:
        grade_num = int(cstr(grade).strip())
    except Exception:
        return ""
    if 1 <= grade_num <= 5:
        return "L1"
    if 6 <= grade_num <= 8:
        return "L2"
    if 9 <= grade_num <= 12:
        return "L3"
    return ""