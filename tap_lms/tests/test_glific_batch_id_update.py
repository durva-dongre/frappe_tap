# test_utils.py - Test utilities and helper functions
"""
Utility functions and helpers for testing Glific batch ID update module
"""

import json
import time
import random
import string
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock
from typing import Dict, List, Any, Optional


class MockDataFactory:
    """Factory class for creating mock test data"""
    
    @staticmethod
    def create_backend_student(
        student_id: str = "STU-001",
        batch: str = "BATCH-CS-2024",
        phone: str = "+1234567890",
        name: str = "John Doe"
    ) -> Dict[str, Any]:
        """Create mock backend student data"""
        return {
            'name': f'BS-{student_id.split("-")[-1]}',
            'student_name': name,
            'phone': phone,
            'student_id': student_id,
            'batch': batch,
            'batch_skeyword': batch.lower().replace('-', '')
        }
    
    @staticmethod
    def create_onboarding_set(
        name: str = "SET-001",
        status: str = "Processed",
        student_count: int = 25
    ) -> Mock:
        """Create mock onboarding set"""
        mock_set = Mock()
        mock_set.name = name
        mock_set.set_name = f"Test {name}"
        mock_set.status = status
        mock_set.processed_student_count = student_count
        mock_set.upload_date = datetime.now().strftime("%Y-%m-%d")
        return mock_set
    
    @staticmethod
    def create_student_document(
        student_id: str = "STU-001",
        glific_id: str = "12345"
    ) -> Mock:
        """Create mock student document"""
        mock_student = Mock()
        mock_student.name = student_id
        mock_student.student_name = "Test Student"
        mock_student.glific_id = glific_id
        return mock_student
    
    @staticmethod
    def create_glific_contact_response(
        contact_id: str = "12345",
        name: str = "Test Student", 
        fields: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create mock Glific contact fetch response"""
        return {
            "data": {
                "contact": {
                    "contact": {
                        "id": contact_id,
                        "name": name,
                        "phone": "+1234567890",
                        "fields": json.dumps(fields or {})
                    }
                }
            }
        }
    
    @staticmethod
    def create_glific_update_response(
        contact_id: str = "12345",
        success: bool = True,
        fields: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Create mock Glific contact update response"""
        if success:
            return {
                "data": {
                    "updateContact": {
                        "contact": {
                            "id": contact_id,
                            "name": "Test Student",
                            "fields": json.dumps(fields or {
                                "batch_id": {
                                    "value": "BATCH-CS-2024",
                                    "type": "string",
                                    "inserted_at": datetime.now(timezone.utc).isoformat()
                                }
                            })
                        }
                    }
                }
            }
        else:
            return {
                "errors": [
                    {
                        "key": "contact",
                        "message": "Update failed"
                    }
                ]
            }
    
    @staticmethod
    def create_batch_of_students(count: int = 10, batch_prefix: str = "BATCH") -> List[Dict[str, Any]]:
        """Create a batch of mock students"""
        return [
            MockDataFactory.create_backend_student(
                student_id=f"STU-{i:03d}",
                batch=f"{batch_prefix}-{(i-1)//10 + 1}",
                phone=f"+123456{i:04d}",
                name=f"Student {i}"
            )
            for i in range(1, count + 1)
        ]


class APIResponseSimulator:
    """Simulate various API response scenarios"""
    
    def __init__(self):
        self.call_count = 0
        self.responses = []
    
    def add_response(self, response: Dict[str, Any], status_code: int = 200):
        """Add a response to the simulation sequence"""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.json = lambda: response
        self.responses.append(mock_response)
    
    def add_error_response(self, status_code: int = 500, message: str = "Server Error"):
        """Add an error response"""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.json = lambda: {"error": message}
        self.responses.append(mock_response)
    
    def add_timeout(self):
        """Add a timeout exception"""
        import requests
        self.responses.append(requests.exceptions.Timeout("Request timed out"))
    
    def add_connection_error(self):
        """Add a connection error"""
        import requests
        self.responses.append(requests.exceptions.ConnectionError("Connection failed"))
    
    def get_side_effect(self):
        """Get side effect function for mocking"""
        def side_effect(*args, **kwargs):
            if self.call_count >= len(self.responses):
                # Return default success response if we run out of predefined responses
                return Mock(
                    status_code=200,
                    json=lambda: MockDataFactory.create_glific_contact_response()
                )
            
            response = self.responses[self.call_count]
            self.call_count += 1
            
            # If it's an exception, raise it
            if isinstance(response, Exception):
                raise response
            
            return response
        
        return side_effect
    
    def reset(self):
        """Reset the simulator"""
        self.call_count = 0
        self.responses = []


class DatabaseMockHelper:
    """Helper for mocking database operations"""
    
    @staticmethod
    def create_frappe_db_mock():
        """Create a comprehensive Frappe DB mock"""
        mock_db = Mock()
        
        # Default behaviors
        mock_db.exists.return_value = True
        mock_db.begin.return_value = None
        mock_db.commit.return_value = None
        mock_db.rollback.return_value = None
        
        return mock_db
    
    @staticmethod
    def create_get_doc_mock(documents: Dict[str, Any]):
        """Create get_doc mock with predefined documents"""
        def get_doc_side_effect(doctype, name):
            key = f"{doctype}:{name}"
            if key in documents:
                return documents[key]
            else:
                # Return a generic mock
                mock_doc = Mock()
                mock_doc.name = name
                return mock_doc
        
        return get_doc_side_effect
    
    @staticmethod
    def create_get_all_mock(results: List[Dict[str, Any]]):
        """Create get_all mock with predefined results"""
        mock_get_all = Mock()
        mock_get_all.return_value = results
        return mock_get_all


class LoggingCapture:
    """Capture and analyze logging output"""
    
    def __init__(self):
        self.logs = {
            'info': [],
            'warning': [],
            'error': [],
            'debug': []
        }
    
    def create_logger_mock(self):
        """Create a logger mock that captures log messages"""
        mock_logger = Mock()
        
        # Capture different log levels
        mock_logger.info = Mock(side_effect=lambda msg: self.logs['info'].append(msg))
        mock_logger.warning = Mock(side_effect=lambda msg: self.logs['warning'].append(msg))
        mock_logger.error = Mock(side_effect=lambda msg: self.logs['error'].append(msg))
        mock_logger.debug = Mock(side_effect=lambda msg: self.logs['debug'].append(msg))
        
        return mock_logger
    
    def get_logs(self, level: str = None) -> List[str]:
        """Get captured logs for a specific level or all levels"""
        if level:
            return self.logs.get(level, [])
        else:
            all_logs = []
            for level_logs in self.logs.values():
                all_logs.extend(level_logs)
            return all_logs
    
    def assert_logged(self, message: str, level: str = None):
        """Assert that a message was logged"""
        logs_to_check = self.get_logs(level)
        assert any(message in log for log in logs_to_check), f"Message '{message}' not found in logs"
    
    def assert_log_count(self, level: str, expected_count: int):
        """Assert the number of logs at a specific level"""
        actual_count = len(self.logs.get(level, []))
        assert actual_count == expected_count, f"Expected {expected_count} {level} logs, got {actual_count}"
    
    def clear(self):
        """Clear all captured logs"""
        for level in self.logs:
            self.logs[level].clear()


class PerformanceProfiler:
    """Performance profiling utilities"""
    
    def __init__(self):
        self.timings = {}
        self.memory_usage = {}
        
    def time_function(self, func_name: str):
        """Decorator to time function execution"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    end_time = time.perf_counter()
                    execution_time = end_time - start_time
                    
                    if func_name not in self.timings:
                        self.timings[func_name] = []
                    self.timings[func_name].append(execution_time)
            return wrapper
        return decorator
    
    def get_average_time(self, func_name: str) -> float:
        """Get average execution time for a function"""
        if func_name not in self.timings or not self.timings[func_name]:
            return 0.0
        return sum(self.timings[func_name]) / len(self.timings[func_name])
    
    def get_max_time(self, func_name: str) -> float:
        """Get maximum execution time for a function"""
        if func_name not in self.timings or not self.timings[func_name]:
            return 0.0
        return max(self.timings[func_name])
    
    def assert_performance(self, func_name: str, max_time: float):
        """Assert that function performance is within limits"""
        avg_time = self.get_average_time(func_name)
        max_time_recorded = self.get_max_time(func_name)
        
        assert avg_time <= max_time, f"Average time {avg_time:.3f}s exceeds limit {max_time:.3f}s"
        assert max_time_recorded <= max_time * 2, f"Max time {max_time_recorded:.3f}s exceeds reasonable limit"


class TestDataGenerator:
    """Generate realistic test data"""
    
    @staticmethod
    def random_phone():
        """Generate a random phone number"""
        return f"+1{''.join(random.choices(string.digits, k=10))}"
    
    @staticmethod
    def random_name():
        """Generate a random student name"""
        first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Diana", "Eve", "Frank"]
        last_names = ["Doe", "Smith", "Johnson", "Brown", "Wilson", "Davis", "Miller", "Taylor"]
        return f"{random.choice(first_names)} {random.choice(last_names)}"
    
    @staticmethod
    def random_batch_id():
        """Generate a random batch ID"""
        departments = ["CS", "EE", "ME", "CE", "BIO"]
        year = random.randint(2020, 2025)
        return f"BATCH-{random.choice(departments)}-{year}"
    
    @staticmethod
    def generate_realistic_students(count: int) -> List[Dict[str, Any]]:
        """Generate realistic student data"""
        students = []
        for i in range(1, count + 1):
            students.append({
                'name': f'BS-{i:03d}',
                'student_name': TestDataGenerator.random_name(),
                'phone': TestDataGenerator.random_phone(),
                'student_id': f'STU-{i:03d}',
                'batch': TestDataGenerator.random_batch_id(),
                'batch_skeyword': f'batch{i//10 + 1}'
            })
        return students


class ErrorScenarioGenerator:
    """Generate various error scenarios for testing"""
    
    @staticmethod
    def create_network_errors():
        """Create network-related errors"""
        import requests
        return [
            requests.exceptions.Timeout("Request timed out"),
            requests.exceptions.ConnectionError("Connection refused"),
            requests.exceptions.HTTPError("404 Not Found"),
            requests.exceptions.RequestException("Generic request error")
        ]
    
    @staticmethod
    def create_api_error_responses():
        """Create API error response scenarios"""
        return [
            Mock(status_code=400, json=lambda: {"error": "Bad Request"}),
            Mock(status_code=401, json=lambda: {"error": "Unauthorized"}), 
            Mock(status_code=403, json=lambda: {"error": "Forbidden"}),
            Mock(status_code=404, json=lambda: {"error": "Not Found"}),
            Mock(status_code=429, json=lambda: {"error": "Rate limit exceeded"}),
            Mock(status_code=500, json=lambda: {"error": "Internal server error"}),
            Mock(status_code=502, json=lambda: {"error": "Bad gateway"}),
            Mock(status_code=503, json=lambda: {"error": "Service unavailable"})
        ]
    
    @staticmethod
    def create_database_errors():
        """Create database-related errors"""
        return [
            Exception("Database connection lost"),
            Exception("Transaction deadlock detected"),
            Exception("Table doesn't exist"),
            Exception("Permission denied")
        ]
    
    @staticmethod
    def create_data_validation_errors():
        """Create data validation error scenarios"""
        return [
            {"student_id": None, "batch": "BATCH-1"},  # Missing student ID
            {"student_id": "", "batch": "BATCH-1"},    # Empty student ID
            {"student_id": "STU-001", "batch": None},  # Missing batch
            {"student_id": "STU-001", "batch": ""},    # Empty batch
            {"student_id": "STU-001", "phone": ""},    # Missing phone
        ]


class AssertionHelpers:
    """Helper functions for common test assertions"""
    
    @staticmethod
    def assert_result_structure(result: Dict[str, Any], expected_keys: List[str]):
        """Assert that result has expected structure"""
        assert isinstance(result, dict), "Result should be a dictionary"
        for key in expected_keys:
            assert key in result, f"Missing key '{key}' in result"
    
    @staticmethod
    def assert_processing_result(result: Dict[str, Any]):
        """Assert standard processing result structure"""
        expected_keys = ["updated", "skipped", "errors", "total_processed"]
        AssertionHelpers.assert_result_structure(result, expected_keys)
        
        # Verify numeric values
        for key in expected_keys:
            assert isinstance(result[key], int), f"{key} should be an integer"
            assert result[key] >= 0, f"{key} should be non-negative"
        
        # Verify totals add up
        total = result["updated"] + result["skipped"] + result["errors"]
        assert total == result["total_processed"], "Totals don't add up correctly"
    
    @staticmethod
    def assert_glific_api_called_correctly(mock_post, expected_call_count: int = None):
        """Assert Glific API was called correctly"""
        assert mock_post.called, "Glific API should have been called"
        
        if expected_call_count:
            assert mock_post.call_count == expected_call_count, \
                f"Expected {expected_call_count} API calls, got {mock_post.call_count}"
        
        # Verify all calls have proper structure
        for call in mock_post.call_args_list:
            args, kwargs = call
            
            # Should have URL and headers
            assert len(args) >= 1, "API call should have URL"
            assert 'headers' in kwargs, "API call should have headers"
            assert 'json' in kwargs, "API call should have JSON payload"
            
            # Verify JSON payload structure
            payload = kwargs['json']
            assert 'query' in payload, "Payload should have GraphQL query"
    
    @staticmethod
    def assert_database_transaction_handling(mock_db):
        """Assert proper database transaction handling"""
        mock_db.begin.assert_called()
        
        # Should have either commit or rollback, but not both
        commit_called = mock_db.commit.called
        rollback_called = mock_db.rollback.called
        
        assert commit_called or rollback_called, "Should have commit or rollback"
        assert not (commit_called and rollback_called), "Should not have both commit and rollback"
    
    @staticmethod
    def assert_error_logged(mock_logger, error_message: str):
        """Assert that an error was properly logged"""
        mock_logger.error.assert_called()
        
        # Check if error message appears in any log call
        logged_messages = [call[0][0] for call in mock_logger.error.call_args_list]
        assert any(error_message in msg for msg in logged_messages), \
            f"Error message '{error_message}' not found in logs"


class TestEnvironmentSetup:
    """Setup and teardown test environments"""
    
    @staticmethod
    def setup_clean_test_environment():
        """Setup a clean test environment"""
        # This would typically set up test database, clear caches, etc.
        pass
    
    @staticmethod
    def setup_frappe_test_environment():
        """Setup Frappe test environment"""
        # Mock all Frappe components
        mocks = {}
        
        with patch('frappe.db') as mock_db, \
             patch('frappe.logger') as mock_logger, \
             patch('frappe.get_doc') as mock_get_doc, \
             patch('frappe.get_all') as mock_get_all, \
             patch('frappe.whitelist') as mock_whitelist:
            
            # Setup default behaviors
            mock_db.exists.return_value = True
            mock_db.begin.return_value = None
            mock_db.commit.return_value = None
            mock_db.rollback.return_value = None
            
            mocks['db'] = mock_db
            mocks['logger'] = mock_logger
            mocks['get_doc'] = mock_get_doc
            mocks['get_all'] = mock_get_all
            mocks['whitelist'] = mock_whitelist
            
            return mocks
    
    @staticmethod
    def setup_glific_test_environment():
        """Setup Glific API test environment"""
        with patch('glific_batch_id_update.get_glific_settings') as mock_settings, \
             patch('glific_batch_id_update.get_glific_auth_headers') as mock_headers, \
             patch('requests.post') as mock_post:
            
            # Setup default settings
            mock_settings.return_value = Mock(api_url="https://test-api.glific.org")
            mock_headers.return_value = {"Authorization": "Bearer test-token"}
            
            # Setup default successful response
            mock_post.return_value = Mock(
                status_code=200,
                json=lambda: MockDataFactory.create_glific_contact_response()
            )
            
            return {
                'settings': mock_settings,
                'headers': mock_headers,
                'post': mock_post
            }


class TestReportGenerator:
    """Generate test reports and summaries"""
    
    def __init__(self):
        self.test_results = []
        self.performance_data = {}
        self.coverage_data = {}
    
    def record_test_result(self, test_name: str, status: str, duration: float, details: Dict = None):
        """Record a test result"""
        self.test_results.append({
            'name': test_name,
            'status': status,  # 'passed', 'failed', 'skipped'
            'duration': duration,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        })
    
    def record_performance_data(self, operation: str, duration: float, memory_usage: int = None):
        """Record performance data"""
        if operation not in self.performance_data:
            self.performance_data[operation] = []
        
        self.performance_data[operation].append({
            'duration': duration,
            'memory_usage': memory_usage,
            'timestamp': datetime.now().isoformat()
        })
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate test summary"""
        total_tests = len(self.test_results)
        passed = len([r for r in self.test_results if r['status'] == 'passed'])
        failed = len([r for r in self.test_results if r['status'] == 'failed'])
        skipped = len([r for r in self.test_results if r['status'] == 'skipped'])
        
        total_duration = sum(r['duration'] for r in self.test_results)
        
        return {
            'summary': {
                'total_tests': total_tests,
                'passed': passed,
                'failed': failed,
                'skipped': skipped,
                'pass_rate': (passed / total_tests * 100) if total_tests > 0 else 0,
                'total_duration': total_duration
            },
            'performance': self._summarize_performance(),
            'failed_tests': [r for r in self.test_results if r['status'] == 'failed']
        }
    
    def _summarize_performance(self) -> Dict[str, Any]:
        """Summarize performance data"""
        summary = {}
        for operation, data in self.performance_data.items():
            durations = [d['duration'] for d in data]
            summary[operation] = {
                'count': len(durations),
                'avg_duration': sum(durations) / len(durations) if durations else 0,
                'min_duration': min(durations) if durations else 0,
                'max_duration': max(durations) if durations else 0
            }
        return summary
    
    def export_to_json(self, filename: str):
        """Export results to JSON file"""
        report_data = {
            'test_results': self.test_results,
            'performance_data': self.performance_data,
            'summary': self.generate_summary(),
            'generated_at': datetime.now().isoformat()
        }
        
        with open(filename, 'w') as f:
            json.dump(report_data, f, indent=2)


class TestConfigManager:
    """Manage test configuration and settings"""
    
    def __init__(self):
        self.config = {
            'api_url': 'https://test-api.glific.org',
            'timeout': 30,
            'retry_count': 3,
            'batch_size': 10,
            'performance_thresholds': {
                'single_student_processing': 1.0,  # seconds
                'batch_processing_per_student': 0.1,  # seconds per student
                'memory_increase_limit': 100 * 1024 * 1024,  # 100MB
            }
        }
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """Set configuration value"""
        self.config[key] = value
    
    def load_from_file(self, filename: str):
        """Load configuration from JSON file"""
        try:
            with open(filename, 'r') as f:
                file_config = json.load(f)
                self.config.update(file_config)
        except FileNotFoundError:
            # Use default config if file doesn't exist
            pass
    
    def save_to_file(self, filename: str):
        """Save configuration to JSON file"""
        with open(filename, 'w') as f:
            json.dump(self.config, f, indent=2)


# Global test configuration instance
test_config = TestConfigManager()


# Decorator for parameterized tests
def parameterized_test(parameters):
    """Decorator for creating parameterized tests"""
    def decorator(test_func):
        def wrapper():
            for params in parameters:
                try:
                    if isinstance(params, dict):
                        test_func(**params)
                    else:
                        test_func(*params)
                except Exception as e:
                    raise AssertionError(f"Test failed with parameters {params}: {e}")
        return wrapper
    return decorator


# Test data validation functions
def validate_student_data(student_data: Dict[str, Any]) -> List[str]:
    """Validate student data and return list of errors"""
    errors = []
    
    required_fields = ['student_id', 'student_name', 'phone', 'batch']
    for field in required_fields:
        if field not in student_data or not student_data[field]:
            errors.append(f"Missing or empty {field}")
    
    # Validate phone number format
    phone = student_data.get('phone', '')
    if phone and not phone.startswith('+') or len(phone) < 10:
        errors.append("Invalid phone number format")
    
    # Validate student ID format
    student_id = student_data.get('student_id', '')
    if student_id and not student_id.startswith('STU-'):
        errors.append("Invalid student ID format")
    
    return errors


def validate_processing_result(result: Dict[str, Any]) -> List[str]:
    """Validate processing result structure"""
    errors = []
    
    required_fields = ['updated', 'skipped', 'errors', 'total_processed']
    for field in required_fields:
        if field not in result:
            errors.append(f"Missing field: {field}")
        elif not isinstance(result[field], int):
            errors.append(f"Field {field} should be integer")
        elif result[field] < 0:
            errors.append(f"Field {field} should be non-negative")
    
    # Validate totals
    if all(field in result for field in required_fields):
        expected_total = result['updated'] + result['skipped'] + result['errors']
        if expected_total != result['total_processed']:
            errors.append("Total processed doesn't match sum of individual counts")
    
    return errors


# Context managers for test scenarios
class MockTimeContextManager:
    """Context manager for mocking time-related functions"""
    
    def __init__(self, mock_time=None):
        self.mock_time = mock_time or datetime.now()
        
    def __enter__(self):
        self.time_patch = patch('time.time', return_value=self.mock_time.timestamp())
        self.datetime_patch = patch('datetime.datetime.now', return_value=self.mock_time)
        
        self.time_patch.start()
        self.datetime_patch.start()
        
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.time_patch.stop()
        self.datetime_patch.stop()


class MockNetworkContextManager:
    """Context manager for mocking network conditions"""
    
    def __init__(self, simulate_slow=False, simulate_failures=False, failure_rate=0.3):
        self.simulate_slow = simulate_slow
        self.simulate_failures = simulate_failures
        self.failure_rate = failure_rate
        self.original_post = None
        
    def __enter__(self):
        import requests
        self.original_post = requests.post
        
        def mock_post(*args, **kwargs):
            # Simulate slow network
            if self.simulate_slow:
                time.sleep(random.uniform(0.5, 2.0))
            
            # Simulate random failures
            if self.simulate_failures and random.random() < self.failure_rate:
                raise requests.exceptions.ConnectionError("Simulated network failure")
            
            # Return successful response
            return Mock(
                status_code=200,
                json=lambda: MockDataFactory.create_glific_contact_response()
            )
        
        requests.post = mock_post
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        import requests
        requests.post = self.original_post


# Main test utilities export
__all__ = [
    'MockDataFactory',
    'APIResponseSimulator', 
    'DatabaseMockHelper',
    'LoggingCapture',
    'PerformanceProfiler',
    'TestDataGenerator',
    'ErrorScenarioGenerator',
    'AssertionHelpers',
    'TestEnvironmentSetup',
    'TestReportGenerator',
    'TestConfigManager',
    'test_config',
    'parameterized_test',
    'validate_student_data',
    'validate_processing_result',
    'MockTimeContextManager',
    'MockNetworkContextManager'
]