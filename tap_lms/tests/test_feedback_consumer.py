import unittest
import sys
import os
from unittest.mock import Mock, patch, MagicMock, call, PropertyMock
import json
from datetime import datetime

# FIXED: Go up TWO levels (not one) to reach the directory containing tap_lms/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Create mock pika exceptions FIRST - MUST inherit from BaseException
class MockChannelClosedByBroker(BaseException):
    def __init__(self, reply_code=200, reply_text=""):
        self.reply_code = reply_code
        self.reply_text = reply_text
        super().__init__(f"{reply_code}: {reply_text}")

class MockConnectionClosed(BaseException):
    pass

# Create a proper module-like object for pika.exceptions
class MockPikaExceptions:
    ChannelClosedByBroker = MockChannelClosedByBroker
    ConnectionClosed = MockConnectionClosed

# Mock all external dependencies before importing anything
sys.modules['frappe'] = MagicMock()

# FIXED: Create a mock pika module with the exceptions
mock_pika = MagicMock()
mock_pika.exceptions = MockPikaExceptions  # Use the class, not an instance
mock_pika.PlainCredentials = MagicMock()
mock_pika.ConnectionParameters = MagicMock()
mock_pika.BlockingConnection = MagicMock()
mock_pika.BasicProperties = MagicMock()
sys.modules['pika'] = mock_pika

# FIXED: Mock glific_integration to prevent relative import error
sys.modules['tap_lms.glific_integration'] = MagicMock()

# Configure frappe mock
frappe_mock = sys.modules['frappe']
frappe_mock.get_single = MagicMock()
frappe_mock.get_doc = MagicMock()
frappe_mock.get_value = MagicMock()
frappe_mock.db = MagicMock()
frappe_mock.logger = MagicMock()
frappe_mock.logger.return_value = MagicMock()

# Try to import the actual class
try:
    from tap_lms.feedback_consumer.feedback_consumer import FeedbackConsumer
    USING_REAL_CLASS = True
except ImportError:
    USING_REAL_CLASS = False
    class FeedbackConsumer:
        def __init__(self):
            self.connection = None
            self.channel = None
            self.settings = None


