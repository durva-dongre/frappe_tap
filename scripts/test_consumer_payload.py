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
  "submission_id": "IMSUB-2601280188",
  "student_id": "ST00000206",
  "assignment_id": "VA_L1_CA1-Basic",
  "feedback": {
    "rubric_evaluations": [
      {
        "Skill": "Content Knowledge",
        "grade_value": 2,
        "observation": "The creature uses basic shapes like circles and ovals but lacks clear patterns and variety."
      },
      {
        "Skill": "Creativity",
        "grade_value": 2,
        "observation": "The creature has simple features and lacks imaginative elements like magical details or unique patterns."
      }
    ],
    "strengths": [
      "Neat arrangement of shapes",
      "Good use of color contrast"
    ],
    "areas_for_improvement": [
      "Incorporate more patterns into the design",
      "Add unique features to enhance creativity"
    ],
    "encouragement": "Great start! Keep experimenting with shapes and patterns to make your creature even more magical.",
    "overall_feedback": "Your creation is neat and well-colored. To make it more magical, try adding more patterns and unique features. Keep up the creativity!",
    "overall_feedback_translated": "आपकी रचना साफ-सुथरी और अच्छी तरह से रंगी हुई है। इसे और जादुई बनाने के लिए और पैटर्न और अनोखी विशेषताएँ जोड़ें। रचनात्मकता बनाए रखें!",
    "learning_objectives_feedback": [
      "Enhance use of diverse shapes and patterns."
    ],
    "final_grade": "40",
    "grade_recommendation": 0,
    "plagiarism_output": {
      "is_plagiarized": False,
      "is_ai_generated": True,
      "match_type": "exact_duplicate",
      "plagiarism_source": "peer", #"self_cross_assignment", "self_late_resubmission"
      "similarity_score": 0.0,
      "ai_detection_source": "none",
      "ai_confidence": 0.0,
      "similar_sources": []
    },
    "translation_language": "Kannada"
  },
  "generated_at": "2026-01-30T11:15:32.212972"
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
        # Declare queue to ensure it exists
        channel.queue_declare(queue=queue_name, durable=True)
        
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
