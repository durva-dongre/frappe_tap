# Teacher Weekly Activity Automation
# File: tap_lms/utils/teacher_weekly_activity.py
#
# This module provides functions for:
# 1. get_weekly_teachers() - Creates a weekly snapshot of eligible teachers with their batch assignments
# 2. trigger_teacher_weekly_activity() - Triggers Glific flows for each teacher in the weekly snapshot
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


def get_eligible_batch_for_teacher(teacher):
    """
    Find the eligible batch onboarding for a teacher based on their school.
    
    Selection criteria:
    - Batch onboarding belongs to teacher's school
    - Batch is active
    - Batch has regular_activity_start_date set
    - Select the batch with latest regular_activity_start_date within the week
    
    Args:
        teacher: Teacher document or dict with school_id field
        
    Returns:
        dict: Batch onboarding info with batch details, or None if not found
    """
    school_id = teacher.get('school_id') if isinstance(teacher, dict) else teacher.school_id
    #print(school_id)
    if not school_id:
        return None
    
    # Get all batch onboardings for this school
    batch_onboardings = frappe.get_all(
        "Batch onboarding",
        filters={"school": school_id},
        fields=["name", "batch", "batch_skeyword", "school"]
    )
    #print(batch_onboardings)
    if not batch_onboardings:
        return None
    
    # Get current week dates
    week_start_date, week_end_date = get_current_week_dates()
    
    eligible_batch = None
    latest_activity_start = None
    
    for bo in batch_onboardings:
        # Get batch details
        batch = frappe.get_doc("Batch", bo.batch)
        
        # Check if batch is active
        if not batch.active:
            continue
        
        # Check if regular_activity_start_date is set
        if not batch.regular_activity_start_date:
            continue
        
        activity_start = getdate(batch.regular_activity_start_date)
        
        # Check if activity has started (start date is on or before current week)
        if activity_start > week_end_date:
            continue
        
        # Select the batch with the latest regular_activity_start_date
        if latest_activity_start is None or activity_start > latest_activity_start:
            latest_activity_start = activity_start
            eligible_batch = {
                "batch_onboarding": bo.name,
                "batch": bo.batch,
                "batch_keyword": bo.batch_skeyword,
                "school": bo.school,
                "regular_activity_start_date": batch.regular_activity_start_date,
                "batch_name": batch.name1
            }
    
    return eligible_batch


