import frappe

def trigger_onboarding_flow(student_id):
    """
    Trigger onboarding for a student in Glific integration.
    """
    try:
        # Fetch student document
        student = frappe.get_doc("Student", student_id)
        student.status = "Onboarded"
        student.save()

        # Commit changes to database
        frappe.db.commit()

        return {
            "status": "success",
            "message": f"Onboarding completed for {student_id}",
            "student_id": student_id
        }
    except frappe.DoesNotExistError:
        return {
            "status": "failed",
            "message": f"Student {student_id} not found"
        }
    except Exception as e:
        frappe.log_error(f"Error in onboarding: {e}", "Glific Onboarding")
        return {
            "status": "error",
            "message": str(e)
        }
