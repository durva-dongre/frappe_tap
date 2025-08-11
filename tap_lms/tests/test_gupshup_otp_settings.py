
"""
Test that actually imports the real GupshupOTPSettings source file
This will give you 100% coverage by executing the actual code

Replace your current test_gupshup_otp_settings.py with this
"""

import sys
import unittest
from unittest.mock import MagicMock, patch


class TestGupshupOTPSettingsRealImport(unittest.TestCase):
    """Test that imports and executes the ACTUAL source file"""
    
    @classmethod
    def setUpClass(cls):
        """Set up mocks before importing the real module"""
        # Create mock Document class
        class MockDocument:
            def __init__(self, *args, **kwargs):
                pass
        
        # Create frappe mock
        frappe_mock = MagicMock()
        frappe_mock.model = MagicMock() 
        frappe_mock.model.document = MagicMock()
        frappe_mock.model.document.Document = MockDocument
        
        # Install mocks in sys.modules BEFORE any imports
        sys.modules['frappe'] = frappe_mock
        sys.modules['frappe.model'] = frappe_mock.model
        sys.modules['frappe.model.document'] = frappe_mock.model.document
        
        cls.MockDocument = MockDocument
    
    def test_import_actual_source_file(self):
        """Test that imports the ACTUAL source file (this gives 100% coverage)"""
        # This import statement will execute ALL lines in your source file:
        # Line 5: from frappe.model.document import Document
        # Line 7: class GupshupOTPSettings(Document):  
        # Line 8:     pass
        
        from tap_lms.tap_lms.doctype.gupshup_otp_settings.gupshup_otp_settings import GupshupOTPSettings
        
        # Verify the import worked
        self.assertIsNotNone(GupshupOTPSettings)
        self.assertEqual(GupshupOTPSettings.__name__, 'GupshupOTPSettings')
        
        # Verify inheritance 
        self.assertTrue(issubclass(GupshupOTPSettings, self.MockDocument))
        
        # Create instance to ensure pass statement is executed
        instance = GupshupOTPSettings()
        self.assertIsNotNone(instance)
        self.assertIsInstance(instance, GupshupOTPSettings)
        
        print("✅ Successfully imported and executed actual source file!")
        print("✅ All 3 lines should now show 100% coverage!")


# Simple pytest functions that also import the real source
def test_real_import():
    """Pytest function that imports real source file"""
    from tap_lms.tap_lms.doctype.gupshup_otp_settings.gupshup_otp_settings import GupshupOTPSettings
    assert GupshupOTPSettings is not None


def test_real_instantiation():
    """Pytest function that creates real instance"""
    from tap_lms.tap_lms.doctype.gupshup_otp_settings.gupshup_otp_settings import GupshupOTPSettings
    doc = GupshupOTPSettings()
    assert doc is not None


# if __name__ == '__main__':
#     unittest.main(verbosity=2)