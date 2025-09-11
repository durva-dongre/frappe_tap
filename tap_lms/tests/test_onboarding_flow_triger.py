# import unittest
# from unittest.mock import Mock, patch, MagicMock
# import json
# from datetime import datetime, timedelta
# import time
# import sys


# class TestOnboardingFlowFunctions(unittest.TestCase):
    
#     def setUp(self):
#         """Set up test fixtures"""
#         self.mock_onboarding_set = "TEST_ONBOARDING_001"
#         self.mock_onboarding_stage = "TEST_STAGE_001"
#         self.mock_student_status = "not_started"
#         self.mock_flow_id = "12345"
#         self.mock_job_id = "test_job_123"
#         self.mock_now = datetime.now()
        
#     def test_trigger_onboarding_flow_success(self):
#         """Test successful trigger_onboarding_flow execution"""
#         with patch('frappe.enqueue') as mock_enqueue, \
#              patch('frappe.get_doc') as mock_get_doc, \
#              patch('frappe.throw') as mock_throw:
            
#             # Mock stage document with new structure
#             mock_stage = Mock()
#             mock_stage.name = self.mock_onboarding_stage
#             mock_stage.is_active = True
#             mock_stage.stage_flows = [Mock(student_status="not_started", glific_flow_id="12345", flow_type="Group")]
            
#             # Mock onboarding document
#             mock_onboarding = Mock()
#             mock_onboarding.name = self.mock_onboarding_set
#             mock_onboarding.status = "Processed"
            
#             mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#             mock_enqueue.return_value = self.mock_job_id
            
#             # Define function locally
#             def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
#                 import frappe
                
#                 if not onboarding_set or not onboarding_stage:
#                     frappe.throw("Both Backend Student Onboarding Set and Onboarding Stage are required")
                    
#                 if not student_status:
#                     frappe.throw("Student status is required")
                    
#                 stage = frappe.get_doc("OnboardingStage", onboarding_stage)
                
#                 if not stage.is_active:
#                     frappe.throw("Selected Onboarding Stage is not active")
                    
#                 onboarding = frappe.get_doc("Backend Student Onboarding", onboarding_set)
#                 if onboarding.status != "Processed":
#                     frappe.throw("Selected Backend Student Onboarding Set is not in Processed status")
                
#                 flow_id = None
#                 flow_type = None
                
#                 if hasattr(stage, 'stage_flows') and stage.stage_flows:
#                     matching_flows = [flow for flow in stage.stage_flows if flow.student_status == student_status]
#                     if not matching_flows:
#                         frappe.throw("No flow configured for stage")
#                     flow_id = matching_flows[0].glific_flow_id
#                     flow_type = matching_flows[0].flow_type
                
#                 job_id = frappe.enqueue(
#                     "_trigger_onboarding_flow_job",
#                     queue="long",
#                     timeout=3600,
#                     job_name=f"Trigger {student_status} Flow: {onboarding_set} - {onboarding_stage}",
#                     onboarding_set=onboarding_set,
#                     onboarding_stage=onboarding_stage,
#                     student_status=student_status,
#                     flow_id=flow_id,
#                     flow_type=flow_type
#                 )
                
#                 return {"success": True, "job_id": job_id}
            
#             # Call function
#             result = trigger_onboarding_flow(
#                 self.mock_onboarding_set, 
#                 self.mock_onboarding_stage, 
#                 self.mock_student_status
#             )
            
#             # Assertions
#             self.assertTrue(result["success"])
#             self.assertEqual(result["job_id"], self.mock_job_id)
#             mock_enqueue.assert_called_once()
#             mock_throw.assert_not_called()
    
#     def test_trigger_onboarding_flow_missing_parameters(self):
#         """Test trigger_onboarding_flow with missing parameters"""
#         with patch('frappe.throw') as mock_throw:
            
#             def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
#                 import frappe
#                 if not onboarding_set or not onboarding_stage:
#                     frappe.throw("Both Backend Student Onboarding Set and Onboarding Stage are required")
#                 if not student_status:
#                     frappe.throw("Student status is required")
            
#             # Test missing onboarding_set
#             trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
#             mock_throw.assert_called()
            
#             # Reset and test missing onboarding_stage
#             mock_throw.reset_mock()
#             trigger_onboarding_flow(self.mock_onboarding_set, "", self.mock_student_status)
#             mock_throw.assert_called()
            
#             # Reset and test missing student_status
#             mock_throw.reset_mock()
#             trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "")
#             mock_throw.assert_called()
    
#     def test_trigger_onboarding_flow_inactive_stage(self):
#         """Test trigger_onboarding_flow with inactive stage"""
#         with patch('frappe.get_doc') as mock_get_doc, \
#              patch('frappe.throw') as mock_throw:
            
#             def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
#                 import frappe
#                 stage = frappe.get_doc("OnboardingStage", onboarding_stage)
#                 if not stage.is_active:
#                     frappe.throw("Selected Onboarding Stage is not active")
            
#             mock_stage = Mock()
#             mock_stage.is_active = False
#             mock_get_doc.return_value = mock_stage
            
#             trigger_onboarding_flow(
#                 self.mock_onboarding_set, 
#                 self.mock_onboarding_stage, 
#                 self.mock_student_status
#             )
            
#             mock_throw.assert_called_with("Selected Onboarding Stage is not active")
    
#     def test_trigger_group_flow_success(self):
#         """Test successful trigger_group_flow execution"""
#         with patch('requests.post') as mock_requests:
            
#             def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
#                 import frappe
#                 import requests
#                 import json
                
#                 if not flow_id:
#                     frappe.throw("No Glific flow ID available for this stage and status")
                
#                 mutation = """
#                 mutation startGroupFlow($flowId: ID!, $groupId: ID!, $defaultResults: Json!) {
#                     startGroupFlow(flowId: $flowId, groupId: $groupId, defaultResults: $defaultResults) {
#                         success
#                         errors {
#                             key
#                             message
#                         }
#                     }
#                 }
#                 """
                
#                 variables = {
#                     "flowId": flow_id,
#                     "groupId": "group_123",
#                     "defaultResults": json.dumps({
#                         "onboarding_stage": stage.name,
#                         "onboarding_set": onboarding.name,
#                         "student_status": student_status
#                     })
#                 }
                
#                 headers = {
#                     "authorization": auth_token,
#                     "Content-Type": "application/json"
#                 }
                
#                 payload = {
#                     "query": mutation,
#                     "variables": variables
#                 }
                
#                 response = requests.post("https://api.glific.org/api", json=payload, headers=headers)
                
#                 if response.status_code != 200:
#                     frappe.throw("Failed to communicate with Glific API")
                
#                 response_data = response.json()
                
