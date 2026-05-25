"""Plain-Python tests for weekly rollup math.

Run without bench or a Frappe server:

    python3 -m unittest tap_lms.summer_program.tests.test_weekly_rollup_local -v

Product rule: submission is part of student activity. At week advance,
total_activity_points receives weekly_activity_points + weekly_submission_points.
"""
import unittest

from tap_lms.summer_program.weekly_rollup import calculate_week_advance_rollup


class TestWeeklyRollupLocal(unittest.TestCase):
    def test_activity_and_submission_week_each_count_once(self):
        """Single week: weekly_activity=10, weekly_submission=25.
        After rollup, total_activity += 10+25, total_submission += 25.
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

        self.assertEqual(result["total_activity_points"], 35)
        self.assertEqual(result["total_submission_points"], 25)
        self.assertEqual(result["total_quiz_points"], 0)
        self.assertEqual(result["total_points"], 35)
        self.assertEqual(result["current_streak"], 1)
        self.assertEqual(result["special_gems"], 1)

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

        self.assertEqual(result["total_activity_points"], 45)    # 10 + 10 + 25
        self.assertEqual(result["total_submission_points"], 50)  # 25 + 25
        self.assertEqual(result["total_points"], 70)             # 35 + 10 + 25
        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["special_gems"], 2)

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
