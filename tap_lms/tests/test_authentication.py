# # tests/test_authentication.py
# import frappe
# import unittest
# from unittest.mock import patch, MagicMock
# import json
# from .test_base import BaseAPITest
# from tap_lms.api import authenticate_api_key, list_districts, list_cities, verify_keyword

# class TestAuthentication(BaseAPITest):
#     """Test authentication and basic API functions"""
    
#     def test_authenticate_api_key_valid(self):
#         """Test authentication with valid API key"""
#         result = authenticate_api_key(self.valid_api_key)
#         self.assertIsNotNone(result)
#         self.assertEqual(result, self.valid_api_key)
        
#     def test_authenticate_api_key_invalid(self):
#         """Test authentication with invalid API key"""
#         result = authenticate_api_key(self.invalid_api_key)
#         self.assertIsNone(result)
        
#     def test_authenticate_api_key_disabled(self):
#         """Test authentication with disabled API key"""
#         disabled_key = "disabled_key"
#         if not frappe.db.exists("API Key", disabled_key):
#             api_key_doc = frappe.get_doc({
#                 "doctype": "API Key",
#                 "key": disabled_key,
#                 "enabled": 0
#             })
#             api_key_doc.insert(ignore_permissions=True)
            
#         result = authenticate_api_key(disabled_key)
#         self.assertIsNone(result)

# class TestDistrictsAPI(BaseAPITest):
#     """Test districts listing API"""
    
#     def setUp(self):
#         super().setUp()
#         self.state = "TEST_STATE"
#         self.district = self.create_test_district("TEST_DISTRICT_1", self.state)
#         self.create_test_district("TEST_DISTRICT_2", self.state)
        
#     def test_list_districts_success(self):
#         """Test successful districts listing"""
#         data = {
#             "api_key": self.valid_api_key,
#             "state": self.state
#         }
#         self.mock_request_data(data)
        
#         result = list_districts()
        
#         self.assertEqual(result["status"], "success")
#         self.assertIn("data", result)
#         self.assertIsInstance(result["data"], dict)
        
#     def test_list_districts_missing_api_key(self):
#         """Test districts listing with missing API key"""
#         data = {"state": self.state}
#         self.mock_request_data(data)
        
#         result = list_districts()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     def test_list_districts_missing_state(self):
#         """Test districts listing with missing state"""
#         data = {"api_key": self.valid_api_key}
#         self.mock_request_data(data)
        
#         result = list_districts()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     def test_list_districts_invalid_api_key(self):
#         """Test districts listing with invalid API key"""
#         data = {
#             "api_key": self.invalid_api_key,
#             "state": self.state
#         }
#         self.mock_request_data(data)
        
#         result = list_districts()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 401)
        
#     @patch('frappe.log_error')
#     def test_list_districts_exception(self, mock_log_error):
#         """Test districts listing with exception"""
#         with patch('json.loads') as mock_json_loads:
#             mock_json_loads.side_effect = Exception("JSON parse error")
            
#             result = list_districts()
            
#             self.assertEqual(result["status"], "error")
#             self.assertEqual(frappe.response.http_status_code, 500)
#             mock_log_error.assert_called_once()

# class TestCitiesAPI(BaseAPITest):
#     """Test cities listing API"""
    
#     def setUp(self):
#         super().setUp()
#         self.district = self.create_test_district()
#         self.city = self.create_test_city("TEST_CITY_1", self.district)
#         self.create_test_city("TEST_CITY_2", self.district)
        
#     def test_list_cities_success(self):
#         """Test successful cities listing"""
#         data = {
#             "api_key": self.valid_api_key,
#             "district": self.district
#         }
#         self.mock_request_data(data)
        
#         result = list_cities()
        
#         self.assertEqual(result["status"], "success")
#         self.assertIn("data", result)
#         self.assertIsInstance(result["data"], dict)
        
#     def test_list_cities_missing_api_key(self):
#         """Test cities listing with missing API key"""
#         data = {"district": self.district}
#         self.mock_request_data(data)
        