@frappe.whitelist()
def get_weekly_teachers():
    """
    Create a weekly snapshot of all eligible teachers and their batch assignments.
    
    This function:
    1. Identifies the current week window (Monday to Sunday)
    2. Fetches all teachers with a school assigned
    3. For each teacher's school, finds active batches with regular_activity_start_date
    4. Creates a WeeklyTeacherFlow document with all eligible teachers
    
    Returns:
        dict: Result with status, message, and document name if successful
    """
    try:
        frappe.logger().info("Starting get_weekly_teachers()")
        
        # Get current week dates
        week_start_date, week_end_date = get_current_week_dates()
        
        frappe.logger().info(f"Week window: {week_start_date} to {week_end_date}")
        
        # Check if a document already exists for this week
        existing_doc = frappe.get_all(
            "WeeklyTeacherFlow",
            filters={
                "week_start_date": week_start_date,
                "week_end_date": week_end_date
            },
            fields=["name"]
        )
        
        if existing_doc:
            frappe.logger().info(f"WeeklyTeacherFlow already exists for this week: {existing_doc[0].name}")
            return {
                "status": "exists",
                "message": f"WeeklyTeacherFlow already exists for this week",
                "document_name": existing_doc[0].name
            }
        
        # Fetch all teachers with a school assigned
        teachers = frappe.get_all(
            "Teacher",
            filters={
                "school_id": ["is", "set"]  # school_id is not null
            },
            fields=["name", "first_name", "last_name", "phone_number", "glific_id", "school_id"]
        )

        #print(teachers)
        
        frappe.logger().info(f"Found {len(teachers)} teachers with school assigned")
        
        if not teachers:
            return {
                "status": "no_teachers",
                "message": "No teachers found with school assigned"
            }
        
        # Create WeeklyTeacherFlow document
        weekly_flow = frappe.new_doc("WeeklyTeacherFlow")
        weekly_flow.week_start_date = week_start_date
        weekly_flow.week_end_date = week_end_date
        weekly_flow.status = "Draft"
        weekly_flow.created_at = now_datetime()
        
        eligible_count = 0
        skipped_count = 0
        
        # Process each teacher
        for teacher in teachers:
            # Find eligible batch for this teacher
            eligible_batch = get_eligible_batch_for_teacher(teacher)
            
            if not eligible_batch:
                skipped_count += 1
                frappe.logger().debug(f"No eligible batch for teacher {teacher.name}")
                continue
            
            # Calculate current week number
            current_week_no = calculate_current_week_no(
                eligible_batch["regular_activity_start_date"],
                week_start_date
            )
            
            if not current_week_no:
                skipped_count += 1
                frappe.logger().debug(f"Could not calculate week number for teacher {teacher.name}")
                continue
            
            # Build teacher name
            teacher_name = f"{teacher.first_name or ''} {teacher.last_name or ''}".strip()
            
            # Add teacher to child table
            weekly_flow.append("teachers", {
                "teacher": teacher.name,
                "teacher_name": teacher_name,
                "phone_number": teacher.phone_number,
                "glific_id": teacher.glific_id,
                "batch_onboarding": eligible_batch["batch_onboarding"],
                "batch_keyword": eligible_batch["batch_keyword"],
                "regular_activity_start_date": eligible_batch["regular_activity_start_date"],
                "current_week_no": current_week_no,
                "flow_trigger_status": "Pending"
            })
            
            eligible_count += 1
        
        frappe.logger().info(f"Eligible teachers: {eligible_count}, Skipped: {skipped_count}")
        
        if eligible_count == 0:
            return {
                "status": "no_eligible_teachers",
                "message": "No eligible teachers found for this week",
                "total_teachers": len(teachers),
                "skipped": skipped_count
            }
        
        # Insert the document
        weekly_flow.insert(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info(f"Created WeeklyTeacherFlow: {weekly_flow.name}")
        
        return {
            "status": "success",
            "message": f"WeeklyTeacherFlow created successfully",
            "document_name": weekly_flow.name,
            "week_start_date": str(week_start_date),
            "week_end_date": str(week_end_date),
            "eligible_teachers": eligible_count,
            "skipped_teachers": skipped_count,
            "total_teachers": len(teachers)
        }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        frappe.log_error(
            message=f"Error in get_weekly_teachers: {str(e)}\n{error_traceback}",
            title="Get Weekly Teachers Error"
        )
        frappe.db.rollback()
        return {
            "status": "error",
            "message": str(e)
        }


def get_teacher_activity_flow_id():
    """
    Get the Glific flow ID for teacher weekly activity.
    
    First checks Glific Settings for a configured teacher_activity_flow_id,
    then falls back to looking up "Teacher Weekly Activity Flow" in Glific Flow doctype.
    
    Returns:
        str: Flow ID or None if not configured
    """
    # Try to get from Glific Settings
    settings = frappe.get_doc("Glific Settings")
    if hasattr(settings, 'teacher_activity_flow_id') and settings.teacher_activity_flow_id:
        return settings.teacher_activity_flow_id
    
    # Fallback: Look up in Glific Flow doctype by label
    flow = frappe.db.get_value(
        "Glific Flow",
        {"label": "Teacher Weekly Activity Flow"},
        "flow_id"
    )
    print(flow)
    
    return flow


def resolve_glific_id(teacher_row):
    """
    Resolve Glific contact ID for a teacher.
    
    If glific_id is already set, return it.
    Otherwise, try to look up via phone number.
    
    Args:
        teacher_row: WeeklyTeachers child row
        
    Returns:
        str: Glific contact ID or None
    """
    # If glific_id is already available
    if teacher_row.glific_id:
        return teacher_row.glific_id
    
    # Try to look up by phone number
    if not teacher_row.phone_number:
        return None
    
    formatted_phone = format_phone_for_glific(teacher_row.phone_number)
    if not formatted_phone:
        return None
    
    try:
        contact = get_contact_by_phone(formatted_phone)
        if contact and contact.get('id'):
            # Update the teacher record with the resolved glific_id
            frappe.db.set_value("Teacher", teacher_row.teacher, "glific_id", contact['id'])
            return contact['id']
    except Exception as e:
        frappe.logger().error(f"Error looking up Glific contact for {teacher_row.teacher}: {str(e)}")
    
    return None


@frappe.whitelist()
def trigger_teacher_weekly_activity(weekly_flow_name=None):
    """
    Trigger Glific flows for teachers in the current week's WeeklyTeacherFlow.
    
    This function:
    1. Finds the current week's WeeklyTeacherFlow document (or uses provided name)
    2. For each teacher row with Pending status:
       - Resolves glific_contact_id if missing (via Glific lookup by phone)
       - Calls Glific Start Flow API
       - Updates flow_trigger_status to Success/Failed
       - Updates flow_triggered_at timestamp
       - Logs any errors
    
    Args:
        weekly_flow_name: Optional specific WeeklyTeacherFlow document name
        
    Returns:
        dict: Result with counts of success/failed triggers
    """
    try:
        frappe.logger().info(f"Starting trigger_teacher_weekly_activity(weekly_flow_name={weekly_flow_name})")
        
        # Find the WeeklyTeacherFlow document
        if weekly_flow_name:
            weekly_flow = frappe.get_doc("WeeklyTeacherFlow", weekly_flow_name)
        else:
            # Get current week's document
            week_start_date, week_end_date = get_current_week_dates()
            
            weekly_flows = frappe.get_all(
                "WeeklyTeacherFlow",
                filters={
                    "week_start_date": week_start_date,
                    "week_end_date": week_end_date
                },
                fields=["name"]
            )
            
            if not weekly_flows:
                return {
                    "status": "not_found",
                    "message": f"No WeeklyTeacherFlow found for week {week_start_date} to {week_end_date}"
                }
            
            weekly_flow = frappe.get_doc("WeeklyTeacherFlow", weekly_flows[0].name)
        
        frappe.logger().info(f"Processing WeeklyTeacherFlow: {weekly_flow.name}")
        
        # Get the flow ID for teacher activity
        flow_id = get_teacher_activity_flow_id()
        
        if not flow_id:
            error_msg = "Teacher activity flow ID not configured in Glific Settings or Glific Flow"
            frappe.log_error(message=error_msg, title="Teacher Activity Flow Error")
            
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
        
        # Process each teacher row
        for teacher_row in weekly_flow.teachers:
            # Skip if already processed
            if teacher_row.flow_trigger_status in ["Success", "Failed"]:
                skipped_count += 1
                continue
            
            current_time = now_datetime()
            
            try:
                # Resolve Glific ID
                glific_id = resolve_glific_id(teacher_row)
                
                if not glific_id:
                    teacher_row.flow_trigger_status = "Failed"
                    teacher_row.flow_triggered_at = current_time
                    teacher_row.error_log = "Glific contact ID not found - teacher does not have glific_id and phone lookup failed"
                    failed_count += 1
                    frappe.logger().warning(f"No Glific ID for teacher {teacher_row.teacher}")
                    continue
                
                # Update glific_id in the row if it was resolved
                if not teacher_row.glific_id:
                    teacher_row.glific_id = glific_id
                
                # Prepare default_results for Glific flow
                default_results = {
                    "batch_keyword": teacher_row.batch_keyword or "",
                    "current_week_no": teacher_row.current_week_no or 0,
                    "teacher_name": teacher_row.teacher_name or "",
                    "teacher_id": teacher_row.teacher or "",
                    "week_start_date": str(weekly_flow.week_start_date),
                    "week_end_date": str(weekly_flow.week_end_date)
                }
                
                frappe.logger().debug(f"Triggering flow for teacher {teacher_row.teacher}, glific_id: {glific_id}")
                
                # Call Glific Start Flow API
                success = start_contact_flow(flow_id, glific_id, default_results)
                
                if success:
                    teacher_row.flow_trigger_status = "Success"
                    teacher_row.flow_triggered_at = current_time
                    teacher_row.error_log = None
                    success_count += 1
                    frappe.logger().info(f"Flow triggered successfully for teacher {teacher_row.teacher}")
                else:
                    teacher_row.flow_trigger_status = "Failed"
                    teacher_row.flow_triggered_at = current_time
                    teacher_row.error_log = "Glific API returned failure - flow could not be started"
                    failed_count += 1
                    frappe.logger().error(f"Flow trigger failed for teacher {teacher_row.teacher}")
                    
            except Exception as e:
                error_msg = str(e)
                teacher_row.flow_trigger_status = "Failed"
                teacher_row.flow_triggered_at = current_time
                teacher_row.error_log = f"Exception occurred: {error_msg}"
                failed_count += 1
                frappe.logger().error(f"Error triggering flow for teacher {teacher_row.teacher}: {error_msg}")
        
        # Update WeeklyTeacherFlow status
        weekly_flow.status = "Completed"
        weekly_flow.save(ignore_permissions=True)
        frappe.db.commit()
        
        frappe.logger().info(f"Completed trigger_teacher_weekly_activity: Success={success_count}, Failed={failed_count}, Skipped={skipped_count}")
        
        return {
            "status": "success",
            "message": "Teacher weekly activity flows triggered",
            "document_name": weekly_flow.name,
            "success_count": success_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "total_teachers": len(weekly_flow.teachers)
        }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        frappe.log_error(
            message=f"Error in trigger_teacher_weekly_activity: {str(e)}\n{error_traceback}",
            title="Trigger Teacher Weekly Activity Error"
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
def run_weekly_teacher_activity_automation():
    """
    Main entry point for the weekly scheduled job.
    
    This function:
    1. Calls get_weekly_teachers() to create the weekly snapshot
    2. If successful, calls trigger_teacher_weekly_activity() to trigger flows
    
    This should be scheduled to run weekly (e.g., Monday morning IST).
    
    Returns:
        dict: Combined result of both operations
    """
    try:
        frappe.logger().info("Starting weekly teacher activity automation")
        
        # Step 1: Create weekly snapshot
        snapshot_result = get_weekly_teachers()
        
        if snapshot_result.get("status") == "error":
            return {
                "status": "error",
                "step": "get_weekly_teachers",
                "message": snapshot_result.get("message")
            }
        
        if snapshot_result.get("status") == "no_teachers":
            return {
                "status": "no_teachers",
                "message": "No teachers with school assigned"
            }
        
        if snapshot_result.get("status") == "no_eligible_teachers":
            return {
                "status": "no_eligible_teachers",
                "message": "No eligible teachers for this week"
            }
        
        # Get the document name (either new or existing)
        document_name = snapshot_result.get("document_name")
        
        # Step 2: Trigger flows
        trigger_result = trigger_teacher_weekly_activity(document_name)
        
        return {
            "status": trigger_result.get("status"),
            "message": "Weekly teacher activity automation completed",
            "snapshot_result": snapshot_result,
            "trigger_result": trigger_result
        }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        frappe.log_error(
            message=f"Error in weekly teacher activity automation: {str(e)}\n{error_traceback}",
            title="Weekly Teacher Activity Automation Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }


# Utility function to manually re-trigger failed flows
@frappe.whitelist()
def retry_failed_flows(weekly_flow_name):
    """
    Retry triggering flows for teachers that previously failed.
    
    Args:
        weekly_flow_name: Name of the WeeklyTeacherFlow document
        
    Returns:
        dict: Result with counts of retried flows
    """
    try:
        weekly_flow = frappe.get_doc("WeeklyTeacherFlow", weekly_flow_name)
        
        # Reset failed rows to Pending
        reset_count = 0
        for teacher_row in weekly_flow.teachers:
            if teacher_row.flow_trigger_status == "Failed":
                teacher_row.flow_trigger_status = "Pending"
                teacher_row.error_log = None
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
        return trigger_teacher_weekly_activity(weekly_flow_name)
        
    except Exception as e:
        frappe.log_error(
            message=f"Error in retry_failed_flows: {str(e)}",
            title="Retry Failed Flows Error"
        )
        return {
            "status": "error",
            "message": str(e)
        }