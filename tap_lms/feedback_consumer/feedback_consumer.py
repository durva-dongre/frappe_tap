# tap_lms/tap_lms/feedback_consumer/feedback_consumer.py

import frappe
import json
import pika
import time
from datetime import datetime
from typing import Dict, Optional
from ..glific_integration import get_glific_settings, start_contact_flow

class FeedbackConsumer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.settings = None
        self.retry_count = {}  # Track retry attempts
        self.max_retries = 3
        self.retry_delays = [5, 15, 45]  # Exponential backoff in seconds

    def setup_rabbitmq(self):
        """Setup RabbitMQ connection and channel"""
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
            
            # Declare main queue
            self.channel.queue_declare(
                queue=self.settings.feedback_results_queue,
                durable=True
            )
            
            # Declare dead letter queue
            self.channel.queue_declare(
                queue=f"{self.settings.feedback_results_queue}_dead_letter",
                durable=True
            )
            
            frappe.logger().info("RabbitMQ connection established successfully")
            
        except Exception as e:
            frappe.logger().error(f"Failed to setup RabbitMQ connection: {str(e)}")
            raise

    def start_consuming(self):
        """Start consuming messages from the queue"""
        try:
            if not self.channel:
                self.setup_rabbitmq()
            
            frappe.logger().info(f"Starting to consume from queue: {self.settings.feedback_results_queue}")
            
            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(
                queue=self.settings.feedback_results_queue,
                on_message_callback=self.process_message
            )
            
            self.channel.start_consuming()
            
        except Exception as e:
            frappe.logger().error(f"Error in consumer: {str(e)}")
            if self.connection and not self.connection.is_closed:
                self.connection.close()
            raise

    def process_message(self, ch, method, properties, body):
        """Process incoming feedback message"""
        message_data = None
        try:
            message_data = json.loads(body)
            submission_id = message_data.get("submission_id")
            
            frappe.logger().info(f"Processing feedback for submission: {submission_id}")
            
            # Update ImgSubmission
            self.update_submission(message_data)
            
            # Send notification via Glific
            self.send_glific_notification(message_data)
            
            # Acknowledge message
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
            frappe.logger().info(f"Successfully processed feedback for submission: {submission_id}")
            
        except Exception as e:
            if message_data and "submission_id" in message_data:
                submission_id = message_data["submission_id"]
                retry_count = self.retry_count.get(submission_id, 0)
                
                if retry_count < self.max_retries:
                    # Increment retry count
                    self.retry_count[submission_id] = retry_count + 1
                    delay = self.retry_delays[retry_count]
                    
                    frappe.logger().warning(
                        f"Retry {retry_count + 1}/{self.max_retries} for submission {submission_id} "
                        f"after {delay} seconds. Error: {str(e)}"
                    )
                    
                    # Reject message for requeue after delay
                    time.sleep(delay)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                else:
                    # Move to dead letter queue after max retries
                    frappe.logger().error(
                        f"Max retries reached for submission {submission_id}. "
                        f"Moving to dead letter queue. Error: {str(e)}"
                    )
                    self.move_to_dead_letter(message_data)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                # Invalid message format, reject without requeue
                frappe.logger().error(f"Invalid message format: {str(e)}")
                ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)

    def update_submission(self, message_data: Dict):
        """Update ImgSubmission with feedback data"""
        try:
            submission_id = message_data["submission_id"]
            submission = frappe.get_doc("ImgSubmission", submission_id)
            
            submission.update({
                "status": "Completed",
                "grade": float(message_data.get("grade_recommendation", 0)),
                "plagiarism_result": message_data.get("plagiarism_score", 0),
                "similar_sources": json.dumps(message_data.get("similar_sources", [])),
                "generated_feedback": json.dumps(message_data["feedback"]),
                "feedback_summary": message_data.get("summary", ""),
                "overall_feedback": message_data["feedback"].get("overall_feedback", ""),
                "completed_at": datetime.now()
            })
            
            submission.save()
            frappe.db.commit()
            
            frappe.logger().info(f"Updated ImgSubmission: {submission_id}")
            
        except Exception as e:
            frappe.logger().error(f"Error updating ImgSubmission: {str(e)}")
            raise

    def send_glific_notification(self, message_data: Dict):
        """Send feedback notification via Glific"""
        try:
            submission_id = message_data["submission_id"]
            student_id = message_data["student_id"]
            overall_feedback = message_data["feedback"].get("overall_feedback", "")
            
            # Get Glific flow ID
            flow_id = frappe.get_value("Glific Flow", {"label": "feedback"}, "flow_id")
            if not flow_id:
                raise Exception("Feedback flow not configured in Glific Flow")
            
            # Prepare default results
            default_results = {
                "submission_id": submission_id,
                "feedback": overall_feedback
            }
            
            # Start Glific flow
            success = start_contact_flow(
                flow_id=flow_id,
                contact_id=student_id,  # Using student_id as Glific contact ID
                default_results=default_results
            )
            
            if not success:
                raise Exception("Failed to start Glific flow")
            
            frappe.logger().info(f"Sent Glific notification for submission: {submission_id}")
            
        except Exception as e:
            frappe.logger().error(f"Error sending Glific notification: {str(e)}")
            self.mark_submission_failed(submission_id, str(e))
            raise

    def mark_submission_failed(self, submission_id: str, error_message: str):
        """Mark submission as failed"""
        try:
            submission = frappe.get_doc("ImgSubmission", submission_id)
            submission.status = "Failed"
            submission.save()
            frappe.db.commit()
            
            frappe.logger().error(
                f"Marked submission {submission_id} as failed. Error: {error_message}"
            )
        except Exception as e:
            frappe.logger().error(f"Error marking submission as failed: {str(e)}")

    def move_to_dead_letter(self, message_data: Dict):
        """Move failed message to dead letter queue"""
        try:
            dead_letter_queue = f"{self.settings.feedback_results_queue}_dead_letter"
            
            self.channel.basic_publish(
                exchange='',
                routing_key=dead_letter_queue,
                body=json.dumps(message_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                )
            )
            
            frappe.logger().warning(
                f"Moved message for submission {message_data.get('submission_id')} "
                f"to dead letter queue"
            )
        except Exception as e:
            frappe.logger().error(f"Error moving message to dead letter queue: {str(e)}")

    def cleanup(self):
        """Clean up connections"""
        try:
            if self.connection and not self.connection.is_closed:
                self.connection.close()
                frappe.logger().info("RabbitMQ connection closed")
        except Exception as e:
            frappe.logger().error(f"Error cleaning up connections: {str(e)}")