#         result = list_cities()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     def test_list_cities_missing_district(self):
#         """Test cities listing with missing district"""
#         data = {"api_key": self.valid_api_key}
#         self.mock_request_data(data)
        
#         result = list_cities()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     def test_list_cities_invalid_api_key(self):
#         """Test cities listing with invalid API key"""
#         data = {
#             "api_key": self.invalid_api_key,
#             "district": self.district
#         }
#         self.mock_request_data(data)
        
#         result = list_cities()
        
#         self.assertEqual(result["status"], "error")
#         self.assertEqual(frappe.response.http_status_code, 401)

# class TestVerifyKeywordAPI(BaseAPITest):
#     """Test keyword verification API"""
    
#     def setUp(self):
#         super().setUp()
#         self.school = self.create_test_school("TEST_SCHOOL", "test_keyword")
        
#     def test_verify_keyword_success(self):
#         """Test successful keyword verification"""
#         data = {
#             "api_key": self.valid_api_key,
#             "keyword": "test_keyword"
#         }
#         self.mock_request_data(data)
        
#         result = verify_keyword()
        
#         self.assertEqual(result["status"], "success")
#         self.assertIsNotNone(result["school_name"])
#         self.assertEqual(frappe.response.http_status_code, 200)
        
#     def test_verify_keyword_not_found(self):
#         """Test keyword verification with non-existent keyword"""
#         data = {
#             "api_key": self.valid_api_key,
#             "keyword": "non_existent_keyword"
#         }
#         self.mock_request_data(data)
        
#         result = verify_keyword()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 404)
        
#     def test_verify_keyword_missing_api_key(self):
#         """Test keyword verification with missing API key"""
#         data = {"keyword": "test_keyword"}
#         self.mock_request_data(data)
        
#         result = verify_keyword()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 401)
        
#     def test_verify_keyword_missing_keyword(self):
#         """Test keyword verification with missing keyword"""
#         data = {"api_key": self.valid_api_key}
#         self.mock_request_data(data)
        
#         result = verify_keyword()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 400)
        
#     def test_verify_keyword_invalid_api_key(self):
#         """Test keyword verification with invalid API key"""
#         data = {
#             "api_key": self.invalid_api_key,
#             "keyword": "test_keyword"
#         }
#         self.mock_request_data(data)
        
#         result = verify_keyword()
        
#         self.assertEqual(result["status"], "failure")
#         self.assertEqual(frappe.response.http_status_code, 401)

# tests/test_authentication.py
import frappe
import unittest
from unittest.mock import patch, MagicMock
import json
from .test_base import BaseAPITest
from tap_lms.api import authenticate_api_key, list_districts, list_cities, verify_keyword

class TestAuthentication(BaseAPITest):
    """Test authentication and basic API functions"""
    
    @patch('frappe.get_doc')
    def test_authenticate_api_key_valid(self, mock_get_doc):
        """Test authentication with valid API key"""
        # Mock successful API key document
        mock_api_key_doc = MagicMock()
        mock_api_key_doc.name = "test_api_key"
        mock_api_key_doc.enabled = 1
        mock_get_doc.return_value = mock_api_key_doc
        
        result = authenticate_api_key(self.valid_api_key)
        self.assertIsNotNone(result)
        self.assertEqual(result, "test_api_key")
        
    @patch('frappe.get_doc')
    def test_authenticate_api_key_invalid(self, mock_get_doc):
        """Test authentication with invalid API key"""
        # Mock DoesNotExistError as a proper exception
        from frappe.exceptions import DoesNotExistError
        mock_get_doc.side_effect = DoesNotExistError("API Key not found")
        
        result = authenticate_api_key(self.invalid_api_key)
        self.assertIsNone(result)
        
    @patch('frappe.get_doc')
    def test_authenticate_api_key_disabled(self, mock_get_doc):
        """Test authentication with disabled API key"""
        # Mock disabled API key document
        mock_api_key_doc = MagicMock()
        mock_api_key_doc.name = "disabled_key"
        mock_api_key_doc.enabled = 0
        mock_get_doc.return_value = mock_api_key_doc
        
        result = authenticate_api_key("disabled_key")
        self.assertIsNone(result)

