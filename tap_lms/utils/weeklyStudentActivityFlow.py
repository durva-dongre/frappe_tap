# Student Weekly Activity Automation
# File: tap_lms/utils/student_weekly_activity.py
#
# This module provides functions for:
# 1. get_weekly_students() - Creates a weekly snapshot of eligible students with their batch assignments
# 2. trigger_student_weekly_activity() - Triggers Glific flows for each student in the weekly snapshot
#
# Scheduled to run weekly (e.g., Monday morning IST)

import frappe
from frappe import _
from frappe.utils import now_datetime, getdate, add_days, get_datetime
from datetime import datetime, timedelta
import json
import traceback

from tap_lms.glific_integration import (
    get_glific_settings,
    get_glific_auth_headers,
    get_contact_by_phone,
    start_contact_flow
)


def get_current_week_dates():
    """
    Get the Monday and Sunday of the current week.
    
    Returns:
        tuple: (week_start_date, week_end_date) as date objects
    """
    today = getdate()
    # Calculate days since Monday (Monday is 0)
    days_since_monday = today.weekday()
    week_start_date = add_days(today, -days_since_monday)
    week_end_date = add_days(week_start_date, 6)
    return week_start_date, week_end_date


def calculate_current_week_no(regular_activity_start_date, week_start_date):
    """
    Calculate the current week number of the activity program.
    
    Formula: days_diff = (week_start_date - regular_activity_start_date).days
             current_week_no = (days_diff // 7) + 1
    
    Args:
        regular_activity_start_date: Date when regular activities started for the batch
        week_start_date: Monday of the current week
        
    Returns:
        int: Week number (1-indexed)
    """
    if not regular_activity_start_date:
        return None
    
    regular_activity_start_date = getdate(regular_activity_start_date)
    week_start_date = getdate(week_start_date)
    
    days_diff = (week_start_date - regular_activity_start_date).days
    
    # Only return positive week numbers (activity has started)
    if days_diff < 0:
        return None
    
    current_week_no = (days_diff // 7) + 1
    return current_week_no


def format_phone_for_glific(phone):
    """
    Format phone number for Glific API lookup.
    
    Args:
        phone: Phone number string
        
    Returns:
        str: Formatted phone number with 91 prefix, or None if invalid
    """
    if not phone:
        return None
    
    phone = str(phone).strip().replace(' ', '').replace('-', '')
    
    if len(phone) == 10 and phone.isdigit():
        return f"91{phone}"
    elif len(phone) == 12 and phone.startswith('91') and phone.isdigit():
        return phone
    elif len(phone) == 11 and phone.startswith('0'):
        return f"91{phone[1:]}"
    else:
        return phone  # Return as-is, might work


def get_latest_active_enrollment_for_student(student_id):
    """
    Find the latest active enrollment for a student with an active batch that has regular activities started.
    
    Selection criteria:
    - Enrollment belongs to the student (from child table)
    - Enrollment status is active (if status field exists)
    - Batch is active
    - Batch has regular_activity_start_date set
    - Regular activities have started (regular_activity_start_date is on or before current week)
    - Select the enrollment with latest regular_activity_start_date
    
    Args:
        student_id: Student ID
        
    Returns:
        dict: Enrollment info with batch details, or None if not found
    """
    if not student_id:
        return None
    
    # Get current week dates
    week_start_date, week_end_date = get_current_week_dates()
    
    # Get the student document with its enrollment child table
    try:
        student = frappe.get_doc("Student", student_id)
    except frappe.DoesNotExistError:
        frappe.logger().error(f"Student {student_id} not found")
        return None
    
    # Check if student has enrollment child table
    if not hasattr(student, 'enrollment') or not student.enrollment:
        frappe.logger().debug(f"No enrollment found for student {student_id}")
        return None
    
    eligible_enrollment = None
    latest_activity_start = None
    
    # Find the enrollment with active batch and latest regular_activity_start_date
    for enrollment in student.enrollment:
        # Check if date_joining exists and student has joined
        if not enrollment.date_joining:
            continue
        
        # Check if student has already joined (enrollment date is on or before current week)
        enrollment_date = getdate(enrollment.date_joining)
        if enrollment_date > week_end_date:
            continue
        
        # Check if batch field exists
        if not enrollment.batch:
            continue
        
        # Uncomment if you have a status field in enrollment child table
        # if hasattr(enrollment, 'status') and enrollment.status != "Active":
        #     continue
        
        # Get batch details
        try:
            batch = frappe.get_doc("Batch", enrollment.batch)
        except frappe.DoesNotExistError:
            frappe.logger().warning(f"Batch {enrollment.batch} not found for student {student_id}")
            continue
        
        # Check if batch is active
        if not batch.active:
            continue
        
        # Check if regular_activity_start_date is set
        if not batch.regular_activity_start_date:
            continue
        
        activity_start = getdate(batch.regular_activity_start_date)
        
        # Check if regular activities have started (start date is on or before current week)
        if activity_start > week_end_date:
            continue
        
        # Select the enrollment with the latest regular_activity_start_date
        if latest_activity_start is None or activity_start > latest_activity_start:
            latest_activity_start = activity_start
            
            # Get batch onboarding details if needed
            batch_onboarding = frappe.db.get_value(
                "Batch onboarding",
                {"batch": enrollment.batch},
                ["name", "batch_skeyword", "school"],
                as_dict=True
            )
            
            eligible_enrollment = {
                "enrollment": enrollment.name,  # Child table row name
                "enrollment_idx": enrollment.idx,  # Row index in child table
                "batch": enrollment.batch,
                "batch_keyword": batch_onboarding.get("batch_skeyword") if batch_onboarding else "",
                "school": batch_onboarding.get("school") if batch_onboarding else "",
                "date_joining": enrollment.date_joining,
                "regular_activity_start_date": batch.regular_activity_start_date,
                "batch_name": batch.name1,
                "batch_onboarding": batch_onboarding.get("name") if batch_onboarding else None
            }
    
    return eligible_enrollment


@frappe.whitelist()
def get_weekly_students():
    """
    Create a weekly snapshot of all eligible students and their batch enrollment.
    
    This function:
    1. Identifies the current week window (Monday to Sunday)
    2. Fetches all students
    3. For each student, finds their latest active enrollment with an active batch
    4. Checks if batch has regular_activity_start_date and activities have started
    5. Creates a Weekly Student Flow document with all eligible students
    
    Returns:
        dict: Result with status, message, and document name if successful
    """
    try:
        frappe.logger().info("Starting get_weekly_students()")
        
        # Get current week dates
        week_start_date, week_end_date = get_current_week_dates()
        
        frappe.logger().info(f"Week window: {week_start_date} to {week_end_date}")
        
        # Convert dates to strings for database query
        week_start_str = str(week_start_date)
        week_end_str = str(week_end_date)
        
        # Check if a document already exists for this week
        existing_doc = frappe.get_all(
            "Weekly Student Flow",
            filters={
                "week_start_date": week_start_str,
                "week_end_date": week_end_str
            },
            fields=["name"]
        )
        
        if existing_doc:
            frappe.logger().info(f"Weekly Student Flow already exists for this week: {existing_doc[0].name}")
            return {
                "status": "exists",
                "message": f"Weekly Student Flow already exists for this week",
                "document_name": existing_doc[0].name
            }
        
        # Fetch all students
        # Adjust field names according to your Student doctype
        students = frappe.get_all(
            "Student",
            filters={},  # Add filters if needed
            fields=["name", "name1", "phone", "glific_id"]
        )
        
        frappe.logger().info(f"Found {len(students)} students")
        
        if not students:
            return {
                "status": "no_students",
                "message": "No students found"
            }
        
        # Create Weekly Student Flow document
        weekly_flow = frappe.new_doc("Weekly Student Flow")
        weekly_flow.week_start_date = week_start_date
        weekly_flow.week_end_date = week_end_date
        weekly_flow.status = "Draft"
        weekly_flow.created_at = now_datetime()
        
        eligible_count = 0
        skipped_count = 0
        
        # Process each student
        for student in students:
            #print(f"Processing student: {student.name}")
            # Find latest active enrollment for this student
            enrollment_info = get_latest_active_enrollment_for_student(student.name)
            #print(f"Enrollment info: {enrollment_info}")
            if not enrollment_info:
                skipped_count += 1
                frappe.logger().debug(f"No active enrollment with active batch for student {student.name}")
                continue
            
            # Calculate current week number based on regular_activity_start_date
            current_week_no = calculate_current_week_no(
                enrollment_info["regular_activity_start_date"],
                week_start_date
            )
            
            if not current_week_no:
                skipped_count += 1
                frappe.logger().debug(f"Could not calculate week number for student {student.name}")
                continue
            
            # Build student name
            student_name = f"{student.name1 or ''} {student.name1 or ''}".strip()
            
            # Add student to child table
            weekly_flow.append("students", {
                "student": student.name,
                "student_name": student_name,
                "phone_number": student.phone,
                "glific_id": student.glific_id,
                #"enrollment": enrollment_info["enrollment"],
                "batch": enrollment_info["batch"],
                "batch_keyword": enrollment_info["batch_keyword"],
                "date_joining": enrollment_info["date_joining"],
                "regular_activity_start_date": enrollment_info["regular_activity_start_date"],
                "current_week_no": current_week_no,
                "flow_trigger_status": "Pending"
            })
            
            eligible_count += 1
        
        frappe.logger().info(f"Eligible students: {eligible_count}, Skipped: {skipped_count}")
        
        if eligible_count == 0:
            return {
                "status": "no_eligible_students",
                "message": "No eligible students found for this week",
                "total_students": len(students),
                "skipped": skipped_count
            }
        
        # Insert the document
        weekly_flow.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info(f"Created Weekly Student Flow: {weekly_flow.name}")
        
        return {
            "status": "success",
            "message": f"Weekly Student Flow created successfully",
            "document_name": weekly_flow.name,
            "week_start_date": week_start_str,
            "week_end_date": week_end_str,
            "eligible_students": eligible_count,
            "skipped_students": skipped_count,
            "total_students": len(students)
        }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        frappe.log_error(
            message=f"Error in get_weekly_students: {str(e)}\n{error_traceback}",
            title="Get Weekly Students Error"
        )
        frappe.db.rollback()
        return {
            "status": "error",
            "message": str(e)
        }

def get_student_activity_flow_id():
    """
    Get the Glific flow ID for student weekly activity.
    
    First checks Glific Settings for a configured student_activity_flow_id,
    then falls back to looking up "Student Weekly Activity Flow" in Glific Flow doctype.
    
    Returns:
        str: Flow ID or None if not configured
    """
    # Try to get from Glific Settings
    settings = frappe.get_doc("Glific Settings")
    if hasattr(settings, 'student_activity_flow_id') and settings.student_activity_flow_id:
        return settings.student_activity_flow_id
    
    # Fallback: Look up in Glific Flow doctype by label
    flow = frappe.db.get_value(
        "Glific Flow",
        {"label": "Student Weekly Activity Flow"},
        "flow_id"
    )
    
    return flow


def resolve_glific_id(student_row):
    """
    Resolve Glific contact ID for a student.
    
    If glific_id is already set, return it.
    Otherwise, try to look up via phone number.
    
    Args:
        student_row: WeeklyStudents child row
        
    Returns:
        str: Glific contact ID or None
    """
    # If glific_id is already available
    if student_row.glific_id:
        return student_row.glific_id
    
    # Try to look up by phone number
    if not student_row.phone_number:
        return None
    
    formatted_phone = format_phone_for_glific(student_row.phone_number)
    if not formatted_phone:
        return None
    
    try:
        contact = get_contact_by_phone(formatted_phone)
        if contact and contact.get('id'):
            # Update the student record with the resolved glific_id
            frappe.db.set_value("Student", student_row.student, "glific_id", contact['id'])
            return contact['id']
    except Exception as e:
        frappe.logger().error(f"Error looking up Glific contact for {student_row.student}: {str(e)}")
    
    return None


@frappe.whitelist()
def trigger_student_weekly_activity(weekly_flow_name=None):
    """
    Trigger Glific flows for students in the current week'sWeekly Student Flow.
    
    This function:
    1. Finds the current week'sWeekly Student Flow document (or uses provided name)
    2. For each student row with Pending status:
       - Resolves glific_contact_id if missing (via Glific lookup by phone)
       - Calls Glific Start Flow API
       - Updates flow_trigger_status to Success/Failed
       - Updates flow_triggered_at timestamp
       - Logs any errors
    
    Args:
        weekly_flow_name: Optional specificWeekly Student Flow document name
        
    Returns:
        dict: Result with counts of success/failed triggers
    """
    try:
        frappe.logger().info(f"Starting trigger_student_weekly_activity(weekly_flow_name={weekly_flow_name})")
        
        # Find theWeekly Student Flow document
        if weekly_flow_name:
            weekly_flow = frappe.get_doc("Weekly Student Flow", weekly_flow_name)
        else:
            # Get current week's document
            week_start_date, week_end_date = get_current_week_dates()
            
            weekly_flows = frappe.get_all(
                "Weekly Student Flow",
                filters={
                    "week_start_date": week_start_date,
                    "week_end_date": week_end_date
                },
                fields=["name"]
            )
            
            if not weekly_flows:
                return {
                    "status": "not_found",
                    "message": f"NoWeekly Student Flow found for week {week_start_date} to {week_end_date}"
                }
            
            weekly_flow = frappe.get_doc("Weekly Student Flow", weekly_flows[0].name)
        
        frappe.logger().info(f"ProcessingWeekly Student Flow: {weekly_flow.name}")
        
        # Get the flow ID for student activity
        flow_id = get_student_activity_flow_id()
        
        if not flow_id:
            error_msg = "Student activity flow ID not configured in Glific Settings or Glific Flow"
            frappe.log_error(message=error_msg, title="Student Activity Flow Error")
            
            # Update status to Failed
            weekly_flow.status = "Failed"
            weekly_flow.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "status": "error",
                "message": error_msg
            }
        
        frappe.logger().info(f"Using flow_id: {flow_id}")
        
        # Update status to Processing
        weekly_flow.status = "Processing"
        weekly_flow.save(ignore_permissions=True)
        frappe.db.commit()
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Process each student row
        for student_row in weekly_flow.students:
            # Skip if already processed
            if student_row.flow_trigger_status in ["Success", "Failed"]:
                skipped_count += 1
                continue
            
            current_time = now_datetime()
            
            try:
                # Resolve Glific ID
                glific_id = resolve_glific_id(student_row)
                
                if not glific_id:
                    student_row.flow_trigger_status = "Failed"
                    student_row.flow_triggered_at = current_time
                    student_row.error_log = "Glific contact ID not found - student does not have glific_id and phone lookup failed"
                    failed_count += 1
                    frappe.logger().warning(f"No Glific ID for student {student_row.student}")
                    continue
                
                # Update glific_id in the row if it was resolved
                if not student_row.glific_id:
                    student_row.glific_id = glific_id
                
                # Prepare default_results for Glific flow
                default_results = {
                    "batch_keyword": student_row.batch_keyword or "",
                    "current_week_no": student_row.current_week_no or 0,
                    "student_name": student_row.student_name or "",
                    "student_id": student_row.student or "",
                    "enrollment_id": student_row.enrollment or "",
                    "batch_id": student_row.batch or "",
                    "date_joining": str(student_row.date_joining) if student_row.date_joining else "",
                    "regular_activity_start_date": str(student_row.regular_activity_start_date) if student_row.regular_activity_start_date else "",
                    "week_start_date": str(weekly_flow.week_start_date),
                    "week_end_date": str(weekly_flow.week_end_date)
                }
                
                frappe.logger().debug(f"Triggering flow for student {student_row.student}, glific_id: {glific_id}")
                
                # Call Glific Start Flow API
                success = start_contact_flow(flow_id, glific_id, default_results)
                
                if success:
                    student_row.flow_trigger_status = "Success"
                    student_row.flow_triggered_at = current_time
                    student_row.error_log = None
                    success_count += 1
                    frappe.logger().info(f"Flow triggered successfully for student {student_row.student}")
                else:
                    student_row.flow_trigger_status = "Failed"
                    student_row.flow_triggered_at = current_time
                    student_row.error_log = "Glific API returned failure - flow could not be started"
                    failed_count += 1
                    frappe.logger().error(f"Flow trigger failed for student {student_row.student}")
                    
            except Exception as e:
                error_msg = str(e)
                student_row.flow_trigger_status = "Failed"
                student_row.flow_triggered_at = current_time
                student_row.error_log = f"Exception occurred: {error_msg}"
                failed_count += 1
                frappe.logger().error(f"Error triggering flow for student {student_row.student}: {error_msg}")
        
        # UpdateWeekly Student Flow status
        weekly_flow.status = "Completed"
        weekly_flow.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info(f"Completed trigger_student_weekly_activity: Success={success_count}, Failed={failed_count}, Skipped={skipped_count}")
        
        return {
            "status": "success",
            "message": "Student weekly activity flows triggered",
            "document_name": weekly_flow.name,
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "total_students": len(weekly_flow.students)
        }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        frappe.log_error(
            message=f"Error in trigger_student_weekly_activity: {str(e)}\n{error_traceback}",
            title="Trigger Student Weekly Activity Error"
        )
        
        # Try to update status to Failed if we have the document
        try:
            if 'weekly_flow' in locals() and weekly_flow:
                weekly_flow.status = "Failed"
                weekly_flow.save(ignore_permissions=True)
                frappe.db.commit()
        except:
            pass
        
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def run_weekly_student_activity_automation():
    """
    Main entry point for the weekly scheduled job.
    
    This function:
    1. Calls get_weekly_students() to create the weekly snapshot
    2. If successful, calls trigger_student_weekly_activity() to trigger flows
    
    This should be scheduled to run weekly (e.g., Monday morning IST).
    
    Returns:
        dict: Combined result of both operations
    """
    try:
        frappe.logger().info("Starting weekly student activity automation")
        
        # Step 1: Create weekly snapshot
        snapshot_result = get_weekly_students()
        
        if snapshot_result.get("status") == "error":
            return {
                "status": "error",
                "step": "get_weekly_students",
                "message": snapshot_result.get("message")
            }
        
        if snapshot_result.get("status") == "no_students":
            return {
                "status": "no_students",
                "message": "No students found"
            }
        
        if snapshot_result.get("status") == "no_eligible_students":
            return {
                "status": "no_eligible_students",
                "message": "No eligible students for this week"
            }
        
        # Get the document name (either new or existing)
        document_name = snapshot_result.get("document_name")
        
        # Step 2: Trigger flows
        trigger_result = trigger_student_weekly_activity(document_name)
        
        return {
            "status": trigger_result.get("status"),
            "message": "Weekly student activity automation completed",
            "snapshot_result": snapshot_result,
            "trigger_result": trigger_result
        }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        frappe.log_error(
            message=f"Error in weekly student activity automation: {str(e)}\n{error_traceback}",
            title="Weekly Student Activity Automation Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }


# Utility function to manually re-trigger failed flows
@frappe.whitelist()
def retry_failed_flows(weekly_flow_name):
    """
    Retry triggering flows for students that previously failed.
    
    Args:
        weekly_flow_name: Name of theWeekly Student Flow document
        
    Returns:
        dict: Result with counts of retried flows
    """
    try:
        weekly_flow = frappe.get_doc("Weekly Student Flow", weekly_flow_name)
        
        # Reset failed rows to Pending
        reset_count = 0
        for student_row in weekly_flow.students:
            if student_row.flow_trigger_status == "Failed":
                student_row.flow_trigger_status = "Pending"
                student_row.error_log = None
                reset_count += 1
        
        if reset_count == 0:
            return {
                "status": "no_failures",
                "message": "No failed flows to retry"
            }
        
        weekly_flow.status = "Draft"
        weekly_flow.save(ignore_permissions=True)
        frappe.db.commit()
        
        # Trigger flows again
        return trigger_student_weekly_activity(weekly_flow_name)
        
    except Exception as e:
        frappe.log_error(
            message=f"Error in retry_failed_flows: {str(e)}",
            title="Retry Failed Flows Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }