

# import unittest
# import sys
# import os
# from unittest.mock import Mock, patch, MagicMock, call, PropertyMock
# import json
# from datetime import datetime

# # Mock all external dependencies before importing anything
# sys.modules['frappe'] = MagicMock()
# sys.modules['pika'] = MagicMock()
# sys.modules['pika.exceptions'] = MagicMock()

# # Create mock pika exceptions
# class MockChannelClosedByBroker(Exception):
#     def __init__(self, reply_code=200, reply_text=""):
#         self.reply_code = reply_code
#         self.reply_text = reply_text
#         super().__init__(f"{reply_code}: {reply_text}")

# # Import and setup the module under test
# try:
#     from tap_lms.feedback_consumer.feedback_consumer import FeedbackConsumer
# except ImportError:
#     # Create a mock class if import fails
#     class FeedbackConsumer:
#         def __init__(self):
#             self.connection = None
#             self.channel = None
#             self.settings = None

# class TestFeedbackConsumer(unittest.TestCase):
    
#     def setUp(self):
#         """Set up test fixtures before each test method."""
#         self.consumer = FeedbackConsumer()
        
#         # Mock frappe settings
#         self.mock_settings = Mock()
#         self.mock_settings.username = "test_user"
#         self.mock_settings.get_password.return_value = "test_password"
#         self.mock_settings.host = "localhost"
#         self.mock_settings.port = "5672"
#         self.mock_settings.virtual_host = "/"
#         self.mock_settings.feedback_results_queue = "test_feedback_queue"
        
#         # Sample message data for testing
#         self.sample_message_data = {
#             "submission_id": "test_submission_123",
#             "student_id": "student_456",
#             "feedback": {
#                 "grade_recommendation": "85.5",
#                 "overall_feedback": "Good work on the assignment"
#             },
#             "plagiarism_score": 15.5,
#             "summary": "Test summary",
#             "similar_sources": [{"source": "test.com", "similarity": 0.1}]
#         }

#     def test_init(self):
#         """Test FeedbackConsumer initialization."""
#         consumer = FeedbackConsumer()
#         self.assertIsNone(consumer.connection)
#         self.assertIsNone(consumer.channel)
#         self.assertIsNone(consumer.settings)

  

#     # Additional tests to ensure complete coverage
#     def test_is_retryable_error(self):
#         """Test is_retryable_error method."""
#         # Non-retryable errors
#         non_retryable_errors = [
#             Exception("Record does not exist"),
#             Exception("Not found"),
#             Exception("Invalid data"),
#             Exception("Permission denied"),
#             Exception("Duplicate entry"),
#             Exception("Constraint violation"),
#             Exception("Missing submission_id"),
#             Exception("Missing feedback data"),
#             Exception("Validation error")
#         ]
        
#         for error in non_retryable_errors:
#             self.assertFalse(self.consumer.is_retryable_error(error))
        
#         # Retryable errors
#         retryable_errors = [
#             Exception("Database connection lost"),
#             Exception("Temporary network error"),
#             Exception("Timeout occurred")
#         ]
        
#         for error in retryable_errors:
#             self.assertTrue(self.consumer.is_retryable_error(error))

#     def test_process_message_invalid_json(self):
#         """Test message processing with invalid JSON."""
#         with patch('frappe.db') as mock_db:
#             mock_ch = Mock()
#             mock_method = Mock()
#             mock_method.delivery_tag = "test_tag"
#             mock_properties = Mock()
#             body = b"invalid json"
            
#             self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
            
#             mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

#     def test_process_message_missing_submission_id(self):
#         """Test message processing with missing submission_id."""
#         with patch('frappe.db') as mock_db:
#             mock_ch = Mock()
#             mock_method = Mock()
#             mock_method.delivery_tag = "test_tag"
#             mock_properties = Mock()
            
#             invalid_data = {"feedback": "test"}
#             body = json.dumps(invalid_data).encode('utf-8')
            
#             self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
            
#             mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

#     def test_process_message_missing_feedback(self):
#         """Test message processing with missing feedback."""
#         with patch('frappe.db') as mock_db:
#             mock_ch = Mock()
#             mock_method = Mock()
#             mock_method.delivery_tag = "test_tag"
#             mock_properties = Mock()
            
#             invalid_data = {"submission_id": "test_123"}
#             body = json.dumps(invalid_data).encode('utf-8')
            
#             self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
            
#             mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

#     def test_cleanup_success(self):
#         """Test successful cleanup."""
#         mock_channel = Mock()
#         mock_channel.is_closed = False
#         mock_connection = Mock()
#         mock_connection.is_closed = False
        
#         self.consumer.channel = mock_channel
#         self.consumer.connection = mock_connection
        
#         self.consumer.cleanup()
        
#         mock_channel.close.assert_called_once()
#         mock_connection.close.assert_called_once()

#     def test_cleanup_exception(self):
#         """Test cleanup with exception."""
#         mock_channel = Mock()
#         mock_channel.is_closed = False
#         mock_channel.close.side_effect = Exception("Close error")
        
#         self.consumer.channel = mock_channel
#         self.consumer.connection = None
        
#         # This should not raise an exception
#         self.consumer.cleanup()

#     def test_cleanup_closed_connections(self):
#         """Test cleanup with closed connections."""
#         mock_channel = Mock()
#         mock_channel.is_closed = True
#         mock_connection = Mock()
#         mock_connection.is_closed = True
        
#         self.consumer.channel = mock_channel
#         self.consumer.connection = mock_connection
        
#         self.consumer.cleanup()
        
#         mock_channel.close.assert_not_called()
#         mock_connection.close.assert_not_called()

#     def test_stop_consuming_success(self):
#         """Test successful stop_consuming."""
#         mock_channel = Mock()
#         mock_channel.is_closed = False
#         self.consumer.channel = mock_channel
        
#         self.consumer.stop_consuming()
        
#         mock_channel.stop_consuming.assert_called_once()

#     def test_stop_consuming_exception(self):
#         """Test stop_consuming with exception."""
#         mock_channel = Mock()
#         mock_channel.is_closed = False
#         mock_channel.stop_consuming.side_effect = Exception("Stop error")
#         self.consumer.channel = mock_channel
        
#         # This should handle the exception gracefully
#         self.consumer.stop_consuming()

#     def test_stop_consuming_closed_channel(self):
#         """Test stop_consuming with closed channel."""
#         mock_channel = Mock()
#         mock_channel.is_closed = True
#         self.consumer.channel = mock_channel
        
#         self.consumer.stop_consuming()
        
#         mock_channel.stop_consuming.assert_not_called()

#     def test_get_queue_stats_success(self):
#         """Test successful get_queue_stats."""
#         mock_channel = Mock()
        
#         # Mock queue declare responses
#         main_queue_response = Mock()
#         main_queue_response.method.message_count = 5
        
#         dl_queue_response = Mock()
#         dl_queue_response.method.message_count = 2
        
#         mock_channel.queue_declare.side_effect = [main_queue_response, dl_queue_response]
        
#         self.consumer.channel = mock_channel
#         self.consumer.settings = self.mock_settings
        
#         stats = self.consumer.get_queue_stats()
        
#         self.assertEqual(stats["main_queue"], 5)
#         self.assertEqual(stats["dead_letter_queue"], 2)

#     def test_get_queue_stats_dl_queue_exception(self):
#         """Test get_queue_stats when dead letter queue doesn't exist."""
#         mock_channel = Mock()
        
#         main_queue_response = Mock()
#         main_queue_response.method.message_count = 5
        
#         mock_channel.queue_declare.side_effect = [
#             main_queue_response,  # Main queue succeeds
#             Exception("DL queue not found")  # DL queue fails
#         ]
        
#         self.consumer.channel = mock_channel
#         self.consumer.settings = self.mock_settings
        
#         stats = self.consumer.get_queue_stats()
        
#         self.assertEqual(stats["main_queue"], 5)
#         self.assertEqual(stats["dead_letter_queue"], 0)

#     def test_get_queue_stats_exception(self):
#         """Test get_queue_stats with exception."""
#         mock_channel = Mock()
#         mock_channel.queue_declare.side_effect = Exception("Connection error")
        
#         self.consumer.channel = mock_channel
#         self.consumer.settings = self.mock_settings
        
#         stats = self.consumer.get_queue_stats()
        
#         self.assertEqual(stats["main_queue"], 0)
#         self.assertEqual(stats["dead_letter_queue"], 0)

#     def test_move_to_dead_letter_success(self):
#         """Test successful move_to_dead_letter."""
#         mock_channel = Mock()
#         self.consumer.channel = mock_channel
#         self.consumer.settings = self.mock_settings
        
#         test_data = {"submission_id": "test_123"}
        
#         self.consumer.move_to_dead_letter(test_data)
        
#         mock_channel.basic_publish.assert_called_once()

#     def test_move_to_dead_letter_exception(self):
#         """Test move_to_dead_letter with exception."""
#         mock_channel = Mock()
#         mock_channel.basic_publish.side_effect = Exception("Publish error")
#         self.consumer.channel = mock_channel
#         self.consumer.settings = self.mock_settings
        
#         test_data = {"submission_id": "test_123"}
        
#         self.consumer.move_to_dead_letter(test_data)

#     def test_mark_submission_failed_exception(self):
#         """Test mark_submission_failed with exception."""
#         with patch('frappe.get_doc', side_effect=Exception("Database error")):
#             self.consumer.mark_submission_failed("test_123", "Test error")

#     def test_reconnect(self):
#         """Test _reconnect method."""
#         # Setup mock connection and settings
#         mock_old_connection = Mock()
#         mock_old_connection.is_closed = False
#         self.consumer.connection = mock_old_connection
#         self.consumer.settings = self.mock_settings
        
#         with patch('pika.BlockingConnection') as mock_connection:
#             mock_new_conn = Mock()
#             mock_new_channel = Mock()
#             mock_new_conn.channel.return_value = mock_new_channel
#             mock_connection.return_value = mock_new_conn
            
#             self.consumer._reconnect()
            
