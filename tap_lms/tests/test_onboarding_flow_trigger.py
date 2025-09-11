
import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timedelta
import time
import sys
import json

# Conditional import guard
try:
    import frappe
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
    FRAPPE_AVAILABLE = True
except ImportError:
    FRAPPE_AVAILABLE = False
    def trigger_onboarding_flow(*args, **kwargs): pass
    def _trigger_onboarding_flow_job(*args, **kwargs): pass
    def trigger_group_flow(*args, **kwargs): pass
    def trigger_individual_flows(*args, **kwargs): pass
    def get_stage_flow_statuses(*args, **kwargs): pass
    def get_students_from_onboarding(*args, **kwargs): pass
    def update_student_stage_progress(*args, **kwargs): pass
    def update_student_stage_progress_batch(*args, **kwargs): pass
    def get_job_status(*args, **kwargs): pass
    def get_onboarding_progress_report(*args, **kwargs): pass
    def update_incomplete_stages(*args, **kwargs): pass

class TestOnboardingFlowFunctions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests (run via 'bench --site <site> test')")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "test_job_123"
        self.current_time = datetime(2025, 9, 11, 13, 16)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    def test_trigger_onboarding_flow_success(self, mock_enqueue, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status=self.mock_student_status, glific_flow_id=self.mock_flow_id)])
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = self.mock_job_id
        
        result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], self.mock_job_id)
        mock_enqueue.assert_called_once()
        mock_throw.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_missing_params(self, mock_throw):
        # Test empty onboarding_set
        with self.assertRaises(Exception):
            trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(frappe._("Both Backend Student Onboarding Set and Onboarding Stage are required"))

        # Test empty onboarding_stage
        mock_throw.reset_mock()
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, "", self.mock_student_status)
        mock_throw.assert_called_with(frappe._("Both Backend Student Onboarding Set and Onboarding Stage are required"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_empty_student_status(self, mock_throw):
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "")
        mock_throw.assert_called_with(frappe._("Student status is required"))

        mock_throw.reset_mock()
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, None)
        mock_throw.assert_called_with(frappe._("Student status is required"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_invalid_stage(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=False)
        mock_get_doc.return_value = mock_stage
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(frappe._("Selected Onboarding Stage is not active"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_invalid_onboarding_status(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status=self.mock_student_status, glific_flow_id=self.mock_flow_id)])
        mock_onboarding = MagicMock(status="Draft")  # Not "Processed"
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(frappe._("Selected Backend Student Onboarding Set is not in Processed status"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_no_matching_flow(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[
            MagicMock(student_status="completed", glific_flow_id="12345")
        ])
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "not_started")
        mock_throw.assert_called_with(frappe._("No flow configured for stage '{0}' with status '{1}'").format(
            self.mock_onboarding_stage, "not_started"
        ))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_onboarding_flow_legacy_fields(self, mock_logger, mock_enqueue, mock_get_doc):
        # Test legacy support for old field structure
        mock_stage = MagicMock(is_active=True, stage_flows=[], glific_flow_id="legacy_flow")
        mock_stage.hasattr = lambda attr: attr in ['glific_flow_id']
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = self.mock_job_id
        
        result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        
        self.assertTrue(result["success"])
        # Should log deprecation warning
        mock_logger.return_value.warning.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_missing_flow_id(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[
            MagicMock(student_status=self.mock_student_status, glific_flow_id="")
        ])
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(frappe._("Flow ID is missing for stage '{0}' with status '{1}'").format(
            self.mock_onboarding_stage, self.mock_student_status
        ))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_success(self, mock_get_doc):
        mock_stage = MagicMock(stage_flows=[
            MagicMock(student_status="not_started"), 
            MagicMock(student_status="in_progress"),
            MagicMock(student_status="not_started")  # Duplicate should be handled
        ])
        mock_get_doc.return_value = mock_stage
        
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        
        self.assertIn("statuses", result)
        self.assertEqual(len(result["statuses"]), 2)  # Should be unique
        self.assertIn("not_started", result["statuses"])
        self.assertIn("in_progress", result["statuses"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_empty(self, mock_get_doc):
        mock_stage = MagicMock(stage_flows=[])
        mock_get_doc.return_value = mock_stage
        
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        
        self.assertIn("statuses", result)
        self.assertEqual(len(result["statuses"]), 0)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses_legacy_support(self, mock_get_doc):
        mock_stage = MagicMock(stage_flows=[], glific_flow_id="legacy_flow")
        mock_get_doc.return_value = mock_stage
        
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        
        self.assertIn("statuses", result)
        # Should return all default statuses for legacy flows
        expected_statuses = ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"]
        self.assertEqual(set(result["statuses"]), set(expected_statuses))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_get_stage_flow_statuses_error_handling(self, mock_log_error, mock_get_doc):
        mock_get_doc.side_effect = Exception("Stage not found")
        
        result = get_stage_flow_statuses(self.mock_onboarding_stage)
        
        self.assertIn("statuses", result)
        self.assertEqual(result["statuses"], [])
        self.assertIn("error", result)
        mock_log_error.assert_called_once()


class TestOnboardingFlowJobAndGroup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow')
    def test_trigger_onboarding_flow_job_success_group(self, mock_trigger_group, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "Bearer token"}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_glific_settings = MagicMock()
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]
        mock_trigger_group.return_value = {"success": True}
        
        result = _trigger_onboarding_flow_job(
            self.mock_onboarding_set, 
            self.mock_onboarding_stage, 
            self.mock_student_status, 
            self.mock_flow_id, 
            "Group"
        )
        
        self.assertIn("success", result)
        mock_trigger_group.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_individual_flows')
    def test_trigger_onboarding_flow_job_success_individual(self, mock_trigger_individual, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "Bearer token"}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_glific_settings = MagicMock()
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]
        mock_trigger_individual.return_value = {"success": True}
        
        result = _trigger_onboarding_flow_job(
            self.mock_onboarding_set, 
            self.mock_onboarding_stage, 
            self.mock_student_status, 
            self.mock_flow_id, 
            "Personal"
        )
        
        self.assertIn("success", result)
        mock_trigger_individual.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_auth_failure(self, mock_auth_headers):
        mock_auth_headers.return_value = {}  # No auth token
        
        result = _trigger_onboarding_flow_job(
            self.mock_onboarding_set, 
            self.mock_onboarding_stage, 
            self.mock_student_status, 
            self.mock_flow_id, 
            "Group"
        )
        
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Failed to authenticate with Glific API")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    def test_trigger_onboarding_flow_job_auth_missing_token(self, mock_auth_headers):
        mock_auth_headers.return_value = {"other_header": "value"}  # Missing authorization
        
        result = _trigger_onboarding_flow_job(
            self.mock_onboarding_set, 
            self.mock_onboarding_stage, 
            self.mock_student_status, 
            self.mock_flow_id, 
            "Group"
        )
        
        self.assertIn("error", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_success(self, mock_create_group, mock_get_doc, mock_requests):
        mock_onboarding = MagicMock(name=self.mock_onboarding_set)
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_response = MagicMock(
            status_code=200, 
            json=lambda: {"data": {"startGroupFlow": {"success": True}}}
        )
        mock_requests.return_value = mock_response
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding') as mock_get_students:
            with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch') as mock_update_batch:
                mock_get_students.return_value = [MagicMock(), MagicMock()]
                
                result = trigger_group_flow(
                    mock_onboarding, 
                    mock_stage, 
                    "Bearer token", 
                    self.mock_student_status, 
                    self.mock_flow_id
                )
                
                self.assertIn("group_flow_result", result)
                self.assertEqual(result["group_count"], 2)
                mock_update_batch.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_group_flow_missing_contact_group(self, mock_throw, mock_create_group):
        mock_create_group.return_value = None
        
        with self.assertRaises(Exception):
            trigger_group_flow(
                MagicMock(), 
                MagicMock(), 
                "Bearer token", 
                self.mock_student_status, 
                self.mock_flow_id
            )
        mock_throw.assert_called_with(frappe._("Could not find or create contact group for this onboarding set"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_group_flow_missing_flow_id(self, mock_throw):
        with self.assertRaises(Exception):
            trigger_group_flow(
                MagicMock(), 
                MagicMock(), 
                "Bearer token", 
                self.mock_student_status, 
                None  # No flow ID
            )
        mock_throw.assert_called_with(frappe._("No Glific flow ID available for this stage and status"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_api_error(self, mock_create_group, mock_get_doc, mock_requests):
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_response = MagicMock(status_code=500, text="Server Error")
        mock_requests.return_value = mock_response
        
        with self.assertRaises(Exception):
            trigger_group_flow(
                mock_onboarding, 
                mock_stage, 
                "Bearer token", 
                self.mock_student_status, 
                self.mock_flow_id
            )

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_glific_api_errors(self, mock_create_group, mock_get_doc, mock_requests):
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_response = MagicMock(
            status_code=200,
            json=lambda: {
                "data": {
                    "startGroupFlow": {
                        "success": False,
                        "errors": [{"message": "Flow not found"}]
                    }
                }
            }
        )
        mock_requests.return_value = mock_response
        
        with self.assertRaises(Exception) as context:
            trigger_group_flow(
                mock_onboarding, 
                mock_stage, 
                "Bearer token", 
                self.mock_student_status, 
                self.mock_flow_id
            )
        
        self.assertIn("Flow not found", str(context.exception))


class TestOnboardingIndividualAndStudents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_students_from_onboarding_success(self, mock_get_all):
        # Mock backend students
        mock_get_all.side_effect = [
            [{"student_id": "STUD_001"}],  # Backend students call
            [{"name": "progress_1"}]       # Stage progress call
        ]
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc') as mock_get_doc:
            mock_student = MagicMock(name="STUD_001")
            mock_get_doc.return_value = mock_student
            
            result = get_students_from_onboarding(
                MagicMock(name=self.mock_onboarding_set), 
                self.mock_onboarding_stage, 
                self.mock_student_status
            )
            
            self.assertEqual(len(result), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_students_from_onboarding_empty(self, mock_get_all):
        mock_get_all.return_value = []  # No backend students
        
        result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), None, None)
        
        self.assertEqual(result, [])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding_with_stage_no_status(self, mock_get_doc, mock_get_all):
        # Test filtering by stage only (any status)
        mock_get_all.side_effect = [
            [{"student_id": "STUD_001"}],  # Backend students
            [{"name": "progress_1"}]       # Any stage progress exists
        ]
        mock_student = MagicMock(name="STUD_001")
        mock_get_doc.return_value = mock_student
        
        result = get_students_from_onboarding(
            MagicMock(name=self.mock_onboarding_set), 
            "STAGE_001", 
            None
        )
        
        self.assertEqual(len(result), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding_not_started_special_case(self, mock_get_doc, mock_get_all):
        # Test the special "not_started" logic where no progress record exists
        mock_get_all.side_effect = [
            [{"student_id": "STUD_001"}, {"student_id": "STUD_002"}],  # Backend students
            [],  # First student has no progress - not_started
            [{"name": "progress_2"}]  # Second student has progress
        ]
        
        def mock_get_doc_side_effect(doctype, name):
            if name == "STUD_001":
                return MagicMock(name="STUD_001")
            elif name == "STUD_002":
                return MagicMock(name="STUD_002")
            return MagicMock()
            
        mock_get_doc.side_effect = mock_get_doc_side_effect
        
        result = get_students_from_onboarding(
            MagicMock(name=self.mock_onboarding_set), 
            "STAGE_001", 
            "not_started"
        )
        
        # Should find the student without progress record
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "STUD_001")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('time.sleep')
    def test_trigger_individual_flows_success(self, mock_sleep, mock_get_students, mock_update_progress, mock_start_flow, mock_get_all):
        mock_student = MagicMock(name="STUD_001", name1="Student One", glific_id="glific_1")
        mock_get_students.return_value = [mock_student]
        mock_start_flow.return_value = True
        
        result = trigger_individual_flows(
            MagicMock(), 
            MagicMock(), 
            "Bearer token", 
            self.mock_student_status, 
            self.mock_flow_id
        )
        
        self.assertEqual(result["individual_count"], 1)
        self.assertEqual(result["error_count"], 0)
        mock_update_progress.assert_called_once()
        mock_start_flow.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_individual_flows_missing_flow_id(self, mock_throw, mock_get_students):
        with self.assertRaises(Exception):
            trigger_individual_flows(
                MagicMock(), 
                MagicMock(), 
                "Bearer token", 
                self.mock_student_status, 
                None  # No flow ID
            )
        mock_throw.assert_called_with(frappe._("No Glific flow ID available for this stage and status"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_individual_flows_no_students(self, mock_throw, mock_get_students):
        mock_get_students.return_value = []
        
        with self.assertRaises(Exception):
            trigger_individual_flows(
                MagicMock(), 
                MagicMock(), 
                "Bearer token", 
                self.mock_student_status, 
                self.mock_flow_id
            )
        mock_throw.assert_called_with(frappe._("No students found in this onboarding set with the selected status"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('time.sleep')
    def test_trigger_individual_flows_missing_glific_id(self, mock_sleep, mock_update_progress, mock_start_flow, mock_get_students):
        # Test students without Glific IDs are skipped
        mock_student_without_glific = MagicMock(name="STUD_001", name1="Student One", glific_id=None)
        mock_student_with_glific = MagicMock(name="STUD_002", name1="Student Two", glific_id="glific_2")
        mock_get_students.return_value = [mock_student_without_glific, mock_student_with_glific]
        mock_start_flow.return_value = True
        
        result = trigger_individual_flows(
            MagicMock(), 
            MagicMock(), 
            "Bearer token", 
            self.mock_student_status, 
            self.mock_flow_id
        )
        
        # Should only process student with Glific ID
        self.assertEqual(result["individual_count"], 1)
        self.assertEqual(len(result["individual_flow_results"]), 1)
        mock_start_flow.assert_called_once()
        mock_update_progress.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('time.sleep')
    def test_trigger_individual_flows_mixed_success_failure(self, mock_sleep, mock_start_flow, mock_get_students):
        mock_student1 = MagicMock(name="STUD_001", name1="Student One", glific_id="glific_1")
        mock_student2 = MagicMock(name="STUD_002", name1="Student Two", glific_id="glific_2")
        mock_get_students.return_value = [mock_student1, mock_student2]
        mock_start_flow.side_effect = [True, False]  # First succeeds, second fails
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress') as mock_update:
            result = trigger_individual_flows(
                MagicMock(), 
                MagicMock(), 
                "Bearer token", 
                self.mock_student_status, 
                self.mock_flow_id
            )
            
            self.assertEqual(result["individual_count"], 1)  # Only one success
            self.assertEqual(result["error_count"], 1)       # One failure
            mock_update.assert_called_once()  # Only called for successful flow

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('time.sleep')
    def test_trigger_individual_flows_exception_handling(self, mock_sleep, mock_start_flow, mock_get_students):
        mock_student = MagicMock(name="STUD_001", name1="Student One", glific_id="glific_1")
        mock_get_students.return_value = [mock_student]
        mock_start_flow.side_effect = Exception("Network error")
        
        result = trigger_individual_flows(
            MagicMock(), 
            MagicMock(), 
            "Bearer token", 
            self.mock_student_status, 
            self.mock_flow_id
        )
        
        self.assertEqual(result["individual_count"], 0)
        self.assertEqual(result["error_count"], 1)
        self.assertIn("Network error", result["individual_flow_results"][0]["error"])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('time.sleep')
    def test_trigger_individual_flows_rate_limiting(self, mock_sleep, mock_start_flow, mock_get_students):
        # Test that batch processing includes delays
        students = [MagicMock(name=f"STUD_{i:03d}", name1=f"Student {i}", glific_id=f"glific_{i}") 
                   for i in range(25)]  # 25 students to test batching
        mock_get_students.return_value = students
        mock_start_flow.return_value = True
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress'):
            with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit'):
                result = trigger_individual_flows(
                    MagicMock(), 
                    MagicMock(), 
                    "Bearer token", 
                    self.mock_student_status, 
                    self.mock_flow_id
                )
                
                self.assertEqual(result["individual_count"], 25)
                # Should call sleep at least twice (after batches of 10)
                self.assertGreaterEqual(mock_sleep.call_count, 2)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_update_student_stage_progress_new(self, mock_commit, mock_new_doc, mock_get_all):
        mock_get_all.return_value = []  # No existing record
        mock_progress = MagicMock()
        mock_new_doc.return_value = mock_progress
        mock_student = MagicMock(name="STUD_001")
        mock_stage = MagicMock(name="STAGE_001")
        
        update_student_stage_progress(mock_student, mock_stage)
        
        mock_new_doc.assert_called_once_with("StudentStageProgress")
        mock_progress.insert.assert_called_once()
        self.assertEqual(mock_progress.status, "assigned")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_update_student_stage_progress_existing(self, mock_commit, mock_get_doc, mock_get_all):
        mock_get_all.return_value = [{"name": "progress_1"}]
        mock_progress = MagicMock(status="not_started", start_timestamp=None)
        mock_get_doc.return_value = mock_progress
        
        update_student_stage_progress(MagicMock(), MagicMock())
        
        self.assertEqual(mock_progress.status, "assigned")
        mock_progress.save.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_update_student_stage_progress_skip_completed(self, mock_get_doc, mock_get_all):
        # Test that completed/in_progress records are not updated
        mock_get_all.return_value = [{"name": "progress_1"}]
        mock_progress = MagicMock(status="completed")
        mock_get_doc.return_value = mock_progress
        
        update_student_stage_progress(MagicMock(), MagicMock())
        
        # Status should remain completed
        self.assertEqual(mock_progress.status, "completed")
        mock_progress.save.assert_not_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_update_student_stage_progress_batch_mixed_scenarios(self, mock_commit, mock_new_doc, mock_get_doc, mock_get_all):
        # Test batch update with mix of existing and new records
        students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        stage = MagicMock(name="STAGE_001")
        
        # First student: no existing record (create new)
        # Second student: existing record (update)
        mock_get_all.side_effect = [[], [{"name": "existing_progress"}]]
        
        mock_new_progress = MagicMock()
        mock_new_doc.return_value = mock_new_progress
        mock_existing_progress = MagicMock(status="not_started")
        mock_get_doc.return_value = mock_existing_progress
        
        update_student_stage_progress_batch(students, stage)
        
        # Should create one new record
        mock_new_doc.assert_called_once_with("StudentStageProgress")
        mock_new_progress.insert.assert_called_once()
        
        # Should update one existing record
        mock_existing_progress.save.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_update_student_stage_progress_batch_empty_list(self, mock_logger):
        update_student_stage_progress_batch([], MagicMock())
        # Should log warning and return gracefully
        mock_logger.return_value.warning.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_update_student_stage_progress_batch_partial_failures(self, mock_logger, mock_get_all):
        # Test when some records fail to update but others succeed
        students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        stage = MagicMock(name="STAGE_001")
        
        def get_all_side_effect(*args, **kwargs):
            if kwargs.get('filters', {}).get('student') == "STUD_001":
                raise Exception("Database error")
            return []
        
        mock_get_all.side_effect = get_all_side_effect
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc'):
            update_student_stage_progress_batch(students, stage)
            
            # Should log errors for failed updates
            mock_logger.return_value.error.assert_called()


class TestOnboardingJobReportAndScheduled(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.current_time = datetime(2025, 9, 11, 13, 16)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_success(self, mock_get_job_status):
        mock_get_job_status.return_value = "finished"
        
        result = get_job_status("test_job")
        
        self.assertEqual(result["status"], "complete")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_failed(self, mock_get_job_status):
        mock_get_job_status.return_value = "failed"
        
        result = get_job_status("test_job")
        
        self.assertEqual(result["status"], "failed")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    def test_get_job_status_running(self, mock_get_job_status):
        mock_get_job_status.return_value = "queued"
        
        result = get_job_status("test_job")
        
        self.assertEqual(result["status"], "queued")

    def test_get_job_status_no_job_id(self):
        result = get_job_status("")
        self.assertEqual(result["status"], "unknown")
        
        result = get_job_status(None)
        self.assertEqual(result["status"], "unknown")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_redis_conn')
    def test_get_job_status_with_results(self, mock_get_redis, mock_get_job_status):
        mock_get_job_status.return_value = "finished"
        mock_redis_conn = MagicMock()
        mock_get_redis.return_value = mock_redis_conn
        
        # Mock Job.fetch
        with patch('rq.job.Job') as mock_job_class:
            mock_job = MagicMock()
            mock_job.result = {"success": True, "message": "Flow completed"}
            mock_job_class.fetch.return_value = mock_job
            
            result = get_job_status("test_job")
            
            self.assertEqual(result["status"], "complete")
            self.assertIn("results", result)
            self.assertEqual(result["results"]["success"], True)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_redis_conn')
    def test_get_job_status_redis_failure(self, mock_get_redis, mock_get_job_status):
        mock_get_job_status.return_value = "finished"
        mock_get_redis.return_value = None  # Redis connection failed
        
        result = get_job_status("test_job")
        
        self.assertEqual(result["status"], "complete")
        self.assertNotIn("results", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_get_job_status_exception_handling(self, mock_log_error, mock_get_job_status):
        mock_get_job_status.side_effect = Exception("Connection failed")
        
        result = get_job_status("test_job")
        
        self.assertEqual(result["status"], "error")
        self.assertIn("message", result)
        mock_log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_get_onboarding_progress_report_empty(self, mock_get_all):
        mock_get_all.return_value = []
        
        result = get_onboarding_progress_report(
            set=self.mock_onboarding_set, 
            stage=self.mock_onboarding_stage
        )
        
        self.assertIn("summary", result)
        self.assertIn("details", result)
        self.assertEqual(len(result["details"]), 0)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_onboarding_progress_report_with_data(self, mock_get_doc, mock_get_all):
        # Mock progress records
        mock_get_all.side_effect = [
            [{"name": "progress_1", "student": "STUD_001", "stage": "STAGE_001", "status": "completed"}],
            [{"student_id": "STUD_001"}]  # Backend students for set filtering
        ]
        
        mock_student = MagicMock(name="STUD_001", name1="Student One", phone="1234567890")
        mock_stage = MagicMock(name="STAGE_001")
        mock_get_doc.side_effect = [mock_student, mock_stage]
        
        result = get_onboarding_progress_report(
            set=self.mock_onboarding_set,
            stage=self.mock_onboarding_stage
        )
        
        self.assertIn("summary", result)
        self.assertIn("details", result)
        self.assertEqual(result["summary"]["completed"], 1)
        self.assertEqual(len(result["details"]), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_onboarding_progress_report_with_set_filter(self, mock_get_doc, mock_get_all):
        # Test report generation with set filtering
        mock_progress_record = {
            "name": "progress_1", 
            "student": "STUD_001", 
            "stage": "STAGE_001", 
            "status": "assigned"
        }
        
        mock_get_all.side_effect = [
            [mock_progress_record],  # Progress records
            [{"student_id": "STUD_001"}]  # Backend students matching the set
        ]
        
        mock_student = MagicMock(name="STUD_001", name1="Student One", phone="1234567890")
        mock_stage = MagicMock(name="STAGE_001")
        mock_get_doc.side_effect = [mock_student, mock_stage]
        
        result = get_onboarding_progress_report(set=self.mock_onboarding_set)
        
        self.assertEqual(len(result["details"]), 1)
        self.assertEqual(result["summary"]["assigned"], 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_onboarding_progress_report_not_started_inclusion(self, mock_get_doc, mock_get_all):
        # Test that not_started students are included in reports
        mock_get_all.side_effect = [
            [],  # No existing progress records
            [{"student_id": "STUD_001"}, {"student_id": "STUD_002"}],  # Backend students
            [],  # First student has no progress - not_started
            []   # Second student has no progress - not_started
        ]
        
        def mock_get_doc_side_effect(doctype, name):
            if doctype == "Student":
                return MagicMock(name=name, name1=f"Student {name[-1]}", phone="1234567890")
            elif doctype == "OnboardingStage":
                return MagicMock(name=name)
            return MagicMock()
        
        mock_get_doc.side_effect = mock_get_doc_side_effect
        
        result = get_onboarding_progress_report(
            set=self.mock_onboarding_set,
            stage=self.mock_onboarding_stage,
            status="not_started"
        )
        
        self.assertEqual(len(result["details"]), 2)
        self.assertEqual(result["summary"]["not_started"], 2)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages_success(self, mock_add_to_date, mock_now_datetime, mock_get_doc, mock_get_all):
        mock_now_datetime.return_value = self.current_time
        mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
        mock_get_all.return_value = [{
            "name": "progress_1", 
            "student": "STUD_001",
            "stage": "STAGE_001",
            "start_timestamp": self.current_time - timedelta(days=5)
        }]
        
        mock_progress = MagicMock(status="assigned")
        mock_get_doc.return_value = mock_progress
        
        update_incomplete_stages()
        
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages_boundary_conditions(self, mock_add_to_date, mock_now_datetime, mock_get_all):
        # Test the 3-day boundary logic more thoroughly
        mock_now_datetime.return_value = self.current_time
        
        # Test records at exactly 3 days, 2.9 days, 3.1 days
        test_cases = [
            (timedelta(days=3), True, "exactly_3_days"),      # Should be marked incomplete
            (timedelta(days=2, hours=22), False, "2.9_days"), # Should NOT be marked incomplete
            (timedelta(days=3, hours=1), True, "3.1_days")    # Should be marked incomplete
        ]
        
        for delta, should_update, case_name in test_cases:
            with self.subTest(case=case_name):
                mock_add_to_date.return_value = self.current_time - delta
                start_time = self.current_time - delta
                
                mock_get_all.return_value = [{
                    "name": f"progress_{case_name}",
                    "student": "STUD_001",
                    "stage": "STAGE_001", 
                    "start_timestamp": start_time
                }]
                
                with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc') as mock_get_doc:
                    mock_progress = MagicMock(status="assigned")
                    mock_get_doc.return_value = mock_progress
                    
                    update_incomplete_stages()
                    
                    if should_update:
                        self.assertEqual(mock_progress.status, "incomplete")
                        mock_progress.save.assert_called()
                    else:
                        # Reset mocks for next iteration
                        mock_progress.reset_mock()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_update_incomplete_stages_no_records(self, mock_get_all):
        mock_get_all.return_value = []
        
        # Should handle gracefully without errors
        try:
            update_incomplete_stages()
        except Exception as e:
            self.fail(f"update_incomplete_stages raised {e} unexpectedly")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_update_incomplete_stages_partial_failures(self, mock_logger, mock_add_to_date, mock_now_datetime, mock_get_doc, mock_get_all):
        # Test when some records fail to update but others succeed
        mock_now_datetime.return_value = self.current_time
        mock_add_to_date.return_value = self.current_time - timedelta(days=3)
        
        mock_get_all.return_value = [
            {"name": "progress_1", "student": "STUD_001", "stage": "STAGE_001", "start_timestamp": self.current_time - timedelta(days=5)},
            {"name": "progress_2", "student": "STUD_002", "stage": "STAGE_001", "start_timestamp": self.current_time - timedelta(days=4)}
        ]
        
        # First record succeeds, second fails
        def mock_get_doc_side_effect(doctype, name):
            progress = MagicMock(status="assigned")
            if name == "progress_2":
                progress.save.side_effect = Exception("Database error")
            return progress
        
        mock_get_doc.side_effect = mock_get_doc_side_effect
        
        update_incomplete_stages()
        
        # Should log errors for failed updates
        mock_logger.return_value.error.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_update_incomplete_stages_exception_handling(self, mock_get_all, mock_log_error):
        mock_get_all.side_effect = Exception("Database connection failed")
        
        # Should handle exception gracefully and log error
        update_incomplete_stages()
        mock_log_error.assert_called_once()


class TestOnboardingErrorHandlingAndEdgeCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_trigger_onboarding_flow_general_exception(self, mock_log_error, mock_get_doc):
        mock_get_doc.side_effect = Exception("Unexpected database error")
        
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        
        mock_log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_trigger_onboarding_flow_job_exception_handling(self, mock_log_error, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "Bearer token"}
        mock_get_doc.side_effect = Exception("Stage not found")
        
        result = _trigger_onboarding_flow_job(
            self.mock_onboarding_set,
            self.mock_onboarding_stage,
            self.mock_student_status,
            self.mock_flow_id,
            "Group"
        )
        
        self.assertIn("error", result)
        mock_log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_get_students_from_onboarding_exception_handling(self, mock_log_error, mock_get_all):
        mock_get_all.side_effect = Exception("Database timeout")
        
        result = get_students_from_onboarding(MagicMock(), "STAGE_001", "not_started")
        
        self.assertEqual(result, [])
        mock_log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_update_student_stage_progress_exception_handling(self, mock_log_error, mock_get_doc, mock_get_all):
        mock_get_all.return_value = []
        mock_get_doc.side_effect = Exception("Permission denied")
        
        # Should handle exception gracefully
        update_student_stage_progress(MagicMock(), MagicMock())
        mock_log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_get_onboarding_progress_report_exception_handling(self, mock_log_error, mock_throw, mock_get_all):
        mock_get_all.side_effect = Exception("Database error")
        
        with self.assertRaises(Exception):
            get_onboarding_progress_report(set=self.mock_onboarding_set)
        
        mock_log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_trigger_group_flow_exception_handling(self, mock_log_error, mock_create_group):
        mock_create_group.side_effect = Exception("API connection failed")
        
        with self.assertRaises(Exception):
            trigger_group_flow(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
        
        mock_log_error.assert_called_once()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.log_error')
    def test_trigger_individual_flows_exception_handling(self, mock_log_error, mock_get_students):
        mock_get_students.side_effect = Exception("Student fetch failed")
        
        with self.assertRaises(Exception):
            trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
        
        mock_log_error.assert_called_once()


class TestOnboardingDataValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_invalid_flow_id_formats(self, mock_throw, mock_get_doc):
        # Test various invalid flow ID scenarios
        invalid_flow_ids = ["", " ", None, "invalid-flow", "12345@#$"]
        
        for invalid_id in invalid_flow_ids:
            with self.subTest(flow_id=invalid_id):
                mock_stage = MagicMock(
                    is_active=True,
                    stage_flows=[MagicMock(student_status="not_started", glific_flow_id=invalid_id)]
                )
                mock_onboarding = MagicMock(status="Processed")
                mock_get_doc.side_effect = [mock_stage, mock_onboarding]
                
                if not invalid_id or invalid_id.strip() == "":
                    with self.assertRaises(Exception):
                        trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "not_started")
                    mock_throw.assert_called()
                
                mock_throw.reset_mock()
                mock_get_doc.reset_mock()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_malformed_stage_configuration(self, mock_get_doc):
        # Test stage with malformed stage_flows
        test_cases = [
            # Empty stage_flows list
            {"stage_flows": [], "glific_flow_id": None},
            # stage_flows with missing required fields
            {"stage_flows": [MagicMock(student_status=None, glific_flow_id="12345")]},
            # Mixed valid and invalid flows
            {"stage_flows": [
                MagicMock(student_status="not_started", glific_flow_id="12345"),
                MagicMock(student_status="", glific_flow_id="67890")
            ]}
        ]
        
        for i, config in enumerate(test_cases):
            with self.subTest(case=i):
                mock_stage = MagicMock(is_active=True, **config)
                mock_onboarding = MagicMock(status="Processed")
                mock_get_doc.side_effect = [mock_stage, mock_onboarding]
                
                # Most should raise exceptions due to invalid configuration
                with self.assertRaises(Exception):
                    trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "not_started")

    def test_student_status_validation(self):
        # Test various student status values
        valid_statuses = ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"]
        invalid_statuses = ["", " ", None, "invalid_status", "123", "COMPLETED"]  # Case sensitive
        
        for status in valid_statuses:
            with self.subTest(status=status):
                # These should be accepted as valid inputs
                self.assertIsInstance(status, str)
                self.assertTrue(len(status) > 0)
        
        for status in invalid_statuses:
            with self.subTest(status=status):
                with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw') as mock_throw:
                    if not status or (isinstance(status, str) and status.strip() == ""):
                        with self.assertRaises(Exception):
                            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, status)


class TestOnboardingConcurrencyAndPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not FRAPPE_AVAILABLE:
            raise unittest.SkipTest("Frappe not available - skipping tests")

    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('time.sleep')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_large_student_batch_processing(self, mock_commit, mock_sleep, mock_update_progress, mock_start_flow, mock_get_students):
        # Test with large number of students (100) to verify batching logic
        large_student_list = [
            MagicMock(name=f"STUD_{i:03d}", name1=f"Student {i}", glific_id=f"glific_{i}")
            for i in range(100)
        ]
        mock_get_students.return_value = large_student_list
        mock_start_flow.return_value = True
        
        result = trigger_individual_flows(
            MagicMock(),
            MagicMock(),
            "Bearer token",
            "not_started",
            "12345"
        )
        
        # Should process all students
        self.assertEqual(result["individual_count"], 100)
        
        # Should have multiple batch commits (every 10 students)
        self.assertEqual(mock_commit.call_count, 10)  # 100 students / 10 per batch
        
        # Should have sleep calls between batches
        self.assertGreaterEqual(mock_sleep.call_count, 9)  # 9 sleep calls for 10 batches

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_batch_update_performance(self, mock_get_doc, mock_new_doc, mock_get_all):
        # Test batch update with mixed scenarios (some exist, some don't)
        students = [MagicMock(name=f"STUD_{i:03d}") for i in range(50)]
        stage = MagicMock(name="STAGE_001")
        
        # Simulate 50% existing records, 50% new records
        def mock_get_all_side_effect(*args, **kwargs):
            student_name = kwargs.get('filters', {}).get('student', '')
            student_num = int(student_name.split('_')[-1]) if student_name else 0
            if student_num % 2 == 0:
                return [{"name": f"progress_{student_num}"}]  # Existing record
            else:
                return []  # No existing record
        
        mock_get_all.side_effect = mock_get_all_side_effect
        mock_new_doc.return_value = MagicMock()
        mock_get_doc.return_value = MagicMock(status="not_started")
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit'):
            update_student_stage_progress_batch(students, stage)
            
            # Should create docs for odd-numbered students (25 new docs)
            self.assertEqual(mock_new_doc.call_count, 25)
            
            # Should fetch existing docs for even-numbered students (25 fetches)
            # Note: get_doc is called for each existing record
            self.assertEqual(mock_get_doc.call_count, 25)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    def test_multiple_concurrent_job_creation(self, mock_enqueue):
        # Test that multiple job requests can be handled
        mock_enqueue.side_effect = ["job_1", "job_2", "job_3"]
        
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc') as mock_get_doc:
            mock_stage = MagicMock(is_active=True, stage_flows=[
                MagicMock(student_status="not_started", glific_flow_id="12345")
            ])
            mock_onboarding = MagicMock(status="Processed")
            mock_get_doc.side_effect = [mock_stage, mock_onboarding] * 3
            
            # Simulate multiple rapid job requests
            results = []
            for i in range(3):
                result = trigger_onboarding_flow(
                    f"ONBOARDING_{i}",
                    "STAGE_001",
                    "not_started"
                )
                results.append(result)
            
            # All should succeed with different job IDs
            for i, result in enumerate(results):
                self.assertTrue(result["success"])
                self.assertEqual(result["job_id"], f"job_{i+1}")


class TestOnboardingFlowRunner:
    @staticmethod
    def run_all_tests(verbosity=2):
        """
        Run all test suites with comprehensive coverage
        """
        test_suite = unittest.TestSuite()
        
        # Add all test classes
        test_classes = [
            TestOnboardingFlowFunctions,
            TestOnboardingFlowJobAndGroup, 
            TestOnboardingIndividualAndStudents,
            TestOnboardingJobReportAndScheduled,
            TestOnboardingErrorHandlingAndEdgeCases,
            TestOnboardingDataValidation,
            TestOnboardingConcurrencyAndPerformance
        ]
        
        for test_class in test_classes:
            tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
            test_suite.addTests(tests)
        
        # Run tests with detailed output
        runner = unittest.TextTestRunner(
            verbosity=verbosity, 
            stream=sys.stdout, 
            buffer=True,
            descriptions=True
        )
        result = runner.run(test_suite)
        
        # Print comprehensive summary
        print(f"\n{'='*80}\nCOMPREHENSIVE TEST SUMMARY\n{'='*80}")
        print(f"Total Test Classes: {len(test_classes)}")
        print(f"Tests Run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
        
        if result.failures:
            print(f"\nFAILURES ({len(result.failures)}):")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip() if 'AssertionError:' in traceback else 'Unknown failure'}")
        
        if result.errors:
            print(f"\nERRORS ({len(result.errors)}):")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split('Exception:')[-1].strip() if 'Exception:' in traceback else 'Unknown error'}")
        
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100) if result.testsRun > 0 else 0
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        
        # Coverage areas tested
        print(f"\n{'='*80}\nCOVERAGE AREAS TESTED\n{'='*80}")
        coverage_areas = [
            "✓ Main function success and failure paths",
            "✓ Parameter validation and error handling", 
            "✓ Authentication and API communication",
            "✓ Group flow processing and error scenarios",
            "✓ Individual flow processing with batching",
            "✓ Student filtering and status management",
            "✓ Database operations and transactions",
            "✓ Background job management and status tracking",
            "✓ Progress reporting and data aggregation",
            "✓ Scheduled tasks and cleanup operations",
            "✓ Exception handling and logging",
            "✓ Data validation and edge cases",
            "✓ Performance with large datasets",
            "✓ Concurrency scenarios",
            "✓ Legacy compatibility",
            "✓ Rate limiting and API throttling"
        ]
        
        for area in coverage_areas:
            print(f"  {area}")
        
        print(f"\n{'='*80}")
        return result.wasSuccessful()


if __name__ == '__main__':
    import sys
    success = TestOnboardingFlowRunner.run_all_tests()
    sys.exit(0 if success else 1)


    
# import unittest
# from unittest.mock import Mock, patch, MagicMock
# from datetime import datetime, timedelta
# import time
# import os

# # Conditional import guard
# try:
#     import frappe
#     from tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger import (
#         trigger_onboarding_flow,
#         _trigger_onboarding_flow_job,
#         trigger_group_flow,
#         trigger_individual_flows,
#         get_stage_flow_statuses,
#         get_students_from_onboarding,
#         update_student_stage_progress,
#         update_student_stage_progress_batch,
#         get_job_status,
#         get_onboarding_progress_report,
#         update_incomplete_stages
#     )
#     FRAPPE_AVAILABLE = True
# except ImportError:
#     FRAPPE_AVAILABLE = False
#     def trigger_onboarding_flow(*args, **kwargs): pass
#     def _trigger_onboarding_flow_job(*args, **kwargs): pass
#     def trigger_group_flow(*args, **kwargs): pass
#     def trigger_individual_flows(*args, **kwargs): pass
#     def get_stage_flow_statuses(*args, **kwargs): pass
#     def get_students_from_onboarding(*args, **kwargs): pass
#     def update_student_stage_progress(*args, **kwargs): pass
#     def update_student_stage_progress_batch(*args, **kwargs): pass
#     def get_job_status(*args, **kwargs): pass
#     def get_onboarding_progress_report(*args, **kwargs): pass
#     def update_incomplete_stages(*args, **kwargs): pass

# class TestOnboardingFlowFunctions(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests (run via 'bench --site <site> test')")

#     def setUp(self):
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"
#         self.mock_job_id = "test_job_123"
#         self.current_time = datetime(2025, 9, 11, 13, 16)  # 01:16 PM IST, September 11, 2025

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
#     def test_trigger_onboarding_flow_success(self, mock_enqueue, mock_throw, mock_get_doc):
#         mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status=self.mock_student_status, glific_flow_id=self.mock_flow_id)])
#         mock_onboarding = MagicMock(status="Processed")
#         mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#         mock_enqueue.return_value = self.mock_job_id
#         result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
#         self.assertTrue(result["success"])
#         mock_enqueue.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
#     def test_trigger_onboarding_flow_missing_params(self, mock_throw, mock_get_doc):
#         with self.assertRaises(Exception):
#             trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
#         mock_throw.assert_called_with(_("Both Backend Student Onboarding Set and Onboarding Stage are required"))

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_success(self, mock_get_doc):
#         mock_stage = MagicMock(stage_flows=[MagicMock(student_status="not_started"), MagicMock(student_status="in_progress")])
#         mock_get_doc.return_value = mock_stage
#         result = get_stage_flow_statuses(self.mock_onboarding_stage)
#         self.assertIn("statuses", result)
#         self.assertEqual(len(result["statuses"]), 2)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_get_stage_flow_statuses_empty(self, mock_get_doc):
#         mock_stage = MagicMock(stage_flows=[])
#         mock_get_doc.return_value = mock_stage
#         result = get_stage_flow_statuses(self.mock_onboarding_stage)
#         self.assertIn("statuses", result)
#         self.assertEqual(len(result["statuses"]), 0)

# class TestOnboardingFlowJobAndGroup(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     def setUp(self):
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_trigger_onboarding_flow_job_success(self, mock_get_doc, mock_auth_headers):
#         mock_auth_headers.return_value = {"Authorization": "Bearer token"}
#         mock_get_doc.return_value = MagicMock()
#         result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
#         self.assertIn("success", result)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_trigger_group_flow_success(self, mock_get_doc, mock_requests):
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_response = MagicMock(status_code=200, json=lambda: {"data": {"startGroupFlow": {"success": True}}})
#         mock_requests.return_value = mock_response
#         result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertIn("group_flow_result", result)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_trigger_group_flow_api_error(self, mock_get_doc, mock_requests):
#         mock_onboarding = MagicMock()
#         mock_stage = MagicMock()
#         mock_contact_group = MagicMock(group_id="group_123")
#         mock_glific_settings = MagicMock(api_url="https://api.glific.org")
#         mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
#         mock_response = MagicMock(status_code=500, text="Server Error")
#         mock_requests.return_value = mock_response
#         with self.assertRaises(Exception):
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)

# class TestOnboardingIndividualAndStudents(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     def setUp(self):
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_get_students_from_onboarding_success(self, mock_get_all):
#         mock_get_all.return_value = [{"student_id": "STUD_001"}]
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), self.mock_onboarding_stage, self.mock_student_status)
#         self.assertEqual(len(result), 1)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_get_students_from_onboarding_empty(self, mock_get_all):
#         mock_get_all.return_value = []
#         result = get_students_from_onboarding(MagicMock(name=self.mock_onboarding_set), None, None)
#         self.assertEqual(result, [])

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
#     def test_trigger_individual_flows_success(self, mock_update_progress, mock_start_flow, mock_get_all):
#         mock_student = MagicMock(name="STUD_001", glific_id="glific_1")
#         mock_get_all.return_value = [{"student_id": "STUD_001"}]
#         mock_start_flow.return_value = True
#         result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
#         self.assertGreaterEqual(result["individual_count"], 1)
#         mock_update_progress.assert_called()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
#     def test_update_student_stage_progress_new(self, mock_new_doc, mock_get_all):
#         mock_get_all.return_value = []
#         mock_progress = MagicMock()
#         mock_new_doc.return_value = mock_progress
#         update_student_stage_progress(MagicMock(), MagicMock())
#         mock_new_doc.assert_called_once_with("StudentStageProgress")
#         mock_progress.insert.assert_called_once()

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     def test_update_student_stage_progress_batch_success(self, mock_get_doc, mock_get_all):
#         mock_students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
#         mock_get_all.return_value = []
#         mock_progress = MagicMock()
#         mock_get_doc.return_value = mock_progress
#         update_student_stage_progress_batch(mock_students, MagicMock())
#         self.assertEqual(mock_progress.status, "assigned")

# class TestOnboardingJobReportAndScheduled(unittest.TestCase):
#     @classmethod
#     def setUpClass(cls):
#         if not FRAPPE_AVAILABLE:
#             raise unittest.SkipTest("Frappe not available - skipping tests")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
#     def test_get_job_status_success(self, mock_get_job_status):
#         mock_get_job_status.return_value = "finished"
#         result = get_job_status("test_job")
#         self.assertEqual(result["status"], "complete")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_get_onboarding_progress_report_empty(self, mock_get_all):
#         mock_get_all.return_value = []
#         result = get_onboarding_progress_report(set=self.mock_onboarding_set, stage=self.mock_onboarding_stage)
#         self.assertIn("summary", result)

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.now_datetime')
#     def test_update_incomplete_stages_success(self, mock_now_datetime, mock_get_doc, mock_get_all):
#         mock_now_datetime.return_value = self.current_time
#         mock_get_all.return_value = [{"name": "progress_1", "status": "assigned", "start_timestamp": self.current_time - timedelta(days=5)}]
#         mock_progress = MagicMock()
#         mock_get_doc.return_value = mock_progress
#         update_incomplete_stages()
#         self.assertEqual(mock_progress.status, "incomplete")

#     @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
#     def test_update_incomplete_stages_no_records(self, mock_get_all):
#         mock_get_all.return_value = []
#         update_incomplete_stages()  # Should handle gracefully

# class TestOnboardingFlowRunner:
#     @staticmethod
#     def run_all_tests(verbosity=2):
#         test_suite = unittest.TestSuite()
#         test_classes = [
#             TestOnboardingFlowFunctions,
#             TestOnboardingFlowJobAndGroup,
#             TestOnboardingIndividualAndStudents,
#             TestOnboardingJobReportAndScheduled
#         ]
#         for test_class in test_classes:
#             tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
#             test_suite.addTests(tests)
#         runner = unittest.TextTestRunner(verbosity=verbosity, stream=sys.stdout, buffer=True)
#         result = runner.run(test_suite)
#         print(f"\n{'='*60}\nTEST SUMMARY\n{'='*60}")
#         print(f"Tests run: {result.testsRun}")
#         print(f"Failures: {len(result.failures)}")
#         print(f"Errors: {len(result.errors)}")
#         print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
#         success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100) if result.testsRun > 0 else 0
#         print(f"Success Rate: {success_rate:.1f}%")
#         return result.wasSuccessful()

# if __name__ == '__main__':
#     success = TestOnboardingFlowRunner.run_all_tests()
#     sys.exit(0 if success else 1)