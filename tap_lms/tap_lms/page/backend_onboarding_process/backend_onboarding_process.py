import frappe
from frappe import _
import json
from frappe.utils import nowdate, nowtime, now
from tap_lms.glific_integration import create_or_get_glific_group_for_batch, add_student_to_glific_for_onboarding, get_contact_by_phone
from tap_lms.api import get_course_level




@frappe.whitelist()
def get_onboarding_batches():
    print("get_onboarding_batches called")

    # Return all draft backend onboarding batches
    return frappe.get_all("Backend Student Onboarding", 
                          filters={"status": ["in", ["Draft", "Processing", "Failed"]]},
                          fields=["name", "set_name", "upload_date", "uploaded_by", 
                                 "student_count", "processed_student_count"])

@frappe.whitelist()
def get_batch_details(batch_id):
    # Get the details of a specific batch
    batch = frappe.get_doc("Backend Student Onboarding", batch_id)
    # Only request fields that exist in the database
    students = frappe.get_all("Backend Students", 
                            filters={"parent": batch_id},
                            fields=["name", "student_name", "phone", "gender", 
                                   "batch", "course_vertical", "grade", "school",
                                   "language", "processing_status", "student_id"])
    
    # Add validation flags
    for student in students:
        student["validation"] = validate_student(student)
    
    # Get Glific group for this batch if exists
    glific_group = frappe.get_all("GlificContactGroup", 
                                filters={"backend_onboarding_set": batch_id},
                                fields=["group_id", "label"])
    
    return {
        "batch": batch,
        "students": students,
        "glific_group": glific_group[0] if glific_group else None
    }

def validate_student(student):
    validation = {}
    
    # Check for empty required fields
    required_fields = ["student_name", "phone", "school", "grade", "language", "batch"]
    for field in required_fields:
        if not student.get(field):
            validation[field] = "missing"
    
    # Check for duplicate phone numbers
    if student.get("phone"):
        existing = frappe.get_all("Student", 
                                filters={"phone": student.get("phone")},
                                fields=["name", "name1"])
        if existing:
            validation["duplicate"] = {
                "student_id": existing[0].name,
                "student_name": existing[0].name1
            }
    
    return validation

@frappe.whitelist()
def get_onboarding_stages():
    try:
        # Check if the DocType exists
        if not frappe.db.table_exists("OnboardingStage"):
            return []
            
        # Get all onboarding stages ordered by the order field
        return frappe.get_all("OnboardingStage", 
                            fields=["name", "description", "order"],
                            order_by="`order`")  # Using backticks to escape the reserved keyword
    except Exception as e:
        frappe.log_error(f"Error fetching OnboardingStage: {str(e)}")
        return []

def get_initial_stage():
    """Get the initial onboarding stage (with order=0)"""
    try:
        stages = frappe.get_all("OnboardingStage", 
                              filters={"order": 0},
                              fields=["name"])
        if stages:
            return stages[0].name
        else:
            # If no stage with order 0, get the stage with minimum order
            stages = frappe.get_all("OnboardingStage", 
                                  fields=["name", "order"],
                                  order_by="order ASC",
                                  limit=1)
            if stages:
                return stages[0].name
    except Exception as e:
        frappe.log_error(f"Error getting initial stage: {str(e)}")
    
    return None

@frappe.whitelist()
def process_batch(batch_id, use_background_job=False):
    """
    Process the batch by creating students and Glific contacts
    
    Args:
        batch_id: ID of the Backend Student Onboarding document
        use_background_job: Whether to process in the background
        
    Returns:
        If background job is used, returns the job ID
        Otherwise, returns processing results
    """
    use_background_job = json.loads(use_background_job) if isinstance(use_background_job, str) else use_background_job
    
    # Update batch status to Processing
    batch = frappe.get_doc("Backend Student Onboarding", batch_id)
    batch.status = "Processing"
    batch.save()
    
    if use_background_job:
        # Enqueue the processing job
        job = frappe.enqueue(
            process_batch_job,
            queue='long',
            timeout=1800,  # 30 minutes
            job_name=f"student_onboarding_{batch_id}",
            batch_id=batch_id
        )
        return {"job_id": job.id}
    else:
        # Process immediately
        return process_batch_job(batch_id)

