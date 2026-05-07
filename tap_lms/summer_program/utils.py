"""
Shared utility helpers for the Summer Program module.
tap_lms/summer_program/utils.py
"""
import frappe


def resolve_student(identifier):
    """Resolve a student identifier (Student name, glific_id, or phone) to Student document name.

    Args:
        identifier: Student document name, Glific ID, or phone number.

    Returns:
        Student document name (str) or None if not found.
    """
    if not identifier:
        return None
    if frappe.db.exists("Student", identifier):
        return identifier
    # Try glific_id
    student = frappe.db.get_value("Student", {"glific_id": identifier}, "name")
    if student:
        return student
    # Try phone
    return frappe.db.get_value("Student", {"phone": str(identifier).strip()}, "name")
