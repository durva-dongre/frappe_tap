import csv
import json
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tap_lms.onboarding import student_sheet_registration as registration


class TestStudentSheetCourse(unittest.TestCase):
    def setUp(self):
        self.frappe = self._patch("frappe", MagicMock())
        self.frappe.ValidationError = ValueError
        self.frappe.db.exists.return_value = True
        self.frappe.db.get_value.side_effect = self._get_value
        self.school_enrollment = SimpleNamespace(
            batch_number="BATCH-1", model="MODEL-1", grades_courses={"7": ["Arts"]}
        )
        self._patch("_get_school_id_for_registration", return_value=("SCHOOL-1", ""))
        self._patch(
            "_get_school_enrollment_for_registration",
            return_value=(self.school_enrollment, ""),
        )
        self._patch("_get_glific_model_name", return_value="Test Model")
        self.new_config = next(
            config for config in registration.FIXED_STUDENT_REGISTRATION_SHEETS
            if config["spreadsheet_id"] == registration.COURSE_SOURCE_SPREADSHEET_ID
        )

    def _patch(self, name, *args, **kwargs):
        patcher = patch.object(registration, name, *args, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    @staticmethod
    def _get_value(doctype, filters, field):
        if doctype == "Course Verticals":
            verticals = {"Dance": "CV-DANCE", "Arts": "CV-ARTS"}
            if isinstance(filters, dict):
                return verticals.get(filters["name2"])
            return {value: key for key, value in verticals.items()}.get(filters)
        if doctype == "Batch":
            return "BT00000029"
        return ""

    def _read_sheet(self, config, extra_columns=None):
        cells = {
            "timestamp": "2026-10-07 10:00:00",
            "contact_phone_number": "9876543210",
            "gender": "Female",
            "grade": "7",
            "shall_we_begin": "Agree ✅",
            "student_name": "Test Student",
            **(extra_columns or {}),
            "registration_status": "",
            "process status": "",
        }
        metadata = {
            "properties": {"title": "Registrations"},
            "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "index": 0}}],
        }
        with (
            patch.object(registration, "_sheets_get", return_value=metadata),
            patch.object(
                registration, "_get_sheet_values",
                return_value=[list(cells), list(cells.values())],
            ),
        ):
            return registration._read_source_sheet(None, config, ensure_status_column=False)

    @staticmethod
    def _prepare(sheet):
        return registration._prepare_source_row(sheet.rows[0], sheet, "HI", set(), set())

    def test_sheet_course_reaches_enrollment_without_school_course_mapping(self):
        self.assertEqual(self.new_config["language"], "Hindi")
        self.school_enrollment.grades_courses = None
        sheet = self._read_sheet(self.new_config, {" Course ": " Dance "})
        row = self._prepare(sheet)
        self.assertEqual(row["prepare_status"], "Ready")
        self.assertEqual(row["course"], "Dance")
        self.assertEqual(row["course_vertical"], "CV-DANCE")

        # The prepare/upload job persists rows as JSON between phases.
        row = json.loads(json.dumps(row))
        student = MagicMock()
        student.get.return_value = []
        self._patch("_find_existing_student", return_value=None)
        self._patch("_insert_student", side_effect=lambda doc: doc)
        self.frappe.get_doc.return_value = student
        registration._upsert_student(row, import_user="Administrator")
        self.assertEqual(self.frappe.get_doc.call_args.args[0]["language"], "HI")
        enrollment = student.append.call_args.args[1]
        self.assertEqual(enrollment["vertical"], "CV-DANCE")
        self.assertEqual(enrollment["batch"], "BATCH-1")

    def test_sheet_course_overrides_conflicting_school_mapping(self):
        row = self._prepare(self._read_sheet(self.new_config, {"course": "Dance"}))
        self.assertEqual(row["course_vertical"], "CV-DANCE")
        self.assertEqual(row["course_names"], ["Dance"])

    def test_new_sheet_requires_course_header(self):
        with self.assertRaisesRegex(ValueError, "missing required columns.*course"):
            self._read_sheet(self.new_config)

    def test_blank_or_unknown_course_does_not_fall_back_to_school_mapping(self):
        for course, message in [("  ", "Missing course"), ("Unknown", "Course vertical not found")]:
            with self.subTest(course=course):
                row = self._prepare(self._read_sheet(self.new_config, {"course": course}))
                self.assertEqual(row["prepare_status"], "Error")
                self.assertIn(message, row["message"])

    def test_other_sources_keep_school_mapping_and_do_not_require_course(self):
        for config in registration.FIXED_STUDENT_REGISTRATION_SHEETS:
            if config == self.new_config:
                continue
            with self.subTest(language=config["language"]):
                row = self._prepare(self._read_sheet(config))
                self.assertEqual(row["prepare_status"], "Ready")
                self.assertEqual(row["course_vertical"], "CV-ARTS")
                self.assertEqual(row["course"], "")

    def test_mixed_source_csv_only_exports_new_sheet_course(self):
        rows = []
        for config in registration.FIXED_STUDENT_REGISTRATION_SHEETS:
            row = self._prepare(self._read_sheet(config, {"course": "Dance"}))
            contact = registration._glific_contact_row(row)
            # Exporting blank course must not change collection routing.
            self.assertEqual(contact["collection"], "TLM26_AllStudents_Batch UP")
            rows.append(contact)

        chunks = list(registration._glific_contact_csv_chunks(rows))
        self.assertEqual(len(chunks), 1)
        reader = csv.DictReader(StringIO(chunks[0][1]))
        self.assertEqual(reader.fieldnames.count("course"), 1)
        exported = list(reader)
        for config, contact in zip(registration.FIXED_STUDENT_REGISTRATION_SHEETS, exported):
            expected = "Dance" if config == self.new_config else ""
            self.assertEqual(contact["course"], expected)

    def test_old_prepared_rows_export_blank_course(self):
        contact = registration._glific_contact_row({"course_vertical": "CV-ARTS"})
        self.assertEqual(contact["course"], "")