#                 if response_data and response_data.get("data", {}).get("startGroupFlow", {}).get("success"):
#                     return {
#                         "group_flow_result": response_data.get("data", {}).get("startGroupFlow"),
#                         "group_count": 3
#                     }
#                 else:
#                     frappe.throw("Failed to trigger group flow")
            
#             # Mock dependencies
#             mock_onboarding = Mock()
#             mock_onboarding.name = self.mock_onboarding_set
            
#             mock_stage = Mock()
#             mock_stage.name = self.mock_onboarding_stage
            
#             # Mock successful API response
#             mock_response = Mock()
#             mock_response.status_code = 200
#             mock_response.json.return_value = {
#                 "data": {
#                     "startGroupFlow": {
#                         "success": True,
#                         "errors": []
#                     }
#                 }
#             }
#             mock_requests.return_value = mock_response
            
#             # Call function
#             result = trigger_group_flow(
#                 mock_onboarding, 
#                 mock_stage, 
#                 "Bearer test_token", 
#                 self.mock_student_status, 
#                 self.mock_flow_id
#             )
            
#             # Assertions
#             self.assertIn("group_flow_result", result)
#             self.assertEqual(result["group_count"], 3)
#             mock_requests.assert_called_once()
    
#     def test_trigger_group_flow_no_flow_id(self):
#         """Test trigger_group_flow without flow ID"""
#         with patch('frappe.throw') as mock_throw:
            
#             def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
#                 import frappe
#                 if not flow_id:
#                     frappe.throw("No Glific flow ID available for this stage and status")
            
#             mock_onboarding = Mock()
#             mock_stage = Mock()
            
#             trigger_group_flow(mock_onboarding, mock_stage, "Bearer test_token", self.mock_student_status, None)
            
#             mock_throw.assert_called_with("No Glific flow ID available for this stage and status")
    
#     def test_trigger_individual_flows_success(self):
#         """Test successful trigger_individual_flows execution"""
#         def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
#             if not flow_id:
#                 raise Exception("No Glific flow ID available for this stage and status")
            
#             # Mock students
#             students = [
#                 Mock(name="student_1", name1="Student 1", glific_id="glific_1"),
#                 Mock(name="student_2", name1="Student 2", glific_id="glific_2"),
#                 Mock(name="student_3", name1="Student 3", glific_id="glific_3")
#             ]
            
#             if not students:
#                 raise Exception("No students found in this onboarding set with the selected status")
            
#             success_count = 0
#             error_count = 0
#             results = []
            
#             for student in students:
#                 if not student.glific_id:
#                     continue
                
#                 # Mock successful flow start
#                 success = True  # Simulate successful flow start
                
#                 if success:
#                     success_count += 1
#                     results.append({
#                         "student": student.name,
#                         "student_name": student.name1,
#                         "glific_id": student.glific_id,
#                         "success": True
#                     })
#                 else:
#                     error_count += 1
#                     results.append({
#                         "student": student.name,
#                         "student_name": student.name1,
#                         "glific_id": student.glific_id,
#                         "success": False,
#                         "error": "Failed to start flow"
#                     })
            
#             return {
#                 "individual_flow_results": results,
#                 "individual_count": success_count,
#                 "error_count": error_count
#             }
        
#         mock_onboarding = Mock()
#         mock_onboarding.name = self.mock_onboarding_set
#         mock_stage = Mock()
#         mock_stage.name = self.mock_onboarding_stage
        
#         # Call function
#         result = trigger_individual_flows(
#             mock_onboarding, 
#             mock_stage, 
#             "Bearer test_token", 
#             self.mock_student_status, 
#             self.mock_flow_id
#         )
        
#         # Assertions
#         self.assertEqual(result["individual_count"], 3)
#         self.assertEqual(result["error_count"], 0)
#         self.assertEqual(len(result["individual_flow_results"]), 3)
    
#     def test_trigger_individual_flows_missing_glific_id(self):
#         """Test trigger_individual_flows with students missing Glific ID"""
#         def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
#             if not flow_id:
#                 raise Exception("No Glific flow ID available for this stage and status")
            
#             # Mock student without Glific ID
#             students = [Mock(name="student_1", name1="Student 1", glific_id=None)]
            
#             if not students:
#                 raise Exception("No students found in this onboarding set with the selected status")
            
#             success_count = 0
#             error_count = 0
#             results = []
            
#             for student in students:
#                 if not student.glific_id:
#                     continue  
                
#                 success_count += 1
            
#             return {
#                 "individual_flow_results": results,
#                 "individual_count": success_count,
#                 "error_count": error_count
#             }
        
#         mock_onboarding = Mock()
#         mock_stage = Mock()
        
#         result = trigger_individual_flows(
#             mock_onboarding, 
#             mock_stage, 
#             "Bearer test_token", 
#             self.mock_student_status, 
#             self.mock_flow_id
#         )
        
#         # Should skip student without Glific ID
#         self.assertEqual(result["individual_count"], 0)
    
#     def test_get_stage_flow_statuses_new_structure(self):
#         """Test get_stage_flow_statuses with new child table structure"""
#         with patch('frappe.get_doc') as mock_get_doc:
            
#             def get_stage_flow_statuses(stage_id):
#                 import frappe
#                 try:
#                     stage = frappe.get_doc("OnboardingStage", stage_id)
                    
#                     if hasattr(stage, 'stage_flows') and stage.stage_flows:
#                         statuses = list(set([flow.student_status for flow in stage.stage_flows]))
#                         return {"statuses": statuses}
                    
#                     if hasattr(stage, 'glific_flow_id') and stage.glific_flow_id:
#                         return {"statuses": ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"]}
                    
#                     return {"statuses": []}
#                 except Exception as e:
#                     return {"statuses": [], "error": str(e)}
            
#             mock_stage = Mock()
#             mock_stage.stage_flows = [
#                 Mock(student_status="not_started"),
#                 Mock(student_status="in_progress"),
#                 Mock(student_status="completed")
#             ]
#             mock_get_doc.return_value = mock_stage
            
#             result = get_stage_flow_statuses("TEST_STAGE")
            
#             self.assertIn("statuses", result)
#             self.assertEqual(len(result["statuses"]), 3)
#             self.assertIn("not_started", result["statuses"])
#             self.assertIn("in_progress", result["statuses"])
#             self.assertIn("completed", result["statuses"])
    
#     def test_get_stage_flow_statuses_legacy_structure(self):
#         """Test get_stage_flow_statuses with legacy structure"""
#         with patch('frappe.get_doc') as mock_get_doc:
            
#             def get_stage_flow_statuses(stage_id):
#                 import frappe
#                 try:
#                     stage = frappe.get_doc("OnboardingStage", stage_id)
                    
#                     if hasattr(stage, 'stage_flows') and stage.stage_flows:
#                         statuses = list(set([flow.student_status for flow in stage.stage_flows]))
#                         return {"statuses": statuses}
                    
