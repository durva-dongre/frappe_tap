import frappe
from datetime import date, datetime, timedelta

WINDOW_DAYS = 7
SUBMISSION_XP = 25
SUBMISSION_GEMS = 1
DEFAULT_ACTIVITY_XP = 10

ARCHETYPE_DORMANT = "dormant"
ARCHETYPE_FENCE_SITTER = "fence_sitter"
ARCHETYPE_IRREGULAR_SUBMITTER = "irregular_submitter"
ARCHETYPE_SUBMITTER = "submitter"


def _today():
    return date.today()


def _parse_date(d):
    if not d:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, datetime):
        return d.date()
    return datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _parse_optional(fields_param):
    if not fields_param:
        return None
    return {f.strip().lower() for f in fields_param.split(",") if f.strip()}


_LEARNER_ROW_COLUMNS = """
    name, student_name, language, district, state, school, birthdate, archetype,
    xp, xp_d0, xp_d1, xp_d2, xp_d3, xp_d4, xp_d5, xp_d6, weekly_xp,
    level, streak, longest_streak, last_activity_date,
    submission_gems, submission_index,
    activities_watched_this_week, max_weekly_activities,
    window_start_date, is_bingeing
"""


def _get_learner_row(learner_id):
    row = frappe.db.sql(
        f'SELECT {_LEARNER_ROW_COLUMNS} FROM "tabTapapp Learner" WHERE name=%s LIMIT 1',
        learner_id,
        as_dict=True,
    )
    return row[0] if row else None


def _get_learner_rows_bulk(learner_ids):
    if not learner_ids:
        return {}
    placeholders = ",".join(["%s"] * len(learner_ids))
    rows = frappe.db.sql(
        f'SELECT {_LEARNER_ROW_COLUMNS} FROM "tabTapapp Learner" WHERE name IN ({placeholders})',
        tuple(learner_ids),
        as_dict=True,
    )
    return {r.name: r for r in rows}


def _get_school_names(school_ids):
    unique_ids = [s for s in dict.fromkeys(school_ids) if s]
    if not unique_ids:
        return {}
    placeholders = ",".join(["%s"] * len(unique_ids))
    rows = frappe.db.sql(
        f'SELECT name, name1 FROM "tabSchool" WHERE name IN ({placeholders})',
        tuple(unique_ids),
        as_dict=True,
    )
    return {r.name: r.name1 for r in rows}


def _compute_archetype(streak, submission_index, last_activity_date, today):
    if not last_activity_date:
        return ARCHETYPE_DORMANT
    days_since_active = (today - last_activity_date).days
    if days_since_active > 21:
        return ARCHETYPE_DORMANT
    if submission_index <= 0:
        return ARCHETYPE_FENCE_SITTER
    if streak >= 2:
        return ARCHETYPE_SUBMITTER
    return ARCHETYPE_IRREGULAR_SUBMITTER


def _sync_archetype(learner_id, r, today):
    computed = _compute_archetype(
        r.streak or 0, r.submission_index or 0, _parse_date(r.last_activity_date), today
    )
    if computed != r.archetype:
        frappe.db.sql(
            'UPDATE "tabTapapp Learner" SET archetype=%s, modified=NOW() WHERE name=%s',
            (computed, learner_id),
        )
        r.archetype = computed
    return computed


def _sync_archetypes_bulk(rows_by_id, today):
    to_update = {}
    for learner_id, r in rows_by_id.items():
        computed = _compute_archetype(
            r.streak or 0, r.submission_index or 0, _parse_date(r.last_activity_date), today
        )
        if computed != r.archetype:
            r.archetype = computed
            to_update.setdefault(computed, []).append(learner_id)

    for archetype, ids in to_update.items():
        placeholders = ",".join(["%s"] * len(ids))
        frappe.db.sql(
            f'UPDATE "tabTapapp Learner" SET archetype=%s, modified=NOW() WHERE name IN ({placeholders})',
            (archetype, *ids),
        )


def _window_view(r, today):
    window_start = _parse_date(r.window_start_date)
    watched = r.activities_watched_this_week or 0
    cap = r.max_weekly_activities or 2

    if window_start is None or today >= window_start + timedelta(days=WINDOW_DAYS):
        return today, 0, False, True

    return window_start, watched, watched >= cap, False