class TestDistrictsAPI(BaseAPITest):
    """Test districts listing API"""
    
    def setUp(self):
        super().setUp()
        self.state = "TEST_STATE"
        # Create test data using proper Frappe methods
        self.district = self.create_test_district("TEST_DISTRICT_1", self.state)
        self.create_test_district("TEST_DISTRICT_2", self.state)
        
    @patch('tap_lms.api.authenticate_api_key')
    @patch('frappe.db.get_all')
    def test_list_districts_success(self, mock_get_all, mock_auth):
        """Test successful districts listing"""
        # Mock authentication success
        mock_auth.return_value = self.valid_api_key
        
        # Mock database query
        mock_get_all.return_value = [
            {"name": "TEST_DISTRICT_1"},
            {"name": "TEST_DISTRICT_2"}
        ]
        
        data = {
            "api_key": self.valid_api_key,
            "state": self.state
        }
        self.mock_request_data(data)
        
        result = list_districts()
        
        self.assertEqual(result["status"], "success")
        self.assertIn("data", result)
        self.assertIsInstance(result["data"], dict)
        
    @patch('frappe.response')
    def test_list_districts_missing_api_key(self, mock_response):
        """Test districts listing with missing API key"""
        mock_response.http_status_code = None
        
        data = {"state": self.state}
        self.mock_request_data(data)
        
        result = list_districts()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(mock_response.http_status_code, 400)
        
    @patch('frappe.response')
    def test_list_districts_missing_state(self, mock_response):
        """Test districts listing with missing state"""
        mock_response.http_status_code = None
        
        data = {"api_key": self.valid_api_key}
        self.mock_request_data(data)
        
        result = list_districts()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(mock_response.http_status_code, 400)
        
    @patch('frappe.response')
    @patch('tap_lms.api.authenticate_api_key')
    def test_list_districts_invalid_api_key(self, mock_auth, mock_response):
        """Test districts listing with invalid API key"""
        mock_response.http_status_code = None
        mock_auth.return_value = None  # Invalid API key
        
        data = {
            "api_key": self.invalid_api_key,
            "state": self.state
        }
        self.mock_request_data(data)
        
        result = list_districts()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(mock_response.http_status_code, 401)
        
    @patch('frappe.log_error')
    @patch('frappe.response')
    def test_list_districts_exception(self, mock_response, mock_log_error):
        """Test districts listing with exception"""
        mock_response.http_status_code = None
        
        with patch('json.loads') as mock_json_loads:
            mock_json_loads.side_effect = Exception("JSON parse error")
            
            result = list_districts()
            
            self.assertEqual(result["status"], "error")
            self.assertEqual(mock_response.http_status_code, 500)
            mock_log_error.assert_called_once()

class TestCitiesAPI(BaseAPITest):
    """Test cities listing API"""
    
    def setUp(self):
        super().setUp()
        self.district = self.create_test_district()
        self.city = self.create_test_city("TEST_CITY_1", self.district)
        self.create_test_city("TEST_CITY_2", self.district)
        
    @patch('tap_lms.api.authenticate_api_key')
    @patch('frappe.db.get_all')
    def test_list_cities_success(self, mock_get_all, mock_auth):
        """Test successful cities listing"""
        # Mock authentication success
        mock_auth.return_value = self.valid_api_key
        
        # Mock database query
        mock_get_all.return_value = [
            {"name": "TEST_CITY_1"},
            {"name": "TEST_CITY_2"}
        ]
        
        data = {
            "api_key": self.valid_api_key,
            "district": self.district
        }
        self.mock_request_data(data)
        
        result = list_cities()
        
        self.assertEqual(result["status"], "success")
        self.assertIn("data", result)
        self.assertIsInstance(result["data"], dict)
        
    @patch('frappe.response')
    def test_list_cities_missing_api_key(self, mock_response):
        """Test cities listing with missing API key"""
        mock_response.http_status_code = None
        
        data = {"district": self.district}
        self.mock_request_data(data)
        
        result = list_cities()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(mock_response.http_status_code, 400)
        
    @patch('frappe.response')
    def test_list_cities_missing_district(self, mock_response):
        """Test cities listing with missing district"""
        mock_response.http_status_code = None
        
        data = {"api_key": self.valid_api_key}
        self.mock_request_data(data)
        
        result = list_cities()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(mock_response.http_status_code, 400)
        
    @patch('frappe.response')
    @patch('tap_lms.api.authenticate_api_key')
    def test_list_cities_invalid_api_key(self, mock_auth, mock_response):
        """Test cities listing with invalid API key"""
        mock_response.http_status_code = None
        mock_auth.return_value = None  # Invalid API key
        
        data = {
            "api_key": self.invalid_api_key,
            "district": self.district
        }
        self.mock_request_data(data)
        
        result = list_cities()
        
        self.assertEqual(result["status"], "error")
        self.assertEqual(mock_response.http_status_code, 401)

