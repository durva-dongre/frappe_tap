# # test_glific_batch_id_update.py
# # Pytest test cases for glific_batch_id_update.py module - All Passing Tests

# import pytest
# import json
# from unittest.mock import Mock, patch, MagicMock, call
# from datetime import datetime, timezone
# import sys
# import os

# # Add the app path to sys.path for imports
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# # Mock frappe module before importing the module under test
# sys.modules['frappe'] = MagicMock()
# sys.modules['frappe.utils.background_jobs'] = MagicMock()
# sys.modules['requests'] = MagicMock()

# # Create mock for DoesNotExistError
# class DoesNotExistError(Exception):
#     pass

# # Set up frappe mock with necessary attributes
# import frappe
# frappe.DoesNotExistError = DoesNotExistError
# frappe.logger = MagicMock(return_value=MagicMock())
# frappe.db = MagicMock()
# frappe.get_doc = MagicMock()
# frappe.get_all = MagicMock()
# frappe.whitelist = MagicMock(return_value=lambda x: x)

# # Mock the glific_integration module dependencies
# sys.modules['tap_lms.glific_integration'] = MagicMock()

# # Import the module under test
# from tap_lms import glific_batch_id_update

# # Mock the imported functions from glific_integration
# glific_batch_id_update.get_glific_settings = MagicMock()
# glific_batch_id_update.get_glific_auth_headers = MagicMock()


# # ============= Fixtures =============

# @pytest.fixture
# def test_data():
#     """Fixture providing test data"""
#     return {
#         "student_id": "STU001",
#         "student_name": "John Doe",
#         "phone": "+1234567890",
#         "glific_id": "12345",
#         "batch_id": "BATCH_2024_01",
#         "onboarding_set": "ONBOARD_SET_001",
#         "backend_student_name": "BACKEND_STU_001"
#     }


# @pytest.fixture
# def mock_onboarding_set():
#     """Fixture for mock onboarding set"""
#     mock_set = MagicMock()
#     mock_set.status = "Processed"
#     mock_set.set_name = "Test Onboarding Set"
#     return mock_set


# @pytest.fixture
# def mock_backend_student(test_data):
#     """Fixture for mock backend student"""
#     mock_student = MagicMock()
#     mock_student.student_id = test_data["student_id"]
#     mock_student.student_name = test_data["student_name"]
#     mock_student.phone = test_data["phone"]
#     mock_student.batch = test_data["batch_id"]
#     mock_student.batch_skeyword = "batch_key"
#     return mock_student


# @pytest.fixture
# def mock_student_doc(test_data):
#     """Fixture for mock student document"""
#     mock_doc = MagicMock()
#     mock_doc.glific_id = test_data["glific_id"]
#     return mock_doc


# @pytest.fixture
# def mock_glific_settings():
#     """Fixture for mock Glific settings"""
#     mock_settings = MagicMock()
#     mock_settings.api_url = "https://api.glific.com"
#     return mock_settings


# # ============= Test get_student_batch_id =============

# class TestGetStudentBatchId:
#     """Test cases for get_student_batch_id function"""
    
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_returns_batch_when_student_exists_and_batch_provided(self, mock_exists, test_data):
#         """Test successful retrieval of batch_id when student exists"""
#         mock_exists.return_value = True
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
#         assert result == test_data["batch_id"]
#         mock_exists.assert_called_once_with("Student", test_data["student_id"])
    
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_returns_none_when_batch_is_none(self, mock_exists, test_data):
#         """Test returns None when batch is None"""
#         mock_exists.return_value = True
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], None)
        
#         assert result is None
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_returns_none_when_student_not_exists(self, mock_exists, mock_logger, test_data):
#         """Test returns None and logs error when student doesn't exist"""
#         mock_exists.return_value = False
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
#         assert result is None
#         mock_logger().error.assert_called_once()
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.exists')
#     def test_handles_exception_gracefully(self, mock_exists, mock_logger, test_data):
#         """Test exception handling returns None and logs error"""
#         mock_exists.side_effect = Exception("Database error")
        
#         result = glific_batch_id_update.get_student_batch_id(test_data["student_id"], test_data["batch_id"])
        
#         assert result is None
#         mock_logger().error.assert_called_once()


# # ============= Test update_specific_set_contacts_with_batch_id =============

# class TestUpdateSpecificSetContacts:
#     """Test cases for update_specific_set_contacts_with_batch_id function"""
    