def _window_status(r, today=None):
    today = today or _today()
    window_start, watched, is_bingeing, _rolled = _window_view(r, today)
    cap = r.max_weekly_activities or 2
    resets_on = window_start + timedelta(days=WINDOW_DAYS) if window_start else None
    return {
        "units_completed_this_week": watched,
        "max_weekly_units": cap,
        "is_bingeing": bool(is_bingeing),
        "window_start_date": str(window_start) if window_start else None,
        "window_resets_on": str(resets_on) if resets_on else None,
        "units_remaining": max(cap - watched, 0),
    }


def _build_state_from_row(learner_id, r, wanted, want_all, today, include_achievements, school_names=None):
    def _want(section):
        return want_all or section in wanted

    result = {"learner_id": learner_id}

    if _want("profile"):
        school_names = school_names if school_names is not None else _get_school_names([r.school])
        result["profile"] = {
            "student_name": r.student_name,
            "language": r.language,
            "district": r.district,
            "state": r.state,
            "school_id": r.school,
            "school_name": school_names.get(r.school),
            "birthdate": str(r.birthdate) if r.birthdate else None,
        }

    if _want("xp"):
        result["xp"] = r.xp or 0
        result["weekly_xp"] = r.weekly_xp or 0
        result["xp_daily"] = [
            r.xp_d0 or 0, r.xp_d1 or 0, r.xp_d2 or 0, r.xp_d3 or 0,
            r.xp_d4 or 0, r.xp_d5 or 0, r.xp_d6 or 0,
        ]

    if _want("level"):
        result["level"] = r.level or "Level 1"

    if _want("streak"):
        result["streak"] = r.streak or 0
        result["longest_streak"] = r.longest_streak or 0
        result["last_activity_date"] = str(r.last_activity_date) if r.last_activity_date else None

    if _want("window"):
        result.update(_window_status(r, today))

    if _want("archetype"):
        result["archetype"] = r.archetype

    if _want("submission"):
        result["submission_gems"] = r.submission_gems or 0
        result["submission_index"] = r.submission_index or 0

    if include_achievements or _want("achievements"):
        from tap_lms.tapapp.api.progress.achievements import fetch_achievements
        result["achievements"] = fetch_achievements(learner_id)

    if _want("enrollment"):
        result["enrollment"] = _fetch_current_enrollment(learner_id)

    return result


def learner_full_state(learner_id, fields=None, include_achievements=False, sync_archetype=True):
    wanted = _parse_optional(fields)
    want_all = wanted is None

    r = _get_learner_row(learner_id)
    if not r:
        return None

    today = _today()

    if sync_archetype and (want_all or "archetype" in (wanted or set())):
        _sync_archetype(learner_id, r, today)

    return _build_state_from_row(learner_id, r, wanted, want_all, today, include_achievements)


def learner_bulk_state(learner_ids, fields=None, include_achievements=False, sync_archetype=True):
    unique_ids = list(dict.fromkeys(lid for lid in learner_ids if lid))
    if not unique_ids:
        return {}

    wanted = _parse_optional(fields)
    want_all = wanted is None
    today = _today()

    rows_by_id = _get_learner_rows_bulk(unique_ids)

    if sync_archetype and (want_all or "archetype" in (wanted or set())):
        _sync_archetypes_bulk(rows_by_id, today)

    achievements_by_learner = {}
    if include_achievements or want_all or "achievements" in (wanted or set()):
        from tap_lms.tapapp.api.progress.achievements import fetch_achievements_bulk
        achievements_by_learner = fetch_achievements_bulk(unique_ids)

    enrollments_by_learner = {}
    if want_all or "enrollment" in (wanted or set()):
        enrollments_by_learner = _fetch_current_enrollments_bulk(unique_ids)

    school_names = {}
    if want_all or "profile" in (wanted or set()):
        school_names = _get_school_names([r.school for r in rows_by_id.values()])

    states = {}
    for learner_id in unique_ids:
        r = rows_by_id.get(learner_id)
        if not r:
            states[learner_id] = None
            continue
        state = _build_state_from_row(
            learner_id, r, wanted, want_all, today, include_achievements=False, school_names=school_names
        )
        if include_achievements or want_all or "achievements" in (wanted or set()):
            state["achievements"] = achievements_by_learner.get(learner_id, [])
        if want_all or "enrollment" in (wanted or set()):
            state["enrollment"] = enrollments_by_learner.get(learner_id)
        states[learner_id] = state

    return states


