import frappe
from datetime import date, datetime, timedelta

WINDOW_DAYS = 7
SUBMISSION_XP = 25
SUBMISSION_GEMS = 1

ARCHETYPE_DORMANT = "dormant"
ARCHETYPE_FENCE_SITTER = "fence_sitter"
ARCHETYPE_IRREGULAR_SUBMITTER = "irregular_submitter"
ARCHETYPE_SUBMITTER = "submitter"

DEFAULT_PROGRESS_FIELDS = "xp,streak,submission,version"


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


def _get_learner_row(learner_id):
    row = frappe.db.sql(
        """
        SELECT student_name, language, district, state, school, birthdate, archetype,
               xp, xp_d0, xp_d1, xp_d2, xp_d3, xp_d4, xp_d5, xp_d6, weekly_xp,
               level, streak, longest_streak, last_activity_date,
               submission_gems, submission_index,
               activities_watched_this_week, max_weekly_activities,
               window_start_date, is_bingeing, modified
        FROM "tabTapapp Learner"
        WHERE name=%s LIMIT 1
        """,
        learner_id,
        as_dict=True,
    )
    return row[0] if row else None


def _get_learner_rows_bulk(learner_ids):
    if not learner_ids:
        return {}
    placeholders = ",".join(["%s"] * len(learner_ids))
    rows = frappe.db.sql(
        f"""
        SELECT name, student_name, language, district, state, school, birthdate, archetype,
               xp, xp_d0, xp_d1, xp_d2, xp_d3, xp_d4, xp_d5, xp_d6, weekly_xp,
               level, streak, longest_streak, last_activity_date,
               submission_gems, submission_index,
               activities_watched_this_week, max_weekly_activities,
               window_start_date, is_bingeing, modified
        FROM "tabTapapp Learner"
        WHERE name IN ({placeholders})
        """,
        tuple(learner_ids),
        as_dict=True,
    )
    return {r.name: r for r in rows}


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


def _sync_archetypes_bulk(rows_by_learner, today):
    updates = []
    for learner_id, r in rows_by_learner.items():
        computed = _compute_archetype(
            r.streak or 0, r.submission_index or 0, _parse_date(r.last_activity_date), today
        )
        if computed != r.archetype:
            r.archetype = computed
            updates.append((computed, learner_id))

    if not updates:
        return

    case_parts = []
    ids = []
    for computed, learner_id in updates:
        case_parts.append("WHEN %s THEN %s")
        ids.append(learner_id)
    params = []
    for computed, learner_id in updates:
        params.extend([learner_id, computed])
    placeholders = ",".join(["%s"] * len(ids))
    params.extend(ids)

    frappe.db.sql(
        f"""
        UPDATE "tabTapapp Learner"
           SET archetype = CASE name {' '.join(case_parts)} ELSE archetype END,
               modified = NOW()
         WHERE name IN ({placeholders})
        """,
        tuple(params),
    )


def _roll_window_if_expired(r, today):
    window_start = _parse_date(r.window_start_date)
    watched = r.activities_watched_this_week or 0
    cap = r.max_weekly_activities or 2

    if window_start is None:
        return today, 0, False, True

    if today >= window_start + timedelta(days=WINDOW_DAYS):
        return today, 0, False, True

    return window_start, watched, watched >= cap, False


def _compute_streak(r, window_started_fresh, today):
    if not window_started_fresh:
        return r.streak or 0, r.longest_streak or 0

    old_window_start = _parse_date(r.window_start_date)
    if old_window_start is None:
        new_streak = 1
    else:
        gap_days = (today - old_window_start).days
        new_streak = (r.streak or 0) + 1 if gap_days == WINDOW_DAYS else 1

    new_longest = max(r.longest_streak or 0, new_streak)
    return new_streak, new_longest