#                     if hasattr(stage, 'glific_flow_id') and stage.glific_flow_id:
#                         return {"statuses": ["not_started", "assigned", "in_progress", "completed", "incomplete", "skipped"]}
                    
#                     return {"statuses": []}
#                 except Exception as e:
#                     return {"statuses": [], "error": str(e)}
            
#             mock_stage = Mock()
#             mock_stage.stage_flows = None
#             mock_stage.glific_flow_id = "12345"
#             mock_get_doc.return_value = mock_stage
            
#             result = get_stage_flow_statuses("TEST_STAGE")
            
#             self.assertIn("statuses", result)
#             self.assertEqual(len(result["statuses"]), 6)  # All default statuses
    
#     def test_update_student_stage_progress_new_record(self):
#         """Test update_student_stage_progress creating new record"""
#         with patch('frappe.get_all') as mock_get_all, \
#              patch('frappe.new_doc') as mock_new_doc, \
#              patch('frappe.db.commit') as mock_commit:
            
#             def update_student_stage_progress(student, stage):
#                 import frappe
#                 from frappe.utils import now_datetime
                
#                 try:
#                     existing = frappe.get_all(
#                         "StudentStageProgress",
#                         filters={
#                             "student": student.name,
#                             "stage_type": "OnboardingStage",
#                             "stage": stage.name
#                         }
#                     )
                    
#                     timestamp = now_datetime()
                    
#                     if existing:
#                         progress = frappe.get_doc("StudentStageProgress", existing[0].name)
#                         if progress.status in ["not_started", "incomplete"]:
#                             progress.status = "assigned"
#                             progress.last_activity_timestamp = timestamp
#                             if not progress.start_timestamp:
#                                 progress.start_timestamp = timestamp
#                             progress.save()
#                     else:
#                         progress = frappe.new_doc("StudentStageProgress")
#                         progress.student = student.name
#                         progress.stage_type = "OnboardingStage"
#                         progress.stage = stage.name
#                         progress.status = "assigned"
#                         progress.start_timestamp = timestamp
#                         progress.last_activity_timestamp = timestamp
#                         progress.insert()
                    
#                     frappe.db.commit()
#                 except Exception:
#                     pass
            
#             mock_get_all.return_value = []  # No existing records
            
#             mock_progress = Mock()
#             mock_new_doc.return_value = mock_progress
            
#             mock_student = Mock()
#             mock_student.name = "STUD_001"
#             mock_stage = Mock()
#             mock_stage.name = "STAGE_001"
            
#             update_student_stage_progress(mock_student, mock_stage)
            
#             # Verify new document creation
#             mock_new_doc.assert_called_once_with("StudentStageProgress")
#             mock_progress.insert.assert_called_once()
#             self.assertEqual(mock_progress.student, "STUD_001")
#             self.assertEqual(mock_progress.stage, "STAGE_001")
#             self.assertEqual(mock_progress.status, "assigned")
    
#     def test_get_job_status_complete_with_results(self):
#         """Test get_job_status for completed job with results"""
#         def get_job_status(job_id):
#             if not job_id:
#                 return {"status": "unknown"}
            
#             # Mock job status check
#             if job_id == "finished_job":
#                 return {
#                     "status": "complete", 
#                     "results": {"success": True, "count": 5}
#                 }
#             elif job_id == "failed_job":
#                 return {"status": "failed"}
#             elif job_id == "running_job":
#                 return {"status": "started"}
#             else:
#                 return {"status": "unknown"}
        
#         result = get_job_status("finished_job")
        
#         self.assertEqual(result["status"], "complete")
#         self.assertIn("results", result)
#         self.assertEqual(result["results"]["count"], 5)
    
#     def test_get_job_status_no_job_id(self):
#         """Test get_job_status with no job ID"""
#         def get_job_status(job_id):
#             if not job_id:
#                 return {"status": "unknown"}
#             return {"status": "running"}
        
#         result = get_job_status("")
        
#         self.assertEqual(result["status"], "unknown")


# class TestOnboardingFlowIntegration(unittest.TestCase):
#     """Integration tests that test multiple functions working together"""
    
#     def setUp(self):
#         """Set up integration test fixtures"""
#         self.test_data = {
#             "onboarding_set": "INT_TEST_SET",
#             "stage": "INT_TEST_STAGE", 
#             "flow_id": "int_flow_123",
#             "students": [
#                 {"id": "INT_STUD_001", "name": "Integration Student 1", "glific_id": "int_glific_1"},
#                 {"id": "INT_STUD_002", "name": "Integration Student 2", "glific_id": "int_glific_2"}
#             ]
#         }
    
#     def test_complete_group_flow_workflow(self):
#         """Test complete workflow from trigger to group flow execution"""
#         with patch('frappe.enqueue') as mock_enqueue, \
#              patch('frappe.get_doc') as mock_get_doc:
            
#             def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
#                 import frappe
#                 stage = frappe.get_doc("OnboardingStage", onboarding_stage)
#                 onboarding = frappe.get_doc("Backend Student Onboarding", onboarding_set)
                
#                 if not stage.is_active:
#                     raise Exception("Stage not active")
#                 if onboarding.status != "Processed":
#                     raise Exception("Set not processed")
                    
#                 flow_id = None
#                 flow_type = None
                
#                 if hasattr(stage, 'stage_flows') and stage.stage_flows:
#                     matching_flows = [flow for flow in stage.stage_flows if flow.student_status == student_status]
#                     if matching_flows:
#                         flow_id = matching_flows[0].glific_flow_id
#                         flow_type = matching_flows[0].flow_type
                
#                 job_id = frappe.enqueue(
#                     "_trigger_onboarding_flow_job",
#                     queue="long",
#                     timeout=3600,
#                     job_name=f"Trigger {student_status} Flow: {onboarding_set} - {onboarding_stage}",
#                     onboarding_set=onboarding_set,
#                     onboarding_stage=onboarding_stage,
#                     student_status=student_status,
#                     flow_id=flow_id,
#                     flow_type=flow_type
#                 )
                
#                 return {"success": True, "job_id": job_id}
            
#             # Setup stage and onboarding mocks
#             mock_stage = Mock()
#             mock_stage.is_active = True
#             mock_stage.stage_flows = [Mock(student_status="not_started", glific_flow_id="group_flow_123", flow_type="Group")]
            
#             mock_onboarding = Mock()
#             mock_onboarding.status = "Processed"
            
#             mock_get_doc.side_effect = [mock_stage, mock_onboarding]
#             mock_enqueue.return_value = "integration_job_123"
            
#             # Trigger the flow
#             result = trigger_onboarding_flow(
#                 self.test_data["onboarding_set"],
#                 self.test_data["stage"],
#                 "not_started"
#             )
            
#             # Verify trigger response
#             self.assertTrue(result["success"])
#             self.assertEqual(result["job_id"], "integration_job_123")
            
