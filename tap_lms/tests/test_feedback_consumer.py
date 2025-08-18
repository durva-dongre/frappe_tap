# test_feedback_consumer.py - FINAL VERSION FOR 100% COVERAGE

import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock, call
import json
from datetime import datetime

# Add the app path to sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Mock frappe and dependencies before importing
sys.modules['frappe'] = MagicMock()
sys.modules['pika'] = MagicMock()

# Create mock pika exceptions
class MockChannelClosedByBroker(Exception):
    def __init__(self, reply_code=200, reply_text=""):
        self.reply_code = reply_code
        self.reply_text = reply_text
        super().__init__(f"{reply_code}: {reply_text}")

# Mock pika module properly
mock_pika = MagicMock()
mock_pika.exceptions = MagicMock()
mock_pika.exceptions.ChannelClosedByBroker = MockChannelClosedByBroker
mock_pika.PlainCredentials = MagicMock()
mock_pika.ConnectionParameters = MagicMock()
mock_pika.BlockingConnection = MagicMock()
mock_pika.BasicProperties = MagicMock()
sys.modules['pika'] = mock_pika
sys.modules['pika.exceptions'] = mock_pika.exceptions

# Import the module under test
from tap_lms.feedback_consumer.feedback_consumer import FeedbackConsumer


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
        
    def tearDown(self):
        """Clean up after each test."""
        if hasattr(self.consumer, 'connection') and self.consumer.connection:
            try:
                self.consumer.cleanup()
            except:
                pass

    def test_init(self):
        """Test FeedbackConsumer initialization."""
        consumer = FeedbackConsumer()
        self.assertIsNone(consumer.connection)
        self.assertIsNone(consumer.channel)
        self.assertIsNone(consumer.settings)

    @patch('frappe.get_single')
    @patch('pika.BlockingConnection')
    @patch('frappe.logger')
    def test_setup_rabbitmq_success(self, mock_logger, mock_connection, mock_get_single):
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
    @patch('frappe.logger')
    def test_setup_rabbitmq_connection_failure(self, mock_logger, mock_connection, mock_get_single):
        """Test RabbitMQ setup connection failure."""
        mock_get_single.return_value = self.mock_settings
        mock_connection.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            self.consumer.setup_rabbitmq()

    @patch('frappe.db')
    @patch('frappe.logger')
    @patch('frappe.db.exists')
    def test_process_message_success(self, mock_exists, mock_logger, mock_db):
        """Test successful message processing."""
        # Setup mocks
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        mock_exists.return_value = True
        
        with patch.object(self.consumer, 'update_submission') as mock_update, \
             patch.object(self.consumer, 'send_glific_notification') as mock_glific:
            
            self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
            
            mock_db.begin.assert_called_once()
            mock_update.assert_called_once_with(self.sample_message_data)
            mock_glific.assert_called_once_with(self.sample_message_data)
            mock_db.commit.assert_called_once()
            mock_ch.basic_ack.assert_called_once_with(delivery_tag="test_tag")

    @patch('frappe.db')
    @patch('frappe.logger')
    def test_cleanup_exception(self, mock_logger, mock_db):
        """Test cleanup with exception."""
        mock_channel = Mock()
        mock_channel.is_closed = False
        mock_channel.close.side_effect = Exception("Close error")
        
        self.consumer.channel = mock_channel
        self.consumer.connection = None
        
        # This should not raise an exception
        self.consumer.cleanup()

    @patch('frappe.db')
    @patch('frappe.logger')
    def test_cleanup_success(self, mock_logger, mock_db):
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

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_mark_submission_failed_success(self, mock_logger, mock_get_doc):
        """Test successful mark_submission_failed."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        self.consumer.mark_submission_failed("test_123", "Test error")
        
        self.assertEqual(mock_submission.status, "Failed")
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_mark_submission_failed_with_error_field(self, mock_logger, mock_get_doc):
        """Test mark_submission_failed with error_message field."""
        mock_submission = Mock()
        # Mock hasattr to return True for error_message
        mock_submission.error_message = ""
        mock_get_doc.return_value = mock_submission
        
        # Use a long error message to test truncation
        long_error = "a" * 600
        
        with patch('builtins.hasattr', return_value=True):
            self.consumer.mark_submission_failed("test_123", long_error)
        
        self.assertEqual(mock_submission.status, "Failed")
        # Should be truncated to 500 characters
        self.assertEqual(len(mock_submission.error_message), 500)

    @patch('frappe.get_value')
    @patch('frappe.logger')
    def test_send_glific_notification_success(self, mock_logger, mock_get_value):
        """Test successful Glific notification."""
        mock_get_value.return_value = "test_flow_id"
        
        # Mock the start_contact_flow import and function
        with patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow', return_value=True):
            self.consumer.send_glific_notification(self.sample_message_data)

    @patch('frappe.logger')
    def test_setup_rabbitmq_connection_failure_detailed(self, mock_logger):
        """Test detailed RabbitMQ setup connection failure."""
        with patch('frappe.get_single') as mock_get_single, \
             patch('pika.BlockingConnection') as mock_connection:
            
            mock_get_single.return_value = self.mock_settings
            mock_connection.side_effect = Exception("Connection failed")
            
            with self.assertRaises(Exception):
                self.consumer.setup_rabbitmq()

    @patch('frappe.logger')
    def test_stop_consuming_exception(self, mock_logger):
        """Test stop_consuming with exception."""
        mock_channel = Mock()
        mock_channel.is_closed = False
        mock_channel.stop_consuming.side_effect = Exception("Stop error")
        self.consumer.channel = mock_channel
        
        # This should handle the exception gracefully
        self.consumer.stop_consuming()

    @patch('frappe.logger')
    def test_stop_consuming_success(self, mock_logger):
        """Test successful stop_consuming."""
        mock_channel = Mock()
        mock_channel.is_closed = False
        self.consumer.channel = mock_channel
        
        self.consumer.stop_consuming()
        
        mock_channel.stop_consuming.assert_called_once()

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_update_submission_success(self, mock_logger, mock_get_doc):
        """Test successful submission update."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        self.consumer.update_submission(self.sample_message_data)
        
        mock_submission.update.assert_called_once()
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

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

    @patch('frappe.db')
    @patch('frappe.logger')
    def test_process_message_invalid_json(self, mock_logger, mock_db):
        """Test message processing with invalid JSON."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = b"invalid json"
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('frappe.db')
    @patch('frappe.logger')
    @patch('frappe.db.exists')
    def test_process_message_submission_not_found(self, mock_exists, mock_logger, mock_db):
        """Test message processing when submission doesn't exist."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        mock_exists.return_value = False
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('frappe.db')
    @patch('frappe.logger')
    @patch('frappe.db.exists')
    def test_process_message_retryable_error(self, mock_exists, mock_logger, mock_db):
        """Test message processing with retryable error."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        mock_exists.return_value = True
        
        with patch.object(self.consumer, 'update_submission') as mock_update, \
             patch.object(self.consumer, 'is_retryable_error', return_value=True):
            
            mock_update.side_effect = Exception("Database lock error")
            
            self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
            
            mock_db.rollback.assert_called_once()
            mock_ch.basic_nack.assert_called_once_with(delivery_tag="test_tag", requeue=True)

    @patch('frappe.db')
    @patch('frappe.logger')
    @patch('frappe.db.exists')
    def test_process_message_non_retryable_error(self, mock_logger, mock_exists, mock_db):
        """Test message processing with non-retryable error."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        mock_exists.return_value = True
        
        with patch.object(self.consumer, 'update_submission') as mock_update, \
             patch.object(self.consumer, 'is_retryable_error', return_value=False), \
             patch.object(self.consumer, 'mark_submission_failed') as mock_mark_failed:
            
            mock_update.side_effect = Exception("Validation error")
            
            self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
            
            mock_db.rollback.assert_called()
            mock_mark_failed.assert_called_once()
            mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('frappe.db')
    @patch('frappe.logger')
    @patch('frappe.db.exists')
    def test_process_message_glific_failure(self, mock_exists, mock_logger, mock_db):
        """Test message processing with Glific notification failure."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        mock_exists.return_value = True
        
        with patch.object(self.consumer, 'update_submission') as mock_update, \
             patch.object(self.consumer, 'send_glific_notification') as mock_glific:
            
            mock_glific.side_effect = Exception("Glific error")
            
            self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
            
            # Should still commit and ack despite Glific failure
            mock_db.commit.assert_called_once()
            mock_ch.basic_ack.assert_called_once_with(delivery_tag="test_tag")

    @patch('frappe.get_value')
    @patch('frappe.logger')
    def test_send_glific_notification_missing_student_id(self, mock_logger, mock_get_value):
        """Test Glific notification with missing student_id."""
        test_data = self.sample_message_data.copy()
        del test_data["student_id"]
        
        self.consumer.send_glific_notification(test_data)

    @patch('frappe.get_value')
    @patch('frappe.logger')
    def test_send_glific_notification_missing_feedback(self, mock_logger, mock_get_value):
        """Test Glific notification with missing overall_feedback."""
        test_data = self.sample_message_data.copy()
        test_data["feedback"] = {}
        
        self.consumer.send_glific_notification(test_data)

    @patch('frappe.get_value')
    @patch('frappe.logger')
    def test_send_glific_notification_no_flow_id(self, mock_logger, mock_get_value):
        """Test Glific notification with no flow ID configured."""
        mock_get_value.return_value = None
        
        self.consumer.send_glific_notification(self.sample_message_data)

    @patch('frappe.get_value')
    @patch('frappe.logger')
    def test_send_glific_notification_flow_failure(self, mock_logger, mock_get_value):
        """Test Glific notification with flow start failure."""
        mock_get_value.return_value = "test_flow_id"
        
        with patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow', return_value=False):
            self.consumer.send_glific_notification(self.sample_message_data)

    @patch('frappe.get_value')
    @patch('frappe.logger')
    def test_send_glific_notification_exception(self, mock_logger, mock_get_value):
        """Test Glific notification with exception."""
        mock_get_value.side_effect = Exception("Glific error")
        
        with self.assertRaises(Exception):
            self.consumer.send_glific_notification(self.sample_message_data)

    @patch('frappe.logger')
    def test_start_consuming_with_setup(self, mock_logger):
        """Test start_consuming when channel is None."""
        self.consumer.channel = None
        
        with patch.object(self.consumer, 'setup_rabbitmq') as mock_setup:
            mock_channel = Mock()
            mock_channel.start_consuming.side_effect = KeyboardInterrupt()
            self.consumer.channel = mock_channel
            self.consumer.settings = self.mock_settings
            
            with patch.object(self.consumer, 'stop_consuming'), \
                 patch.object(self.consumer, 'cleanup'):
                
                self.consumer.start_consuming()
                mock_setup.assert_called_once()

    @patch('frappe.logger')
    def test_start_consuming_exception(self, mock_logger):
        """Test start_consuming with exception."""
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        mock_channel.start_consuming.side_effect = Exception("Test error")
        
        with patch.object(self.consumer, 'cleanup') as mock_cleanup:
            with self.assertRaises(Exception):
                self.consumer.start_consuming()
            
            mock_cleanup.assert_called_once()

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

    def test_get_queue_stats_no_channel(self):
        """Test get_queue_stats when channel is None."""
        self.consumer.channel = None
        
        with patch.object(self.consumer, 'setup_rabbitmq') as mock_setup:
            mock_channel = Mock()
            main_queue_response = Mock()
            main_queue_response.method.message_count = 3
            mock_channel.queue_declare.return_value = main_queue_response
            
            self.consumer.channel = mock_channel
            self.consumer.settings = self.mock_settings
            
            stats = self.consumer.get_queue_stats()
            
            mock_setup.assert_called_once()
            self.assertEqual(stats["main_queue"], 3)

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

    @patch('frappe.logger')
    def test_get_queue_stats_exception(self, mock_logger):
        """Test get_queue_stats with exception."""
        mock_channel = Mock()
        mock_channel.queue_declare.side_effect = Exception("Connection error")
        
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        stats = self.consumer.get_queue_stats()
        
        self.assertEqual(stats["main_queue"], 0)
        self.assertEqual(stats["dead_letter_queue"], 0)

    @patch('frappe.logger')
    def test_move_to_dead_letter_success(self, mock_logger):
        """Test successful move_to_dead_letter."""
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        test_data = {"submission_id": "test_123"}
        
        self.consumer.move_to_dead_letter(test_data)
        
        mock_channel.basic_publish.assert_called_once()

    @patch('frappe.logger')
    def test_move_to_dead_letter_exception(self, mock_logger):
        """Test move_to_dead_letter with exception."""
        mock_channel = Mock()
        mock_channel.basic_publish.side_effect = Exception("Publish error")
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        test_data = {"submission_id": "test_123"}
        
        self.consumer.move_to_dead_letter(test_data)

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_update_submission_with_string_grade(self, mock_logger, mock_get_doc):
        """Test submission update with string grade that needs cleaning."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        # Test with grade that has non-numeric characters
        test_data = self.sample_message_data.copy()
        test_data["feedback"]["grade_recommendation"] = "85.5%"
        
        self.consumer.update_submission(test_data)
        
        mock_submission.update.assert_called_once()
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_update_submission_invalid_grade(self, mock_logger, mock_get_doc):
        """Test submission update with invalid grade."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        test_data = self.sample_message_data.copy()
        test_data["feedback"]["grade_recommendation"] = "invalid_grade"
        
        self.consumer.update_submission(test_data)
        
        mock_submission.update.assert_called_once()
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_update_submission_numeric_grade(self, mock_logger, mock_get_doc):
        """Test submission update with numeric grade."""
        mock_submission = Mock()
        mock_get_doc.return_value = mock_submission
        
        test_data = self.sample_message_data.copy()
        test_data["feedback"]["grade_recommendation"] = 85.5
        
        self.consumer.update_submission(test_data)
        
        mock_submission.update.assert_called_once()
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_update_submission_exception(self, mock_logger, mock_get_doc):
        """Test submission update with exception."""
        mock_get_doc.side_effect = Exception("Database error")
        
        with self.assertRaises(Exception):
            self.consumer.update_submission(self.sample_message_data)

    @patch('frappe.get_doc')
    @patch('frappe.logger')
    def test_mark_submission_failed_exception(self, mock_logger, mock_get_doc):
        """Test mark_submission_failed with exception."""
        mock_get_doc.side_effect = Exception("Database error")
        
        self.consumer.mark_submission_failed("test_123", "Test error")

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

    @patch('frappe.get_single')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_dlx_durable_fallback(self, mock_connection, mock_get_single):
        """Test dead letter exchange durable fallback."""
        mock_get_single.return_value = self.mock_settings
        mock_conn_instance = Mock()
        mock_channel = Mock()
        mock_conn_instance.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn_instance
        
        # Test durable=True fallback
        mock_channel.exchange_declare.side_effect = [
            MockChannelClosedByBroker(200, "NOT_FOUND"),  # Passive check fails
            MockChannelClosedByBroker(200, "NOT_FOUND"),  # durable=False fails
            None,  # durable=True succeeds
        ]
        
        with patch.object(self.consumer, '_reconnect') as mock_reconnect:
            self.consumer.setup_rabbitmq()
            self.assertEqual(mock_reconnect.call_count, 2)

    @patch('frappe.get_single')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_queue_scenarios(self, mock_connection, mock_get_single):
        """Test main queue setup scenarios."""
        mock_get_single.return_value = self.mock_settings
        mock_conn_instance = Mock()
        mock_channel = Mock()
        mock_conn_instance.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn_instance
        
        # Test main queue creation when it doesn't exist
        mock_channel.queue_declare.side_effect = [
            None,  # DL queue succeeds
            MockChannelClosedByBroker(200, "NOT_FOUND"),  # Main queue passive fails
            None,  # Main queue creation succeeds
        ]
        
        with patch.object(self.consumer, '_reconnect') as mock_reconnect:
            self.consumer.setup_rabbitmq()
            mock_reconnect.assert_called()

    @patch('frappe.db')
    @patch('frappe.logger')
    def test_process_message_missing_submission_id(self, mock_logger, mock_db):
        """Test message processing with missing submission_id."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        
        invalid_data = {"feedback": "test"}
        body = json.dumps(invalid_data).encode('utf-8')
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('frappe.db')
    @patch('frappe.logger')
    def test_process_message_missing_feedback(self, mock_logger, mock_db):
        """Test message processing with missing feedback."""
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        
        invalid_data = {"submission_id": "test_123"}
        body = json.dumps(invalid_data).encode('utf-8')
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('frappe.logger')
    def test_stop_consuming_closed_channel(self, mock_logger):
        """Test stop_consuming with closed channel."""
        mock_channel = Mock()
        mock_channel.is_closed = True
        self.consumer.channel = mock_channel
        
        self.consumer.stop_consuming()
        
        mock_channel.stop_consuming.assert_not_called()

    @patch('frappe.logger')
    def test_cleanup_closed_connections(self, mock_logger):
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


if __name__ == '__main__':
    unittest.main(verbosity=2)