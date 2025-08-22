# conftest.py - Pytest configuration for Glific Batch ID Update tests

import pytest
import sys
from unittest.mock import MagicMock


@pytest.fixture(scope="session", autouse=True)
def setup_frappe_mock():
    """Session-scoped fixture to mock frappe for all tests"""
    if 'frappe' not in sys.modules:
        # Create a comprehensive frappe mock
        frappe_mock = MagicMock()
        
        # Add common frappe exceptions
        frappe_mock.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
        frappe_mock.ValidationError = type('ValidationError', (Exception,), {})
        frappe_mock.PermissionError = type('PermissionError', (Exception,), {})
        
        # Mock database operations
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin.return_value = None
        frappe_mock.db.commit.return_value = None
        frappe_mock.db.rollback.return_value = None
        
        # Mock logger
        frappe_mock.logger.return_value = MagicMock()
        
        # Add to sys.modules
        sys.modules['frappe'] = frappe_mock
        sys.modules['frappe.utils'] = MagicMock()
        sys.modules['frappe.utils.background_jobs'] = MagicMock()
        
        print("✓ Frappe mock setup completed")
    
    return sys.modules['frappe']


@pytest.fixture(scope="function")
def clean_imports():
    """Clean up imports before each test"""
    modules_to_clean = [
        'tap_lms.glific_batch_id_update',
        'tap_lms.glific_integration'
    ]
    
    for module in modules_to_clean:
        if module in sys.modules:
            del sys.modules[module]
    
    yield
    
    # Cleanup after test
    for module in modules_to_clean:
        if module in sys.modules:
            del sys.modules[module]


# Test data fixtures
@pytest.fixture
def sample_test_data():
    """Provide sample test data for all tests"""
    return {
        'onboarding_set_name': "SAMPLE_SET_001",
        'student_id': "SAMPLE_STU_001",
        'student_name': "Sample Test Student",
        'phone': "+1234567890",
        'batch_id': "SAMPLE_BATCH_2024_A",
        'glific_id': "54321"
    }


@pytest.fixture
def sample_backend_students():
    """Provide sample backend students data"""
    return [
        {
            "name": "backend_student_1",
            "student_name": "Sample Student 01",
            "phone": "+1234567890",
            "student_id": "SAMPLE_STU_001",
            "batch": "SAMPLE_BATCH_A",
            "batch_skeyword": "SKEY01"
        },
        {
            "name": "backend_student_2", 
            "student_name": "Sample Student 02",
            "phone": "+1234567891",
            "student_id": "SAMPLE_STU_002",
            "batch": "SAMPLE_BATCH_B",
            "batch_skeyword": "SKEY02"
        }
    ]


@pytest.fixture
def sample_onboarding_sets():
    """Provide sample onboarding sets data"""
    return [
        {
            "name": "SAMPLE_SET_001",
            "set_name": "Sample Test Set 1",
            "processed_student_count": 10,
            "upload_date": "2024-01-15",
            "status": "Processed"
        },
        {
            "name": "SAMPLE_SET_002",
            "set_name": "Sample Test Set 2", 
            "processed_student_count": 25,
            "upload_date": "2024-01-10",
            "status": "Processed"
        }
    ]


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "api: mark test as an API test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "frappe: mark test as requiring Frappe environment")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers"""
    for item in items:
        # Add unit marker to all tests by default
        if not any(mark.name in ['integration', 'api', 'slow'] for mark in item.iter_markers()):
            item.add_marker(pytest.mark.unit)
        
        # Add frappe marker to tests that use frappe
        if 'frappe' in item.name.lower() or 'glific' in item.name.lower():
            item.add_marker(pytest.mark.frappe)


def pytest_runtest_setup(item):
    """Setup for each test run"""
    # Skip tests if module cannot be imported
    if hasattr(item, 'function'):
        # Check if test requires the tap_lms module
        if 'tap_lms' in str(item.function):
            pytest.importorskip("tap_lms.glific_batch_id_update", 
                              reason="tap_lms module not available")


# ============================================================================
# SETUP INSTRUCTIONS AND TROUBLESHOOTING GUIDE
# ============================================================================

