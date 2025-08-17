import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the path to your module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tap_lms.config.tap_lms import get_data


class TestTapLmsConfig(unittest.TestCase):
    """Test cases for tap_lms configuration module"""
    
    def test_get_data_returns_dict(self):
        """Test that get_data returns a dictionary"""
        result = get_data()
        self.assertIsInstance(result, dict)
    
    def test_get_data_has_required_keys(self):
        """Test that get_data returns dictionary with expected top-level keys"""
        result = get_data()
        expected_keys = ['label', 'items']
        
        for key in expected_keys:
            with self.subTest(key=key):
                self.assertIn(key, result)
    
    def test_get_data_label_value(self):
        """Test that the label has the expected value"""
        result = get_data()
        self.assertEqual(result['label'], '_("School")')
    
    def test_get_data_items_structure(self):
        """Test the structure of items array"""
        result = get_data()
        items = result['items']
        
        # Should be a list
        self.assertIsInstance(items, list)
        
        # Should have at least one item
        self.assertGreater(len(items), 0)
        
        # First item should be a dictionary
        self.assertIsInstance(items[0], dict)
    
    def test_get_data_school_item_properties(self):
        """Test the properties of the school item configuration"""
        result = get_data()
        school_item = result['items'][0]
        
        expected_properties = {
            'type': 'doctype',
            'name': 'School',
            'label': '_("School")',
            'description': '_("Manage School")',
            'onboard': 1
        }
        
        for key, expected_value in expected_properties.items():
            with self.subTest(property=key):
                self.assertIn(key, school_item)
                self.assertEqual(school_item[key], expected_value)
    
    def test_get_data_consistent_calls(self):
        """Test that multiple calls to get_data return the same result"""
        result1 = get_data()
        result2 = get_data()
        
        self.assertEqual(result1, result2)
    
    @patch('tap_lms.config.tap_lms.frappe')
    def test_get_data_with_frappe_import(self, mock_frappe):
        """Test that get_data works when frappe is imported"""
        # This test assumes frappe import might affect the function
        # You can remove this if frappe import doesn't impact the function
        result = get_data()
        self.assertIsInstance(result, dict)
        self.assertIn('label', result)
        self.assertIn('items', result)
    
    def test_get_data_items_count(self):
        """Test the expected number of items"""
        result = get_data()
        items = result['items']
        
        # Based on the visible code, there should be exactly 1 item
        self.assertEqual(len(items), 1)
    
    def test_get_data_school_item_type_doctype(self):
        """Test that the school item has type 'doctype'"""
        result = get_data()
        school_item = result['items'][0]
        
        self.assertEqual(school_item['type'], 'doctype')
    
    def test_get_data_school_item_onboard_flag(self):
        """Test that the school item has onboard flag set to 1"""
        result = get_data()
        school_item = result['items'][0]
        
        self.assertEqual(school_item['onboard'], 1)


class TestTapLmsConfigIntegration(unittest.TestCase):
    """Integration tests for tap_lms configuration"""
    
    def test_config_can_be_serialized(self):
        """Test that the configuration can be serialized to JSON"""
        import json
        
        result = get_data()
        
        # Should not raise an exception
        json_string = json.dumps(result)
        self.assertIsInstance(json_string, str)
        
        # Should be able to deserialize back
        deserialized = json.loads(json_string)
        self.assertEqual(result, deserialized)
    
    def test_config_structure_for_ui_consumption(self):
        """Test that the configuration structure is suitable for UI consumption"""
        result = get_data()
        
        # Verify structure that a UI might expect
        self.assertTrue(all(isinstance(item, dict) for item in result['items']))
        
        # Each item should have required fields for UI rendering
        for item in result['items']:
            required_ui_fields = ['type', 'name', 'label']
            for field in required_ui_fields:
                with self.subTest(item=item.get('name', 'unknown'), field=field):
                    self.assertIn(field, item)


# if __name__ == '__main__':
#     # Run the tests
#     unittest.main(verbosity=2)


# # Alternative pytest version if you prefer pytest
# """
# To run with pytest, save this as test_tap_lms_pytest.py:

# import pytest
# import json
# from tap_lms.config.tap_lms import get_data


# class TestTapLmsConfig:
    
#     def test_get_data_returns_dict(self):
#         result = get_data()
#         assert isinstance(result, dict)
    
#     def test_get_data_has_required_keys(self):
#         result = get_data()
#         assert 'label' in result
#         assert 'items' in result
    
#     def test_get_data_label_value(self):
#         result = get_data()
#         assert result['label'] == '_("School")'
    
#     def test_get_data_items_structure(self):
#         result = get_data()
#         items = result['items']
#         assert isinstance(items, list)
#         assert len(items) > 0
#         assert isinstance(items[0], dict)
    
#     def test_get_data_school_item_properties(self):
#         result = get_data()
#         school_item = result['items'][0]
        
#         assert school_item['type'] == 'doctype'
#         assert school_item['name'] == 'School'
#         assert school_item['label'] == '_("School")'
#         assert school_item['description'] == '_("Manage School")'
#         assert school_item['onboard'] == 1
    
#     def test_config_serializable(self):
#         result = get_data()
#         json_string = json.dumps(result)
#         deserialized = json.loads(json_string)
#         assert result == deserialized

# """