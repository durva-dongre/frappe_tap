from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.lib.text import clean_text, prepare, strip_markup


class TestStripMarkup(FrappeTestCase):
    def test_strips_html_tags(self):
        self.assertEqual(strip_markup("<b>Hello</b> world"), "Hello world")

    def test_strips_nested_tags(self):
        self.assertEqual(strip_markup("<div><span>Hi</span> there</div>"), "Hi there")

    def test_collapses_whitespace(self):
        self.assertEqual(strip_markup("a   b\n\nc"), "a b c")


class TestCleanText(FrappeTestCase):
    def test_nfc_normalizes(self):
        self.assertEqual(clean_text("e\u0301"), "\u00e9")

    def test_drops_control_chars(self):
        self.assertEqual(clean_text("a\u200bb"), "ab")

    def test_keeps_tab_and_newline_as_space(self):
        self.assertEqual(clean_text("a\tb\nc"), "a b c")


class TestPrepare(FrappeTestCase):
    def test_truncates_at_sentence_end(self):
        text = "First sentence. Second sentence that pushes well past the limit here."
        prepared, truncated = prepare(text, 20, "truncate")
        self.assertTrue(truncated)
        self.assertTrue(prepared.endswith("."))

    def test_skip_policy_returns_empty(self):
        text = "x" * 400
        prepared, truncated = prepare(text, 300, "skip")
        self.assertEqual(prepared, "")
        self.assertTrue(truncated)

    def test_idempotent_after_truncation(self):
        text = "First sentence. " * 30
        prepared, _ = prepare(text, 300, "truncate")
        reprepared, _ = prepare(prepared, 300, "truncate")
        self.assertEqual(prepared, reprepared)