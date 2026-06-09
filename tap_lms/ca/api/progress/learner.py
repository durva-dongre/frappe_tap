import frappe
import json
from datetime import date, datetime

MAX_XP_PER_CALL = 25
XP_QUEUE_KEY = "ca:xp_queue"
XP_QUEUE_MAX_SIZE = 500000
XP_FLUSH_LOCK_KEY = "ca:xp_flush:running"
XP_FLUSH_LOCK_TTL = 60


def _today():
    return date.today()


def _parse_date(d):
    if not d:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _parse_optional(fields_param):
    if not fields_param:
        return None
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


def _learner_xp_state(learner_id: str, include_daily: bool = False) -> dict:
    base_cols = "xp, weekly_xp, streak, longest_streak, level, last_activity_date"
    daily_cols = ", xp_d0, xp_d1, xp_d2, xp_d3, xp_d4, xp_d5, xp_d6"
    cols = base_cols + (daily_cols if include_daily else "")

    row = frappe.db.sql(
        f'SELECT {cols} FROM "tabCitizenship Learner" WHERE name=%s LIMIT 1',
        learner_id,
        as_dict=True,
    )
    if not row:
        return {}

    r = row[0]
    result = {
        "xp": r.xp or 0,
        "weekly_xp": r.weekly_xp or 0,
        "streak": r.streak or 0,
        "longest_streak": r.longest_streak or 0,
        "level": r.level or "Level 1",
        "last_activity_date": str(r.last_activity_date) if r.last_activity_date else None,
    }

    if include_daily:
        daily = [r.xp_d0 or 0, r.xp_d1 or 0, r.xp_d2 or 0,
                 r.xp_d3 or 0, r.xp_d4 or 0, r.xp_d5 or 0, r.xp_d6 or 0]
        result["xp_daily"] = daily
        result["xp_today"] = daily[0]
        result["xp_peak_day"] = max(daily)
        result["active_days"] = sum(1 for v in daily if v > 0)

    return result


def _update_streak(learner_id: str):
    frappe.db.sql(
        """
        UPDATE "tabCitizenship Learner"
           SET streak = CASE
                            WHEN last_activity_date = CURRENT_DATE - INTERVAL '1 day'
                            THEN streak + 1
                            ELSE 1
                        END,
               longest_streak = GREATEST(
                                    longest_streak,
                                    CASE
                                        WHEN last_activity_date = CURRENT_DATE - INTERVAL '1 day'
                                        THEN streak + 1
                                        ELSE 1
                                    END
                                ),
               last_activity_date = CURRENT_DATE
         WHERE name = %s
           AND (last_activity_date IS NULL OR last_activity_date < CURRENT_DATE)
        """,
        (learner_id,),
    )
    frappe.db.commit()


def _queue_xp(learner_id: str, xp: int):
    cache = frappe.cache()
    if (cache.llen(XP_QUEUE_KEY) or 0) < XP_QUEUE_MAX_SIZE:
        cache.rpush(XP_QUEUE_KEY, json.dumps({"learner_id": learner_id, "xp": xp}))
    else:
        frappe.log_error(title="XP Queue Full", message=f"Dropped xp={xp} for learner={learner_id}")


def flush_xp_queue():
    cache = frappe.cache()

    acquired = cache.set_value(XP_FLUSH_LOCK_KEY, "1", expires_in_sec=XP_FLUSH_LOCK_TTL, nx=True)
    if not acquired:
        return

    try:
        raw_items = cache.lrange(XP_QUEUE_KEY, 0, -1)
        if not raw_items:
            return
        cache.delete(XP_QUEUE_KEY)

        totals: dict[str, int] = {}
        for item in raw_items:
            try:
                entry = json.loads(item)
                lid = entry["learner_id"]
                totals[lid] = totals.get(lid, 0) + entry["xp"]
            except Exception:
                continue

        for learner_id, xp in totals.items():
            frappe.db.sql(
                """
                UPDATE "tabCitizenship Learner"
                   SET xp        = xp + %s,
                       xp_d0     = xp_d0 + %s,
                       -- PostgreSQL evaluates all RHS expressions against the pre-update row values.
                       -- xp_d0 here is the OLD value. (old_xp_d0 + delta) + xp_d1 + ... is correct.
                       -- Do not change this to xp_d0 alone — that would drop the delta.
                       weekly_xp = (xp_d0 + %s) + xp_d1 + xp_d2 + xp_d3 + xp_d4 + xp_d5 + xp_d6,
                       modified  = NOW()
                 WHERE name = %s
                """,
                (xp, xp, xp, learner_id),
            )
        frappe.db.commit()
    finally:
        cache.delete_value(XP_FLUSH_LOCK_KEY)


@frappe.whitelist(allow_guest=True)
def get_learner_state(learner_id=None, fields=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    optional = _parse_optional(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    result = {}
    want_daily = _want("xp_daily")

    if want_all or _want("xp") or want_daily:
        result.update(_learner_xp_state(learner_id, include_daily=want_daily))

    if _want("enrollments"):
        page = int(fd.get("page", 1))
        page_size = min(int(fd.get("page_size", 20)), 100)
        offset = (page - 1) * page_size
        rows = frappe.db.sql(
            """
            SELECT course, status, videos_completed, quizzes_completed, enrolled_on
            FROM "tabCitizenship Enrollment"
            WHERE parent=%s
            ORDER BY enrolled_on DESC
            LIMIT %s OFFSET %s
            """,
            (learner_id, page_size + 1, offset),
            as_dict=True,
        )
        has_more = len(rows) > page_size
        result["enrollments"] = [
            {
                "course": r.course,
                "status": r.status,
                "videos_completed": r.videos_completed or 0,
                "quizzes_completed": r.quizzes_completed or 0,
                "enrolled_on": str(r.enrolled_on) if r.enrolled_on else None,
            }
            for r in rows[:page_size]
        ]
        result["enrollments_has_more"] = has_more

    if not result:
        result.update(_learner_xp_state(learner_id, include_daily=False))

    return result


@frappe.whitelist(allow_guest=True)
def enroll_course(learner_id=None, course=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    frappe.db.sql(
        """
        INSERT INTO "tabCitizenship Enrollment"
            (name, parent, parenttype, parentfield,
             course, enrolled_on, status,
             videos_completed, quizzes_completed,
             creation, modified, modified_by, owner)
        VALUES
            (%s, %s, 'Citizenship Learner', 'enrollments',
             %s, CURRENT_DATE, 'active',
             0, 0,
             NOW(), NOW(), 'Administrator', 'Administrator')
        ON CONFLICT (parent, course) DO NOTHING
        """,
        (frappe.generate_hash(length=10), learner_id, course),
    )
    frappe.db.commit()
    return {"enrolled": True, "course": course}


@frappe.whitelist(allow_guest=True)
def add_xp_and_streak(learner_id=None, xp=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    xp = xp if xp is not None else fd.get("xp")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    xp = min(int(xp or 10), MAX_XP_PER_CALL)
    if xp <= 0:
        frappe.throw("xp must be positive", frappe.ValidationError)

    _update_streak(learner_id)
    _queue_xp(learner_id, xp)

    return {**_learner_xp_state(learner_id), "queued_xp": xp}