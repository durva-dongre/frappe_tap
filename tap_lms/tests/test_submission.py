import unittest
import frappe
import json
from unittest.mock import patch, MagicMock, call
import pika
from your_module import submit_artwork, img_feedback, get_assignment_context, enqueue_submission

class TestArtworkSubmissionAPI(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.valid_api_key = "test_api_key_123"
        self.invalid_api_key = "invalid_key"
        self.assign_id = "ASSIGN-001"
        self.student_id = "STU-001"
        self.img_url = "https://example.com/image.jpg"
        self.submission_id = "SUB-001"
        
    def tearDown(self):
        """Clean up after each test method."""
        frappe.db.rollback()

class TestSubmitArtwork(TestArtworkSubmissionAPI):
    
    @patch('frappe.db.get_value')
    @patch('frappe.set_user')
    @patch('frappe.new_doc')
    @patch('frappe.db.commit')
    @patch('your_module.enqueue_submission')
    def test_submit_artwork_success(self, mock_enqueue, mock_commit, mock_new_doc, mock_set_user, mock_get_value):
        """Test successful artwork submission"""
        # Mock API key validation
        mock_get_value.return_value = {"user": "test_user@example.com"}
        
        # Mock submission document
        mock_submission = MagicMock()
        mock_submission.name = "SUB-001"
        mock_submission.assign_id = self.assign_id
        mock_submission.student_id = self.student_id
        mock_submission.img_url = self.img_url
        mock_new_doc.return_value = mock_submission
        
        # Call the function
        result = submit_artwork(self.valid_api_key, self.assign_id, self.student_id, self.img_url)
        
        # Assertions
        mock_get_value.assert_called_once_with("API Key", {"key": self.valid_api_key, "enabled": 1}, ["user"], as_dict=True)
        mock_set_user.assert_any_call("test_user@example.com")
        mock_set_user.assert_any_call("Administrator")
        mock_new_doc.assert_called_once_with("ImgSubmission")
        
        # Verify submission fields are set
        self.assertEqual(mock_submission.assign_id, self.assign_id)
        self.assertEqual(mock_submission.student_id, self.student_id)
        self.assertEqual(mock_submission.img_url, self.img_url)
        self.assertEqual(mock_submission.status, "Pending")
        
        mock_submission.insert.assert_called_once()
        mock_commit.assert_called_once()
        mock_enqueue.assert_called_once_with("SUB-001")
        
        # Check return value
        expected_result = {"message": "Submission received", "submission_id": "SUB-001"}
        self.assertEqual(result, expected_result)
    
    @patch('frappe.db.get_value')
    @patch('frappe.throw')
    def test_submit_artwork_invalid_api_key(self, mock_throw, mock_get_value):
        """Test submission with invalid API key"""
        # Mock API key validation failure
        mock_get_value.return_value = None
        
        # Call the function
        submit_artwork(self.invalid_api_key, self.assign_id, self.student_id, self.img_url)
        
        # Assertions
        mock_get_value.assert_called_once_with("API Key", {"key": self.invalid_api_key, "enabled": 1}, ["user"], as_dict=True)
        mock_throw.assert_called_once_with("Invalid API key")
    
    @patch('frappe.db.get_value')
    @patch('frappe.set_user')
    @patch('frappe.new_doc')
    def test_submit_artwork_database_error(self, mock_new_doc, mock_set_user, mock_get_value):
        """Test submission with database error"""
        # Mock API key validation
        mock_get_value.return_value = {"user": "test_user@example.com"}
        
        # Mock submission document that raises an error on insert
        mock_submission = MagicMock()
        mock_submission.insert.side_effect = Exception("Database error")
        mock_new_doc.return_value = mock_submission
        
        # Call the function and expect an exception
        with self.assertRaises(Exception):
            submit_artwork(self.valid_api_key, self.assign_id, self.student_id, self.img_url)
        
        # Verify user is reset to Administrator even on error
        mock_set_user.assert_any_call("Administrator")

class TestEnqueueSubmission(TestArtworkSubmissionAPI):
    
    @patch('frappe.get_doc')
    @patch('pika.BlockingConnection')
    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    def test_enqueue_submission_success(self, mock_params, mock_credentials, mock_connection, mock_get_doc):
        """Test successful RabbitMQ message enqueuing"""
        # Mock submission document
        mock_submission = MagicMock()
        mock_submission.name = "SUB-001"
        mock_submission.assign_id = self.assign_id
        mock_submission.student_id = self.student_id
        mock_submission.img_url = self.img_url
        mock_get_doc.return_value = mock_submission
        
        # Mock RabbitMQ connection
        mock_channel = MagicMock()
        mock_conn_instance = MagicMock()
        mock_conn_instance.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn_instance
        
        # Call the function
        enqueue_submission("SUB-001")
        
        # Assertions
        mock_get_doc.assert_called_once_with("ImgSubmission", "SUB-001")
        mock_credentials.assert_called_once_with('fzdqidte', '0SMrDogBVcWUcu9brWwp2QhET_kArl59')
        mock_channel.queue_declare.assert_called_once_with(queue='submission_queue')
        
        # Verify message payload
        expected_payload = {
            "submission_id": "SUB-001",
            "assign_id": self.assign_id,
            "student_id": self.student_id,
            "img_url": self.img_url
        }
        mock_channel.basic_publish.assert_called_once_with(
            exchange='',
            routing_key='submission_queue',
            body=json.dumps(expected_payload)
        )
        mock_conn_instance.close.assert_called_once()
    
    @patch('frappe.get_doc')
    @patch('pika.BlockingConnection')
    def test_enqueue_submission_connection_error(self, mock_connection, mock_get_doc):
        """Test RabbitMQ connection error handling"""
        # Mock submission document
        mock_submission = MagicMock()
        mock_get_doc.return_value = mock_submission
        
        # Mock connection error
        mock_connection.side_effect = pika.exceptions.AMQPConnectionError("Connection failed")
        
        # Call the function and expect an exception
        with self.assertRaises(pika.exceptions.AMQPConnectionError):
            enqueue_submission("SUB-001")

class TestImgFeedback(TestArtworkSubmissionAPI):
    
    @patch('frappe.db.get_value')
    @patch('frappe.set_user')
    @patch('frappe.get_doc')
    def test_img_feedback_completed_status(self, mock_get_doc, mock_set_user, mock_get_value):
        """Test feedback retrieval for completed submission"""
        # Mock API key validation
        mock_get_value.return_value = {"user": "test_user@example.com"}
        
        # Mock completed submission
        mock_submission = MagicMock()
        mock_submission.status = "Completed"
        mock_submission.overall_feedback = "Great work! Your artwork shows excellent use of color."
        mock_get_doc.return_value = mock_submission
        
        # Call the function
        result = img_feedback(self.valid_api_key, self.submission_id)
        
        # Assertions
        mock_get_value.assert_called_once_with("API Key", {"key": self.valid_api_key, "enabled": 1}, ["user"], as_dict=True)
        mock_set_user.assert_any_call("test_user@example.com")
        mock_set_user.assert_any_call("Administrator")
        mock_get_doc.assert_called_once_with("ImgSubmission", self.submission_id)
        
        expected_result = {
            "status": "Completed",
            "overall_feedback": "Great work! Your artwork shows excellent use of color."
        }
        self.assertEqual(result, expected_result)
    
    @patch('frappe.db.get_value')
    @patch('frappe.set_user')
    @patch('frappe.get_doc')
    def test_img_feedback_pending_status(self, mock_get_doc, mock_set_user, mock_get_value):
        """Test feedback retrieval for pending submission"""
        # Mock API key validation
        mock_get_value.return_value = {"user": "test_user@example.com"}
        
        # Mock pending submission
        mock_submission = MagicMock()
        mock_submission.status = "Pending"
        mock_get_doc.return_value = mock_submission
        
        # Call the function
        result = img_feedback(self.valid_api_key, self.submission_id)
        
        # Assertions
        expected_result = {"status": "Pending"}
        self.assertEqual(result, expected_result)
    
    @patch('frappe.db.get_value')
    @patch('frappe.throw')
    def test_img_feedback_invalid_api_key(self, mock_throw, mock_get_value):
        """Test feedback retrieval with invalid API key"""
        # Mock API key validation failure
        mock_get_value.return_value = None
        
        # Call the function
        img_feedback(self.invalid_api_key, self.submission_id)
        
        # Assertions
        mock_throw.assert_called_once_with("Invalid API key")
    
    @patch('frappe.db.get_value')
    @patch('frappe.set_user')
    @patch('frappe.get_doc')
    def test_img_feedback_submission_not_found(self, mock_get_doc, mock_set_user, mock_get_value):
        """Test feedback retrieval for non-existent submission"""
        # Mock API key validation
        mock_get_value.return_value = {"user": "test_user@example.com"}
        
        # Mock submission not found
        mock_get_doc.side_effect = frappe.DoesNotExistError("Submission not found")
        
        # Call the function
        result = img_feedback(self.valid_api_key, "INVALID-SUB")
        
        # Assertions
        expected_result = {"error": "Submission not found"}
        self.assertEqual(result, expected_result)
        mock_set_user.assert_any_call("Administrator")  # Ensure cleanup happens
    
    @patch('frappe.db.get_value')
    @patch('frappe.set_user')
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_img_feedback_unexpected_error(self, mock_log_error, mock_get_doc, mock_set_user, mock_get_value):
        """Test feedback retrieval with unexpected error"""
        # Mock API key validation
        mock_get_value.return_value = {"user": "test_user@example.com"}
        
        # Mock unexpected error
        mock_get_doc.side_effect = Exception("Unexpected database error")
        
        # Call the function
        result = img_feedback(self.valid_api_key, self.submission_id)
        
        # Assertions
        expected_result = {"error": "An error occurred while checking submission status"}
        self.assertEqual(result, expected_result)
        mock_log_error.assert_called_once()
        mock_set_user.assert_any_call("Administrator")

class TestGetAssignmentContext(TestArtworkSubmissionAPI):
    
    @patch('frappe.get_doc')
    @patch('frappe.db.get_value')
    def test_get_assignment_context_without_student(self, mock_get_value, mock_get_doc):
        """Test assignment context retrieval without student information"""
        # Mock assignment document
        mock_assignment = MagicMock()
        mock_assignment.assignment_name = "Art Project 1"
        mock_assignment.description = "Create a landscape painting"
        mock_assignment.assignment_type = "Creative"
        mock_assignment.subject = "Art"
        mock_assignment.submission_guidelines = "Submit as JPEG format"
        mock_assignment.reference_image = "ref_image.jpg"
        mock_assignment.max_score = 100
        mock_assignment.enable_auto_feedback = False
        mock_assignment.learning_objectives = [
            MagicMock(learning_objective="LO-001"),
            MagicMock(learning_objective="LO-002")
        ]
        mock_get_doc.return_value = mock_assignment
        
        # Mock learning objective descriptions
        mock_get_value.side_effect = [
            "Understand color theory",
            "Apply composition techniques"
        ]
        
        # Call the function
        result = get_assignment_context("ASSIGN-001")
        
        # Assertions
        mock_get_doc.assert_called_once_with("Assignment", "ASSIGN-001")
        
        expected_result = {
            "assignment": {
                "name": "Art Project 1",
                "description": "Create a landscape painting",
                "type": "Creative",
                "subject": "Art",
                "submission_guidelines": "Submit as JPEG format",
                "reference_image": "ref_image.jpg",
                "max_score": 100
            },
            "learning_objectives": [
                {
                    "objective": "LO-001",
                    "description": "Understand color theory"
                },
                {
                    "objective": "LO-002",
                    "description": "Apply composition techniques"
                }
            ]
        }
        self.assertEqual(result, expected_result)
    
    @patch('frappe.get_doc')
    @patch('frappe.db.get_value')
    def test_get_assignment_context_with_student(self, mock_get_value, mock_get_doc):
        """Test assignment context retrieval with student information"""
        # Mock assignment document
        mock_assignment = MagicMock()
        mock_assignment.assignment_name = "Art Project 1"
        mock_assignment.description = "Create a landscape painting"
        mock_assignment.assignment_type = "Creative"
        mock_assignment.subject = "Art"
        mock_assignment.submission_guidelines = "Submit as JPEG format"
        mock_assignment.reference_image = "ref_image.jpg"
        mock_assignment.max_score = 100
        mock_assignment.enable_auto_feedback = True
        mock_assignment.feedback_prompt = "Focus on color usage and composition"
        mock_assignment.learning_objectives = []
        
        # Mock student document
        mock_student = MagicMock()
        mock_student.grade = "Grade 5"
        mock_student.level = "Intermediate"
        mock_student.language = "English"
        
        mock_get_doc.side_effect = [mock_assignment, mock_student]
        
        # Call the function
        result = get_assignment_context("ASSIGN-001", "STU-001")
        
        # Assertions
        expected_calls = [
            call("Assignment", "ASSIGN-001"),
            call("Student", "STU-001")
        ]
        mock_get_doc.assert_has_calls(expected_calls)
        
        # Check that student context is included
        self.assertIn("student", result)
        self.assertEqual(result["student"]["grade"], "Grade 5")
        self.assertEqual(result["student"]["level"], "Intermediate")
        self.assertEqual(result["student"]["language"], "English")
        
        # Check that feedback prompt is included
        self.assertIn("feedback_prompt", result)
        self.assertEqual(result["feedback_prompt"], "Focus on color usage and composition")
    
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_get_assignment_context_assignment_not_found(self, mock_log_error, mock_get_doc):
        """Test assignment context retrieval for non-existent assignment"""
        # Mock assignment not found
        mock_get_doc.side_effect = frappe.DoesNotExistError("Assignment not found")
        
        # Call the function
        result = get_assignment_context("INVALID-ASSIGN")
        
        # Assertions
        self.assertIsNone(result)
        mock_log_error.assert_called_once()
    
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_get_assignment_context_unexpected_error(self, mock_log_error, mock_get_doc):
        """Test assignment context retrieval with unexpected error"""
        # Mock unexpected error
        mock_get_doc.side_effect = Exception("Database connection error")
        
        # Call the function
        result = get_assignment_context("ASSIGN-001")
        
        # Assertions
        self.assertIsNone(result)
        mock_log_error.assert_called_once_with(
            "Error getting assignment context: Database connection error",
            "RAG Context Error"
        )

class TestIntegrationScenarios(TestArtworkSubmissionAPI):
    """Integration test scenarios combining multiple functions"""
    
    @patch('frappe.db.get_value')
    @patch('frappe.set_user')
    @patch('frappe.new_doc')
    @patch('frappe.db.commit')
    @patch('your_module.enqueue_submission')
    @patch('frappe.get_doc')
    def test_complete_submission_workflow(self, mock_get_doc_feedback, mock_enqueue, 
                                        mock_commit, mock_new_doc, mock_set_user, mock_get_value):
        """Test complete workflow: submit artwork -> check feedback"""
        # Setup for submit_artwork
        mock_get_value.return_value = {"user": "test_user@example.com"}
        mock_submission = MagicMock()
        mock_submission.name = "SUB-001"
        mock_submission.assign_id = self.assign_id
        mock_submission.student_id = self.student_id
        mock_submission.img_url = self.img_url
        mock_new_doc.return_value = mock_submission
        
        # Submit artwork
        submit_result = submit_artwork(self.valid_api_key, self.assign_id, self.student_id, self.img_url)
        
        # Verify submission
        self.assertEqual(submit_result["submission_id"], "SUB-001")
        
        # Setup for img_feedback (completed submission)
        mock_submission_feedback = MagicMock()
        mock_submission_feedback.status = "Completed"
        mock_submission_feedback.overall_feedback = "Excellent work!"
        mock_get_doc_feedback.return_value = mock_submission_feedback
        
        # Check feedback
        feedback_result = img_feedback(self.valid_api_key, "SUB-001")
        
        # Verify feedback
        self.assertEqual(feedback_result["status"], "Completed")
        self.assertEqual(feedback_result["overall_feedback"], "Excellent work!")

if __name__ == '__main__':
    # Test configuration
    frappe.init(site='test_site')
    frappe.connect()
    
    # Run tests
    unittest.main(verbosity=2)