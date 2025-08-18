# import json
# import frappe
# import pika

# def submit_artwork(api_key, assign_id, student_id, img_url):
#     # Authenticate the API request using the provided api_key
#     api_key_doc = frappe.db.get_value("API Key", {"key": api_key, "enabled": 1}, ["user"], as_dict=True)
#     if not api_key_doc:
#         frappe.throw("Invalid API key")

#     # Switch to the user associated with the API key
#     frappe.set_user(api_key_doc.user)

#     try:
#         # Create a new submission
#         submission = frappe.new_doc("ImgSubmission")
#         submission.assign_id = assign_id
#         submission.student_id = student_id
#         submission.img_url = img_url
#         submission.status = "Pending"
#         submission.insert()
#         frappe.db.commit()

#         # Log for debugging
#         frappe.logger("submission").debug(f"Inserted submission: assign_id={submission.assign_id}, student_id={submission.student_id}, img_url={submission.img_url}")

#         # Send the submission details to RabbitMQ
#         enqueue_submission(submission.name)

#         return {"message": "Submission received", "submission_id": submission.name}

#     finally:
#         # Switch back to the original user
#         frappe.set_user("Administrator")

# def enqueue_submission(submission_id):
#     submission = frappe.get_doc("ImgSubmission", submission_id)
#     payload = {
#         "submission_id": submission.name,
#         "assign_id": submission.assign_id,
#         "student_id": submission.student_id,
#         "img_url": submission.img_url
#     }

#     rabbitmq_config = {
#         'host': 'armadillo.rmq.cloudamqp.com',
#         'port': 5672,
#         'virtual_host': 'fzdqidte',
#         'username': 'fzdqidte',
#         'password': '0SMrDogBVcWUcu9brWwp2QhET_kArl59',
#         'queue': 'submission_queue'
#     }

#     # Establish a connection to RabbitMQ
#     credentials = pika.PlainCredentials(rabbitmq_config['username'], rabbitmq_config['password'])
#     parameters = pika.ConnectionParameters(
#         rabbitmq_config['host'],
#         rabbitmq_config['port'],
#         rabbitmq_config['virtual_host'],
#         credentials
#     )
#     connection = pika.BlockingConnection(parameters)
#     channel = connection.channel()

#     # Declare the queue
#     channel.queue_declare(queue=rabbitmq_config['queue'])

#     # Publish the message to the queue
#     channel.basic_publish(
#         exchange='',
#         routing_key=rabbitmq_config['queue'],
#         body=json.dumps(payload)
#     )

#     # Close the connection
#     connection.close()

# def img_feedback(api_key, submission_id):
#     # Authenticate the API request using the provided api_key
#     api_key_doc = frappe.db.get_value("API Key", {"key": api_key, "enabled": 1}, ["user"], as_dict=True)
#     if not api_key_doc:
#         frappe.throw("Invalid API key")

#     # Switch to the user associated with the API key
#     frappe.set_user(api_key_doc.user)

#     try:
#         # Get the submission document
#         submission = frappe.get_doc("ImgSubmission", submission_id)
        
#         # Prepare the response based on status
#         if submission.status == "Completed":
#             response = {
#                 "status": submission.status,
#                 "overall_feedback": submission.overall_feedback
#             }
#         else:
#             response = {
#                 "status": submission.status
#             }
        
#         return response

#     except frappe.DoesNotExistError:
#         return {"error": "Submission not found"}
    
#     except Exception as e:
#         frappe.log_error(f"Error checking submission status: {str(e)}", "Submission Status Error")
#         return {"error": "An error occurred while checking submission status"}

#     finally:
#         # Switch back to the original user
#         frappe.set_user("Administrator")

# def get_assignment_context(assignment_id, student_id=None):
#     """Get complete assignment context for RAG service"""
#     try:
#         assignment = frappe.get_doc("Assignment", assignment_id)
        
