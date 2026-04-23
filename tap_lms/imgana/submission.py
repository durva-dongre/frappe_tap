import frappe
import json
import pika
import base64
from tap_lms.imgana.gcs_client import upload_to_gcs


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

def process_submission_async(submission_id, img_url):
    """
    Background job that uploads the submission to GCS and enqueues it for processing.
    """
    try:
        submission = frappe.get_doc("ImgSubmission", submission_id)

        public_url = upload_to_gcs(img_url, submission.name)

        submission.img_url = public_url
        submission.status = "Processing"
        submission.upload_error_log = None
        submission.save(ignore_permissions=True)
        frappe.db.commit()

        frappe.logger("submission").debug(
            f"Submission prepared for processing: assign_id={submission.assign_id}, "
            f"student_id={submission.student_id}, "
            f"original_url={img_url}, "
            f"gcs_url={public_url}"
        )

        enqueue_submission(submission.name)

    except Exception as e:
        frappe.db.rollback()
        error_message = str(e)
        frappe.logger("submission").error(
            f"Error in background processing for submission {submission_id}: {error_message}"
        )

        try:
            submission = frappe.get_doc("ImgSubmission", submission_id)
            submission.status = "Failed"
            submission.upload_error_log = frappe.get_traceback()[:5000]
            submission.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as log_error:
            frappe.logger("submission").error(
                f"Failed to update submission {submission_id} after background error: {str(log_error)}"
            )