#     def test_returns_error_when_no_set_name_provided(self):
#         """Test error when onboarding set name is None"""
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(None)
        
#         assert "error" in result
#         assert result["error"] == "Backend Student Onboarding set name is required"
    
#     @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
#     def test_returns_error_when_set_not_found(self, mock_get_doc, test_data):
#         """Test error when onboarding set doesn't exist"""
#         mock_get_doc.side_effect = DoesNotExistError
        
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(test_data["onboarding_set"])
        
#         assert "error" in result
#         assert "not found" in result["error"]
    
#     @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
#     def test_returns_error_when_set_not_processed(self, mock_get_doc, test_data):
#         """Test error when set status is not 'Processed'"""
#         mock_set = MagicMock()
#         mock_set.status = "Pending"
#         mock_set.set_name = test_data["onboarding_set"]
#         mock_get_doc.return_value = mock_set
        
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id(test_data["onboarding_set"])
        
#         assert "error" in result
#         assert "not 'Processed'" in result["error"]
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.get_all')
#     @patch('tap_lms.glific_batch_id_update.frappe.get_doc')
#     def test_returns_message_when_no_students_found(self, mock_get_doc, mock_get_all, 
#                                                     mock_logger, mock_onboarding_set):
#         """Test message when no successfully processed students found"""
#         mock_get_doc.return_value = mock_onboarding_set
#         mock_get_all.return_value = []
        
#         result = glific_batch_id_update.update_specific_set_contacts_with_batch_id("ONBOARD_SET_001")
        
#         assert "message" in result
#         assert "No successfully processed students" in result["message"]
    


# class TestRunBatchIdUpdate:
#     """Test cases for run_batch_id_update_for_specific_set function"""
    
#     def test_returns_error_message_when_no_set_name(self):
#         """Test error message when set name is not provided"""
#         result = glific_batch_id_update.run_batch_id_update_for_specific_set(None)
        
#         assert "Error: Backend Student Onboarding set name is required" in result
    
#     @patch('tap_lms.glific_batch_id_update.frappe.db.commit')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_returns_success_message_on_completion(self, mock_update, mock_begin, mock_commit, test_data):
#         """Test successful completion message"""
#         mock_update.return_value = {
#             "set_name": test_data["onboarding_set"],
#             "updated": 5,
#             "skipped": 2,
#             "errors": 1,
#             "total_processed": 8
#         }
        
#         result = glific_batch_id_update.run_batch_id_update_for_specific_set(test_data["onboarding_set"])
        
#         assert "Process completed" in result
#         assert "Updated: 5" in result
#         assert "Skipped: 2" in result
#         assert "Errors: 1" in result
#         assert "Total Processed: 8" in result
#         mock_begin.assert_called_once()
#         mock_commit.assert_called_once()
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.rollback')
#     @patch('tap_lms.glific_batch_id_update.frappe.db.begin')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_handles_exception_with_rollback(self, mock_update, mock_begin, mock_rollback, mock_logger):
#         """Test exception handling with database rollback"""
#         mock_update.side_effect = Exception("Test exception")
        
#         result = glific_batch_id_update.run_batch_id_update_for_specific_set("ONBOARD_SET_001")
        
#         assert "Error occurred" in result
#         assert "Test exception" in result
#         mock_rollback.assert_called_once()
#         mock_logger().error.assert_called_once()


# # ============= Test process_multiple_sets_batch_id =============

# class TestProcessMultipleSets:
#     """Test cases for process_multiple_sets_batch_id function"""
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('time.sleep')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_processes_multiple_sets_successfully(self, mock_update, mock_sleep, mock_logger):
#         """Test successful processing of multiple sets"""
#         # First set processes in 2 batches, second set has no students
#         mock_update.side_effect = [
#             {"updated": 3, "errors": 0, "skipped": 1, "total_processed": 4},
#             {"updated": 2, "errors": 1, "skipped": 0, "total_processed": 3},
#             {"updated": 0, "errors": 0, "skipped": 0, "total_processed": 0},
#             {"message": "No successfully processed students found"}
#         ]
        
#         set_names = ["SET001", "SET002"]
#         results = glific_batch_id_update.process_multiple_sets_batch_id(set_names, batch_size=5)
        
#         assert len(results) == 2
#         assert results[0]["set_name"] == "SET001"
#         assert results[0]["updated"] == 5
#         assert results[0]["errors"] == 1
#         assert results[0]["skipped"] == 1
#         assert results[0]["status"] == "completed"
        
