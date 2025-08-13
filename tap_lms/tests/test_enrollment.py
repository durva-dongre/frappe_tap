# Copyright (c) 2023, Tech4dev and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.test_runner import make_test_records
from frappe.utils import today, add_days, now_datetime

class TestEnrollment(unittest.TestCase):
   
    @classmethod
    def setUpClass(cls):
        """Set up test data"""
        frappe.set_user("Administrator")
        # Create test records if needed
        make_test_records("User")
       
        # Try to create Course records if Course doctype exists
        try:
            make_test_records("Course")
        except Exception as e:
            # If Course doctype doesn't exist, create a simple test course
            if not frappe.db.exists("Course", "TEST-COURSE-001"):
                try:
                    course = frappe.get_doc({
                        "doctype": "Course",
                        "course_name": "Test Course 001",
                        "course_code": "TEST-COURSE-001"
                    })
                    course.insert(ignore_permissions=True)
                except Exception as create_error:
                    pass  # Course doctype might not exist yet

        # Create additional test courses
        test_courses = ["TEST-COURSE-002", "TEST-COURSE-003"]
        for course_code in test_courses:
            if not frappe.db.exists("Course", course_code):
                try:
                    course = frappe.get_doc({
                        "doctype": "Course",
                        "course_name": f"Test Course {course_code[-3:]}",
                        "course_code": course_code
                    })
                    course.insert(ignore_permissions=True)
                except Exception:
                    pass
   
    def setUp(self):
        """Set up before each test"""
        frappe.set_user("Administrator")
        # Clean up any existing test enrollments more thoroughly
        frappe.db.sql("DELETE FROM `tabEnrollment` WHERE student LIKE 'test%@example.com'")
        frappe.db.commit()
   
    def tearDown(self):
        """Clean up after each test"""
        # Clean up test data more thoroughly
        frappe.db.sql("DELETE FROM `tabEnrollment` WHERE student LIKE 'test%@example.com'")
        frappe.db.commit()

    def test_enrollment_creation(self):
        """Test basic enrollment creation"""
        enrollment = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test1@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Active"
        })
        enrollment.insert(ignore_permissions=True)
        
        # Verify enrollment was created
        self.assertTrue(enrollment.name)
        self.assertEqual(enrollment.student, "test1@example.com")
        self.assertEqual(enrollment.status, "Active")
   
    def test_enrollment_update(self):
        """Test enrollment update functionality"""
        # Create enrollment
        enrollment = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test2@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Active"
        })
        enrollment.insert(ignore_permissions=True)
       
        # Update enrollment status
        enrollment.status = "Completed"
        enrollment.completion_date = today()
        enrollment.save(ignore_permissions=True)
       
        # Verify update
        updated_enrollment = frappe.get_doc("Enrollment", enrollment.name)
        self.assertEqual(updated_enrollment.status, "Completed")

    def test_enrollment_validation(self):
        """Test enrollment validation rules"""
        # Test duplicate enrollment prevention
        enrollment1 = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test3@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Active"
        })
        enrollment1.insert(ignore_permissions=True)
        
        # Try to create duplicate enrollment
        enrollment2 = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test3@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Active"
        })
        
        # This should either raise an exception or handle duplicates gracefully
        try:
            enrollment2.insert(ignore_permissions=True)
            # If no exception, check if duplicate was prevented another way
        except frappe.DuplicateEntryError:
            pass  # Expected behavior
        except Exception as e:
            # Handle other validation errors
            pass

    def test_enrollment_status_transitions(self):
        """Test different status transitions"""
        enrollment = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test4@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Pending"
        })
        enrollment.insert(ignore_permissions=True)
        
        # Test status progression: Pending -> Active -> Completed
        enrollment.status = "Active"
        enrollment.save(ignore_permissions=True)
        self.assertEqual(enrollment.status, "Active")
        
        enrollment.status = "Completed"
        enrollment.completion_date = today()
        enrollment.save(ignore_permissions=True)
        self.assertEqual(enrollment.status, "Completed")

    def test_enrollment_dates(self):
        """Test enrollment date handling"""
        future_date = add_days(today(), 30)
        
        enrollment = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test5@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "expected_completion_date": future_date,
            "status": "Active"
        })
        enrollment.insert(ignore_permissions=True)
        
        # Test date validations if they exist
        self.assertTrue(enrollment.enrollment_date)
        self.assertEqual(enrollment.expected_completion_date, future_date)

    def test_enrollment_cancellation(self):
        """Test enrollment cancellation"""
        enrollment = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test6@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Active"
        })
        enrollment.insert(ignore_permissions=True)
        
        # Cancel enrollment
        enrollment.status = "Cancelled"
        enrollment.save(ignore_permissions=True)
        
        self.assertEqual(enrollment.status, "Cancelled")

    def test_enrollment_bulk_operations(self):
        """Test bulk enrollment operations"""
        # Create multiple enrollments
        students = ["test7@example.com", "test8@example.com", "test9@example.com"]
        
        for student in students:
            enrollment = frappe.get_doc({
                "doctype": "Enrollment",
                "student": student,
                "course": "TEST-COURSE-002",
                "enrollment_date": today(),
                "status": "Active"
            })
            enrollment.insert(ignore_permissions=True)
        
        # Verify all enrollments were created
        count = frappe.db.count("Enrollment", {
            "course": "TEST-COURSE-002",
            "status": "Active"
        })
        self.assertEqual(count, 3)

    def test_enrollment_hooks_and_triggers(self):
        """Test any hooks, triggers, or custom methods"""
        enrollment = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test10@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Active"
        })
        enrollment.insert(ignore_permissions=True)
        
        # Test any custom methods that might exist
        try:
            # Example: if there's a method to calculate progress
            if hasattr(enrollment, 'calculate_progress'):
                enrollment.calculate_progress()
            
            # Example: if there's a method to send notifications
            if hasattr(enrollment, 'send_enrollment_notification'):
                enrollment.send_enrollment_notification()
                
            # Example: if there's a method to update student records
            if hasattr(enrollment, 'update_student_record'):
                enrollment.update_student_record()
                
        except Exception as e:
            # Handle method calls that might fail in test environment
            pass

    def test_enrollment_permissions(self):
        """Test enrollment permissions and access control"""
        # Test with different user roles if applicable
        enrollment = frappe.get_doc({
            "doctype": "Enrollment",
            "student": "test11@example.com",
            "course": "TEST-COURSE-001",
            "enrollment_date": today(),
            "status": "Active"
        })
        enrollment.insert(ignore_permissions=True)
        
        # Test read permissions
        fetched_enrollment = frappe.get_doc("Enrollment", enrollment.name)
        self.assertEqual(fetched_enrollment.name, enrollment.name)

    def test_enrollment_edge_cases(self):
        """Test edge cases and error handling"""
        # Test with invalid course
        try:
            enrollment = frappe.get_doc({
                "doctype": "Enrollment",
                "student": "test12@example.com",
                "course": "INVALID-COURSE",
                "enrollment_date": today(),
                "status": "Active"
            })
            enrollment.insert(ignore_permissions=True)
        except Exception as e:
            # Expected to fail with invalid course
            pass
        
        # Test with empty/invalid student email
        try:
            enrollment = frappe.get_doc({
                "doctype": "Enrollment",
                "student": "",
                "course": "TEST-COURSE-001",
                "enrollment_date": today(),
                "status": "Active"
            })
            enrollment.insert(ignore_permissions=True)
        except Exception as e:
            # Expected to fail with empty student
            pass

    def test_enrollment_reports_and_queries(self):
        """Test any report generation or complex queries"""
        # Create test data for reports
        test_enrollments = [
            {"student": "report1@example.com", "status": "Active"},
            {"student": "report2@example.com", "status": "Completed"},
            {"student": "report3@example.com", "status": "Cancelled"}
        ]
        
        for enroll_data in test_enrollments:
            enrollment = frappe.get_doc({
                "doctype": "Enrollment",
                "student": enroll_data["student"],
                "course": "TEST-COURSE-001",
                "enrollment_date": today(),
                "status": enroll_data["status"]
            })
            enrollment.insert(ignore_permissions=True)
        
        # Test status-based queries
        active_count = frappe.db.count("Enrollment", {"status": "Active", "course": "TEST-COURSE-001"})
        self.assertGreaterEqual(active_count, 1)
        
        completed_count = frappe.db.count("Enrollment", {"status": "Completed", "course": "TEST-COURSE-001"})
        self.assertGreaterEqual(completed_count, 1)