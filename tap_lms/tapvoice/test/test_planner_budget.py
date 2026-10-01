import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.constants import DECISION_DEPLOY, DECISION_SKIP_BELOW_MINIMUM, DECISION_SKIP_BUDGET
from tap_lms.tapvoice.lib import planner as planner_lib
from tap_lms.tapvoice.lib.settings import load as load_settings


class TestPlanner(FrappeTestCase):
    def setUp(self):
        self._created = []

    def tearDown(self):
        for name in self._created:
            frappe.delete_doc("Submission", name, force=True, ignore_permissions=True)
        frappe.db.commit()

    def _make_submission(self, age_hours=1):
        doc = frappe.get_doc(
            {
                "doctype": "Submission",
                "status": "Completed",
                "overall_feedback_translated": "Good feedback for testing purposes here.",
                "translation_language": "english",
                "audio_feedback_url": "",
            }
        )
        doc.insert(ignore_permissions=True)
        if age_hours:
            backdated = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-age_hours)
            frappe.db.set_value("Submission", doc.name, "creation", backdated, update_modified=False)
        frappe.db.commit()
        self._created.append(doc.name)
        return doc

    def _settings(self, **overrides):
        settings = load_settings()
        settings.window_hours = 72
        settings.max_cost_per_run_usd = 100
        settings.max_cost_per_day_usd = 100
        settings.max_cost_per_month_usd = 1000
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def _plan(self, settings, force=False):
        return planner_lib.plan_batch(settings, force=force, only_names=list(self._created))

    def test_below_minimum_skips(self):
        self._make_submission()
        settings = self._settings(min_items_to_deploy=50, run_interval_hours=12, urgent_margin_hours=1)
        plan = self._plan(settings)
        self.assertEqual(plan.decision, DECISION_SKIP_BELOW_MINIMUM)

    def test_urgent_item_forces_deploy_even_below_minimum(self):
        self._make_submission(age_hours=50)
        settings = self._settings(
            min_items_to_deploy=50,
            window_hours=72,
            run_interval_hours=12,
            urgent_margin_hours=1,
        )
        plan = self._plan(settings)
        self.assertEqual(plan.decision, DECISION_DEPLOY)
        self.assertGreaterEqual(plan.urgent_count, 1)

    def test_budget_exhausted_skips(self):
        for _ in range(3):
            self._make_submission()
        settings = self._settings(
            min_items_to_deploy=1,
            max_cost_per_run_usd=0.0,
            max_cost_per_day_usd=0.0,
            max_cost_per_month_usd=0.0,
        )
        plan = self._plan(settings)
        self.assertEqual(plan.decision, DECISION_SKIP_BUDGET)

    def test_preview_matches_deploy_decision(self):
        for _ in range(3):
            self._make_submission()
        settings = self._settings(min_items_to_deploy=1)
        plan_a = self._plan(settings)
        plan_b = self._plan(settings)
        self.assertEqual(plan_a.decision, plan_b.decision)
        self.assertEqual(len(plan_a.items), len(plan_b.items))

    def test_trimming_respects_run_cap(self):
        for _ in range(5):
            self._make_submission()
        settings = self._settings(
            min_items_to_deploy=1,
            max_clips_per_run=2,
            max_cost_per_run_usd=1000,
            max_cost_per_day_usd=1000,
            max_cost_per_month_usd=10000,
        )
        plan = self._plan(settings)
        self.assertLessEqual(len(plan.items), 2)