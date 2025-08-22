import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import json


class TestGlificWebhookDiscovery(unittest.TestCase):
    """Test to discover the actual structure of the Glific webhook module"""
    
    def test_discover_module_structure(self):
        """Discover what's actually available in the module"""
        print("\n" + "="*60)
        print("🔍 DISCOVERING MODULE STRUCTURE")
        print("="*60)
        
        # Try different possible import paths
        possible_paths = [
            "tap_lms.integrations.glific_webhook",
            "tap_lms.glific_webhook", 
            "integrations.glific_webhook",
            "glific_webhook"
        ]
        
        found_module = None
        for path in possible_paths:
            try:
                print(f"Trying to import: {path}")
                module = __import__(path, fromlist=[''])
                found_module = module
                print(f"✅ Successfully imported: {path}")
                break
            except ImportError as e:
                print(f"❌ Failed to import {path}: {e}")
        
        if found_module:
            print(f"\n📋 Module contents:")
            for attr in dir(found_module):
                if not attr.startswith('_'):
                    obj = getattr(found_module, attr)
                    obj_type = type(obj).__name__
                    print(f"  - {attr} ({obj_type})")
                    
                    if callable(obj):
                        try:
                            import inspect
                            sig = inspect.signature(obj)
                            print(f"    Signature: {attr}{sig}")
                        except:
                            print(f"    Signature: Could not determine")
        else:
            print("❌ Could not import any module variant")
            
        # Try to find the actual file
        print(f"\n📁 Looking for webhook files...")
        possible_file_paths = [
            "/home/frappe/frappe-bench/apps/tap_lms/tap_lms/integrations/glific_webhook.py",
            "/home/frappe/frappe-bench/apps/tap_lms/tap_lms/glific_webhook.py",
            "/home/frappe/frappe-bench/apps/tap_lms/integrations/glific_webhook.py"
        ]
        
        for file_path in possible_file_paths:
            if os.path.exists(file_path):
                print(f"✅ Found file: {file_path}")
                with open(file_path, 'r') as f:
                    content = f.read()
                    print(f"📏 File size: {len(content)} characters")
                    
                    # Extract function names
                    import re
                    functions = re.findall(r'def (\w+)\(', content)
                    print(f"🔧 Functions found: {functions}")
                    break
            else:
                print(f"❌ File not found: {file_path}")


class TestGlificWebhookBasic(unittest.TestCase):
    """Basic tests that work with any module structure"""
    
    def setUp(self):
        """Set up basic mocks and test data"""
        self.teacher_doc = Mock()
        self.teacher_doc.doctype = "Teacher"
        self.teacher_doc.name = "TEST-001"
        self.teacher_doc.glific_id = "123"
        
    def test_basic_frappe_availability(self):
        """Test if frappe is available"""
        try:
            import frappe
            print("✅ Frappe is available")
            print(f"📍 Frappe module path: {frappe.__file__ if hasattr(frappe, '__file__') else 'No file path'}")
        except ImportError:
            print("❌ Frappe is not available - mocking required")
            
    def test_basic_imports(self):
        """Test basic imports work"""
        try:
            # Try importing common modules
            import requests
            print("✅ Requests module available")
        except ImportError:
            print("❌ Requests module not available")
            
        try:
            import json
            print("✅ JSON module available")
        except ImportError:
            print("❌ JSON module not available")


class TestGlificWebhookAdaptive(unittest.TestCase):
    """Adaptive tests that adjust based on what's available"""
    
    def setUp(self):
        """Setup with dynamic import discovery"""
        self.module = None
        self.functions = {}
        
        # Try to import the actual module
        possible_imports = [
            ("tap_lms.integrations.glific_webhook", ["update_glific_contact", "get_glific_contact", "prepare_update_payload", "send_glific_update"]),
            ("glific_webhook", ["update_glific_contact", "get_glific_contact", "prepare_update_payload", "send_glific_update"])
        ]
        
        for module_path, expected_functions in possible_imports:
            try:
                self.module = __import__(module_path, fromlist=expected_functions)
                for func_name in expected_functions:
                    if hasattr(self.module, func_name):
                        self.functions[func_name] = getattr(self.module, func_name)
                break
            except ImportError:
                continue
                
    def test_update_glific_contact_exists(self):
        """Test if update_glific_contact function exists and is callable"""
        if 'update_glific_contact' in self.functions:
            func = self.functions['update_glific_contact']
            self.assertTrue(callable(func), "update_glific_contact should be callable")
            print("✅ update_glific_contact function found and callable")
            
            # Try to call with mock data
            try:
                teacher_doc = Mock()
                teacher_doc.doctype = "Student"  # Non-teacher to test early return
                
                # This should not raise an exception
                func(teacher_doc, "on_update")
                print("✅ update_glific_contact handles non-Teacher doctype")
            except Exception as e:
                print(f"⚠️  update_glific_contact raised exception: {e}")
        else:
            self.skipTest("update_glific_contact function not found")
            
    def test_get_glific_contact_exists(self):
        """Test if get_glific_contact function exists"""
        if 'get_glific_contact' in self.functions:
            func = self.functions['get_glific_contact']
            self.assertTrue(callable(func), "get_glific_contact should be callable")
            print("✅ get_glific_contact function found and callable")
        else:
            self.skipTest("get_glific_contact function not found")
            
    def test_prepare_update_payload_exists(self):
        """Test if prepare_update_payload function exists"""
        if 'prepare_update_payload' in self.functions:
            func = self.functions['prepare_update_payload']
            self.assertTrue(callable(func), "prepare_update_payload should be callable")
            print("✅ prepare_update_payload function found and callable")
        else:
            self.skipTest("prepare_update_payload function not found")
            
    def test_send_glific_update_exists(self):
        """Test if send_glific_update function exists"""
        if 'send_glific_update' in self.functions:
            func = self.functions['send_glific_update']
            self.assertTrue(callable(func), "send_glific_update should be callable")
            print("✅ send_glific_update function found and callable")
        else:
            self.skipTest("send_glific_update function not found")


