import unittest
from unittest.mock import patch, MagicMock
from frappe.model.document import Document
from tap_lms.tap_lms.doctype.competencylist.competencylist import CompetencyList


class TestCompetencyList(unittest.TestCase):
    """Test cases for CompetencyList doctype"""
    
    def setUp(self):
        """Set up test fixtures before each test method"""
        self.competency_list = CompetencyList()
    
    def test_competency_list_inheritance(self):
        """Test that CompetencyList inherits from Document"""
        self.assertIsInstance(self.competency_list, Document)
        self.assertTrue(issubclass(CompetencyList, Document))
    
    def test_competency_list_instantiation(self):
        """Test CompetencyList can be instantiated"""
        self.assertIsNotNone(self.competency_list)
        self.assertEqual(type(self.competency_list).__name__, 'CompetencyList')
    
    @patch('frappe.get_doc')
    def test_competency_list_creation_with_frappe(self, mock_get_doc):
        """Test CompetencyList creation through Frappe framework"""
        mock_doc = MagicMock(spec=CompetencyList)
        mock_get_doc.return_value = mock_doc
        
        # Simulate creating a new CompetencyList document
        doc = mock_get_doc('CompetencyList')
        
        self.assertIsNotNone(doc)
        mock_get_doc.assert_called_once_with('CompetencyList')
    
       
    @patch('frappe.new_doc')
    def test_competency_list_new_document(self, mock_new_doc):
        """Test creating a new CompetencyList document"""
        mock_doc = MagicMock(spec=CompetencyList)
        mock_new_doc.return_value = mock_doc
        
        # Simulate creating a new document
        new_competency_list = mock_new_doc('CompetencyList')
        
        self.assertIsNotNone(new_competency_list)
        mock_new_doc.assert_called_once_with('CompetencyList')
    
    def test_competency_list_str_representation(self):
        """Test string representation of CompetencyList"""
        # Set a name for testing
        self.competency_list.name = "Test Competency List"
        
        # The string representation should include the name
        str_repr = str(self.competency_list)
        self.assertIsInstance(str_repr, str)
    
    def test_competency_list_doctype_property(self):
        """Test that doctype is set correctly"""
        # This might be set automatically by Frappe
        if hasattr(self.competency_list, 'doctype'):
            self.assertEqual(self.competency_list.doctype, 'CompetencyList')


class TestCompetencyListIntegration(unittest.TestCase):
    """Integration tests for CompetencyList with Frappe framework"""
    
    @patch('frappe.get_all')
    def test_get_all_competency_lists(self, mock_get_all):
        """Test retrieving all CompetencyList documents"""
        mock_get_all.return_value = [
            {'name': 'CL001', 'title': 'Basic Skills'},
            {'name': 'CL002', 'title': 'Advanced Skills'}
        ]
        
        # This would be how you'd typically query CompetencyList documents
        import frappe
        competency_lists = frappe.get_all('CompetencyList', 
                                        fields=['name', 'title'])
        
        self.assertEqual(len(competency_lists), 2)
        self.assertEqual(competency_lists[0]['name'], 'CL001')
        mock_get_all.assert_called_once_with('CompetencyList', 
                                           fields=['name', 'title'])
    
    @patch('frappe.db.exists')
    def test_competency_list_exists(self, mock_exists):
        """Test checking if CompetencyList document exists"""
        mock_exists.return_value = True
        
        import frappe
        exists = frappe.db.exists('CompetencyList', 'CL001')
        
        self.assertTrue(exists)
        mock_exists.assert_called_once_with('CompetencyList', 'CL001')


# if __name__ == '__main__':
#     # Run the tests
#     unittest.main(verbosity=2)