import unittest
from unittest.mock import patch, MagicMock, Mock, call
import json
import sys
import frappe
from frappe import ValidationError


class TestOnboardingFlows(unittest.TestCase):
    def setUp(self):
        # Mock frappe and other dependencies
        self.setup_mocks()
        self.setup_test_data()
        
    def setup_mocks(self):
        # Mock frappe module
        self.frappe_patcher = patch.dict('sys.modules', {
            'frappe': MagicMock(),
            'frappe.utils': MagicMock(),
            'frappe.utils.background_jobs': MagicMock(),
            'frappe.model.document': MagicMock(),
            'frappe.model.base_document': MagicMock(),
            'frappe.utils.data': MagicMock(),
            'frappe.utils.background_jobs': MagicMock(),
        })
        self.frappe_patcher.start()
        
        # Mock other dependencies
        self.requests_patcher = patch.dict('sys.modules', {
            'requests': MagicMock()
        })
        self.requests_patcher.start()
        
        # Mock rq for job handling
        self.rq_patcher = patch.dict('sys.modules', {
            'rq': MagicMock(),
            'rq.job': MagicMock()
        })
        self.rq_patcher.start()
        
        # Mock the glific_integration module
        self.glific_patcher = patch.dict('sys.modules', {
            'tap_lms.glific_integration': MagicMock()
        })
        self.glific_patcher.start()
        
        # Now import the module and functions
        sys.path.insert(0, 'tap_lms')
        from tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger import (
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
        
        self.trigger_onboarding_flow = trigger_onboarding_flow
        self._trigger_onboarding_flow_job = _trigger_onboarding_flow_job
        self.trigger_group_flow = trigger_group_flow
        self.trigger_individual_flows = trigger_individual_flows
        self.get_stage_flow_statuses = get_stage_flow_statuses
        self.get_students_from_onboarding = get_students_from_onboarding
        self.update_student_stage_progress = update_student_stage_progress
        self.update_student_stage_progress_batch = update_student_stage_progress_batch
        self.get_job_status = get_job_status
        self.get_onboarding_progress_report = get_onboarding_progress_report
        self.update_incomplete_stages = update_incomplete_stages

    def setup_test_data(self):
        # Create mock documents
        self.stage = MagicMock()
        self.stage.name = "Test Onboarding Stage"
        self.stage.is_active = True
        self.stage.stage_flows = [MagicMock(student_status="assigned", glific_flow_id="flow_123", flow_type="Group")]
        
        self.onboarding = MagicMock()
        self.onboarding.name = "Test Onboarding Set"
        self.onboarding.status = "Processed"
        
        self.student = MagicMock()
        self.student.name = "STU-001"
        self.student.first_name = "Test"
        self.student.last_name = "Student"
        self.student.phone = "+1234567890"
        self.student.glific_id = "test_glific_id_123"
        self.student.name1 = "Test Student"
        
        self.backend_student = MagicMock()
        self.backend_student.student_id = self.student.name
        self.backend_student.processing_status = "Success"
        
        self.glific_settings = MagicMock()
        self.glific_settings.api_url = "https://test.glific.com"
        self.glific_settings.auth_token = "test_token"
        
        self.progress_record = MagicMock()
        self.progress_record.name = "PROG-001"
        self.progress_record.status = "assigned"
        self.progress_record.start_timestamp = "2020-01-01 00:00:00"
        
        # Mock frappe functions
        import frappe
        frappe.throw = Mock(side_effect=ValidationError)
        frappe.log_error = Mock()
        frappe.logger = Mock()
        frappe.logger().info = Mock()
        frappe.logger().debug = Mock()
        frappe.logger().warning = Mock()
        frappe.logger().error = Mock()
        frappe.enqueue = Mock()
        frappe.get_doc = Mock()
        frappe.get_all = Mock()
        frappe.new_doc = Mock()
        frappe.db = Mock()
        frappe.db.commit = Mock()
        frappe._ = lambda x: x

    def tearDown(self):
        self.frappe_patcher.stop()
        self.requests_patcher.stop()
        self.rq_patcher.stop()
        self.glific_patcher.stop()

    # Test 1: trigger_onboarding_flow - Basic functionality
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_success(self, mock_get_doc, mock_enqueue):
        # Mock documents
        mock_get_doc.side_effect = [self.stage, self.onboarding]
        mock_enqueue.return_value = "job_123"
        
        # Execute
        result = self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
        
        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], "job_123")
        mock_enqueue.assert_called_once()

    # Test 2: trigger_onboarding_flow - Validation errors
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_validation_errors(self, mock_get_doc):
        # Test missing parameters
        with self.assertRaises(ValidationError):
            self.trigger_onboarding_flow("", "", "")
            
        # Test inactive stage
        inactive_stage = MagicMock()
        inactive_stage.is_active = False
        mock_get_doc.return_value = inactive_stage
        
        with self.assertRaises(ValidationError):
            self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
            
        # Test onboarding not processed
        not_processed_onboarding = MagicMock()
        not_processed_onboarding.status = "Draft"
        mock_get_doc.side_effect = [self.stage, not_processed_onboarding]
        
        with self.assertRaises(ValidationError):
            self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
            
        # Test no flow configured
        stage_no_flow = MagicMock()
        stage_no_flow.is_active = True
        stage_no_flow.stage_flows = []
        stage_no_flow.glific_flow_id = None
        mock_get_doc.side_effect = [stage_no_flow, self.onboarding]
        
        with self.assertRaises(ValidationError):
            self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")

    # Test 3: _trigger_onboarding_flow_job - Group flow
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_group_flow')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_job_group(self, mock_get_doc, mock_trigger_group, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "test_token"}
        mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
        mock_trigger_group.return_value = {"success": True}
        
        result = self._trigger_onboarding_flow_job(
            self.onboarding.name, self.stage.name, "assigned", "flow_123", "Group"
        )
        
        self.assertEqual(result, {"success": True})

    # Test 4: _trigger_onboarding_flow_job - Individual flow
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.trigger_individual_flows')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_job_individual(self, mock_get_doc, mock_trigger_individual, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "test_token"}
        mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
        mock_trigger_individual.return_value = {"success": True}
        
        result = self._trigger_onboarding_flow_job(
            self.onboarding.name, self.stage.name, "assigned", "flow_123", "Personal"
        )
        
        self.assertEqual(result, {"success": True})

    # Test 5: _trigger_onboarding_flow_job - Authentication failure
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_job_auth_failure(self, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {}
        mock_get_doc.side_effect = [self.stage, self.onboarding, self.glific_settings]
        
        result = self._trigger_onboarding_flow_job(
            self.onboarding.name, self.stage.name, "assigned", "flow_123", "Group"
        )
        
        self.assertIn("error", result)

    # Test 6: trigger_group_flow - Success case
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_group_flow_success(self, mock_get_doc, mock_update_progress, 
                                      mock_get_students, mock_post, mock_create_group):
        # Mock responses
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_group = MagicMock()
        mock_group.group_id = "group_123"
        mock_get_doc.return_value = mock_group
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"startGroupFlow": {"success": True}}
        }
        mock_post.return_value = mock_response
        
        mock_get_students.return_value = [self.student]
        
        result = self.trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        self.assertTrue(result["group_flow_result"]["success"])
        mock_update_progress.assert_called_once()

    # Test 7: trigger_group_flow - Error case
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    def test_trigger_group_flow_error(self, mock_create_group):
        mock_create_group.return_value = None
        
        with self.assertRaises(ValidationError):
            self.trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

    # Test 8: trigger_group_flow - API failure
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_group_flow_api_failure(self, mock_get_doc, mock_post, mock_create_group):
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_group = MagicMock()
        mock_group.group_id = "group_123"
        mock_get_doc.return_value = mock_group
        
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        with self.assertRaises(ValidationError):
            self.trigger_group_flow(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

    # Test 9: trigger_individual_flows - Success case
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.time.sleep', return_value=None)
    def test_trigger_individual_flows_success(self, mock_sleep, mock_get_students, mock_update_progress, mock_start_flow):
        mock_get_students.return_value = [self.student]
        mock_start_flow.return_value = True
        
        result = self.trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        self.assertEqual(result["individual_count"], 1)
        mock_update_progress.assert_called_once()

    # Test 10: trigger_individual_flows - No students case
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_trigger_individual_flows_no_students(self, mock_get_students):
        mock_get_students.return_value = []
        
        with self.assertRaises(ValidationError):
            self.trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")

    # Test 11: trigger_individual_flows - Student without glific_id
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.time.sleep', return_value=None)
    def test_trigger_individual_flows_no_glific_id(self, mock_sleep, mock_get_students, mock_update_progress, mock_start_flow):
        student_no_glific = MagicMock()
        student_no_glific.name = "STU-002"
        student_no_glific.name1 = "Test Student 2"
        student_no_glific.glific_id = None
        
        mock_get_students.return_value = [student_no_glific, self.student]
        mock_start_flow.return_value = True
        
        result = self.trigger_individual_flows(self.onboarding, self.stage, "test_token", "assigned", "flow_123")
        
        # Should process one student (the one with glific_id)
        self.assertEqual(result["individual_count"], 1)
        self.assertEqual(result["error_count"], 0)

    # Test 12: get_stage_flow_statuses
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_stage_flow_statuses(self, mock_get_doc):
        # Test with stage flows
        mock_get_doc.return_value = self.stage
        
        result = self.get_stage_flow_statuses(self.stage.name)
        self.assertEqual(result["statuses"], ["assigned"])
        
        # Test with legacy flow configuration
        legacy_stage = MagicMock()
        legacy_stage.stage_flows = []
        legacy_stage.glific_flow_id = "legacy_flow_123"
        mock_get_doc.return_value = legacy_stage
        
        result = self.get_stage_flow_statuses(legacy_stage.name)
        self.assertEqual(len(result["statuses"]), 6)  # All statuses for legacy
        
        # Test with no flows configured
        no_flow_stage = MagicMock()
        no_flow_stage.stage_flows = []
        no_flow_stage.glific_flow_id = None
        mock_get_doc.return_value = no_flow_stage
        
        result = self.get_stage_flow_statuses(no_flow_stage.name)
        self.assertEqual(result["statuses"], [])

    # Test 13: get_students_from_onboarding
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding(self, mock_get_doc, mock_get_all):
        # Mock backend students
        mock_get_all.return_value = [{"student_id": self.student.name}]
        mock_get_doc.return_value = self.student
        
        # Test with stage and status filter
        result = self.get_students_from_onboarding(self.onboarding, self.stage.name, "assigned")
        self.assertEqual(len(result), 1)
        
        # Test with stage only filter
        result = self.get_students_from_onboarding(self.onboarding, self.stage.name, None)
        self.assertEqual(len(result), 1)
        
        # Test with no filters
        result = self.get_students_from_onboarding(self.onboarding, None, None)
        self.assertEqual(len(result), 1)
        
        # Test with not_started status (special case)
        mock_get_all.side_effect = [
            [{"student_id": self.student.name}],  # Backend students
            []  # No stage progress records
        ]
        
        result = self.get_students_from_onboarding(self.onboarding, self.stage.name, "not_started")
        self.assertEqual(len(result), 1)

    # Test 14: update_student_stage_progress
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    def test_update_student_stage_progress(self, mock_now, mock_get_doc, mock_get_all):
        mock_now.return_value = "2024-01-01 00:00:00"
        
        # Test creating new progress record
        mock_get_all.return_value = []  # No existing record
        mock_new_doc = MagicMock()
        mock_get_doc.return_value = mock_new_doc
        
        self.update_student_stage_progress(self.student, self.stage)
        
        mock_new_doc.insert.assert_called_once()
        
        # Test updating existing record
        mock_get_all.return_value = [{"name": "PROG-001"}]  # Existing record
        mock_existing_doc = MagicMock()
        mock_existing_doc.status = "not_started"
        mock_get_doc.return_value = mock_existing_doc
        
        self.update_student_stage_progress(self.student, self.stage)
        
        mock_existing_doc.save.assert_called_once()
        
        # Test not updating completed record
        mock_existing_doc.status = "completed"
        
        self.update_student_stage_progress(self.student, self.stage)
        
        # Should not call save for completed records
        self.assertEqual(mock_existing_doc.save.call_count, 1)  # Still only called once from previous test

    # Test 15: update_student_stage_progress_batch
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    def test_update_student_stage_progress_batch(self, mock_update_progress):
        students = [self.student]
        self.update_student_stage_progress_batch(students, self.stage)
        
        mock_update_progress.assert_called_once_with(self.student, self.stage)
        
        # Test with empty list
        self.update_student_stage_progress_batch([], self.stage)
        # Should not call update for empty list
        self.assertEqual(mock_update_progress.call_count, 1)  # Still only called once

    # Test 16: get_job_status
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.utils.background_jobs.get_job_status')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.Job')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_redis_conn')
    def test_get_job_status(self, mock_get_redis, mock_job, mock_get_job_status):
        # Test finished job with results
        mock_get_job_status.return_value = "finished"
        mock_job_instance = MagicMock()
        mock_job_instance.result = {"success": True}
        mock_job.fetch.return_value = mock_job_instance
        mock_get_redis.return_value = MagicMock()
        
        result = self.get_job_status("test_job_id")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["results"], {"success": True})
        
        # Test finished job without results
        mock_job_instance.result = None
        result = self.get_job_status("test_job_id")
        self.assertEqual(result["status"], "complete")
        
        # Test failed job
        mock_get_job_status.return_value = "failed"
        result = self.get_job_status("test_job_id")
        self.assertEqual(result["status"], "failed")
        
        # Test unknown job status
        mock_get_job_status.return_value = "queued"
        result = self.get_job_status("test_job_id")
        self.assertEqual(result["status"], "queued")
        
        # Test error case
        mock_get_job_status.side_effect = Exception("Test error")
        result = self.get_job_status("test_job_id")
        self.assertEqual(result["status"], "error")

    # Test 17: get_onboarding_progress_report
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_onboarding_progress_report(self, mock_get_doc, mock_get_all):
        # Mock progress records
        mock_get_all.side_effect = [
            [{"name": "PROG-001", "student": self.student.name, "stage": self.stage.name, 
              "status": "assigned", "start_timestamp": "2024-01-01 00:00:00"}],  # Progress records
            [{"student_id": self.student.name}]  # Backend students for not_started check
        ]
        
        mock_get_doc.side_effect = [self.student, self.stage]
        
        result = self.get_onboarding_progress_report(self.onboarding.name, self.stage.name, "assigned")
        
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["assigned"], 1)
        self.assertEqual(len(result["details"]), 1)
        
        # Test with not_started status
        mock_get_all.side_effect = [
            [],  # No progress records
            [{"student_id": self.student.name}]  # Backend students
        ]
        
        result = self.get_onboarding_progress_report(self.onboarding.name, self.stage.name, "not_started")
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["summary"]["not_started"], 1)

    # Test 18: update_incomplete_stages
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    def test_update_incomplete_stages(self, mock_add_to_date, mock_now_datetime, mock_get_doc, mock_get_all):
        mock_now_datetime.return_value = "2024-01-01 00:00:00"
        mock_add_to_date.return_value = "2023-12-29 00:00:00"  # 3 days ago
        
        # Mock assigned records
        mock_get_all.return_value = [{"name": "PROG-001", "student": self.student.name, 
                                     "stage": self.stage.name, "start_timestamp": "2023-12-28 00:00:00"}]
        
        mock_progress = MagicMock()
        mock_progress.status = "assigned"
        mock_get_doc.return_value = mock_progress
        
        self.update_incomplete_stages()
        
        # Should update status to incomplete
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()
        
        # Test with no records to update
        mock_get_all.return_value = []
        self.update_incomplete_stages()
        # Should not call get_doc or save
        mock_get_doc.assert_called_once()  # Still only called once from previous test

    # Test 19: Test with legacy flow configuration in trigger_onboarding_flow
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_legacy(self, mock_get_doc, mock_enqueue):
        legacy_stage = MagicMock()
        legacy_stage.is_active = True
        legacy_stage.stage_flows = []  # No stage_flows
        legacy_stage.glific_flow_id = "legacy_flow_123"
        legacy_stage.glific_flow_type = "Group"
        
        mock_onboarding = MagicMock()
        mock_onboarding.status = "Processed"
        
        mock_get_doc.side_effect = [legacy_stage, mock_onboarding]
        mock_enqueue.return_value = "job_123"
        
        result = self.trigger_onboarding_flow(self.onboarding.name, self.stage.name, "assigned")
        
        self.assertTrue(result["success"])

    # Test 20: Test error handling in _trigger_onboarding_flow_job
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_trigger_onboarding_flow_job_error(self, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {"authorization": "test_token"}
        mock_get_doc.side_effect = Exception("Test error")
        
        result = self._trigger_onboarding_flow_job(
            self.onboarding.name, self.stage.name, "assigned", "flow_123", "Group"
        )
        
        self.assertIn("error", result)


if __name__ == '__main__':
    unittest.main()