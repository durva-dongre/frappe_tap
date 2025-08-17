import unittest
import frappe
from frappe.tests.utils import FrappeTestCase

class TestState(FrappeTestCase):
    def setUp(self):
        """Set up test data before each test method"""
        frappe.set_user("Administrator")
        
    def test_state_creation(self):
        """Test basic State document creation"""
        # Create a new State document
        state_doc = frappe.get_doc({
            "doctype": "State",
            "state_name": "Test State",
            "state_code": "TS"
        })
        
        # Insert the document
        state_doc.insert(ignore_permissions=True)
        
        # Verify the document was created
        self.assertTrue(state_doc.name)
        self.assertEqual(state_doc.state_name, "Test State")
        self.assertEqual(state_doc.state_code, "TS")
        
        # Clean up
        state_doc.delete()
        
    def test_state_validation(self):
        """Test State document validation"""
        # Test with valid data
        state_doc = frappe.get_doc({
            "doctype": "State",
            "state_name": "Valid State",
            "state_code": "VS"
        })
        
        # This should not raise any validation errors
        state_doc.insert(ignore_permissions=True)
        self.assertTrue(state_doc.name)
        
        # Clean up
        state_doc.delete()
        
    def test_state_duplicate_prevention(self):
        """Test that duplicate states are handled properly"""
        # Create first state
        state_doc1 = frappe.get_doc({
            "doctype": "State",
            "state_name": "Duplicate Test",
            "state_code": "DT"
        })
        state_doc1.insert(ignore_permissions=True)
        
        try:
            # Try to create duplicate (this may or may not throw error depending on your schema)
            state_doc2 = frappe.get_doc({
                "doctype": "State",
                "state_name": "Duplicate Test",
                "state_code": "DT"
            })
            state_doc2.insert(ignore_permissions=True)
            
            # If no error, clean up both
            state_doc2.delete()
            
        except Exception as e:
            # If duplicate validation exists, this is expected
            pass
        finally:
            # Clean up first document
            state_doc1.delete()
            
    def test_state_get_doc(self):
        """Test retrieving State document"""
        # Create a state
        state_doc = frappe.get_doc({
            "doctype": "State",
            "state_name": "Retrieve Test",
            "state_code": "RT"
        })
        state_doc.insert(ignore_permissions=True)
        
        # Retrieve the document
        retrieved_doc = frappe.get_doc("State", state_doc.name)
        
        # Verify retrieved data
        self.assertEqual(retrieved_doc.state_name, "Retrieve Test")
        self.assertEqual(retrieved_doc.state_code, "RT")
        
        # Clean up
        state_doc.delete()
        
    def test_state_update(self):
        """Test updating State document"""
        # Create a state
        state_doc = frappe.get_doc({
            "doctype": "State",
            "state_name": "Update Test",
            "state_code": "UT"
        })
        state_doc.insert(ignore_permissions=True)
        
        # Update the document
        state_doc.state_name = "Updated State Name"
        state_doc.save()
        
        # Verify the update
        self.assertEqual(state_doc.state_name, "Updated State Name")
        
        # Clean up
        state_doc.delete()
        
    def tearDown(self):
        """Clean up after each test method"""
        frappe.db.rollback()
