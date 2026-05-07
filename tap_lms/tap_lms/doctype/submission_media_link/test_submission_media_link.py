import frappe
import unittest


class TestSubmissionMediaLink(unittest.TestCase):
	def _make_assignment(self):
		if frappe.db.exists("Assignment", "_TEST-ASSIGN"):
			return frappe.get_doc("Assignment", "_TEST-ASSIGN")
		doc = frappe.get_doc(
			{
				"doctype": "Assignment",
				"assignment_id": "_TEST-ASSIGN",
				"assignment_name": "Test Assignment for Media Links",
				"assignment_type": "Practical",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_row(self, media_type, language, url, duration=None):
		return {
			"doctype": "Submission Media Link",
			"media_type": media_type,
			"language": language,
			"url": url,
			"duration": duration or "",
		}

	def test_valid_drive_link(self):
		doc = self._make_assignment()
		doc.append("media_links", self._make_row("Drive", "Hindi", "https://drive.google.com/file/abc"))
		doc.save(ignore_permissions=True)
		saved = frappe.get_doc("Assignment", doc.name)
		self.assertEqual(len(saved.media_links), 1)
		self.assertEqual(saved.media_links[0].media_type, "Drive")
		self.assertEqual(saved.media_links[0].language, "Hindi")

	def test_valid_youtube_link(self):
		doc = self._make_assignment()
		doc.reload()
		doc.append("media_links", self._make_row("YouTube", "Hinglish", "https://www.youtube.com/watch?v=abc123", "5:30"))
		doc.save(ignore_permissions=True)
		saved = frappe.get_doc("Assignment", doc.name)
		youtube_rows = [r for r in saved.media_links if r.media_type == "YouTube"]
		self.assertTrue(len(youtube_rows) >= 1)
		self.assertEqual(youtube_rows[0].duration, "5:30")

	def test_valid_plio_link(self):
		doc = self._make_assignment()
		doc.reload()
		doc.append("media_links", self._make_row("Plio", "Marathi", "https://app.plio.in/play/xyz"))
		doc.save(ignore_permissions=True)
		saved = frappe.get_doc("Assignment", doc.name)
		plio_rows = [r for r in saved.media_links if r.media_type == "Plio"]
		self.assertTrue(len(plio_rows) >= 1)

	def test_valid_canva_link(self):
		doc = self._make_assignment()
		doc.reload()
		doc.append("media_links", self._make_row("Canva", "Punjabi", "https://www.canva.com/design/abc"))
		doc.save(ignore_permissions=True)
		saved = frappe.get_doc("Assignment", doc.name)
		canva_rows = [r for r in saved.media_links if r.media_type == "Canva"]
		self.assertTrue(len(canva_rows) >= 1)

	def test_invalid_url_raises(self):
		doc = self._make_assignment()
		doc.reload()
		doc.append("media_links", self._make_row("Drive", "Hindi", "not-a-valid-url"))
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.save(ignore_permissions=True)

	def test_multiple_languages_same_type(self):
		doc = self._make_assignment()
		doc.reload()
		for lang in ("Hinglish", "Hindi", "Marathi", "Punjabi"):
			doc.append(
				"media_links",
				self._make_row("YouTube", lang, f"https://www.youtube.com/watch?v={lang.lower()}"),
			)
		doc.save(ignore_permissions=True)
		saved = frappe.get_doc("Assignment", doc.name)
		youtube_rows = [r for r in saved.media_links if r.media_type == "YouTube"]
		self.assertEqual(len(youtube_rows), 4)

	def tearDown(self):
		if frappe.db.exists("Assignment", "_TEST-ASSIGN"):
			frappe.delete_doc("Assignment", "_TEST-ASSIGN", ignore_permissions=True, force=True)
		frappe.db.commit()