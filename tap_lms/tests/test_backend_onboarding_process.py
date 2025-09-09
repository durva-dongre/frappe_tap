# conftest.py - Pytest configuration and fixtures
import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@pytest.fixture(scope="session", autouse=True)
def setup_frappe_environment():
    """Setup mock Frappe environment for all tests"""
    # Mock frappe module
    frappe_mock = Mock()
    
    # Mock common frappe functions
    frappe_mock.whitelist = lambda func: func
    frappe_mock.log_error = Mock()
    frappe_mock.logger = Mock()
    frappe_mock.get_all = Mock()
    frappe_mock.get_doc = Mock()
    frappe_mock.new_doc = Mock()
    frappe_mock.get_value = Mock()
    frappe_mock.delete_doc = Mock()
    frappe_mock.enqueue = Mock()
    frappe_mock.publish_progress = Mock()
    
    # Mock frappe.db
    frappe_mock.db = Mock()
    frappe_mock.db.sql = Mock()
    frappe_mock.db.exists = Mock()
    frappe_mock.db.get_value = Mock()
    frappe_mock.db.set_value = Mock()
    frappe_mock.db.commit = Mock()
    frappe_mock.db.rollback = Mock()
    frappe_mock.db.count = Mock()
    frappe_mock.db.table_exists = Mock()
    
    # Mock frappe.utils
    frappe_mock.utils = Mock()
    frappe_mock.utils.nowdate = Mock(return_value="2025-01-15")
    frappe_mock.utils.nowtime = Mock(return_value="10:30:00")
    frappe_mock.utils.now = Mock(return_value="2025-01-15 10:30:00")
    frappe_mock.utils.getdate = Mock()
    
    # Mock frappe.get_meta
    frappe_mock.get_meta = Mock()
    
    # Mock frappe translation
    frappe_mock._ = lambda x: x
    
    # Add to sys.modules
    sys.modules['frappe'] = frappe_mock
    sys.modules['frappe.utils'] = frappe_mock.utils
    
    # Mock tap_lms modules
    tap_lms_mock = Mock()
    tap_lms_api_mock = Mock()
    tap_lms_glific_mock = Mock()
    
    # Mock specific functions from tap_lms.api
    tap_lms_api_mock.get_course_level = Mock(return_value="CL001")
    
    # Mock specific functions from tap_lms.glific_integration
    tap_lms_glific_mock.create_or_get_glific_group_for_batch = Mock()
    tap_lms_glific_mock.add_student_to_glific_for_onboarding = Mock()
    tap_lms_glific_mock.get_contact_by_phone = Mock()
    tap_lms_glific_mock.add_contact_to_group = Mock()
    tap_lms_glific_mock.update_contact_fields = Mock()
    
    sys.modules['tap_lms'] = tap_lms_mock
    sys.modules['tap_lms.api'] = tap_lms_api_mock
    sys.modules['tap_lms.glific_integration'] = tap_lms_glific_mock
    
    yield frappe_mock
    
    # Cleanup
    if 'frappe' in sys.modules:
        del sys.modules['frappe']
    if 'frappe.utils' in sys.modules:
        del sys.modules['frappe.utils']
    if 'tap_lms' in sys.modules:
        del sys.modules['tap_lms']
    if 'tap_lms.api' in sys.modules:
        del sys.modules['tap_lms.api']
    if 'tap_lms.glific_integration' in sys.modules:
        del sys.modules['tap_lms.glific_integration']

@pytest.fixture
def sample_backend_student():
    """Sample backend student data for testing"""
    student = Mock()
    student.name = "BS001"
    student.student_name = "John Doe"
    student.phone = "9876543210"
    student.gender = "Male"
    student.batch = "BT001"
    student.course_vertical = "Math"
    student.grade = "5"
    student.school = "SCH001"
    student.language = "EN"
    student.processing_status = "Pending"
    student.student_id = None
    student.batch_skeyword = "MATH5"
    return student

@pytest.fixture
def sample_glific_contact():
    """Sample Glific contact data for testing"""
    return {
        "id": "GC001",
        "name": "John Doe",
        "phone": "919876543210"
    }

@pytest.fixture
def sample_batch():
    """Sample batch data for testing"""
    batch = Mock()
    batch.name = "BSO001"
    batch.set_name = "Test Batch Set"
    batch.upload_date = "2025-01-15"
    batch.uploaded_by = "admin"
    batch.student_count = 10
    batch.processed_student_count = 0
    batch.status = "Draft"
    return batch