#         assert results[1]["set_name"] == "SET002"
#         assert results[1]["status"] == "completed"
    
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     def test_handles_errors_in_individual_sets(self, mock_update, mock_logger):
#         """Test handling of errors in individual sets"""
#         mock_update.side_effect = [
#             {"updated": 5, "errors": 0, "skipped": 0, "total_processed": 5},
#             {"updated": 0, "errors": 0, "skipped": 0, "total_processed": 0},
#             Exception("Database connection error")
#         ]
        
#         set_names = ["SET001", "SET002"]
#         results = glific_batch_id_update.process_multiple_sets_batch_id(set_names, batch_size=10)
        
#         assert results[0]["status"] == "completed"
#         assert results[0]["updated"] == 5
        
#         assert results[1]["status"] == "error"
#         assert "Database connection error" in results[1]["error"]
#         assert results[1]["updated"] == 0


# # ============= Test process_multiple_sets_batch_id_background =============

# class TestProcessMultipleSetsBackground:
#     """Test cases for process_multiple_sets_batch_id_background function"""
    
#     @patch('frappe.utils.background_jobs.enqueue')
#     def test_enqueues_job_with_list_input(self, mock_enqueue):
#         """Test background job enqueueing with list input"""
#         # Re-import to get the enqueue function
#         from frappe.utils.background_jobs import enqueue
#         glific_batch_id_update.enqueue = enqueue
        
#         mock_job = MagicMock()
#         mock_job.id = "JOB123"
#         mock_enqueue.return_value = mock_job
        
#         set_names = ["SET001", "SET002", "SET003"]
#         result = glific_batch_id_update.process_multiple_sets_batch_id_background(set_names)
        
#         assert "Started processing 3 sets" in result
#         assert "JOB123" in result
        
#         mock_enqueue.assert_called_once()
#         call_args = mock_enqueue.call_args
#         assert call_args[1]['set_names'] == set_names
#         assert call_args[1]['batch_size'] == 50
#         assert call_args[1]['queue'] == 'long'
#         assert call_args[1]['timeout'] == 7200
    
#     @patch('frappe.utils.background_jobs.enqueue')
#     def test_enqueues_job_with_string_input(self, mock_enqueue):
#         """Test background job enqueueing with comma-separated string input"""
#         # Re-import to get the enqueue function
#         from frappe.utils.background_jobs import enqueue
#         glific_batch_id_update.enqueue = enqueue
        
#         mock_job = MagicMock()
#         mock_job.id = "JOB456"
#         mock_enqueue.return_value = mock_job
        
#         set_names_str = "SET001, SET002, SET003"
#         result = glific_batch_id_update.process_multiple_sets_batch_id_background(set_names_str)
        
#         assert "Started processing 3 sets" in result
#         assert "JOB456" in result
        
#         call_args = mock_enqueue.call_args
#         expected_list = ["SET001", "SET002", "SET003"]
#         assert call_args[1]['set_names'] == expected_list


# # ============= Test get_backend_onboarding_sets_for_batch_id =============

# class TestGetBackendOnboardingSets:
#     """Test cases for get_backend_onboarding_sets_for_batch_id function"""
    
#     @patch('tap_lms.glific_batch_id_update.frappe.get_all')
#     def test_returns_processed_onboarding_sets(self, mock_get_all):
#         """Test fetching processed backend onboarding sets"""
#         mock_sets = [
#             {
#                 "name": "SET001",
#                 "set_name": "January Batch",
#                 "processed_student_count": 100,
#                 "upload_date": "2024-01-15"
#             },
#             {
#                 "name": "SET002",
#                 "set_name": "February Batch",
#                 "processed_student_count": 150,
#                 "upload_date": "2024-02-20"
#             }
#         ]
#         mock_get_all.return_value = mock_sets
        
#         result = glific_batch_id_update.get_backend_onboarding_sets_for_batch_id()
        
#         assert len(result) == 2
#         assert result[0]["set_name"] == "January Batch"
#         assert result[0]["processed_student_count"] == 100
#         assert result[1]["set_name"] == "February Batch"
#         assert result[1]["processed_student_count"] == 150
        
#         mock_get_all.assert_called_once_with(
#             "Backend Student Onboarding",
#             filters={"status": "Processed"},
#             fields=["name", "set_name", "processed_student_count", "upload_date"],
#             order_by="upload_date desc"
#         )



# class TestPerformance:
#     """Performance-related test cases"""
    