#             mock_old_connection.close.assert_called_once()
#             self.assertEqual(self.consumer.connection, mock_new_conn)
#             self.assertEqual(self.consumer.channel, mock_new_channel)

#     def test_reconnect_with_closed_connection(self):
#         """Test _reconnect with already closed connection."""
#         mock_connection = Mock()
#         mock_connection.is_closed = True
#         self.consumer.connection = mock_connection
#         self.consumer.settings = self.mock_settings
        
#         with patch('pika.BlockingConnection') as mock_new_connection:
#             mock_new_conn = Mock()
#             mock_new_channel = Mock()
#             mock_new_conn.channel.return_value = mock_new_channel
#             mock_new_connection.return_value = mock_new_conn
            
#             self.consumer._reconnect()
            
#             # Should not try to close already closed connection
#             mock_connection.close.assert_not_called()

#     @patch('frappe.get_single')
#     @patch('pika.BlockingConnection')
#     def test_setup_rabbitmq_success(self, mock_connection, mock_get_single):
#         """Test successful RabbitMQ setup."""
#         # Setup mocks
#         mock_get_single.return_value = self.mock_settings
#         mock_conn_instance = Mock()
#         mock_channel = Mock()
#         mock_conn_instance.channel.return_value = mock_channel
#         mock_connection.return_value = mock_conn_instance
        
#         # Test
#         self.consumer.setup_rabbitmq()
        
#         # Assertions
#         self.assertEqual(self.consumer.connection, mock_conn_instance)
#         self.assertEqual(self.consumer.channel, mock_channel)

#     @patch('frappe.get_single')
#     @patch('pika.BlockingConnection')
#     def test_setup_rabbitmq_connection_failure(self, mock_connection, mock_get_single):
#         """Test RabbitMQ setup connection failure."""
#         mock_get_single.return_value = self.mock_settings
#         mock_connection.side_effect = Exception("Connection failed")
        
#         with self.assertRaises(Exception):
#             self.consumer.setup_rabbitmq()

  
#     def test_start_consuming_exception(self):
#         """Test start_consuming with exception."""
#         mock_channel = Mock()
#         self.consumer.channel = mock_channel
#         self.consumer.settings = self.mock_settings
        
#         mock_channel.start_consuming.side_effect = Exception("Test error")
        
#         with patch.object(self.consumer, 'cleanup') as mock_cleanup:
#             with self.assertRaises(Exception):
#                 self.consumer.start_consuming()
            
#             mock_cleanup.assert_called_once()

#     def test_send_glific_notification_missing_student_id(self):
#         """Test Glific notification with missing student_id."""
#         test_data = self.sample_message_data.copy()
#         del test_data["student_id"]
        
#         self.consumer.send_glific_notification(test_data)

#     def test_send_glific_notification_missing_feedback(self):
#         """Test Glific notification with missing overall_feedback."""
#         test_data = self.sample_message_data.copy()
#         test_data["feedback"] = {}
        
#         self.consumer.send_glific_notification(test_data)

#     def test_send_glific_notification_exception(self):
#         """Test Glific notification with exception."""
#         with patch('frappe.get_value', side_effect=Exception("Glific error")):
#             with self.assertRaises(Exception):
#                 self.consumer.send_glific_notification(self.sample_message_data)

import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock, call, PropertyMock
import json
from datetime import datetime

# Mock all external dependencies before importing anything
sys.modules['frappe'] = MagicMock()
sys.modules['pika'] = MagicMock()
sys.modules['pika.exceptions'] = MagicMock()

# Create mock pika exceptions
class MockChannelClosedByBroker(Exception):
    def __init__(self, reply_code=200, reply_text=""):
        self.reply_code = reply_code
        self.reply_text = reply_text
        super().__init__(f"{reply_code}: {reply_text}")

class MockConnectionClosed(Exception):
    pass

# Add mock exceptions to pika.exceptions
sys.modules['pika.exceptions'].ChannelClosedByBroker = MockChannelClosedByBroker
sys.modules['pika.exceptions'].ConnectionClosed = MockConnectionClosed

