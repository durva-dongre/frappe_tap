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

    Invariant (pinned by test_weekly_rollup_local.test_total_streams_sum_to_total_points):

        total_activity_points + total_quiz_points + total_submission_points
        + bonus_quiz_points_lifetime_if_any  ==  total_points

    Fix 2026-05-23 (task #77): previously this function folded
    `weekly_submission_points` into BOTH `total_activity_points` AND
    `total_submission_points`, breaking the invariant by double-counting.
    Discovered via diagnostic against palv2-test-BT52231 PE h2i6sbirph
    (ST00051359): total_activity_points=35 = weekly_activity(10) +
    weekly_submission(25), total_submission_points=25 (= weekly_submission
    again), total_points=36 — sum of streams (61) overshot total_points
    by exactly weekly_submission. Glific would have shown students inflated
    activity totals = real activity + submission earnings.

    The fix: each total_* column gets ONLY its corresponding weekly_* value.
    `total_points` still gets the full sum of all four streams (activity,
    quiz, submission, bonus_quiz) — that's the only sum-of-everything field
    in the contract.
    """
    weekly_activity = _int_field(pe, "weekly_activity_points")
    weekly_submission = _int_field(pe, "weekly_submission_points")
    weekly_quiz = _int_field(pe, "weekly_quiz_points")
    weekly_bonus_quiz = _int_field(pe, "bonus_quiz_points")

    weekly_total = weekly_activity + weekly_submission + weekly_quiz + weekly_bonus_quiz

    streak_update = _int_field(pe, "current_streak")
    gems_update = _int_field(pe, "special_gems")
    if bool(_field(pe, "weekly_video_done", 0)) and not bool(_field(pe, "weekly_submission_done", 0)):
        streak_update = 0
        gems_update = max(0, gems_update - 1)

    return {
        "current_streak": streak_update,
        "special_gems": gems_update,
        # Each total_* gets ONLY its own weekly_* — no cross-contamination.
        "total_activity_points": _int_field(pe, "total_activity_points") + weekly_activity,
        "total_submission_points": _int_field(pe, "total_submission_points") + weekly_submission,
        "total_quiz_points": _int_field(pe, "total_quiz_points") + weekly_quiz,
        # total_points is the sum-of-everything cumulative counter.
        "total_points": _int_field(pe, "total_points") + weekly_total,
    }