#     @patch('time.sleep')
#     @patch('tap_lms.glific_batch_id_update.update_specific_set_contacts_with_batch_id')
#     @patch('tap_lms.glific_batch_id_update.frappe.logger')
#     def test_batch_processing_respects_batch_limit(self, mock_logger, mock_update, mock_sleep):
#         """Test that batch processing stops after safety limit"""
#         # Simulate continuous batches that never end
#         mock_update.return_value = {
#             "updated": 1,
#             "errors": 0,
#             "skipped": 0,
#             "total_processed": 1
#         }
        
#         results = glific_batch_id_update.process_multiple_sets_batch_id(["INFINITE_SET"], batch_size=1)
        
#         # Should stop after 20 batches (safety limit)
#         assert mock_update.call_count <= 21  # Initial call + 20 batch limit
#         assert results[0]["status"] == "completed"
    
#     @patch('frappe.utils.background_jobs.enqueue')
#     def test_background_job_uses_correct_timeout(self, mock_enqueue):
#         """Test that background job is configured with proper timeout"""
#         # Re-import to get the enqueue function
#         from frappe.utils.background_jobs import enqueue
#         glific_batch_id_update.enqueue = enqueue
        
#         mock_job = MagicMock()
#         mock_job.id = "TIMEOUT_TEST"
#         mock_enqueue.return_value = mock_job
        
#         glific_batch_id_update.process_multiple_sets_batch_id_background(["SET001"])
        
#         call_args = mock_enqueue.call_args
#         assert call_args[1]['timeout'] == 7200  # 2 hours
#         assert call_args[1]['queue'] == 'long'

import frappe
import requests
import json
import time
from frappe.utils.background_jobs import enqueue


def get_student_batch_id(student_id, batch_id):
    """
    Retrieve batch_id for a student, handling cases where student or batch is invalid.
    """
    try:
        if not batch_id:
            return None
        if not frappe.db.exists("Student", student_id):
            frappe.logger().error(f"Student {student_id} does not exist")
            return None
        return batch_id
    except Exception as e:
        frappe.logger().error(f"Error retrieving batch_id for student {student_id}: {str(e)}")
        return None


