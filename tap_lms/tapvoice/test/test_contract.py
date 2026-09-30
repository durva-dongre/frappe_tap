import json
import os

from frappe.tests.utils import FrappeTestCase

from tap_lms.tapvoice.lib import contract

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "content_hash_vectors.json"
)


class TestContractHashVectors(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(FIXTURE_PATH, encoding="utf-8") as handle:
            cls.vectors = json.load(handle)
        cls.vectors_by_name = {v["name"]: v for v in cls.vectors}

    def test_all_vectors_match(self):
        for vector in self.vectors:
            computed = contract.content_hash(
                vector["text"],
                vector["voice"],
                vector.get("emotion"),
                vector["format"],
                vector["model_revision"],
            )
            self.assertEqual(computed, vector["expected_hash"], vector["name"])

    def test_different_revision_changes_hash(self):
        base = self.vectors_by_name["base"]
        candidates = [
            v
            for v in self.vectors
            if v["text"] == base["text"]
            and v["voice"] == base["voice"]
            and v.get("emotion") == base.get("emotion")
            and v["format"] == base["format"]
            and v["model_revision"] != base["model_revision"]
        ]
        self.assertTrue(candidates, "fixture needs a same-text different-revision vector")
        self.assertNotEqual(base["expected_hash"], candidates[0]["expected_hash"])

    def test_clean_text_parity(self):
        for vector in self.vectors:
            if "raw_text" in vector:
                self.assertEqual(contract.clean_text(vector["raw_text"]), vector["text"])

    def test_url_equality(self):
        vector = self.vectors_by_name["base"]
        expected_key = contract.expected_key(
            vector["text"],
            vector["voice"],
            vector.get("emotion"),
            vector["format"],
            vector["model_revision"],
            "tts",
            vector.get("language", "english"),
        )
        self.assertTrue(expected_key.endswith(f".{vector['format']}"))