# test_pathwaymodification.py
"""
Frappe-style test for PathwayModification
"""
import frappe
import unittest
from frappe.tests.utils import FrappeTestCase

class TestPathwayModification(FrappeTestCase):
    """Test PathwayModification doctype"""
    
    def test_import_and_class_definition(self):
        """Test importing the class and its definition"""
        # This covers the import statement (line 5)
        from tap_lms.tap_lms.doctype.pathwaymodification.pathwaymodification import PathwayModification
        
        # Verify the class exists
        self.assertIsNotNone(PathwayModification)
        
        # Check inheritance (covers class definition - line 7)
        self.assertTrue(hasattr(PathwayModification, '__bases__'))
        
        # The class should have Document as base class
        base_class_names = [base.__name__ for base in PathwayModification.__bases__]
        self.assertIn('Document', base_class_names)
    
    def test_class_instantiation(self):
        """Test creating a new PathwayModification document"""
        # This covers the pass statement (line 8) when the class is instantiated
        doc = frappe.new_doc("PathwayModification")
        self.assertEqual(doc.doctype, "PathwayModification")
        
        # Test direct class instantiation as well
        from tap_lms.tap_lms.doctype.pathwaymodification.pathwaymodification import PathwayModification
        instance = PathwayModification()
        self.assertIsInstance(instance, PathwayModification)
    
    def test_doctype_meta(self):
        """Test doctype metadata"""
        meta = frappe.get_meta("PathwayModification")
        self.assertIsNotNone(meta)
        self.assertEqual(meta.name, "PathwayModification")
        
    def test_class_methods_and_attributes(self):
        """Test any inherited methods and attributes"""
        from tap_lms.tap_lms.doctype.pathwaymodification.pathwaymodification import PathwayModification
        
        # Test that the class has expected attributes from Document
        instance = PathwayModification()
        
        # These should be inherited from Document class
        self.assertTrue(hasattr(instance, 'doctype'))
        self.assertTrue(hasattr(instance, 'name'))
        
    def tearDown(self):
        """Clean up after tests"""
        frappe.db.rollback()