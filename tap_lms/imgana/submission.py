import frappe
import json
import pika
import requests
from urllib.parse import urlparse
import os


def get_rabbitmq_settings():
    """
    Fetch RabbitMQ configuration from the RabbitMQ Settings DocType.
    Returns a dict with connection parameters.
    """
    settings = frappe.get_single("RabbitMQ Settings")
    return {
        'host': settings.host,
        'port': int(settings.port),
        'virtual_host': settings.virtual_host,
        'username': settings.username,
        'password': settings.get_password('password'),
        'queue': settings.submission_queue
    }


def download_and_save_image(img_url, submission_name):
    """
    Download image from external URL and save to Frappe's file system.
    Returns the new public URL.
    """
    try:
        # Download the image
        response = requests.get(img_url, timeout=30)
        response.raise_for_status()
        
        # Get the file extension from URL or content-type
        parsed_url = urlparse(img_url)
        original_filename = os.path.basename(parsed_url.path)
        
        # If no extension in URL, try to get from content-type
        if '.' not in original_filename:
            content_type = response.headers.get('content-type', '')
            ext_map = {
                'image/jpeg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'image/bmp': '.bmp'
            }
            ext = ext_map.get(content_type.split(';')[0], '.jpg')
            original_filename = f"image{ext}"
        
        # Create a unique filename using submission name
        new_filename = f"{submission_name}_{original_filename}"
        
        # Save the file using Frappe's file handling
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": new_filename,
            "attached_to_doctype": "ImgSubmission",
            "attached_to_name": submission_name,
            "is_private": 0,  # Public file
            "content": response.content
        })
        file_doc.save(ignore_permissions=True)
        
        # Get the public URL
        site_url = frappe.utils.get_url()
        public_url = f"{site_url}{file_doc.file_url}"
        
        frappe.logger("submission").info(
            f"Image saved: {img_url} -> {public_url}"
        )
        
        return public_url, file_doc.file_url
        
    except requests.exceptions.RequestException as e:
        frappe.logger("submission").error(f"Failed to download image from {img_url}: {str(e)}")
        raise frappe.ValidationError(f"Failed to download image: {str(e)}")
    except Exception as e:
        frappe.logger("submission").error(f"Failed to save image: {str(e)}")
        raise


@frappe.whitelist(allow_guest=True)
def submit_artwork(api_key, assign_id, student_id, img_url):
    # Authenticate the API request using the provided api_key
    api_key_doc = frappe.db.get_value("API Key", {"key": api_key, "enabled": 1}, ["user"], as_dict=True)
    if not api_key_doc:
        frappe.throw("Invalid API key")

    # Switch to the user associated with the API key
    frappe.set_user(api_key_doc.user)

    try:
        # Create a new submission first (to get the submission name)
        submission = frappe.new_doc("ImgSubmission")
        submission.assign_id = assign_id
        submission.student_id = student_id
        submission.img_url = img_url  # Store original URL initially
        submission.status = "Pending"
        submission.insert()
        
        # Download and save the image, get new public URL
        public_url, file_url = download_and_save_image(img_url, submission.name)
        
        # Update the submission with the new local file URL
        submission.img_url = public_url
        submission.save()
        
        frappe.db.commit()

        # Log for debugging
        frappe.logger("submission").debug(
            f"Inserted submission: assign_id={submission.assign_id}, "
            f"student_id={submission.student_id}, "
            f"original_url={img_url}, "
            f"public_url={public_url}"
        )

        # Send the submission details to RabbitMQ with the NEW public URL
        enqueue_submission(submission.name)

        return {
            "message": "Submission received",
            "submission_id": submission.name,
            "image_url": public_url
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.logger("submission").error(f"Error in submit_artwork: {str(e)}")
        frappe.throw(f"Failed to process submission: {str(e)}")

    finally:
        # Switch back to the original user
        frappe.set_user("Administrator")


def enqueue_submission(submission_id):
    submission = frappe.get_doc("ImgSubmission", submission_id)
    
    # The img_url now contains the NEW public URL (saved locally)
    payload = {
        "submission_id": submission.name,
        "assign_id": submission.assign_id,
        "student_id": submission.student_id,
        "img_url": submission.img_url
    }

    # Get RabbitMQ settings from DocType
    rabbitmq_config = get_rabbitmq_settings()

    # Establish a connection to RabbitMQ
    credentials = pika.PlainCredentials(
        rabbitmq_config['username'], 
        rabbitmq_config['password']
    )
    parameters = pika.ConnectionParameters(
        rabbitmq_config['host'],
        rabbitmq_config['port'],
        rabbitmq_config['virtual_host'],
        credentials
    )
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # Declare the queue
    channel.queue_declare(queue=rabbitmq_config['queue'])

    # Publish the message to the queue
    channel.basic_publish(
        exchange='',
        routing_key=rabbitmq_config['queue'],
        body=json.dumps(payload)
    )

    # Close the connection
    connection.close()
    
    frappe.logger("submission").info(
        f"Enqueued submission {submission_id} with img_url: {submission.img_url}"
    )


@frappe.whitelist(allow_guest=True)
def img_feedback(api_key, submission_id):
    # Authenticate the API request using the provided api_key
    api_key_doc = frappe.db.get_value("API Key", {"key": api_key, "enabled": 1}, ["user"], as_dict=True)
    if not api_key_doc:
        frappe.throw("Invalid API key")

    # Switch to the user associated with the API key
    frappe.set_user(api_key_doc.user)

    try:
        # Get the submission document
        submission = frappe.get_doc("ImgSubmission", submission_id)
        
        # Prepare the response based on status
        if submission.status == "Completed":
            response = {
                "status": submission.status,
                "overall_feedback": submission.overall_feedback
            }
        else:
            response = {
                "status": submission.status
            }
        
        return response

    except frappe.DoesNotExistError:
        return {"error": "Submission not found"}
    
    except Exception as e:
        frappe.log_error(f"Error checking submission status: {str(e)}", "Submission Status Error")
        return {"error": "An error occurred while checking submission status"}

    finally:
        # Switch back to the original user
        frappe.set_user("Administrator")


@frappe.whitelist()
def get_assignment_context(assignment_id, student_id=None):
    """Get complete assignment context for RAG service"""
    try:
        assignment = frappe.get_doc("Assignment", assignment_id)
        
        context = {
            "assignment": {
                "name": assignment.assignment_name,
                "description": assignment.description,
                "type": assignment.assignment_type,
                "subject": assignment.subject,
                "submission_guidelines": assignment.submission_guidelines,
                "reference_image": assignment.reference_image,
                "max_score": assignment.max_score
            },
            "learning_objectives": [
                {
                    "objective": obj.learning_objective,
                    "description": frappe.db.get_value(
                        "Learning Objective",
                        obj.learning_objective,
                        "description"
                    )
                }
                for obj in assignment.learning_objectives
            ]
        }
        
        # Add student context if provided
        if student_id:
            student = frappe.get_doc("Student", student_id)
            context["student"] = {
                "grade": student.grade,
                "level": student.level,
                "language": student.language
            }
        
        # Add custom feedback prompt if enabled
        if assignment.enable_auto_feedback and assignment.feedback_prompt:
            context["feedback_prompt"] = assignment.feedback_prompt
            
        return context
        
    except Exception as e:
        frappe.log_error(
            f"Error getting assignment context: {str(e)}",
            "RAG Context Error"
        )
        return None