#             # Verify job was enqueued with correct parameters
#             mock_enqueue.assert_called_once()
#             call_kwargs = mock_enqueue.call_args[1]
#             self.assertEqual(call_kwargs["flow_id"], "group_flow_123")
#             self.assertEqual(call_kwargs["flow_type"], "Group")
    
#     def test_complete_individual_flow_workflow(self):
#         """Test complete individual flow workflow with progress tracking"""
#         def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
#             if not flow_id:
#                 raise Exception("No flow ID")
            
#             # Mock students
#             students = []
#             for student_data in self.test_data["students"]:
#                 student = Mock()
#                 student.name = student_data["id"]
#                 student.name1 = student_data["name"] 
#                 student.glific_id = student_data["glific_id"]
#                 students.append(student)
            
#             if not students:
#                 raise Exception("No students found")
            
#             success_count = 0
#             error_count = 0
#             results = []
            
#             for student in students:
#                 if not student.glific_id:
#                     continue
                
#                 # Mock successful flow start
#                 success = True
                
#                 if success:
#                     # Mock progress update
#                     update_student_stage_progress(student, stage)
#                     success_count += 1
#                     results.append({
#                         "student": student.name,
#                         "student_name": student.name1,
#                         "glific_id": student.glific_id,
#                         "success": True
#                     })
#                 else:
#                     error_count += 1
#                     results.append({
#                         "student": student.name,
#                         "student_name": student.name1,
#                         "glific_id": student.glific_id,
#                         "success": False,
#                         "error": "Failed to start flow"
#                     })
            
#             return {
#                 "individual_flow_results": results,
#                 "individual_count": success_count,
#                 "error_count": error_count
#             }
        
#         def update_student_stage_progress(student, stage):
#             # Mock progress update
#             pass
        
#         # Mock documents
#         mock_onboarding = Mock(name=self.test_data["onboarding_set"])
#         mock_stage = Mock(name=self.test_data["stage"])
        
#         # Execute individual flows
#         result = trigger_individual_flows(
#             mock_onboarding,
#             mock_stage, 
#             "Bearer integration_token",
#             "not_started",
#             self.test_data["flow_id"]
#         )
        
#         # Verify results
#         self.assertEqual(result["individual_count"], 2)
#         self.assertEqual(result["error_count"], 0)
        
#         # Verify all students had flows started
#         self.assertEqual(len(result["individual_flow_results"]), 2)
#         for result_item in result["individual_flow_results"]:
#             self.assertTrue(result_item["success"])
 

# class TestOnboardingFlowEdgeCases(unittest.TestCase):
#     """Test edge cases and error conditions"""
    
#     def setUp(self):
#         """Set up edge case test fixtures"""
#         self.edge_case_data = {
#             "malformed_stage": Mock(is_active=True, stage_flows=[], glific_flow_id=None),
#             "empty_students": [],
#             "mixed_glific_ids": [
#                 Mock(name="STUD_001", glific_id="valid_id"),
#                 Mock(name="STUD_002", glific_id=None),
#                 Mock(name="STUD_003", glific_id=""),
#                 Mock(name="STUD_004", glific_id="another_valid_id")
#             ]
#         }
    
#     def test_malformed_stage_configuration(self):
#         """Test handling of malformed stage configurations"""
#         with patch('frappe.get_doc') as mock_get_doc:
            
#             def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
#                 import frappe
#                 stage = frappe.get_doc("OnboardingStage", onboarding_stage)
                
#                 # Check for flows
#                 flow_id = None
#                 if hasattr(stage, 'stage_flows') and stage.stage_flows:
#                     matching_flows = [flow for flow in stage.stage_flows if flow.student_status == student_status]
#                     if matching_flows:
#                         flow_id = matching_flows[0].glific_flow_id
#                 elif hasattr(stage, 'glific_flow_id') and stage.glific_flow_id:
#                     flow_id = stage.glific_flow_id
                
#                 if not flow_id:
#                     raise Exception("No flows configured for stage")
            
#             # Stage with empty flows and no legacy configuration
#             mock_get_doc.return_value = self.edge_case_data["malformed_stage"]
            
#             with self.assertRaises(Exception) as context:
#                 trigger_onboarding_flow("SET_001", "MALFORMED_STAGE", "not_started")
            
#             self.assertIn("No flows configured", str(context.exception))
    
#     def test_empty_student_list_handling(self):
#         """Test handling when no students are found"""
#         def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
#             students = self.edge_case_data["empty_students"]
            
#             if not students:
#                 raise Exception("No students found in this onboarding set with the selected status")
        
#         mock_onboarding = Mock()
#         mock_stage = Mock()
        
#         with self.assertRaises(Exception) as context:
#             trigger_individual_flows(
#                 mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
#             )
        
#         self.assertIn("No students found", str(context.exception))
    
#     def test_mixed_glific_id_scenarios(self):
#         """Test handling of students with mixed Glific ID statuses"""
#         def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
#             students = self.edge_case_data["mixed_glific_ids"]
            
#             success_count = 0
#             error_count = 0
#             results = []
            
#             for student in students:
#                 if not student.glific_id:
#                     continue  # Skip students without valid Glific IDs
                
#                 # Mock successful flow start for valid IDs
#                 success_count += 1
#                 results.append({
#                     "student": student.name,
#                     "success": True
#                 })
            
#             return {
#                 "individual_flow_results": results,
#                 "individual_count": success_count,
#                 "error_count": error_count
#             }
        
#         mock_onboarding = Mock()
#         mock_stage = Mock()
        
#         result = trigger_individual_flows(
#             mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
#         )
        
#         # Should only process students with valid Glific IDs
#         self.assertEqual(result["individual_count"], 2)  # Only 2 valid IDs
    
#     def test_database_connectivity_issues(self):
#         """Test handling of database connectivity issues"""
#         with patch('frappe.get_all') as mock_get_all:
            
#             def get_students_from_onboarding(onboarding):
#                 import frappe
#                 try:
#                     backend_students = frappe.get_all(
#                         "Backend Students", 
#                         filters={"parent": onboarding.name}
#                     )
#                     return backend_students
#                 except Exception:
#                     return []
            
#             # Simulate database connection failure
#             mock_get_all.side_effect = Exception("Database connection timeout")
            
#             mock_onboarding = Mock()
            
#             result = get_students_from_onboarding(mock_onboarding)
            
#             # Should return empty list
#             self.assertEqual(result, [])
    
#     def test_glific_api_timeout_handling(self):
#         """Test handling of Glific API timeouts"""
#         with patch('requests.post') as mock_requests:
            
#             def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
#                 import requests
#                 try:
#                     response = requests.post("https://api.glific.org/api", json={}, headers={})
#                     return {"success": True}
#                 except requests.exceptions.Timeout:
#                     raise Exception("API request timed out")
            