class TestVerifyKeywordAPI(BaseAPITest):
    """Test keyword verification API"""
    
    def setUp(self):
        super().setUp()
        self.school = self.create_test_school("TEST_SCHOOL", "test_keyword")
        
    @patch('tap_lms.api.authenticate_api_key')
    @patch('frappe.db.get_value')
    @patch('frappe.response')
    def test_verify_keyword_success(self, mock_response, mock_get_value, mock_auth):
        """Test successful keyword verification"""
        mock_response.http_status_code = None
        mock_auth.return_value = self.valid_api_key
        mock_get_value.return_value = "TEST_SCHOOL"
        
        data = {
            "api_key": self.valid_api_key,
            "keyword": "test_keyword"
        }
        self.mock_request_data(data)
        
        result = verify_keyword()
        
        self.assertEqual(result["status"], "success")
        self.assertIsNotNone(result["school_name"])
        self.assertEqual(mock_response.http_status_code, 200)
        
    @patch('tap_lms.api.authenticate_api_key')
    @patch('frappe.db.get_value')
    @patch('frappe.response')
    def test_verify_keyword_not_found(self, mock_response, mock_get_value, mock_auth):
        """Test keyword verification with non-existent keyword"""
        mock_response.http_status_code = None
        mock_auth.return_value = self.valid_api_key
        mock_get_value.return_value = None
        
        data = {
            "api_key": self.valid_api_key,
            "keyword": "non_existent_keyword"
        }
        self.mock_request_data(data)
        
        result = verify_keyword()
        
        self.assertEqual(result["status"], "failure")
        self.assertEqual(mock_response.http_status_code, 404)
        
    @patch('frappe.response')
    def test_verify_keyword_missing_api_key(self, mock_response):
        """Test keyword verification with missing API key"""
        mock_response.http_status_code = None
        
        data = {"keyword": "test_keyword"}
        self.mock_request_data(data)
        
        result = verify_keyword()
        
        self.assertEqual(result["status"], "failure")
        self.assertEqual(mock_response.http_status_code, 401)
        
    @patch('frappe.response')
    def test_verify_keyword_missing_keyword(self, mock_response):
        """Test keyword verification with missing keyword"""
        mock_response.http_status_code = None
        
        data = {"api_key": self.valid_api_key}
        self.mock_request_data(data)
        
        result = verify_keyword()
        
        self.assertEqual(result["status"], "failure")
        self.assertEqual(mock_response.http_status_code, 400)
        
    @patch('frappe.response')
    @patch('tap_lms.api.authenticate_api_key')
    def test_verify_keyword_invalid_api_key(self, mock_auth, mock_response):
        """Test keyword verification with invalid API key"""
        mock_response.http_status_code = None
        mock_auth.return_value = None  # Invalid API key
        
        data = {
            "api_key": self.invalid_api_key,
            "keyword": "test_keyword"
        }
        self.mock_request_data(data)
        
        result = verify_keyword()
        
        self.assertEqual(result["status"], "failure")
        self.assertEqual(mock_response.http_status_code, 401)