import frappe
import json
from datetime import date, datetime

MAX_XP_PER_CALL = 25
XP_QUEUE_KEY = "ca:xp_queue"
XP_QUEUE_MAX_SIZE = 500000


def _today():
    return date.today()


def _parse_date(d):
    if not d:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _get_learner_name(student_id: str):
    return frappe.db.get_value("Citizenship Learner", {"student": student_id}, "name")


def _get_or_create_learner(student_id: str) -> str:
    name = _get_learner_name(student_id)
    if name:
        return name
    try:
        doc = frappe.new_doc("Citizenship Learner")
        doc.student = student_id
        doc.xp = 0
        doc.xp_d0 = 0
        doc.xp_d1 = 0
        doc.xp_d2 = 0
        doc.xp_d3 = 0
        doc.xp_d4 = 0
        doc.xp_d5 = 0
        doc.xp_d6 = 0
        doc.weekly_xp = 0
        doc.streak = 0
        doc.longest_streak = 0
        doc.level = 1
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name
    except frappe.exceptions.DuplicateEntryError:
        frappe.db.rollback()
        return _get_learner_name(student_id)


def _learner_xp_state(student_id: str, include_daily: bool = False) -> dict:
    base_fields = ["xp", "weekly_xp", "streak", "longest_streak", "level", "last_activity_date"]
    daily_fields = ["xp_d0", "xp_d1", "xp_d2", "xp_d3", "xp_d4", "xp_d5", "xp_d6"]
    fetch_fields = base_fields + daily_fields if include_daily else base_fields

    row = frappe.db.get_value(
        "Citizenship Learner",
        {"student": student_id},
        fetch_fields,
        as_dict=True,
    )
    if not row:
        return {}

    result = {
        "xp": row.xp or 0,
        "weekly_xp": row.weekly_xp or 0,
        "streak": row.streak or 0,
        "longest_streak": row.longest_streak or 0,
        "level": row.level or 1,
        "last_activity_date": str(row.last_activity_date) if row.last_activity_date else None,
    }

    if include_daily:
        daily = [row.xp_d0 or 0, row.xp_d1 or 0, row.xp_d2 or 0,
                 row.xp_d3 or 0, row.xp_d4 or 0, row.xp_d5 or 0, row.xp_d6 or 0]
        result["xp_daily"] = daily
        result["xp_today"] = daily[0]
        result["xp_peak_day"] = max(daily)
        result["active_days"] = sum(1 for v in daily if v > 0)

    return result


def _update_streak(learner_name: str) -> bool:
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
        (learner_name,),
    )
    frappe.db.commit()
    updated_date = _parse_date(
        frappe.db.get_value("Citizenship Learner", learner_name, "last_activity_date")
    )
    return updated_date == _today()


def _queue_xp(student_id: str, xp: int):
    cache = frappe.cache()
    if (cache.llen(XP_QUEUE_KEY) or 0) < XP_QUEUE_MAX_SIZE:
        cache.rpush(XP_QUEUE_KEY, json.dumps({"student_id": student_id, "xp": xp}))
    else:
        frappe.log_error(
            title="XP Queue Full",
            message=f"XP queue exceeded {XP_QUEUE_MAX_SIZE}. Dropped xp={xp} for student={student_id}",
        )


def _bulk_course_meta(course_ids: list) -> dict:
    if not course_ids:
        return {}
    rows = frappe.get_all(
        "Course Level",
        filters={"name": ["in", course_ids]},
        fields=["name", "name1", "level", "stage", "vertical", "color_code", "icon"],
    )
    return {r.name: r for r in rows}


def _bulk_course_translations(course_ids: list, lang) -> dict:
    if not course_ids or not lang or lang.lower() in ("en", "english"):
        return {}
    rows = frappe.get_all(
        "Course_LevelTranslation",
        filters={"parent": ["in", course_ids], "language": lang},
        fields=["parent", "translated_name"],
    )
    return {r.parent: r.translated_name for r in rows}


def flush_xp_queue():
    cache = frappe.cache()
    raw_items = cache.lrange(XP_QUEUE_KEY, 0, -1)
    if not raw_items:
        return
    cache.delete(XP_QUEUE_KEY)

    batch = []
    for item in raw_items:
        try:
            batch.append(json.loads(item))
        except Exception:
            continue

    if not batch:
        return

    totals: dict[str, int] = {}
    for entry in batch:
        sid = entry["student_id"]
        totals[sid] = totals.get(sid, 0) + entry["xp"]

    for student_id, xp in totals.items():
        name = _get_learner_name(student_id)
        if not name:
            continue
        frappe.db.sql(
            """
            UPDATE "tabCitizenship Learner"
               SET xp        = xp + %s,
                   xp_d0     = xp_d0 + %s,
                   weekly_xp = (xp_d0 + %s) + xp_d1 + xp_d2 + xp_d3 + xp_d4 + xp_d5 + xp_d6,
                   modified  = NOW()
             WHERE name = %s
            """,
            (xp, xp, xp, name),
        )

    frappe.db.commit()


