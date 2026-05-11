"""
Tests for summer_program.utils.

Covers:
  - get_student_display_name — must read Student.name1 (canonical) and
    gracefully handle missing fields, dict inputs, and empty values.
    Regression test for the silent-empty-string bug where code read
    `student.student_name` (a non-existent field on the Student doctype)
    and silently pushed "" to Glific, breaking @contact.student_name
    personalization in WhatsApp messages.
"""
import unittest
from unittest.mock import MagicMock

from tap_lms.summer_program.utils import get_student_display_name


class TestGetStudentDisplayName(unittest.TestCase):
    """G1 regression coverage."""

    def test_reads_name1_when_present(self):
        """Canonical: Student doctype has field `name1` (label 'Name')."""
        student = MagicMock()
        student.name1 = "Rahul Kumar"
        student.student_name = None
        student.first_name = None
        self.assertEqual(get_student_display_name(student), "Rahul Kumar")

    def test_falls_back_to_student_name_if_doctype_ever_adds_it(self):
        """Future-proof: if Student doctype later adds student_name, use it as
        a secondary read so we don't have to touch this helper again."""
        student = MagicMock()
        student.name1 = None
        student.student_name = "Priya Singh"
        student.first_name = None
        self.assertEqual(get_student_display_name(student), "Priya Singh")

    def test_falls_back_to_first_name(self):
        """Legacy paths sometimes only populate first_name."""
        student = MagicMock()
        student.name1 = None
        student.student_name = None
        student.first_name = "Anjali"
        self.assertEqual(get_student_display_name(student), "Anjali")

    def test_returns_empty_string_when_all_fields_missing(self):
        """Defensive: no display name available → empty string, not None
        (Glific expects strings; None would serialize wrong)."""
        student = MagicMock()
        student.name1 = None
        student.student_name = None
        student.first_name = None
        self.assertEqual(get_student_display_name(student), "")

    def test_returns_empty_string_for_none_input(self):
        """Defensive: caller passes None (e.g., student lookup failed)."""
        self.assertEqual(get_student_display_name(None), "")

    def test_strips_whitespace(self):
        """CSV imports sometimes leave trailing whitespace."""
        student = MagicMock()
        student.name1 = "  Vikram Mehta  "
        student.student_name = None
        student.first_name = None
        self.assertEqual(get_student_display_name(student), "Vikram Mehta")

    def test_works_with_dict_input(self):
        """Helper should accept dicts too (used in fixture loaders + tests)."""
        student = {"name1": "Aisha Patel"}
        self.assertEqual(get_student_display_name(student), "Aisha Patel")

    def test_dict_input_with_no_name_keys(self):
        """Empty dict → empty string, no KeyError."""
        self.assertEqual(get_student_display_name({}), "")

    def test_priority_order_name1_wins_over_student_name(self):
        """When both are set (transition period), name1 wins because that's
        the canonical doctype field."""
        student = MagicMock()
        student.name1 = "Canonical Name"
        student.student_name = "Stale Name"
        student.first_name = "Other"
        self.assertEqual(get_student_display_name(student), "Canonical Name")

    def test_empty_string_field_falls_through(self):
        """`name1=""` should fall through to the next field rather than
        return "" prematurely. Otherwise a CSV with blank Name column would
        kill all downstream personalization."""
        student = MagicMock()
        student.name1 = ""
        student.student_name = "Backup Name"
        student.first_name = None
        self.assertEqual(get_student_display_name(student), "Backup Name")


if __name__ == "__main__":
    unittest.main()