def process_batch_job(batch_id):
    """Background job function to process the batch"""
    try:
        frappe.db.commit()  # Commit any pending changes before starting job
        
        batch = frappe.get_doc("Backend Student Onboarding", batch_id)
        
        # Get students to process (only pending or failed)
        students = frappe.get_all("Backend Students", 
                                filters={"parent": batch_id, "processing_status": ["in", ["Pending", "Failed"]]},
                                fields=["name"])
        
        success_count = 0
        failure_count = 0
        results = {
            "success": [],
            "failed": []
        }
        
        # Get or create Glific group for this batch
        try:
            glific_group = create_or_get_glific_group_for_batch(batch_id)
        except Exception as e:
            frappe.log_error(f"Error creating Glific group: {str(e)}", "Backend Student Onboarding")
            glific_group = None
        
        # Get initial stage
        initial_stage = get_initial_stage()
        
        # Process each student
        total_students = len(students)
        for index, student_entry in enumerate(students):
            try:
                # Update job progress (if this is a background job)
                update_job_progress(index, total_students)
                
                student = frappe.get_doc("Backend Students", student_entry.name)
                
                # 1. First, handle Glific contact creation/retrieval
                try:
                    glific_contact = process_glific_contact(student, glific_group)
                except Exception as e:
                    frappe.log_error(f"Error processing Glific contact for {student.student_name}: {str(e)}", 
                                    "Backend Student Onboarding")
                    glific_contact = None
                
                # 2. Then create/update student record
                student_doc = process_student_record(student, glific_contact, batch_id, initial_stage)
                
                # 3. Update Backend Students record
                update_backend_student_status(student, "Success", student_doc)
                
                success_count += 1
                success_data = {
                    "backend_id": student.name,
                    "student_id": student_doc.name,
                    "student_name": student_doc.name1,
                    "phone": student.phone
                }
                # Only add glific_id if it exists in the doctype
                if glific_contact and 'id' in glific_contact:
                    success_data["glific_id"] = glific_contact['id']
                
                results["success"].append(success_data)
                
                # Commit after each successful student to avoid losing progress
                frappe.db.commit()
                
            except Exception as e:
                frappe.db.rollback()  # Rollback the failed transaction
                
                failure_count += 1
                try:
                    student = frappe.get_doc("Backend Students", student_entry.name)
                    update_backend_student_status(student, "Failed", error=str(e))
                    
                    results["failed"].append({
                        "backend_id": student.name,
                        "student_name": student.student_name,
                        "error": str(e)
                    })
                    
                    frappe.db.commit()  # Commit the status update
                except Exception as inner_e:
                    # If updating the student record itself fails
                    frappe.log_error(f"Error updating failed status for student {student_entry.name}: {str(inner_e)}", 
                                    "Backend Student Onboarding")
                    
                    results["failed"].append({
                        "backend_id": student_entry.name,
                        "student_name": "Unknown",
                        "error": f"Original error: {str(e)}. Status update error: {str(inner_e)}"
                    })
        
        # Update batch status
        try:
            batch = frappe.get_doc("Backend Student Onboarding", batch_id)
            if failure_count == 0:
                batch.status = "Processed"
            elif success_count == 0:
                batch.status = "Failed"
            else:
                batch.status = "Processing" # Since "Partially Processed" might not be an allowed status value
            
            # Update processed_student_count field if it exists
            processed_count = frappe.db.count("Backend Students", 
                                            filters={"parent": batch_id, "processing_status": "Success"})
            if hasattr(batch, 'processed_student_count'):
                batch.processed_student_count = processed_count
            
            batch.save()
            frappe.db.commit()  # Final commit
        except Exception as e:
            frappe.log_error(f"Error updating batch status: {str(e)}", "Backend Student Onboarding")
        
        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results
        }
    except Exception as e:
        frappe.db.rollback()
        try:
            # Update batch status to Failed
            batch = frappe.get_doc("Backend Student Onboarding", batch_id)
            batch.status = "Failed"
            # Add processing_notes if the field exists
            if hasattr(batch, 'processing_notes'):
                # Get the field's max length
                meta = frappe.get_meta("Backend Student Onboarding")
                field = meta.get_field("processing_notes")
                max_length = field.length if field and hasattr(field, 'length') else 140
                
                batch.processing_notes = str(e)[:max_length]
            batch.save()
            frappe.db.commit()
        except:
            pass  # If this fails too, just continue
            
        frappe.log_error(f"Error in batch processing job: {str(e)}", "Backend Student Onboarding")
        raise

