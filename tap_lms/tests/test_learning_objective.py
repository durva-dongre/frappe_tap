import pytest
from frappe.model.document import Document
from tap_lms.tap_lms.doctype.learning_objective.learning_objective import LearningObjective


class TestLearningObjective:
    """Test cases for LearningObjective class"""
    
    def test_learning_objective_inheritance(self):
        """Test that LearningObjective properly inherits from Document"""
        # This will cover the class definition line
        learning_obj = LearningObjective()
        assert isinstance(learning_obj, Document)
        assert isinstance(learning_obj, LearningObjective)
    
    def test_learning_objective_instantiation(self):
        """Test basic instantiation of LearningObjective"""
        # This covers the class definition and pass statement
        learning_obj = LearningObjective()
        assert learning_obj is not None
        assert learning_obj.__class__.__name__ == "LearningObjective"
    
   

# Alternative test structure using unittest if you prefer
import unittest

class TestLearningObjectiveUnittest(unittest.TestCase):
    """Alternative unittest-based test cases"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.learning_obj = LearningObjective()
    
    def test_class_inheritance(self):
        """Test class inheritance"""
        self.assertIsInstance(self.learning_obj, Document)
        self.assertIsInstance(self.learning_obj, LearningObjective)
    
    def test_class_attributes(self):
        """Test class has expected attributes"""
        # This ensures the class definition and pass are executed
        self.assertTrue(hasattr(LearningObjective, '__doc__'))
        self.assertTrue(hasattr(LearningObjective, '__module__'))
        self.assertEqual(LearningObjective.__bases__, (Document,))