def _fetch_current_enrollment(learner_id):
    row = frappe.db.sql(
        """
        SELECT name, course, status, videos_completed, quizzes_completed,
               submission_index, enrolled_on
        FROM "tabTapapp Enroll"
        WHERE parent=%s
        ORDER BY enrolled_on DESC
        LIMIT 1
        """,
        learner_id,
        as_dict=True,
    )
    if not row:
        return None
    e = row[0]
    return {
        "course": e.course,
        "status": e.status,
        "videos_completed": e.videos_completed or 0,
        "quizzes_completed": e.quizzes_completed or 0,
        "submission_index": e.submission_index or 0,
        "enrolled_on": str(e.enrolled_on) if e.enrolled_on else None,
    }


def _fetch_current_enrollments_bulk(learner_ids):
    if not learner_ids:
        return {}
    placeholders = ",".join(["%s"] * len(learner_ids))
    rows = frappe.db.sql(
        f"""
        SELECT DISTINCT ON (parent) parent, course, status, videos_completed,
               quizzes_completed, submission_index, enrolled_on
        FROM "tabTapapp Enroll"
        WHERE parent IN ({placeholders})
        ORDER BY parent, enrolled_on DESC
        """,
        tuple(learner_ids),
        as_dict=True,
    )
    result = {}
    for e in rows:
        result[e.parent] = {
            "course": e.course,
            "status": e.status,
            "videos_completed": e.videos_completed or 0,
            "quizzes_completed": e.quizzes_completed or 0,
            "submission_index": e.submission_index or 0,
            "enrolled_on": str(e.enrolled_on) if e.enrolled_on else None,
        }
    return result


def _get_enrollment_row(learner_id):
    rows = frappe.db.sql(
        """
        SELECT name, course, videos_completed, quizzes_completed,
               submission_index, status, enrolled_on
        FROM "tabTapapp Enroll"
        WHERE parent=%s
        ORDER BY enrolled_on DESC
        LIMIT 1
        """,
        learner_id,
        as_dict=True,
    )
    return rows[0] if rows else None


