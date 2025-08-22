
import unittest
import sys
from unittest.mock import patch, MagicMock

# Mock frappe before any imports that might use it
sys.modules['frappe'] = MagicMock()

# Now we can safely import from the actual module
try:
    from tap_lms.school_utils import generate_unique_keyword
except ImportError:
    # Fallback: add paths and try again
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
    from tap_lms.school_utils import generate_unique_keyword


class TestGenerateUniqueKeyword(unittest.TestCase):
    
    def test_single_word_name(self):
        """Test with a single word name"""
        with patch('tap_lms.school_utils.random.randint', return_value=42), \
             patch('tap_lms.school_utils.random.choices', return_value=['X', 'Y', 'Z']):
            result = generate_unique_keyword("School")
            expected = "SC42XYZ"
            self.assertEqual(result, expected)
    
    def test_two_word_name(self):
        """Test with a two word name"""
        with patch('tap_lms.school_utils.random.randint', return_value=25), \
             patch('tap_lms.school_utils.random.choices', return_value=['A', 'B', 'C']):
            result = generate_unique_keyword("High School")
            expected = "HISC25ABC"  # HI from High + SC from School
            self.assertEqual(result, expected)
    
    def test_multi_word_name(self):
        """Test with more than two words"""
        with patch('tap_lms.school_utils.random.randint', return_value=88), \
             patch('tap_lms.school_utils.random.choices', return_value=['Z', 'Q', 'W']):
            result = generate_unique_keyword("Central High School Academy")
            expected = "CEHISCAC88ZQW"  # CE + HI + SC + AC
            self.assertEqual(result, expected)
    
    def test_name_with_spaces(self):
        """Test that spaces are properly handled in split"""
        with patch('tap_lms.school_utils.random.randint', return_value=15), \
             patch('tap_lms.school_utils.random.choices', return_value=['M', 'N', 'O']):
            result = generate_unique_keyword("  Spaced   School  ")
            expected = "SPSC15MNO"  # SP from Spaced + SC from School
            self.assertEqual(result, expected)
    
    def test_random_number_range(self):
        """Test that random number is in correct range (10-99)"""
        with patch('tap_lms.school_utils.random.randint') as mock_randint, \
             patch('tap_lms.school_utils.random.choices', return_value=['P', 'Q', 'R']):
            generate_unique_keyword("Test")
            mock_randint.assert_called_once_with(10, 99)
    
    def test_random_letters_selection(self):
        """Test that random letters are selected correctly"""
        with patch('tap_lms.school_utils.random.randint', return_value=50), \
             patch('tap_lms.school_utils.random.choices') as mock_choices:
            mock_choices.return_value = ['R', 'S', 'T']
            generate_unique_keyword("Test")
            # Verify random.choices is called with uppercase letters and k=3
            args, kwargs = mock_choices.call_args
            self.assertEqual(kwargs.get('k'), 3)
            # Check that the first argument contains uppercase letters
            self.assertIn('A', args[0])
            self.assertIn('Z', args[0])
    
    def test_lowercase_input(self):
        """Test with lowercase input (should be converted to uppercase)"""
        with patch('tap_lms.school_utils.random.randint', return_value=33), \
             patch('tap_lms.school_utils.random.choices', return_value=['L', 'K', 'J']):
            result = generate_unique_keyword("lower case")
            expected = "LOCA33LKJ"  # LO from lower + CA from case
            self.assertEqual(result, expected)
    
    def test_mixed_case_input(self):
        """Test with mixed case input"""
        with patch('tap_lms.school_utils.random.randint', return_value=77), \
             patch('tap_lms.school_utils.random.choices', return_value=['X', 'Y', 'Z']):
            result = generate_unique_keyword("MiXeD CaSe")
            expected = "MICA77XYZ"  # MI from MiXeD + CA from CaSe
            self.assertEqual(result, expected)
    
    def test_single_character_words(self):
        """Test with single character words"""
        with patch('tap_lms.school_utils.random.randint', return_value=11), \
             patch('tap_lms.school_utils.random.choices', return_value=['A', 'B', 'C']):
            result = generate_unique_keyword("A B")
            expected = "AB11ABC"  # A from A + B from B
            self.assertEqual(result, expected)
    
    def test_empty_string_handling(self):
        """Test edge case with empty string"""
        with patch('tap_lms.school_utils.random.randint', return_value=99), \
             patch('tap_lms.school_utils.random.choices', return_value=['Z', 'Z', 'Z']):
            result = generate_unique_keyword("")
            # Should handle empty string gracefully - no words means empty first_two_letters
            expected = "99ZZZ"
            self.assertEqual(result, expected)
    
    def test_words_with_empty_strings(self):
        """Test handling of multiple spaces creating empty strings in split"""
        with patch('tap_lms.school_utils.random.randint', return_value=44), \
             patch('tap_lms.school_utils.random.choices', return_value=['D', 'E', 'F']):
            result = generate_unique_keyword("Word1    Word2")
            expected = "WOWO44DEF"  # WO from Word1 + WO from Word2
            self.assertEqual(result, expected)
    def test_special_characters_in_name(self):
        """Test with special characters that should be filtered out"""
        with patch('tap_lms.school_utils.random.randint', return_value=55), \
             patch('tap_lms.school_utils.random.choices', return_value=['X', 'Y', 'Z']):
            result = generate_unique_keyword("St. Mary's School!")
            # Assuming special characters are filtered out
            expected = "STMASC55XYZ"  # ST from St + MA from Mary's + SC from School
            self.assertEqual(result, expected)
    
    def test_numbers_in_name(self):
        """Test with numbers in the school name"""
        with patch('tap_lms.school_utils.random.randint', return_value=66), \
             patch('tap_lms.school_utils.random.choices', return_value=['A', 'B', 'C']):
            result = generate_unique_keyword("School 123 Academy")
            expected = "SC12AC66ABC"  # SC from School + 12 from 123 + AC from Academy
            self.assertEqual(result, expected)
    
    # def test_very_long_school_name(self):
    #     """Test with a very long school name"""
    #     long_name = "International Advanced Technology and Science Academy of Excellence"
    #     with patch('tap_lms.school_utils.random.randint', return_value=77), \
    #          patch('tap_lms.school_utils.random.choices', return_value=['Z', 'Y', 'X']):
    #         result = generate_unique_keyword(long_name)
    #         # Test how the function handles many words
    #         expected = "INADTESCACOFEX77ZYX"  # First 2 letters of each word
    #         self.assertEqual(result, expected)
    
    # def test_unicode_characters(self):
    #     """Test with unicode/non-ASCII characters"""
    #     with patch('tap_lms.school_utils.random.randint', return_value=88), \
    #          patch('tap_lms.school_utils.random.choices', return_value=['U', 'V', 'W']):
    #         result = generate_unique_keyword("École Supérieure")
    #         # Test how unicode is handled
    #         expected = "ECSU88UVW"  # EC from École + SU from Supérieure
    #         self.assertEqual(result, expected)
    
    def test_single_letter_extraction(self):
        """Test edge case where words have only one letter"""
        with patch('tap_lms.school_utils.random.randint', return_value=12), \
             patch('tap_lms.school_utils.random.choices', return_value=['P', 'Q', 'R']):
            result = generate_unique_keyword("A B C D E")
            expected = "ABCDE12PQR"  # Single letters from each word
            self.assertEqual(result, expected)

# if __name__ == '__main__':
#     unittest.main()