def update_job_progress(current, total):
    """Update the background job progress"""
    if total > 0:
        try:
            # Try without user parameter first (for older Frappe versions)
            frappe.publish_progress(
                percent=(current+1) * 100 / total,
                title=_("Processing Students"),
                description=_("Processing student {0} of {1}").format(current + 1, total)
            )
        except Exception:
            # Fall back to basic approach if publish_progress fails
            if (current+1) % 10 == 0 or (current+1) == total:  # Update every 10 items
                frappe.db.commit()
                print(f"Processed {current+1} of {total} students")

def process_glific_contact(student, glific_group):
    """
    Process Glific contact creation or retrieval
    
    Args:
        student: Backend Students document
        glific_group: Glific group information
        
    Returns:
        Glific contact information if successful, None otherwise
    """
    # Format phone number 
    phone = format_phone_number(student.phone)
    if not phone:
        raise ValueError(f"Invalid phone number format: {student.phone}")
    
    # Get school name for Glific
    school_name = ""
    if student.school:
        school_name = frappe.get_value("School", student.school, "name1") or ""
    
    # Get batch name for Glific
    batch_name = ""
    if student.batch:
        batch_name = frappe.get_value("Batch", student.batch, "name1") or ""
    
    # Get language ID for Glific from TAP Language
    language_id = None
    if student.language:
        try:
            language_id = frappe.get_value("TAP Language", student.language, "glific_language_id")
            if not language_id:
                frappe.logger().warning(f"No glific_language_id found for language {student.language}, will use default")
        except Exception as e:
            frappe.logger().warning(f"Error getting glific_language_id: {str(e)}")
    
    # Check if contact already exists in Glific
    existing_contact = get_contact_by_phone(phone)
    
    if existing_contact and 'id' in existing_contact:
        # Contact exists, add to group if needed
        if glific_group and glific_group.get("group_id"):
            from tap_lms.glific_integration import add_contact_to_group
            add_contact_to_group(existing_contact['id'], glific_group.get("group_id"))
        
        # Update fields to ensure they're current
        if student.batch or school_name:
            from tap_lms.glific_integration import update_contact_fields
            fields_to_update = {
                "buddy_name": student.student_name,
                "batch_id": student.batch
            }
            if school_name:
                fields_to_update["school"] = school_name
            
            update_contact_fields(existing_contact['id'], fields_to_update)
        
        return existing_contact
    else:
        # Create new contact and add to group, passing the language_id
        contact = add_student_to_glific_for_onboarding(
            student.student_name,
            phone,
            school_name,
            batch_name,
            glific_group.get("group_id") if glific_group else None,
            language_id  # Pass the language_id here
        )
        
        if not contact or 'id' not in contact:
            frappe.log_error(
                f"Failed to create Glific contact for {student.student_name} ({phone})",
                "Backend Student Onboarding"
            )
        
        return contact