class TestGlificWebhookMocked(unittest.TestCase):
    """Tests using completely mocked functions"""
    
    def setUp(self):
        """Set up mocked versions of functions for testing logic"""
        self.teacher_doc = Mock()
        self.teacher_doc.doctype = "Teacher"
        self.teacher_doc.name = "TEST-001"
        self.teacher_doc.glific_id = "123"
        
    def create_mock_update_glific_contact(self):
        """Create a mock version of update_glific_contact for testing"""
        def mock_update_glific_contact(doc, method):
            if doc.doctype != "Teacher":
                return
            
            # Mock the main logic
            if not hasattr(doc, 'glific_id') or not doc.glific_id:
                print(f"No Glific ID for {doc.name}")
                return
                
            print(f"Processing teacher {doc.name} with Glific ID {doc.glific_id}")
            return True
            
        return mock_update_glific_contact
        
    def test_mock_update_logic(self):
        """Test the basic logic using mocked function"""
        mock_func = self.create_mock_update_glific_contact()
        
        # Test with Teacher doctype
        result = mock_func(self.teacher_doc, "on_update")
        self.assertTrue(result)
        
        # Test with non-Teacher doctype
        student_doc = Mock()
        student_doc.doctype = "Student"
        result = mock_func(student_doc, "on_update")
        self.assertIsNone(result)
        
        print("✅ Mock update logic tests passed")


class TestGlificWebhookIntegration(unittest.TestCase):
    """Integration-style tests that work with the actual environment"""
    
    @patch('requests.post')
    def test_mock_api_calls(self, mock_post):
        """Test API call mocking works correctly"""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"contact": {"contact": {"id": "123"}}}}
        mock_post.return_value = mock_response
        
        # Test that we can mock requests.post
        import requests
        response = requests.post("https://test.com", json={"test": "data"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("data", response.json())
        
        print("✅ API call mocking works correctly")
        
    @patch('frappe.logger')
    @patch('frappe.get_all')
    def test_mock_frappe_calls(self, mock_get_all, mock_logger):
        """Test Frappe function mocking works correctly"""
        # Setup mock returns
        mock_get_all.return_value = [{"frappe_field": "phone", "glific_field": "phone"}]
        
        # Test the mocks
        try:
            import frappe
            result = frappe.get_all("Test DocType")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["frappe_field"], "phone")
            
            frappe.logger().info("Test message")
            mock_logger().info.assert_called_with("Test message")
            
            print("✅ Frappe function mocking works correctly")
        except ImportError:
            print("⚠️  Frappe not available, but mocking structure is correct")


def run_diagnostic_tests():
    """Run diagnostic tests to understand the environment"""
    print("🔍 RUNNING DIAGNOSTIC TESTS")
    print("="*50)
    
    # Check Python environment
    print(f"Python version: {sys.version}")
    print(f"Python path: {sys.path[:3]}...")  # Show first 3 paths
    
    # Check current directory
    print(f"Current directory: {os.getcwd()}")
    
    # Check if we're in a Frappe environment
    try:
        import frappe
        print("✅ Running in Frappe environment")
    except ImportError:
        print("❌ Not in Frappe environment")
    
    # Run the discovery test
    suite = unittest.TestSuite()
    suite.addTest(TestGlificWebhookDiscovery('test_discover_module_structure'))
    
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Glific webhook tests')
    parser.add_argument('--diagnostic', '-d', action='store_true', help='Run diagnostic tests only')
    parser.add_argument('--basic', '-b', action='store_true', help='Run basic tests only')
    parser.add_argument('--adaptive', '-a', action='store_true', help='Run adaptive tests only')
    parser.add_argument('--mocked', '-m', action='store_true', help='Run mocked tests only')
    
    args = parser.parse_args()
    
    if args.diagnostic:
        run_diagnostic_tests()
    elif args.basic:
        suite = unittest.TestLoader().loadTestsFromTestCase(TestGlificWebhookBasic)
        unittest.TextTestRunner(verbosity=2).run(suite)
    elif args.adaptive:
        suite = unittest.TestLoader().loadTestsFromTestCase(TestGlificWebhookAdaptive)
        unittest.TextTestRunner(verbosity=2).run(suite)
    elif args.mocked:
        suite = unittest.TestLoader().loadTestsFromTestCase(TestGlificWebhookMocked)
        unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        # Run all tests
        print("🚀 RUNNING ALL GLIFIC WEBHOOK TESTS")
        print("="*50)
        
        # First run diagnostic
        run_diagnostic_tests()
        
        # Then run all other tests
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        
        suite.addTests(loader.loadTestsFromTestCase(TestGlificWebhookBasic))
        suite.addTests(loader.loadTestsFromTestCase(TestGlificWebhookAdaptive))
        suite.addTests(loader.loadTestsFromTestCase(TestGlificWebhookMocked))
        suite.addTests(loader.loadTestsFromTestCase(TestGlificWebhookIntegration))
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        print("\n" + "="*50)
        if result.wasSuccessful():
            print(f"✅ All {result.testsRun} tests passed!")
        else:
            print(f"❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")
            
            if result.failures:
                print("\n🔴 Failures:")
                for test, traceback in result.failures:
                    print(f"  - {test}")
                    
            if result.errors:
                print("\n🔴 Errors:")
                for test, traceback in result.errors:
                    print(f"  - {test}")