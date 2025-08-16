# apps/tap_lms/tap_lms/tests/test_quiz.py

import frappe
import unittest
from frappe.test_runner import make_test_records


class TestQuiz(unittest.TestCase):
    """
    Test cases for Quiz doctype to achieve 100% code coverage
    Fixed version to avoid mock issues
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once for the entire test class"""
        # Ensure we're in the right context
        if not frappe.db:
            frappe.connect()
        frappe.set_user("Administrator")
    
    def setUp(self):
        """Set up before each test"""
        frappe.set_user("Administrator")
        # Clear any existing transactions
        frappe.db.rollback()
    
    def tearDown(self):
        """Clean up after each test"""
        frappe.db.rollback()
    
    def test_quiz_class_inheritance(self):
        """Test that Quiz class inherits from Document - covers class definition"""
        # Import inside the test to avoid mock issues
        from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
        from frappe.model.document import Document
        
        # Test that Quiz is a subclass of Document
        self.assertTrue(issubclass(Quiz, Document))
        
    def test_quiz_instantiation(self):
        """Test Quiz class can be instantiated - covers pass statement"""
        # Import fresh to avoid mock interference
        from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
        
        # Create instance
        quiz = Quiz()
        self.assertIsInstance(quiz, Quiz)

        
    
        
  
    def test_quiz_empty_initialization(self):
        """Test Quiz with no parameters"""
        from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
        
        # This should work without issues
        quiz = Quiz()
        self.assertIsInstance(quiz, Quiz)
        
    def test_import_coverage(self):
        """Test to ensure import statement is covered"""
        # This import will execute the import line in quiz.py
        from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
        from frappe.model.document import Document
        
        # Verify the import worked correctly
        self.assertTrue(Quiz)
        self.assertTrue(Document)
        self.assertTrue(issubclass(Quiz, Document))
        
    def test_quiz_class_attributes(self):
        """Test Quiz class has expected attributes"""
        from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
        
        # Verify class definition is properly executed
        self.assertTrue(hasattr(Quiz, '__module__'))
        self.assertTrue(hasattr(Quiz, '__doc__'))
        
    def test_quiz_class_module(self):
        """Test Quiz class module path"""
        from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
        
        # Verify the module path
        self.assertEqual(Quiz.__module__, 'tap_lms.tap_lms.doctype.quiz.quiz')


# Additional function-level test to ensure import coverage
def test_module_import():
    """Function to test module import outside of class context"""
    from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
    return Quiz is not None


# Test the import when module is run directly
if __name__ == "__main__":
    # Test import
    result = test_module_import()
    print(f"Import test result: {result}")
    
    # Run tests
    unittest.main(verbosity=2)