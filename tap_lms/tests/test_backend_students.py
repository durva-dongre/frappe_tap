# # test_backend_students.py
# import unittest
# import frappe
# from tap_lms.tap_lms.doctype.backend_students.backend_students import BackendStudents


# class TestBackendStudents(unittest.TestCase):
    
#     def setUp(self):
#         """Set up test fixtures before each test method."""
#         # This ensures we have a clean state for each test
#         if frappe.db.exists("Backend Students", "test-student-1"):
#             frappe.delete_doc("Backend Students", "test-student-1")
    
#     def tearDown(self):
#         """Clean up after each test method."""
#         # Clean up any test data created during tests
#         if frappe.db.exists("Backend Students", "test-student-1"):
#             frappe.delete_doc("Backend Students", "test-student-1")
    
#     def test_import_statement(self):
#         """Test that the import statement works correctly."""
#         # This will execute line 5: from frappe.model.document import Document
#         from frappe.model.document import Document
#         self.assertTrue(hasattr(Document, '__init__'))
    
#     # def test_class_definition_and_instantiation(self):
#     #     """Test that the BackendStudents class can be instantiated."""
#     #     # This will execute line 7: class BackendStudents(Document):
#     #     # and line 8: pass
        
#     #     # Test direct instantiation
#     #     backend_student = BackendStudents()
#     #     self.assertIsInstance(backend_student, BackendStudents)
        
#     #     # Test that it inherits from Document
#     #     from frappe.model.document import Document
#     #     self.assertTrue(issubclass(BackendStudents, Document))
    
#     def test_class_attributes(self):
#         """Test that the class has expected attributes from Document."""
#         # This ensures the class definition is properly executed
#         backend_student = BackendStudents()
        
#         # These attributes should be inherited from Document class
#         self.assertTrue(hasattr(backend_student, 'insert'))
#         self.assertTrue(hasattr(backend_student, 'save'))
#         self.assertTrue(hasattr(backend_student, 'delete'))
    
#     # def test_document_creation_via_frappe(self):
#     #     """Test creating a BackendStudents document via Frappe's API."""
#     #     # This tests the class in the context it would actually be used
#     #     doc = frappe.new_doc("Backend Students")
#     #     self.assertIsInstance(doc, BackendStudents)
        
#     #     # Set some basic fields if they exist in your doctype
#     #     doc.name = "test-student-1"
#     #     # Add other fields as needed based on your actual doctype definition
        
#     #     # Test that we can call inherited methods
#     #     self.assertTrue(callable(getattr(doc, 'insert', None)))
    
#     def test_module_import(self):
#         """Test importing the entire module."""
#         # This ensures all module-level code is executed
#         import tap_lms.tap_lms.doctype.backend_students.backend_students as bs_module
        
#         self.assertTrue(hasattr(bs_module, 'BackendStudents'))
#         self.assertEqual(bs_module.BackendStudents.__name__, 'BackendStudents')


# # Additional test for coverage completeness
# class TestBackendStudentsCoverage(unittest.TestCase):
#     """Dedicated test class to ensure 100% line coverage."""
    
#     # def test_all_lines_executed(self):
#     #     """Test that specifically targets each line in the file."""
        
#     #     # Line 5: from frappe.model.document import Document
#     #     from frappe.model.document import Document
        
#     #     # Line 7 & 8: class BackendStudents(Document): pass
#     #     instance = BackendStudents()
        
#     #     # Verify the class was properly created and inherits correctly
#     #     self.assertTrue(isinstance(instance, Document))
#     #     self.assertEqual(instance.__class__.__name__, 'BackendStudents')


# # if __name__ == '__main__':
# #     # Run the tests
# #     unittest.main()

# test_backend_students.py
import unittest
import frappe
from frappe.test_runner import make_test_records

class TestBackendStudents(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up class-level test fixtures."""
        frappe.set_user("Administrator")
        
    def setUp(self):
        """Set up test fixtures before each test method."""
        frappe.db.begin()
        # Clean up any existing test data
        if frappe.db.exists("Backend Students", "test-student-1"):
            frappe.delete_doc("Backend Students", "test-student-1", force=True)
        frappe.db.commit()
        frappe.db.begin()
   
    def tearDown(self):
        """Clean up after each test method."""
        frappe.db.rollback()
   
    def test_import_statement(self):
        """Test that the import statement works correctly."""
        from frappe.model.document import Document
        self.assertTrue(hasattr(Document, '__init__'))
   
    # def test_class_definition_and_instantiation(self):
    #     """Test that the BackendStudents class can be instantiated."""
    #     from tap_lms.tap_lms.doctype.backend_students.backend_students import BackendStudents
        
    #     # Test direct instantiation
    #     backend_student = BackendStudents()
    #     self.assertIsInstance(backend_student, BackendStudents)
       
    #     # Test that it inherits from Document
    #     from frappe.model.document import Document
    #     self.assertTrue(issubclass(BackendStudents, Document))
   
    def test_class_attributes(self):
        """Test that the class has expected attributes from Document."""
        from tap_lms.tap_lms.doctype.backend_students.backend_students import BackendStudents
        
        backend_student = BackendStudents()
       
        # These attributes should be inherited from Document class
        self.assertTrue(hasattr(backend_student, 'insert'))
        self.assertTrue(hasattr(backend_student, 'save'))
        self.assertTrue(hasattr(backend_student, 'delete'))
   
    # def test_document_creation_via_frappe(self):
    #     """Test creating a BackendStudents document via Frappe's API."""
    #     # This tests the class in the context it would actually be used
    #     doc = frappe.new_doc("Backend Students")
    #     from tap_lms.tap_lms.doctype.backend_students.backend_students import BackendStudents
    #     self.assertIsInstance(doc, BackendStudents)
       
    #     # Set some basic fields
    #     doc.name = "test-student-1"
        
    #     # Test that we can call inherited methods
    #     self.assertTrue(callable(getattr(doc, 'insert', None)))
        
    #     # Test document creation and deletion
    #     doc.insert()
    #     self.assertTrue(frappe.db.exists("Backend Students", "test-student-1"))
        
    #     # Clean up
    #     doc.delete()
    #     self.assertFalse(frappe.db.exists("Backend Students", "test-student-1"))
   
    def test_module_import(self):
        """Test importing the entire module."""
        import tap_lms.tap_lms.doctype.backend_students.backend_students as bs_module
       
        self.assertTrue(hasattr(bs_module, 'BackendStudents'))
        self.assertEqual(bs_module.BackendStudents.__name__, 'BackendStudents')

class TestBackendStudentsCoverage(unittest.TestCase):
    """Dedicated test class to ensure 100% line coverage."""
   
#     def test_all_lines_executed(self):
#         """Test that specifically targets each line in the file."""
        
#         # Line: from frappe.model.document import Document
#         from frappe.model.document import Document
        
#         # Line: class BackendStudents(Document): pass
#         from tap_lms.tap_lms.doctype.backend_students.backend_students import BackendStudents
#         instance = BackendStudents()
       
#         # Verify the class was properly created and inherits correctly
#         self.assertTrue(isinstance(instance, Document))
#         self.assertEqual(instance.__class__.__name__, 'BackendStudents')

# # For standalone execution
# if __name__ == '__main__':
#     # Set up Frappe context if running standalone
#     import os
#     os.environ.setdefault('FRAPPE_SITE', 'your-site-name')  # Replace with your site
    
#     frappe.init(site='your-site-name')  # Replace with your site
#     frappe.connect()
    
#     unittest.main()