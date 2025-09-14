

import pytest
import os
import csv
import tempfile
import shutil
import sys
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path

# Mock frappe module before importing phone_checker
sys.modules['frappe'] = MagicMock()

# Now import the functions to test
from ..utils.phone_checker import norm_last10, check_missing_phones


class TestNormLast10:
    """Test cases for norm_last10 function"""
    
    def test_normal_phone_number(self):
        """Test with regular phone number"""
        assert norm_last10("1234567890") == "1234567890"
        assert norm_last10("9876543210") == "9876543210"
    
    def test_phone_with_country_code(self):
        """Test phone number with country code"""
        assert norm_last10("+919876543210") == "9876543210"
        assert norm_last10("919876543210") == "9876543210"
    
    def test_phone_with_special_chars(self):
        """Test phone with special characters"""
        assert norm_last10("(123) 456-7890") == "1234567890"
        assert norm_last10("+1-234-567-8901") == "2345678901"
        assert norm_last10("123.456.7890") == "1234567890"
    
    def test_phone_longer_than_10(self):
        """Test phone number longer than 10 digits"""
        assert norm_last10("12345678901234") == "5678901234"
        assert norm_last10("+91-98765-43210") == "9876543210"
    
    def test_phone_shorter_than_10(self):
        """Test phone number shorter than 10 digits"""
        assert norm_last10("12345") == "12345"
        assert norm_last10("567") == "567"
    
    def test_empty_and_none(self):
        """Test empty string and None"""
        assert norm_last10(None) is None
        assert norm_last10("") is None
        assert norm_last10("   ") is None
    
    def test_non_numeric_input(self):
        """Test completely non-numeric input"""
        assert norm_last10("abcdefghij") is None
        assert norm_last10("no numbers here") is None
    
    def test_mixed_input(self):
        """Test mixed alphanumeric input"""
        assert norm_last10("abc123def456ghi7890") == "1234567890"
        assert norm_last10("Phone: 9876543210") == "9876543210"