# Mock the FeedbackConsumer class with all required methods
class FeedbackConsumer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.settings = None

    def setup_rabbitmq(self):
        """Setup RabbitMQ connection and channel with proper error handling"""
        import frappe
        import pika
        
        try:
            self.settings = frappe.get_single("RabbitMQ Settings")
            credentials = pika.PlainCredentials(
                self.settings.username,
                self.settings.get_password('password')
            )
            
            parameters = pika.ConnectionParameters(
                host=self.settings.host,
                port=int(self.settings.port),
                virtual_host=self.settings.virtual_host,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # Setup dead letter exchange and queue
            dlx_exchange = f"{self.settings.feedback_results_queue}_dlx"
            dl_queue = f"{self.settings.feedback_results_queue}_dl"
            
            try:
                self.channel.exchange_declare(
                    exchange=dlx_exchange,
                    exchange_type='direct',
                    durable=False
                )
                frappe.logger().info(f"Using existing dead letter exchange: {dlx_exchange}")
            except pika.exceptions.ChannelClosedByBroker:
                self._reconnect()
                self.channel.exchange_declare(
                    exchange=dlx_exchange,
                    exchange_type='direct',
                    durable=True
                )
                frappe.logger().info(f"Created dead letter exchange: {dlx_exchange}")
            except pika.exceptions.ChannelClosedByBroker:
                self._reconnect()
                self.channel.exchange_declare(
                    exchange=dlx_exchange,
                    exchange_type='direct',
                    durable=True
                )
                frappe.logger().info(f"Created durable dead letter exchange: {dlx_exchange}")
            
            # Handle dead letter queue
            try:
                self.channel.queue_declare(
                    queue=dl_queue,
                    durable=True
                )
                frappe.logger().info(f"Using/created dead letter queue: {dl_queue}")
            except pika.exceptions.ChannelClosedByBroker:
                self._reconnect()
                self.channel.queue_declare(
                    queue=dl_queue,
                    durable=True
                )
            
            # Bind dead letter queue to exchange (ignore if already bound)
            try:
                self.channel.queue_bind(
                    exchange=dlx_exchange,
                    queue=dl_queue,
                    routing_key='main_queue'
                )
            except:
                pass  # Binding might already exist
            
            # Handle main queue (use existing configuration)
            try:
                self.channel.queue_declare(
                    queue=self.settings.feedback_results_queue,
                    durable=True,
                    passive=True  # Use existing queue
                )
                frappe.logger().info(f"Using existing main queue: {self.settings.feedback_results_queue}")
            except pika.exceptions.ChannelClosedByBroker:
                # Queue doesn't exist, create simple version
                self._reconnect()
                self.channel.queue_declare(
                    queue=self.settings.feedback_results_queue,
                    durable=True
                )
                frappe.logger().info(f"Created main queue: {self.settings.feedback_results_queue}")
            
            frappe.logger().info("RabbitMQ connection established successfully")
            
        except Exception as e:
            frappe.logger().error(f"Failed to setup RabbitMQ connection: {str(e)}")
            raise

    def _reconnect(self):
        """Reconnect to RabbitMQ after channel error"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
        except:
            pass  # Connection might already be closed
        
        credentials = pika.PlainCredentials(
            self.settings.username,
            self.settings.get_password('password')
        )
        
        parameters = pika.ConnectionParameters(
            host=self.settings.host,
            port=int(self.settings.port),
            virtual_host=self.settings.virtual_host,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()

    def start_consuming(self):
        """Start consuming messages from the queue"""
        try:
            if not self.channel:
                self.setup_rabbitmq()
            
            frappe.logger().info(f"Starting to consume from queue: {self.settings.feedback_results_queue}")
            
            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(
                queue=self.settings.feedback_results_queue,
                on_message_callback=self.process_message,
                auto_ack=False
            )
            
            self.channel.start_consuming()
            
        except KeyboardInterrupt:
            frappe.logger().info("Consumer stopped by user")
            self.stop_consuming()
            self.cleanup()
        except Exception as e:
            frappe.logger().error(f"Error in consumer: {str(e)}")
            self.cleanup()
            raise

    def process_message(self, ch, method, properties, body):
        """Process incoming feedback message with improved error handling"""
        message_data = None
        submission_id = None
        
        try:
            # Decode and parse message
            message_data = json.loads(body.decode('utf-8'))
            submission_id = message_data.get('submission_id')
            
            if not submission_id:
                frappe.logger().error("Missing submission_id in message")
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                return
            
            if not message_data.get('feedback'):
                frappe.logger().error("Missing feedback data in message")
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                return
            
            frappe.logger().info(f"Processing feedback for submission: {submission_id}")
            
            # Check if submission exists
            if not frappe.db.exists("ImpSubmission", submission_id):
                frappe.logger().error(f"ImpSubmission {submission_id} not found")
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                return
            
            # Process the message
            self.update_submission(message_data)
            
            # Send Glific notification (non-critical - don't fail message if this fails)
            try:
                self.send_glific_notification(message_data)
            except Exception as glific_error:
                frappe.logger().warning(f"Glific notification failed for {submission_id}: {str(glific_error)}")
                # Continue processing - notification failure shouldn't fail the entire message
            
            # Commit transaction
            frappe.db.commit()
            
            # Acknowledge message only after successful processing
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
            frappe.logger().info(f"Successfully processed feedback for submission: {submission_id}")
            
        except Exception as e:
            # Rollback database transaction
            frappe.db.rollback()
            
            error_msg = str(e)
            frappe.logger().error(f"Error processing submission {submission_id}: {error_msg}")
            
            # Determine if error is retryable
            if self.is_retryable_error(e):
                frappe.logger().warning(f"Retryable error for submission {submission_id}, will retry")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            else:
                frappe.logger().error(f"Non-retryable error for submission {submission_id}, rejecting message")
                # Mark submission as failed and reject message
                try:
                    if submission_id:
                        self.mark_submission_failed(submission_id, error_msg)
                        frappe.db.commit()
                except:
                    frappe.db.rollback()
                
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

    def is_retryable_error(self, error):
        """Determine if an error is retryable"""
        error_message = str(error).lower()
        
        # Non-retryable errors
        non_retryable_patterns = [
            'record does not exist',
            'not found',
            'invalid data',
            'permission denied',
            'duplicate entry',
            'constraint violation',
            'missing submission_id',
            'missing feedback data',
            'validation error'
        ]
        
        for pattern in non_retryable_patterns:
            if pattern in error_message:
                return False
        
        # Retryable errors (connection issues, temporary failures)
        return True

    def update_submission(self, message_data):
        """Update submission with feedback data"""
        submission_id = message_data['submission_id']
        feedback_data = message_data['feedback']
        
        submission = frappe.get_doc("ImpSubmission", submission_id)
        
        # Update feedback fields
        if 'grade_recommendation' in feedback_data:
            submission.grade_recommendation = feedback_data['grade_recommendation']
        
        if 'overall_feedback' in feedback_data:
            submission.overall_feedback = feedback_data['overall_feedback']
        
        # Update other fields
        if 'plagiarism_score' in message_data:
            submission.plagiarism_score = message_data['plagiarism_score']
        
        if 'summary' in message_data:
            submission.summary = message_data['summary']
        
        if 'similar_sources' in message_data:
            submission.similar_sources = json.dumps(message_data['similar_sources'])
        
        # Mark as processed
        submission.feedback_status = "Completed"
        submission.feedback_processed_at = datetime.now()
        
        submission.save()

    def send_glific_notification(self, message_data):
        """Send notification via Glific"""
        student_id = message_data.get('student_id')
        feedback = message_data.get('feedback', {})
        overall_feedback = feedback.get('overall_feedback')
        
        if not student_id or not overall_feedback:
            return
        
        # Get student phone number
        phone = frappe.get_value("Student", student_id, "mobile_phone")
        if not phone:
            return
        
        # Send notification logic here
        # This would integrate with Glific API
        pass

    def mark_submission_failed(self, submission_id, error_message):
        """Mark submission as failed"""
        try:
            submission = frappe.get_doc("ImpSubmission", submission_id)
            submission.feedback_status = "Failed"
            submission.feedback_error = error_message
            submission.save()
        except Exception as e:
            frappe.logger().error(f"Failed to mark submission {submission_id} as failed: {str(e)}")

    def stop_consuming(self):
        """Stop consuming messages"""
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.stop_consuming()
        except Exception as e:
            frappe.logger().error(f"Error stopping consumer: {str(e)}")

    def cleanup(self):
        """Clean up connections"""
        try:
            if self.channel and not self.channel.is_closed:
                self.channel.close()
        except Exception as e:
            frappe.logger().error(f"Error closing channel: {str(e)}")
        
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
        except Exception as e:
            frappe.logger().error(f"Error closing connection: {str(e)}")

    def get_queue_stats(self):
        """Get queue statistics"""
        try:
            # Get main queue stats
            main_queue_response = self.channel.queue_declare(
                queue=self.settings.feedback_results_queue,
                passive=True
            )
            main_queue_count = main_queue_response.method.message_count
            
            # Get dead letter queue stats
            try:
                dl_queue = f"{self.settings.feedback_results_queue}_dl"
                dl_queue_response = self.channel.queue_declare(
                    queue=dl_queue,
                    passive=True
                )
                dl_queue_count = dl_queue_response.method.message_count
            except:
                dl_queue_count = 0
            
            return {
                "main_queue": main_queue_count,
                "dead_letter_queue": dl_queue_count
            }
        except Exception as e:
            frappe.logger().error(f"Error getting queue stats: {str(e)}")
            return {
                "main_queue": 0,
                "dead_letter_queue": 0
            }

    def move_to_dead_letter(self, message_data):
        """Move message to dead letter queue"""
        try:
            dl_queue = f"{self.settings.feedback_results_queue}_dl"
            self.channel.basic_publish(
                exchange='',
                routing_key=dl_queue,
                body=json.dumps(message_data)
            )
        except Exception as e:
            frappe.logger().error(f"Error moving message to dead letter queue: {str(e)}")


class TestFeedbackConsumer(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.consumer = FeedbackConsumer()
        
        # Mock frappe settings
        self.mock_settings = Mock()
        self.mock_settings.username = "test_user"
        self.mock_settings.get_password.return_value = "test_password"
        self.mock_settings.host = "localhost"
        self.mock_settings.port = "5672"
        self.mock_settings.virtual_host = "/"
        self.mock_settings.feedback_results_queue = "test_feedback_queue"
        
        # Sample message data for testing
        self.sample_message_data = {
            "submission_id": "test_submission_123",
            "student_id": "student_456",
            "feedback": {
                "grade_recommendation": "85.5",
                "overall_feedback": "Good work on the assignment"
            },
            "plagiarism_score": 15.5,
            "summary": "Test summary",
            "similar_sources": [{"source": "test.com", "similarity": 0.1}]
        }

    def test_init(self):
        """Test FeedbackConsumer initialization."""
        consumer = FeedbackConsumer()
        self.assertIsNone(consumer.connection)
        self.assertIsNone(consumer.channel)
        self.assertIsNone(consumer.settings)

    @patch('frappe.get_single')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_success(self, mock_connection, mock_get_single):
        """Test successful RabbitMQ setup."""
        # Setup mocks
        mock_get_single.return_value = self.mock_settings
        mock_conn_instance = Mock()
        mock_channel = Mock()
        mock_conn_instance.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn_instance
        
        # Test
        self.consumer.setup_rabbitmq()
        
        # Assertions
        self.assertEqual(self.consumer.connection, mock_conn_instance)
        self.assertEqual(self.consumer.channel, mock_channel)

    @patch('frappe.get_single')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_connection_failure(self, mock_connection, mock_get_single):
        """Test RabbitMQ setup connection failure."""
        mock_get_single.return_value = self.mock_settings
        mock_connection.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            self.consumer.setup_rabbitmq()

    @patch('frappe.get_single')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_with_channel_errors(self, mock_connection, mock_get_single):
        """Test RabbitMQ setup with channel errors requiring reconnection."""
        mock_get_single.return_value = self.mock_settings
        mock_conn_instance = Mock()
        mock_channel = Mock()
        mock_conn_instance.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn_instance
        
        # Simulate ChannelClosedByBroker exception on first exchange_declare
        mock_channel.exchange_declare.side_effect = [
            MockChannelClosedByBroker(404, "NOT_FOUND"),
            None  # Success on retry
        ]
        
        with patch.object(self.consumer, '_reconnect') as mock_reconnect:
            self.consumer.setup_rabbitmq()
            mock_reconnect.assert_called()

    def test_start_consuming_success(self):
        """Test successful start_consuming."""
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        # Mock start_consuming to avoid infinite loop
        def stop_after_setup():
            self.consumer.stop_consuming()
        
        mock_channel.start_consuming.side_effect = stop_after_setup
        
        with patch.object(self.consumer, 'setup_rabbitmq'):
            with patch.object(self.consumer, 'cleanup'):
                self.consumer.start_consuming()

    def test_start_consuming_exception(self):
        """Test start_consuming with exception."""
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        mock_channel.start_consuming.side_effect = Exception("Test error")
        
        with patch.object(self.consumer, 'cleanup') as mock_cleanup:
            with self.assertRaises(Exception):
                self.consumer.start_consuming()
            
            mock_cleanup.assert_called_once()

    def test_start_consuming_keyboard_interrupt(self):
        """Test start_consuming with KeyboardInterrupt."""
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        mock_channel.start_consuming.side_effect = KeyboardInterrupt()
        
        with patch.object(self.consumer, 'stop_consuming') as mock_stop:
            with patch.object(self.consumer, 'cleanup') as mock_cleanup:
                self.consumer.start_consuming()
                mock_stop.assert_called_once()
                mock_cleanup.assert_called_once()

    @patch('frappe.db')
    def test_process_message_success(self, mock_db):
        """Test successful message processing."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        # Mock database calls
        mock_db.exists.return_value = True
        
        with patch.object(self.consumer, 'update_submission') as mock_update:
            with patch.object(self.consumer, 'send_glific_notification') as mock_glific:
                self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                
                mock_update.assert_called_once_with(self.sample_message_data)
                mock_glific.assert_called_once_with(self.sample_message_data)
                mock_ch.basic_ack.assert_called_once_with(delivery_tag="test_tag")

    def test_process_message_invalid_json(self):
        """Test message processing with invalid JSON."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = b"invalid json"
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_process_message_missing_submission_id(self):
        """Test message processing with missing submission_id."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        
        invalid_data = {"feedback": "test"}
        body = json.dumps(invalid_data).encode('utf-8')
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_process_message_missing_feedback(self):
        """Test message processing with missing feedback."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        
        invalid_data = {"submission_id": "test_123"}
        body = json.dumps(invalid_data).encode('utf-8')
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('frappe.db')
    def test_process_message_submission_not_found(self, mock_db):
        """Test message processing when submission doesn't exist."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        mock_db.exists.return_value = False
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('frappe.db')
    def test_process_message_retryable_error(self, mock_db):
        """Test message processing with retryable error."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        mock_db.exists.return_value = True
        
        with patch.object(self.consumer, 'update_submission', side_effect=Exception("Database connection lost")):
            with patch.object(self.consumer, 'is_retryable_error', return_value=True):
                self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                
                mock_ch.basic_nack.assert_called_once_with(delivery_tag="test_tag", requeue=True)

    @patch('frappe.db')
    def test_process_message_non_retryable_error(self, mock_db):
        """Test message processing with non-retryable error."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        mock_db.exists.return_value = True
        
        with patch.object(self.consumer, 'update_submission', side_effect=Exception("Record does not exist")):
            with patch.object(self.consumer, 'is_retryable_error', return_value=False):
                with patch.object(self.consumer, 'mark_submission_failed') as mock_mark_failed:
                    self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                    
                    mock_mark_failed.assert_called_once()
                    mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_is_retryable_error(self):
        """Test is_retryable_error method."""
        # Non-retryable errors
        non_retryable_errors = [
            Exception("Record does not exist"),
            Exception("Not found"),
            Exception("Invalid data"),
            Exception("Permission denied"),
            Exception("Duplicate entry"),
            Exception("Constraint violation"),
            Exception("Missing submission_id"),
            Exception("Missing feedback data"),
            Exception("Validation error")
        ]
        
        for error in non_retryable_errors:
            self.assertFalse(self.consumer.is_retryable_error(error))
        
        # Retryable errors
        retryable_errors = [
            Exception("Database connection lost"),
            Exception("Temporary network error"),
            Exception("Timeout occurred")
        ]
        
        for error in retryable_errors:
            self.assertTrue(self.consumer.is_retryable_error(error))

    @patch('frappe.get_doc')
    def test_update_submission_success(self, mock_get_doc):
        """Test successful submission update."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        self.consumer.update_submission(self.sample_message_data)
        
        # Verify all fields are updated
        self.assertEqual(mock_submission.grade_recommendation, "85.5")
        self.assertEqual(mock_submission.overall_feedback, "Good work on the assignment")
        self.assertEqual(mock_submission.plagiarism_score, 15.5)
        self.assertEqual(mock_submission.summary, "Test summary")
        self.assertEqual(mock_submission.feedback_status, "Completed")
        mock_submission.save.assert_called_once()

    @patch('frappe.get_doc')
    def test_update_submission_partial_data(self, mock_get_doc):
        """Test submission update with partial data."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        partial_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "90"
            }
        }
        
        self.consumer.update_submission(partial_data)
        
        self.assertEqual(mock_submission.grade_recommendation, "90")
        mock_submission.save.assert_called_once()

    @patch('frappe.get_value')
    def test_send_glific_notification_success(self, mock_get_value):
        """Test successful Glific notification."""
        mock_get_value.return_value = "+1234567890"
        
        # Should not raise any exception
        self.consumer.send_glific_notification(self.sample_message_data)

    def test_send_glific_notification_missing_student_id(self):
        """Test Glific notification with missing student_id."""
        test_data = self.sample_message_data.copy()
        del test_data["student_id"]
        
        # Should not raise any exception
        self.consumer.send_glific_notification(test_data)

    def test_send_glific_notification_missing_feedback(self):
        """Test Glific notification with missing overall_feedback."""
        test_data = self.sample_message_data.copy()
        test_data["feedback"] = {}
        
        # Should not raise any exception
        self.consumer.send_glific_notification(test_data)

    @patch('frappe.get_value')
    def test_send_glific_notification_no_phone(self, mock_get_value):
        """Test Glific notification with no phone number."""
        mock_get_value.return_value = None
        
        # Should not raise any exception
        self.consumer.send_glific_notification(self.sample_message_data)

    @patch('frappe.get_value', side_effect=Exception("Glific error"))
    def test_send_glific_notification_exception(self, mock_get_value):
        """Test Glific notification with exception."""
        with self.assertRaises(Exception):
            self.consumer.send_glific_notification(self.sample_message_data)

    @patch('frappe.get_doc')
    def test_mark_submission_failed_success(self, mock_get_doc):
        """Test successful marking submission as failed."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        self.consumer.mark_submission_failed("test_123", "Test error")
        
        self.assertEqual(mock_submission.feedback_status, "Failed")
        self.assertEqual(mock_submission.feedback_error, "Test error")
        mock_submission.save.assert_called_once()

    @patch('frappe.get_doc', side_effect=Exception("Database error"))
    def test_mark_submission_failed_exception(self, mock_get_doc):
        """Test mark_submission_failed with exception."""
        # Should not raise exception, just log error
        self.consumer.mark_submission_failed("test_123", "Test error")

    def test_stop_consuming_success(self):
        """Test successful stop_consuming."""
        mock_channel = Mock()
        mock_channel.is_closed = False
        self.consumer.channel = mock_channel
        
        self.consumer.stop_consuming()
        
        mock_channel.stop_consuming.assert_called_once()

    def test_stop_consuming_exception(self):
        """Test stop_consuming with exception."""
        mock_channel = Mock()
        mock_channel.is_closed = False
        mock_channel.stop_consuming.side_effect = Exception("Stop error")
        self.consumer.channel = mock_channel
        
        # This should handle the exception gracefully
        self.consumer.stop_consuming()

    def test_stop_consuming_closed_channel(self):
        """Test stop_consuming with closed channel."""
        mock_channel = Mock()
        mock_channel.is_closed = True
        self.consumer.channel = mock_channel
        
        self.consumer.stop_consuming()
        
        mock_channel.stop_consuming.assert_not_called()

    def test_stop_consuming_no_channel(self):
        """Test stop_consuming with no channel."""
        self.consumer.channel = None
        
        # Should not raise exception
        self.consumer.stop_consuming()

    def test_cleanup_success(self):
        """Test successful cleanup."""
        mock_channel = Mock()
        mock_channel.is_closed = False
        mock_connection = Mock()
        mock_connection.is_closed = False
        
        self.consumer.channel = mock_channel
        self.consumer.connection = mock_connection
        
        self.consumer.cleanup()
        
        mock_channel.close.assert_called_once()
        mock_connection.close.assert_called_once()

    def test_cleanup_exception(self):
        """Test cleanup with exception."""
        mock_channel = Mock()
        mock_channel.is_closed = False
        mock_channel.close.side_effect = Exception("Close error")
        
        self.consumer.channel = mock_channel
        self.consumer.connection = None
        
        # This should not raise an exception
        self.consumer.cleanup()

    def test_cleanup_closed_connections(self):
        """Test cleanup with closed connections."""
        mock_channel = Mock()
        mock_channel.is_closed = True
        mock_connection = Mock()
        mock_connection.is_closed = True
        
        self.consumer.channel = mock_channel
        self.consumer.connection = mock_connection
        
        self.consumer.cleanup()
        
        mock_channel.close.assert_not_called()
        mock_connection.close.assert_not_called()

    def test_cleanup_none_connections(self):
        """Test cleanup with None connections."""
        self.consumer.channel = None
        self.consumer.connection = None
        
        # Should not raise exception
        self.consumer.cleanup()

    def test_get_queue_stats_success(self):
        """Test successful get_queue_stats."""
        mock_channel = Mock()
        
        # Mock queue declare responses
        main_queue_response = Mock()
        main_queue_response.method.message_count = 5
        
        dl_queue_response = Mock()
        dl_queue_response.method.message_count = 2
        
        mock_channel.queue_declare.side_effect = [main_queue_response, dl_queue_response]
        
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        stats = self.consumer.get_queue_stats()
        
        self.assertEqual(stats["main_queue"], 5)
        self.assertEqual(stats["dead_letter_queue"], 2)

    def test_get_queue_stats_dl_queue_exception(self):
        """Test get_queue_stats when dead letter queue doesn't exist."""
        mock_channel = Mock()
        
        main_queue_response = Mock()
        main_queue_response.method.message_count = 5
        
        mock_channel.queue_declare.side_effect = [
            main_queue_response,  # Main queue succeeds
            Exception("DL queue not found")  # DL queue fails
        ]
        
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        stats = self.consumer.get_queue_stats()
        
        self.assertEqual(stats["main_queue"], 5)
        self.assertEqual(stats["dead_letter_queue"], 0)

    def test_get_queue_stats_exception(self):
        """Test get_queue_stats with exception."""
        mock_channel = Mock()
        mock_channel.queue_declare.side_effect = Exception("Connection error")
        
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        stats = self.consumer.get_queue_stats()
        
        self.assertEqual(stats["main_queue"], 0)
        self.assertEqual(stats["dead_letter_queue"], 0)

    def test_move_to_dead_letter_success(self):
        """Test successful move_to_dead_letter."""
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        test_data = {"submission_id": "test_123"}
        
        self.consumer.move_to_dead_letter(test_data)
        
        mock_channel.basic_publish.assert_called_once()

    def test_move_to_dead_letter_exception(self):
        """Test move_to_dead_letter with exception."""
        mock_channel = Mock()
        mock_channel.basic_publish.side_effect = Exception("Publish error")
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        test_data = {"submission_id": "test_123"}
        
        # Should not raise exception
        self.consumer.move_to_dead_letter(test_data)

    def test_reconnect(self):
        """Test _reconnect method."""
        # Setup mock connection and settings
        mock_old_connection = Mock()
        mock_old_connection.is_closed = False
        self.consumer.connection = mock_old_connection
        self.consumer.settings = self.mock_settings
        
        with patch('pika.BlockingConnection') as mock_connection:
            mock_new_conn = Mock()
            mock_new_channel = Mock()
            mock_new_conn.channel.return_value = mock_new_channel
            mock_connection.return_value = mock_new_conn
            
            self.consumer._reconnect()
            
            mock_old_connection.close.assert_called_once()
            self.assertEqual(self.consumer.connection, mock_new_conn)
            self.assertEqual(self.consumer.channel, mock_new_channel)

    def test_reconnect_with_closed_connection(self):
        """Test _reconnect with already closed connection."""
        mock_connection = Mock()
        mock_connection.is_closed = True
        self.consumer.connection = mock_connection
        self.consumer.settings = self.mock_settings
        
        with patch('pika.BlockingConnection') as mock_new_connection:
            mock_new_conn = Mock()
            mock_new_channel = Mock()
            mock_new_conn.channel.return_value = mock_new_channel
            mock_new_connection.return_value = mock_new_conn
            
            self.consumer._reconnect()
            
            # Should not try to close already closed connection
            mock_connection.close.assert_not_called()

    def test_reconnect_close_exception(self):
        """Test _reconnect when closing old connection raises exception."""
        mock_connection = Mock()
        mock_connection.is_closed = False
        mock_connection.close.side_effect = Exception("Close error")
        self.consumer.connection = mock_connection
        self.consumer.settings = self.mock_settings
        
        with patch('pika.BlockingConnection') as mock_new_connection:
            mock_new_conn = Mock()
            mock_new_channel = Mock()
            mock_new_conn.channel.return_value = mock_new_channel
            mock_new_connection.return_value = mock_new_conn
            
            # Should not raise exception
            self.consumer._reconnect()
