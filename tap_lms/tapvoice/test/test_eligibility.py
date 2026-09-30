import frappe
from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.lib import eligibility
from tap_lms.tapvoice.lib.settings import load as load_settings


class TestEligibility(FrappeTestCase):
    def setUp(self):
        self._created = []

    def tearDown(self):
        for name in self._created:
            frappe.delete_doc("Submission", name, force=True, ignore_permissions=True)
        frappe.db.rollback()

    def _make_submission(self, **kwargs):
        defaults = {
            "doctype": "Submission",
            "status": "Completed",
            "overall_feedback_translated": "This is good feedback for the student.",
            "translation_language": "english",
            "audio_feedback_url": "",
            "result_status": "Success - Original",
            "is_plagiarized": 0,
            "is_ai_generated": 0,
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        self._created.append(doc.name)
        return doc

    def _settings(self, **overrides):
        settings = load_settings()
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_null_status_is_eligible(self):
        doc = self._make_submission(status=None)
        settings = self._settings(window_hours=72)
        result = eligibility.find_eligible(settings, 1000)
        self.assertIn(doc.name, [i.id for i in result.items])

    def test_failed_status_excluded(self):
        doc = self._make_submission(status="Failed")
        settings = self._settings(window_hours=72)
        result = eligibility.find_eligible(settings, 1000)
        self.assertNotIn(doc.name, [i.id for i in result.items])

    def test_whitespace_only_text_excluded(self):
        doc = self._make_submission(overall_feedback_translated="   ")
        settings = self._settings(window_hours=72)
        result = eligibility.find_eligible(settings, 1000)
        self.assertNotIn(doc.name, [i.id for i in result.items])
        self.assertGreaterEqual(result.skipped_empty_text, 1)

    def test_unsupported_language_excluded(self):
        doc = self._make_submission(translation_language="klingon")
        settings = self._settings(window_hours=72)
        result = eligibility.find_eligible(settings, 1000)
        self.assertNotIn(doc.name, [i.id for i in result.items])
        self.assertGreaterEqual(result.skipped_unsupported_language, 1)
        self.assertIn("klingon", result.unsupported_language_values)

    def test_existing_url_excluded(self):
        doc = self._make_submission(audio_feedback_url="https://cdn.example.com/x.ogg")
        settings = self._settings(window_hours=72)
        result = eligibility.find_eligible(settings, 1000)
        self.assertNotIn(doc.name, [i.id for i in result.items])

    def test_flagged_skip_when_enabled(self):
        doc = self._make_submission(result_status="Success - Flagged")
        settings = self._settings(window_hours=72, skip_flagged=1)
        result = eligibility.find_eligible(settings, 1000)
        self.assertNotIn(doc.name, [i.id for i in result.items])
        self.assertGreaterEqual(result.skipped_flagged, 1)

    def test_flagged_included_when_disabled(self):
        doc = self._make_submission(result_status="Success - Flagged")
        settings = self._settings(window_hours=72, skip_flagged=0)
        result = eligibility.find_eligible(settings, 1000)
        self.assertIn(doc.name, [i.id for i in result.items])

    def test_ordering_oldest_first(self):
        first = self._make_submission()
        second = self._make_submission()
        settings = self._settings(window_hours=72)
        result = eligibility.find_eligible(settings, 1000)
        ids = [i.id for i in result.items]
        if first.name in ids and second.name in ids:
            self.assertLess(ids.index(first.name), ids.index(second.name))