class TestCheckMissingPhones:
    """Test cases for check_missing_phones function"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture(autouse=True)
    def mock_frappe_module(self):
        """Ensure frappe module is mocked for all tests"""
        if 'frappe' not in sys.modules:
            sys.modules['frappe'] = MagicMock()
        yield
        # Clean up after tests if needed
    
    def create_test_csv(self, filepath, phone_numbers):
        """Helper to create test CSV files"""
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['phone_number'])
            writer.writeheader()
            for phone in phone_numbers:
                writer.writerow({'phone_number': phone})
    
    def read_output_csv(self, filepath):
        """Helper to read output CSV files"""
        results = []
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                if row:
                    results.append(row[0])
        return results
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_basic_functionality(self, mock_frappe, temp_dir):
        """Test basic phone comparison functionality"""
        # Setup test data
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        # Create test CSV with phone numbers
        self.create_test_csv(input_csv, [
            '9876543210',
            '8765432109',
            '7654321098'
        ])
        
        # Mock frappe.get_all to return Student data
        mock_frappe.get_all.return_value = [
            {'name': 'STU001', 'phone': '9876543210', 'alt_phone': None},
            {'name': 'STU002', 'phone': '6543210987', 'alt_phone': None}
        ]
        
        # Run function
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        # Verify outputs
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        assert '7654321098' in missing
        assert '8765432109' in missing
        assert '6543210987' in extras
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_with_glific_id(self, mock_frappe, temp_dir):
        """Test including glific_id in comparison"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        self.create_test_csv(input_csv, ['9876543210', '8765432109'])
        
        mock_frappe.get_all.return_value = [
            {
                'name': 'STU001',
                'phone': '9876543210',
                'alt_phone': None,
                'glific_id': '7777777777'
            }
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=True,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        assert '8765432109' in missing
        assert '7777777777' in extras
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_with_alt_phone(self, mock_frappe, temp_dir):
        """Test with alternative phone numbers"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        self.create_test_csv(input_csv, ['9876543210', '8765432109'])
        
        mock_frappe.get_all.return_value = [
            {
                'name': 'STU001',
                'phone': '9876543210',
                'alt_phone': '5555555555'
            }
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        assert '8765432109' in missing
        assert '5555555555' in extras
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_phone_normalization(self, mock_frappe, temp_dir):
        """Test phone number normalization in comparison"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        # CSV has phones with special characters
        self.create_test_csv(input_csv, [
            '+91-9876543210',
            '(876) 543-2109',
            '765.432.1098'
        ])
        
        # Students have plain numbers
        mock_frappe.get_all.return_value = [
            {'name': 'STU001', 'phone': '9876543210', 'alt_phone': None},
            {'name': 'STU002', 'phone': '+918765432109', 'alt_phone': None}
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        # 7654321098 should be missing (not in Student)
        assert '7654321098' in missing
        # Both should match after normalization
        assert '9876543210' not in missing
        assert '8765432109' not in missing
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_empty_csv(self, mock_frappe, temp_dir):
        """Test with empty CSV file"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        # Create empty CSV (only header)
        self.create_test_csv(input_csv, [])
        
        mock_frappe.get_all.return_value = [
            {'name': 'STU001', 'phone': '9876543210', 'alt_phone': None}
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        assert len(missing) == 0
        assert '9876543210' in extras
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_no_students(self, mock_frappe, temp_dir):
        """Test when no students exist"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        self.create_test_csv(input_csv, ['9876543210', '8765432109'])
        
        mock_frappe.get_all.return_value = []
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        assert '9876543210' in missing
        assert '8765432109' in missing
        assert len(extras) == 0
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_invalid_csv_no_phone_column(self, mock_frappe, temp_dir):
        """Test with CSV missing phone_number column"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        
        # Create CSV with wrong column name
        with open(input_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['wrong_column'])
            writer.writeheader()
            writer.writerow({'wrong_column': '9876543210'})
        
        with pytest.raises(Exception) as exc_info:
            check_missing_phones(input_csv=input_csv)
        
        assert "CSV must have a 'phone_number' column" in str(exc_info.value)
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_default_file_paths(self, mock_frappe, temp_dir):
        """Test with default file paths"""
        # Mock frappe.get_site_path to return temp paths
        def mock_site_path(*args):
            return os.path.join(temp_dir, *args[2:])
        
        mock_frappe.get_site_path.side_effect = mock_site_path
        mock_frappe.get_all.return_value = []
        
        # Create default input file
        default_input = os.path.join(temp_dir, 'phones.csv')
        self.create_test_csv(default_input, ['9876543210'])
        
        # Run with no arguments (should use defaults)
        check_missing_phones()
        
        # Check default output files were created
        assert os.path.exists(os.path.join(temp_dir, 'missing_phones_last10.csv'))
        assert os.path.exists(os.path.join(temp_dir, 'doctype_only_phones_last10.csv'))
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_relative_file_paths(self, mock_frappe, temp_dir):
        """Test with relative file paths"""
        def mock_site_path(*args):
            return os.path.join(temp_dir, *args[2:])
        
        mock_frappe.get_site_path.side_effect = mock_site_path
        mock_frappe.get_all.return_value = []
        
        # Create input file
        input_file = os.path.join(temp_dir, 'test_phones.csv')
        self.create_test_csv(input_file, ['9876543210'])
        
        # Use relative paths
        check_missing_phones(
            input_csv='test_phones.csv',
            out_missing='test_missing.csv',
            out_extras='test_extras.csv'
        )
        
        # Verify files were created
        assert os.path.exists(os.path.join(temp_dir, 'test_missing.csv'))
        assert os.path.exists(os.path.join(temp_dir, 'test_extras.csv'))
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_duplicate_phones_in_csv(self, mock_frappe, temp_dir):
        """Test handling of duplicate phone numbers in CSV"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        # Create CSV with duplicate numbers
        self.create_test_csv(input_csv, [
            '9876543210',
            '9876543210',  # Duplicate
            '8765432109'
        ])
        
        mock_frappe.get_all.return_value = [
            {'name': 'STU001', 'phone': '9876543210', 'alt_phone': None}
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        
        # Should only have one entry for missing number
        assert missing.count('8765432109') == 1
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_null_and_empty_phones(self, mock_frappe, temp_dir):
        """Test handling of null and empty phone values"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        # Create CSV with some empty values
        with open(input_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['phone_number'])
            writer.writeheader()
            writer.writerow({'phone_number': '9876543210'})
            writer.writerow({'phone_number': ''})  # Empty
            writer.writerow({'phone_number': None})  # None
            writer.writerow({'phone_number': '   '})  # Whitespace
        
        mock_frappe.get_all.return_value = [
            {'name': 'STU001', 'phone': None, 'alt_phone': ''},
            {'name': 'STU002', 'phone': '9876543210', 'alt_phone': '   '}
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        # Empty values should be ignored
        assert len(missing) == 0
        assert len(extras) == 0
    
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_output_sorting(self, mock_frappe, temp_dir):
        """Test that output files have sorted phone numbers"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        self.create_test_csv(input_csv, [
            '3333333333',
            '1111111111',
            '2222222222'
        ])
        
        mock_frappe.get_all.return_value = [
            {'name': 'STU001', 'phone': '9999999999', 'alt_phone': None},
            {'name': 'STU002', 'phone': '7777777777', 'alt_phone': None},
            {'name': 'STU003', 'phone': '8888888888', 'alt_phone': None}
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        missing = self.read_output_csv(out_missing)
        extras = self.read_output_csv(out_extras)
        
        # Check sorting
        assert missing == sorted(missing)
        assert extras == sorted(extras)
        
        # Verify content
        assert missing == ['1111111111', '2222222222', '3333333333']
        assert extras == ['7777777777', '8888888888', '9999999999']
    
    @patch('builtins.print')
    @patch('tap_lms.utils.phone_checker.frappe')
    def test_console_output(self, mock_frappe, mock_print, temp_dir):
        """Test console output messages"""
        input_csv = os.path.join(temp_dir, 'phones.csv')
        out_missing = os.path.join(temp_dir, 'missing.csv')
        out_extras = os.path.join(temp_dir, 'extras.csv')
        
        self.create_test_csv(input_csv, ['9876543210', '8765432109'])
        
        mock_frappe.get_all.return_value = [
            {'name': 'STU001', 'phone': '7654321098', 'alt_phone': None}
        ]
        
        check_missing_phones(
            input_csv=input_csv,
            include_glific=False,
            out_missing=out_missing,
            out_extras=out_extras
        )
        
        # Verify print statements
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any('Done.' in str(call) for call in print_calls)
        assert any('CSV phones total' in str(call) for call in print_calls)
        assert any('Missing in Student: 2' in str(call) for call in print_calls)
        assert any('In Student only:   1' in str(call) for call in print_calls)