@frappe.whitelist(allow_guest=True)
def get_learner_state(learner_id=None, fields=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    state = learner_full_state(learner_id, fields=fields)
    if state is None:
        frappe.throw("Learner not found", frappe.DoesNotExistError)
    return state


@frappe.whitelist(allow_guest=True)
def enroll_course(learner_id=None, course=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    frappe.db.sql(
        """
        UPDATE "tabTapapp Enroll"
           SET course=%s, status='active', modified=NOW()
         WHERE parent=%s
        """,
        (course, learner_id),
    )
    if frappe.db.rowcount == 0:
        frappe.db.sql(
            """
            INSERT INTO "tabTapapp Enroll"
                (name, parent, parenttype, parentfield,
                 course, enrolled_on, status,
                 videos_completed, quizzes_completed, submission_index,
                 creation, modified, modified_by, owner, idx)
            VALUES
                (%s, %s, 'Tapapp Learner', 'enrollments',
                 %s, CURRENT_DATE, 'active',
                 0, 0, 0,
                 NOW(), NOW(), 'Administrator', 'Administrator', 1)
            """,
            (frappe.generate_hash(length=10), learner_id, course),
        )
    frappe.db.commit()

    return {"enrolled": True, "course": course, **learner_full_state(learner_id, fields="enrollment")}


@frappe.whitelist(allow_guest=True)
def submit_progress(
    learner_id=None,
    xp=None,
    activity_type=None,
    video_index=None,
    quiz_index=None,
    submission_index=None,
    fields=None,
):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    xp = xp if xp is not None else fd.get("xp")
    activity_type = activity_type or fd.get("activity_type")
    video_index = video_index if video_index is not None else fd.get("video_index")
    quiz_index = quiz_index if quiz_index is not None else fd.get("quiz_index")
    submission_index = submission_index if submission_index is not None else fd.get("submission_index")
    fields = fields or fd.get("fields")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    xp = int(xp) if xp is not None else DEFAULT_ACTIVITY_XP
    if xp < 0:
        frappe.throw("xp cannot be negative", frappe.ValidationError)

    has_video = video_index is not None
    has_quiz = quiz_index is not None
    has_submission = submission_index is not None

    video_count = int(video_index) if has_video else None
    quiz_count = int(quiz_index) if has_quiz else None
    submission_count = int(submission_index) if has_submission else None

    r = _get_learner_row(learner_id)
    if not r:
        frappe.throw("Learner not found", frappe.DoesNotExistError)

    today = _today()
    window_start, watched, is_bingeing, window_started_fresh = _window_view(r, today)
    cap = r.max_weekly_activities or 2

    if watched >= cap:
        frappe.throw(
            f"Weekly unit limit reached ({cap} units). Try again after the window resets.",
            frappe.ValidationError,
        )

    expected_submission_index = r.submission_index or 0
    expected_watched = watched

    submission_processed = False
    submission_reason = None
    if has_submission:
        if submission_count <= expected_submission_index:
            submission_reason = "already_processed"
        elif submission_count != expected_submission_index + 1:
            submission_reason = "out_of_sequence"
        else:
            submission_processed = True

    enrollment = _get_enrollment_row(learner_id)
    if (has_video or has_quiz or submission_processed) and not enrollment:
        frappe.throw("Learner has no active enrollment", frappe.ValidationError)

    if window_started_fresh:
        old_window_start = _parse_date(r.window_start_date)
        if old_window_start is None:
            new_streak = 1
        else:
            gap_days = (today - old_window_start).days
            new_streak = (r.streak or 0) + 1 if gap_days == WINDOW_DAYS else 1
        new_longest = max(r.longest_streak or 0, new_streak)
        new_window_start = today
    else:
        new_streak = r.streak or 0
        new_longest = r.longest_streak or 0
        new_window_start = window_start

    new_watched = expected_watched + 1
    new_is_bingeing = new_watched >= cap

    total_xp = xp + (SUBMISSION_XP if submission_processed else 0)
    submission_gems_delta = SUBMISSION_GEMS if submission_processed else 0
    new_submission_index = submission_count if submission_processed else expected_submission_index

    frappe.db.sql(
        """
        UPDATE "tabTapapp Learner"
           SET xp = xp + %(total_xp)s,
               xp_d0 = xp_d0 + %(total_xp)s,
               weekly_xp = weekly_xp + %(total_xp)s,
               submission_gems = submission_gems + %(gems)s,
               submission_index = %(new_submission_index)s,
               last_activity_date = %(today)s,
               window_start_date = %(new_window_start)s,
               activities_watched_this_week = %(new_watched)s,
               is_bingeing = %(new_is_bingeing)s,
               streak = %(new_streak)s,
               longest_streak = %(new_longest)s,
               modified = NOW()
         WHERE name = %(learner_id)s
           AND submission_index = %(expected_submission_index)s
           AND activities_watched_this_week = %(expected_watched)s
        """,
        {
            "total_xp": total_xp,
            "gems": submission_gems_delta,
            "new_submission_index": new_submission_index,
            "today": today,
            "new_window_start": new_window_start,
            "new_watched": new_watched,
            "new_is_bingeing": 1 if new_is_bingeing else 0,
            "new_streak": new_streak,
            "new_longest": new_longest,
            "learner_id": learner_id,
            "expected_submission_index": expected_submission_index,
            "expected_watched": expected_watched,
        },
    )

    if frappe.db.rowcount == 0:
        frappe.db.rollback()
        return {
            "progress_recorded": False,
            "conflict": True,
            **learner_full_state(learner_id, fields=fields),
        }

    enrollment_updated = False
    if enrollment and (has_video or has_quiz or submission_processed):
        current_videos = enrollment.videos_completed or 0
        current_quizzes = enrollment.quizzes_completed or 0
        current_enroll_submission = enrollment.submission_index or 0

        new_videos = max(current_videos, video_count) if has_video and video_count is not None else current_videos
        new_quizzes = max(current_quizzes, quiz_count) if has_quiz and quiz_count is not None else current_quizzes
        new_enroll_submission = (
            max(current_enroll_submission, new_submission_index)
            if submission_processed
            else current_enroll_submission
        )

        enrollment_updated = (
            new_videos != current_videos
            or new_quizzes != current_quizzes
            or new_enroll_submission != current_enroll_submission
        )

        if enrollment_updated:
            frappe.db.sql(
                """
                UPDATE "tabTapapp Enroll"
                   SET videos_completed = %s,
                       quizzes_completed = %s,
                       submission_index = %s,
                       modified = NOW()
                 WHERE name = %s
                """,
                (new_videos, new_quizzes, new_enroll_submission, enrollment.name),
            )

    frappe.db.commit()

    result = {
        "progress_recorded": True,
        "conflict": False,
        "activity_type": activity_type,
        "xp_awarded": total_xp,
        "submission_processed": submission_processed,
        "gems_awarded": submission_gems_delta,
        "enrollment_updated": enrollment_updated,
    }
    if has_submission and not submission_processed:
        result["submission_reason"] = submission_reason
        result["expected_submission_index"] = expected_submission_index + 1

    return {**result, **learner_full_state(learner_id, fields=fields)}