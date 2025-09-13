import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import sys
import os
import json

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
            'frappe.utils.background_jobs': MagicMock(),
            'tap_lms.glific_integration': MagicMock()
        })
        self.frappe_patcher.start()
        
        # Import after patching
        from tap_lms.tap_lms.page.onboarding_flow_trigger import onboarding_flow_trigger
        
        # Store references to the actual functions
        self.module = onboarding_flow_trigger
        self.trigger_onboarding_flow = onboarding_flow_trigger.trigger_onboarding_flow
        self._trigger_onboarding_flow_job = onboarding_flow_trigger._trigger_onboarding_flow_job
        self.trigger_group_flow = onboarding_flow_trigger.trigger_group_flow
        self.trigger_individual_flows = onboarding_flow_trigger.trigger_individual_flows
        self.get_stage_flow_statuses = onboarding_flow_trigger.get_stage_flow_statuses
        self.get_students_from_onboarding = onboarding_flow_trigger.get_students_from_onboarding
        self.update_student_stage_progress = onboarding_flow_trigger.update_student_stage_progress
        self.update_student_stage_progress_batch = onboarding_flow_trigger.update_student_stage_progress_batch
        self.get_job_status = onboarding_flow_trigger.get_job_status
        self.get_onboarding_progress_report = onboarding_flow_trigger.get_onboarding_progress_report
        self.update_incomplete_stages = onboarding_flow_trigger.update_incomplete_stages
        
    def tearDown(self):
        """Clean up after each test."""
        self.frappe_patcher.stop()

    # ============= Main Entry Point Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_missing_parameters(self, mock_frappe):
        """Test trigger_onboarding_flow with missing parameters"""
        mock_frappe.throw = Mock(side_effect=Exception("Parameters required"))
        mock_frappe.logger.return_value = MagicMock()
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(None, None, None)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_inactive_stage(self, mock_frappe):
        """Test trigger_onboarding_flow with inactive stage"""
        mock_stage = MagicMock()
        mock_stage.is_active = False
        mock_frappe.get_doc.return_value = mock_stage
        mock_frappe.throw = Mock(side_effect=Exception("Stage not active"))
        mock_frappe.logger.return_value = MagicMock()
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "status")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_wrong_onboarding_status(self, mock_frappe):
        """Test trigger_onboarding_flow with wrong onboarding status"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Draft"
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_frappe.throw = Mock(side_effect=Exception("Not processed"))
        mock_frappe.logger.return_value = MagicMock()
        
        with self.assertRaises(Exception):
            self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "status")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_with_child_table(self, mock_frappe):
        """Test trigger_onboarding_flow with new child table structure"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.name = self.mock_onboarding_stage
        mock_stage.stage_flows = [
            MagicMock(student_status="not_started", glific_flow_id="flow_123", flow_type="Group")
        ]
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_frappe.enqueue.return_value = "job_123"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "not_started")
        
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "job_123")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_onboarding_flow_legacy_structure(self, mock_frappe):
        """Test trigger_onboarding_flow with legacy field structure"""
        mock_stage = MagicMock()
        mock_stage.is_active = True
        mock_stage.name = self.mock_onboarding_stage
        mock_stage.stage_flows = []  # Empty child table
        mock_stage.glific_flow_id = "legacy_flow_123"
        mock_stage.glific_flow_type = "Individual"
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_frappe.enqueue.return_value = "job_123"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "status")
        
        self.assertTrue(result["success"])

    # ============= Background Job Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow')
    def test_trigger_onboarding_flow_job_group_success(self, mock_trigger_group, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job with successful group flow"""
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding, MagicMock()]
        mock_trigger_group.return_value = {"success": True}
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "Group")
        
        self.assertEqual(result, {"success": True})
        mock_trigger_group.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_individual_flows')
    def test_trigger_onboarding_flow_job_individual_success(self, mock_trigger_individual, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job with successful individual flow"""
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_frappe.get_doc.side_effect = [mock_stage, mock_onboarding, MagicMock()]
        mock_trigger_individual.return_value = {"success": True}
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "Individual")
        
        self.assertEqual(result, {"success": True})
        mock_trigger_individual.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_auth_none(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job with no auth"""
        mock_auth.return_value = None
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "type")
        
        self.assertIn("error", result)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_missing_auth_token(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job with missing authorization in headers"""
        mock_auth.return_value = {"some_key": "some_value"}  # No authorization key
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "type")
        
        self.assertIn("error", result)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_exception_handling(self, mock_auth, mock_frappe):
        """Test _trigger_onboarding_flow_job exception handling"""
        mock_auth.return_value = {"authorization": "Bearer token"}
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.log_error = MagicMock()
        mock_frappe.logger.return_value = MagicMock()
        
        result = self._trigger_onboarding_flow_job("set", "stage", "status", "flow", "Group")
        
        self.assertIn("error", result)
        mock_frappe.log_error.assert_called_once()

    # ============= Group Flow Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_group_flow_no_flow_id(self, mock_frappe):
        """Test trigger_group_flow with no flow ID"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("No flow ID"))
        
        with self.assertRaises(Exception):
            self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, None)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_no_contact_group(self, mock_create_group, mock_frappe):
        """Test trigger_group_flow with no contact group"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_create_group.return_value = None
        mock_frappe.throw = Mock(side_effect=Exception("No contact group"))
        mock_frappe.logger.return_value = MagicMock()
        
        with self.assertRaises(Exception):
            self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_trigger_group_flow_success(self, mock_get_students, mock_update_batch, mock_create_group, mock_requests, mock_frappe):
        """Test successful group flow trigger"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING"
        mock_stage = MagicMock()
        mock_stage.name = "TEST_STAGE"
        
        mock_contact_group = MagicMock()
        mock_settings = MagicMock()
        mock_settings.api_url = "https://api.glific.com"
        
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_get_students.return_value = [MagicMock(), MagicMock(), MagicMock()]  # 3 students
        mock_frappe.logger.return_value = MagicMock()
        
        def mock_get_doc_side_effect(doctype, filters=None):
            if doctype == "Glific Settings":
                return mock_settings
            if doctype == "GlificContactGroup":
                mock_group = MagicMock()
                mock_group.group_id = "group_123"
                return mock_group
            return mock_contact_group
        
        mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": True}}
        }
        mock_requests.post.return_value = mock_response
        
        result = self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        
        self.assertEqual(result["group_count"], 3)
        mock_update_batch.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_trigger_group_flow_empty_students(self, mock_get_students, mock_create_group, mock_requests, mock_frappe):
        """Test group flow with empty students list"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        
        mock_settings = MagicMock()
        mock_settings.api_url = "https://api.glific.com"
        
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_get_students.return_value = []  # No students
        mock_frappe.logger.return_value = MagicMock()
        
        def mock_get_doc_side_effect(doctype, filters=None):
            if doctype == "Glific Settings":
                return mock_settings
            mock_group = MagicMock()
            mock_group.group_id = "group_123"
            return mock_group
        
        mock_frappe.get_doc.side_effect = mock_get_doc_side_effect
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": True}}
        }
        mock_requests.post.return_value = mock_response
        
        result = self.trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        
        self.assertEqual(result["group_count"], 0)

    # ============= Individual Flow Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_trigger_individual_flows_no_flow_id(self, mock_frappe):
        """Test trigger_individual_flows with no flow ID"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_frappe.throw = Mock(side_effect=Exception("No flow ID"))
        
        with self.assertRaises(Exception):
            self.trigger_individual_flows(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, None)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('time.sleep')
    def test_trigger_individual_flows_batch_processing(self, mock_sleep, mock_update_progress, mock_get_students, mock_start_flow, mock_frappe):
        """Test trigger_individual_flows with batch processing (>10 students)"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        
        # Create 15 students to test batch processing
        students = []
        for i in range(15):
            student = MagicMock()
            student.name = f"STUD_{i:03d}"
            student.name1 = f"Student {i}"
            student.glific_id = f"contact_{i:03d}"
            students.append(student)
        
        mock_get_students.return_value = students
        mock_start_flow.return_value = True
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.db.commit.return_value = None
        
        result = self.trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", 
            self.mock_student_status, self.mock_flow_id
        )
        
        self.assertEqual(result["individual_count"], 15)
        self.assertEqual(mock_start_flow.call_count, 15)
        # Should sleep once between batches (15 students = 2 batches)
        mock_sleep.assert_called_once_with(2)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_trigger_individual_flows_all_missing_glific_id(self, mock_get_students, mock_frappe):
        """Test trigger_individual_flows with all students missing glific_id"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        
        students = []
        for i in range(3):
            student = MagicMock()
            student.name = f"STUD_{i:03d}"
            student.glific_id = None  # All missing glific_id
            students.append(student)
        
        mock_get_students.return_value = students
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.db.commit.return_value = None
        
        result = self.trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", 
            self.mock_student_status, self.mock_flow_id
        )
        
        self.assertEqual(result["individual_count"], 0)
        self.assertEqual(result["error_count"], 0)

    # ============= Get Stage Flow Statuses Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_with_child_table(self, mock_frappe):
        """Test get_stage_flow_statuses with new child table structure"""
        mock_stage = MagicMock()
        mock_stage.stage_flows = [
            MagicMock(student_status="not_started"),
            MagicMock(student_status="completed"),
            MagicMock(student_status="not_started")  # Duplicate
        ]
        
        mock_frappe.get_doc.return_value = mock_stage
        
        result = self.get_stage_flow_statuses("STAGE_001")
        
        self.assertEqual(len(result["statuses"]), 2)
        self.assertIn("not_started", result["statuses"])
        self.assertIn("completed", result["statuses"])
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_legacy_structure(self, mock_frappe):
        """Test get_stage_flow_statuses with legacy structure"""
        mock_stage = MagicMock()
        mock_stage.stage_flows = []
        mock_stage.glific_flow_id = "legacy_flow"
        
        mock_frappe.get_doc.return_value = mock_stage
        
        result = self.get_stage_flow_statuses("STAGE_001")
        
        self.assertEqual(len(result["statuses"]), 6)  # All default statuses
        self.assertIn("not_started", result["statuses"])
        self.assertIn("completed", result["statuses"])
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_no_flows(self, mock_frappe):
        """Test get_stage_flow_statuses with no flows configured"""
        mock_stage = MagicMock()
        mock_stage.stage_flows = []
        
        # Ensure glific_flow_id doesn't exist
        if hasattr(mock_stage, 'glific_flow_id'):
            delattr(mock_stage, 'glific_flow_id')
        
        mock_frappe.get_doc.return_value = mock_stage
        
        result = self.get_stage_flow_statuses("STAGE_001")
        
        self.assertEqual(result["statuses"], [])
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_stage_flow_statuses_exception(self, mock_frappe):
        """Test get_stage_flow_statuses exception handling"""
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.log_error = MagicMock()
        
        result = self.get_stage_flow_statuses("STAGE_001")
        
        self.assertEqual(result["statuses"], [])
        self.assertIn("error", result)

    # ============= Get Students from Onboarding Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_with_stage_filter(self, mock_frappe):
        """Test get_students_from_onboarding with stage_name filter"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        backend_students = [{"student_id": "STUD_001"}]
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        
        # Mock calls in order: backend students, student doc, stage progress
        mock_frappe.get_all.side_effect = [
            backend_students,  # Backend students
            [{"name": "PROGRESS_001"}]  # Stage progress exists
        ]
        mock_frappe.get_doc.return_value = mock_student
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding, "STAGE_001")
        
        self.assertEqual(len(result), 1)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_with_status_filter(self, mock_frappe):
        """Test get_students_from_onboarding with student_status filter"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        backend_students = [{"student_id": "STUD_001"}]
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        
        mock_frappe.get_all.side_effect = [
            backend_students,  # Backend students
            [{"name": "PROGRESS_001"}]  # Stage progress with matching status
        ]
        mock_frappe.get_doc.return_value = mock_student
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding, "STAGE_001", "completed")
        
        self.assertEqual(len(result), 1)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_not_started_status(self, mock_frappe):
        """Test get_students_from_onboarding with not_started status"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = self.mock_onboarding_set
        
        backend_students = [
            {"student_id": "STUD_001"},
            {"student_id": "STUD_002"}
        ]
        mock_student1 = MagicMock()
        mock_student1.name = "STUD_001"
        mock_student2 = MagicMock()
        mock_student2.name = "STUD_002"
        
        # Mock calls: backend students, then alternating student docs and stage progress checks
        mock_frappe.get_all.side_effect = [
            backend_students,  # Backend students
            [],  # No stage progress for STUD_001
            [{"name": "PROGRESS_001"}],  # Stage progress exists for STUD_002
            [],  # Check again for STUD_001 in not_started section
            [{"name": "PROGRESS_001"}]  # Check again for STUD_002 in not_started section
        ]
        mock_frappe.get_doc.side_effect = [mock_student1, mock_student2, mock_student1, mock_student2]
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding, "STAGE_001", "not_started")
        
        # Only STUD_001 should be in result (no stage progress = not_started)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "STUD_001")

    # ============= Update Student Stage Progress Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_update_not_started(self, mock_now, mock_frappe):
        """Test updating from not_started to assigned status"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_stage = MagicMock()
        
        existing = [{"name": "PROGRESS_001"}]
        mock_frappe.get_all.return_value = existing
        
        mock_progress = MagicMock()
        mock_progress.status = "not_started"
        mock_progress.start_timestamp = None
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        self.assertEqual(mock_progress.status, "assigned")
        self.assertEqual(mock_progress.start_timestamp, self.current_time)
        mock_progress.save.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_update_incomplete(self, mock_now, mock_frappe):
        """Test updating from incomplete to assigned status"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_stage = MagicMock()
        
        existing = [{"name": "PROGRESS_001"}]
        mock_frappe.get_all.return_value = existing
        
        mock_progress = MagicMock()
        mock_progress.status = "incomplete"
        mock_progress.start_timestamp = self.current_time - timedelta(days=5)
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        self.assertEqual(mock_progress.status, "assigned")
        mock_progress.save.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_skip_in_progress(self, mock_now, mock_frappe):
        """Test not updating in_progress status"""
        mock_now.return_value = self.current_time
        mock_student = MagicMock()
        mock_stage = MagicMock()
        
        existing = [{"name": "PROGRESS_001"}]
        mock_frappe.get_all.return_value = existing
        
        mock_progress = MagicMock()
        mock_progress.status = "in_progress"
        mock_frappe.get_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress(mock_student, mock_stage)
        
        mock_progress.save.assert_not_called()

    # ============= Update Student Stage Progress Batch Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_batch_mixed(self, mock_now, mock_frappe):
        """Test batch update with mix of existing and new records"""
        mock_now.return_value = self.current_time
        
        students = [
            MagicMock(name="STUD_001"),
            MagicMock(name="STUD_002"),
            MagicMock(name="STUD_003")
        ]
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        # Mock existing progress for STUD_001, none for others
        mock_frappe.get_all.side_effect = [
            [{"name": "PROGRESS_001"}],  # STUD_001 has existing
            [],  # STUD_002 doesn't exist
            []   # STUD_003 doesn't exist
        ]
        
        mock_existing_progress = MagicMock()
        mock_existing_progress.status = "not_started"
        mock_new_progress = MagicMock()
        
        mock_frappe.get_doc.return_value = mock_existing_progress
        mock_frappe.new_doc.return_value = mock_new_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress_batch(students, mock_stage)
        
        mock_existing_progress.save.assert_called_once()
        self.assertEqual(mock_new_progress.insert.call_count, 2)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress_batch_error_handling(self, mock_now, mock_frappe):
        """Test batch update with individual student failures"""
        mock_now.return_value = self.current_time
        
        students = [
            MagicMock(name="STUD_001"),
            MagicMock(name="STUD_002")
        ]
        mock_stage = MagicMock()
        
        # First student succeeds, second fails
        mock_frappe.get_all.side_effect = [
            [],  # STUD_001
            Exception("Database error")  # STUD_002 fails
        ]
        
        mock_progress = MagicMock()
        mock_frappe.new_doc.return_value = mock_progress
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_student_stage_progress_batch(students, mock_stage)
        
        # Should still commit despite one failure
        mock_frappe.db.commit.assert_called_once()

    # ============= Get Job Status Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    def test_get_job_status_finished(self, mock_get_status, mock_frappe):
        """Test get_job_status with finished job"""
        mock_get_status.return_value = "finished"
        mock_frappe.logger.return_value = MagicMock()
        
        # Need to mock the actual Job fetch
        with patch('rq.job.Job.fetch') as mock_fetch:
            mock_job = MagicMock()
            mock_job.result = {"success": True, "data": "test"}
            mock_fetch.return_value = mock_job
            
            with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_redis_conn') as mock_redis:
                mock_redis.return_value = MagicMock()
                
                result = self.get_job_status("job_123")
                
                self.assertEqual(result["status"], "complete")
                self.assertIn("results", result)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    def test_get_job_status_failed(self, mock_get_status, mock_frappe):
        """Test get_job_status with failed job"""
        mock_get_status.return_value = "failed"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_job_status("job_123")
        
        self.assertEqual(result["status"], "failed")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    def test_get_job_status_started(self, mock_get_status, mock_frappe):
        """Test get_job_status with started job"""
        mock_get_status.return_value = "started"
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_job_status("job_123")
        
        self.assertEqual(result["status"], "started")
    
    def test_get_job_status_no_job_id(self):
        """Test get_job_status with no job_id"""
        result = self.get_job_status(None)
        
        self.assertEqual(result["status"], "unknown")
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_job_status_exception(self, mock_frappe):
        """Test get_job_status exception handling"""
        mock_frappe.log_error = MagicMock()
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status') as mock_get_status:
            mock_get_status.side_effect = Exception("Redis error")
            
            result = self.get_job_status("job_123")
            
            self.assertEqual(result["status"], "error")
            self.assertIn("message", result)

    # ============= Get Onboarding Progress Report Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_all_filters(self, mock_frappe):
        """Test get_onboarding_progress_report with all filters"""
        progress_records = [
            {
                "name": "PROG_001",
                "student": "STUD_001",
                "stage": "STAGE_001",
                "status": "completed",
                "start_timestamp": self.current_time,
                "last_activity_timestamp": self.current_time,
                "completion_timestamp": self.current_time
            }
        ]
        
        mock_frappe.get_all.side_effect = [
            progress_records,  # Progress records
            [{"student_id": "STUD_001"}]  # Backend students check
        ]
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.name1 = "Student One"
        mock_student.phone = "1234567890"
        
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        mock_frappe.get_doc.side_effect = [mock_student, mock_stage]
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_onboarding_progress_report(set="SET_001", stage="STAGE_001", status="completed")
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(len(result["details"]), 1)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_onboarding_progress_report_not_started_handling(self, mock_frappe):
        """Test get_onboarding_progress_report with not_started status"""
        # No progress records exist
        mock_frappe.get_all.side_effect = [
            [],  # No progress records
            [{"student_id": "STUD_001"}],  # Backend students
            []  # No stage progress for STUD_001
        ]
        
        mock_student = MagicMock()
        mock_student.name = "STUD_001"
        mock_student.name1 = "Student One"
        mock_student.phone = "1234567890"
        
        mock_stage = MagicMock()
        mock_stage.name = "STAGE_001"
        
        mock_frappe.get_doc.side_effect = [mock_student, mock_stage]
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_onboarding_progress_report(set="SET_001", stage="STAGE_001", status="not_started")
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["not_started"], 1)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.traceback')
    def test_get_onboarding_progress_report_exception(self, mock_traceback, mock_frappe):
        """Test get_onboarding_progress_report exception handling"""
        mock_frappe.get_all.side_effect = Exception("Database error")
        mock_frappe.throw = Mock(side_effect=Exception("Report error"))
        mock_traceback.format_exc.return_value = "Mock traceback"
        mock_frappe.logger.return_value = MagicMock()
        
        with self.assertRaises(Exception):
            self.get_onboarding_progress_report()

    # ============= Update Incomplete Stages Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages_success(self, mock_add_to_date, mock_now, mock_frappe):
        """Test update_incomplete_stages successful update"""
        mock_now.return_value = self.current_time
        mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
        incomplete_records = [
            {"name": "PROGRESS_001", "student": "STUD_001", "stage": "STAGE_001", "start_timestamp": self.current_time - timedelta(days=4)},
            {"name": "PROGRESS_002", "student": "STUD_002", "stage": "STAGE_001", "start_timestamp": self.current_time - timedelta(days=5)}
        ]
        
        mock_frappe.get_all.return_value = incomplete_records
        
        mock_progress1 = MagicMock()
        mock_progress1.status = "assigned"
        mock_progress2 = MagicMock()
        mock_progress2.status = "assigned"
        
        mock_frappe.get_doc.side_effect = [mock_progress1, mock_progress2]
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_incomplete_stages()
        
        self.assertEqual(mock_progress1.status, "incomplete")
        self.assertEqual(mock_progress2.status, "incomplete")
        mock_progress1.save.assert_called_once()
        mock_progress2.save.assert_called_once()
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages_partial_failure(self, mock_add_to_date, mock_now, mock_frappe):
        """Test update_incomplete_stages with partial failure"""
        mock_now.return_value = self.current_time
        mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
        incomplete_records = [
            {"name": "PROGRESS_001", "student": "STUD_001", "stage": "STAGE_001"},
            {"name": "PROGRESS_002", "student": "STUD_002", "stage": "STAGE_001"}
        ]
        
        mock_frappe.get_all.return_value = incomplete_records
        
        mock_progress1 = MagicMock()
        
        # First succeeds, second fails
        mock_frappe.get_doc.side_effect = [mock_progress1, Exception("Database error")]
        mock_frappe.logger.return_value = MagicMock()
        
        self.update_incomplete_stages()
        
        # Should still commit despite one failure
        mock_frappe.db.commit.assert_called_once()

    # ============= Edge Cases and Integration Tests =============
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('time.sleep')
    def test_trigger_individual_flows_large_batch(self, mock_sleep, mock_get_students, mock_start_flow, mock_frappe):
        """Test trigger_individual_flows with very large student set (>100)"""
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        
        # Create 105 students
        students = []
        for i in range(105):
            student = MagicMock()
            student.name = f"STUD_{i:03d}"
            student.name1 = f"Student {i}"
            student.glific_id = f"contact_{i:03d}"
            students.append(student)
        
        mock_get_students.return_value = students
        mock_start_flow.return_value = True
        mock_frappe.logger.return_value = MagicMock()
        mock_frappe.db.commit.return_value = None
        
        result = self.trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", 
            self.mock_student_status, self.mock_flow_id
        )
        
        self.assertEqual(result["individual_count"], 105)
        # Should sleep 10 times (105 students = 11 batches - 1)
        self.assertEqual(mock_sleep.call_count, 10)
    
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe')
    def test_get_students_from_onboarding_special_characters(self, mock_frappe):
        """Test get_students_from_onboarding with special characters in names"""
        mock_onboarding = MagicMock()
        mock_onboarding.name = "TEST_ONBOARDING_#$%"
        
        backend_students = [{"student_id": "STUD_001'DROP TABLE"}]
        mock_student = MagicMock()
        mock_student.name = "STUD_001'DROP TABLE"
        
        mock_frappe.get_all.return_value = backend_students
        mock_frappe.get_doc.return_value = mock_student
        mock_frappe.logger.return_value = MagicMock()
        
        result = self.get_students_from_onboarding(mock_onboarding)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "STUD_001'DROP TABLE")


if __name__ == '__main__':
    unittest.main()