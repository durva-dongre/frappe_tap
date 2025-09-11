

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os

# Add the project root to Python path if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestOnboardingFlowFunctions(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "job_123"
        self.current_time = datetime(2025, 9, 11, 16, 3)
        
        # Mock frappe module at module level
        self.frappe_patcher = patch.dict('sys.modules', {
            'frappe': MagicMock(),
            'frappe.utils': MagicMock(),
            'frappe.utils.background_jobs': MagicMock()
        })
        self.frappe_patcher.start()
        
        # Now import the actual functions
        from tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger import (
            trigger_onboarding_flow,
            _trigger_onboarding_flow_job,
            trigger_group_flow,
            trigger_individual_flows,
            get_stage_flow_statuses,
            get_students_from_onboarding,
            update_student_stage_progress,
            update_student_stage_progress_batch,
            get_job_status,
            get_onboarding_progress_report,
            update_incomplete_stages
        )
        
        # Store references to the actual functions
        self.trigger_onboarding_flow = trigger_onboarding_flow
        self.trigger_group_flow = trigger_group_flow
        self.trigger_individual_flows = trigger_individual_flows
        # ... store other functions
        
    def tearDown(self):
        """Clean up after each test."""
        self.frappe_patcher.stop()

    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    # def test_trigger_onboarding_flow_success(self, mock_frappe):
    #     """Test successful triggering of onboarding flow - with REAL logic execution"""
        
    #     # Configure mocks to return specific values
    #     mock_stage = MagicMock()
    #     mock_stage.is_active = True
    #     mock_stage.stage_flows = [
    #         MagicMock(
    #             student_status=self.mock_student_status,
    #             glific_flow_id=self.mock_flow_id,
    #             flow_type="Group"
    #         )
    #     ]
        
    #     mock_onboarding = MagicMock()
    #     mock_onboarding.status = "Processed"
        
    #     # Set up get_doc to return different objects based on doctype
    #     def get_doc_side_effect(doctype, name):
    #         if doctype == "OnboardingStage":
    #             return mock_stage
    #         elif doctype == "BackendStudentOnboardingSet":
    #             return mock_onboarding
    #         return MagicMock()
            
    #     mock_frappe.get_doc.side_effect = get_doc_side_effect
    #     mock_frappe.enqueue.return_value = self.mock_job_id
    #     mock_frappe.throw = Exception  # Make throw raise actual exceptions
        
    #     # Call the REAL function
    #     result = self.trigger_onboarding_flow(
    #         self.mock_onboarding_set, 
    #         self.mock_onboarding_stage, 
    #         self.mock_student_status
    #     )
        
    #     # Verify the result
    #     self.assertEqual(result, {"success": True, "job_id": self.mock_job_id})
        
    #     # Verify the function called frappe.enqueue
    #     mock_frappe.enqueue.assert_called_once()
        
    #     # Verify logger was called
    #     self.assertTrue(mock_frappe.logger.info.called)

    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    # def test_trigger_onboarding_flow_missing_inputs(self, mock_frappe):
    #     """Test validation logic is actually executed"""
    #     mock_frappe.throw = Exception
        
    #     # This should execute the actual validation logic
    #     with self.assertRaises(Exception) as cm:
    #         self.trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
        
    #     # Verify the specific error message
    #     mock_frappe.throw.assert_called_with(
    #         "Both Backend Student Onboarding Set and Onboarding Stage are required"
    #     )

    # @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    # def test_trigger_onboarding_flow_inactive_stage(self, mock_frappe):
    #     """Test inactive stage validation"""
    #     mock_stage = MagicMock()
    #     mock_stage.is_active = False
        
    #     mock_frappe.get_doc.return_value = mock_stage
    #     mock_frappe.throw = Exception
        
    #     with self.assertRaises(Exception):
    #         self.trigger_onboarding_flow(
    #             self.mock_onboarding_set, 
    #             self.mock_onboarding_stage, 
    #             self.mock_student_status
    #         )
        
    #     mock_frappe.throw.assert_called_with("Selected Onboarding Stage is not active")

    # Add more tests that actually exercise the code paths...
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    def test_trigger_group_flow_success_real_logic(self, mock_requests, mock_frappe):
        """Test group flow with minimal mocking to exercise real logic"""
        
        # Set up the minimum required mocks
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        mock_stage = MagicMock()
        mock_stage.name = self.mock_onboarding_stage
        
        mock_glific_settings = MagicMock()
        mock_glific_settings.api_url = "https://api.glific.org"
        
        mock_contact_group = MagicMock()
        mock_contact_group.group_id = "group_123"
        
        def get_doc_side_effect(doctype, name=None):
            if doctype == "GlificSettings":
                return mock_glific_settings
            elif doctype == "ContactGroup":
                return mock_contact_group
            return MagicMock()
        
        mock_frappe.get_doc.side_effect = get_doc_side_effect
        
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "startGroupFlow": {
                    "success": True,
                    "errors": []
                }
            }
        }
        mock_requests.post.return_value = mock_response
        
        # Mock other required functions
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding') as mock_get_students, \
             patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch') as mock_update_batch, \
             patch('tap_lms.glific_integration.create_or_get_glific_group_for_batch') as mock_create_group:
            
            mock_get_students.return_value = [MagicMock(name="STUD_001")]
            mock_create_group.return_value = {"group_id": "group_123"}
            
            # Call the real function
            result = self.trigger_group_flow(
                mock_onboarding,
                mock_stage,
                "Bearer token",
                self.mock_student_status,
                self.mock_flow_id
            )
            
            # Verify results
            self.assertIn("group_flow_result", result)
            self.assertEqual(result["group_count"], 1)
            
            # Verify actual HTTP call was made
            mock_requests.post.assert_called_once()
            mock_update_batch.assert_called_once()

