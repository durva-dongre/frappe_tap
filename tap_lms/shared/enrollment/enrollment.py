from __future__ import annotations

import frappe

from shared.db_retry import run_sql_one, with_serialization_retry
from shared.errors import ValidationFailed

ALLOWED_TRANSITIONS = {
    "default": frozenset({"active", "dropped"}),
    "active": frozenset({"paused", "no_activity", "completed", "dropped", "manual"}),
    "paused": frozenset({"active", "dropped"}),
    "no_activity": frozenset({"active", "dropped"}),
    "completed": frozenset({"manual"}),
    "dropped": frozenset({"active"}),
    "manual": frozenset({"active", "dropped"}),
}

VALID_ACTIVITY_TYPES = ("video", "submission", "quiz")

STAGE_IMPLIES_STATUS = {
    "manually_dropped": "dropped",
    "reengagement_exhausted": "dropped",
    "delivery_failure": "no_activity",
}


@with_serialization_retry
def create_enrollment(student_id: str, batch: str, course_level: str) -> dict:
    name = frappe.generate_hash(length=10)
    rows = frappe.db.sql(
        """
        WITH existing AS (
            SELECT name FROM "tabProgramEnrollment"
             WHERE student = %(student_id)s AND batch = %(batch)s
               AND course_level = %(course_level)s AND status != 'dropped'
             LIMIT 1
        ),
        inserted AS (
            INSERT INTO "tabProgramEnrollment"
                (name, student, batch, course_level, status, creation, modified, owner, modified_by)
            SELECT %(name)s, %(student_id)s, %(batch)s, %(course_level)s, 'default',
                   now(), now(), %(owner)s, %(owner)s
             WHERE NOT EXISTS (SELECT 1 FROM existing)
            RETURNING name
        )
        SELECT COALESCE((SELECT name FROM inserted), (SELECT name FROM existing)) AS enrollment_name,
               EXISTS(SELECT 1 FROM existing) AS already_existed
        """,
        {"student_id": student_id, "batch": batch, "course_level": course_level,
         "name": name, "owner": frappe.session.user},
        as_dict=True,
    )
    frappe.db.commit()
    result = rows[0]
    return {"enrollment_name": result["enrollment_name"], "already_existed": result["already_existed"]}


@with_serialization_retry
def touch_activity(enrollment_name: str, activity_type: str | None = None) -> None:
    if activity_type not in VALID_ACTIVITY_TYPES:
        activity_type = None
    frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET last_activity_type = COALESCE(%(activity_type)s, last_activity_type),
               last_activity_at = now(),
               stage = CASE WHEN stage = 'no_response' THEN NULL ELSE stage END,
               modified = now()
         WHERE name = %(enrollment)s
        """,
        {"enrollment": enrollment_name, "activity_type": activity_type},
    )
    frappe.db.commit()


@with_serialization_retry
def transition(enrollment_name: str, new_status: str) -> None:
    current = run_sql_one(
        """SELECT status FROM "tabProgramEnrollment" WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name},
    )
    if not current:
        raise ValidationFailed("enrollment not found", error_code="enrollment_not_found")
    allowed = ALLOWED_TRANSITIONS.get(current["status"], frozenset())
    if new_status not in allowed:
        raise ValidationFailed(
            f"cannot transition from {current['status']} to {new_status}",
            error_code="invalid_transition",
        )
    frappe.db.sql(
        """UPDATE "tabProgramEnrollment" SET status = %(new_status)s, modified = now() WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name, "new_status": new_status},
    )
    frappe.db.commit()


@with_serialization_retry
def apply_stage(enrollment_name: str, new_stage: str) -> None:
    frappe.db.sql(
        """UPDATE "tabProgramEnrollment" SET stage = %(stage)s, modified = now() WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name, "stage": new_stage},
    )
    frappe.db.commit()

    implied_status = STAGE_IMPLIES_STATUS.get(new_stage)
    if not implied_status:
        return
    current = run_sql_one(
        """SELECT status FROM "tabProgramEnrollment" WHERE name = %(enrollment)s""",
        {"enrollment": enrollment_name},
    )
    if current and implied_status in ALLOWED_TRANSITIONS.get(current["status"], frozenset()):
        transition(enrollment_name, implied_status)


@with_serialization_retry
def bump_points_and_activity(enrollment_name: str, points_delta: int = 0, activity_delta: int = 0) -> dict:
    """Direct, synchronous bump - replaces the old Redis-queue enqueue_points.
    No queue anywhere in the TapApp path."""
    rows = frappe.db.sql(
        """
        UPDATE "tabProgramEnrollment"
           SET points = COALESCE(points, 0) + %(points_delta)s,
               activity_this_week = COALESCE(activity_this_week, 0) + %(activity_delta)s,
               modified = now()
         WHERE name = %(enrollment)s
        RETURNING points, activity_this_week
        """,
        {"enrollment": enrollment_name, "points_delta": points_delta, "activity_delta": activity_delta},
        as_dict=True,
    )
    frappe.db.commit()
    if not rows:
        raise ValidationFailed("enrollment not found", error_code="enrollment_not_found")
    return {"points": rows[0]["points"], "activity_this_week": rows[0]["activity_this_week"]}