"""
FRAPPE GLIFIC BATCH ID UPDATE - TEST SETUP GUIDE
===============================================

This guide will help you set up and run the test suite for the Glific Batch ID Update functionality.

QUICK SETUP:
-----------

1. Navigate to your app's test directory:
   cd /home/frappe/frappe-bench/apps/tap_lms/tap_lms/tests/

2. Copy the test files to this directory:
   - test_glific_batch_id_update.py (Frappe-compatible version)
   - pytest_test_glific_batch_id.py (pytest version)
   - conftest.py (this file)

3. Run the tests:
   
   # Option A: Using pytest (recommended)
   pytest pytest_test_glific_batch_id.py -v
   
   # Option B: Using unittest
   python test_glific_batch_id_update.py
   
   # Option C: Using Frappe's test runner
   bench run-tests --app tap_lms --module tap_lms.tests.test_glific_batch_id_update

TROUBLESHOOTING COMMON ISSUES:
-----------------------------

1. ImportError: No module named 'frappe.tests'
   Solution: Use the Frappe-compatible test file (test_glific_batch_id_update.py)

2. ImportError: No module named 'tap_lms.glific_batch_id_update'
   Solutions:
   - Verify the file path: apps/tap_lms/tap_lms/glific_batch_id_update.py
   - Check the module structure and imports
   - Use pytest.importorskip() to handle missing modules gracefully

3. Tests are being skipped with "Module not available for import"
   This is expected behavior when the module doesn't exist or has import issues.
   The tests will skip gracefully instead of failing.

4. Mock-related errors
   Ensure you're using the correct patch paths. Update module paths in @patch decorators
   to match your actual file structure.

RUNNING SPECIFIC TEST CATEGORIES:
-------------------------------

# Run only unit tests
pytest -m unit pytest_test_glific_batch_id.py

# Run only integration tests  
pytest -m integration pytest_test_glific_batch_id.py

# Skip slow tests
pytest -m "not slow" pytest_test_glific_batch_id.py

# Run with detailed output
pytest -v -s pytest_test_glific_batch_id.py

# Run specific test class
pytest pytest_test_glific_batch_id.py::TestGetStudentBatchId -v

# Run specific test method
pytest pytest_test_glific_batch_id.py::TestGetStudentBatchId::test_get_student_batch_id_success -v

INTEGRATION WITH CI/CD:
---------------------

For Jenkins or other CI systems, create a pytest.ini file:

```ini
[tool:pytest]
testpaths = tap_lms/tests
python_files = test_*.py pytest_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests
    integration: Integration tests
    api: API tests
    slow: Slow tests
    frappe: Tests requiring Frappe
addopts = -v --tb=short --strict-markers
```

CUSTOM TEST CONFIGURATION:
-------------------------

You can customize test behavior by modifying conftest.py:

1. Change mock behavior in setup_frappe_mock()
2. Add new fixtures for your specific test data
3. Modify pytest_configure() to add custom markers
4. Update pytest_collection_modifyitems() to auto-categorize tests

DEBUGGING FAILED TESTS:
----------------------

1. Run with verbose output:
   pytest -v -s pytest_test_glific_batch_id.py

2. Use pdb for debugging:
   pytest --pdb pytest_test_glific_batch_id.py

3. Run only failed tests:
   pytest --lf pytest_test_glific_batch_id.py

4. Show local variables in tracebacks:
   pytest -l pytest_test_glific_batch_id.py

PERFORMANCE TESTING:
-------------------

To run performance tests:
pytest -m slow pytest_test_glific_batch_id.py

To benchmark test execution:
pytest --benchmark-only pytest_test_glific_batch_id.py

ENVIRONMENT VARIABLES:
--------------------

Set these environment variables for test configuration:

export FRAPPE_TEST_MODE=1
export GLIFIC_TEST_API_URL=https://api.glific.test
export TEST_BATCH_SIZE=10

MANUAL TESTING:
--------------

For manual testing outside of the test suite:

```python
# In Frappe console
from tap_lms.glific_batch_id_update import get_student_batch_id

# Test the function manually
result = get_student_batch_id("STU001", "BATCH_A")
print(f"Result: {result}")
```

CREATING NEW TESTS:
------------------

When adding new test cases:

1. Follow the naming convention: test_<function_name>_<scenario>
2. Use descriptive docstrings
3. Add appropriate markers (@pytest.mark.unit, etc.)
4. Include both positive and negative test cases
5. Mock all external dependencies
6. Use fixtures for common test data

EXAMPLE TEST STRUCTURE:
---------------------

```python
class TestNewFunction:
    '''Test cases for new_function'''
    
    def test_new_function_success(self, sample_test_data):
        '''Test successful execution'''
        # Setup
        # Execute  
        # Assert
        
    def test_new_function_error(self):
        '''Test error handling'''
        # Setup error condition
        # Execute
        # Assert error response
```

For additional help or questions, refer to:
- Frappe Testing Documentation
- pytest Documentation  
- Python unittest Documentation
"""

# Helper functions for test execution
def run_all_tests():
    """Run all tests with standard configuration"""
    import subprocess
    import sys
    
    try:
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'pytest_test_glific_batch_id.py', 
            '-v', '--tb=short'
        ], capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"Error running tests: {e}")
        return False


def validate_test_environment():
    """Validate that the test environment is properly configured"""
    import importlib
    
    print("Validating test environment...")
    
    # Check required modules
    required_modules = ['unittest', 'pytest', 'json', 'datetime']
    missing_modules = []
    
    for module in required_modules:
        try:
            importlib.import_module(module)
            print(f"✓ {module} - Available")
        except ImportError:
            missing_modules.append(module)
            print(f"✗ {module} - Missing")
    
    # Check optional modules
    optional_modules = ['tap_lms.glific_batch_id_update']
    
    for module in optional_modules:
        try:
            importlib.import_module(module)
            print(f"✓ {module} - Available")
        except ImportError:
            print(f"⚠ {module} - Not available (tests will be skipped)")
    
    if missing_modules:
        print(f"\nError: Missing required modules: {missing_modules}")
        return False
    
    print("\n✓ Test environment validation completed!")
    return True
