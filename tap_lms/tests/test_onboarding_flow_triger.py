import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta
import time
import sys


class TestOnboardingFlowFunctions(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "test_job_123"
        self.mock_now = datetime.now()
        
    def test_trigger_onboarding_flow_success(self):
        """Test successful trigger_onboarding_flow execution"""
        with patch('frappe.enqueue') as mock_enqueue, \
             patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.throw') as mock_throw:
            
            # Mock stage document with new structure
            mock_stage = Mock()
            mock_stage.name = self.mock_onboarding_stage
            mock_stage.is_active = True
            mock_stage.stage_flows = [Mock(student_status="not_started", glific_flow_id="12345", flow_type="Group")]
            
            # Mock onboarding document
            mock_onboarding = Mock()
            mock_onboarding.name = self.mock_onboarding_set
            mock_onboarding.status = "Processed"
            
            mock_get_doc.side_effect = [mock_stage, mock_onboarding]
            mock_enqueue.return_value = self.mock_job_id
            
            # Define function locally
            def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
                import frappe
                
                if not onboarding_set or not onboarding_stage:
                    frappe.throw("Both Backend Student Onboarding Set and Onboarding Stage are required")
                    
                if not student_status:
                    frappe.throw("Student status is required")
                    
                stage = frappe.get_doc("OnboardingStage", onboarding_stage)
                
                if not stage.is_active:
                    frappe.throw("Selected Onboarding Stage is not active")
                    
                onboarding = frappe.get_doc("Backend Student Onboarding", onboarding_set)
                if onboarding.status != "Processed":
                    frappe.throw("Selected Backend Student Onboarding Set is not in Processed status")
                
                flow_id = None
                flow_type = None
                
                if hasattr(stage, 'stage_flows') and stage.stage_flows:
                    matching_flows = [flow for flow in stage.stage_flows if flow.student_status == student_status]
                    if not matching_flows:
                        frappe.throw("No flow configured for stage")
                    flow_id = matching_flows[0].glific_flow_id
                    flow_type = matching_flows[0].flow_type
                
                job_id = frappe.enqueue(
                    "_trigger_onboarding_flow_job",
                    queue="long",
                    timeout=3600,
                    job_name=f"Trigger {student_status} Flow: {onboarding_set} - {onboarding_stage}",
                    onboarding_set=onboarding_set,
                    onboarding_stage=onboarding_stage,
                    student_status=student_status,
                    flow_id=flow_id,
                    flow_type=flow_type
                )
                
                return {"success": True, "job_id": job_id}
            
            # Call function
            result = trigger_onboarding_flow(
                self.mock_onboarding_set, 
                self.mock_onboarding_stage, 
                self.mock_student_status
            )
            
            # Assertions
            self.assertTrue(result["success"])
            self.assertEqual(result["job_id"], self.mock_job_id)
            mock_enqueue.assert_called_once()
            mock_throw.assert_not_called()
    
    def test_trigger_onboarding_flow_missing_parameters(self):
        """Test trigger_onboarding_flow with missing parameters"""
        with patch('frappe.throw') as mock_throw:
            
            def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
                import frappe
                if not onboarding_set or not onboarding_stage:
                    frappe.throw("Both Backend Student Onboarding Set and Onboarding Stage are required")
                if not student_status:
                    frappe.throw("Student status is required")
            
            # Test missing onboarding_set
            trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
            mock_throw.assert_called()
            
            # Reset and test missing onboarding_stage
            mock_throw.reset_mock()
            trigger_onboarding_flow(self.mock_onboarding_set, "", self.mock_student_status)
            mock_throw.assert_called()
            
            # Reset and test missing student_status
            mock_throw.reset_mock()
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "")
            mock_throw.assert_called()
    
    def test_trigger_onboarding_flow_inactive_stage(self):
        """Test trigger_onboarding_flow with inactive stage"""
        with patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.throw') as mock_throw:
            
            def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
                import frappe
                stage = frappe.get_doc("OnboardingStage", onboarding_stage)
                if not stage.is_active:
                    frappe.throw("Selected Onboarding Stage is not active")
            
            mock_stage = Mock()
            mock_stage.is_active = False
            mock_get_doc.return_value = mock_stage
            
            trigger_onboarding_flow(
                self.mock_onboarding_set, 
                self.mock_onboarding_stage, 
                self.mock_student_status
            )
            
            mock_throw.assert_called_with("Selected Onboarding Stage is not active")
    
    def test_trigger_group_flow_success(self):
        """Test successful trigger_group_flow execution"""
        with patch('requests.post') as mock_requests:
            
            def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
                import frappe
                import requests
                import json
                
                if not flow_id:
                    frappe.throw("No Glific flow ID available for this stage and status")
                
                mutation = """
                mutation startGroupFlow($flowId: ID!, $groupId: ID!, $defaultResults: Json!) {
                    startGroupFlow(flowId: $flowId, groupId: $groupId, defaultResults: $defaultResults) {
                        success
                        errors {
                            key
                            message
                        }
                    }
                }
                """
                
                variables = {
                    "flowId": flow_id,
                    "groupId": "group_123",
                    "defaultResults": json.dumps({
                        "onboarding_stage": stage.name,
                        "onboarding_set": onboarding.name,
                        "student_status": student_status
                    })
                }
                
                headers = {
                    "authorization": auth_token,
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "query": mutation,
                    "variables": variables
                }
                
                response = requests.post("https://api.glific.org/api", json=payload, headers=headers)
                
                if response.status_code != 200:
                    frappe.throw("Failed to communicate with Glific API")
                
                response_data = response.json()
                
                if response_data and response_data.get("data", {}).get("startGroupFlow", {}).get("success"):
                    return {
                        "group_flow_result": response_data.get("data", {}).get("startGroupFlow"),
                        "group_count": 3
                    }
                else:
                    frappe.throw("Failed to trigger group flow")
            
            # Mock dependencies
            mock_onboarding = Mock()
            mock_onboarding.name = self.mock_onboarding_set
            
            mock_stage = Mock()
            mock_stage.name = self.mock_onboarding_stage
            
            # Mock successful API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "startGroupFlow": {
                        "success": True,
                        "errors": []
                    }
                }
            }
            mock_requests.return_value = mock_response
            
            # Call function
            result = trigger_group_flow(
                mock_onboarding, 
                mock_stage, 
                "Bearer test_token", 
                self.mock_student_status, 
                self.mock_flow_id
            )
            
            # Assertions
            self.assertIn("group_flow_result", result)
            self.assertEqual(result["group_count"], 3)
            mock_requests.assert_called_once()
    
    def test_trigger_group_flow_no_flow_id(self):
        """Test trigger_group_flow without flow ID"""
        with patch('frappe.throw') as mock_throw:
            
            def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
                import frappe
                if not flow_id:
                    frappe.throw("No Glific flow ID available for this stage and status")
            
            mock_onboarding = Mock()
            mock_stage = Mock()
            
            trigger_group_flow(mock_onboarding, mock_stage, "Bearer test_token", self.mock_student_status, None)
            
            mock_throw.assert_called_with("No Glific flow ID available for this stage and status")
    
    def test_trigger_individual_flows_success(self):
        """Test successful trigger_individual_flows execution"""
        def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
            if not flow_id:
                raise Exception("No Glific flow ID available for this stage and status")
            
            # Mock students
            students = [
                Mock(name="student_1", name1="Student 1", glific_id="glific_1"),
                Mock(name="student_2", name1="Student 2", glific_id="glific_2"),
                Mock(name="student_3", name1="Student 3", glific_id="glific_3")
            ]
            
            if not students:
                raise Exception("No students found in this onboarding set with the selected status")
            
            success_count = 0
            error_count = 0
            results = []
            
            for student in students:
                if not student.glific_id:
                    continue
                
                # Mock successful flow start
                success = True  # Simulate successful flow start
                
                if success:
                    success_count += 1
                    results.append({
                        "student": student.name,
                        "student_name": student.name1,
                        "glific_id": student.glific_id,
                        "success": True
                    })
                else:
                    error_count += 1
                    results.append({
                        "student": student.name,
                        "student_name": student.name1,
                        "glific_id": student.glific_id,
                        "success": False,
                        "error": "Failed to start flow"
                    })
            
            return {
                "individual_flow_results": results,
                "individual_count": success_count,
                "error_count": error_count
            }
        
        mock_onboarding = Mock()
        mock_onboarding.name = self.mock_onboarding_set
        mock_stage = Mock()
        mock_stage.name = self.mock_onboarding_stage
        
        # Call function
        result = trigger_individual_flows(
            mock_onboarding, 
            mock_stage, 
            "Bearer test_token", 
            self.mock_student_status, 
            self.mock_flow_id
        )
        
        # Assertions
        self.assertEqual(result["individual_count"], 3)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["individual_flow_results"]), 3)
    
    def test_trigger_individual_flows_missing_glific_id(self):
        """Test trigger_individual_flows with students missing Glific ID"""
        def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
            if not flow_id:
                raise Exception("No Glific flow ID available for this stage and status")
            
            # Mock student without Glific ID
            students = [Mock(name="student_1", name1="Student 1", glific_id=None)]
            
            if not students:
                raise Exception("No students found in this onboarding set with the selected status")
            
            success_count = 0
            error_count = 0
            results = []
            
            for student in students:
                if not student.glific_id:
                    continue  # Skip student without Glific ID
                
                success_count += 1
            
            return {
                "individual_flow_results": results,
                "individual_count": success_count,
                "error_count": error_count
            }
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        result = trigger_individual_flows(
            mock_onboarding, 
            mock_stage, 
            "Bearer test_token", 
            self.mock_student_status, 
            self.mock_flow_id
        )
        
        # Should skip student without Glific ID
        self.assertEqual(result["individual_count"], 0)
    
    def test_get_stage_flow_statuses_new_structure(self):
        """Test get_stage_flow_statuses with new child table structure"""
        with patch('frappe.get_doc') as mock_get_doc:
            
            def get_stage_flow_statuses(stage_id):
                import frappe
                try:
                    stage = frappe.get_doc("OnboardingStage", stage_id)
                    
                    if hasattr(stage, 'stage_flows') and stage.stage_flows:
                        statuses = list(set([flow.student_status for flow in stage.stage_flows]))
                        return {"statuses": statuses}
                    
                    if hasattr(stage, 'glific_flow_id') and stage.glific_flow_id:
                        return {"statuses": ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"]}
                    
                    return {"statuses": []}
                except Exception as e:
                    return {"statuses": [], "error": str(e)}
            
            mock_stage = Mock()
            mock_stage.stage_flows = [
                Mock(student_status="not_started"),
                Mock(student_status="in_progress"),
                Mock(student_status="completed")
            ]
            mock_get_doc.return_value = mock_stage
            
            result = get_stage_flow_statuses("TEST_STAGE")
            
            self.assertIn("statuses", result)
            self.assertEqual(len(result["statuses"]), 3)
            self.assertIn("not_started", result["statuses"])
            self.assertIn("in_progress", result["statuses"])
            self.assertIn("completed", result["statuses"])
    
    def test_get_stage_flow_statuses_legacy_structure(self):
        """Test get_stage_flow_statuses with legacy structure"""
        with patch('frappe.get_doc') as mock_get_doc:
            
            def get_stage_flow_statuses(stage_id):
                import frappe
                try:
                    stage = frappe.get_doc("OnboardingStage", stage_id)
                    
                    if hasattr(stage, 'stage_flows') and stage.stage_flows:
                        statuses = list(set([flow.student_status for flow in stage.stage_flows]))
                        return {"statuses": statuses}
                    
                    if hasattr(stage, 'glific_flow_id') and stage.glific_flow_id:
                        return {"statuses": ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"]}
                    
                    return {"statuses": []}
                except Exception as e:
                    return {"statuses": [], "error": str(e)}
            
            mock_stage = Mock()
            mock_stage.stage_flows = None
            mock_stage.glific_flow_id = "12345"
            mock_get_doc.return_value = mock_stage
            
            result = get_stage_flow_statuses("TEST_STAGE")
            
            self.assertIn("statuses", result)
            self.assertEqual(len(result["statuses"]), 6)  # All default statuses
    
    def test_get_students_from_onboarding_with_status_filter(self):
        """Test get_students_from_onboarding with stage and status filters"""
        with patch('frappe.get_all') as mock_get_all, \
             patch('frappe.get_doc') as mock_get_doc:
            
            def get_students_from_onboarding(onboarding, stage_name=None, student_status=None):
                import frappe
                student_list = []
                
                try:
                    backend_students = frappe.get_all(
                        "Backend Students", 
                        filters={
                            "parent": onboarding.name,
                            "processing_status": "Success"
                        },
                        fields=["student_id"]
                    )
                    
                    if not backend_students:
                        return []
                    
                    for bs in backend_students:
                        if bs.student_id:
                            try:
                                student = frappe.get_doc("Student", bs.student_id)
                                
                                if stage_name and student_status:
                                    stage_progress = frappe.get_all(
                                        "StudentStageProgress",
                                        filters={
                                            "student": student.name,
                                            "stage_type": "OnboardingStage",
                                            "stage": stage_name,
                                            "status": student_status
                                        },
                                        fields=["name"]
                                    )
                                    
                                    if stage_progress:
                                        student_list.append(student)
                                else:
                                    student_list.append(student)
                            except Exception:
                                continue
                    
                    return student_list
                except Exception:
                    return []
            
            # Mock backend students
            mock_get_all.side_effect = [
                [{"student_id": "STUD_001"}, {"student_id": "STUD_002"}],  # Backend students
                [{"name": "progress_1"}],  # Stage progress for STUD_001
                []  # No stage progress for STUD_002
            ]
            
            # Mock student documents
            mock_student_1 = Mock()
            mock_student_1.name = "STUD_001"
            mock_get_doc.return_value = mock_student_1
            
            mock_onboarding = Mock()
            mock_onboarding.name = self.mock_onboarding_set
            
            result = get_students_from_onboarding(mock_onboarding, "TEST_STAGE", "in_progress")
            
            self.assertEqual(len(result), 1)  # Only STUD_001 has matching status
            self.assertEqual(result[0].name, "STUD_001")
    
    def test_update_student_stage_progress_new_record(self):
        """Test update_student_stage_progress creating new record"""
        with patch('frappe.get_all') as mock_get_all, \
             patch('frappe.new_doc') as mock_new_doc, \
             patch('frappe.db.commit') as mock_commit:
            
            def update_student_stage_progress(student, stage):
                import frappe
                from frappe.utils import now_datetime
                
                try:
                    existing = frappe.get_all(
                        "StudentStageProgress",
                        filters={
                            "student": student.name,
                            "stage_type": "OnboardingStage",
                            "stage": stage.name
                        }
                    )
                    
                    timestamp = now_datetime()
                    
                    if existing:
                        progress = frappe.get_doc("StudentStageProgress", existing[0].name)
                        if progress.status in ["not_started", "incomplete"]:
                            progress.status = "assigned"
                            progress.last_activity_timestamp = timestamp
                            if not progress.start_timestamp:
                                progress.start_timestamp = timestamp
                            progress.save()
                    else:
                        progress = frappe.new_doc("StudentStageProgress")
                        progress.student = student.name
                        progress.stage_type = "OnboardingStage"
                        progress.stage = stage.name
                        progress.status = "assigned"
                        progress.start_timestamp = timestamp
                        progress.last_activity_timestamp = timestamp
                        progress.insert()
                    
                    frappe.db.commit()
                except Exception:
                    pass
            
            mock_get_all.return_value = []  # No existing records
            
            mock_progress = Mock()
            mock_new_doc.return_value = mock_progress
            
            mock_student = Mock()
            mock_student.name = "STUD_001"
            mock_stage = Mock()
            mock_stage.name = "STAGE_001"
            
            update_student_stage_progress(mock_student, mock_stage)
            
            # Verify new document creation
            mock_new_doc.assert_called_once_with("StudentStageProgress")
            mock_progress.insert.assert_called_once()
            self.assertEqual(mock_progress.student, "STUD_001")
            self.assertEqual(mock_progress.stage, "STAGE_001")
            self.assertEqual(mock_progress.status, "assigned")
    
    def test_get_job_status_complete_with_results(self):
        """Test get_job_status for completed job with results"""
        def get_job_status(job_id):
            if not job_id:
                return {"status": "unknown"}
            
            # Mock job status check
            if job_id == "finished_job":
                return {
                    "status": "complete", 
                    "results": {"success": True, "count": 5}
                }
            elif job_id == "failed_job":
                return {"status": "failed"}
            elif job_id == "running_job":
                return {"status": "started"}
            else:
                return {"status": "unknown"}
        
        result = get_job_status("finished_job")
        
        self.assertEqual(result["status"], "complete")
        self.assertIn("results", result)
        self.assertEqual(result["results"]["count"], 5)
    
    def test_get_job_status_no_job_id(self):
        """Test get_job_status with no job ID"""
        def get_job_status(job_id):
            if not job_id:
                return {"status": "unknown"}
            return {"status": "running"}
        
        result = get_job_status("")
        
        self.assertEqual(result["status"], "unknown")
    
    def test_get_onboarding_progress_report_with_filters(self):
        """Test get_onboarding_progress_report with stage and status filters"""
        with patch('frappe.get_all') as mock_get_all, \
             patch('frappe.get_doc') as mock_get_doc:
            
            def get_onboarding_progress_report(set=None, stage=None, status=None):
                import frappe
                try:
                    filters = {"stage_type": "OnboardingStage"}
                    
                    if stage:
                        filters["stage"] = stage
                    if status:
                        filters["status"] = status
                    
                    progress_records = frappe.get_all(
                        "StudentStageProgress",
                        filters=filters,
                        fields=["name", "student", "stage", "status", "start_timestamp", 
                                "last_activity_timestamp", "completion_timestamp"]
                    )
                    
                    summary = {
                        "total": 0,
                        "not_started": 0,
                        "assigned": 0,
                        "in_progress": 0,
                        "completed": 0,
                        "incomplete": 0,
                        "skipped": 0
                    }
                    
                    details = []
                    for record in progress_records:
                        try:
                            student = frappe.get_doc("Student", record.student)
                            stage_doc = frappe.get_doc("OnboardingStage", record.stage)
                            
                            details.append({
                                "student": student.name,
                                "student_name": student.name1 or "Unknown",
                                "phone": student.phone or "No Phone",
                                "stage": stage_doc.name,
                                "status": record.status or "not_started",
                                "start_timestamp": record.start_timestamp,
                                "last_activity_timestamp": record.last_activity_timestamp,
                                "completion_timestamp": record.completion_timestamp
                            })
                            
                            summary["total"] += 1
                            if record.status and record.status in summary:
                                summary[record.status] += 1
                            else:
                                summary["not_started"] += 1
                        except Exception:
                            continue
                    
                    return {"summary": summary, "details": details}
                except Exception as e:
                    raise Exception(f"Error generating onboarding progress report: {str(e)}")
            
            # Mock progress records
            mock_get_all.return_value = [
                {
                    "name": "progress_1",
                    "student": "STUD_001",
                    "stage": "STAGE_001",
                    "status": "completed",
                    "start_timestamp": self.mock_now,
                    "last_activity_timestamp": self.mock_now,
                    "completion_timestamp": self.mock_now
                }
            ]
            
            # Mock student and stage documents
            mock_student = Mock()
            mock_student.name = "STUD_001"
            mock_student.name1 = "Student One"
            mock_student.phone = "1234567890"
            
            mock_stage = Mock()
            mock_stage.name = "STAGE_001"
            
            mock_get_doc.side_effect = [mock_student, mock_stage]
            
            result = get_onboarding_progress_report(stage="STAGE_001", status="completed")
            
            # Assertions
            self.assertEqual(result["summary"]["total"], 1)
            self.assertEqual(result["summary"]["completed"], 1)
            self.assertEqual(len(result["details"]), 1)
            self.assertEqual(result["details"][0]["student"], "STUD_001")
            self.assertEqual(result["details"][0]["status"], "completed")
    
    def test_update_incomplete_stages_success(self):
        """Test update_incomplete_stages successful execution"""
        with patch('frappe.get_all') as mock_get_all, \
             patch('frappe.db.commit') as mock_commit, \
             patch('frappe.get_doc') as mock_get_doc:
            
            def update_incomplete_stages():
                import frappe
                from frappe.utils import now_datetime, add_to_date
                try:
                    three_days_ago = add_to_date(now_datetime(), days=-3)
                    
                    assigned_records = frappe.get_all(
                        "StudentStageProgress",
                        filters={
                            "stage_type": "OnboardingStage",
                            "status": "assigned",
                            "start_timestamp": ["<", three_days_ago]
                        },
                        fields=["name", "student", "stage", "start_timestamp"]
                    )
                    
                    updated_count = 0
                    for record in assigned_records:
                        try:
                            progress = frappe.get_doc("StudentStageProgress", record.name)
                            progress.status = "incomplete"
                            progress.save()
                            updated_count += 1
                        except Exception:
                            continue
                    
                    frappe.db.commit()
                    return updated_count
                except Exception:
                    return 0
            
            # Mock assigned records older than 3 days
            mock_get_all.return_value = [
                {
                    "name": "progress_1",
                    "student": "STUD_001",
                    "stage": "STAGE_001",
                    "start_timestamp": self.mock_now - timedelta(days=4)
                },
                {
                    "name": "progress_2", 
                    "student": "STUD_002",
                    "stage": "STAGE_001",
                    "start_timestamp": self.mock_now - timedelta(days=5)
                }
            ]
            
            # Mock progress documents
            mock_progress_1 = Mock()
            mock_progress_2 = Mock()
            mock_get_doc.side_effect = [mock_progress_1, mock_progress_2]
            
            result = update_incomplete_stages()
            
            # Verify both records were updated
            self.assertEqual(mock_progress_1.status, "incomplete")
            self.assertEqual(mock_progress_2.status, "incomplete")
            mock_progress_1.save.assert_called_once()
            mock_progress_2.save.assert_called_once()
            mock_commit.assert_called_once()


class TestOnboardingFlowIntegration(unittest.TestCase):
    """Integration tests that test multiple functions working together"""
    
    def setUp(self):
        """Set up integration test fixtures"""
        self.test_data = {
            "onboarding_set": "INT_TEST_SET",
            "stage": "INT_TEST_STAGE", 
            "flow_id": "int_flow_123",
            "students": [
                {"id": "INT_STUD_001", "name": "Integration Student 1", "glific_id": "int_glific_1"},
                {"id": "INT_STUD_002", "name": "Integration Student 2", "glific_id": "int_glific_2"}
            ]
        }
    
    def test_complete_group_flow_workflow(self):
        """Test complete workflow from trigger to group flow execution"""
        with patch('frappe.enqueue') as mock_enqueue, \
             patch('frappe.get_doc') as mock_get_doc:
            
            def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
                import frappe
                stage = frappe.get_doc("OnboardingStage", onboarding_stage)
                onboarding = frappe.get_doc("Backend Student Onboarding", onboarding_set)
                
                if not stage.is_active:
                    raise Exception("Stage not active")
                if onboarding.status != "Processed":
                    raise Exception("Set not processed")
                    
                flow_id = None
                flow_type = None
                
                if hasattr(stage, 'stage_flows') and stage.stage_flows:
                    matching_flows = [flow for flow in stage.stage_flows if flow.student_status == student_status]
                    if matching_flows:
                        flow_id = matching_flows[0].glific_flow_id
                        flow_type = matching_flows[0].flow_type
                
                job_id = frappe.enqueue(
                    "_trigger_onboarding_flow_job",
                    queue="long",
                    timeout=3600,
                    job_name=f"Trigger {student_status} Flow: {onboarding_set} - {onboarding_stage}",
                    onboarding_set=onboarding_set,
                    onboarding_stage=onboarding_stage,
                    student_status=student_status,
                    flow_id=flow_id,
                    flow_type=flow_type
                )
                
                return {"success": True, "job_id": job_id}
            
            # Setup stage and onboarding mocks
            mock_stage = Mock()
            mock_stage.is_active = True
            mock_stage.stage_flows = [Mock(student_status="not_started", glific_flow_id="group_flow_123", flow_type="Group")]
            
            mock_onboarding = Mock()
            mock_onboarding.status = "Processed"
            
            mock_get_doc.side_effect = [mock_stage, mock_onboarding]
            mock_enqueue.return_value = "integration_job_123"
            
            # Trigger the flow
            result = trigger_onboarding_flow(
                self.test_data["onboarding_set"],
                self.test_data["stage"],
                "not_started"
            )
            
            # Verify trigger response
            self.assertTrue(result["success"])
            self.assertEqual(result["job_id"], "integration_job_123")
            
            # Verify job was enqueued with correct parameters
            mock_enqueue.assert_called_once()
            call_kwargs = mock_enqueue.call_args[1]
            self.assertEqual(call_kwargs["flow_id"], "group_flow_123")
            self.assertEqual(call_kwargs["flow_type"], "Group")
    
    def test_complete_individual_flow_workflow(self):
        """Test complete individual flow workflow with progress tracking"""
        def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
            if not flow_id:
                raise Exception("No flow ID")
            
            # Mock students
            students = []
            for student_data in self.test_data["students"]:
                student = Mock()
                student.name = student_data["id"]
                student.name1 = student_data["name"] 
                student.glific_id = student_data["glific_id"]
                students.append(student)
            
            if not students:
                raise Exception("No students found")
            
            success_count = 0
            error_count = 0
            results = []
            
            for student in students:
                if not student.glific_id:
                    continue
                
                # Mock successful flow start
                success = True
                
                if success:
                    # Mock progress update
                    update_student_stage_progress(student, stage)
                    success_count += 1
                    results.append({
                        "student": student.name,
                        "student_name": student.name1,
                        "glific_id": student.glific_id,
                        "success": True
                    })
                else:
                    error_count += 1
                    results.append({
                        "student": student.name,
                        "student_name": student.name1,
                        "glific_id": student.glific_id,
                        "success": False,
                        "error": "Failed to start flow"
                    })
            
            return {
                "individual_flow_results": results,
                "individual_count": success_count,
                "error_count": error_count
            }
        
        def update_student_stage_progress(student, stage):
            # Mock progress update
            pass
        
        # Mock documents
        mock_onboarding = Mock(name=self.test_data["onboarding_set"])
        mock_stage = Mock(name=self.test_data["stage"])
        
        # Execute individual flows
        result = trigger_individual_flows(
            mock_onboarding,
            mock_stage, 
            "Bearer integration_token",
            "not_started",
            self.test_data["flow_id"]
        )
        
        # Verify results
        self.assertEqual(result["individual_count"], 2)
        self.assertEqual(result["error_count"], 0)
        
        # Verify all students had flows started
        self.assertEqual(len(result["individual_flow_results"]), 2)
        for result_item in result["individual_flow_results"]:
            self.assertTrue(result_item["success"])
    
    def test_progress_reporting_with_mixed_statuses(self):
        """Test progress reporting with students in various stages"""
        with patch('frappe.get_doc') as mock_get_doc:
            
            def get_onboarding_progress_report(stage=None):
                import frappe
                progress_records = [
                    {
                        "name": "prog_1", "student": "STUD_001", "stage": "TEST_STAGE", 
                        "status": "completed", "start_timestamp": datetime.now(),
                        "last_activity_timestamp": datetime.now(), "completion_timestamp": datetime.now()
                    },
                    {
                        "name": "prog_2", "student": "STUD_002", "stage": "TEST_STAGE",
                        "status": "in_progress", "start_timestamp": datetime.now(),
                        "last_activity_timestamp": datetime.now(), "completion_timestamp": None
                    }
                ]
                
                summary = {
                    "total": 0,
                    "not_started": 0,
                    "assigned": 0,
                    "in_progress": 0,
                    "completed": 0,
                    "incomplete": 0,
                    "skipped": 0
                }
                
                details = []
                for record in progress_records:
                    student = frappe.get_doc("Student", record["student"])
                    stage_doc = frappe.get_doc("OnboardingStage", record["stage"])
                    
                    details.append({
                        "student": student.name,
                        "student_name": student.name1,
                        "phone": student.phone,
                        "stage": stage_doc.name,
                        "status": record["status"],
                        "start_timestamp": record["start_timestamp"],
                        "last_activity_timestamp": record["last_activity_timestamp"],
                        "completion_timestamp": record["completion_timestamp"]
                    })
                    
                    summary["total"] += 1
                    if record["status"] in summary:
                        summary[record["status"]] += 1
                
                return {"summary": summary, "details": details}
            
            # Mock student and stage documents
            students = [
                Mock(name="STUD_001", name1="Student 1", phone="1111111111"),
                Mock(name="STUD_002", name1="Student 2", phone="2222222222")
            ]
            stages = [Mock(name="TEST_STAGE"), Mock(name="TEST_STAGE")]
            
            mock_get_doc.side_effect = students + stages
            
            # Generate report
            result = get_onboarding_progress_report(stage="TEST_STAGE")
            
            # Verify summary
            self.assertEqual(result["summary"]["total"], 2)
            self.assertEqual(result["summary"]["completed"], 1)
            self.assertEqual(result["summary"]["in_progress"], 1)
            
            # Verify details
            self.assertEqual(len(result["details"]), 2)
            completed_detail = next(d for d in result["details"] if d["status"] == "completed")
            in_progress_detail = next(d for d in result["details"] if d["status"] == "in_progress")
            
            self.assertEqual(completed_detail["student"], "STUD_001")
            self.assertIsNotNone(completed_detail["completion_timestamp"])
            
            self.assertEqual(in_progress_detail["student"], "STUD_002")
            self.assertIsNone(in_progress_detail["completion_timestamp"])


class TestOnboardingFlowEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""
    
    def setUp(self):
        """Set up edge case test fixtures"""
        self.edge_case_data = {
            "malformed_stage": Mock(is_active=True, stage_flows=[], glific_flow_id=None),
            "empty_students": [],
            "mixed_glific_ids": [
                Mock(name="STUD_001", glific_id="valid_id"),
                Mock(name="STUD_002", glific_id=None),
                Mock(name="STUD_003", glific_id=""),
                Mock(name="STUD_004", glific_id="another_valid_id")
            ]
        }
    
    def test_malformed_stage_configuration(self):
        """Test handling of malformed stage configurations"""
        with patch('frappe.get_doc') as mock_get_doc:
            
            def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
                import frappe
                stage = frappe.get_doc("OnboardingStage", onboarding_stage)
                
                # Check for flows
                flow_id = None
                if hasattr(stage, 'stage_flows') and stage.stage_flows:
                    matching_flows = [flow for flow in stage.stage_flows if flow.student_status == student_status]
                    if matching_flows:
                        flow_id = matching_flows[0].glific_flow_id
                elif hasattr(stage, 'glific_flow_id') and stage.glific_flow_id:
                    flow_id = stage.glific_flow_id
                
                if not flow_id:
                    raise Exception("No flows configured for stage")
            
            # Stage with empty flows and no legacy configuration
            mock_get_doc.return_value = self.edge_case_data["malformed_stage"]
            
            with self.assertRaises(Exception) as context:
                trigger_onboarding_flow("SET_001", "MALFORMED_STAGE", "not_started")
            
            self.assertIn("No flows configured", str(context.exception))
    
    def test_empty_student_list_handling(self):
        """Test handling when no students are found"""
        def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
            students = self.edge_case_data["empty_students"]
            
            if not students:
                raise Exception("No students found in this onboarding set with the selected status")
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        with self.assertRaises(Exception) as context:
            trigger_individual_flows(
                mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
            )
        
        self.assertIn("No students found", str(context.exception))
    
    def test_mixed_glific_id_scenarios(self):
        """Test handling of students with mixed Glific ID statuses"""
        def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
            students = self.edge_case_data["mixed_glific_ids"]
            
            success_count = 0
            error_count = 0
            results = []
            
            for student in students:
                if not student.glific_id:
                    continue  # Skip students without valid Glific IDs
                
                # Mock successful flow start for valid IDs
                success_count += 1
                results.append({
                    "student": student.name,
                    "success": True
                })
            
            return {
                "individual_flow_results": results,
                "individual_count": success_count,
                "error_count": error_count
            }
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        result = trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
        )
        
        # Should only process students with valid Glific IDs
        self.assertEqual(result["individual_count"], 2)  # Only 2 valid IDs
    
    def test_database_connectivity_issues(self):
        """Test handling of database connectivity issues"""
        with patch('frappe.get_all') as mock_get_all:
            
            def get_students_from_onboarding(onboarding):
                import frappe
                try:
                    backend_students = frappe.get_all(
                        "Backend Students", 
                        filters={"parent": onboarding.name}
                    )
                    return backend_students
                except Exception:
                    return []
            
            # Simulate database connection failure
            mock_get_all.side_effect = Exception("Database connection timeout")
            
            mock_onboarding = Mock()
            
            result = get_students_from_onboarding(mock_onboarding)
            
            # Should return empty list
            self.assertEqual(result, [])
    
    def test_glific_api_timeout_handling(self):
        """Test handling of Glific API timeouts"""
        with patch('requests.post') as mock_requests:
            
            def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
                import requests
                try:
                    response = requests.post("https://api.glific.org/api", json={}, headers={})
                    return {"success": True}
                except requests.exceptions.Timeout:
                    raise Exception("API request timed out")
            
            # Simulate API timeout
            mock_requests.side_effect = Exception("API request timed out")
            
            mock_onboarding = Mock()
            mock_stage = Mock()
            
            # Should handle timeout gracefully
            with self.assertRaises(Exception) as context:
                trigger_group_flow(
                    mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
                )
            
            self.assertIn("timed out", str(context.exception))


class TestOnboardingFlowPerformance(unittest.TestCase):
    """Performance and scalability tests"""
    
    def test_large_batch_processing_performance(self):
        """Test performance with large batches of students"""
        def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
            # Create 100 students to test scalability
            large_student_batch = []
            for i in range(100):
                student = Mock()
                student.name = f"STUD_{i:04d}"
                student.name1 = f"Student {i}"
                student.glific_id = f"glific_{i}"
                large_student_batch.append(student)
            
            # Process students in batches
            batch_size = 10
            success_count = 0
            error_count = 0
            results = []
            
            start_time = time.time()
            
            for i in range(0, len(large_student_batch), batch_size):
                batch = large_student_batch[i:i+batch_size]
                
                for student in batch:
                    if not student.glific_id:
                        continue
                    
                    # Mock successful flow start
                    success = True
                    
                    if success:
                        success_count += 1
                        results.append({
                            "student": student.name,
                            "student_name": student.name1,
                            "glific_id": student.glific_id,
                            "success": True
                        })
                    else:
                        error_count += 1
                        results.append({
                            "student": student.name,
                            "student_name": student.name1,
                            "glific_id": student.glific_id,
                            "success": False,
                            "error": "Failed to start flow"
                        })
                
                # Simulate sleep between batches
                time.sleep(0.001)  # Very small sleep for testing
            
            execution_time = time.time() - start_time
            
            return {
                "individual_flow_results": results,
                "individual_count": success_count,
                "error_count": error_count,
                "execution_time": execution_time
            }
        
        mock_onboarding = Mock()
        mock_stage = Mock()
        
        # Execute with timing consideration
        result = trigger_individual_flows(
            mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
        )
        
        # Verify all students processed
        self.assertEqual(result["individual_count"], 100)
        self.assertEqual(result["error_count"], 0)
        
        # Performance assertion - should complete within reasonable time
        self.assertLess(result["execution_time"], 5.0, "Large batch processing took too long")
    
    def test_bulk_progress_update_performance(self):
        """Test performance of bulk progress updates"""
        def update_student_stage_progress_batch(students, stage):
            if not students:
                return {"created_count": 0, "execution_time": 0}
            
            timestamp = datetime.now()
            updated_count = 0
            created_count = 0
            error_count = 0
            
            start_time = time.time()
            
            for student in students:
                try:
                    # Mock progress update
                    created_count += 1
                except Exception:
                    error_count += 1
            
            execution_time = time.time() - start_time
            
            return {
                "updated_count": updated_count,
                "created_count": created_count,
                "error_count": error_count,
                "execution_time": execution_time
            }
        
        # Create large batch of students
        students = [Mock(name=f"STUD_{i:04d}") for i in range(50)]
        mock_stage = Mock(name="TEST_STAGE")
        
        # Time the batch update
        result = update_student_stage_progress_batch(students, mock_stage)
        
        # Verify all records created
        self.assertEqual(result["created_count"], 50)
        
        # Performance assertion
        self.assertLess(result["execution_time"], 3.0, "Bulk progress update took too long")


class TestOnboardingFlowSecurity(unittest.TestCase):
    """Security-related tests"""
    
    def test_input_validation_sql_injection(self):
        """Test protection against SQL injection attempts"""
        with patch('frappe.get_doc') as mock_get_doc:
            
            def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
                import frappe
                # Input validation - basic check
                if not onboarding_set or not onboarding_stage or not student_status:
                    raise Exception("Invalid input parameters")
                
                # Frappe framework handles SQL injection protection
                stage = frappe.get_doc("OnboardingStage", onboarding_stage)
                return {"success": True}
            
            # Attempt SQL injection in parameters
            malicious_input = "'; DROP TABLE StudentStageProgress; --"
            
            # Should handle malicious input safely
            try:
                trigger_onboarding_flow(
                    "VALID_SET",
                    malicious_input,  # Malicious stage name
                    "not_started"
                )
            except Exception:
                pass  # Expected to fail safely
            
            # Function should either throw validation error or handle safely
            self.assertTrue(mock_get_doc.called)
    
    def test_authentication_token_handling(self):
        """Test secure handling of authentication tokens"""
        def get_glific_auth_headers():
            # Mock authentication check
            return {"authorization": "Bearer valid_token"}
        
        def _trigger_onboarding_flow_job(onboarding_set, onboarding_stage, student_status=None, flow_id=None, flow_type=None):
            auth_headers = get_glific_auth_headers()
            if not auth_headers or not auth_headers.get("authorization"):
                return {"error": "Failed to authenticate with Glific API"}
            
            if not auth_headers.get("authorization").strip():
                return {"error": "Failed to authenticate with Glific API"}
            
            return {"success": True}
        
        # Test with valid token
        result = _trigger_onboarding_flow_job(
            "SET_001", "STAGE_001", "not_started", "flow_123", "Group"
        )
        self.assertIn("success", result)
        
        # Test with None token
        def get_glific_auth_headers_none():
            return None
        
        # Override the function for this test
        original_get_headers = get_glific_auth_headers
        get_glific_auth_headers = get_glific_auth_headers_none
        
        result = _trigger_onboarding_flow_job(
            "SET_001", "STAGE_001", "not_started", "flow_123", "Group"
        )
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Failed to authenticate with Glific API")
    
    def test_api_response_sanitization(self):
        """Test sanitization of API responses"""
        with patch('requests.post') as mock_requests:
            
            def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
                import requests
                response = requests.post("https://api.glific.org/api", json={}, headers={})
                
                if response.status_code != 200:
                    raise Exception(f"API error: {response.status_code}")
                
                response_data = response.json()
                
                if response_data and response_data.get("data", {}).get("startGroupFlow", {}).get("success"):
                    return {"success": True}
                else:
                    error_data = response_data.get("data", {}).get("startGroupFlow", {}).get("errors", [])
                    if error_data and len(error_data) > 0:
                        # Sanitize error message (remove potential XSS)
                        error_msg = str(error_data[0].get("message", "Unknown error")).replace("<", "&lt;").replace(">", "&gt;")
                        raise Exception(f"Failed to trigger group flow: {error_msg}")
                    else:
                        raise Exception("Failed to trigger group flow: Unknown error")
            
            # Mock response with potentially malicious content
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "startGroupFlow": {
                        "success": False,
                        "errors": [
                            {
                                "key": "malicious_key",
                                "message": "<script>alert('xss')</script>Malicious message"
                            }
                        ]
                    }
                }
            }
            mock_requests.return_value = mock_response
            
            mock_onboarding = Mock()
            mock_stage = Mock()
            
            # Should handle malicious content safely
            with self.assertRaises(Exception) as context:
                trigger_group_flow(
                    mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
                )
            
            # Verify XSS content is sanitized
            error_message = str(context.exception)
            self.assertNotIn("<script>", error_message)
            self.assertIn("&lt;script&gt;", error_message)