@frappe.whitelist(allow_guest=True)
def get_learner_state(student_id=None, lang=None, fields=None):
    fd = frappe.form_dict
    student_id = student_id or fd.get("student_id")
    lang       = lang       or fd.get("lang")
    fields     = fields     or fd.get("fields")

    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)

    optional = _parse_optional(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    learner_name = _get_or_create_learner(student_id)
    result = {}

    want_daily = _want("xp_daily")
    if _want("xp") or want_daily:
        result.update(_learner_xp_state(student_id, include_daily=want_daily))

    if _want("enrollments"):
        rows = frappe.get_all(
            "Citizenship Enrollment",
            filters={"parent": learner_name},
            fields=["course", "status", "videos_completed", "quizzes_completed", "enrolled_on"],
            order_by="enrolled_on desc",
        )
        course_ids   = [r.course for r in rows if r.course]
        course_meta  = _bulk_course_meta(course_ids)
        course_trans = _bulk_course_translations(course_ids, lang)

        enrollments = []
        for row in rows:
            meta     = course_meta.get(row.course)
            eng_name = (meta.name1 if meta else None) or row.course
            title    = course_trans.get(row.course) or eng_name
            enrollments.append({
                "course":            row.course,
                "course_title":      title,
                "eng_name":          eng_name,
                "course_level":      meta.level    if meta else None,
                "course_stage":      meta.stage    if meta else None,
                "vertical":          meta.vertical if meta else None,
                "color_code":        meta.color_code if meta else None,
                "icon":              meta.icon     if meta else None,
                "status":            row.status,
                "videos_completed":  row.videos_completed  or 0,
                "quizzes_completed": row.quizzes_completed or 0,
                "enrolled_on":       str(row.enrolled_on) if row.enrolled_on else None,
            })
        result["enrollments"] = enrollments

    if not result:
        result.update(_learner_xp_state(student_id, include_daily=False))

    return result


def _parse_optional(fields_param):
    if not fields_param:
        return None
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


@frappe.whitelist(allow_guest=True)
def add_xp_and_streak(student_id=None, xp=None):
    fd = frappe.form_dict
    student_id = student_id or fd.get("student_id")
    xp         = xp if xp is not None else fd.get("xp")

    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)

    xp = min(int(xp or 10), MAX_XP_PER_CALL)
    if xp <= 0:
        frappe.throw("xp must be positive", frappe.ValidationError)

    learner_name   = _get_or_create_learner(student_id)
    streak_updated = _update_streak(learner_name)
    _queue_xp(student_id, xp)

    return {**_learner_xp_state(student_id), "queued_xp": xp, "streak_updated": streak_updated}


@frappe.whitelist(allow_guest=True)
def enroll_course(student_id=None, course=None, lang=None, fields=None):
    fd = frappe.form_dict
    student_id = student_id or fd.get("student_id")
    course     = course     or fd.get("course")
    lang       = lang       or fd.get("lang")
    fields     = fields     or fd.get("fields")

    if not student_id or not course:
        frappe.throw("student_id and course are required", frappe.ValidationError)

    if not frappe.db.exists("Course Level", course):
        frappe.throw("Course not found", frappe.DoesNotExistError)

    optional = _parse_optional(fields)
    want_all = optional is None

    def _want(f):
        return want_all or f in optional

    learner_name = _get_or_create_learner(student_id)

    existing = frappe.db.sql(
        """
        SELECT name FROM "tabCitizenship Enrollment"
         WHERE parent = %s AND course = %s
         LIMIT 1
        """,
        (learner_name, course),
        as_dict=True,
    )
    if existing:
        result = {"enrolled": False, "reason": "already_enrolled", "course": course}
        if _want("xp"):
            result.update(_learner_xp_state(student_id))
        return result

    try:
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
            (frappe.generate_hash(length=10), learner_name, course),
        )
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        result = {"enrolled": False, "reason": "already_enrolled", "course": course}
        if _want("xp"):
            result.update(_learner_xp_state(student_id))
        return result

    inserted = frappe.db.sql(
        'SELECT name FROM "tabCitizenship Enrollment" WHERE parent=%s AND course=%s LIMIT 1',
        (learner_name, course),
        as_dict=True,
    )
    if not inserted:
        result = {"enrolled": False, "reason": "already_enrolled", "course": course}
        if _want("xp"):
            result.update(_learner_xp_state(student_id))
        return result

    result = {"enrolled": True, "course": course}

    if _want("xp"):
        result.update(_learner_xp_state(student_id))

    if _want("enrollments"):
        rows = frappe.get_all(
            "Citizenship Enrollment",
            filters={"parent": learner_name},
            fields=["course", "status", "videos_completed", "quizzes_completed", "enrolled_on"],
            order_by="enrolled_on desc",
        )
        course_ids   = [r.course for r in rows if r.course]
        course_meta  = _bulk_course_meta(course_ids)
        course_trans = _bulk_course_translations(course_ids, lang)

        enrollments = []
        for row in rows:
            meta     = course_meta.get(row.course)
            eng_name = (meta.name1 if meta else None) or row.course
            title    = course_trans.get(row.course) or eng_name
            enrollments.append({
                "course":            row.course,
                "course_title":      title,
                "eng_name":          eng_name,
                "status":            row.status,
                "videos_completed":  row.videos_completed  or 0,
                "quizzes_completed": row.quizzes_completed or 0,
                "enrolled_on":       str(row.enrolled_on) if row.enrolled_on else None,
            })
        result["enrollments"] = enrollments

    return result


@frappe.whitelist(allow_guest=True)
def get_enrollments(student_id=None, lang=None, fields=None):
    fd = frappe.form_dict
    student_id = student_id or fd.get("student_id")
    lang       = lang       or fd.get("lang")
    fields     = fields     or fd.get("fields")

    if not student_id:
        frappe.throw("student_id is required", frappe.ValidationError)

    return get_learner_state(student_id=student_id, lang=lang, fields="enrollments")