#         context = {
#             "assignment": {
#                 "name": assignment.assignment_name,
#                 "description": assignment.description,
#                 "type": assignment.assignment_type,
#                 "subject": assignment.subject,
#                 "submission_guidelines": assignment.submission_guidelines,
#                 "reference_image": assignment.reference_image,
#                 "max_score": assignment.max_score
#             },
#             "learning_objectives": [
#                 {
#                     "objective": obj.learning_objective,
#                     "description": frappe.db.get_value(
#                         "Learning Objective",
#                         obj.learning_objective,
#                         "description"
#                     )
#                 }
#                 for obj in assignment.learning_objectives
#             ]
#         }
        
#         # Add student context if provided
#         if student_id:
#             student = frappe.get_doc("Student", student_id)
#             context["student"] = {
#                 "grade": student.grade,
#                 "level": student.level,
#                 "language": student.language
#             }
        
#         # Add custom feedback prompt if enabled
#         if assignment.enable_auto_feedback and assignment.feedback_prompt:
#             context["feedback_prompt"] = assignment.feedback_prompt
            
#         return context
        
#     except Exception as e:
#         frappe.log_error(
#             f"Error getting assignment context: {str(e)}",
#             "RAG Context Error"
#         )
#         return None


import json
import unittest
from unittest.mock import Mock, patch, MagicMock
import frappe
from frappe.exceptions import DoesNotExistError

# Import your actual functions here
# from your_module import submit_artwork, enqueue_submission, img_feedback, get_assignment_context

