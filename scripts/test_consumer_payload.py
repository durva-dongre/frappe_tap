#!/usr/bin/env python3
"""
Test script to send payloads directly to the RabbitMQ consumer for testing.
Simply modify the payload dictionary below and run: python test_consumer_payload.py
"""

import sys
import json
import pika
from datetime import datetime
from pathlib import Path

# Add the apps directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))



# ============================================================================
# EDIT THE PAYLOAD BELOW TO TEST DIFFERENT DATA
# ============================================================================
PAYLOAD = {
  "submission_id": "SUB-2605020246",
  "student_id": "ST00000182",
  "assignment_id": "VAL1RB07",
  "feedback": {
    "rubric_evaluations": [
      {
        "Skill": "Content Knowledge",
        "grade_value": 1,
        "observation": "The submission meets the criterion by providing the '👍' emoji, which is listed in the 'valid_criteria' ('👍 or 👎'). A lower grade was not assigned because the submission does not meet the 'invalid_criteria', which is 'Any emoji other than 👍 or 👎'. A higher level is not available as the highest level for this criterion has been met."
      }
    ],
    "overall_feedback": "Great job on completing the Pop Art activity! It's wonderful to see that you enjoyed it by sending the thumbs-up emoji. You followed the instructions correctly for this step. Keep up the fantastic engagement in our activities!",
    "overall_feedback_translated": "पॉप आर्ट एक्टिविटी को पूरा करने पर बहुत बढ़िया काम! यह देखकर बहुत अच्छा लगा कि आपने थम्स-अप इमोजी भेजकर इसका आनंद लिया। आपने इस चरण के लिए निर्देशों का पूरी तरह से पालन किया। हमारी एक्टिविटीज़ में अपनी शानदार भागीदारी बनाए रखें!",
    "final_grade": 1.0,
    "plagiarism_output": {
      "is_plagiarized": False,
      "is_ai_generated": False,
      "match_type": "original",
      "plagiarism_source": "none",
      "similarity_score": 0.0,
      "ai_detection_source": "none",
      "ai_confidence": 0.0,
      "similar_sources": []
    },
    "strengths": [
      "cost:0.007323",
      "Feedback_LP:0.0",
      "Eval_LP:0.0"
    ],
    "areas_for_improvement": [],
    "encouragement": "",
    "translation_language": "Hindi"
  },
  "generated_at": "2026-05-03T17:16:01.149789"
}

# ============================================================================


def get_rabbitmq_settings():
    """Get RabbitMQ settings from Frappe"""
    try:
        return {
            "host": "rabbit-01.lmq.cloudamqp.com",
            "port": "5672",
            "username": "aoafhbrm",
            "password": "****",
            "virtual_host": "aoafhbrm",
            "queue": "feedback_q_local",
        }
    except Exception as e:
        print(f"Error fetching RabbitMQ settings: {e}")
        return None


def connect_to_rabbitmq(settings):
    """Establish connection to RabbitMQ"""
    try:
        credentials = pika.PlainCredentials(settings["username"], settings["password"])
        parameters = pika.ConnectionParameters(
            host=settings["host"],
            port=settings["port"],
            virtual_host=settings["virtual_host"],
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300,
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        print(f"\n✓ Connected to RabbitMQ at {settings['host']}:{settings['port']}")
        return connection, channel
    except Exception as e:
        print(f"\n✗ RabbitMQ Connection Error: {e}")
        return None, None


def send_payload(connection, channel, queue_name, payload):
    """Send a payload to RabbitMQ queue"""
    try:
        # Set up dead-letter queue infrastructure
        dlx_exchange = f"{queue_name}_dlx"
        dl_queue = f"{queue_name}_dead_letter"
        main_queue_arguments = {
            "x-dead-letter-exchange": dlx_exchange,
            "x-dead-letter-routing-key": queue_name,
        }
        
        # Declare dead-letter exchange
        channel.exchange_declare(
            exchange=dlx_exchange,
            exchange_type='direct',
            durable=True
        )
        print(f"  Declared dead letter exchange: {dlx_exchange}")
        
        # Declare dead-letter queue
        channel.queue_declare(
            queue=dl_queue,
            durable=True
        )
        print(f"  Declared dead letter queue: {dl_queue}")
        
        # Bind dead-letter queue to dead-letter exchange
        channel.queue_bind(
            exchange=dlx_exchange,
            queue=dl_queue,
            routing_key=queue_name
        )
        
        # Declare main queue with dead-letter routing
        channel.queue_declare(
            queue=queue_name,
            durable=True,
            arguments=main_queue_arguments
        )
        print(f"  Declared main queue with dead letter routing: {queue_name}")
        
        # Send message
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(payload, ensure_ascii=False),
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
            ),
        )
        print(f"\n✓ Payload sent to queue '{queue_name}'")
        print(f"  Submission ID: {payload.get('submission_id')}")
        print(f"  Student ID: {payload.get('student_id')}")
        print(f"  Assignment ID: {payload.get('assignment_id')}")
        return True
    except Exception as e:
        print(f"\n✗ Error sending payload: {e}")
        return False
    finally:
        if connection and not connection.is_closed:
            connection.close()


def main():
    # Get RabbitMQ settings
    settings = get_rabbitmq_settings()
    if not settings:
        print("\n✗ Unable to retrieve RabbitMQ settings")
        return

    print(f"\n=== RabbitMQ Consumer Test Script ===")
    print(f"Host: {settings['host']}")
    print(f"Port: {settings['port']}")
    print(f"Queue: {settings['queue']}")

    # Connect to RabbitMQ
    connection, channel = connect_to_rabbitmq(settings)
    if not connection or not channel:
        return

    try:
        # Validate required fields

        print(f"\n--- Sending Payload ---")
        print(f"Payload:\n{json.dumps(PAYLOAD, indent=2, ensure_ascii=False)}")
        send_payload(connection, channel, settings["queue"], PAYLOAD)

    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("\n✓ Disconnected from RabbitMQ")


if __name__ == "__main__":
    main()


# /home/frappe/frappe-bench/apps/tap_lms/scripts/test_consumer_payload.py