def _window_status(r, today=None):
    today = today or _today()
    window_start, watched, is_bingeing, _rolled = _roll_window_if_expired(r, today)
    cap = r.max_weekly_activities or 2
    resets_on = window_start + timedelta(days=WINDOW_DAYS) if window_start else None
    return {
        "activities_watched_this_week": watched,
        "max_weekly_activities": cap,
        "is_bingeing": bool(is_bingeing),
        "window_start_date": str(window_start) if window_start else None,
        "window_resets_on": str(resets_on) if resets_on else None,
        "activities_remaining": max(cap - watched, 0),
    }


_ALL_SECTIONS = {"xp", "streak", "window", "level", "archetype", "submission", "enrollment", "achievements", "version"}


def _build_state_from_row(learner_id, r, wanted, want_all, today, include_achievements, achievements_by_learner=None):
    def _want(section):
        return want_all or section in wanted

    result = {"learner_id": learner_id}

    if _want("profile"):
        result["profile"] = {
            "student_name": r.student_name,
            "language": r.language,
            "district": r.district,
            "state": r.state,
            "school": r.school,
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

    if _want("version"):
        result["version"] = str(r.modified) if getattr(r, "modified", None) else None

    if include_achievements or _want("achievements"):
        if achievements_by_learner is not None:
            result["achievements"] = achievements_by_learner.get(learner_id, [])
        else:
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

    if sync_archetype and (want_all or "archetype" in wanted):
        _sync_archetype(learner_id, r, today)

    return _build_state_from_row(learner_id, r, wanted, want_all, today, include_achievements)


def learner_bulk_state(learner_ids, fields=None, include_achievements=False, sync_archetype=True):
    """Batched equivalent of learner_full_state for many learners at once.

    Returns a dict keyed by learner_id. Unknown/missing learner_ids are
    simply absent from the result (callers use .get(learner_id) and treat
    a missing key the same as None).
    """
    learner_ids = [lid for lid in (learner_ids or []) if lid]
    if not learner_ids:
        return {}

    wanted = _parse_optional(fields)
    want_all = wanted is None
    today = _today()

    rows_by_learner = _get_learner_rows_bulk(learner_ids)
    if not rows_by_learner:
        return {}

    if sync_archetype and (want_all or "archetype" in wanted):
        _sync_archetypes_bulk(rows_by_learner, today)

    achievements_by_learner = None
    if include_achievements or want_all or "achievements" in wanted:
        from tap_lms.tapapp.api.progress.achievements import fetch_achievements_bulk
        achievements_by_learner = fetch_achievements_bulk(list(rows_by_learner.keys()))

    return {
        learner_id: _build_state_from_row(
            learner_id, r, wanted, want_all, today, include_achievements, achievements_by_learner
        )
        for learner_id, r in rows_by_learner.items()
    }


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
def get_learner_progress(learner_id=None, fields=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields") or DEFAULT_PROGRESS_FIELDS

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    state = learner_full_state(learner_id, fields=fields)
    if state is None:
        frappe.throw("Learner not found", frappe.DoesNotExistError)
    return state


@frappe.whitelist(allow_guest=True)
def get_learners_progress(learner_ids=None, fields=None):
    fd = frappe.form_dict
    learner_ids = learner_ids or fd.get("learner_ids")
    fields = fields or fd.get("fields") or DEFAULT_PROGRESS_FIELDS

    if isinstance(learner_ids, str):
        try:
            learner_ids = frappe.parse_json(learner_ids)
        except Exception:
            learner_ids = [x.strip() for x in learner_ids.split(",") if x.strip()]

    if not isinstance(learner_ids, list) or not learner_ids:
        frappe.throw("learner_ids must be a non-empty array", frappe.ValidationError)

    return learner_bulk_state(learner_ids, fields=fields)


def _enroll_course_internal(learner_id, course):
    existing = _get_enrollment_row(learner_id)
    if existing:
        frappe.db.sql(
            """
            UPDATE "tabTapapp Enroll"
               SET course=%s, status='active', modified=NOW()
             WHERE name=%s
            """,
            (course, existing.name),
        )
    else:
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


@frappe.whitelist(allow_guest=True)
def enroll_course(learner_id=None, course=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    _enroll_course_internal(learner_id, course)
    frappe.db.commit()

    return {"enrolled": True, "course": course, **learner_full_state(learner_id, fields="enrollment")}


@frappe.whitelist(allow_guest=True)
def record_activity(learner_id=None, xp=None, activity_type=None, fields=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    xp = xp if xp is not None else fd.get("xp")
    activity_type = activity_type or fd.get("activity_type")
    fields = fields or fd.get("fields") or DEFAULT_PROGRESS_FIELDS

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    xp = int(xp or 10)
    if xp <= 0:
        frappe.throw("xp must be positive", frappe.ValidationError)

    r = _get_learner_row(learner_id)
    if not r:
        frappe.throw("Learner not found", frappe.DoesNotExistError)

    today = _today()
    window_start, watched, is_bingeing, window_started_fresh = _roll_window_if_expired(r, today)

    cap = r.max_weekly_activities or 2
    if watched >= cap:
        frappe.throw(
            f"Weekly activity limit reached ({cap} activities). Try again after the window resets.",
            frappe.ValidationError,
        )

    new_streak, new_longest = _compute_streak(r, window_started_fresh, today)
    new_watched = watched + 1
    new_is_bingeing = new_watched >= cap

    frappe.db.sql(
        """
        UPDATE "tabTapapp Learner"
           SET xp = xp + %s,
               xp_d0 = xp_d0 + %s,
               weekly_xp = weekly_xp + %s,
               last_activity_date = %s,
               window_start_date = %s,
               activities_watched_this_week = %s,
               is_bingeing = %s,
               streak = %s,
               longest_streak = %s,
               modified = NOW()
         WHERE name = %s
        """,
        (
            xp, xp, xp, today, window_start,
            new_watched, 1 if new_is_bingeing else 0,
            new_streak, new_longest,
            learner_id,
        ),
    )
    frappe.db.commit()

    return {
        "activity_recorded": True,
        "activity_type": activity_type,
        "xp_awarded": xp,
        **learner_full_state(learner_id, fields=fields),
    }


@frappe.whitelist(allow_guest=True)
def update_content_progress(
    learner_id=None, video_index=None, quiz_index=None, submission_index=None,
    xp=None, activity_type=None, fields=None,
):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    video_index = video_index if video_index is not None else fd.get("video_index")
    quiz_index = quiz_index if quiz_index is not None else fd.get("quiz_index")
    submission_index = submission_index if submission_index is not None else fd.get("submission_index")
    xp = xp if xp is not None else fd.get("xp")
    activity_type = activity_type or fd.get("activity_type")
    fields = fields or fd.get("fields") or DEFAULT_PROGRESS_FIELDS

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    has_video = video_index is not None
    has_quiz = quiz_index is not None
    has_submission = submission_index is not None
    if not has_video and not has_quiz and not has_submission:
        frappe.throw(
            "At least one of video_index, quiz_index or submission_index is required",
            frappe.ValidationError,
        )

    video_count = int(video_index) if has_video else None
    quiz_count = int(quiz_index) if has_quiz else None
    submission_count = int(submission_index) if has_submission else None

    enrollment = _get_enrollment_row(learner_id)
    if not enrollment:
        frappe.throw("Learner has no active enrollment", frappe.ValidationError)

    r = _get_learner_row(learner_id)
    if not r:
        frappe.throw("Learner not found", frappe.DoesNotExistError)

    today = _today()
    _window_start, watched, _is_bingeing, _fresh = _roll_window_if_expired(r, today)
    cap = r.max_weekly_activities or 2
    if watched >= cap:
        frappe.throw(
            f"Weekly activity limit reached ({cap} activities). Try again after the window resets.",
            frappe.ValidationError,
        )

    current_videos = enrollment.videos_completed or 0
    current_quizzes = enrollment.quizzes_completed or 0
    current_submissions = enrollment.submission_index or 0
    new_videos = max(current_videos, video_count) if has_video else current_videos
    new_quizzes = max(current_quizzes, quiz_count) if has_quiz else current_quizzes
    new_submissions = max(current_submissions, submission_count) if has_submission else current_submissions
    progress_moved = (
        new_videos > current_videos
        or new_quizzes > current_quizzes
        or new_submissions > current_submissions
    )

    if progress_moved:
        frappe.db.sql(
            """
            UPDATE "tabTapapp Enroll"
               SET videos_completed = GREATEST(videos_completed, %s),
                   quizzes_completed = GREATEST(quizzes_completed, %s),
                   submission_index = GREATEST(submission_index, %s),
                   modified = NOW()
             WHERE name = %s
            """,
            (new_videos, new_quizzes, new_submissions, enrollment.name),
        )
        frappe.db.commit()

    if has_submission and new_submissions > current_submissions:
        frappe.db.sql(
            """
            UPDATE "tabTapapp Learner"
               SET submission_gems = submission_gems + %s,
                   submission_index = GREATEST(submission_index, %s),
                   modified = NOW()
             WHERE name = %s
            """,
            (SUBMISSION_GEMS, new_submissions, learner_id),
        )
        frappe.db.commit()

    activity_result = record_activity(learner_id=learner_id, xp=xp, activity_type=activity_type, fields=fields)

    return {
        "updated": progress_moved,
        "videos_completed": new_videos,
        "quizzes_completed": new_quizzes,
        "submission_index": new_submissions,
        **activity_result,
    }


# Alias so the worker's existing route target
# (tap_lms.tapapp.api.progress.learner.submit_progress) resolves without
# needing to change worker/src/routes.js. Frappe's dispatcher does
# getattr(module, "submit_progress"), so this points straight at the
# already-whitelisted update_content_progress function.
submit_progress = update_content_progress


@frappe.whitelist()
def submission_verified_webhook(learner_id=None, submission_index=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    submission_index = submission_index if submission_index is not None else fd.get("submission_index")

    if not learner_id or submission_index is None:
        frappe.throw("learner_id and submission_index are required", frappe.ValidationError)

    submission_index = int(submission_index)

    r = _get_learner_row(learner_id)
    if not r:
        frappe.throw("Learner not found", frappe.DoesNotExistError)

    current_index = r.submission_index or 0

    if submission_index <= current_index:
        return {
            "processed": False,
            "reason": "already_processed",
            "submission_index": current_index,
            "submission_gems": r.submission_gems or 0,
        }

    if submission_index != current_index + 1:
        return {
            "processed": False,
            "reason": "out_of_sequence",
            "expected_submission_index": current_index + 1,
            "submission_index": current_index,
            "submission_gems": r.submission_gems or 0,
        }

    today = _today()

    frappe.db.sql(
        """
        UPDATE "tabTapapp Learner"
           SET xp = xp + %s,
               xp_d0 = xp_d0 + %s,
               weekly_xp = weekly_xp + %s,
               submission_gems = submission_gems + %s,
               submission_index = %s,
               last_activity_date = %s,
               modified = NOW()
         WHERE name = %s
        """,
        (
            SUBMISSION_XP, SUBMISSION_XP, SUBMISSION_XP,
            SUBMISSION_GEMS, submission_index, today,
            learner_id,
        ),
    )

    enrollment = _get_enrollment_row(learner_id)
    if enrollment:
        frappe.db.sql(
            """
            UPDATE "tabTapapp Enroll"
               SET submission_index = GREATEST(submission_index, %s),
                   modified = NOW()
             WHERE name = %s
            """,
            (submission_index, enrollment.name),
        )

    frappe.db.commit()

    return {
        "processed": True,
        "submission_index": submission_index,
        "xp_awarded": SUBMISSION_XP,
        "gems_awarded": SUBMISSION_GEMS,
        **learner_full_state(learner_id, fields="xp,submission,archetype,version"),
    }