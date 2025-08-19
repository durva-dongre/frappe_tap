# tests/test_base.py
import frappe
import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timedelta

class BaseAPITest(unittest.TestCase):
    """Base test class with common setup and utilities"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and common test data"""
        frappe.init(site="test_site")
        frappe.connect()
        frappe.db.begin()
        
    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests"""
        frappe.db.rollback()
        frappe.destroy()
        
    def setUp(self):
        """Set up before each test"""
        frappe.set_user("Administrator")
        self.valid_api_key = "test_valid_api_key"
        self.invalid_api_key = "test_invalid_api_key"
        
        # Create test API key
        if not frappe.db.exists("API Key", self.valid_api_key):
            api_key_doc = frappe.get_doc({
                "doctype": "API Key",
                "key": self.valid_api_key,
                "enabled": 1
            })
            api_key_doc.insert(ignore_permissions=True)
            
    def tearDown(self):
        """Clean up after each test"""
        frappe.db.rollback()
        
    def create_test_district(self, name="TEST_DISTRICT", state="TEST_STATE"):
        """Helper to create test district"""
        if not frappe.db.exists("District", name):
            district = frappe.get_doc({
                "doctype": "District",
                "name": name,
                "district_name": f"{name}_NAME",
                "state": state
            })
            district.insert(ignore_permissions=True)
        return name
        
    def create_test_city(self, name="TEST_CITY", district="TEST_DISTRICT"):
        """Helper to create test city"""
        if not frappe.db.exists("City", name):
            city = frappe.get_doc({
                "doctype": "City",
                "name": name,
                "city_name": f"{name}_NAME",
                "district": district
            })
            city.insert(ignore_permissions=True)
        return name
        
    def create_test_school(self, name="TEST_SCHOOL", keyword="test_keyword"):
        """Helper to create test school"""
        if not frappe.db.exists("School", name):
            school = frappe.get_doc({
                "doctype": "School",
                "name": name,
                "name1": f"{name}_DISPLAY",
                "keyword": keyword,
                "model": "TEST_MODEL"
            })
            school.insert(ignore_permissions=True)
        return name
        
    def create_test_batch(self, name="TEST_BATCH", active=1):
        """Helper to create test batch"""
        if not frappe.db.exists("Batch", name):
            batch = frappe.get_doc({
                "doctype": "Batch",
                "name": name,
                "batch_id": f"{name}_ID",
                "active": active,
                "start_date": frappe.utils.today(),
                "end_date": frappe.utils.add_days(frappe.utils.today(), 30),
                "regist_end_date": frappe.utils.add_days(frappe.utils.today(), 15)
            })
            batch.insert(ignore_permissions=True)
        return name
        
    def create_test_batch_onboarding(self, school, batch, keyword="test_batch_keyword"):
        """Helper to create test batch onboarding"""
        name = f"{school}_{batch}_ONBOARDING"
        if not frappe.db.exists("Batch onboarding", name):
            onboarding = frappe.get_doc({
                "doctype": "Batch onboarding",
                "name": name,
                "school": school,
                "batch": batch,
                "batch_skeyword": keyword,
                "model": "TEST_MODEL",
                "kit_less": 0,
                "from_grade": "1",
                "to_grade": "12"
            })
            onboarding.insert(ignore_permissions=True)
        return name
        
    def mock_request_data(self, data):
        """Helper to mock frappe.request.data"""
        frappe.request.data = json.dumps(data).encode('utf-8')
        
    def mock_form_dict(self, data):
        """Helper to mock frappe.form_dict"""
        frappe.form_dict = data

# tests/conftest.py (if using pytest)
import pytest
import frappe

@pytest.fixture(scope="session", autouse=True)
def setup_test_site():
    """Setup test site for all tests"""
    frappe.init(site="test_site")
    frappe.connect()
    yield
    frappe.destroy()

@pytest.fixture(autouse=True)
def setup_test_data():
    """Setup test data for each test"""
    frappe.db.begin()
    yield
    frappe.db.rollback()