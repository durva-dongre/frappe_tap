import unittest
import frappe
from frappe.test_runner import make_test_records
from tap_lms.tap_lms.doctype.quiz.quiz import Quiz


class TestQuiz(unittest.TestCase):
    """Test cases for Quiz doctype to achieve 100% code coverage"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures for the entire test class."""
        # Ensure we're in a test environment
        frappe.set_user("Administrator")
        
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Clean up any existing test documents
        self.cleanup_test_docs()
        
    def tearDown(self):
        """Clean up after each test method."""
        self.cleanup_test_docs()
        
    def cleanup_test_docs(self):
        """Helper method to clean up test documents"""
        test_names = ["Test Quiz 1", "Test Quiz 2", "Quiz 1", "Quiz 2"]
        for name in test_names:
            try:
                if frappe.db.exists("Quiz", name):
                    frappe.delete_doc("Quiz", name, force=True, ignore_permissions=True)
            except Exception:
                pass
        frappe.db.commit()
    
    def test_quiz_class_inheritance(self):
        """Test that Quiz class inherits from Document - covers class definition"""
        # This test ensures the class definition line is executed
        self.assertTrue(issubclass(Quiz, frappe.model.document.Document))
        
    def test_quiz_instantiation(self):
        """Test Quiz class can be instantiated - covers pass statement"""
        # This test ensures the class definition and pass statement are executed
        quiz = Quiz()
        self.assertIsInstance(quiz, Quiz)
        self.assertIsInstance(quiz, frappe.model.document.Document)
    
    def test_quiz_creation_with_data(self):
        """Test Quiz document creation with data"""
        quiz_data = {
            "doctype": "Quiz",
            "name": "Test Quiz 1"
        }
        quiz = Quiz(quiz_data)
        self.assertEqual(quiz.doctype, "Quiz")
        self.assertEqual(quiz.name, "Test Quiz 1")
    
    def test_quiz_document_methods(self):
        """Test inherited Document methods work correctly"""
        quiz_data = {
            "doctype": "Quiz", 
            "name": "Test Quiz 2"
        }
        quiz = Quiz(quiz_data)
        
        # Test that inherited methods are accessible
        self.assertTrue(hasattr(quiz, 'insert'))
        self.assertTrue(hasattr(quiz, 'save'))
        self.assertTrue(hasattr(quiz, 'delete'))
    
    def test_quiz_with_frappe_new_doc(self):
        """Test Quiz creation using frappe.new_doc"""
        # Another way to ensure class instantiation is covered
        quiz = frappe.new_doc("Quiz")
        self.assertIsInstance(quiz, Quiz)
        quiz.name = "Quiz 1"
        self.assertEqual(quiz.name, "Quiz 1")
    
    def test_multiple_quiz_instances(self):
        """Test creating multiple Quiz instances"""
        # Ensure class definition is executed multiple times
        quiz1 = Quiz({"doctype": "Quiz", "name": "Quiz Instance 1"})
        quiz2 = Quiz({"doctype": "Quiz", "name": "Quiz Instance 2"})
        
        self.assertIsInstance(quiz1, Quiz)
        self.assertIsInstance(quiz2, Quiz)
        self.assertNotEqual(id(quiz1), id(quiz2))
    
    def test_quiz_empty_initialization(self):
        """Test Quiz with no parameters"""
        quiz = Quiz()
        self.assertIsInstance(quiz, Quiz)
        # Test that it has the basic doctype attribute
        self.assertTrue(hasattr(quiz, 'doctype'))


# Separate test class to ensure import coverage
class TestQuizImport(unittest.TestCase):
    """Test class specifically for import statement coverage"""
    
    def test_import_statement_coverage(self):
        """Test to ensure import statement is covered"""
        # Import the module to ensure import line is executed
        from tap_lms.tap_lms.doctype.quiz.quiz import Quiz
        from frappe.model.document import Document
        
        # Verify the import worked
        self.assertTrue(Quiz)
        self.assertTrue(Document)
        self.assertTrue(issubclass(Quiz, Document))


# Edge cases test class
class TestQuizEdgeCases(unittest.TestCase):
    """Additional test cases for edge scenarios"""
    
    def setUp(self):
        frappe.set_user("Administrator")
    
    def test_quiz_class_attributes(self):
        """Test Quiz class has expected attributes"""
        # Verify class definition is properly executed
        self.assertTrue(hasattr(Quiz, '__module__'))
        self.assertTrue(hasattr(Quiz, '__bases__'))
        
        # Check that it properly inherits from Document
        self.assertIn(frappe.model.document.Document, Quiz.__mro__)
    
    def test_quiz_repr_and_str(self):
        """Test string representations work"""
        quiz = Quiz({"doctype": "Quiz", "name": "Test Quiz Repr"})
        # These should not raise exceptions
        str_repr = str(quiz)
        self.assertIsInstance(str_repr, str)


if __name__ == '__main__':
    # Set up Frappe environment for testing
    try:
        frappe.init(site="test_site")
        frappe.connect()
        frappe.set_user("Administrator")
    except Exception as e:
        print(f"Frappe setup error: {e}")
    
    # Run the tests
    unittest.main(verbosity=2)