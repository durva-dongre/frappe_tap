import unittest
import frappe
from frappe.test_runner import make_test_records

class TestStageFlow(unittest.TestCase):
    def setUp(self):
        """Set up test data before each test method"""
        frappe.clear_cache()
        frappe.set_user("Administrator")
        
    def test_stageflow_creation(self):
        """Test basic StageFlow document creation"""
        # Create a new StageFlow document
        stageflow_doc = frappe.get_doc({
            "doctype": "StageFlow",
            "stage_name": "Test Stage",
            "stage_order": 1,
            "description": "Test stage description"
        })
        
        # Insert the document
        stageflow_doc.insert(ignore_permissions=True)
        
        # Verify the document was created
        self.assertTrue(stageflow_doc.name)
        self.assertEqual(stageflow_doc.stage_name, "Test Stage")
        self.assertEqual(stageflow_doc.stage_order, 1)
        
        # Clean up
        stageflow_doc.delete()
        
    def test_stageflow_validation(self):
        """Test StageFlow document validation"""
        # Test with valid data
        stageflow_doc = frappe.get_doc({
            "doctype": "StageFlow",
            "stage_name": "Valid Stage",
            "stage_order": 2
        })
        
        # This should not raise any validation errors
        stageflow_doc.insert(ignore_permissions=True)
        self.assertTrue(stageflow_doc.name)
        
        # Clean up
        stageflow_doc.delete()
        
    def test_stageflow_stage_order_validation(self):
        """Test stage order validation"""
        # Create stage with order 1
        stage1 = frappe.get_doc({
            "doctype": "StageFlow",
            "stage_name": "First Stage",
            "stage_order": 1
        })
        stage1.insert(ignore_permissions=True)
        
        # Create stage with order 2
        stage2 = frappe.get_doc({
            "doctype": "StageFlow",
            "stage_name": "Second Stage", 
            "stage_order": 2
        })
        stage2.insert(ignore_permissions=True)
        
        # Verify both stages exist
        self.assertTrue(stage1.name)
        self.assertTrue(stage2.name)
        
        # Clean up
        stage1.delete()
        stage2.delete()
        
    def test_stageflow_get_doc(self):
        """Test retrieving StageFlow document"""
        # Create a stageflow
        stageflow_doc = frappe.get_doc({
            "doctype": "StageFlow",
            "stage_name": "Retrieve Test Stage",
            "stage_order": 3,
            "description": "Test description"
        })
        stageflow_doc.insert(ignore_permissions=True)
        
        # Retrieve the document
        retrieved_doc = frappe.get_doc("StageFlow", stageflow_doc.name)
        
        # Verify retrieved data
        self.assertEqual(retrieved_doc.stage_name, "Retrieve Test Stage")
        self.assertEqual(retrieved_doc.stage_order, 3)
        self.assertEqual(retrieved_doc.description, "Test description")
        
        # Clean up
        stageflow_doc.delete()
        
    def test_stageflow_update(self):
        """Test updating StageFlow document"""
        # Create a stageflow
        stageflow_doc = frappe.get_doc({
            "doctype": "StageFlow",
            "stage_name": "Update Test Stage",
            "stage_order": 4
        })
        stageflow_doc.insert(ignore_permissions=True)
        
        # Update the document
        stageflow_doc.stage_name = "Updated Stage Name"
        stageflow_doc.stage_order = 5
        stageflow_doc.save()
        
        # Verify the update
        self.assertEqual(stageflow_doc.stage_name, "Updated Stage Name")
        self.assertEqual(stageflow_doc.stage_order, 5)
        
        # Clean up
        stageflow_doc.delete()
        
    def test_stageflow_workflow_sequence(self):
        """Test workflow sequence functionality"""
        # Create multiple stages in sequence
        stages = []
        for i in range(1, 4):
            stage = frappe.get_doc({
                "doctype": "StageFlow",
                "stage_name": f"Stage {i}",
                "stage_order": i,
                "description": f"Description for stage {i}"
            })
            stage.insert(ignore_permissions=True)
            stages.append(stage)
        
        # Verify all stages were created with correct order
        for i, stage in enumerate(stages):
            self.assertEqual(stage.stage_order, i + 1)
            self.assertEqual(stage.stage_name, f"Stage {i + 1}")
        
        # Clean up
        for stage in stages:
            stage.delete()
        
    def tearDown(self):
        """Clean up after each test method"""
        frappe.db.rollback()
        frappe.clear_cache()

def make_test_records():
    """Create test records for StageFlow doctype"""
    pass