@frappe.whitelist(allow_guest=True)
def submit_artwork_internal(api_key, assign_id, name1, glific_id, img_url):
    """
    API endpoint to submit artwork.
    Downloads image, uploads to GCS, creates submission, and enqueues to RabbitMQ.
    """
    # Authenticate the API request using the provided api_key
    api_key_doc = frappe.db.get_value("API Key", {"key": api_key, "enabled": 1}, ["user"], as_dict=True)
    if not api_key_doc:
        frappe.throw("Invalid API key")

    # Switch to the user associated with the API key
    frappe.set_user(api_key_doc.user)
    
    student_id = "ST00000206"

    try:
        # Create a new submission first (to get the submission name)
        submission = frappe.new_doc("ImgSubmission")
        submission.assign_id = assign_id
        submission.student_id = student_id
        submission.img_url = img_url  # Store original URL initially
        submission.status = "Pending"
        submission.insert()
        frappe.db.commit()
        frappe.enqueue(
            process_submission_async,
            queue="long",
            timeout=600,
            submission_id=submission.name,
            img_url=img_url
        )

        return {
            "message": "Submission received",
            "submission_id": submission.name,
            "student_id": student_id
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.logger("submission").error(f"Error in submit_artwork: {str(e)}")
        frappe.throw(f"Failed to process submission: {str(e)}")

    finally:
        # Switch back to the original user
        frappe.set_user("Administrator")


@frappe.whitelist(allow_guest=True)
def submit_artwork(api_key, assign_id, name1, glific_id, img_url):
    """
    API endpoint to submit artwork.
    Downloads image, uploads to GCS, creates submission, and enqueues to RabbitMQ.
    """
    # Authenticate the API request using the provided api_key
    api_key_doc = frappe.db.get_value("API Key", {"key": api_key, "enabled": 1}, ["user"], as_dict=True)
    if not api_key_doc:
        frappe.throw("Invalid API key")

    # Switch to the user associated with the API key
    frappe.set_user(api_key_doc.user)
    
    # Get student document
    student = frappe.get_doc(
                    "Student",
                    {
                        "name1": name1,
                        "glific_id": glific_id
                    },
                    limit=1
                )
    if not student:
        frappe.throw("Student not found with provided name and glific_id")
    student_id = student.name

    try:
        # Create a new submission first (to get the submission name)
        submission = frappe.new_doc("ImgSubmission")
        submission.assign_id = assign_id
        submission.student_id = student_id
        submission.img_url = img_url  # Store original URL initially
        submission.status = "Pending"
        submission.insert()
        frappe.db.commit()
        frappe.enqueue(
            process_submission_async,
            queue="long",
            timeout=600,
            submission_id=submission.name,
            img_url=img_url
        )

        return {
            "message": "Submission received",
            "submission_id": submission.name,
            "student_id": student_id
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.logger("submission").error(f"Error in submit_artwork: {str(e)}")
        frappe.throw(f"Failed to process submission: {str(e)}")

    finally:
        # Switch back to the original user
        frappe.set_user("Administrator")


def enqueue_submission(submission_id):
    """
    Send submission details to RabbitMQ queue.
    The img_url now contains the GCS public URL.
    """
    try:
        submission = frappe.get_doc("ImgSubmission", submission_id)
        
        # Payload with GCS public URL
        payload = {
            "submission_id": submission.name,
            "assign_id": submission.assign_id,
            "student_id": submission.student_id,
            "img_url": submission.img_url,  # This is now the GCS public URL
            # Optional: Add metadata for better detection
            "created_at": str(submission.created_at)
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
        try:
            # First try passive declaration to check if queue exists
            channel.queue_declare(queue=rabbitmq_config['queue'],durable=True,passive=True)
        except Exception:
            # If it doesn't exist, declare it
            channel.queue_declare(queue=rabbitmq_config['queue'], durable=True)


        # Publish the message to the queue
        channel.basic_publish(
            exchange='',
            routing_key=rabbitmq_config['queue'],
            body=json.dumps(payload)
        )

        # Close the connection
        connection.close()
        
        frappe.logger("submission").info(
            f"Enqueued submission {submission_id} with GCS URL: {submission.img_url}"
        )
    except Exception as e:
        frappe.logger("submission").error(f"Failed to enqueue submission {submission_id}: {str(e)}")
        raise frappe.ValidationError(f"Failed to enqueue submission: {str(e)}")


@frappe.whitelist(allow_guest=True)
def img_feedback(api_key, submission_id):
    """
    API endpoint to get feedback for a submission.
    """
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
                "overall_feedback": submission.overall_feedback,
                "overall_feedback_translated" : submission.overall_feedback_translated,
                "audio_feedback_url": submission.audio_feedback_url,
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
        images = []
        for row in assignment.reference_images:
            file_url = row.image
            file_doc = frappe.get_doc("File", {"file_url": file_url})

            file_path = file_doc.get_full_path()
            with open(file_path, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')
            images.append({
                'name': file_doc.file_name,
                'content_type': 'image/jpeg',
                'content': content  # base64 encoded
            })

        rubrics = {}
        rubric_grades = assignment.get('rubric_grades', [])

        # Process each rubric grade entry
        for grade in rubric_grades:
            skill_name = grade.get('skill_name')
            if skill_name not in rubrics:
                rubrics[skill_name] = []
            # Create the grade entry with only grade_value and grade_description
            grade_entry = {
                'grade_value': grade.get('grade_value'),
                'grade_description': grade.get('grade_description')
            }
            rubrics[skill_name].append(grade_entry)


        context = {
            "assignment": {
                "name": assignment.assignment_name,
                "description": assignment.description,
                "assignment_type": assignment.assignment_type, 
                "activity_type": assignment.activity_type,
                "course_vertical": assignment.course_vertical,
                "submission_guidelines": assignment.submission_guidelines,
                "reference_images": images,
                "max_score": assignment.max_score,
                "rubrics": rubrics
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


@frappe.whitelist()
def get_student_details(student_id):
    """Get student grade level and language details"""
    try:
        student = frappe.get_doc("Student", student_id)
                    
        print(student)
        
        if not student:
            frappe.log_error(
                f"Student {student_id} not found",
                "Student Details Error"
            )
            return None

            
        
        return {
            "student_id": student.name,
            "grade": student.grade,
            "level": student.level,
            "language": student.language
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error getting student details: {str(e)}",
            "Student Details Error"
        )
        print(e)
        return None
