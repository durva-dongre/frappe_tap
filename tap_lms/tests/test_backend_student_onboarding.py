# run_tests_with_coverage.py
"""
Test runner script to execute tests with coverage reporting
"""

import coverage
import unittest
import sys
import os

def run_tests_with_coverage():
    """Run tests with coverage measurement."""
    
    # Initialize coverage
    cov = coverage.Coverage()
    cov.start()
    
    try:
        # Import and run your test
        from test_backend_students import TestBackendStudents, TestBackendStudentsCoverage
        
        # Create test suite
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        
        # Add test cases
        suite.addTests(loader.loadTestsFromTestCase(TestBackendStudents))
        suite.addTests(loader.loadTestsFromTestCase(TestBackendStudentsCoverage))
        
        # Run tests
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        # Stop coverage measurement
        cov.stop()
        cov.save()
        
        # Generate coverage report
        print("\n" + "="*50)
        print("COVERAGE REPORT")
        print("="*50)
        
        # Show coverage for your specific file
        cov.report(
            show_missing=True,
            include="**/backend_students.py"
        )
        
        # Generate HTML report (optional)
        cov.html_report(directory='coverage_html_report')
        print(f"\nHTML coverage report generated in 'coverage_html_report' directory")
        
        return result.wasSuccessful()
        
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure your Frappe environment is properly set up")
        return False
    except Exception as e:
        print(f"Error running tests: {e}")
        return False
    finally:
        cov.stop()

if __name__ == '__main__':
    success = run_tests_with_coverage()
    sys.exit(0 if success else 1)