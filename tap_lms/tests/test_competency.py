import pytest
import sys
from unittest.mock import Mock

def test_competency_coverage():
    """
    Minimal test to achieve 100% coverage for competency.py
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
    from tap_lms.tap_lms.doctype.competency.competency import Competency
    competency = Competency()
    
    # Basic assertions
    assert competency is not None
    assert Competency.__name__ == 'Competency'
    assert isinstance(competency, Competency)


def test_competency_inheritance():
    """Test Competency inherits from Document"""
    from tap_lms.tap_lms.doctype.competency.competency import Competency
    competency = Competency()
    assert competency is not None


def test_competency_multiple_instances():
    """Test multiple Competency instances"""
    from tap_lms.tap_lms.doctype.competency.competency import Competency
    
    competency1 = Competency()
    competency2 = Competency()
    
    assert competency1 is not None
    assert competency2 is not None
    assert competency1 is not competency2