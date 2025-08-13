# Copyright (c) 2023, Tech4dev and contributors
# For license information, please see license.txt

import unittest
import frappe
from unittest.mock import patch


class TestEnrollment(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up test class"""
        # Simple initialization - always try to ensure connection
        try:
            frappe.init(site="test_site")
            frappe.connect()
        except Exception:
            # Already initialized or initialization failed
            pass

    def setUp(self):
        """Set up test dependencies"""
        # Clean up any existing test records
        if frappe.db.exists("DocType", "Enrollment"):
            frappe.db.delete("Enrollment", {"name": ["like", "TEST-%"]})
            frappe.db.commit()

    def tearDown(self):
        """Clean up after tests"""
        # Clean up test records
        if frappe.db.exists("DocType", "Enrollment"):
            frappe.db.delete("Enrollment", {"name": ["like", "TEST-%"]})
            frappe.db.commit()

    def test_enrollment_doctype_exists(self):
        """Test that Enrollment DocType exists"""
        self.assertTrue(frappe.db.exists("DocType", "Enrollment"))

    
    