def process_student_record(student, glific_contact, batch_id, initial_stage):
    """
    Create or update student record based on duplicate handling logic
    
    Args:
        student: Backend Students document
        glific_contact: Glific contact information
        batch_id: Backend Student Onboarding ID
        initial_stage: Initial onboarding stage
        
    Returns:
        Student document
    """
    # Check for duplicate - if phone AND name match, update existing student
    existing_student = None
    existing = frappe.get_all("Student", 
                            filters={"phone": student.phone, "name1": student.student_name},
                            fields=["name"])
    
    if existing:
        # Phone and name match - update existing student
        existing_student = frappe.get_doc("Student", existing[0].name)
        
        # Update relevant fields (careful not to overwrite existing data)
        if not existing_student.batch:
            existing_student.batch = student.batch
        
        # Add new enrollment if it doesn't already exist
        has_enrollment = False
        if existing_student.enrollment:
            for enrollment in existing_student.enrollment:
                if enrollment.batch == student.batch:
                    has_enrollment = True
                    break
        
        if not has_enrollment and student.batch:
            # Get course level using batch_skeyword if available
            course_level = None
            if hasattr(student, 'batch_skeyword') and student.batch_skeyword and student.course_vertical and student.grade:
                try:
                    # Get batch onboarding details using batch_skeyword
                    batch_onboarding = frappe.get_all(
                        "Batch onboarding",
                        filters={"batch_skeyword": student.batch_skeyword},
                        fields=["name", "kit_less"]
                    )
                    
                    if batch_onboarding:
                        kitless = batch_onboarding[0].kit_less
                        # Use existing course level selection logic
                        course_level = get_course_level(student.course_vertical, student.grade, kitless)
                        frappe.logger().info(f"Selected course level {course_level} for student {student.student_name}")
                except Exception as e:
                    frappe.log_error(f"Error selecting course level: {str(e)}", "Backend Student Onboarding")
            
            enrollment = {
                "doctype": "Enrollments",
                "batch": student.batch,
                "grade": student.grade,
                "date_joining": nowdate(),
                "school": student.school
            }
            
            # Add course level if we found one
            if course_level:
                enrollment["course"] = course_level
            
            existing_student.append("enrollment", enrollment)
        
        # Update Glific ID if we have it and student doesn't
        if glific_contact and 'id' in glific_contact and not existing_student.glific_id:
            existing_student.glific_id = glific_contact['id']
        
        existing_student.backend_onboarding = batch_id
        existing_student.save()
        student_doc = existing_student
    else:
        # Create new student
        student_doc = frappe.new_doc("Student")
        student_doc.name1 = student.student_name
        student_doc.phone = student.phone
        student_doc.gender = student.gender
        student_doc.school_id = student.school
        student_doc.grade = student.grade
        student_doc.language = student.language
        student_doc.batch = student.batch
        student_doc.backend_onboarding = batch_id
        student_doc.joined_on = nowdate()
        student_doc.status = "active"
        
        # Add Glific ID if available
        if glific_contact and 'id' in glific_contact:
            student_doc.glific_id = glific_contact['id']
        
        # Add enrollment with course level if possible
        if student.batch:
            # Get course level using batch_skeyword if available
            course_level = None
            if hasattr(student, 'batch_skeyword') and student.batch_skeyword and student.course_vertical and student.grade:
                try:
                    # Get batch onboarding details using batch_skeyword
                    batch_onboarding = frappe.get_all(
                        "Batch onboarding",
                        filters={"batch_skeyword": student.batch_skeyword},
                        fields=["name", "kit_less"]
                    )
                    
                    if batch_onboarding:
                        kitless = batch_onboarding[0].kit_less
                        # Use existing course level selection logic
                        course_level = get_course_level(student.course_vertical, student.grade, kitless)
                        frappe.logger().info(f"Selected course level {course_level} for student {student.student_name}")
                except Exception as e:
                    frappe.log_error(f"Error selecting course level: {str(e)}", "Backend Student Onboarding")
            
            enrollment = {
                "doctype": "Enrollments",
                "batch": student.batch,
                "grade": student.grade,
                "date_joining": nowdate(),
                "school": student.school
            }
            
            # Add course level if we found one
            if course_level:
                enrollment["course"] = course_level
            
            student_doc.append("enrollment", enrollment)
        
        student_doc.insert()
    
    # Initialize LearningState if it doesn't exist
    if not frappe.db.exists("LearningState", {"student": student_doc.name}):
        try:
            learning_state = frappe.new_doc("LearningState")
            learning_state.student = student_doc.name
            learning_state.insert()
        except Exception as e:
            frappe.log_error(f"Error creating LearningState for student {student_doc.name}: {str(e)}", 
                           "Backend Student Onboarding")
            # Continue without creating LearningState if there's an error
    
    # Initialize EngagementState if it doesn't exist
    if not frappe.db.exists("EngagementState", {"student": student_doc.name}):
        try:
            engagement_state = frappe.new_doc("EngagementState")
            engagement_state.student = student_doc.name
            
            # Set default values for required fields
            engagement_state.average_response_time = "0"  # Based on error, this is a required field
            engagement_state.completion_rate = "0"
            engagement_state.session_frequency = 0
            engagement_state.current_streak = 0
            engagement_state.last_activity_date = nowdate()
            engagement_state.engagement_trend = "Stable"
            engagement_state.re_engagement_attempts = "0"
            engagement_state.sentiment_analysis = "Neutral"
            
            engagement_state.insert()
        except Exception as e:
            frappe.log_error(f"Error creating EngagementState for student {student_doc.name}: {str(e)}", 
                           "Backend Student Onboarding")
            # Continue without creating EngagementState if there's an error
    
    # Create first StudentStageProgress for onboarding if it doesn't exist
    if initial_stage and not frappe.db.exists("StudentStageProgress", 
                                           {"student": student_doc.name, "stage_type": "OnboardingStage"}):
        try:
            stage_progress = frappe.new_doc("StudentStageProgress")
            stage_progress.student = student_doc.name
            stage_progress.stage_type = "OnboardingStage"
            stage_progress.stage = initial_stage
            stage_progress.status = "not_started"
            stage_progress.start_timestamp = now()
            stage_progress.insert()
        except Exception as e:
            frappe.log_error(f"Error creating StudentStageProgress for student {student_doc.name}: {str(e)}", 
                           "Backend Student Onboarding")
            # Continue without creating StudentStageProgress if there's an error
    
    return student_doc




