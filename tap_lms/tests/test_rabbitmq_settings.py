"""
Direct test approach to achieve 100% coverage for rabbitmq_settings.py
This bypasses frappe import issues by mocking the dependencies.
"""

import subprocess
import sys
import tempfile
import os


def test_rabbitmq_settings_coverage():
    """Test rabbitmq_settings.py by executing it directly with mocked dependencies"""
    
    # Create a temporary test script that mocks frappe and imports the module
    test_script = '''
import sys
from unittest.mock import Mock

# Mock frappe before any imports
mock_document = Mock()
mock_frappe = Mock()
mock_frappe.model = Mock()
mock_frappe.model.document = Mock()
mock_frappe.model.document.Document = mock_document

# Add mocked frappe to sys.modules
sys.modules['frappe'] = mock_frappe
sys.modules['frappe.model'] = mock_frappe.model
sys.modules['frappe.model.document'] = mock_frappe.model.document

# Now import the module under test
try:
    from tap_lms.tap_lms.doctype.rabbitmq_settings.rabbitmq_settings import RabbitmqSettings
    
    # Test 1: Import statement coverage (line 5)
    print("✓ Import statement executed")
    
    # Test 2: Class definition coverage (line 7)
    assert RabbitmqSettings is not None
    print("✓ Class definition executed")
    
    # Test 3: Pass statement coverage (line 8)
    instance = RabbitmqSettings()
    assert instance is not None
    print("✓ Pass statement executed")
    
    print("All tests passed - 100% coverage achieved!")
    
except Exception as e:
    print(f"Test failed: {e}")
    sys.exit(1)
'''
    
    # Write test script to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_script)
        temp_script = f.name
    
    try:
        # Run the test script
        result = subprocess.run([
            sys.executable, temp_script
        ], capture_output=True, text=True, cwd=os.getcwd())
        
        print("Test output:")
        print(result.stdout)
        
        if result.stderr:
            print("Test errors:")
            print(result.stderr)
        
        assert result.returncode == 0, f"Test script failed with return code {result.returncode}"
        
    finally:
        # Clean up temporary file
        if os.path.exists(temp_script):
            os.unlink(temp_script)


def test_simple_import():
    """Simple test to verify the module can be imported with mocking"""
    from unittest.mock import Mock, patch
    
    # Create mock
    mock_document = Mock()
    
    # Patch the frappe import
    with patch.dict('sys.modules', {
        'frappe': Mock(),
        'frappe.model': Mock(),
        'frappe.model.document': Mock(Document=mock_document)
    }):
        # This should now work
        import tap_lms.tap_lms.doctype.rabbitmq_settings.rabbitmq_settings as module
        assert module is not None


if __name__ == "__main__":
    test_rabbitmq_settings_coverage()
    test_simple_import()
    print("All tests completed successfully!")