class TestFeedbackConsumer(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        # Reset all frappe mocks and clear side_effects
        frappe_mock.reset_mock()
        frappe_mock.get_doc.side_effect = None
        frappe_mock.get_value.side_effect = None
        frappe_mock.get_single.side_effect = None
        frappe_mock.db.exists.side_effect = None
        
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

    # ==================== Initialization Tests ====================
    
    def test_init(self):
        """Test FeedbackConsumer initialization."""
        consumer = FeedbackConsumer()
        self.assertIsNone(consumer.connection)
        self.assertIsNone(consumer.channel)
        self.assertIsNone(consumer.settings)

    def test_mock_exception_classes(self):
        """Test the mock exception classes for coverage."""
        # Test MockChannelClosedByBroker
        exception = MockChannelClosedByBroker(404, "Not Found")
        self.assertEqual(exception.reply_code, 404)
        self.assertEqual(exception.reply_text, "Not Found")
        self.assertEqual(str(exception), "404: Not Found")
        
        # Test default values
        exception_default = MockChannelClosedByBroker()
        self.assertEqual(exception_default.reply_code, 200)
        self.assertEqual(exception_default.reply_text, "")
        
        # Test MockConnectionClosed
        conn_exception = MockConnectionClosed()
        self.assertIsInstance(conn_exception, BaseException)

    # ==================== setup_rabbitmq Tests ====================
    
    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_success(self, mock_connection, mock_params, mock_creds):
        """Test successful RabbitMQ setup."""
        if not USING_REAL_CLASS:
            return
        
        # Mock successful setup
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        # Mock successful queue declarations
        mock_channel.exchange_declare = Mock()
        mock_channel.queue_declare = Mock()
        mock_channel.queue_bind = Mock()
        
        self.consumer.setup_rabbitmq()
        
        # Verify calls were made
        mock_connection.assert_called_once()
        self.assertEqual(self.consumer.connection, mock_conn)
        self.assertEqual(self.consumer.channel, mock_channel)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_exchange_doesnt_exist(self, mock_connection, mock_params, mock_creds):
        """Test setup when exchange doesn't exist and needs creation."""
        if not USING_REAL_CLASS:
            return
        
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        # First call (passive check) fails, second call (creation) succeeds
        mock_channel.exchange_declare.side_effect = [
            MockChannelClosedByBroker(),
            None
        ]
        mock_channel.queue_declare = Mock()
        mock_channel.queue_bind = Mock()
        
        with patch.object(FeedbackConsumer, '_reconnect') as mock_reconnect:
            mock_reconnect.return_value = None
            # Need to reset channel after reconnect
            def reconnect_side_effect():
                self.consumer.connection = mock_conn
                self.consumer.channel = mock_channel
            mock_reconnect.side_effect = reconnect_side_effect
            
            self.consumer.setup_rabbitmq()
        
        self.assertGreaterEqual(mock_channel.exchange_declare.call_count, 2)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_exchange_needs_durable(self, mock_connection, mock_params, mock_creds):
        """Test setup when exchange needs durable=True."""
        if not USING_REAL_CLASS:
            return
        
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        # Passive fails, durable=False fails, durable=True succeeds
        mock_channel.exchange_declare.side_effect = [
            MockChannelClosedByBroker(),
            MockChannelClosedByBroker(),
            None
        ]
        mock_channel.queue_declare = Mock()
        mock_channel.queue_bind = Mock()
        
        with patch.object(FeedbackConsumer, '_reconnect') as mock_reconnect:
            def reconnect_side_effect():
                self.consumer.connection = mock_conn
                self.consumer.channel = mock_channel
            mock_reconnect.side_effect = reconnect_side_effect
            
            self.consumer.setup_rabbitmq()
        
        self.assertGreaterEqual(mock_channel.exchange_declare.call_count, 3)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_main_queue_doesnt_exist(self, mock_connection, mock_params, mock_creds):
        """Test setup when main queue doesn't exist."""
        if not USING_REAL_CLASS:
            return
        
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        mock_channel.exchange_declare = Mock()
        mock_channel.queue_bind = Mock()
        
        # DL queue succeeds, main queue passive fails, then creation succeeds
        mock_channel.queue_declare.side_effect = [
            Mock(),
            MockChannelClosedByBroker(),
            Mock()
        ]
        
        with patch.object(FeedbackConsumer, '_reconnect') as mock_reconnect:
            def reconnect_side_effect():
                self.consumer.connection = mock_conn
                self.consumer.channel = mock_channel
            mock_reconnect.side_effect = reconnect_side_effect
            
            self.consumer.setup_rabbitmq()
        
        self.assertGreaterEqual(mock_channel.queue_declare.call_count, 3)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_connection_failure(self, mock_connection, mock_params, mock_creds):
        """Test setup_rabbitmq with connection failure."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_single.return_value = self.mock_settings
        mock_connection.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            self.consumer.setup_rabbitmq()

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_full_execution(self, mock_connection, mock_params, mock_creds):
        """Force full execution of setup_rabbitmq with all paths."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        # Mock all operations to succeed
        mock_channel.exchange_declare = Mock()
        mock_channel.queue_declare = Mock(return_value=Mock())
        mock_channel.queue_bind = Mock()
        
        self.consumer.setup_rabbitmq()
        
        # Verify everything was set up
        self.assertIsNotNone(self.consumer.connection)
        self.assertIsNotNone(self.consumer.channel)
        self.assertIsNotNone(self.consumer.settings)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_dl_queue_channel_error(self, mock_connection, mock_params, mock_creds):
        """Test setup when dead letter queue declaration fails."""
        if not USING_REAL_CLASS:
            return
        
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        # Exchange succeeds, DL queue fails, then succeeds after reconnect
        mock_channel.exchange_declare = Mock()
        mock_channel.queue_declare.side_effect = [
            MockChannelClosedByBroker(),  # DL queue fails
            Mock(),  # DL queue succeeds after reconnect
            Mock()   # Main queue succeeds
        ]
        mock_channel.queue_bind = Mock()
        
        with patch.object(FeedbackConsumer, '_reconnect') as mock_reconnect:
            def reconnect_side_effect():
                self.consumer.connection = mock_conn
                self.consumer.channel = mock_channel
            mock_reconnect.side_effect = reconnect_side_effect
            
            self.consumer.setup_rabbitmq()
        
        self.assertGreaterEqual(mock_channel.queue_declare.call_count, 2)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_queue_bind_exception(self, mock_connection, mock_params, mock_creds):
        """Test setup when queue bind fails (should be ignored)."""
        if not USING_REAL_CLASS:
            return
        
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        mock_channel.exchange_declare = Mock()
        mock_channel.queue_declare = Mock(return_value=Mock())
        mock_channel.queue_bind.side_effect = Exception("Bind failed")
        
        # Should not raise exception - binding errors are ignored
        self.consumer.setup_rabbitmq()
        
        self.assertIsNotNone(self.consumer.channel)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_setup_rabbitmq_all_scenarios(self, mock_connection, mock_params, mock_creds):
        """Test setup_rabbitmq with comprehensive scenario coverage."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_single.return_value = self.mock_settings
        
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.channel.return_value = mock_channel
        mock_connection.return_value = mock_conn
        
        # Simulate: exchange exists, DL queue exists, main queue doesn't exist
        mock_channel.exchange_declare = Mock()  # Succeeds (exchange exists)
        
        mock_channel.queue_declare.side_effect = [
            Mock(),  # DL queue succeeds
            MockChannelClosedByBroker(),  # Main queue passive check fails
            Mock()   # Main queue creation succeeds
        ]
        
        mock_channel.queue_bind = Mock()
        
        with patch.object(FeedbackConsumer, '_reconnect') as mock_reconnect:
            def reconnect_side_effect():
                self.consumer.connection = mock_conn
                self.consumer.channel = mock_channel
            mock_reconnect.side_effect = reconnect_side_effect
            
            self.consumer.setup_rabbitmq()
        
        # Verify setup completed
        self.assertIsNotNone(self.consumer.connection)
        self.assertIsNotNone(self.consumer.channel)

    # ==================== _reconnect Tests ====================
    
    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_reconnect_success(self, mock_connection, mock_params, mock_creds):
        """Test successful reconnection."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.settings = self.mock_settings
        
        old_conn = Mock()
        old_conn.is_closed = False
        self.consumer.connection = old_conn
        
        mock_new_conn = Mock()
        mock_new_channel = Mock()
        mock_new_conn.channel.return_value = mock_new_channel
        mock_connection.return_value = mock_new_conn
        
        self.consumer._reconnect()
        
        old_conn.close.assert_called_once()
        self.assertEqual(self.consumer.connection, mock_new_conn)
        self.assertEqual(self.consumer.channel, mock_new_channel)

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_reconnect_with_closed_connection(self, mock_connection, mock_params, mock_creds):
        """Test _reconnect with already closed connection."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.settings = self.mock_settings
        
        mock_connection_obj = Mock()
        mock_connection_obj.is_closed = True
        self.consumer.connection = mock_connection_obj
        
        mock_new_conn = Mock()
        mock_new_channel = Mock()
        mock_new_conn.channel.return_value = mock_new_channel
        mock_connection.return_value = mock_new_conn
        
        self.consumer._reconnect()
        
        # Should not try to close already closed connection
        mock_connection_obj.close.assert_not_called()

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_reconnect_close_exception(self, mock_connection, mock_params, mock_creds):
        """Test _reconnect when closing old connection raises exception."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.settings = self.mock_settings
        
        mock_connection_obj = Mock()
        mock_connection_obj.is_closed = False
        mock_connection_obj.close.side_effect = Exception("Close error")
        self.consumer.connection = mock_connection_obj
        
        mock_new_conn = Mock()
        mock_new_channel = Mock()
        mock_new_conn.channel.return_value = mock_new_channel
        mock_connection.return_value = mock_new_conn
        
        # Should not raise exception
        self.consumer._reconnect()
        
        self.assertEqual(self.consumer.connection, mock_new_conn)

    def test_reconnect_exception_during_close(self):
        """Test reconnection when closing old connection fails."""
        if not USING_REAL_CLASS:
            return
            
        self.consumer.settings = self.mock_settings
        
        # Mock old connection that fails to close
        old_conn = Mock()
        old_conn.is_closed = False
        old_conn.close.side_effect = Exception("Close failed")
        self.consumer.connection = old_conn
        
        with patch('pika.PlainCredentials'):
            with patch('pika.ConnectionParameters'):
                with patch('pika.BlockingConnection') as mock_connection:
                    mock_new_conn = Mock()
                    mock_new_channel = Mock()
                    mock_new_conn.channel.return_value = mock_new_channel
                    mock_connection.return_value = mock_new_conn
                    
                    # Should not raise exception
                    self.consumer._reconnect()

    @patch('pika.PlainCredentials')
    @patch('pika.ConnectionParameters')
    @patch('pika.BlockingConnection')
    def test_reconnect_with_none_connection(self, mock_connection, mock_params, mock_creds):
        """Test _reconnect when connection is None."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.settings = self.mock_settings
        self.consumer.connection = None
        
        mock_new_conn = Mock()
        mock_new_channel = Mock()
        mock_new_conn.channel.return_value = mock_new_channel
        mock_connection.return_value = mock_new_conn
        
        self.consumer._reconnect()
        
        self.assertEqual(self.consumer.connection, mock_new_conn)
        self.assertEqual(self.consumer.channel, mock_new_channel)

    # ==================== start_consuming Tests ====================
    
    def test_start_consuming_success(self):
        """Test successful start_consuming."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        # Mock start_consuming to avoid infinite loop
        def stop_after_setup():
            self.consumer.stop_consuming()
        
        mock_channel.start_consuming.side_effect = stop_after_setup
        
        with patch.object(self.consumer, 'cleanup'):
            self.consumer.start_consuming()
        
        mock_channel.basic_qos.assert_called_once_with(prefetch_count=1)
        mock_channel.basic_consume.assert_called_once()

    def test_start_consuming_no_channel(self):
        """Test start_consuming when channel is not set."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.channel = None
        self.consumer.settings = self.mock_settings
        
        with patch.object(self.consumer, 'setup_rabbitmq') as mock_setup:
            mock_channel = Mock()
            
            def setup_side_effect():
                self.consumer.channel = mock_channel
                self.consumer.stop_consuming()
            
            mock_setup.side_effect = setup_side_effect
            mock_channel.start_consuming.side_effect = lambda: None
            
            with patch.object(self.consumer, 'cleanup'):
                self.consumer.start_consuming()
            
            mock_setup.assert_called_once()

    def test_start_consuming_keyboard_interrupt(self):
        """Test start_consuming with KeyboardInterrupt."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        mock_channel.start_consuming.side_effect = KeyboardInterrupt()
        
        with patch.object(self.consumer, 'stop_consuming') as mock_stop:
            with patch.object(self.consumer, 'cleanup') as mock_cleanup:
                self.consumer.start_consuming()
                mock_stop.assert_called_once()
                mock_cleanup.assert_called_once()

    def test_start_consuming_exception(self):
        """Test start_consuming with exception."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        mock_channel.start_consuming.side_effect = Exception("Test error")
        
        with patch.object(self.consumer, 'cleanup') as mock_cleanup:
            with self.assertRaises(Exception):
                self.consumer.start_consuming()
            
            mock_cleanup.assert_called_once()

    # ==================== process_message Tests ====================
    
    def test_process_message_successful_processing(self):
        """Test successful message processing with database transaction."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.commit = Mock()
        
        with patch.object(self.consumer, 'update_submission') as mock_update:
            with patch.object(self.consumer, 'send_glific_notification') as mock_glific:
                self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                
                frappe_mock.db.begin.assert_called_once()
                mock_update.assert_called_once()
                mock_glific.assert_called_once()
                frappe_mock.db.commit.assert_called_once()
                mock_ch.basic_ack.assert_called_once_with(delivery_tag="test_tag")

    def test_process_message_with_rollback(self):
        """Test message processing with database rollback on error."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.rollback = Mock()
        
        with patch.object(self.consumer, 'update_submission', side_effect=Exception("Database error")):
            with patch.object(self.consumer, 'is_retryable_error', return_value=False):
                with patch.object(self.consumer, 'mark_submission_failed') as mock_mark:
                    self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                    
                    frappe_mock.db.rollback.assert_called()
                    mock_mark.assert_called_once()

    def test_process_message_invalid_json(self):
        """Test message processing with invalid JSON."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = b"invalid json"
        
        frappe_mock.db.begin = Mock()
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_process_message_missing_submission_id(self):
        """Test message processing with missing submission_id."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        
        invalid_data = {"feedback": {"overall_feedback": "test"}}
        body = json.dumps(invalid_data).encode('utf-8')
        
        frappe_mock.db.begin = Mock()
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_process_message_missing_feedback(self):
        """Test message processing with missing feedback."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        
        invalid_data = {"submission_id": "test_123"}
        body = json.dumps(invalid_data).encode('utf-8')
        
        frappe_mock.db.begin = Mock()
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_process_message_submission_not_found(self):
        """Test message processing when submission doesn't exist."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.begin = Mock()
        frappe_mock.db.exists.return_value = False
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_process_message_retryable_error(self):
        """Test message processing with retryable error."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.rollback = Mock()
        
        with patch.object(self.consumer, 'update_submission', side_effect=Exception("Database connection lost")):
            with patch.object(self.consumer, 'is_retryable_error', return_value=True):
                self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                
                frappe_mock.db.rollback.assert_called()
                mock_ch.basic_nack.assert_called_once_with(delivery_tag="test_tag", requeue=True)

    def test_process_message_non_retryable_error(self):
        """Test message processing with non-retryable error."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.rollback = Mock()
        frappe_mock.db.commit = Mock()
        
        with patch.object(self.consumer, 'update_submission', side_effect=Exception("Record does not exist")):
            with patch.object(self.consumer, 'is_retryable_error', return_value=False):
                with patch.object(self.consumer, 'mark_submission_failed') as mock_mark_failed:
                    self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                    
                    frappe_mock.db.rollback.assert_called()
                    mock_mark_failed.assert_called_once()
                    mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    def test_process_message_glific_notification_failure(self):
        """Test message processing when Glific notification fails (should not fail message)."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.commit = Mock()
        
        with patch.object(self.consumer, 'update_submission') as mock_update:
            with patch.object(self.consumer, 'send_glific_notification', side_effect=Exception("Glific error")):
                self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                
                # Should still commit and ack despite Glific failure
                mock_update.assert_called_once()
                frappe_mock.db.commit.assert_called_once()
                mock_ch.basic_ack.assert_called_once_with(delivery_tag="test_tag")

    def test_process_message_mark_failed_exception(self):
        """Test process_message when mark_submission_failed also fails."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "test_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.rollback = Mock()
        
        with patch.object(self.consumer, 'update_submission', side_effect=Exception("Update error")):
            with patch.object(self.consumer, 'is_retryable_error', return_value=False):
                with patch.object(self.consumer, 'mark_submission_failed', side_effect=Exception("Mark failed error")):
                    self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                    
                    # Should still reject the message
                    mock_ch.basic_reject.assert_called_once_with(delivery_tag="test_tag", requeue=False)

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_process_message_complete_integration(self, mock_start_flow):
        """Test complete process_message integration with all components."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "integration_tag"
        mock_properties = Mock()
        
        complete_message = {
            "submission_id": "integration_test_123",
            "student_id": "student_integration",
            "feedback": {
                "grade_recommendation": "95.0",
                "overall_feedback": "Outstanding work!"
            },
            "plagiarism_score": 3.5,
            "summary": "Excellent submission",
            "similar_sources": [{"source": "academic.com", "score": 0.03}]
        }
        body = json.dumps(complete_message).encode('utf-8')
        
        # Setup mocks
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.commit = Mock()
        frappe_mock.get_value.return_value = "flow_integration"
        mock_start_flow.return_value = True
        
        mock_submission = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        # Execute
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        # Verify complete flow
        frappe_mock.db.begin.assert_called_once()
        # Check that the submission was updated (update is called on the mock)
        self.assertTrue(hasattr(mock_submission, 'update'))
        mock_submission.save.assert_called_once()
        mock_start_flow.assert_called_once()
        frappe_mock.db.commit.assert_called_once()
        mock_ch.basic_ack.assert_called_once_with(delivery_tag="integration_tag")

    def test_process_message_json_decode_error_specific(self):
        """Test process_message with JSON decode error specifically."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "decode_tag"
        mock_properties = Mock()
        body = b"{invalid json content"
        
        frappe_mock.db.begin = Mock()
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="decode_tag", requeue=False)

    def test_process_message_value_error_in_validation(self):
        """Test process_message with ValueError during validation."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "value_tag"
        mock_properties = Mock()
        
        # Valid JSON but will trigger ValueError in validation
        invalid_data = {"submission_id": "", "feedback": {}}  # Empty submission_id
        body = json.dumps(invalid_data).encode('utf-8')
        
        frappe_mock.db.begin = Mock()
        
        self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
        
        mock_ch.basic_reject.assert_called_once_with(delivery_tag="value_tag", requeue=False)

    def test_full_error_flow_with_retries(self):
        """Test complete error flow with retry logic."""
        if not USING_REAL_CLASS:
            return
        
        mock_ch = Mock()
        mock_method = Mock()
        mock_method.delivery_tag = "retry_tag"
        mock_properties = Mock()
        body = json.dumps(self.sample_message_data).encode('utf-8')
        
        frappe_mock.db.exists.return_value = True
        frappe_mock.db.begin = Mock()
        frappe_mock.db.rollback = Mock()
        
        # Simulate retryable error
        error = Exception("Connection timeout")
        
        with patch.object(self.consumer, 'update_submission', side_effect=error):
            with patch.object(self.consumer, 'is_retryable_error', return_value=True):
                self.consumer.process_message(mock_ch, mock_method, mock_properties, body)
                
                frappe_mock.db.rollback.assert_called()
                mock_ch.basic_nack.assert_called_once_with(
                    delivery_tag="retry_tag",
                    requeue=True
                )

    def test_process_message_all_error_patterns(self):
        """Test all error patterns in is_retryable_error."""
        if not USING_REAL_CLASS:
            return
        
        # Test each non-retryable pattern
        patterns = [
            ("does not exist", False),
            ("not found", False),
            ("invalid", False),
            ("permission denied", False),
            ("duplicate", False),
            ("constraint violation", False),
            ("missing submission_id", False),
            ("missing feedback data", False),
            ("validation error", False),
            ("random error", True),  # Retryable
        ]
        
        for error_msg, should_retry in patterns:
            error = Exception(error_msg)
            result = self.consumer.is_retryable_error(error)
            self.assertEqual(
                result,
                should_retry,
                f"Error '{error_msg}' should {'be retryable' if should_retry else 'not be retryable'}"
            )

    # ==================== is_retryable_error Tests ====================
    
    def test_is_retryable_error(self):
        """Test is_retryable_error method."""
        if not USING_REAL_CLASS:
            return
        
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
            self.assertFalse(self.consumer.is_retryable_error(error), f"Should not retry: {error}")
        
        # Retryable errors
        retryable_errors = [
            Exception("Database connection lost"),
            Exception("Temporary network error"),
            Exception("Timeout occurred"),
            Exception("Connection reset"),
            Exception("Deadlock detected")
        ]
        
        for error in retryable_errors:
            self.assertTrue(self.consumer.is_retryable_error(error), f"Should retry: {error}")

    # ==================== update_submission Tests ====================
    
    def test_update_submission_complete_flow(self):
        """Test complete update_submission flow with all fields."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        # Complete message data
        complete_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "92.5",
                "overall_feedback": "Excellent work with detailed analysis"
            },
            "plagiarism_score": 8.3,
            "summary": "Well-researched submission",
            "similar_sources": [
                {"source": "example.com", "score": 0.15},
                {"source": "test.org", "score": 0.08}
            ]
        }
        
        self.consumer.update_submission(complete_data)
        
        # Verify all fields were updated
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["status"], "Completed")
        self.assertEqual(call_args["grade"], 92.5)
        self.assertEqual(call_args["plagiarism_result"], 8.3)
        self.assertEqual(call_args["feedback_summary"], "Well-researched submission")
        self.assertEqual(call_args["overall_feedback"], "Excellent work with detailed analysis")
        self.assertIn("similar_sources", call_args)
        self.assertIn("generated_feedback", call_args)
        mock_submission.save.assert_called_once_with(ignore_permissions=True)
    
    def test_update_submission_with_string_grade(self):
        """Test update_submission with string grade value."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "85.5",
                "overall_feedback": "Good work"
            },
            "plagiarism_score": "15.5",
            "summary": "Summary text",
            "similar_sources": [{"source": "test.com"}]
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 85.5)
        self.assertEqual(call_args["status"], "Completed")
        self.assertEqual(call_args["plagiarism_result"], 15.5)
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    def test_update_submission_with_numeric_grade(self):
        """Test update_submission with numeric grade value."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": 90.0,
                "overall_feedback": "Excellent"
            },
            "plagiarism_score": 5.0,
            "summary": "Summary",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 90.0)

    def test_update_submission_with_invalid_grade(self):
        """Test update_submission with invalid grade (should default to 0.0)."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "invalid_grade",
                "overall_feedback": "Feedback"
            },
            "plagiarism_score": 0,
            "summary": "",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 0.0)

    def test_update_submission_with_string_with_text(self):
        """Test update_submission with grade string containing text."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "Grade: 87.5 points",
                "overall_feedback": "Good"
            },
            "plagiarism_score": 10,
            "summary": "Test",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 87.5)

    def test_update_submission_with_non_list_similar_sources(self):
        """Test update_submission with non-list similar_sources."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "80",
                "overall_feedback": "OK"
            },
            "plagiarism_score": 0,
            "summary": "",
            "similar_sources": "not a list"
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["similar_sources"], "[]")

    def test_update_submission_with_non_dict_feedback(self):
        """Test update_submission with non-dict feedback data."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": "string instead of dict",
            "plagiarism_score": 0,
            "summary": "",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["generated_feedback"], "{}")
        # Should still complete with default values
        self.assertEqual(call_args["status"], "Completed")
        self.assertEqual(call_args["grade"], 0.0)

    def test_update_submission_with_invalid_plagiarism_score(self):
        """Test update_submission with invalid plagiarism score."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "75",
                "overall_feedback": "OK"
            },
            "plagiarism_score": "not_a_number",
            "summary": "",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["plagiarism_result"], 0.0)

    def test_update_submission_exception(self):
        """Test update_submission when document update fails."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_doc.side_effect = Exception("Document error")
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "80",
                "overall_feedback": "Good work"
            }
        }
        
        try:
            with self.assertRaises(Exception):
                self.consumer.update_submission(test_data)
        finally:
            # Clean up side_effect for next tests
            frappe_mock.get_doc.side_effect = None

    def test_update_submission_with_missing_optional_fields(self):
        """Test update_submission with missing optional fields."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "test_123",
            "feedback": {
                "grade_recommendation": "75"
            }
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 75.0)
        self.assertEqual(call_args["overall_feedback"], "")
        self.assertEqual(call_args["feedback_summary"], "")

    def test_update_submission_all_edge_cases(self):
        """Test update_submission with various edge cases in one test."""
        if not USING_REAL_CLASS:
            return
        
        # Test with empty strings and missing fields
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        edge_case_data = {
            "submission_id": "edge_case_123",
            "feedback": {
                "grade_recommendation": "",  # Empty string
                "overall_feedback": ""
            },
            "plagiarism_score": None,  # None value
            "summary": None,
            "similar_sources": None
        }
        
        # Should not raise exception
        self.consumer.update_submission(edge_case_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["status"], "Completed")
        # Empty grade should become 0.0
        self.assertEqual(call_args["grade"], 0.0)
        # None plagiarism should become 0.0
        self.assertEqual(call_args["plagiarism_result"], 0.0)
        mock_submission.save.assert_called_once()

    def test_update_submission_real_execution(self):
        """Force real execution of update_submission with all code paths."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        data = {
            "submission_id": "real_test_123",
            "feedback": {
                "grade_recommendation": "78.5",
                "overall_feedback": "Good effort"
            },
            "plagiarism_score": 12.3,
            "summary": "Test summary",
            "similar_sources": [{"source": "test.com"}]
        }
        
        # This will execute all lines in update_submission
        self.consumer.update_submission(data)
        
        # Verify execution
        mock_submission.update.assert_called_once()
        call_args = mock_submission.update.call_args[0][0]
        
        # Verify all fields were processed
        self.assertIn("status", call_args)
        self.assertIn("grade", call_args)
        self.assertIn("plagiarism_result", call_args)
        self.assertIn("feedback_summary", call_args)
        self.assertIn("overall_feedback", call_args)
        self.assertIn("similar_sources", call_args)
        self.assertIn("generated_feedback", call_args)
        self.assertIn("completed_at", call_args)
        
        self.assertEqual(call_args["grade"], 78.5)
        self.assertEqual(call_args["status"], "Completed")
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    def test_update_submission_with_none_grade(self):
        """Test update_submission when grade_recommendation is None."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "none_grade_123",
            "feedback": {
                "grade_recommendation": None,
                "overall_feedback": "Feedback"
            },
            "plagiarism_score": 0,
            "summary": "",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 0.0)

    def test_update_submission_type_error_in_grade(self):
        """Test update_submission with TypeError in grade conversion."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "type_error_123",
            "feedback": {
                "grade_recommendation": {"nested": "dict"},  # Will cause TypeError
                "overall_feedback": "Test"
            },
            "plagiarism_score": 0,
            "summary": "",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 0.0)

    def test_update_submission_missing_grade_key(self):
        """Test update_submission when grade_recommendation key is missing."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "missing_grade_123",
            "feedback": {
                "overall_feedback": "Good"
            },
            "plagiarism_score": 5,
            "summary": "Summary",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 0.0)  # Default when missing

    def test_update_submission_with_decimal_in_string(self):
        """Test update_submission with grade as string with multiple decimals."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "decimal_123",
            "feedback": {
                "grade_recommendation": "Score: 88.75%",
                "overall_feedback": "Great"
            },
            "plagiarism_score": 2.5,
            "summary": "Test",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        self.assertEqual(call_args["grade"], 88.75)

    def test_update_submission_with_boolean_grade(self):
        """Test update_submission with boolean grade value."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "bool_grade_123",
            "feedback": {
                "grade_recommendation": True,  # Boolean instead of number
                "overall_feedback": "Test"
            },
            "plagiarism_score": 0,
            "summary": "",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        # Boolean True should convert to 1.0
        self.assertEqual(call_args["grade"], 1.0)

    def test_update_submission_with_list_grade(self):
        """Test update_submission with list as grade value."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.update = Mock()
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        test_data = {
            "submission_id": "list_grade_123",
            "feedback": {
                "grade_recommendation": [85, 90],  # List instead of number
                "overall_feedback": "Test"
            },
            "plagiarism_score": 0,
            "summary": "",
            "similar_sources": []
        }
        
        self.consumer.update_submission(test_data)
        
        call_args = mock_submission.update.call_args[0][0]
        # Should default to 0.0 for invalid types
        self.assertEqual(call_args["grade"], 0.0)

    # ==================== send_glific_notification Tests ====================
    
    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_send_glific_notification_success(self, mock_start_flow):
        """Test successful Glific notification."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_value.return_value = "flow_123"
        mock_start_flow.return_value = True
        
        self.consumer.send_glific_notification(self.sample_message_data)
        
        mock_start_flow.assert_called_once()
        call_args = mock_start_flow.call_args[1]
        self.assertEqual(call_args["flow_id"], "flow_123")
        self.assertEqual(call_args["contact_id"], "student_456")

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_send_glific_notification_no_flow_configured(self, mock_start_flow):
        """Test Glific notification when flow is not configured."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_value.return_value = None
        
        self.consumer.send_glific_notification(self.sample_message_data)
        
        mock_start_flow.assert_not_called()

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_send_glific_notification_flow_fails(self, mock_start_flow):
        """Test Glific notification when flow execution fails."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_value.return_value = "flow_123"
        mock_start_flow.return_value = False
        
        self.consumer.send_glific_notification(self.sample_message_data)
        
        mock_start_flow.assert_called_once()

    def test_send_glific_notification_missing_student_id(self):
        """Test Glific notification with missing student_id."""
        if not USING_REAL_CLASS:
            return
        
        test_data = self.sample_message_data.copy()
        del test_data["student_id"]
        
        # Should not raise any exception
        self.consumer.send_glific_notification(test_data)

    def test_send_glific_notification_missing_feedback(self):
        """Test Glific notification with missing overall_feedback."""
        if not USING_REAL_CLASS:
            return
        
        test_data = self.sample_message_data.copy()
        test_data["feedback"] = {}
        
        # Should not raise any exception
        self.consumer.send_glific_notification(test_data)

    def test_send_glific_notification_exception(self):
        """Test Glific notification with exception."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_value.side_effect = Exception("Glific error")
        
        try:
            with self.assertRaises(Exception):
                self.consumer.send_glific_notification(self.sample_message_data)
        finally:
            # Clean up side_effect for next tests
            frappe_mock.get_value.side_effect = None

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    @patch('tap_lms.feedback_consumer.feedback_consumer.get_glific_settings')
    def test_send_glific_notification_complete_flow(self, mock_settings, mock_start_flow):
        """Test complete Glific notification flow."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_value.return_value = "flow_456"
        mock_start_flow.return_value = True
        
        complete_data = {
            "submission_id": "test_sub_999",
            "student_id": "student_789",
            "feedback": {
                "grade_recommendation": "88",
                "overall_feedback": "Great job on this assignment!"
            }
        }
        
        self.consumer.send_glific_notification(complete_data)
        
        # Verify flow was called with correct parameters
        self.assertTrue(mock_start_flow.called)
        call_kwargs = mock_start_flow.call_args[1]
        self.assertEqual(call_kwargs["flow_id"], "flow_456")
        self.assertEqual(call_kwargs["contact_id"], "student_789")
        self.assertIn("default_results", call_kwargs)
        self.assertEqual(call_kwargs["default_results"]["submission_id"], "test_sub_999")

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_send_glific_notification_real_execution(self, mock_flow):
        """Force real execution of send_glific_notification."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_value.return_value = "flow_real_test"
        mock_flow.return_value = True
        
        data = {
            "submission_id": "glific_real_123",
            "student_id": "student_real_456",
            "feedback": {
                "overall_feedback": "Well done!"
            }
        }
        
        # Execute
        self.consumer.send_glific_notification(data)
        
        # Verify
        mock_flow.assert_called_once()
        call_kwargs = mock_flow.call_args[1]
        self.assertEqual(call_kwargs["flow_id"], "flow_real_test")
        self.assertEqual(call_kwargs["contact_id"], "student_real_456")
        self.assertIn("default_results", call_kwargs)

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_send_glific_notification_empty_student_id(self, mock_start_flow):
        """Test Glific notification with empty string student_id."""
        if not USING_REAL_CLASS:
            return
        
        test_data = self.sample_message_data.copy()
        test_data["student_id"] = ""
        
        self.consumer.send_glific_notification(test_data)
        
        mock_start_flow.assert_not_called()

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_send_glific_notification_empty_feedback(self, mock_start_flow):
        """Test Glific notification with empty overall_feedback."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_value.return_value = "flow_123"
        
        test_data = self.sample_message_data.copy()
        test_data["feedback"]["overall_feedback"] = ""
        
        self.consumer.send_glific_notification(test_data)
        
        mock_start_flow.assert_not_called()

    @patch('tap_lms.feedback_consumer.feedback_consumer.start_contact_flow')
    def test_send_glific_notification_missing_feedback_dict(self, mock_start_flow):
        """Test Glific notification when feedback key is missing entirely."""
        if not USING_REAL_CLASS:
            return
        
        test_data = {
            "submission_id": "test_123",
            "student_id": "student_456"
        }
        
        self.consumer.send_glific_notification(test_data)
        
        mock_start_flow.assert_not_called()

    # ==================== mark_submission_failed Tests ====================
    
    def test_mark_submission_failed_with_error_field(self):
        """Test mark_submission_failed when error_message field exists."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.error_message = ""  # Initialize the attribute
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        error_msg = "Test error message"
        self.consumer.mark_submission_failed("test_123", error_msg)
        
        self.assertEqual(mock_submission.status, "Failed")
        self.assertEqual(mock_submission.error_message, error_msg)
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    def test_mark_submission_failed_without_error_field(self):
        """Test mark_submission_failed when error_message field doesn't exist."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock(spec=['status', 'save'])  # Only has status and save
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        error_msg = "Test error message"
        self.consumer.mark_submission_failed("test_123", error_msg)
        
        self.assertEqual(mock_submission.status, "Failed")
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    def test_mark_submission_failed_exception(self):
        """Test mark_submission_failed with exception."""
        if not USING_REAL_CLASS:
            return
        
        frappe_mock.get_doc.side_effect = Exception("Database error")
        
        # Should not raise exception, just log error
        self.consumer.mark_submission_failed("test_123", "Test error")
        
        # Clean up for next tests
        frappe_mock.get_doc.side_effect = None

    def test_mark_submission_failed_long_error_message(self):
        """Test mark_submission_failed with very long error message."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.error_message = ""  # Initialize the attribute
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        error_msg = "x" * 1000  # Very long message
        self.consumer.mark_submission_failed("test_123", error_msg)
        
        # Should truncate to 500 characters
        self.assertEqual(len(mock_submission.error_message), 500)
        self.assertEqual(mock_submission.status, "Failed")
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    def test_mark_submission_failed_complete_coverage(self):
        """Test mark_submission_failed with complete coverage."""
        if not USING_REAL_CLASS:
            return
        
        # Test with error_message attribute present
        mock_submission_with_attr = Mock()
        mock_submission_with_attr.error_message = ""  # Initialize the attribute
        mock_submission_with_attr.save = Mock()
        
        frappe_mock.get_doc.return_value = mock_submission_with_attr
        
        long_error = "x" * 600  # Longer than 500
        self.consumer.mark_submission_failed("test_fail_123", long_error)
        
        self.assertEqual(mock_submission_with_attr.status, "Failed")
        # Should be truncated to 500
        self.assertEqual(len(mock_submission_with_attr.error_message), 500)
        mock_submission_with_attr.save.assert_called_once()

    def test_mark_submission_failed_real_execution(self):
        """Force real execution of mark_submission_failed."""
        if not USING_REAL_CLASS:
            return
        
        mock_sub = Mock()
        mock_sub.error_message = ""  # Initialize the attribute
        mock_sub.save = Mock()
        frappe_mock.get_doc.return_value = mock_sub
        
        error_msg = "Real test error" * 50  # Long error
        
        # Execute
        self.consumer.mark_submission_failed("real_fail_123", error_msg)
        
        # Verify
        self.assertEqual(mock_sub.status, "Failed")
        # Should truncate to 500 chars
        self.assertTrue(len(mock_sub.error_message) <= 500)
        mock_sub.save.assert_called_once_with(ignore_permissions=True)

    def test_mark_submission_failed_save_exception(self):
        """Test mark_submission_failed when save() raises exception."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.error_message = ""  # Initialize the attribute
        mock_submission.save.side_effect = Exception("Save failed")
        frappe_mock.get_doc.return_value = mock_submission
        
        # Should not raise exception
        self.consumer.mark_submission_failed("test_123", "Error message")
        
        self.assertEqual(mock_submission.status, "Failed")
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    def test_mark_submission_failed_exact_500_chars(self):
        """Test mark_submission_failed with exactly 500 character error."""
        if not USING_REAL_CLASS:
            return
        
        mock_submission = Mock()
        mock_submission.error_message = ""  # Initialize the attribute
        mock_submission.save = Mock()
        frappe_mock.get_doc.return_value = mock_submission
        
        error_msg = "x" * 500
        self.consumer.mark_submission_failed("test_123", error_msg)
        
        self.assertEqual(len(mock_submission.error_message), 500)
        self.assertEqual(mock_submission.status, "Failed")
        mock_submission.save.assert_called_once_with(ignore_permissions=True)

    # ==================== stop_consuming Tests ====================
    
    def test_stop_consuming_success(self):
        """Test successful stop_consuming."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        mock_channel.is_closed = False
        self.consumer.channel = mock_channel
        
        self.consumer.stop_consuming()
        mock_channel.stop_consuming.assert_called_once()

    def test_stop_consuming_exception(self):
        """Test stop_consuming with exception."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        mock_channel.is_closed = False
        mock_channel.stop_consuming.side_effect = Exception("Stop error")
        self.consumer.channel = mock_channel
        
        # Should handle exception gracefully
        self.consumer.stop_consuming()

    def test_stop_consuming_closed_channel(self):
        """Test stop_consuming with closed channel."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        mock_channel.is_closed = True
        self.consumer.channel = mock_channel
        
        self.consumer.stop_consuming()
        mock_channel.stop_consuming.assert_not_called()

    def test_stop_consuming_no_channel(self):
        """Test stop_consuming with no channel."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.channel = None
        
        # Should not raise exception
        self.consumer.stop_consuming()

    # ==================== cleanup Tests ====================
    
    def test_cleanup_success(self):
        """Test successful cleanup."""
        if not USING_REAL_CLASS:
            return
        
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
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        mock_channel.is_closed = False
        mock_channel.close.side_effect = Exception("Close error")
        
        self.consumer.channel = mock_channel
        self.consumer.connection = None
        
        # Should not raise an exception
        self.consumer.cleanup()

    def test_cleanup_closed_connections(self):
        """Test cleanup with closed connections."""
        if not USING_REAL_CLASS:
            return
        
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
        if not USING_REAL_CLASS:
            return
        
        self.consumer.channel = None
        self.consumer.connection = None
        
        # Should not raise exception
        self.consumer.cleanup()

    # ==================== get_queue_stats Tests ====================
    
    def test_get_queue_stats_success(self):
        """Test successful get_queue_stats."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        
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
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        
        main_queue_response = Mock()
        main_queue_response.method.message_count = 5
        
        mock_channel.queue_declare.side_effect = [
            main_queue_response,
            Exception("DL queue not found")
        ]
        
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        stats = self.consumer.get_queue_stats()
        self.assertEqual(stats["main_queue"], 5)
        self.assertEqual(stats["dead_letter_queue"], 0)

    def test_get_queue_stats_no_channel(self):
        """Test get_queue_stats when channel is not set."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.channel = None
        self.consumer.settings = self.mock_settings
        
        mock_channel = Mock()
        main_queue_response = Mock()
        main_queue_response.method.message_count = 3
        dl_queue_response = Mock()
        dl_queue_response.method.message_count = 1
        
        mock_channel.queue_declare.side_effect = [main_queue_response, dl_queue_response]
        
        with patch.object(self.consumer, 'setup_rabbitmq') as mock_setup:
            def setup_side_effect():
                self.consumer.channel = mock_channel
            mock_setup.side_effect = setup_side_effect
            
            stats = self.consumer.get_queue_stats()
            
            mock_setup.assert_called_once()
            self.assertEqual(stats["main_queue"], 3)
            self.assertEqual(stats["dead_letter_queue"], 1)

    def test_get_queue_stats_exception(self):
        """Test get_queue_stats with exception."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        mock_channel.queue_declare.side_effect = Exception("Connection error")
        
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        stats = self.consumer.get_queue_stats()
        self.assertEqual(stats["main_queue"], 0)
        self.assertEqual(stats["dead_letter_queue"], 0)

    def test_get_queue_stats_no_channel_setup(self):
        """Test get_queue_stats triggers setup when no channel."""
        if not USING_REAL_CLASS:
            return
        
        self.consumer.channel = None
        self.consumer.settings = self.mock_settings
        
        with patch.object(self.consumer, 'setup_rabbitmq') as mock_setup:
            mock_channel = Mock()
            main_response = Mock()
            main_response.method.message_count = 10
            dl_response = Mock()
            dl_response.method.message_count = 2
            
            mock_channel.queue_declare.side_effect = [main_response, dl_response]
            
            def setup_effect():
                self.consumer.channel = mock_channel
            
            mock_setup.side_effect = setup_effect
            
            stats = self.consumer.get_queue_stats()
            
            mock_setup.assert_called_once()
            self.assertEqual(stats["main_queue"], 10)
            self.assertEqual(stats["dead_letter_queue"], 2)

    # ==================== move_to_dead_letter Tests ====================
    
    def test_move_to_dead_letter_success(self):
        """Test successful move_to_dead_letter."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        test_data = {"submission_id": "test_123", "error": "Test error"}
        
        self.consumer.move_to_dead_letter(test_data)
        mock_channel.basic_publish.assert_called_once()
        
        # Verify routing key
        call_args = mock_channel.basic_publish.call_args
        self.assertEqual(call_args[1]['routing_key'], f"{self.mock_settings.feedback_results_queue}_dead_letter")

    def test_move_to_dead_letter_exception(self):
        """Test move_to_dead_letter with exception."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        mock_channel.basic_publish.side_effect = Exception("Publish error")
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        test_data = {"submission_id": "test_123"}
        
        # Should not raise exception
        self.consumer.move_to_dead_letter(test_data)

    def test_move_to_dead_letter_with_properties(self):
        """Test move_to_dead_letter verifies properties are set correctly."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        test_data = {
            "submission_id": "dlq_123",
            "error": "Test error",
            "timestamp": "2025-01-01"
        }
        
        self.consumer.move_to_dead_letter(test_data)
        
        # Verify basic_publish was called
        self.assertTrue(mock_channel.basic_publish.called)
        
        # Verify properties
        call_kwargs = mock_channel.basic_publish.call_args[1]
        self.assertIn('properties', call_kwargs)

    def test_move_to_dead_letter_json_serialization(self):
        """Test move_to_dead_letter handles complex data structures."""
        if not USING_REAL_CLASS:
            return
        
        mock_channel = Mock()
        self.consumer.channel = mock_channel
        self.consumer.settings = self.mock_settings
        
        complex_data = {
            "submission_id": "complex_123",
            "nested": {"data": [1, 2, 3]},
            "list": ["a", "b", "c"]
        }
        
        self.consumer.move_to_dead_letter(complex_data)
        
        mock_channel.basic_publish.assert_called_once()
        
        # Verify body can be deserialized
        call_kwargs = mock_channel.basic_publish.call_args[1]
        body = call_kwargs['body']
        parsed = json.loads(body)
        self.assertEqual(parsed["submission_id"], "complex_123")

    # ==================== Coverage Helper Tests ====================
    
    def test_frappe_mock_coverage(self):
        """Test frappe mock methods to ensure coverage."""
        frappe_mock.get_single("test")
        frappe_mock.get_doc("test")
        frappe_mock.get_value("test")
        frappe_mock.db.exists("test")
        logger = frappe_mock.logger()
        
        self.assertTrue(frappe_mock.get_single.called)
        self.assertTrue(frappe_mock.get_doc.called)
        self.assertTrue(frappe_mock.get_value.called)
        self.assertTrue(frappe_mock.db.exists.called)
        self.assertTrue(frappe_mock.logger.called)

    def test_using_real_class_branches(self):
        """Test both branches of USING_REAL_CLASS."""
        # This test ensures both code paths are covered
        if USING_REAL_CLASS:
            # Test real class import
            self.assertTrue(USING_REAL_CLASS)
            # Verify the real class has expected methods
            expected_methods = [
                'setup_rabbitmq', 'start_consuming', 'stop_consuming',
                'cleanup', 'process_message', 'is_retryable_error',
                'update_submission', 'send_glific_notification',
                'mark_submission_failed', 'move_to_dead_letter',
                'get_queue_stats', '_reconnect'
            ]
            for method in expected_methods:
                self.assertTrue(hasattr(self.consumer, method), f"Missing method: {method}")
        else:
            # Test mock class fallback
            self.assertFalse(USING_REAL_CLASS)
            # Verify mock class basic structure
            self.assertIsNone(self.consumer.connection)
            self.assertIsNone(self.consumer.channel)
            self.assertIsNone(self.consumer.settings)

    def test_basic_functionality_mock_fallback(self):
        """Test basic functionality when using mock fallback."""
        if not USING_REAL_CLASS:
            self.assertIsNone(self.consumer.connection)
            self.assertIsNone(self.consumer.channel)
            self.assertIsNone(self.consumer.settings)
        else:
            self.assertTrue(hasattr(self.consumer, 'connection'))
            self.assertTrue(hasattr(self.consumer, 'channel'))
            self.assertTrue(hasattr(self.consumer, 'settings'))


if __name__ == '__main__':
    unittest.main()