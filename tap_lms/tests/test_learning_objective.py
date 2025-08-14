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
    
    def test_learning_objective_with_data(self):
        """Test LearningObjective with sample data"""
        # Create with some sample data to ensure it works as a Document
        learning_obj = LearningObjective({
            'name': 'test-learning-objective',
            'title': 'Test Learning Objective',
            'description': 'A test learning objective'
        })
        assert learning_obj.name == 'test-learning-objective'
        assert learning_obj.title == 'Test Learning Objective'
        assert learning_obj.description == 'A test learning objective'
    
    def test_learning_objective_methods_inherited(self):
        """Test that Document methods are available"""
        learning_obj = LearningObjective()
        # Test that common Document methods are accessible
        assert hasattr(learning_obj, 'get')
        assert hasattr(learning_obj, 'set')
        assert hasattr(learning_obj, 'update')
        assert callable(getattr(learning_obj, 'get'))
        assert callable(getattr(learning_obj, 'set'))
        assert callable(getattr(learning_obj, 'update'))


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


# Fixtures for pytest (if using pytest)
@pytest.fixture
def learning_objective():
    """Fixture to create a LearningObjective instance"""
    return LearningObjective()

@pytest.fixture
def learning_objective_with_data():
    """Fixture to create a LearningObjective with sample data"""
    return LearningObjective({
        'name': 'sample-objective',
        'title': 'Sample Learning Objective',
        'description': 'Sample description for testing'
    })


# Parameterized tests for better coverage
@pytest.mark.parametrize("test_data", [
    {},
    {'name': 'test1'},
    {'name': 'test2', 'title': 'Test Title'},
    {'name': 'test3', 'title': 'Test Title', 'description': 'Test Description'}
])
def test_learning_objective_with_various_data(test_data):
    """Test LearningObjective with various data configurations"""
    learning_obj = LearningObjective(test_data)
    assert learning_obj is not None
    
    # Verify data was set correctly
    for key, value in test_data.items():
        assert getattr(learning_obj, key, None) == value


if __name__ == '__main__':
    # Run tests directly
    unittest.main()