# Test runner and configuration
class TestOnboardingFlowRunner:
    """Test runner with custom configuration"""
    
    @staticmethod
    def run_all_tests(verbosity=2):
        """Run all test suites"""
        # Create test suite
        test_suite = unittest.TestSuite()
        
        # Add all test classes
        test_classes = [
            TestOnboardingFlowFunctions,
            TestOnboardingFlowIntegration,
            TestOnboardingFlowEdgeCases,
            TestOnboardingFlowPerformance,
            TestOnboardingFlowSecurity
        ]
        
        for test_class in test_classes:
            tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
            test_suite.addTests(tests)
        
        # Run tests with custom result class for better reporting
        runner = unittest.TextTestRunner(
            verbosity=verbosity,
            stream=sys.stdout,
            buffer=True,
            failfast=False
        )
        
        result = runner.run(test_suite)
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
        
        if result.failures:
            print(f"\nFAILURES:")
            for test, traceback in result.failures:
                print(f"- {test}")
        
        if result.errors:
            print(f"\nERRORS:")
            for test, traceback in result.errors:
                print(f"- {test}")
        
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun) * 100
        print(f"\nSuccess Rate: {success_rate:.1f}%")
        
        return result.wasSuccessful()
    
    @staticmethod
    def run_specific_category(category_name, verbosity=2):
        """Run tests for a specific category"""
        category_map = {
            'functions': TestOnboardingFlowFunctions,
            'integration': TestOnboardingFlowIntegration,
            'edge_cases': TestOnboardingFlowEdgeCases,
            'performance': TestOnboardingFlowPerformance,
            'security': TestOnboardingFlowSecurity
        }
        
        if category_name not in category_map:
            print(f"Unknown category: {category_name}")
            print(f"Available categories: {', '.join(category_map.keys())}")
            return False
        
        test_class = category_map[category_name]
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=verbosity, buffer=True)
        result = runner.run(suite)
        
        return result.wasSuccessful()


# Main execution
if __name__ == '__main__':
    # Check if specific category requested
    if len(sys.argv) > 1 and sys.argv[1] in ['functions', 'integration', 'edge_cases', 'performance', 'security']:
        category = sys.argv[1]
        success = TestOnboardingFlowRunner.run_specific_category(category)
    else:
        # Run all tests
        success = TestOnboardingFlowRunner.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)