def update_backend_student_status(student, status, student_doc=None, error=None):
    """
    Update the status of a Backend Students record
    
    Args:
        student: Backend Students document
        status: New status ("Success" or "Failed")
        student_doc: Optional Student document (for Success status)
        error: Optional error message (for Failed status)
    """
    student.processing_status = status
    
    if status == "Success" and student_doc:
        student.student_id = student_doc.name
        # If we have a glific_id field, update it
        if hasattr(student, 'glific_id') and student_doc.glific_id:
            student.glific_id = student_doc.glific_id
    
    # Handle processing_notes with proper truncation for not-null constraint
    if error and hasattr(student, 'processing_notes'):
        # Get the field's max length from metadata or default to 140
        try:
            meta = frappe.get_meta("Backend Students")
            field = meta.get_field("processing_notes")
            max_length = field.length if field and hasattr(field, 'length') else 140
        except:
            max_length = 140  # Fallback if metadata can't be accessed
        
        # Truncate error message to max length
        student.processing_notes = str(error)[:max_length]
    
    student.save()

def format_phone_number(phone):
    """Format phone number for Glific (must be 12 digits with 91 prefix for India)"""
    if not phone:
        return None
    
    phone = phone.strip().replace(' ', '')
    if len(phone) == 10:
        return f"91{phone}"
    elif len(phone) == 12 and phone.startswith('91'):
        return phone
    else:
        return None


@frappe.whitelist()
def get_job_status(job_id):
    """Get the status of a background job using compatibility methods for different Frappe versions"""
    try:
        # First try to get the job directly from the database instead of using get_doc
        result = {
            "status": "Unknown"
        }
        
        # Try different table names that might exist in different Frappe versions
        tables_to_try = ["tabBackground Job", "tabRQ Job"]
        
        for table in tables_to_try:
            # Check if table exists
            if frappe.db.table_exists(table.replace("tab", "")):
                try:
                    # Get job data directly from the table
                    job_data = frappe.db.get_value(
                        table, 
                        job_id, 
                        ["status", "progress_data", "result"], 
                        as_dict=True
                    )
                    
                    if job_data:
                        result["status"] = job_data.status
                        
                        # If job is running or queued, check progress
                        if job_data.status == "started" or job_data.status == "Started":
                            if job_data.progress_data:
                                try:
                                    progress = json.loads(job_data.progress_data)
                                    result["progress"] = progress
                                except:
                                    pass
                        
                        # If job is completed, check result
                        if job_data.status == "finished" or job_data.status == "Finished":
                            result["status"] = "Completed"
                            if job_data.result:
                                try:
                                    result["result"] = json.loads(job_data.result)
                                except:
                                    pass
                        
                        # If job failed, update status
                        if job_data.status == "failed" or job_data.status == "Failed":
                            result["status"] = "Failed"
                        
                        return result
                except Exception as e:
                    frappe.logger().warning(f"Error getting job data from {table}: {str(e)}")
                    continue
        
        # If we reach here, try using frappe's queue functions directly
        try:
            from frappe.utils.background_jobs import get_job_status as get_rq_job_status
            status = get_rq_job_status(job_id)
            if status:
                result["status"] = status
        except Exception as e:
            frappe.logger().warning(f"Error getting job status via RQ: {str(e)}")
        
        return result
    except Exception as e:
        frappe.logger().error(f"Error in get_job_status: {str(e)}")
        # Return a fallback response that won't break the UI
        return {
            "status": "Unknown",
            "message": "Unable to determine job status. The job may still be running or have completed."
        }
