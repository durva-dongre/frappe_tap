import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

def setup_frappe_mocks():
    """Setup comprehensive frappe mocks"""
    mock_frappe = Mock()
    mock_frappe.db = Mock()
    mock_frappe.logger = Mock()
    mock_frappe.logger.return_value = Mock()
    
    # Mock enqueue
    mock_enqueue = Mock()
    
    sys.modules['frappe'] = mock_frappe
    sys.modules['frappe.utils'] = Mock()
    sys.modules['frappe.utils.background_jobs'] = Mock()
    sys.modules['frappe.utils.background_jobs'].enqueue = mock_enqueue
    
    return mock_frappe, mock_enqueue

def setup_glific_mocks():
    """Setup glific integration mocks"""
    mock_glific = Mock()
    mock_glific.optin_contact = Mock()
    mock_glific.start_contact_flow = Mock()
    mock_glific.create_or_get_teacher_group_for_batch = Mock()
    mock_glific.add_contact_to_group = Mock()
    
    sys.modules['tap_lms.background_jobs.glific_integration'] = mock_glific
    
    return mock_glific

class TestProcessGlificActions:
    
    def setup_method(self):
        """Setup before each test"""
        self.mock_frappe, self.mock_enqueue = setup_frappe_mocks()
        self.mock_glific = setup_glific_mocks()
        
        # Clear any existing modules
        if 'tap_lms.background_jobs' in sys.modules:
            del sys.modules['tap_lms.background_jobs']

    @patch('tap_lms.background_jobs.optin_contact')
    @patch('tap_lms.background_jobs.start_contact_flow')
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    @patch('tap_lms.background_jobs.add_contact_to_group')
    def test_process_glific_actions_success_flow(self, mock_add_contact, mock_create_group, 
                                               mock_start_flow, mock_optin):
        """Test successful process_glific_actions execution"""
        # Setup mocks
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        mock_create_group.return_value = {"group_id": "group_789", "label": "Test Group"}
        mock_add_contact.return_value = True
        mock_start_flow.return_value = True
        
        from tap_lms.background_jobs import process_glific_actions
        
        # Execute
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify calls
        mock_optin.assert_called_once_with("1234567890", "John")
        self.mock_frappe.db.get_value.assert_any_call("Teacher", "teacher_1", "glific_id")
        mock_create_group.assert_called_once_with("Batch A", "batch_1")
        mock_add_contact.assert_called_once_with("glific_123", "group_789")
        mock_start_flow.assert_called_once()

    @patch('tap_lms.background_jobs.optin_contact')
    def test_process_glific_actions_optin_failure(self, mock_optin):
        """Test process_glific_actions when optin fails"""
        mock_optin.return_value = False
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify optin was called and error was logged
        mock_optin.assert_called_once_with("1234567890", "John")
        self.mock_frappe.logger().error.assert_called()

    @patch('tap_lms.background_jobs.optin_contact')
    def test_process_glific_actions_no_glific_id(self, mock_optin):
        """Test process_glific_actions when glific_id not found"""
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.return_value = None
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify error was logged for missing glific_id
        error_calls = self.mock_frappe.logger().error.call_args_list
        assert any("Glific ID not found" in str(call) for call in error_calls)

    @patch('tap_lms.background_jobs.optin_contact')
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    def test_process_glific_actions_no_valid_batch(self, mock_create_group, mock_optin):
        """Test process_glific_actions with no valid batch_id"""
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        
        from tap_lms.background_jobs import process_glific_actions
        
        # Test with no_active_batch_id
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "no_active_batch_id"
        )
        
        # Verify group creation was not called
        mock_create_group.assert_not_called()
        self.mock_frappe.logger().info.assert_called()

    @patch('tap_lms.background_jobs.optin_contact')
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    @patch('tap_lms.background_jobs.add_contact_to_group')
    def test_process_glific_actions_group_creation_failure(self, mock_add_contact, 
                                                         mock_create_group, mock_optin):
        """Test process_glific_actions when group creation fails"""
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        mock_create_group.return_value = None
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify warning was logged
        self.mock_frappe.logger().warning.assert_called()
        mock_add_contact.assert_not_called()

    @patch('tap_lms.background_jobs.optin_contact')
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    @patch('tap_lms.background_jobs.add_contact_to_group')
    def test_process_glific_actions_add_contact_failure(self, mock_add_contact, 
                                                       mock_create_group, mock_optin):
        """Test process_glific_actions when adding contact to group fails - covers line 38"""
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        mock_create_group.return_value = {"group_id": "group_789", "label": "Test Group"}
        mock_add_contact.return_value = False  # Simulate add contact failure
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify add_contact was called but failed
        mock_add_contact.assert_called_once_with("glific_123", "group_789")
        # Verify warning was logged for failed group addition (line 38)
        warning_calls = self.mock_frappe.logger().warning.call_args_list
        assert any("Failed to add teacher" in str(call) for call in warning_calls)

    @patch('tap_lms.background_jobs.optin_contact')
    @patch('tap_lms.background_jobs.start_contact_flow')
    def test_process_glific_actions_no_flow_found(self, mock_start_flow, mock_optin):
        """Test process_glific_actions when flow not found"""
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.side_effect = ["glific_123", None]
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify error was logged and flow was not started
        error_calls = self.mock_frappe.logger().error.call_args_list
        assert any("Glific flow not found" in str(call) for call in error_calls)
        mock_start_flow.assert_not_called()

    @patch('tap_lms.background_jobs.optin_contact')
    def test_process_glific_actions_exception_handling(self, mock_optin):
        """Test process_glific_actions exception handling"""
        mock_optin.side_effect = Exception("Test exception")
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify exception was logged
        error_calls = self.mock_frappe.logger().error.call_args_list
        assert any("Error in process_glific_actions" in str(call) for call in error_calls)

    @patch('tap_lms.background_jobs.optin_contact')
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    def test_process_glific_actions_group_exception(self, mock_create_group, mock_optin):
        """Test process_glific_actions when group operations raise exception"""
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        mock_create_group.side_effect = Exception("Group creation failed")
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "Batch A", "batch_1"
        )
        
        # Verify error was logged but process continued
        error_calls = self.mock_frappe.logger().error.call_args_list
        assert any("Error managing teacher group" in str(call) for call in error_calls)

