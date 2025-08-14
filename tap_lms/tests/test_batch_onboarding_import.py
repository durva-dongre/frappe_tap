import pytest
import sys
from unittest.mock import Mock, patch

def test_generate_unique_batch_keyword_coverage():
    """
    Test to achieve 100% coverage for batch_onboarding_utils.py
    Tests the generate_unique_batch_keyword function with all code paths
    """
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        # Mock frappe functions
        mock_frappe = sys.modules['frappe']
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock()
        
        # Mock random module
        mock_random = sys.modules['random']
        mock_random.randint = Mock()
        mock_random.choices = Mock()
        
        # Mock string module
        mock_string = sys.modules['string']
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Mock the join function
        mock_random.choices.return_value = ['A', 'B']
        
        # Create mock school and batch documents
        mock_school = Mock()
        mock_school.name1 = "Test School Name"
        
        mock_batch = Mock()
        mock_batch.name1 = "Batch Alpha"
        
        mock_frappe.get_doc.side_effect = [mock_school, mock_batch]
        
        # Test case 1: Keyword is unique on first try (covers lines 5-14, 22)
        mock_random.randint.return_value = 42
        mock_frappe.db.exists.return_value = False  # Keyword is unique
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        result = generate_unique_batch_keyword("school_id", "batch_id")
        
        # Verify the function calls
        mock_frappe.get_doc.assert_any_call("School", "school_id")
        mock_frappe.get_doc.assert_any_call("Batch", "batch_id")
        mock_random.randint.assert_called_with(10, 99)
        mock_random.choices.assert_called_with("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=2)
        mock_frappe.db.exists.assert_called_with("Batch Onboarding", {"batch_skeyword": "TESTSCHOOL_BATCHALPHA_42_AB"})
        
        # Verify the result
        assert result == "TESTSCHOOL_BATCHALPHA_42_AB"


def test_generate_unique_batch_keyword_with_collision():
    """
    Test generate_unique_batch_keyword when keyword collision occurs
    This tests the while loop functionality (lines 17-21)
    """
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        # Mock frappe functions
        mock_frappe = sys.modules['frappe']
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock()
        
        # Mock random module
        mock_random = sys.modules['random']
        mock_random.randint = Mock()
        mock_random.choices = Mock()
        
        # Mock string module
        mock_string = sys.modules['string']
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Create mock school and batch documents
        mock_school = Mock()
        mock_school.name1 = "Collision School"
        
        mock_batch = Mock()
        mock_batch.name1 = "Test Batch"
        
        mock_frappe.get_doc.side_effect = [mock_school, mock_batch]
        
        # Set up collision scenario
        mock_random.randint.side_effect = [10, 20]  # First collision, then unique
        mock_random.choices.side_effect = [['X', 'Y'], ['Z', 'W']]  # Different letters each time
        mock_frappe.db.exists.side_effect = [True, False]  # First exists (collision), second is unique
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        result = generate_unique_batch_keyword("collision_school", "test_batch")
        
        # Verify the function was called twice due to collision
        assert mock_random.randint.call_count == 2
        assert mock_random.choices.call_count == 2
        assert mock_frappe.db.exists.call_count == 2
        
        # Verify the final result is the second (unique) keyword
        assert result == "COLLISIONSCHOOL_TESTBATCH_20_ZW"


def test_generate_unique_batch_keyword_edge_cases():
    """
    Test edge cases for generate_unique_batch_keyword function
    """
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        # Mock setup
        mock_frappe = sys.modules['frappe']
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random = sys.modules['random']
        mock_random.randint = Mock(return_value=99)
        mock_random.choices = Mock(return_value=['Z', 'Z'])
        
        mock_string = sys.modules['string']
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        # Test with school/batch names that have special characters and spaces
        mock_school = Mock()
        mock_school.name1 = "St. Mary's High School & College"
        
        mock_batch = Mock()
        mock_batch.name1 = "Advanced-Level Batch 2024"
        
        mock_frappe.get_doc.side_effect = [mock_school, mock_batch]
        
        result = generate_unique_batch_keyword("special_school", "special_batch")
        
        # Should handle special characters and create valid keyword
        assert result == "ST.MARY'SHIGHSCHOOL&COLLEGE_ADVANCED-LEVELBATCH2024_99_ZZ"
        
        # Reset for next test
        mock_frappe.get_doc.reset_mock()
        
        # Test with very short names
        mock_school_short = Mock()
        mock_school_short.name1 = "A"
        
        mock_batch_short = Mock()
        mock_batch_short.name1 = "B"
        
        mock_frappe.get_doc.side_effect = [mock_school_short, mock_batch_short]
        
        result = generate_unique_batch_keyword("short_school", "short_batch")
        
        assert result == "A_B_99_ZZ"


def test_generate_unique_batch_keyword_multiple_collisions():
    """
    Test generate_unique_batch_keyword with multiple collisions
    """
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        # Mock setup
        mock_frappe = sys.modules['frappe']
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock()
        
        mock_random = sys.modules['random']
        mock_random.randint = Mock()
        mock_random.choices = Mock()
        
        mock_string = sys.modules['string']
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Create mock documents
        mock_school = Mock()
        mock_school.name1 = "Multi Collision School"
        
        mock_batch = Mock()
        mock_batch.name1 = "Collision Batch"
        
        mock_frappe.get_doc.side_effect = [mock_school, mock_batch]
        
        # Set up multiple collisions (3 attempts before success)
        mock_random.randint.side_effect = [11, 22, 33]
        mock_random.choices.side_effect = [['A', 'A'], ['B', 'B'], ['C', 'C']]
        mock_frappe.db.exists.side_effect = [True, True, False]  # Two collisions, then unique
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        result = generate_unique_batch_keyword("multi_school", "multi_batch")
        
        # Verify multiple attempts were made
        assert mock_random.randint.call_count == 3
        assert mock_random.choices.call_count == 3
        assert mock_frappe.db.exists.call_count == 3
        
        # Verify final result
        assert result == "MULTICOLLISIONSCHOOL_COLLISIONBATCH_33_CC"


def test_import_statements_coverage():
    """Test that all import statements are covered"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        # This covers lines 1-3 (import statements)
        try:
            from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
            import_success = True
        except ImportError:
            import_success = False
        
        assert import_success
        assert callable(generate_unique_batch_keyword)


def test_function_definition_coverage():
    """Test that the function definition is covered"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        # Test function signature
        import inspect
        sig = inspect.signature(generate_unique_batch_keyword)
        assert len(sig.parameters) == 1  # Should take doc parameter
        
        # Test function exists
        assert generate_unique_batch_keyword.__name__ == 'generate_unique_batch_keyword'


def test_string_manipulation_logic():
    """Test the string manipulation logic in detail"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        # Mock setup
        mock_frappe = sys.modules['frappe']
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random = sys.modules['random']
        mock_random.randint = Mock(return_value=55)
        mock_random.choices = Mock(return_value=['X', 'Y'])
        
        mock_string = sys.modules['string']
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        # Test that spaces are removed and text is uppercased
        mock_school = Mock()
        mock_school.name1 = "lowercase school name"
        
        mock_batch = Mock()
        mock_batch.name1 = "MIXED Case Batch"
        
        mock_frappe.get_doc.side_effect = [mock_school, mock_batch]
        
        result = generate_unique_batch_keyword("test_doc")
        
        # Verify string processing: spaces removed, uppercased
        expected = "LOWERCASESCHOOLNAME_MIXEDCASEBATCH_55_XY"
        assert result == expected
        
        # Verify the database check was made with correct keyword
        mock_frappe.db.exists.assert_called_with("Batch Onboarding", {"batch_skeyword": expected})


def test_random_generation_bounds():
    """Test that random number and letter generation works correctly"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        # Mock setup
        mock_frappe = sys.modules['frappe']
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random = sys.modules['random']
        mock_random.randint = Mock(return_value=10)  # Minimum value
        mock_random.choices = Mock(return_value=['A', 'Z'])  # First and last letters
        
        mock_string = sys.modules['string']
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        # Create simple mock documents
        mock_school = Mock()
        mock_school.name1 = "Test"
        
        mock_batch = Mock()
        mock_batch.name1 = "Batch"
        
        mock_frappe.get_doc.side_effect = [mock_school, mock_batch]
        
        result = generate_unique_batch_keyword("test_doc")
        
        # Verify random functions were called with correct parameters
        mock_random.randint.assert_called_with(10, 99)
        mock_random.choices.assert_called_with("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=2)
        
        # Verify result format
        assert result == "TEST_BATCH_10_AZ"