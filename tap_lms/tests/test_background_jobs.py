import pytest
import sys
from unittest.mock import Mock, patch

# Simple mock setup
mock_frappe = Mock()
mock_frappe.db = Mock()
mock_frappe.logger = Mock()
mock_frappe.logger.return_value = Mock()

sys.modules['frappe'] = mock_frappe
sys.modules['frappe.utils'] = Mock()
sys.modules['frappe.utils.background_jobs'] = Mock()

# Mock all the glific functions
sys.modules['tap_lms.background_jobs.glific_integration'] = Mock()

class TestBackgroundJobs:
    
    @patch('tap_lms.background_jobs.optin_contact')
    def test_optin_failure(self, mock_optin):
        """Test when optin fails"""
        mock_optin.return_value = False
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions("teacher_1", "1234567890", "John", "school_1", 
                             "Test School", "en", "model_1", "Batch A", "batch_1")
        
        mock_optin.assert_called_once()

    @patch('tap_lms.background_jobs.start_contact_flow')
    @patch('tap_lms.background_jobs.add_contact_to_group') 
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    @patch('tap_lms.background_jobs.optin_contact')
    def test_flow_failure(self, mock_optin, mock_create_group, mock_add_contact, mock_start_flow):
        """Test when flow start fails - covers missing line"""
        mock_optin.return_value = True
        mock_create_group.return_value = {"group_id": "123", "label": "test"}
        mock_add_contact.return_value = True
        mock_start_flow.return_value = False  # This will trigger the error line
        
        mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions("teacher_1", "1234567890", "John", "school_1", 
                             "Test School", "en", "model_1", "Batch A", "batch_1")
        
        mock_start_flow.assert_called_once()

    @patch('tap_lms.background_jobs.add_contact_to_group')
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    @patch('tap_lms.background_jobs.optin_contact')
    def test_add_contact_failure(self, mock_optin, mock_create_group, mock_add_contact):
        """Test when add contact fails - covers missing line"""
        mock_optin.return_value = True
        mock_create_group.return_value = {"group_id": "123", "label": "test"}
        mock_add_contact.return_value = False  # This will trigger the warning line
        
        mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions("teacher_1", "1234567890", "John", "school_1", 
                             "Test School", "en", "model_1", "Batch A", "batch_1")
        
        mock_add_contact.assert_called_once()

    @patch('frappe.utils.background_jobs.enqueue')
    def test_enqueue_function(self, mock_enqueue):
        """Test enqueue function"""
        from tap_lms.background_jobs import enqueue_glific_actions
        
        enqueue_glific_actions("teacher_1", "1234567890", "John", "school_1",
                             "Test School", "en", "model_1", "Batch A", "batch_1")
        
        mock_enqueue.assert_called_once()

    def test_import_coverage(self):
        """Test imports work"""
        import tap_lms.background_jobs
        assert hasattr(tap_lms.background_jobs, 'process_glific_actions')
        assert hasattr(tap_lms.background_jobs, 'enqueue_glific_actions')