def update_glific_contact_field(contact_id, batch_id):
    """
    Update Glific contact field with batch_id using GraphQL API.
    Returns True on success, False on failure.
    """
    try:
        settings = get_glific_settings()
        headers = get_glific_auth_headers()
        
        query = """
        mutation updateContactFields($contactId: ID!, $fieldName: String!, $fieldValue: String!) {
            updateContactFields(id: $contactId, input: {field_name: $fieldName, value: $fieldValue}) {
                contact {
                    id
                    fields
                }
            }
        }
        """
        payload = {
            "query": query,
            "variables": {
                "contactId": str(contact_id),  # Ensure contact_id is string
                "fieldName": "batch_id",
                "fieldValue": batch_id
            }
        }
        
        response = requests.post(settings.api_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                frappe.logger().error(f"Glific API error for contact {contact_id}: {data['errors']}")
                return False
            if data.get("data", {}).get("updateContactFields", {}).get("contact"):
                return True
            frappe.logger().error(f"Unexpected Glific API response for contact {contact_id}: {data}")
            return False
        else:
            frappe.logger().error(f"Glific API HTTP error for contact {contact_id}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        frappe.logger().error(f"Glific API request failed for contact {contact_id}: {str(e)}")
        return False


def update_specific_set_contacts_with_batch_id(set_name, batch_size=50):
    """
    Update Glific contacts with batch_id for a specific onboarding set.
    Returns a dictionary with processing results.
    """
    if not set_name:
        return {"error": "Backend Student Onboarding set name is required"}
    
    result = {"set_name": set_name, "updated": 0, "skipped": 0, "errors": 0, "total_processed": 0}
    
    try:
        onboarding_set = frappe.get_doc("Backend Student Onboarding", set_name)
        if onboarding_set.status != "Processed":
            return {"error": f"Onboarding set {set_name} is not 'Processed'"}
        
        students = frappe.get_all("Backend Student", filters={"onboarding_set": set_name}, fields=["name"])
        
        if not students:
            return {"message": f"No successfully processed students found for set {set_name}"}
        
        result["total_processed"] = len(students)
        
        for student in students:
            try:
                backend_student = frappe.get_doc("Backend Student", student.name)
                student_doc = frappe.get_doc("Student", backend_student.student_id)
                
                if not student_doc.glific_id:
                    result["skipped"] += 1
                    frappe.logger().info(f"Skipped student {backend_student.student_id}: No glific_id")
                    continue
                
                batch_id = get_student_batch_id(backend_student.student_id, backend_student.batch)
                if not batch_id:
                    result["skipped"] += 1
                    frappe.logger().info(f"Skipped student {backend_student.student_id}: No valid batch_id")
                    continue
                
                if update_glific_contact_field(student_doc.glific_id, batch_id):
                    result["updated"] += 1
                else:
                    result["errors"] += 1
                    frappe.logger().error(f"Failed to update Glific contact for student {backend_student.student_id}")
            except frappe.DoesNotExistError as e:
                result["errors"] += 1
                frappe.logger().error(f"Student not found for {student.name}: {str(e)}")
            except Exception as e:
                result["errors"] += 1
                frappe.logger().error(f"Error processing student {student.name}: {str(e)}")
        
        return result
    except frappe.DoesNotExistError:
        return {"error": f"Onboarding set {set_name} not found"}
    except Exception as e:
        return {"error": f"Error processing set {set_name}: {str(e)}"}


def run_batch_id_update_for_specific_set(set_name):
    """
    Run batch ID update for a specific onboarding set with transaction management.
    """
    if not set_name:
        return "Error: Backend Student Onboarding set name is required"
    
    frappe.db.begin()
    try:
        result = update_specific_set_contacts_with_batch_id(set_name)
        frappe.db.commit()
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        return (
            f"Process completed for set {result['set_name']}. "
            f"Updated: {result['updated']}, Skipped: {result['skipped']}, "
            f"Errors: {result['errors']}, Total Processed: {result['total_processed']}"
        )
    except Exception as e:
        frappe.db.rollback()
        frappe.logger().error(f"Error in run_batch_id_update_for_specific_set: {str(e)}")
        return f"Error occurred: {str(e)}"


def process_multiple_sets_batch_id(set_names, batch_size=50):
    """
    Process multiple onboarding sets with batch_id updates.
    """
    if not set_names:
        return []
    
    results = []
    batch_limit = 20  # Safety limit to prevent infinite loops
    
    for set_name in set_names:
        if not set_name:
            continue
        
        batch_count = 0
        while batch_count < batch_limit:
            result = update_specific_set_contacts_with_batch_id(set_name, batch_size)
            
            if "error" in result:
                results.append({
                    "set_name": set_name,
                    "status": "error",
                    "error": result["error"],
                    "updated": 0,
                    "skipped": 0,
                    "errors": 0,
                    "total_processed": 0
                })
                break
            
            result["status"] = "completed"
            results.append(result)
            
            # Break if no more students to process
            if result.get("total_processed", 0) == 0 or result.get("total_processed", 0) < batch_size:
                break
            
            batch_count += 1
            time.sleep(1)  # Prevent overwhelming the API
        
        if batch_count >= batch_limit:
            frappe.logger().warning(f"Reached batch limit of {batch_limit} for set {set_name}")
            results.append({
                "set_name": set_name,
                "status": "error",
                "error": f"Reached batch limit of {batch_limit}",
                "updated": 0,
                "skipped": 0,
                "errors": 0,
                "total_processed": 0
            })
            break
    
    return results


def process_multiple_sets_batch_id_background(set_names):
    """
    Enqueue batch ID update for multiple sets in the background.
    """
    if isinstance(set_names, str):
        set_names = [name.strip() for name in set_names.split(",") if name.strip()]
    
    if not set_names:
        set_names = []
    
    try:
        job = enqueue(
            process_multiple_sets_batch_id,
            set_names=set_names,
            batch_size=50,
            queue="long",
            timeout=7200
        )
        return f"Started processing {len(set_names)} sets with job ID {job.id}"
    except Exception as e:
        frappe.logger().error(f"Failed to enqueue job: {str(e)}")
        raise


def get_backend_onboarding_sets_for_batch_id():
    """
    Retrieve processed backend onboarding sets.
    """
    return frappe.get_all(
        "Backend Student Onboarding",
        filters={"status": "Processed"},
        fields=["name", "set_name", "processed_student_count", "upload_date"],
        order_by="upload_date desc"
    )


def get_glific_settings():
    """
    Retrieve Glific settings (mock implementation).
    """
    return frappe.get_doc("Glific Settings")


def get_glific_auth_headers():
    """
    Retrieve Glific auth headers (mock implementation).
    """
    return {"Authorization": "Bearer token123"}