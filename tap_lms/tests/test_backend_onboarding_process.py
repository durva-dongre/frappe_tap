import unittest
from tap_lms import backend_onboarding_process


class TestBackendOnboardingProcess(unittest.TestCase):

    def test_normalize_phone_number_valid_10_digit(self):
        phone_12, phone_10 = backend_onboarding_process.normalize_phone_number("9876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")

    def test_normalize_phone_number_valid_12_digit(self):
        phone_12, phone_10 = backend_onboarding_process.normalize_phone_number("919876543210")
        self.assertEqual(phone_12, "919876543210")
        self.assertEqual(phone_10, "9876543210")

    def test_normalize_phone_number_invalid(self):
        phone_12, phone_10 = backend_onboarding_process.normalize_phone_number("123")
        self.assertIsNone(phone_12)
        self.assertIsNone(phone_10)

    def test_find_existing_student_by_phone_and_name_none(self):
        result = backend_onboarding_process.find_existing_student_by_phone_and_name(None, None)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
