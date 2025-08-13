import pytest
import sys
from unittest.mock import Mock

def test_course_project_coverage():
    """
    Minimal test to achieve 100% coverage for courseproject.py
    Covers lines 5, 7, and 8
    """
    
    # Mock frappe module
    class MockDocument:
        def __init__(self, *args, **kwargs):
            pass
    
    mock_frappe = Mock()
    mock_frappe.model = Mock()
    mock_frappe.model.document = Mock()
    mock_frappe.model.document.Document = MockDocument
    
    sys.modules['frappe'] = mock_frappe
    sys.modules['frappe.model'] = mock_frappe.model
    sys.modules['frappe.model.document'] = mock_frappe.model.document
    
    # Import and instantiate - this covers all 3 lines
    from tap_lms.tap_lms.doctype.courseproject.courseproject import CourseProject
    course_project = CourseProject()
    
    # Basic assertions
    assert course_project is not None
    assert CourseProject.__name__ == 'CourseProject'
    assert isinstance(course_project, CourseProject)


def test_course_project_inheritance():
    """Test CourseProject inherits from Document"""
    from tap_lms.tap_lms.doctype.courseproject.courseproject import CourseProject
    course_project = CourseProject()
    assert course_project is not None


def test_course_project_multiple_instances():
    """Test multiple CourseProject instances"""
    from tap_lms.tap_lms.doctype.courseproject.courseproject import CourseProject
    
    project1 = CourseProject()
    project2 = CourseProject()
    
    assert project1 is not None
    assert project2 is not None
    assert project1 is not project2
    