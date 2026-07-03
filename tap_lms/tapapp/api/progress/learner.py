import frappe
from datetime import date, datetime, timedelta
from tap_lms.ca_api.progress.achievements import _fetch_achievements_sql

# ---------------------------------------------------------------------------
# Citizenship / Tapapp Academy — progress engine
#
# Tapapp Learner fields actually used here (nothing invented):
#   xp, last_activity_xp, level, streak, longest_streak, last_activity_date,
#   activities_watched_this_week, max_weekly_activities, window_start_date,
#   is_bingeing, enrollments (Tapapp Enroll), achievements (Tapapp Learner
#   Achievements)
#
# There is no weekly_xp / xp_d0..d6 field on this doctype, so points are
# tracked as a single cumulative `xp` value (per your explicit decision).
# The "weekly" concept only governs the binge-lock window and the streak,
# per the field descriptions already written into the doctype json:
#   - window_start_date: set on first activity in a window
#   - window rolls forward only once today >= window_start_date + 7 days
#   - streak increments when the new window immediately follows the last one
# ---------------------------------------------------------------------------

WINDOW_DAYS = 7


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


# --- window / streak / binge-lock core -----------------------------------

def _get_learner_window_row(learner_id):
    row = frappe.db.sql(
        """
        SELECT xp, last_activity_xp, level, streak, longest_streak,
               last_activity_date, activities_watched_this_week,
               max_weekly_activities, window_start_date, is_bingeing
        FROM "tabTapapp Learner"
        WHERE name=%s LIMIT 1
        """,
        learner_id,
        as_dict=True,
    )
    return row[0] if row else None


def _roll_window_if_expired(r, today):
    """
    Given the current row values and today's date, returns the window state
    that should apply *before* recording a new activity:
      (window_start_date, activities_watched_this_week, is_bingeing, window_started_fresh)

    window_started_fresh is True whenever this activity begins a brand new
    window — either because the learner has never had one, or because the
    old one expired. It does NOT mean the window is necessarily the very
    next consecutive one (that distinction, for streak purposes, is made
    separately in _compute_streak using the old window_start_date).
    """
    window_start = _parse_date(r.window_start_date)
    watched = r.activities_watched_this_week or 0
    cap = r.max_weekly_activities or 2

    if window_start is None:
        # No window ever started yet — this activity starts the first one.
        return today, 0, False, True

    if today >= window_start + timedelta(days=WINDOW_DAYS):
        # Window has expired -> roll forward to a fresh window starting today.
        return today, 0, False, True

    # Still inside current window.
    return window_start, watched, watched >= cap, False


def _compute_streak(r, window_started_fresh):
    """
    Streak increments whenever a new window starts fresh AND it is the
    window immediately following the previous one (the gap between the old
    window_start_date and today is exactly WINDOW_DAYS). A learner's very
    first-ever activity (old window_start_date is None) also counts as
    starting a streak of 1. Any larger gap resets streak to 1. If we're
    still inside the same window (no fresh start), streak is unchanged.
    """
    if not window_started_fresh:
        return r.streak or 0, r.longest_streak or 0

    old_window_start = _parse_date(r.window_start_date)
    if old_window_start is None:
        new_streak = 1
    else:
        gap_days = (_today() - old_window_start).days
        new_streak = (r.streak or 0) + 1 if gap_days == WINDOW_DAYS else 1

    new_longest = max(r.longest_streak or 0, new_streak)
    return new_streak, new_longest