#             # Simulate API timeout
#             mock_requests.side_effect = Exception("API request timed out")
            
#             mock_onboarding = Mock()
#             mock_stage = Mock()
            
#             # # Should handle timeout gracefully
#             # with self.assertRaises(Exception) as context:
#             #     trigger_group_flow(
#             #         mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
#             #     )
            
#             # self.assertIn("timed out", str(context.exception))
#             # Should handle timeout gracefully
#             with self.assertRaises(Exception) as context:
#                 trigger_group_flow(
#                     mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
#                 )


# class TestOnboardingFlowPerformance(unittest.TestCase):
#     """Performance and scalability tests"""
    
#     def test_large_batch_processing_performance(self):
#         """Test performance with large batches of students"""
#         def trigger_individual_flows(onboarding, stage, auth_token, student_status=None, flow_id=None):
#             # Create 100 students to test scalability
#             large_student_batch = []
#             for i in range(100):
#                 student = Mock()
#                 student.name = f"STUD_{i:04d}"
#                 student.name1 = f"Student {i}"
#                 student.glific_id = f"glific_{i}"
#                 large_student_batch.append(student)
            
#             # Process students in batches
#             batch_size = 10
#             success_count = 0
#             error_count = 0
#             results = []
            
#             start_time = time.time()
            
#             for i in range(0, len(large_student_batch), batch_size):
#                 batch = large_student_batch[i:i+batch_size]
                
#                 for student in batch:
#                     if not student.glific_id:
#                         continue
                    
#                     # Mock successful flow start
#                     success = True
                    
#                     if success:
#                         success_count += 1
#                         results.append({
#                             "student": student.name,
#                             "student_name": student.name1,
#                             "glific_id": student.glific_id,
#                             "success": True
#                         })
#                     else:
#                         error_count += 1
#                         results.append({
#                             "student": student.name,
#                             "student_name": student.name1,
#                             "glific_id": student.glific_id,
#                             "success": False,
#                             "error": "Failed to start flow"
#                         })
                
#                 # Simulate sleep between batches
#                 time.sleep(0.001)  # Very small sleep for testing
            
#             execution_time = time.time() - start_time
            
#             return {
#                 "individual_flow_results": results,
#                 "individual_count": success_count,
#                 "error_count": error_count,
#                 "execution_time": execution_time
#             }
        
#         mock_onboarding = Mock()
#         mock_stage = Mock()
        
#         # Execute with timing consideration
#         result = trigger_individual_flows(
#             mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
#         )
        
#         # Verify all students processed
#         self.assertEqual(result["individual_count"], 100)
#         self.assertEqual(result["error_count"], 0)
        
#         # Performance assertion - should complete within reasonable time
#         self.assertLess(result["execution_time"], 5.0, "Large batch processing took too long")
    
#     def test_bulk_progress_update_performance(self):
#         """Test performance of bulk progress updates"""
#         def update_student_stage_progress_batch(students, stage):
#             if not students:
#                 return {"created_count": 0, "execution_time": 0}
            
#             timestamp = datetime.now()
#             updated_count = 0
#             created_count = 0
#             error_count = 0
            
#             start_time = time.time()
            
#             for student in students:
#                 try:
#                     # Mock progress update
#                     created_count += 1
#                 except Exception:
#                     error_count += 1
            
#             execution_time = time.time() - start_time
            
#             return {
#                 "updated_count": updated_count,
#                 "created_count": created_count,
#                 "error_count": error_count,
#                 "execution_time": execution_time
#             }
        
#         # Create large batch of students
#         students = [Mock(name=f"STUD_{i:04d}") for i in range(50)]
#         mock_stage = Mock(name="TEST_STAGE")
        
#         # Time the batch update
#         result = update_student_stage_progress_batch(students, mock_stage)
        
#         # Verify all records created
#         self.assertEqual(result["created_count"], 50)
        
#         # Performance assertion
#         self.assertLess(result["execution_time"], 3.0, "Bulk progress update took too long")


# class TestOnboardingFlowSecurity(unittest.TestCase):
#     """Security-related tests"""
    
#     def test_input_validation_sql_injection(self):
#         """Test protection against SQL injection attempts"""
#         with patch('frappe.get_doc') as mock_get_doc:
            
#             def trigger_onboarding_flow(onboarding_set, onboarding_stage, student_status=None):
#                 import frappe
#                 # Input validation - basic check
#                 if not onboarding_set or not onboarding_stage or not student_status:
#                     raise Exception("Invalid input parameters")
                
#                 # Frappe framework handles SQL injection protection
#                 stage = frappe.get_doc("OnboardingStage", onboarding_stage)
#                 return {"success": True}
            
#             # Attempt SQL injection in parameters
#             malicious_input = "'; DROP TABLE StudentStageProgress; --"
            
#             # Should handle malicious input safely
#             try:
#                 trigger_onboarding_flow(
#                     "VALID_SET",
#                     malicious_input,  # Malicious stage name
#                     "not_started"
#                 )
#             except Exception:
#                 pass  # Expected to fail safely
            
#             # Function should either throw validation error or handle safely
#             self.assertTrue(mock_get_doc.called)
    
#     def test_authentication_token_handling(self):
#         """Test secure handling of authentication tokens"""
#         def get_glific_auth_headers():
#             # Mock authentication check
#             return {"authorization": "Bearer valid_token"}
        
#         def _trigger_onboarding_flow_job(onboarding_set, onboarding_stage, student_status=None, flow_id=None, flow_type=None):
#             auth_headers = get_glific_auth_headers()
#             if not auth_headers or not auth_headers.get("authorization"):
#                 return {"error": "Failed to authenticate with Glific API"}
            
#             if not auth_headers.get("authorization").strip():
#                 return {"error": "Failed to authenticate with Glific API"}
            
#             return {"success": True}
        
#         # Test with valid token
#         result = _trigger_onboarding_flow_job(
#             "SET_001", "STAGE_001", "not_started", "flow_123", "Group"
#         )
#         self.assertIn("success", result)
        
#         # Test with None token
#         def get_glific_auth_headers_none():
#             return None
        
#         # Override the function for this test
#         original_get_headers = get_glific_auth_headers
#         get_glific_auth_headers = get_glific_auth_headers_none
        
#         result = _trigger_onboarding_flow_job(
#             "SET_001", "STAGE_001", "not_started", "flow_123", "Group"
#         )
#         self.assertIn("error", result)
#         self.assertEqual(result["error"], "Failed to authenticate with Glific API")
    
#     def test_api_response_sanitization(self):
#         """Test sanitization of API responses"""
#         with patch('requests.post') as mock_requests:
            
#             def trigger_group_flow(onboarding, stage, auth_token, student_status=None, flow_id=None):
#                 import requests
#                 response = requests.post("https://api.glific.org/api", json={}, headers={})
                