class TestSubmission(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Reset all mocks
        frappe.reset_mock() if hasattr(frappe, 'reset_mock') else None
        
    @patch('your_module.pika')  # Replace 'your_module' with actual module name
    @patch('your_module.frappe')
    def test_submit_artwork_valid_api_key(self, mock_frappe, mock_pika):
        """Test submit_artwork with valid API key - covers lines 7-30"""
        # Setup mocks
        mock_frappe.db.get_value.return_value = {"user": "test_user"}
        
        mock_submission = Mock()
        mock_submission.name = "SUB-001"
        mock_submission.assign_id = "ASSIGN-001"
        mock_submission.student_id = "STU-001"
        mock_submission.img_url = "http://example.com/image.jpg"
        mock_submission.status = "Pending"
        
        mock_frappe.new_doc.return_value = mock_submission
        mock_frappe.get_doc.return_value = mock_submission
        
        # Mock RabbitMQ components
        mock_connection = Mock()
        mock_channel = Mock()
        mock_connection.channel.return_value = mock_channel
        mock_pika.BlockingConnection.return_value = mock_connection
        
        # Test the function
        from your_module import submit_artwork  # Replace with actual import
        result = submit_artwork("valid_key", "ASSIGN-001", "STU-001", "http://example.com/image.jpg")
        
        # Assertions
        self.assertEqual(result["message"], "Submission received")
        self.assertEqual(result["submission_id"], "SUB-001")
        mock_frappe.db.get_value.assert_called_once()
        mock_frappe.set_user.assert_called()
        mock_submission.insert.assert_called_once()
        mock_frappe.db.commit.assert_called_once()

    @patch('your_module.frappe')
    def test_submit_artwork_invalid_api_key(self, mock_frappe):
        """Test submit_artwork with invalid API key - covers lines 8-9"""
        # Setup mocks
        mock_frappe.db.get_value.return_value = None
        mock_frappe.throw.side_effect = Exception("Invalid API key")
        
        # Test the function
        from your_module import submit_artwork
        with self.assertRaises(Exception) as context:
            submit_artwork("invalid_key", "ASSIGN-001", "STU-001", "http://example.com/image.jpg")
        
        self.assertEqual(str(context.exception), "Invalid API key")

    @patch('your_module.pika')
    @patch('your_module.frappe')
    def test_enqueue_submission(self, mock_frappe, mock_pika):
        """Test enqueue_submission function - covers lines 36-76"""
        # Setup mocks
        mock_submission = Mock()
        mock_submission.name = "SUB-001"
        mock_submission.assign_id = "ASSIGN-001"
        mock_submission.student_id = "STU-001"
        mock_submission.img_url = "http://example.com/image.jpg"
        
        mock_frappe.get_doc.return_value = mock_submission
        
        # Mock RabbitMQ components
        mock_credentials = Mock()
        mock_parameters = Mock()
        mock_connection = Mock()
        mock_channel = Mock()
        
        mock_pika.PlainCredentials.return_value = mock_credentials
        mock_pika.ConnectionParameters.return_value = mock_parameters
        mock_pika.BlockingConnection.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel
        
        # Test the function
        from your_module import enqueue_submission
        enqueue_submission("SUB-001")
        
        # Assertions
        mock_frappe.get_doc.assert_called_with("ImgSubmission", "SUB-001")
        mock_pika.PlainCredentials.assert_called_once()
        mock_pika.ConnectionParameters.assert_called_once()
        mock_pika.BlockingConnection.assert_called_once()
        mock_channel.queue_declare.assert_called_once()
        mock_channel.basic_publish.assert_called_once()
        mock_connection.close.assert_called_once()

    @patch('your_module.frappe')
    def test_img_feedback_completed_status(self, mock_frappe):
        """Test img_feedback with completed submission - covers lines 80-102"""
        # Setup mocks
        mock_frappe.db.get_value.return_value = {"user": "test_user"}
        
        mock_submission = Mock()
        mock_submission.status = "Completed"
        mock_submission.overall_feedback = "Great work!"
        
        mock_frappe.get_doc.return_value = mock_submission
        
        # Test the function
        from your_module import img_feedback
        result = img_feedback("valid_key", "SUB-001")
        
        # Assertions
        self.assertEqual(result["status"], "Completed")
        self.assertEqual(result["overall_feedback"], "Great work!")
        mock_frappe.set_user.assert_called()

    @patch('your_module.frappe')
    def test_img_feedback_pending_status(self, mock_frappe):
        """Test img_feedback with pending submission - covers lines 97-100"""
        # Setup mocks
        mock_frappe.db.get_value.return_value = {"user": "test_user"}
        
        mock_submission = Mock()
        mock_submission.status = "Pending"
        
        mock_frappe.get_doc.return_value = mock_submission
        
        # Test the function
        from your_module import img_feedback
        result = img_feedback("valid_key", "SUB-001")
        
        # Assertions
        self.assertEqual(result["status"], "Pending")
        self.assertNotIn("overall_feedback", result)

    @patch('your_module.frappe')
    def test_img_feedback_submission_not_found(self, mock_frappe):
        """Test img_feedback with non-existent submission - covers lines 104-105"""
        # Setup mocks
        mock_frappe.db.get_value.return_value = {"user": "test_user"}
        mock_frappe.get_doc.side_effect = DoesNotExistError("Submission not found")
        mock_frappe.DoesNotExistError = DoesNotExistError
        
        # Test the function
        from your_module import img_feedback
        result = img_feedback("valid_key", "NONEXISTENT")
        
        # Assertions
        self.assertEqual(result["error"], "Submission not found")

    @patch('your_module.frappe')
    def test_img_feedback_general_exception(self, mock_frappe):
        """Test img_feedback with general exception - covers lines 107-109"""
        # Setup mocks
        mock_frappe.db.get_value.return_value = {"user": "test_user"}
        mock_frappe.get_doc.side_effect = Exception("Database error")
        mock_frappe.DoesNotExistError = DoesNotExistError
        
        # Test the function
        from your_module import img_feedback
        result = img_feedback("valid_key", "SUB-001")
        
        # Assertions
        self.assertEqual(result["error"], "An error occurred while checking submission status")
        mock_frappe.log_error.assert_called_once()

    @patch('your_module.frappe')
    def test_get_assignment_context_basic(self, mock_frappe):
        """Test get_assignment_context without student - covers lines 117-142"""
        # Setup mocks
        mock_assignment = Mock()
        mock_assignment.assignment_name = "Math Test"
        mock_assignment.description = "Basic math assignment"
        mock_assignment.assignment_type = "Quiz"
        mock_assignment.subject = "Mathematics"
        mock_assignment.submission_guidelines = "Submit your answers"
        mock_assignment.reference_image = "ref.jpg"
        mock_assignment.max_score = 100
        mock_assignment.enable_auto_feedback = False
        
        mock_objective = Mock()
        mock_objective.learning_objective = "LO-001"
        mock_assignment.learning_objectives = [mock_objective]
        
        mock_frappe.get_doc.return_value = mock_assignment
        mock_frappe.db.get_value.return_value = "Understand basic math"
        
        # Test the function
        from your_module import get_assignment_context
        result = get_assignment_context("ASSIGN-001")
        
        # Assertions
        self.assertEqual(result["assignment"]["name"], "Math Test")
        self.assertEqual(result["assignment"]["description"], "Basic math assignment")
        self.assertEqual(len(result["learning_objectives"]), 1)
        self.assertNotIn("student", result)

    @patch('your_module.frappe')
    def test_get_assignment_context_with_student(self, mock_frappe):
        """Test get_assignment_context with student - covers lines 144-150"""
        # Setup mocks
        mock_assignment = Mock()
        mock_assignment.assignment_name = "Math Test"
        mock_assignment.description = "Basic math assignment"
        mock_assignment.assignment_type = "Quiz"
        mock_assignment.subject = "Mathematics"
        mock_assignment.submission_guidelines = "Submit your answers"
        mock_assignment.reference_image = "ref.jpg"
        mock_assignment.max_score = 100
        mock_assignment.enable_auto_feedback = False
        mock_assignment.learning_objectives = []
        
        mock_student = Mock()
        mock_student.grade = "10"
        mock_student.level = "Intermediate"
        mock_student.language = "English"
        
        def mock_get_doc(doctype, doc_id):
            if doctype == "Assignment":
                return mock_assignment
            elif doctype == "Student":
                return mock_student
        
        mock_frappe.get_doc.side_effect = mock_get_doc
        
        # Test the function
        from your_module import get_assignment_context
        result = get_assignment_context("ASSIGN-001", "STU-001")
        
        # Assertions
        self.assertEqual(result["assignment"]["name"], "Math Test")
        self.assertEqual(result["student"]["grade"], "10")
        self.assertEqual(result["student"]["level"], "Intermediate")
        self.assertEqual(result["student"]["language"], "English")

    @patch('your_module.frappe')
    def test_get_assignment_context_with_feedback_prompt(self, mock_frappe):
        """Test get_assignment_context with feedback prompt - covers lines 153-154"""
        # Setup mocks
        mock_assignment = Mock()
        mock_assignment.assignment_name = "Math Test"
        mock_assignment.description = "Basic math assignment"
        mock_assignment.assignment_type = "Quiz"
        mock_assignment.subject = "Mathematics"
        mock_assignment.submission_guidelines = "Submit your answers"
        mock_assignment.reference_image = "ref.jpg"
        mock_assignment.max_score = 100
        mock_assignment.enable_auto_feedback = True
        mock_assignment.feedback_prompt = "Provide detailed feedback"
        mock_assignment.learning_objectives = []
        
        mock_frappe.get_doc.return_value = mock_assignment
        
        # Test the function
        from your_module import get_assignment_context
        result = get_assignment_context("ASSIGN-001")
        
        # Assertions
        self.assertEqual(result["assignment"]["name"], "Math Test")
        self.assertEqual(result["feedback_prompt"], "Provide detailed feedback")

    @patch('your_module.frappe')
    def test_get_assignment_context_exception(self, mock_frappe):
        """Test get_assignment_context with exception - covers lines 158-163"""
        # Setup mocks
        mock_frappe.get_doc.side_effect = Exception("Database error")
        
        # Test the function
        from your_module import get_assignment_context
        result = get_assignment_context("INVALID-ASSIGN")
        
        # Assertions
        self.assertIsNone(result)
        mock_frappe.log_error.assert_called_once()