@frappe.whitelist(allow_guest=True)
def record_activity(learner_id=None, xp=None, activity_type=None):
    """
    Records one activity (video/quiz/etc) for a learner:
      - enforces the 2-per-week (rolling, per-student) binge lock — HARD BLOCK
      - awards xp (cumulative)
      - updates streak per the weekly-window rule
      - returns full updated learner state in the same response

    xp defaults to 10 if not supplied.
    """
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    xp = xp if xp is not None else fd.get("xp")
    activity_type = activity_type or fd.get("activity_type")

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    xp = int(xp or 10)
    if xp <= 0:
        frappe.throw("xp must be positive", frappe.ValidationError)

    r = _get_learner_window_row(learner_id)
    if not r:
        frappe.throw("Learner not found", frappe.DoesNotExistError)

    today = _today()
    window_start, watched, is_bingeing, window_started_fresh = _roll_window_if_expired(r, today)

    # HARD BLOCK: if the student has already hit their cap for the
    # window that applies right now (after any due rollover), reject
    # before writing anything. A freshly-started window always has
    # watched=0, so this only fires for a still-open window at/over cap,
    # or the defensive edge case of max_weekly_activities being set to 0.
    cap = r.max_weekly_activities or 2
    if watched >= cap:
        frappe.throw(
            f"Weekly activity limit reached ({cap} activities). Try again after the window resets.",
            frappe.ValidationError,
        )

    new_streak, new_longest = _compute_streak(r, window_started_fresh)

    new_watched = watched + 1
    new_is_bingeing = new_watched >= cap

    frappe.db.sql(
        """
        UPDATE "tabTapapp Learner"
           SET xp = xp + %s,
               last_activity_xp = %s,
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
            xp, xp, today, window_start,
            new_watched, 1 if new_is_bingeing else 0,
            new_streak, new_longest,
            learner_id,
        ),
    )
    frappe.db.commit()

    return {"activity_recorded": True, "activity_type": activity_type, "xp_awarded": xp, **_learner_full_state(learner_id)}


def _window_status(r, today=None):
    """Read-only projection of what the window would look like right now,
    without writing anything — used by GET-style state calls."""
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


# --- flexible full-state builder ------------------------------------------

_ALL_SECTIONS = {"xp", "streak", "window", "level", "enrollments", "achievements"}


def _learner_full_state(learner_id: str, fields=None, include_enrollments=False, page=1, page_size=20) -> dict:
    """
    One helper backing every state-returning endpoint. `fields` is an
    optional comma-separated subset of: xp, streak, window, level,
    enrollments, achievements. Omit it to get everything except
    enrollments/achievements (those stay opt-in since they're child-table
    reads); pass include_enrollments=1 or fields=...,enrollments to include.
    """
    wanted = _parse_optional(fields)
    want_all = wanted is None

    def _want(section):
        return want_all or section in wanted

    row = frappe.db.sql(
        """
        SELECT student_name, language, district, state, school, birthdate,
               xp, last_activity_xp, level, streak, longest_streak,
               last_activity_date, activities_watched_this_week,
               max_weekly_activities, window_start_date, is_bingeing
        FROM "tabTapapp Learner"
        WHERE name=%s LIMIT 1
        """,
        learner_id,
        as_dict=True,
    )
    if not row:
        return {}
    r = row[0]

    result = {}

    if _want("xp"):
        result["xp"] = r.xp or 0
        result["last_activity_xp"] = r.last_activity_xp or 0
        result["last_activity_date"] = str(r.last_activity_date) if r.last_activity_date else None

    if _want("level"):
        result["level"] = r.level or "Level 1"

    if _want("streak"):
        result["streak"] = r.streak or 0
        result["longest_streak"] = r.longest_streak or 0

    if _want("window"):
        result.update(_window_status(r))

    if include_enrollments or (wanted is not None and "enrollments" in wanted):
        enrollments, has_more = _fetch_enrollments_sql(learner_id, page=page, page_size=page_size)
        result["enrollments"] = enrollments
        result["enrollments_has_more"] = has_more

    if wanted is not None and "achievements" in wanted:
        result["achievements"] = _fetch_achievements_sql(learner_id)

    return result


@frappe.whitelist(allow_guest=True)
def get_learner_state(learner_id=None, fields=None, include_enrollments=None, page=None, page_size=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    fields = fields or fd.get("fields")
    include_enrollments = include_enrollments if include_enrollments is not None else fd.get("include_enrollments")
    page = int(page or fd.get("page", 1))
    page_size = min(int(page_size or fd.get("page_size", 20)), 100)

    if not learner_id:
        frappe.throw("learner_id is required", frappe.ValidationError)

    inc = str(include_enrollments).lower() in ("true", "1", "yes") if include_enrollments else False
    return _learner_full_state(learner_id, fields=fields, include_enrollments=inc, page=page, page_size=page_size)


# --- enrollments (Tapapp Enroll child table) -------------------------------
# Multi-enrollment is fully supported (it's just child-table rows). The
# API defaults to single-current-course usage via `is_current_course`,
# but nothing stops a caller from enrolling in several without switching
# the current flag, if that flexibility is ever needed.

def _fetch_enrollments_sql(learner_id, page=1, page_size=20):
    offset = (page - 1) * page_size
    rows = frappe.db.sql(
        """
        SELECT course, enrolled_on, status, is_current_course,
               videos_completed, quizzes_completed
        FROM "tabTapapp Enroll"
        WHERE parent=%s
        ORDER BY is_current_course DESC, enrolled_on DESC
        LIMIT %s OFFSET %s
        """,
        (learner_id, page_size + 1, offset),
        as_dict=True,
    )
    has_more = len(rows) > page_size
    enrollments = [
        {
            "course": r.course,
            "status": r.status,
            "is_current_course": bool(r.is_current_course),
            "videos_completed": r.videos_completed or 0,
            "quizzes_completed": r.quizzes_completed or 0,
            "enrolled_on": str(r.enrolled_on) if r.enrolled_on else None,
        }
        for r in rows[:page_size]
    ]
    return enrollments, has_more


def _get_enrollment_row(learner_id: str, course: str):
    rows = frappe.db.sql(
        """
        SELECT name, videos_completed, quizzes_completed, status, enrolled_on, is_current_course
        FROM "tabTapapp Enroll"
        WHERE parent=%s AND course=%s
        LIMIT 1
        """,
        (learner_id, course),
        as_dict=True,
    )
    return rows[0] if rows else None


@frappe.whitelist(allow_guest=True)
def enroll_course(learner_id=None, course=None, make_current=None, fields=None):
    """
    Enrolls a learner in a course. By default (make_current not passed, or
    truthy) this becomes the student's single "current" course — matching
    the single-focus usage pattern — and any other course's
    is_current_course flag is cleared. Pass make_current=0 to add a course
    without disturbing the current one, enabling multi-enrollment when
    that flexibility is actually needed.
    """
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")
    make_current = make_current if make_current is not None else fd.get("make_current", True)
    fields = fields or fd.get("fields")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    make_current_flag = str(make_current).lower() in ("true", "1", "yes")

    existing = _get_enrollment_row(learner_id, course)
    if not existing:
        frappe.db.sql(
            """
            INSERT INTO "tabTapapp Enroll"
                (name, parent, parenttype, parentfield,
                 course, enrolled_on, status, is_current_course,
                 videos_completed, quizzes_completed,
                 creation, modified, modified_by, owner, idx)
            VALUES
                (%s, %s, 'Tapapp Learner', 'enrollments',
                 %s, CURRENT_DATE, 'active', %s,
                 0, 0,
                 NOW(), NOW(), 'Administrator', 'Administrator',
                 COALESCE((SELECT MAX(idx) FROM "tabTapapp Enroll" WHERE parent=%s), 0) + 1)
            """,
            (frappe.generate_hash(length=10), learner_id, course, 1 if make_current_flag else 0, learner_id),
        )

    if make_current_flag:
        frappe.db.sql(
            'UPDATE "tabTapapp Enroll" SET is_current_course=0, modified=NOW() WHERE parent=%s AND course != %s',
            (learner_id, course),
        )
        frappe.db.sql(
            'UPDATE "tabTapapp Enroll" SET is_current_course=1, status=\'active\', modified=NOW() WHERE parent=%s AND course=%s',
            (learner_id, course),
        )

    frappe.db.commit()
    return {"enrolled": True, "course": course, "is_current_course": make_current_flag, **_learner_full_state(learner_id, fields=fields)}


@frappe.whitelist(allow_guest=True)
def switch_current_course(learner_id=None, course=None):
    """Switches which already-enrolled course is 'current' without creating
    a new enrollment or losing progress on the others."""
    learner_id = learner_id or frappe.form_dict.get("learner_id")
    course = course or frappe.form_dict.get("course")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    if not _get_enrollment_row(learner_id, course):
        frappe.throw("Learner is not enrolled in this course", frappe.ValidationError)

    frappe.db.sql('UPDATE "tabTapapp Enroll" SET is_current_course=0, modified=NOW() WHERE parent=%s', (learner_id,))
    frappe.db.sql(
        'UPDATE "tabTapapp Enroll" SET is_current_course=1, modified=NOW() WHERE parent=%s AND course=%s',
        (learner_id, course),
    )
    frappe.db.commit()
    return {"success": True, "current_course": course}


@frappe.whitelist(allow_guest=True)
def get_course_progress(learner_id=None, course=None, fields=None):
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")
    fields = fields or fd.get("fields")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    enrollment = _get_enrollment_row(learner_id, course)
    result = {
        "course": course,
        "videos_completed": enrollment.videos_completed if enrollment else 0,
        "quizzes_completed": enrollment.quizzes_completed if enrollment else 0,
        "status": enrollment.status if enrollment else None,
        "is_current_course": bool(enrollment.is_current_course) if enrollment else False,
        "enrolled_on": str(enrollment.enrolled_on) if enrollment and enrollment.enrolled_on else None,
    }
    result.update(_learner_full_state(learner_id, fields=fields))
    return result


@frappe.whitelist(allow_guest=True)
def update_content_progress(
    learner_id=None, course=None, video_index=None,
    quiz_index=None, xp=None, activity_type=None, fields=None,
):
    """
    Updates video/quiz completion counters for a course AND records the
    activity (binge-lock + streak + xp) in one call, so a single request
    covers both course progress and gamification state.
    """
    fd = frappe.form_dict
    learner_id = learner_id or fd.get("learner_id")
    course = course or fd.get("course")
    video_index = video_index if video_index is not None else fd.get("video_index")
    quiz_index = quiz_index if quiz_index is not None else fd.get("quiz_index")
    xp = xp if xp is not None else fd.get("xp")
    activity_type = activity_type or fd.get("activity_type")
    fields = fields or fd.get("fields")

    if not learner_id or not course:
        frappe.throw("learner_id and course are required", frappe.ValidationError)

    has_video = video_index is not None
    has_quiz = quiz_index is not None
    if not has_video and not has_quiz:
        frappe.throw("At least one of video_index or quiz_index is required", frappe.ValidationError)

    video_count = int(video_index) if has_video else None
    quiz_count = int(quiz_index) if has_quiz else None

    enrollment = _get_enrollment_row(learner_id, course)
    if not enrollment:
        frappe.throw("Learner is not enrolled in this course", frappe.ValidationError)

    # Check the binge lock BEFORE writing anything, so a blocked request
    # never advances video/quiz counters either — the whole call is
    # all-or-nothing rather than leaving progress saved with no XP.
    r = _get_learner_window_row(learner_id)
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
    new_videos = max(current_videos, video_count) if has_video else current_videos
    new_quizzes = max(current_quizzes, quiz_count) if has_quiz else current_quizzes
    progress_moved = new_videos > current_videos or new_quizzes > current_quizzes

    if progress_moved:
        frappe.db.sql(
            """
            UPDATE "tabTapapp Enroll"
               SET videos_completed  = GREATEST(videos_completed, %s),
                   quizzes_completed = GREATEST(quizzes_completed, %s),
                   modified          = NOW()
             WHERE name = %s
            """,
            (new_videos, new_quizzes, enrollment.name),
        )
        frappe.db.commit()

    # record_activity re-validates the lock (harmless — window state hasn't
    # changed since the check above within this single request) and does
    # the actual xp/streak write + commit.
    activity_result = record_activity(learner_id=learner_id, xp=xp, activity_type=activity_type)

    return {
        "updated": progress_moved,
        "videos_completed": new_videos,
        "quizzes_completed": new_quizzes,
        **activity_result,
    }