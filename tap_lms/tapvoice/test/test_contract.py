import json
import os
import unittest

from tap_lms.tapvoice.lib import contract
from tap_lms.tapvoice.lib.text import clean_text

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_vectors():
    with open(os.path.join(FIXTURES_DIR, "content_hash_vectors.json"), encoding="utf-8") as handle:
        return json.load(handle)


class TestContractHashVectors(unittest.TestCase):
    def test_all_vectors_match(self):
        for vector in load_vectors():
            cleaned = clean_text(vector["text"])
            self.assertEqual(cleaned, vector["cleaned_text"])
            actual = contract.content_hash(
                cleaned,
                vector["voice"],
                vector["emotion"],
                vector["format"],
                vector["model_revision"],
            )
            self.assertEqual(actual, vector["expected_hash"])

    def test_different_revision_changes_hash(self):
        vectors = load_vectors()
        same_text_diff_rev = [v for v in vectors if v["text"] == "Same text different revision"]
        base = contract.content_hash("Same text different revision", "English (Female)", None, "ogg", "rev1")
        self.assertNotEqual(base, same_text_diff_rev[0]["expected_hash"])


class TestUrlContract(unittest.TestCase):
    def test_expected_url_shape(self):
        url = contract.expected_url(
            "Hello there",
            "hindi",
            "rev1",
            "tts",
            "https://cdn.example.com",
        )
        self.assertTrue(url.startswith("https://cdn.example.com/tts/hindi/"))
        self.assertTrue(url.endswith(".ogg"))

    def test_url_matches_strict(self):
        url = contract.expected_url("Hi", "english", "rev1", "tts", "https://cdn.example.com")
        self.assertTrue(contract.url_matches(url, url))
        self.assertFalse(contract.url_matches(url + "x", url))
        self.assertFalse(contract.url_matches(None, url))

    def test_hash_matches(self):
        self.assertTrue(contract.hash_matches("abc", "abc"))
        self.assertFalse(contract.hash_matches("abc", "abd"))
        self.assertFalse(contract.hash_matches(None, "abc"))
