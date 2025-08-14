# Copyright (c) 2025, Tech4dev and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

class TestInteractionLog(FrappeTestCase):
    
    def setUp(self):
        """Set up test data before each test method"""
        # Create test user if needed
        if not frappe.db.exists("User", "test@example.com"):
            frappe.get_doc({
                "doctype": "User",
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User"
            }).insert()
    
    def tearDown(self):
        """Clean up after each test method"""
        # Delete test interaction logs
        frappe.db.delete("Interaction Log", {"reference_doctype": "Test Document"})
        frappe.db.commit()
    
    def test_create_interaction_log(self):
        """Test creating a new interaction log entry"""
        log = frappe.get_doc({
            "doctype": "Interaction Log",
            "interaction_type": "Email",
            "reference_doctype": "Test Document",
            "reference_name": "TEST-001",
            "subject": "Test Email Subject",
            "content": "Test email content",
            "communication_medium": "Email"
        })
        log.insert()
        
        self.assertTrue(log.name)
        self.assertEqual(log.interaction_type, "Email")
        self.assertEqual(log.subject, "Test Email Subject")
    
    def test_interaction_log_validation(self):
        """Test validation rules for interaction log"""
        # Test missing required fields
        with self.assertRaises(frappe.ValidationError):
            log = frappe.get_doc({
                "doctype": "Interaction Log",
                # Missing required fields
            })
            log.insert()
    
    def test_get_interaction_logs_by_reference(self):
        """Test retrieving interaction logs by reference document"""
        # Create test interaction log
        log = frappe.get_doc({
            "doctype": "Interaction Log",
            "interaction_type": "Phone Call",
            "reference_doctype": "Test Document",
            "reference_name": "TEST-002",
            "subject": "Follow-up call",
            "content": "Discussed project requirements"
        })
        log.insert()
        
        # Retrieve logs by reference
        logs = frappe.get_all("Interaction Log", 
                            filters={"reference_name": "TEST-002"},
                            fields=["name", "subject", "interaction_type"])
        
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["subject"], "Follow-up call")
    
    def test_interaction_log_timeline(self):
        """Test chronological ordering of interaction logs"""
        import time
        
        # Create multiple logs with different timestamps
        log1 = frappe.get_doc({
            "doctype": "Interaction Log",
            "interaction_type": "Email",
            "reference_doctype": "Test Document",
            "reference_name": "TEST-003",
            "subject": "First interaction"
        })
        log1.insert()
        
        time.sleep(1)  # Ensure different timestamps
        
        log2 = frappe.get_doc({
            "doctype": "Interaction Log",
            "interaction_type": "Meeting",
            "reference_doctype": "Test Document",
            "reference_name": "TEST-003",
            "subject": "Second interaction"
        })
        log2.insert()
        
        # Get logs ordered by creation time
        logs = frappe.get_all("Interaction Log",
                            filters={"reference_name": "TEST-003"},
                            fields=["name", "subject", "creation"],
                            order_by="creation")
        
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["subject"], "First interaction")
        self.assertEqual(logs[1]["subject"], "Second interaction")
    
    def test_interaction_log_permissions(self):
        """Test permission controls for interaction logs"""
        # This would test read/write permissions based on user roles
        # Implementation depends on your permission structure
        pass
    
    def test_interaction_log_linking(self):
        """Test linking interaction logs to different document types"""
        # Test linking to different reference doctypes
        doctypes_to_test = ["Customer", "Lead", "Opportunity", "Issue"]
        
        for doctype in doctypes_to_test:
            if frappe.db.exists("DocType", doctype):
                log = frappe.get_doc({
                    "doctype": "Interaction Log",
                    "interaction_type": "Email",
                    "reference_doctype": doctype,
                    "reference_name": f"TEST-{doctype}",
                    "subject": f"Test {doctype} interaction"
                })
                log.insert()
                
                self.assertEqual(log.reference_doctype, doctype)
    
    def test_interaction_log_search(self):
        """Test searching through interaction logs"""
        # Create searchable content
        log = frappe.get_doc({
            "doctype": "Interaction Log",
            "interaction_type": "Email",
            "reference_doctype": "Test Document",
            "reference_name": "TEST-004",
            "subject": "Important meeting discussion",
            "content": "Discussed budget allocation and project timeline"
        })
        log.insert()
        
        # Search by content
        results = frappe.get_all("Interaction Log",
                               filters={"content": ["like", "%budget%"]},
                               fields=["name", "subject"])
        
        self.assertTrue(len(results) > 0)
    
    def test_interaction_log_status_updates(self):
        """Test status tracking in interaction logs"""
        log = frappe.get_doc({
            "doctype": "Interaction Log",
            "interaction_type": "Follow-up",
            "reference_doctype": "Test Document", 
            "reference_name": "TEST-005",
            "subject": "Status update",
            "status": "Open"
        })
        log.insert()
        
        # Update status
        log.status = "Completed"
        log.save()
        
        updated_log = frappe.get_doc("Interaction Log", log.name)
        self.assertEqual(updated_log.status, "Completed")
    
    def test_interaction_log_bulk_operations(self):
        """Test bulk operations on interaction logs"""
        # Create multiple logs
        logs = []
        for i in range(3):
            log = frappe.get_doc({
                "doctype": "Interaction Log",
                "interaction_type": "Email",
                "reference_doctype": "Test Document",
                "reference_name": f"BULK-TEST-{i}",
                "subject": f"Bulk test {i}"
            })
            log.insert()
            logs.append(log.name)
        
        # Test bulk retrieval
        bulk_logs = frappe.get_all("Interaction Log",
                                 filters={"name": ["in", logs]},
                                 fields=["name", "subject"])
        
        self.assertEqual(len(bulk_logs), 3)