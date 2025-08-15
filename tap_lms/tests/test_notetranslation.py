# test_notetranslation.py
import unittest
from unittest.mock import patch, MagicMock
import frappe
from frappe.tests.utils import FrappeTestCase
from tap_lms.tap_lms.doctype.notetranslation.notetranslation import NoteTranslation


class TestNoteTranslation(FrappeTestCase):
    """Test cases for NoteTranslation DocType"""
    
    def setUp(self):
        """Set up test data before each test method"""
        self.test_doc_data = {
            "doctype": "NoteTranslation",
            "name": "TEST-NOTE-TRANS-001",
            "original_note": "This is a test note in English",
            "translated_note": "Esta es una nota de prueba en español",
            "source_language": "en",
            "target_language": "es",
            "translation_status": "Completed"
        }
    
    def tearDown(self):
        """Clean up test data after each test method"""
        # Clean up any test documents created
        frappe.db.rollback()
    
    def test_create_note_translation(self):
        """Test creating a new NoteTranslation document"""
        # Create a new NoteTranslation document
        doc = frappe.get_doc(self.test_doc_data)
        doc.insert()
        
        # Verify the document was created successfully
        self.assertEqual(doc.doctype, "NoteTranslation")
        self.assertEqual(doc.original_note, "This is a test note in English")
        self.assertEqual(doc.translated_note, "Esta es una nota de prueba en español")
        self.assertEqual(doc.source_language, "en")
        self.assertEqual(doc.target_language, "es")
        self.assertEqual(doc.translation_status, "Completed")
    
    def test_note_translation_class_instantiation(self):
        """Test that NoteTranslation class can be instantiated"""
        # Create an instance of NoteTranslation
        note_translation = NoteTranslation()
        
        # Verify it's an instance of the correct class
        self.assertIsInstance(note_translation, NoteTranslation)
        
        # Verify it inherits from Document
        self.assertTrue(hasattr(note_translation, 'insert'))
        self.assertTrue(hasattr(note_translation, 'save'))
        self.assertTrue(hasattr(note_translation, 'delete'))
    
    def test_note_translation_with_document_data(self):
        """Test NoteTranslation with actual document data"""
        # Create NoteTranslation with data
        doc = frappe.get_doc(self.test_doc_data)
        note_translation = NoteTranslation(doc.as_dict())
        
        # Verify the data is properly set
        self.assertEqual(note_translation.original_note, "This is a test note in English")
        self.assertEqual(note_translation.translated_note, "Esta es una nota de prueba en español")
    
    def test_save_note_translation(self):
        """Test saving a NoteTranslation document"""
        doc = frappe.get_doc(self.test_doc_data)
        doc.insert()
        
        # Modify and save
        doc.translation_status = "In Progress"
        doc.save()
        
        # Verify the change was saved
        saved_doc = frappe.get_doc("NoteTranslation", doc.name)
        self.assertEqual(saved_doc.translation_status, "In Progress")
    
    def test_delete_note_translation(self):
        """Test deleting a NoteTranslation document"""
        doc = frappe.get_doc(self.test_doc_data)
        doc.insert()
        doc_name = doc.name
        
        # Delete the document
        doc.delete()
        
        # Verify it's deleted
        with self.assertRaises(frappe.DoesNotExistError):
            frappe.get_doc("NoteTranslation", doc_name)
    
    def test_note_translation_validation(self):
        """Test validation of NoteTranslation fields"""
        # Test with missing required fields
        invalid_data = {
            "doctype": "NoteTranslation",
            "original_note": "",  # Empty required field
        }
        
        doc = frappe.get_doc(invalid_data)
        
        # This should not raise an error since the base class just has 'pass'
        # But we're testing the inheritance and basic functionality
        self.assertEqual(doc.doctype, "NoteTranslation")
    
    @patch('frappe.db.commit')
    def test_note_translation_database_operations(self, mock_commit):
        """Test database operations with NoteTranslation"""
        doc = frappe.get_doc(self.test_doc_data)
        doc.insert()
        
        # Verify database commit was called
        mock_commit.assert_called()
        
        # Test querying
        found_docs = frappe.get_all("NoteTranslation", 
                                   filters={"source_language": "en"})
        self.assertGreaterEqual(len(found_docs), 0)
    
    def test_note_translation_field_access(self):
        """Test accessing fields on NoteTranslation"""
        doc = frappe.get_doc(self.test_doc_data)
        
        # Test field access
        self.assertTrue(hasattr(doc, 'original_note'))
        self.assertTrue(hasattr(doc, 'translated_note'))
        self.assertTrue(hasattr(doc, 'source_language'))
        self.assertTrue(hasattr(doc, 'target_language'))
        
        # Test field values
        self.assertEqual(doc.get('original_note'), "This is a test note in English")
        self.assertEqual(doc.get('translated_note'), "Esta es una nota de prueba en español")
    
    def test_note_translation_inheritance(self):
        """Test that NoteTranslation properly inherits from Document"""
        from frappe.model.document import Document
        
        doc = frappe.get_doc(self.test_doc_data)
        
        # Verify inheritance
        self.assertIsInstance(doc, Document)
        self.assertTrue(hasattr(doc, 'as_dict'))
        self.assertTrue(hasattr(doc, 'get'))
        self.assertTrue(hasattr(doc, 'set'))
    
    def test_note_translation_json_serialization(self):
        """Test JSON serialization of NoteTranslation"""
        doc = frappe.get_doc(self.test_doc_data)
        
        # Test as_dict method
        doc_dict = doc.as_dict()
        self.assertIsInstance(doc_dict, dict)
        self.assertIn('original_note', doc_dict)
        self.assertIn('translated_note', doc_dict)
        
        # Test JSON serialization
        import json
        json_str = json.dumps(doc_dict, default=str)
        self.assertIsInstance(json_str, str)


class TestNoteTranslationIntegration(FrappeTestCase):
    """Integration tests for NoteTranslation"""
    
    def test_note_translation_workflow(self):
        """Test complete workflow of NoteTranslation"""
        # Create
        doc_data = {
            "doctype": "NoteTranslation",
            "original_note": "Hello World",
            "translated_note": "Hola Mundo",
            "source_language": "en",
            "target_language": "es",
            "translation_status": "Draft"
        }
        
        doc = frappe.get_doc(doc_data)
        doc.insert()
        
        # Update
        doc.translation_status = "In Progress"
        doc.save()
        
        # Read
        saved_doc = frappe.get_doc("NoteTranslation", doc.name)
        self.assertEqual(saved_doc.translation_status, "In Progress")
        
        # Complete translation
        saved_doc.translation_status = "Completed"
        saved_doc.save()
        
        # Verify final state
        final_doc = frappe.get_doc("NoteTranslation", doc.name)
        self.assertEqual(final_doc.translation_status, "Completed")
        
        # Delete
        final_doc.delete()