# pytest.ini content (create as separate file)
PYTEST_INI_CONTENT = """[tool:pytest]
testpaths = tests
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --color=yes
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
    glific: Tests involving Glific integration
    database: Tests requiring database operations
"""

# requirements-test.txt content
REQUIREMENTS_TEST_CONTENT = """pytest>=7.0.0
pytest-mock>=3.10.0
pytest-cov>=4.0.0
pytest-xdist>=3.0.0
coverage>=7.0.0
mock>=4.0.0
"""

# test_integration.py - Integration tests
INTEGRATION_TESTS_CONTENT = '''import pytest
from unittest.mock import Mock, patch, call
import json

class TestEndToEndIntegration:
    """End-to-end integration tests"""
    
    @pytest.fixture
    def complete_batch_setup(self, sample_batch, sample_backend_student, sample_glific_contact):
        """Complete batch setup for integration testing"""
        return {
            'batch': sample_batch,
            'students': [sample_backend_student],
            'glific_contact': sample_glific_contact
        }
    
    def test_complete_student_onboarding_flow(self, complete_batch_setup):
        """Test complete student onboarding flow from batch to student creation"""
        from tap_lms.backend_onboarding import process_batch_job
        
        with patch('frappe.db') as mock_db, \\
             patch('frappe.get_doc') as mock_get_doc, \\
             patch('frappe.get_all') as mock_get_all, \\
             patch('frappe.new_doc') as mock_new_doc, \\
             patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
             patch('tap_lms.backend_onboarding.get_initial_stage') as mock_get_stage, \\
             patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
             patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student, \\
             patch('tap_lms.backend_onboarding.get_course_level_with_validation_backend') as mock_get_course:
            
            # Setup mocks
            batch = complete_batch_setup['batch']
            student = complete_batch_setup['students'][0]
            
            mock_get_doc.side_effect = [batch, student]
            mock_get_all.side_effect = [
                [{'name': 'BS001', 'batch_skeyword': 'MATH5'}],  # Students
                [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]  # Batch onboarding
            ]
            
            mock_create_group.return_value = {"group_id": "GG001"}
            mock_get_stage.return_value = "STAGE001"
            mock_process_glific.return_value = complete_batch_setup['glific_contact']
            mock_find_student.return_value = None  # New student
            mock_get_course.return_value = "CL001"
            
            # Mock new student creation
            mock_student_doc = Mock()
            mock_student_doc.name = "STU001"
            mock_student_doc.glific_id = None
            mock_student_doc.append = Mock()
            mock_student_doc.insert = Mock()
            mock_new_doc.return_value = mock_student_doc
            
            # Mock database operations
            mock_db.exists.return_value = False  # LearningState and EngagementState don't exist
            mock_db.commit = Mock()
            mock_db.count.return_value = 1
            
            # Execute
            result = process_batch_job("BSO001")
            
            # Verify results
            assert result['success_count'] == 1
            assert result['failure_count'] == 0
            assert len(result['results']['success']) == 1
            
            # Verify student was created
            mock_new_doc.assert_called_with("Student")
            mock_student_doc.insert.assert_called_once()
            
            # Verify Glific integration
            mock_process_glific.assert_called_once()
            
            # Verify course level assignment
            mock_get_course.assert_called_once()

    def test_batch_processing_with_mixed_results(self, complete_batch_setup):
        """Test batch processing with both successful and failed students"""
        from tap_lms.backend_onboarding import process_batch_job
        
        with patch('frappe.db') as mock_db, \\
             patch('frappe.get_doc') as mock_get_doc, \\
             patch('frappe.get_all') as mock_get_all, \\
             patch('frappe.new_doc') as mock_new_doc, \\
             patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
             patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
             patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student:
            
            batch = complete_batch_setup['batch']
            
            # Create two students - one will succeed, one will fail
            student1 = Mock()
            student1.name = "BS001"
            student1.student_name = "John Doe"
            student1.phone = "9876543210"
            
            student2 = Mock()
            student2.name = "BS002"
            student2.student_name = "Jane Doe"
            student2.phone = "9876543211"
            
            mock_get_doc.side_effect = [batch, student1, student2]
            mock_get_all.side_effect = [
                [{'name': 'BS001', 'batch_skeyword': 'MATH5'}, {'name': 'BS002', 'batch_skeyword': 'MATH5'}],
                [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]
            ]
            
            mock_create_group.return_value = {"group_id": "GG001"}
            mock_find_student.return_value = None
            
            # First student succeeds, second fails
            mock_student_doc = Mock()
            mock_student_doc.name = "STU001"
            mock_student_doc.insert = Mock()
            mock_new_doc.return_value = mock_student_doc
            
            # Mock Glific success for first, failure for second
            mock_process_glific.side_effect = [
                complete_batch_setup['glific_contact'],  # Success
                Exception("Glific API error")  # Failure
            ]
            
            mock_db.commit = Mock()
            mock_db.rollback = Mock()
            mock_db.count.return_value = 1
            
            result = process_batch_job("BSO001")
            
            assert result['success_count'] == 1
            assert result['failure_count'] == 1


class TestErrorRecoveryScenarios:
    """Test error recovery and resilience scenarios"""
    
    def test_database_connection_failure_recovery(self, sample_batch):
        """Test recovery from database connection failures"""
        from tap_lms.backend_onboarding import process_batch_job
        
        with patch('frappe.db') as mock_db, \\
             patch('frappe.get_doc') as mock_get_doc, \\
             patch('frappe.get_all') as mock_get_all:
            
            mock_get_doc.return_value = sample_batch
            mock_get_all.return_value = []  # No students
            
            # Simulate database connection failure
            mock_db.commit.side_effect = Exception("Database connection lost")
            mock_db.rollback = Mock()
            
            with pytest.raises(Exception, match="Database connection lost"):
                process_batch_job("BSO001")
            
            # Verify rollback was called
            mock_db.rollback.assert_called()

    def test_glific_api_unavailable_graceful_handling(self, sample_backend_student, sample_batch):
        """Test graceful handling when Glific API is unavailable"""
        from tap_lms.backend_onboarding import process_batch_job
        
        with patch('frappe.db') as mock_db, \\
             patch('frappe.get_doc') as mock_get_doc, \\
             patch('frappe.get_all') as mock_get_all, \\
             patch('frappe.new_doc') as mock_new_doc, \\
             patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
             patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
             patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student:
            
            mock_get_doc.side_effect = [sample_batch, sample_backend_student]
            mock_get_all.side_effect = [
                [{'name': 'BS001', 'batch_skeyword': 'MATH5'}],
                [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]
            ]
            
            # Glific completely unavailable
            mock_create_group.side_effect = Exception("Glific API unavailable")
            mock_process_glific.return_value = None
            mock_find_student.return_value = None
            
            # Student creation should still succeed without Glific
            mock_student_doc = Mock()
            mock_student_doc.name = "STU001"
            mock_student_doc.glific_id = None
            mock_student_doc.insert = Mock()
            mock_new_doc.return_value = mock_student_doc
            
            mock_db.exists.return_value = False
            mock_db.commit = Mock()
            mock_db.count.return_value = 1
            
            result = process_batch_job("BSO001")
            
            # Should succeed even without Glific
            assert result['success_count'] == 1
            assert result['failure_count'] == 0

    def test_partial_data_corruption_handling(self, sample_batch):
        """Test handling of partially corrupted data"""
        from tap_lms.backend_onboarding import validate_enrollment_data
        
        with patch('frappe.db') as mock_db:
            # Mock corrupted enrollment data
            mock_db.sql.return_value = [
                {
                    'student_id': 'STU001',
                    'enrollment_id': 'ENR001',
                    'course': None,  # Corrupted - NULL course
                    'batch': 'BT001',
                    'grade': '5'
                },
                {
                    'student_id': 'STU001',
                    'enrollment_id': 'ENR002',
                    'course': 'INVALID_COURSE',  # Corrupted - invalid reference
                    'batch': 'BT002',
                    'grade': '6'
                }
            ]
            
            mock_db.exists.return_value = False  # Course doesn't exist
            
            result = validate_enrollment_data("John Doe", "9876543210")
            
            assert result['total_enrollments'] == 2
            assert result['broken_enrollments'] == 1  # Only the invalid course, not NULL
            assert result['broken_details'][0]['invalid_course'] == 'INVALID_COURSE'


class TestPerformanceScenarios:
    """Test performance-related scenarios"""
    
    @pytest.mark.slow
    def test_large_batch_processing_performance(self):
        """Test processing of large batches (performance test)"""
        from tap_lms.backend_onboarding import process_batch_job
        
        # Create 100 mock students
        large_student_list = []
        for i in range(100):
            large_student_list.append({
                'name': f'BS{i:03d}',
                'batch_skeyword': 'MATH5'
            })
        
        with patch('frappe.db') as mock_db, \\
             patch('frappe.get_doc') as mock_get_doc, \\
             patch('frappe.get_all') as mock_get_all, \\
             patch('frappe.new_doc') as mock_new_doc, \\
             patch('tap_lms.backend_onboarding.create_or_get_glific_group_for_batch') as mock_create_group, \\
             patch('tap_lms.backend_onboarding.process_glific_contact') as mock_process_glific, \\
             patch('tap_lms.backend_onboarding.find_existing_student_by_phone_and_name') as mock_find_student, \\
             patch('tap_lms.backend_onboarding.update_job_progress') as mock_update_progress:
            
            # Setup mocks for large batch
            mock_batch = Mock()
            mock_batch.status = "Processing"
            mock_get_doc.return_value = mock_batch
            
            mock_get_all.side_effect = [
                large_student_list,  # Large student list
                [{'batch_skeyword': 'MATH5', 'name': 'BO001', 'kit_less': False}]
            ]
            
            mock_create_group.return_value = {"group_id": "GG001"}
            mock_process_glific.return_value = {"id": "GC001"}
            mock_find_student.return_value = None
            
            # Mock student creation to be fast
            mock_student_doc = Mock()
            mock_student_doc.name = "STU001"
            mock_student_doc.insert = Mock()
            mock_new_doc.return_value = mock_student_doc
            
            mock_db.exists.return_value = False
            mock_db.commit = Mock()
            mock_db.count.return_value = 100
            
            # Create mock students for get_doc calls
            def get_doc_side_effect(doctype, name):
                if doctype == "Backend Student Onboarding":
                    return mock_batch
                else:  # Backend Students
                    mock_student = Mock()
                    mock_student.name = name
                    mock_student.student_name = f"Student {name}"
                    mock_student.phone = f"98765432{name[-2:]}"
                    mock_student.batch_skeyword = "MATH5"
                    return mock_student
            
            mock_get_doc.side_effect = get_doc_side_effect
            
            result = process_batch_job("BSO001")
            
            # Verify all students were processed
            assert result['success_count'] == 100
            assert result['failure_count'] == 0
            
            # Verify progress updates were called
            assert mock_update_progress.call_count > 0

    def test_concurrent_batch_processing_safety(self):
        """Test that concurrent batch processing is handled safely"""
        from tap_lms.backend_onboarding import process_batch
        
        with patch('frappe.get_doc') as mock_get_doc, \\
             patch('frappe.enqueue') as mock_enqueue:
            
            mock_batch = Mock()
            mock_batch.status = "Draft"
            mock_get_doc.return_value = mock_batch
            
            mock_job = Mock()
            mock_job.id = "JOB001"
            mock_enqueue.return_value = mock_job
            
            # Process same batch twice (simulating concurrent requests)
            result1 = process_batch("BSO001", use_background_job=True)
            result2 = process_batch("BSO001", use_background_job=True)
            
            # Both should get job IDs (framework should handle concurrency)
            assert "job_id" in result1
            assert "job_id" in result2
            
            # Batch status should be set to Processing
            assert mock_batch.status == "Processing"
            assert mock_batch.save.call_count >= 2  # Called at least twice


# Run configuration script
if __name__ == "__main__":
    # Create pytest.ini file
    with open("pytest.ini", "w") as f:
        f.write(PYTEST_INI_CONTENT)
    
    # Create requirements-test.txt file  
    with open("requirements-test.txt", "w") as f:
        f.write(REQUIREMENTS_TEST_CONTENT)
    
    # Create integration tests file
    with open("test_integration.py", "w") as f:
        f.write(INTEGRATION_TESTS_CONTENT)
    
    print("Pytest configuration files created successfully!")
    print("To run tests:")
    print("1. Install test dependencies: pip install -r requirements-test.txt")
    print("2. Run all tests: pytest")
    print("3. Run with coverage: pytest --cov=tap_lms.backend_onboarding")
    print("4. Run specific test class: pytest -k TestPhoneNumberNormalization")
'''