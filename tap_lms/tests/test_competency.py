
import unittest
from unittest.mock import patch, MagicMock
import sys
import importlib

# Test file for competency.py to achieve 100% coverage
class TestCompetency(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Mock frappe module to avoid import errors during testing
        self.frappe_mock = MagicMock()
        self.document_mock = MagicMock()
        self.frappe_mock.model.document.Document = self.document_mock
        sys.modules['frappe'] = self.frappe_mock
        sys.modules['frappe.model'] = self.frappe_mock.model
        sys.modules['frappe.model.document'] = self.frappe_mock.model.document
    
    def tearDown(self):
        """Clean up after each test method."""
        # Remove mocked modules
        modules_to_remove = [
            'frappe',
            'frappe.model',
            'frappe.model.document',
            'tap_lms.tap_lms.doctype.competency.competency'
        ]
        for module in modules_to_remove:
            if module in sys.modules:
                del sys.modules[module]
    

