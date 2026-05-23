"""Plain-Python tests for weekly rollup math.

Run without bench or a Frappe server:

    python3 -m unittest tap_lms.summer_program.tests.test_weekly_rollup_local -v
"""
import unittest

from tap_lms.summer_program.weekly_rollup import calculate_week_advance_rollup


class TestWeeklyRollupLocal(unittest.TestCase):
    def test_activity_and_submission_week_rolls_to_activity_total(self):
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
        result = calculate_week_advance_rollup({
            "total_activity_points": 35,
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

        self.assertEqual(result["total_activity_points"], 45)
        self.assertEqual(result["total_submission_points"], 25)
        self.assertEqual(result["total_points"], 45)
        self.assertEqual(result["current_streak"], 0)
        self.assertEqual(result["special_gems"], 1)

    def test_activity_and_submission_week_adds_both_to_existing_activity_total(self):
        result = calculate_week_advance_rollup({
            "total_activity_points": 35,
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

        self.assertEqual(result["total_activity_points"], 70)
        self.assertEqual(result["total_submission_points"], 50)
        self.assertEqual(result["total_points"], 70)
        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["special_gems"], 2)

    def test_quiz_and_bonus_roll_into_total_points(self):
        result = calculate_week_advance_rollup({
            "total_activity_points": 70,
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

        self.assertEqual(result["total_activity_points"], 70)
        self.assertEqual(result["total_quiz_points"], 10)
        self.assertEqual(result["total_points"], 83)
        self.assertEqual(result["current_streak"], 2)
        self.assertEqual(result["special_gems"], 2)


if __name__ == "__main__":
    unittest.main()
