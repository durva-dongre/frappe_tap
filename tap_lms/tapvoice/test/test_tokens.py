import time
import unittest

from tap_lms.tapvoice.lib import tokens


class TestTokens(unittest.TestCase):
    def test_valid_roundtrip(self):
        token = tokens.issue("RUN-1", "secret", 10)
        self.assertTrue(tokens.verify("RUN-1", token, "secret"))

    def test_wrong_run_id_fails(self):
        token = tokens.issue("RUN-1", "secret", 10)
        with self.assertRaises(tokens.TokenInvalid):
            tokens.verify("RUN-2", token, "secret")

    def test_wrong_secret_fails(self):
        token = tokens.issue("RUN-1", "secret", 10)
        with self.assertRaises(tokens.TokenInvalid):
            tokens.verify("RUN-1", token, "rotated-secret")

    def test_tampered_signature_fails(self):
        token = tokens.issue("RUN-1", "secret", 10)
        expiry, _, signature = token.partition(".")
        tampered = f"{expiry}.{'0' * len(signature)}"
        with self.assertRaises(tokens.TokenInvalid):
            tokens.verify("RUN-1", tampered, "secret")

    def test_malformed_token_fails(self):
        with self.assertRaises(tokens.TokenInvalid):
            tokens.verify("RUN-1", "not-a-token", "secret")
        with self.assertRaises(tokens.TokenInvalid):
            tokens.verify("RUN-1", "", "secret")

    def test_expired_token_fails(self):
        token = tokens.issue("RUN-1", "secret", 0)
        time.sleep(1.1)
        with self.assertRaises(tokens.TokenInvalid):
            tokens.verify("RUN-1", token, "secret")