#                 if response.status_code != 200:
#                     raise Exception(f"API error: {response.status_code}")
                
#                 response_data = response.json()
                
#                 if response_data and response_data.get("data", {}).get("startGroupFlow", {}).get("success"):
#                     return {"success": True}
#                 else:
#                     error_data = response_data.get("data", {}).get("startGroupFlow", {}).get("errors", [])
#                     if error_data and len(error_data) > 0:
#                         # Sanitize error message (remove potential XSS)
#                         error_msg = str(error_data[0].get("message", "Unknown error")).replace("<", "&lt;").replace(">", "&gt;")
#                         raise Exception(f"Failed to trigger group flow: {error_msg}")
#                     else:
#                         raise Exception("Failed to trigger group flow: Unknown error")
            
#             # Mock response with potentially malicious content
#             mock_response = Mock()
#             mock_response.status_code = 200
#             mock_response.json.return_value = {
#                 "data": {
#                     "startGroupFlow": {
#                         "success": False,
#                         "errors": [
#                             {
#                                 "key": "malicious_key",
#                                 "message": "<script>alert('xss')</script>Malicious message"
#                             }
#                         ]
#                     }
#                 }
#             }
#             mock_requests.return_value = mock_response
            
#             mock_onboarding = Mock()
#             mock_stage = Mock()
            
#             # Should handle malicious content safely
#             with self.assertRaises(Exception) as context:
#                 trigger_group_flow(
#                     mock_onboarding, mock_stage, "Bearer token", "not_started", "flow_123"
#                 )
            
#             # Verify XSS content is sanitized
#             error_message = str(context.exception)
#             self.assertNotIn("<script>", error_message)
#             self.assertIn("&lt;script&gt;", error_message)


# # Test runner and configuration
# class TestOnboardingFlowRunner:
#     """Test runner with custom configuration"""
    
#     @staticmethod
#     def run_all_tests(verbosity=2):
#         """Run all test suites"""
#         # Create test suite
#         test_suite = unittest.TestSuite()
        
#         # Add all test classes
#         test_classes = [
#             TestOnboardingFlowFunctions,
#             TestOnboardingFlowIntegration,
#             TestOnboardingFlowEdgeCases,
#             TestOnboardingFlowPerformance,
#             TestOnboardingFlowSecurity
#         ]
        
#         for test_class in test_classes:
#             tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
#             test_suite.addTests(tests)
        
#         # Run tests with custom result class for better reporting
#         runner = unittest.TextTestRunner(
#             verbosity=verbosity,
#             stream=sys.stdout,
#             buffer=True,
#             failfast=False
#         )
        
#         result = runner.run(test_suite)
        
#         # Print summary
#         print(f"\n{'='*60}")
#         print(f"TEST SUMMARY")
#         print(f"{'='*60}")
#         print(f"Tests run: {result.testsRun}")
#         print(f"Failures: {len(result.failures)}")
#         print(f"Errors: {len(result.errors)}")
#         print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
        
#         if result.failures:
#             print(f"\nFAILURES:")
#             for test, traceback in result.failures:
#                 print(f"- {test}")
        
#         if result.errors:
#             print(f"\nERRORS:")
#             for test, traceback in result.errors:
#                 print(f"- {test}")
        
#         success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun) * 100
#         print(f"\nSuccess Rate: {success_rate:.1f}%")
        
#         return result.wasSuccessful()
    
#     @staticmethod
#     def run_specific_category(category_name, verbosity=2):
#         """Run tests for a specific category"""
#         category_map = {
#             'functions': TestOnboardingFlowFunctions,
#             'integration': TestOnboardingFlowIntegration,
#             'edge_cases': TestOnboardingFlowEdgeCases,
#             'performance': TestOnboardingFlowPerformance,
#             'security': TestOnboardingFlowSecurity
#         }
        
#         if category_name not in category_map:
#             print(f"Unknown category: {category_name}")
#             print(f"Available categories: {', '.join(category_map.keys())}")
#             return False
        
#         test_class = category_map[category_name]
#         suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
#         runner = unittest.TextTestRunner(verbosity=verbosity, buffer=True)
#         result = runner.run(suite)
        
#         return result.wasSuccessful()


# # Main execution
# if __name__ == '__main__':
#     # Check if specific category requested
#     if len(sys.argv) > 1 and sys.argv[1] in ['functions', 'integration', 'edge_cases', 'performance', 'security']:
#         category = sys.argv[1]
#         success = TestOnboardingFlowRunner.run_specific_category(category)
#     else:
#         # Run all tests
#         success = TestOnboardingFlowRunner.run_all_tests()
    
#     # Exit with appropriate code
#     sys.exit(0 if success else 1)



import unittest
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta
import time
import sys

# Import the actual module to test, adjusted for your nested structure
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

