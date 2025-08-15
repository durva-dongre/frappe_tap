import pytest
import sys
from unittest.mock import Mock, patch

def test_generate_unique_batch_keyword_basic():
    """Test basic functionality of generate_unique_batch_keyword"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_random = sys.modules['random']
        mock_string = sys.modules['string']
        
        # Setup mocks
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random.randint = Mock(return_value=42)
        mock_random.choices = Mock(return_value=['A', 'B'])
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Mock documents
        mock_school_doc = Mock()
        mock_school_doc.name1 = "Test School"
        mock_batch_doc = Mock()
        mock_batch_doc.name1 = "Test Batch"
        
        mock_frappe.get_doc.side_effect = [mock_school_doc, mock_batch_doc]
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        # Test document
        mock_doc = Mock()
        mock_doc.school = "school_id"
        mock_doc.batch = "batch_id"
        
        result = generate_unique_batch_keyword(mock_doc)
        
        # Verify calls
        mock_frappe.get_doc.assert_any_call("School", "school_id")
        mock_frappe.get_doc.assert_any_call("Batch", "batch_id")
        mock_random.randint.assert_called_with(10, 99)
        mock_random.choices.assert_called_with("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=2)
        
        # Verify result format (no curly braces)
        expected = "TETE42AB"
        assert result == expected


def test_generate_unique_batch_keyword_collision():
    """Test collision handling in while loop"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_random = sys.modules['random']
        mock_string = sys.modules['string']
        
        # Setup mocks
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        
        # First attempt exists, second doesn't
        mock_frappe.db.exists.side_effect = [True, False]
        
        mock_random.randint.side_effect = [11, 22]
        mock_random.choices.side_effect = [['X', 'Y'], ['Z', 'A']]
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Mock documents
        mock_school_doc = Mock()
        mock_school_doc.name1 = "School Name"
        mock_batch_doc = Mock()
        mock_batch_doc.name1 = "Batch Name"
        
        mock_frappe.get_doc.side_effect = [mock_school_doc, mock_batch_doc]
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        mock_doc = Mock()
        mock_doc.school = "school_id"
        mock_doc.batch = "batch_id"
        
        result = generate_unique_batch_keyword(mock_doc)
        
        # Should use second attempt
        expected = "SCBA22ZA"
        assert result == expected
        
        # Verify collision handling
        assert mock_random.randint.call_count == 2
        assert mock_random.choices.call_count == 2
        assert mock_frappe.db.exists.call_count == 2


def test_generate_unique_batch_keyword_short_names():
    """Test with short names"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_random = sys.modules['random']
        mock_string = sys.modules['string']
        
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random.randint = Mock(return_value=77)
        mock_random.choices = Mock(return_value=['R', 'S'])
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Short names
        mock_school_doc = Mock()
        mock_school_doc.name1 = "A"
        mock_batch_doc = Mock()
        mock_batch_doc.name1 = "B"
        
        mock_frappe.get_doc.side_effect = [mock_school_doc, mock_batch_doc]
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        mock_doc = Mock()
        mock_doc.school = "school_id"
        mock_doc.batch = "batch_id"
        
        result = generate_unique_batch_keyword(mock_doc)
        
        expected = "AB77RS"
        assert result == expected


def test_generate_unique_batch_keyword_empty_names():
    """Test with empty names"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_random = sys.modules['random']
        mock_string = sys.modules['string']
        
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random.randint = Mock(return_value=88)
        mock_random.choices = Mock(return_value=['T', 'U'])
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Empty names
        mock_school_doc = Mock()
        mock_school_doc.name1 = ""
        mock_batch_doc = Mock()
        mock_batch_doc.name1 = ""
        
        mock_frappe.get_doc.side_effect = [mock_school_doc, mock_batch_doc]
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        mock_doc = Mock()
        mock_doc.school = "school_id"
        mock_doc.batch = "batch_id"
        
        result = generate_unique_batch_keyword(mock_doc)
        
        expected = "88TU"
        assert result == expected


def test_generate_unique_batch_keyword_multiple_collisions():
    """Test multiple collisions"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_random = sys.modules['random']
        mock_string = sys.modules['string']
        
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        
        # 3 collisions, then success
        mock_frappe.db.exists.side_effect = [True, True, True, False]
        
        mock_random.randint.side_effect = [10, 20, 30, 40]
        mock_random.choices.side_effect = [['A', 'A'], ['B', 'B'], ['C', 'C'], ['D', 'D']]
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        mock_school_doc = Mock()
        mock_school_doc.name1 = "Multi School"
        mock_batch_doc = Mock()
        mock_batch_doc.name1 = "Multi Batch"
        
        mock_frappe.get_doc.side_effect = [mock_school_doc, mock_batch_doc]
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        mock_doc = Mock()
        mock_doc.school = "school_id"
        mock_doc.batch = "batch_id"
        
        result = generate_unique_batch_keyword(mock_doc)
        
        # Should use 4th attempt
        expected = "MUMU40DD"
        assert result == expected
        
        assert mock_random.randint.call_count == 4
        assert mock_random.choices.call_count == 4
        assert mock_frappe.db.exists.call_count == 4


def test_function_imports():
    """Test that imports work"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        assert callable(generate_unique_batch_keyword)


def test_function_signature():
    """Test function signature"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        import inspect
        sig = inspect.signature(generate_unique_batch_keyword)
        assert len(sig.parameters) == 1
        assert 'doc' in sig.parameters


def test_complete_workflow():
    """Test complete workflow with all components"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_random = sys.modules['random']
        mock_string = sys.modules['string']
        
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random.randint = Mock(return_value=99)
        mock_random.choices = Mock(return_value=['Z', 'Z'])
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        mock_school_doc = Mock()
        mock_school_doc.name1 = "Complete School"
        mock_batch_doc = Mock()
        mock_batch_doc.name1 = "Complete Batch"
        
        mock_frappe.get_doc.side_effect = [mock_school_doc, mock_batch_doc]
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        mock_doc = Mock()
        mock_doc.school = "school_id"
        mock_doc.batch = "batch_id"
        
        result = generate_unique_batch_keyword(mock_doc)
        
        expected = "COCO99ZZ"
        assert result == expected
        
        # Verify all mocks were called
        assert mock_frappe.get_doc.call_count == 2
        mock_random.randint.assert_called_once()
        mock_random.choices.assert_called_once()
        mock_frappe.db.exists.assert_called_once()


def test_string_processing():
    """Test string processing logic"""
    
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'random': Mock(),
        'string': Mock(),
    }):
        mock_frappe = sys.modules['frappe']
        mock_random = sys.modules['random']
        mock_string = sys.modules['string']
        
        mock_frappe.get_doc = Mock()
        mock_frappe.db = Mock()
        mock_frappe.db.exists = Mock(return_value=False)
        
        mock_random.randint = Mock(return_value=55)
        mock_random.choices = Mock(return_value=['P', 'Q'])
        mock_string.ascii_uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        
        # Long names that need slicing
        mock_school_doc = Mock()
        mock_school_doc.name1 = "Very Long School Name"
        mock_batch_doc = Mock()
        mock_batch_doc.name1 = "very long batch name"
        
        mock_frappe.get_doc.side_effect = [mock_school_doc, mock_batch_doc]
        
        from tap_lms.batch_onboarding_utils import generate_unique_batch_keyword
        
        mock_doc = Mock()
        mock_doc.school = "school_id"
        mock_doc.batch = "batch_id"
        
        result = generate_unique_batch_keyword(mock_doc)
        
        # First 2 chars, uppercased
        expected = "VEVE55PQ"
        assert result == expected