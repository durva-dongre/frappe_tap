import unittest

from tap_lms.tapvoice.lib.text import clean_text, prepare, strip_markup, truncate_at_boundary


class TestStripMarkup(unittest.TestCase):
    def test_strips_html_tags(self):
        self.assertEqual(strip_markup("<b>Hello</b> world").strip(), "Hello world")

    def test_strips_trailing_angle_word(self):
        result = strip_markup("Great job <happy>")
        self.assertNotIn("<happy>", result)

    def test_strips_markdown_symbols(self):
        self.assertNotIn("*", strip_markup("**bold** text"))
        self.assertNotIn("#", strip_markup("# heading"))


class TestCleanText(unittest.TestCase):
    def test_collapses_whitespace(self):
        self.assertEqual(clean_text("  a\u200b  b\n"), "a b")

    def test_tabs_and_newlines_become_space(self):
        self.assertEqual(clean_text("a\tb\nc"), "a b c")


class TestTruncateAtBoundary(unittest.TestCase):
    def test_truncates_at_sentence_end(self):
        text = "First sentence. Second sentence. Third sentence that is long."
        truncated, was_truncated = truncate_at_boundary(text, 32)
        self.assertTrue(was_truncated)
        self.assertTrue(truncated.endswith("."))

    def test_truncates_at_space_when_no_sentence_end(self):
        text = "one two three four five six seven eight nine ten"
        truncated, was_truncated = truncate_at_boundary(text, 20)
        self.assertTrue(was_truncated)
        self.assertNotIn(" ", truncated[-1:])

    def test_no_truncation_when_within_limit(self):
        text = "short text"
        truncated, was_truncated = truncate_at_boundary(text, 100)
        self.assertEqual(truncated, text)
        self.assertFalse(was_truncated)


class TestPrepare(unittest.TestCase):
    def test_unsupported_language_returns_none(self):
        self.assertIsNone(prepare("Hello", "klingon", 300, "truncate"))

    def test_empty_text_returns_none(self):
        self.assertIsNone(prepare("   ", "english", 300, "truncate"))

    def test_over_length_skip_policy_returns_none(self):
        long_text = "word " * 200
        self.assertIsNone(prepare(long_text, "english", 50, "skip"))

    def test_over_length_truncate_policy_marks_truncated(self):
        long_text = "word " * 200
        result = prepare(long_text, "english", 50, "truncate")
        self.assertIsNotNone(result)
        self.assertTrue(result.truncated)
        self.assertLessEqual(len(result.text), 50)

    def test_idempotent_under_recleaning(self):
        result = prepare("Hello <happy> world!", "english", 300, "truncate")
        self.assertIsNotNone(result)
        second = clean_text(result.text)
        self.assertEqual(second, result.text)

    def test_fingerprint_changes_with_language(self):
        a = prepare("Hello world", "english", 300, "truncate")
        b = prepare("Hello world", "hindi", 300, "truncate")
        self.assertNotEqual(a.fingerprint, b.fingerprint)

    def test_fingerprint_stable_for_same_input(self):
        a = prepare("Hello world", "english", 300, "truncate")
        b = prepare("Hello world", "english", 300, "truncate")
        self.assertEqual(a.fingerprint, b.fingerprint)