class TestOnboardingFlowFunctions(unittest.TestCase):
    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"
        self.mock_job_id = "test_job_123"
        self.mock_now = datetime.now()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_onboarding_flow_success(self, mock_logger, mock_enqueue, mock_throw, mock_get_doc):
        mock_stage = MagicMock()
        mock_stage.name = self.mock_onboarding_stage
        mock_stage.is_active = True
        mock_stage.stage_flows = [MagicMock(student_status="not_started", glific_flow_id=self.mock_flow_id, flow_type="Group")]
        mock_onboarding = MagicMock(name=self.mock_onboarding_set, status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = self.mock_job_id

        result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        self.assertTrue(result["success"])
        self.assertEqual(result["job_id"], self.mock_job_id)
        mock_enqueue.assert_called_once()
        mock_throw.assert_not_called()
        mock_logger.info.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_missing_parameters(self, mock_throw):
        with self.assertRaises(Exception):
            trigger_onboarding_flow("", self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(_("Both Backend Student Onboarding Set and Onboarding Stage are required"))

        mock_throw.reset_mock()
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, "", self.mock_student_status)
        mock_throw.assert_called_with(_("Both Backend Student Onboarding Set and Onboarding Stage are required"))

        mock_throw.reset_mock()
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, "")
        mock_throw.assert_called_with(_("Student status is required"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_inactive_stage(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=False)
        mock_get_doc.return_value = mock_stage
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(_("Selected Onboarding Stage is not active"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_unprocessed_set(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[MagicMock(student_status="not_started", glific_flow_id=self.mock_flow_id)])
        mock_onboarding = MagicMock(status="Draft")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(_("Selected Backend Student Onboarding Set is not in Processed status"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_onboarding_flow_no_flows(self, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[], glific_flow_id=None)
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        with self.assertRaises(Exception):
            trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        mock_throw.assert_called_with(_("No flows configured for stage '{0}'").format(self.mock_onboarding_stage))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.enqueue')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_onboarding_flow_legacy(self, mock_logger, mock_enqueue, mock_throw, mock_get_doc):
        mock_stage = MagicMock(is_active=True, stage_flows=[], glific_flow_id=self.mock_flow_id, glific_flow_type="Group")
        mock_onboarding = MagicMock(status="Processed")
        mock_get_doc.side_effect = [mock_stage, mock_onboarding]
        mock_enqueue.return_value = self.mock_job_id

        result = trigger_onboarding_flow(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status)
        self.assertTrue(result["success"])
        mock_logger.warning.assert_called()
        mock_enqueue.assert_called_once()

class TestOnboardingFlowJobAndGroup(unittest.TestCase):
    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_glific_auth_headers')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_onboarding_flow_job_auth_error(self, mock_logger, mock_get_doc, mock_auth_headers):
        mock_auth_headers.return_value = {}
        mock_stage = MagicMock()
        mock_onboarding = MagicMock()
        mock_glific_settings = MagicMock()
        mock_get_doc.side_effect = [mock_stage, mock_onboarding, mock_glific_settings]

        result = _trigger_onboarding_flow_job(self.mock_onboarding_set, self.mock_onboarding_stage, self.mock_student_status, self.mock_flow_id, "Group")
        self.assertEqual(result["error"], "Failed to authenticate with Glific API")
        mock_logger.error.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress_batch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_group_flow_success(self, mock_logger, mock_update_progress, mock_get_students, mock_create_group, mock_get_doc, mock_requests):
        mock_onboarding = MagicMock(name=self.mock_onboarding_set)
        mock_stage = MagicMock(name=self.mock_onboarding_stage)
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_create_group.return_value = {"group_id": "group_123"}
        mock_get_students.return_value = [MagicMock()]
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"data": {"startGroupFlow": {"success": True, "errors": []}}}
        mock_requests.return_value = mock_response

        result = trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertIn("group_flow_result", result)
        self.assertEqual(result["group_count"], 1)
        mock_update_progress.assert_called_once()
        mock_logger.debug.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_group_flow_api_error(self, mock_throw, mock_get_doc, mock_requests):
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        mock_contact_group = MagicMock(group_id="group_123")
        mock_glific_settings = MagicMock(api_url="https://api.glific.org")
        mock_get_doc.side_effect = [mock_contact_group, mock_glific_settings]
        mock_response = MagicMock(status_code=500, text="Server Error")
        mock_requests.return_value = mock_response

        with self.assertRaises(Exception):
            trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        mock_throw.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_group_flow_no_group(self, mock_throw, mock_get_doc):
        mock_onboarding = MagicMock()
        mock_stage = MagicMock()
        with patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.create_or_get_glific_group_for_batch', return_value=None):
            with self.assertRaises(Exception):
                trigger_group_flow(mock_onboarding, mock_stage, "Bearer token", self.mock_student_status, self.mock_flow_id)
        mock_throw.assert_called_with(_("Could not find or create contact group for this onboarding set"))

class TestOnboardingIndividualAndStudents(unittest.TestCase):
    def setUp(self):
        self.mock_onboarding_set = "TEST_ONBOARDING_001"
        self.mock_onboarding_stage = "TEST_STAGE_001"
        self.mock_student_status = "not_started"
        self.mock_flow_id = "12345"

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_trigger_individual_flows_no_students(self, mock_throw, mock_get_students):
        mock_get_students.return_value = []
        with self.assertRaises(Exception):
            trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
        mock_throw.assert_called_with(_("No students found in this onboarding set with the selected status"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.update_student_stage_progress')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_trigger_individual_flows_success(self, mock_commit, mock_logger, mock_update_progress, mock_start_flow, mock_get_students):
        mock_student = MagicMock(name="STUD_001", name1="Student1", glific_id="glific_1")
        mock_get_students.return_value = [mock_student]
        mock_start_flow.return_value = True

        result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertEqual(result["individual_count"], 1)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(len(result["individual_flow_results"]), 1)
        mock_update_progress.assert_called_once()
        mock_commit.assert_called()
        mock_logger.debug.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_individual_flows_no_glific_id(self, mock_logger, mock_get_students):
        mock_student = MagicMock(name="STUD_001", name1="Student1", glific_id=None)
        mock_get_students.return_value = [mock_student]
        result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertEqual(result["individual_count"], 0)
        self.assertEqual(result["error_count"], 0)
        mock_logger.warning.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    def test_trigger_individual_flows_flow_error(self, mock_logger, mock_start_flow, mock_get_students):
        mock_student = MagicMock(name="STUD_001", name1="Student1", glific_id="glific_1")
        mock_get_students.return_value = [mock_student]
        mock_start_flow.side_effect = Exception("Flow error")
        result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", self.mock_student_status, self.mock_flow_id)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["individual_count"], 0)
        mock_logger.error.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding_no_students(self, mock_get_doc, mock_get_all):
        mock_get_all.return_value = []
        result = get_students_from_onboarding(MagicMock(name="TEST_SET"), None, None)
        self.assertEqual(result, [])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding_with_filters(self, mock_get_doc, mock_get_all):
        mock_student = MagicMock(name="STUD_001")
        mock_get_all.side_effect = [[{"student_id": "STUD_001"}], [{"name": "progress_1"}]]
        mock_get_doc.return_value = mock_student
        result = get_students_from_onboarding(MagicMock(name="TEST_SET"), "TEST_STAGE", "in_progress")
        self.assertEqual(len(result), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_students_from_onboarding_not_started(self, mock_get_doc, mock_get_all):
        mock_student = MagicMock(name="STUD_001")
        mock_get_all.side_effect = [[{"student_id": "STUD_001"}], []]  # No progress records
        mock_get_doc.return_value = mock_student
        result = get_students_from_onboarding(MagicMock(name="TEST_SET"), "TEST_STAGE", "not_started")
        self.assertEqual(len(result), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_update_student_stage_progress_existing(self, mock_commit, mock_get_doc, mock_get_all):
        mock_student = MagicMock(name="STUD_001")
        mock_stage = MagicMock(name="TEST_STAGE")
        mock_progress = MagicMock(status="not_started")
        mock_get_all.return_value = [{"name": "progress_1"}]
        mock_get_doc.return_value = mock_progress
        update_student_stage_progress(mock_student, mock_stage)
        self.assertEqual(mock_progress.status, "assigned")
        mock_progress.save.assert_called_once()
        mock_commit.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_update_student_stage_progress_new(self, mock_commit, mock_new_doc, mock_get_all):
        mock_student = MagicMock(name="STUD_001")
        mock_stage = MagicMock(name="TEST_STAGE")
        mock_progress = MagicMock()
        mock_get_all.return_value = []
        mock_new_doc.return_value = mock_progress
        update_student_stage_progress(mock_student, mock_stage)
        mock_new_doc.assert_called_once_with("StudentStageProgress")
        mock_progress.insert.assert_called_once()
        mock_commit.assert_called()

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.new_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.logger')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_update_student_stage_progress_batch_mixed(self, mock_commit, mock_logger, mock_new_doc, mock_get_all):
        mock_students = [MagicMock(name="STUD_001"), MagicMock(name="STUD_002")]
        mock_stage = MagicMock()
        mock_progress = MagicMock(status="not_started")
        mock_get_all.side_effect = [[{"name": "progress_1"}], Exception("DB error")]
        mock_new_doc.return_value = mock_progress
        update_student_stage_progress_batch(mock_students, mock_stage)
        mock_progress.save.assert_called_once()  # First student updated
        mock_logger.error.assert_called()  # Second student error logged
        mock_commit.assert_called()

class TestOnboardingJobReportAndScheduled(unittest.TestCase):
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')  # From frappe.utils.background_jobs
    @patch('rq.job.Job.fetch')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_redis_conn')
    def test_get_job_status_finished_with_results(self, mock_redis_conn, mock_job_fetch, mock_get_job_status):
        mock_get_job_status.return_value = "finished"
        mock_job = MagicMock(result={"key": "value"})
        mock_job_fetch.return_value = mock_job
        mock_redis_conn.return_value = MagicMock()

        result = get_job_status("finished_job")
        self.assertEqual(result["status"], "complete")
        self.assertIn("results", result)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_job_status')
    def test_get_job_status_failed(self, mock_get_job_status):
        mock_get_job_status.return_value = "failed"
        result = get_job_status("failed_job")
        self.assertEqual(result["status"], "failed")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_onboarding_progress_report_filtered(self, mock_get_doc, mock_get_all):
        mock_progress = {"name": "progress_1", "student": "STUD_001", "stage": "TEST_STAGE", "status": "in_progress"}
        mock_get_all.return_value = [mock_progress]
        mock_student = MagicMock(name1="Student1", phone="123")
        mock_stage = MagicMock()
        mock_get_doc.side_effect = [mock_student, mock_stage]
        result = get_onboarding_progress_report(stage="TEST_STAGE", status="in_progress")
        self.assertEqual(result["summary"]["in_progress"], 1)
        self.assertEqual(len(result["details"]), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    def test_get_onboarding_progress_report_not_started(self, mock_get_doc, mock_get_all):
        mock_get_all.side_effect = [[], [{"student_id": "STUD_001"}]]  # No progress, has backend student
        mock_student = MagicMock(name1="Student1", phone="123")
        mock_stage = MagicMock()
        mock_get_doc.side_effect = [mock_student, mock_stage]
        result = get_onboarding_progress_report(set="TEST_SET", stage="TEST_STAGE", status="not_started")
        self.assertEqual(result["summary"]["not_started"], 1)
        self.assertEqual(len(result["details"]), 1)

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.now_datetime')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.add_to_date')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.db.commit')
    def test_update_incomplete_stages(self, mock_commit, mock_add_to_date, mock_now_datetime, mock_get_doc, mock_get_all):
        mock_now_datetime.return_value = datetime.now()
        mock_add_to_date.return_value = datetime.now() - timedelta(days=4)
        mock_progress = MagicMock(status="assigned")
        mock_get_all.return_value = [{"name": "progress_1", "student": "STUD_001", "stage": "TEST_STAGE", "start_timestamp": datetime.now() - timedelta(days=5)}]
        mock_get_doc.return_value = mock_progress
        update_incomplete_stages()
        self.assertEqual(mock_progress.status, "incomplete")
        mock_progress.save.assert_called_once()
        mock_commit.assert_called()

class TestOnboardingFlowEdgeCases(unittest.TestCase):
    def setUp(self):
        self.edge_case_data = {
            "malformed_stage": MagicMock(is_active=True, stage_flows=[], glific_flow_id=None),
            "empty_students": [],
            "mixed_glific_ids": [
                MagicMock(name="STUD_001", glific_id="valid_id"),
                MagicMock(name="STUD_002", glific_id=None),
                MagicMock(name="STUD_003", glific_id=""),
                MagicMock(name="STUD_004", glific_id="another_valid_id")
            ]
        }

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_doc')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.throw')
    def test_malformed_stage_configuration(self, mock_throw, mock_get_doc):
        mock_get_doc.side_effect = [self.edge_case_data["malformed_stage"], MagicMock(status="Processed")]
        with self.assertRaises(Exception):
            trigger_onboarding_flow("SET_001", "MALFORMED_STAGE", "not_started")
        mock_throw.assert_called_with(_("No flows configured for stage '{0}'").format("MALFORMED_STAGE"))

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    def test_empty_student_list_handling(self, mock_get_students):
        mock_get_students.return_value = self.edge_case_data["empty_students"]
        with self.assertRaises(Exception):
            trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", "not_started", "flow_123")

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.get_students_from_onboarding')
    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.start_contact_flow')
    def test_mixed_glific_id_scenarios(self, mock_start_flow, mock_get_students):
        mock_get_students.return_value = self.edge_case_data["mixed_glific_ids"]
        mock_start_flow.return_value = True
        result = trigger_individual_flows(MagicMock(), MagicMock(), "Bearer token", "not_started", "flow_123")
        self.assertEqual(result["individual_count"], 2)  # Only valid IDs processed

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.frappe.get_all')
    def test_database_connectivity_issues(self, mock_get_all):
        mock_get_all.side_effect = Exception("Database connection timeout")
        result = get_students_from_onboarding(MagicMock(), None, None)
        self.assertEqual(result, [])

    @patch('tap_lms.tap_lms.page.onboarding_flow_trigger.onboarding_flow_trigger.requests.post')
    def test_glific_api_timeout_handling(self, mock_requests):
        mock_requests.side_effect = Exception("API request timed out")
        with self.assertRaises(Exception):
            trigger_group_flow(MagicMock(), MagicMock(), "Bearer token", "not_started", "flow_123")

class TestOnboardingFlowRunner:
    @staticmethod
    def run_all_tests(verbosity=2):
        test_suite = unittest.TestSuite()
        test_classes = [
            TestOnboardingFlowFunctions,
            TestOnboardingFlowJobAndGroup,
            TestOnboardingIndividualAndStudents,
            TestOnboardingJobReportAndScheduled,
            TestOnboardingFlowEdgeCases
        ]
        for test_class in test_classes:
            tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
            test_suite.addTests(tests)
        runner = unittest.TextTestRunner(verbosity=verbosity, stream=sys.stdout, buffer=True)
        result = runner.run(test_suite)
        print(f"\n{'='*60}\nTEST SUMMARY\n{'='*60}")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun) * 100
        print(f"Success Rate: {success_rate:.1f}%")
        return result.wasSuccessful()

if __name__ == '__main__':
    success = TestOnboardingFlowRunner.run_all_tests()
    sys.exit(0 if success else 1)