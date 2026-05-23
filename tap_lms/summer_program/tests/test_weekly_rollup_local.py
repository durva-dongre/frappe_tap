"""Plain-Python tests for weekly rollup math.

Run without bench or a Frappe server:

    python3 -m unittest tap_lms.summer_program.tests.test_weekly_rollup_local -v

Updated 2026-05-23 (task #77): expected values corrected after removing
the double-count of weekly_submission_points into total_activity_points.
Previously each weekly_submission contributed to BOTH total_activity AND
total_submission; now it contributes only to total_submission. The bug
was discovered via a production diagnostic against palv2-test-BT52231
(ST00051359 showed total_activity=35, total_submission=25, total_points=36
→ stream_sum 61 ≠ total_points 36).
"""
import unittest

from tap_lms.summer_program.weekly_rollup import calculate_week_advance_rollup


class TestWeeklyRollupLocal(unittest.TestCase):
    """Pin the invariant:
        total_activity_points + total_quiz_points + total_submission_points
        + bonus_quiz_points (if pushed to total)
        == total_points
    """

    def test_activity_and_submission_week_each_count_once(self):
        """Single week: weekly_activity=10, weekly_submission=25.
        After rollup, total_activity += 10 (NOT 10+25), total_submission += 25.
        total_points += full sum (10 + 25 + 0 + 0 = 35)."""
        result = calculate_week_advance_rollup({
            "total_activity_points": 0,
            "total_submission_points": 0,
            "total_quiz_points": 0,
            "total_points": 0,
            "weekly_activity_points": 10,
            "weekly_submission_points": 25,
            "weekly_quiz_points": 0,
            "bonus_quiz_points": 0,
            "current_streak": 1,
            "special_gems": 1,
            "weekly_video_done": 1,
            "weekly_submission_done": 1,
        })

        self.assertEqual(result["total_activity_points"], 10,
                         "activity total gets ONLY weekly_activity, not "
                         "weekly_activity + weekly_submission (task #77 fix)")
        self.assertEqual(result["total_submission_points"], 25)
        self.assertEqual(result["total_quiz_points"], 0)
        self.assertEqual(result["total_points"], 35)
        self.assertEqual(result["current_streak"], 1)
        self.assertEqual(result["special_gems"], 1)
        # Invariant
        self.assertEqual(
            result["total_activity_points"] + result["total_quiz_points"]
            + result["total_submission_points"],
            result["total_points"],
            "stream sum must equal total_points (no double-count)",
        )

    def test_activity_only_week_adds_to_existing_activity_total(self):
        """Second week with activity only (no submission this week)."""
        result = calculate_week_advance_rollup({
            "total_activity_points": 10,
            "total_submission_points": 25,
            "total_quiz_points": 0,
            "total_points": 35,
            "weekly_activity_points": 10,
            "weekly_submission_points": 0,
            "weekly_quiz_points": 0,
            "bonus_quiz_points": 0,
            "current_streak": 2,
            "special_gems": 2,
            "weekly_video_done": 1,
            "weekly_submission_done": 0,
        })

        self.assertEqual(result["total_activity_points"], 20)   # 10 + 10
        self.assertEqual(result["total_submission_points"], 25)  # unchanged
        self.assertEqual(result["total_points"], 45)             # 35 + 10
        # Penalty branch: weekly_video_done=1, weekly_submission_done=0
        self.assertEqual(result["current_streak"], 0)
        self.assertEqual(result["special_gems"], 1)
        # Invariant
        self.assertEqual(
            result["total_activity_points"] + result["total_quiz_points"]
            + result["total_submission_points"],
            result["total_points"],
        )

    def test_activity_and_submission_week_adds_both_to_existing_totals(self):
        """Second week with both activity AND submission."""
        result = calculate_week_advance_rollup({
            "total_activity_points": 10,
            "total_submission_points": 25,
            "total_quiz_points": 0,
            "total_points": 35,
            "weekly_activity_points": 10,
            "weekly_submission_points": 25,
            "weekly_quiz_points": 0,
            "bonus_quiz_points": 0,
            "current_streak": 2,
            "special_gems": 2,
            "weekly_video_done": 1,
            "weekly_submission_done": 1,
        })

        self.assertEqual(result["total_activity_points"], 20)    # 10 + 10
        self.assertEqual(result["total_submission_points"], 50)  # 25 + 25
        self.assertEqual(result["total_points"], 70)             # 35 + 10 + 25
        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["special_gems"], 2)
        # Invariant
        self.assertEqual(
            result["total_activity_points"] + result["total_quiz_points"]
            + result["total_submission_points"],
            result["total_points"],
        )

    def test_quiz_and_bonus_roll_into_total_points(self):
        """Quiz week + bonus points. total_points includes both."""
        result = calculate_week_advance_rollup({
            "total_activity_points": 20,
            "total_submission_points": 50,
            "total_quiz_points": 2,
            "total_points": 72,
            "weekly_activity_points": 0,
            "weekly_submission_points": 0,
            "weekly_quiz_points": 8,
            "bonus_quiz_points": 3,
            "current_streak": 2,
            "special_gems": 2,
            "weekly_video_done": 0,
            "weekly_submission_done": 0,
        })

        self.assertEqual(result["total_activity_points"], 20)   # unchanged
        self.assertEqual(result["total_submission_points"], 50)  # unchanged
        self.assertEqual(result["total_quiz_points"], 10)        # 2 + 8
        self.assertEqual(result["total_points"], 83)             # 72 + 8 + 3
        # weekly_video_done=0 → no penalty branch
        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["special_gems"], 2)
        # NOTE: bonus_quiz_points is included in total_points but isn't in
        # any of the three stream totals — so the strict
        # stream_sum == total_points invariant only holds when
        # bonus_quiz_points = 0. With bonus=3 added in this case, total_points
        # exceeds the stream sum by exactly the bonus.
        self.assertEqual(
            result["total_activity_points"] + result["total_quiz_points"]
            + result["total_submission_points"] + 3,   # + bonus_quiz contributed
            result["total_points"],
        )

    def test_zero_week_no_op(self):
        """Empty week (no activity, no submission, no quiz, no bonus).
        Streak/gem penalty branch doesn't fire because weekly_video_done=0."""
        result = calculate_week_advance_rollup({
            "total_activity_points": 100,
            "total_submission_points": 50,
            "total_quiz_points": 25,
            "total_points": 175,
            "weekly_activity_points": 0,
            "weekly_submission_points": 0,
            "weekly_quiz_points": 0,
            "bonus_quiz_points": 0,
            "current_streak": 3,
            "special_gems": 4,
            "weekly_video_done": 0,
            "weekly_submission_done": 0,
        })
        self.assertEqual(result["total_activity_points"], 100)
        self.assertEqual(result["total_submission_points"], 50)
        self.assertEqual(result["total_quiz_points"], 25)
        self.assertEqual(result["total_points"], 175)
        self.assertEqual(result["current_streak"], 3)
        self.assertEqual(result["special_gems"], 4)

    def test_penalty_branch_floors_gems_at_zero(self):
        """Gems can't go negative even if penalty fires when gems=0."""
        result = calculate_week_advance_rollup({
            "total_activity_points": 10,
            "total_submission_points": 0,
            "total_quiz_points": 0,
            "total_points": 10,
            "weekly_activity_points": 0,
            "weekly_submission_points": 0,
            "weekly_quiz_points": 0,
            "bonus_quiz_points": 0,
            "current_streak": 0,
            "special_gems": 0,
            "weekly_video_done": 1,
            "weekly_submission_done": 0,
        })
        self.assertEqual(result["current_streak"], 0)
        self.assertEqual(result["special_gems"], 0,
                         "gems must floor at 0, never go negative")


if __name__ == "__main__":
    unittest.main()
