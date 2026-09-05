import json

import frappe

TEST_BATCH = "BT00000025"

PE_DEFAULTS = {
    "program_type": "Summer",
    "current_path": "Core",
    "archetype": "submitter",
    "journey_label": "enrolled",
    "program_status": "active",
    "resolved_flow_state": "normal_content_delivery",
    "current_week": 1,
    "max_allowed_week": 1,
}


def _get_payload():
    if frappe.request and frappe.request.data:
        try:
            return json.loads(frappe.request.data)
        except ValueError:
            pass
    return frappe.local.form_dict


def _normalize_phone(phone):
    phone = (phone or "").strip()
    if phone.startswith("91") and len(phone) == 12:
        return phone[2:]
    return phone


@frappe.whitelist(allow_guest=False)
def register_test_student():
    payload = _get_payload()
    name1 = payload.get("name1")
    phone = _normalize_phone(payload.get("phone"))
    glific_id = payload.get("glific_id")
    grade = payload.get("grade")
    gender = payload.get("gender")

    if not name1 or not phone:
        return {
            "message": {
                "status_code": 400,
                "success": False,
                "error": "name1 and phone are required",
            }
        }

    try:
        existing_students = frappe.get_all(
            "Student",
            filters={"phone": phone, "name1": name1},
            fields=["name"],
            limit=1,
        )

        if existing_students:
            student_id = existing_students[0]["name"]
            existing_pe = frappe.get_all(
                "ProgramEnrollment",
                filters={"student": student_id, "batch": TEST_BATCH},
                fields=["name"],
                limit=1,
            )
            pe_name = existing_pe[0]["name"] if existing_pe else None
            return {
                "message": {
                    "status_code": 200,
                    "success": True,
                    "student_id": student_id,
                    "pe_name": pe_name,
                    "created_student": False,
                    "created_pe": False,
                }
            }

        student = frappe.new_doc("Student")
        student.name1 = name1
        student.phone = phone
        if grade:
            student.grade = grade
        if gender:
            student.gender = gender
        if glific_id:
            student.glific_id = glific_id
        student.status = "active"
        student.insert(ignore_permissions=True)

        pe = frappe.new_doc("ProgramEnrollment")
        pe.student = student.name
        pe.batch = TEST_BATCH
        pe.enrollment = f"{student.name}-{TEST_BATCH}"
        pe.glific_id = glific_id or ""
        for field, value in PE_DEFAULTS.items():
            setattr(pe, field, value)
        pe.insert(ignore_permissions=True)

        frappe.db.commit()

        return {
            "message": {
                "status_code": 200,
                "success": True,
                "student_id": student.name,
                "pe_name": pe.name,
                "created_student": True,
                "created_pe": True,
            }
        }
    except Exception as err:
        frappe.db.rollback()
        frappe.log_error(
            title="register_test_student failed",
            message=frappe.get_traceback(),
        )
        return {
            "message": {
                "status_code": 500,
                "success": False,
                "error": str(err),
            }
        }


@frappe.whitelist(allow_guest=False)
def reset_test_student():
    payload = _get_payload()
    student_id = payload.get("student_id")

    if not student_id:
        return {
            "message": {
                "success": False,
                "error": "student_id is required",
            }
        }

    try:
        pe_names = frappe.get_all(
            "ProgramEnrollment",
            filters={"student": student_id},
            fields=["name"],
        )

        pe_reset = False
        for row in pe_names:
            pe = frappe.get_doc("ProgramEnrollment", row["name"])
            for field, value in PE_DEFAULTS.items():
                setattr(pe, field, value)
            pe.total_activity_points = 0
            pe.weekly_activity_points = 0
            pe.total_quiz_points = 0
            pe.weekly_quiz_points = 0
            pe.bonus_quiz_points = 0
            pe.total_submission_points = 0
            pe.weekly_submission_points = 0
            pe.special_gems = 0
            pe.total_points = 0
            pe.current_streak = 0
            pe.pause_count = 0
            pe.submission_count = 0
            pe.quiz_completed = 0
            pe.weekly_submission_done = 0
            pe.weekly_video_done = 0
            pe.in_grace_window = 0
            pe.grace_window_start = None
            pe.grace_window_end_at = None
            pe.pause_reason = None
            pe.next_action_at = None
            pe.next_action_type = None
            pe.delivery_failure_count = 0
            pe.last_flow_triggered = None
            pe.last_flow_triggered_at = None
            pe.last_submission_at = None
            pe.current_escalation_step = 0
            pe.current_escalation_type = None
            pe.drop_reason = None
            pe.save(ignore_permissions=True)
            pe_reset = True

        submission_names = frappe.get_all(
            "Submission",
            filters={"student_id": student_id},
            fields=["name"],
        )
        submissions_deleted = 0
        for row in submission_names:
            frappe.delete_doc("Submission", row["name"], ignore_permissions=True, force=True)
            submissions_deleted += 1

        student = frappe.get_doc("Student", student_id)
        student.language = None
        student.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "message": {
                "success": True,
                "student_id": student_id,
                "submissions_deleted": submissions_deleted,
                "pe_reset": pe_reset,
            }
        }
    except Exception as err:
        frappe.db.rollback()
        frappe.log_error(
            title="reset_test_student failed",
            message=frappe.get_traceback(),
        )
        return {
            "message": {
                "success": False,
                "error": str(err),
            }
        }


@frappe.whitelist(allow_guest=False)
def get_test_student_by_phone():
    payload = _get_payload()
    raw_phone = payload.get("phone", "")
    phone = _normalize_phone(raw_phone)

    try:
        pe_rows = frappe.get_all(
            "ProgramEnrollment",
            filters={"batch": TEST_BATCH},
            fields=["name", "student", "modified"],
        )
        pe_by_student = {}
        for row in pe_rows:
            existing = pe_by_student.get(row["student"])
            if existing is None or row["modified"] > existing["modified"]:
                pe_by_student[row["student"]] = row

        if not pe_by_student:
            return {
                "message": {
                    "status_code": 200,
                    "success": True,
                    "phone": raw_phone,
                    "matched_student_count": 0,
                    "students": [],
                }
            }

        student_ids = list(pe_by_student.keys())
        students = frappe.get_all(
            "Student",
            filters={"name": ["in", student_ids], "phone": phone},
            fields=["name", "name1", "phone", "language", "status", "grade"],
        )

        results = []
        for s in students:
            pe = pe_by_student.get(s["name"])
            results.append(
                {
                    "student_id": s["name"],
                    "name1": s["name1"],
                    "phone": s["phone"],
                    "language": s.get("language"),
                    "status": s.get("status"),
                    "grade": s.get("grade"),
                    "pe_name": pe["name"] if pe else None,
                    "batch": TEST_BATCH,
                    "last_activity": str(pe["modified"]) if pe else None,
                }
            )

        results.sort(key=lambda r: r["last_activity"] or "", reverse=True)

        return {
            "message": {
                "status_code": 200,
                "success": True,
                "phone": raw_phone,
                "matched_student_count": len(results),
                "students": results,
            }
        }
    except Exception as err:
        frappe.log_error(
            title="get_test_student_by_phone failed",
            message=frappe.get_traceback(),
        )
        return {
            "message": {
                "status_code": 500,
                "success": False,
                "error": str(err),
            }
        }
