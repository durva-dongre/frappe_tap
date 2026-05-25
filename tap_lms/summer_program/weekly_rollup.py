"""Pure weekly rollup helpers for Summer Program gamification.

This module intentionally has no Frappe imports so the core points math can be
tested with plain local Python.
"""


def _field(source, name, default=0):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _int_field(source, name):
    return int(_field(source, name, 0) or 0)


def calculate_week_advance_rollup(pe):
    """Return cumulative point/streak/gem updates for week advance.

    Weekly buckets are rolled into cumulative totals, then the caller resets
    those weekly fields on the persisted ProgramEnrollment row.

    Product rule: submissions are part of activity for the student-facing
    activity total, so total_activity_points rolls up both weekly activity and
    weekly submission points. total_submission_points is still maintained as
    its own stream for reporting.
    """
    weekly_activity = _int_field(pe, "weekly_activity_points")
    weekly_submission = _int_field(pe, "weekly_submission_points")
    weekly_quiz = _int_field(pe, "weekly_quiz_points")
    weekly_bonus_quiz = _int_field(pe, "bonus_quiz_points")

    weekly_activity_total = weekly_activity + weekly_submission
    weekly_total = weekly_activity_total + weekly_quiz + weekly_bonus_quiz

    streak_update = _int_field(pe, "current_streak")
    gems_update = _int_field(pe, "special_gems")
    if bool(_field(pe, "weekly_video_done", 0)) and not bool(_field(pe, "weekly_submission_done", 0)):
        streak_update = 0
        gems_update = max(0, gems_update - 1)

    return {
        "current_streak": streak_update,
        "special_gems": gems_update,
        "total_activity_points": _int_field(pe, "total_activity_points") + weekly_activity_total,
        "total_submission_points": _int_field(pe, "total_submission_points") + weekly_submission,
        "total_quiz_points": _int_field(pe, "total_quiz_points") + weekly_quiz,
        # total_points is the sum-of-everything cumulative counter.
        "total_points": _int_field(pe, "total_points") + weekly_total,
    }