class TestEnqueueGlificActions:
    
    def setup_method(self):
        """Setup before each test"""
        self.mock_frappe, self.mock_enqueue = setup_frappe_mocks()

    # def test_enqueue_glific_actions(self):
    #     """Test enqueue_glific_actions function"""
    #     from tap_lms.background_jobs import enqueue_glific_actions
        
    #     enqueue_glific_actions(
    #         "teacher_1", "1234567890", "John", "school_1",
    #         "Test School", "en", "model_1", "Batch A", "batch_1"
    #     )
        
    #     # Verify enqueue was called with correct parameters
    #     self.mock_enqueue.assert_called_once()
    #     call_args = self.mock_enqueue.call_args
        
    #     # Check positional arguments
    #     assert call_args[0][0].__name__ == 'process_glific_actions'
        
    #     # Check keyword arguments
    #     kwargs = call_args[1]
    #     assert kwargs['queue'] == "short"
    #     assert kwargs['timeout'] == 300
    #     assert kwargs['teacher_id'] == "teacher_1"
    #     assert kwargs['phone'] == "1234567890"
    #     assert kwargs['first_name'] == "John"
    #     assert kwargs['school'] == "school_1"
    #     assert kwargs['school_name'] == "Test School"
    #     assert kwargs['language'] == "en"
    #     assert kwargs['model_name'] == "model_1"
    #     assert kwargs['batch_name'] == "Batch A"
    #     assert kwargs['batch_id'] == "batch_1"

class TestImportStatements:
    
    def test_import_coverage(self):
        """Test all import statements are covered"""
        # Setup mocks
        setup_frappe_mocks()
        setup_glific_mocks()
        
        # Import the module to cover import statements
        import tap_lms.background_jobs
        
        # Verify module was imported successfully
        assert tap_lms.background_jobs is not None
        assert hasattr(tap_lms.background_jobs, 'process_glific_actions')
        assert hasattr(tap_lms.background_jobs, 'enqueue_glific_actions')

class TestEdgeCases:
    
    def setup_method(self):
        """Setup before each test"""
        self.mock_frappe, self.mock_enqueue = setup_frappe_mocks()
        self.mock_glific = setup_glific_mocks()

    @patch('tap_lms.background_jobs.optin_contact')
    @patch('tap_lms.background_jobs.start_contact_flow')
    @patch('tap_lms.background_jobs.create_or_get_teacher_group_for_batch')
    @patch('tap_lms.background_jobs.add_contact_to_group')
    def test_empty_batch_name(self, mock_add_contact, mock_create_group, 
                             mock_start_flow, mock_optin):
        """Test with empty batch_name"""
        mock_optin.return_value = True
        self.mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
        
        from tap_lms.background_jobs import process_glific_actions
        
        process_glific_actions(
            "teacher_1", "1234567890", "John", "school_1", 
            "Test School", "en", "model_1", "", "batch_1"
        )
        
        # Verify group creation was not called due to empty batch_name
        mock_create_group.assert_not_called()

    # @patch('tap_lms.background_jobs.optin_contact')
    # @patch('tap_lms.background_jobs.start_contact_flow')
    # def test_flow_start_failure(self, mock_start_flow, mock_optin):
    #     """Test when flow start fails - covers line 62"""
    #     mock_optin.return_value = True
    #     self.mock_frappe.db.get_value.side_effect = ["glific_123", "flow_456"]
    #     mock_start_flow.return_value = False
        
    #     from tap_lms.background_jobs import process_glific_actions
        
    #     process_glific_actions(
    #         "teacher_1", "1234567890", "John", "school_1", 
    #         "Test School", "en", "model_1", "Batch A", "batch_1"
    #     )
        
    #     # Verify flow start was attempted
    #     mock_start_flow.assert_called_once()
    #     # Verify error was logged for flow start failure (line 62)
    #     error_calls = self.mock_frappe.logger().error.call_args_list
    #     assert any("Failed to start onboarding flow" in str(call) for call in error_calls)