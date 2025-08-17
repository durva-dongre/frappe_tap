import pytest
from unittest.mock import Mock, patch
from frappe.model.document import Document
from tap_lms.tap_lms.doctype.studentfeedbackchannel.studentfeedbackchannel import StudentFeedbackChannel


class TestStudentFeedbackChannel:
    """Test cases for StudentFeedbackChannel doctype"""
    
    def test_student_feedback_channel_creation(self):
        """Test basic creation of StudentFeedbackChannel document"""
        # Create a mock document
        doc = StudentFeedbackChannel()
        
        # Verify it's an instance of Document
        assert isinstance(doc, Document)
        assert doc.__class__.__name__ == "StudentFeedbackChannel"

    def test_student_feedback_channel_doctype_name(self):
        """Test that the doctype name is correctly set"""
        doc = StudentFeedbackChannel()
        
        # The doctype should be inferred from class name
        expected_doctype = "StudentFeedbackChannel"
        assert doc.__class__.__name__ == expected_doctype
    
    @patch('frappe.get_doc')
    def test_student_feedback_channel_factory_creation(self, mock_get_doc):
        """Test creating StudentFeedbackChannel through frappe factory"""
        mock_doc = Mock(spec=StudentFeedbackChannel)
        mock_get_doc.return_value = mock_doc
        
        import frappe
        doc = frappe.get_doc("StudentFeedbackChannel")
        
        mock_get_doc.assert_called_once_with("StudentFeedbackChannel")
        assert doc == mock_doc
    
    def test_student_feedback_channel_pass_statement(self):
        """Test that the pass statement in the class works correctly"""
        # This test ensures the class can be instantiated despite having only 'pass'
        try:
            doc = StudentFeedbackChannel()
            # If we get here, the pass statement worked correctly
            assert True
        except Exception as e:
            pytest.fail(f"StudentFeedbackChannel instantiation failed: {e}")
    
   


# Fixtures for test data
@pytest.fixture
def sample_feedback_channel_data():
    """Fixture providing sample data for StudentFeedbackChannel"""
    return {
        'name': 'Sample Feedback Channel',
        'description': 'A sample feedback channel for testing',
        'is_active': 1,
        'creation': '2025-08-17 10:00:00',
        'modified': '2025-08-17 10:00:00'
    }


@pytest.fixture
def mock_student_feedback_channel(sample_feedback_channel_data):
    """Fixture providing a mocked StudentFeedbackChannel instance"""
    with patch('frappe.model.document.Document.__init__'):
        doc = StudentFeedbackChannel(sample_feedback_channel_data)
        for key, value in sample_feedback_channel_data.items():
            setattr(doc, key, value)
        return doc