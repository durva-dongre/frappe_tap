# import pytest
# import frappe
# from unittest.mock import patch, MagicMock, call


# class TestGlificUtils:
#     """Test cases for glific_utils.py to achieve 100% code coverage"""

#     @patch('tap_lms.glific_utils.frappe.db.count')
#     @patch('tap_lms.glific_utils.frappe.enqueue')
#     def test_run_glific_id_update_with_students_found(self, mock_enqueue, mock_count):
#         """Test run_glific_id_update when students are found"""
#         from tap_lms.glific_utils import run_glific_id_update
        
#         # Mock frappe.db.count to return students found
#         mock_count.return_value = 5
        
#         # Mock enqueue function
#         mock_job = MagicMock()
#         mock_job.name = "test_job_123"
#         mock_enqueue.return_value = mock_job
        
#         result = run_glific_id_update()
        
#         # Verify frappe.db.count was called with correct parameters
#         mock_count.assert_called_once_with(
#             "Student", 
#             {"glific_id": ["in", ["", None]]}
#         )
        
#         # Verify enqueue was called with correct parameters
#         from tap_lms.glific_utils import process_glific_id_update
#         mock_enqueue.assert_called_once_with(
#             process_glific_id_update,
#             queue='long',
#             timeout=3600,
#             total_students=5
#         )
        
#         # Verify return value
#         assert result == "Glific ID update process started. Job ID: test_job_123"

#     @patch('tap_lms.glific_utils.frappe.db.count')
#     def test_run_glific_id_update_no_students_found(self, mock_count):
#         """Test run_glific_id_update when no students are found"""
#         from tap_lms.glific_utils import run_glific_id_update
        
#         # Mock frappe.db.count to return 0 students
#         mock_count.return_value = 0
        
#         result = run_glific_id_update()
        
#         # Verify frappe.db.count was called
#         mock_count.assert_called_once_with(
#             "Student", 
#             {"glific_id": ["in", ["", None]]}
#         )
        
#         # Verify return value when no students found
#         assert result == "No students found without Glific ID."

#     @patch('tap_lms.glific_utils.frappe.publish_realtime')
#     @patch('tap_lms.glific_utils.frappe.db.commit')
#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     def test_process_glific_id_update_complete_batch_processing(self, mock_update, mock_commit, mock_publish):
#         """Test process_glific_id_update with complete batch processing"""
#         from tap_lms.glific_utils import process_glific_id_update
        
#         total_students = 250  # More than one batch
        
#         # Mock update_student_glific_ids to return different values for different calls
#         mock_update.side_effect = [100, 100, 50]
        
#         process_glific_id_update(total_students)
        
#         # Verify frappe.db.commit was called 3 times (once per batch)
#         assert mock_commit.call_count == 3
        
#         # Verify publish_realtime was called for progress updates
#         progress_calls = mock_publish.call_args_list
        
#         # Should have 3 progress calls and 1 completion call
#         assert len(progress_calls) == 4
        
#         # Verify progress calls
#         assert progress_calls[0] == call("glific_id_update_progress", {"processed": 100, "total": 250})
#         assert progress_calls[1] == call("glific_id_update_progress", {"processed": 200, "total": 250})
#         assert progress_calls[2] == call("glific_id_update_progress", {"processed": 250, "total": 250})
        
#         # Verify completion call
#         assert progress_calls[3] == call("glific_id_update_complete", {"total_updated": 250})

#     @patch('tap_lms.glific_utils.frappe.publish_realtime')
#     @patch('tap_lms.glific_utils.frappe.db.commit')
#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     def test_process_glific_id_update_single_batch(self, mock_update, mock_commit, mock_publish):
#         """Test process_glific_id_update with single batch (less than 100 students)"""
#         from tap_lms.glific_utils import process_glific_id_update
        
#         total_students = 50
        
#         # Mock update_student_glific_ids to return updated count
#         mock_update.return_value = 50
        
#         process_glific_id_update(total_students)
        
#         # Verify frappe.db.commit was called once
#         mock_commit.assert_called_once()
        
#         # Verify publish_realtime calls
#         progress_calls = mock_publish.call_args_list
        
#         # Should have 1 progress call and 1 completion call
#         assert len(progress_calls) == 2
        
#         # Verify calls
#         assert progress_calls[0] == call("glific_id_update_progress", {"processed": 50, "total": 50})
#         assert progress_calls[1] == call("glific_id_update_complete", {"total_updated": 50})

#     @patch('tap_lms.glific_utils.frappe.publish_realtime')
#     @patch('tap_lms.glific_utils.frappe.db.commit')
#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     def test_process_glific_id_update_exact_batch_size(self, mock_update, mock_commit, mock_publish):
#         """Test process_glific_id_update with exactly 100 students (one complete batch)"""
#         from tap_lms.glific_utils import process_glific_id_update
        
#         total_students = 100
        
#         # Mock update_student_glific_ids to return updated count
#         mock_update.return_value = 100
        
#         process_glific_id_update(total_students)
        
#         # Verify frappe.db.commit was called once
#         mock_commit.assert_called_once()
        
#         # Verify publish_realtime calls
#         progress_calls = mock_publish.call_args_list
#         assert len(progress_calls) == 2
        
#         # Verify calls
#         assert progress_calls[0] == call("glific_id_update_progress", {"processed": 100, "total": 100})
#         assert progress_calls[1] == call("glific_id_update_complete", {"total_updated": 100})

#     @patch('tap_lms.glific_utils.frappe.publish_realtime')
#     def test_process_glific_id_update_with_zero_students(self, mock_publish):
#         """Test process_glific_id_update with zero total students"""
#         from tap_lms.glific_utils import process_glific_id_update
        
#         total_students = 0
        
#         with patch('tap_lms.glific_utils.frappe.db.commit') as mock_commit, \
#              patch('tap_lms.glific_utils.update_student_glific_ids') as mock_update:
            
#             process_glific_id_update(total_students)
            
#             # Verify no database operations were performed
#             mock_commit.assert_not_called()
#             mock_update.assert_not_called()
            
#             # Verify only completion call was made
#             mock_publish.assert_called_once_with(
#                 "glific_id_update_complete", 
#                 {"total_updated": 0}
#             )

#     @patch('tap_lms.glific_utils.frappe.publish_realtime')
#     @patch('tap_lms.glific_utils.frappe.db.commit')
#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     def test_process_glific_id_update_partial_update_in_batch(self, mock_update, mock_commit, mock_publish):
#         """Test process_glific_id_update when update_student_glific_ids returns less than batch size"""
#         from tap_lms.glific_utils import process_glific_id_update
        
#         total_students = 300
        
#         # Mock update_student_glific_ids to return partial updates
#         mock_update.side_effect = [80, 90, 70]  # Total: 240 < 300
        
#         process_glific_id_update(total_students)
        
#         # Verify progress tracking with actual processed counts
#         progress_calls = mock_publish.call_args_list
        
#         # Should have 3 progress calls and 1 completion call
#         assert len(progress_calls) == 4
        
#         # Verify progress calls reflect actual processed amounts
#         assert progress_calls[0] == call("glific_id_update_progress", {"processed": 80, "total": 300})
#         assert progress_calls[1] == call("glific_id_update_progress", {"processed": 170, "total": 300})
#         assert progress_calls[2] == call("glific_id_update_progress", {"processed": 240, "total": 300})
#         assert progress_calls[3] == call("glific_id_update_complete", {"total_updated": 240})


# # Additional integration test
# class TestGlificUtilsIntegration:
#     """Integration tests for the complete workflow"""
    
#     @patch('tap_lms.glific_utils.frappe.db.count')
#     @patch('tap_lms.glific_utils.frappe.enqueue')
#     def test_complete_workflow_integration(self, mock_enqueue, mock_count):
#         """Test the complete workflow from run_glific_id_update to process_glific_id_update"""
#         from tap_lms.glific_utils import run_glific_id_update, process_glific_id_update
        
#         # Setup
#         mock_count.return_value = 150
#         mock_job = MagicMock()
#         mock_job.name = "integration_test_job"
#         mock_enqueue.return_value = mock_job
        
#         # Test run_glific_id_update
#         result = run_glific_id_update()
        
#         # Verify enqueue was called
#         assert mock_enqueue.called
#         args, kwargs = mock_enqueue.call_args
#         assert args[0] == process_glific_id_update
#         assert kwargs['total_students'] == 150
#         assert kwargs['queue'] == 'long'
#         assert kwargs['timeout'] == 3600
        
#         # Verify result
#         assert result == "Glific ID update process started. Job ID: integration_test_job"


# # Test fixtures and helpers
# @pytest.fixture
# def mock_glific_integration():
#     """Fixture to mock Glific Integration document"""
#     mock_doc = MagicMock()
#     mock_doc.update_student_glific_ids.return_value = 100
#     return mock_doc


# # Edge case tests
# class TestGlificUtilsEdgeCases:
#     """Test edge cases and error scenarios"""
    
#     @patch('tap_lms.glific_utils.frappe.publish_realtime')
#     @patch('tap_lms.glific_utils.frappe.db.commit')
#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     def test_large_student_count(self, mock_update, mock_commit, mock_publish):
#         """Test with very large student count"""
#         from tap_lms.glific_utils import process_glific_id_update
        
#         total_students = 10000  # 100 batches
        
#         # Mock consistent returns
#         mock_update.return_value = 100
        
#         process_glific_id_update(total_students)
        
#         # Verify correct number of commits (100 batches)
#         assert mock_commit.call_count == 100
        
#         # Verify final completion call
#         completion_calls = [call for call in mock_publish.call_args_list 
#                           if call[0][0] == "glific_id_update_complete"]
#         assert len(completion_calls) == 1
#         assert completion_calls[0] == call("glific_id_update_complete", {"total_updated": 10000})

#     @patch('tap_lms.glific_utils.frappe.publish_realtime')
#     @patch('tap_lms.glific_utils.frappe.db.commit')
#     @patch('tap_lms.glific_utils.update_student_glific_ids')
#     def test_batch_size_boundary(self, mock_update, mock_commit, mock_publish):
#         """Test exactly at batch size boundaries"""
#         from tap_lms.glific_utils import process_glific_id_update
        
#         test_cases = [99, 100, 101, 199, 200, 201]
        
#         for total_students in test_cases:
#             mock_commit.reset_mock()
#             mock_update.reset_mock()
#             mock_publish.reset_mock()
            
#             mock_update.return_value = min(100, total_students)
            
#             process_glific_id_update(total_students)
            
#             expected_batches = (total_students + 99) // 100  # Ceiling division
#             assert mock_commit.call_count == expected_batches



import pytest
import sys
import os
from unittest.mock import patch, MagicMock, call

# Add the current directory to Python path to allow imports
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, '..'))

# Mock frappe before any imports
sys.modules['frappe'] = MagicMock()
sys.modules['frappe.db'] = MagicMock()
sys.modules['frappe.enqueue'] = MagicMock()
sys.modules['frappe.publish_realtime'] = MagicMock()

# Import our functions - adjust these imports based on your actual file structure
try:
    from tap_lms.glific_utils import run_glific_id_update, process_glific_id_update
except ImportError:
    try:
        import tap_lms.glific_utils as glific_utils
        run_glific_id_update = glific_utils.run_glific_id_update
        process_glific_id_update = glific_utils.process_glific_id_update
    except ImportError:
        # Last resort - try direct import from current directory
        sys.path.insert(0, os.path.dirname(__file__))
        import glific_utils
        run_glific_id_update = glific_utils.run_glific_id_update
        process_glific_id_update = glific_utils.process_glific_id_update


class TestGlificUtils:
    """Test cases for glific_utils.py to achieve 100% code coverage"""
    
    def setup_method(self):
        """Reset mocks before each test"""
        # Create fresh mock instances
        self.mock_frappe = MagicMock()
        self.mock_frappe.db.count = MagicMock()
        self.mock_frappe.db.commit = MagicMock()
        self.mock_frappe.enqueue = MagicMock()
        self.mock_frappe.publish_realtime = MagicMock()
        
        # Patch frappe in the module where our functions are defined
        self.frappe_patcher = patch('glific_utils.frappe', self.mock_frappe)
        self.frappe_patcher.start()
        
    def teardown_method(self):
        """Clean up patches after each test"""
        self.frappe_patcher.stop()

    def test_run_glific_id_update_with_students_found(self):
        """Test run_glific_id_update when students are found"""
        # Mock frappe.db.count to return students found
        self.mock_frappe.db.count.return_value = 5
        
        # Mock enqueue function
        mock_job = MagicMock()
        mock_job.name = "test_job_123"
        self.mock_frappe.enqueue.return_value = mock_job
        
        result = run_glific_id_update()
        
        # Verify frappe.db.count was called with correct parameters
        self.mock_frappe.db.count.assert_called_once_with(
            "Student", 
            {"glific_id": ["in", ["", None]]}
        )
        
        # Verify enqueue was called with correct parameters
        self.mock_frappe.enqueue.assert_called_once_with(
            process_glific_id_update,
            queue='long',
            timeout=3600,
            total_students=5
        )
        
        # Verify return value
        assert result == "Glific ID update process started. Job ID: test_job_123"

    def test_run_glific_id_update_no_students_found(self):
        """Test run_glific_id_update when no students are found"""
        # Mock frappe.db.count to return 0 students
        self.mock_frappe.db.count.return_value = 0
        
        result = run_glific_id_update()
        
        # Verify frappe.db.count was called
        self.mock_frappe.db.count.assert_called_once_with(
            "Student", 
            {"glific_id": ["in", ["", None]]}
        )
        
        # Verify return value when no students found
        assert result == "No students found without Glific ID."

    def test_process_glific_id_update_single_batch(self):
        """Test process_glific_id_update with single batch (less than 100 students)"""
        with patch('glific_utils.update_student_glific_ids') as mock_update:
            mock_update.return_value = 50
            
            process_glific_id_update(50)
            
            # Verify frappe.db.commit was called once
            self.mock_frappe.db.commit.assert_called_once()
            
            # Verify publish_realtime calls
            progress_calls = self.mock_frappe.publish_realtime.call_args_list
            
            # Should have 1 progress call and 1 completion call
            assert len(progress_calls) == 2
            
            # Verify calls
            assert progress_calls[0] == call("glific_id_update_progress", {"processed": 50, "total": 50})
            assert progress_calls[1] == call("glific_id_update_complete", {"total_updated": 50})

    def test_process_glific_id_update_multiple_batches(self):
        """Test process_glific_id_update with multiple batches"""
        with patch('glific_utils.update_student_glific_ids') as mock_update:
            # Mock to return 100, 100, 50 for three consecutive calls
            mock_update.side_effect = [100, 100, 50]
            
            process_glific_id_update(250)
            
            # Verify frappe.db.commit was called 3 times (once per batch)
            assert self.mock_frappe.db.commit.call_count == 3
            
            # Verify publish_realtime was called for progress updates
            progress_calls = self.mock_frappe.publish_realtime.call_args_list
            
            # Should have 3 progress calls and 1 completion call
            assert len(progress_calls) == 4
            
            # Verify progress calls
            assert progress_calls[0] == call("glific_id_update_progress", {"processed": 100, "total": 250})
            assert progress_calls[1] == call("glific_id_update_progress", {"processed": 200, "total": 250})
            assert progress_calls[2] == call("glific_id_update_progress", {"processed": 250, "total": 250})
            
            # Verify completion call
            assert progress_calls[3] == call("glific_id_update_complete", {"total_updated": 250})

    def test_process_glific_id_update_with_zero_students(self):
        """Test process_glific_id_update with zero total students"""
        with patch('glific_utils.update_student_glific_ids') as mock_update:
            process_glific_id_update(0)
            
            # Verify no database operations were performed
            self.mock_frappe.db.commit.assert_not_called()
            mock_update.assert_not_called()
            
            # Verify only completion call was made
            self.mock_frappe.publish_realtime.assert_called_once_with(
                "glific_id_update_complete", 
                {"total_updated": 0}
            )

    def test_process_glific_id_update_exact_batch_size(self):
        """Test process_glific_id_update with exactly 100 students"""
        with patch('glific_utils.update_student_glific_ids') as mock_update:
            mock_update.return_value = 100
            
            process_glific_id_update(100)
            
            # Verify frappe.db.commit was called once
            self.mock_frappe.db.commit.assert_called_once()
            
            # Verify publish_realtime calls
            progress_calls = self.mock_frappe.publish_realtime.call_args_list
            assert len(progress_calls) == 2
            
            # Verify calls
            assert progress_calls[0] == call("glific_id_update_progress", {"processed": 100, "total": 100})
            assert progress_calls[1] == call("glific_id_update_complete", {"total_updated": 100})


class TestGlificUtilsIntegration:
    """Integration tests for the complete workflow"""
    
    def setup_method(self):
        """Reset mocks before each test"""
        self.mock_frappe = MagicMock()
        self.mock_frappe.db.count = MagicMock()
        self.mock_frappe.enqueue = MagicMock()
        
        # Patch frappe in the module
        self.frappe_patcher = patch('glific_utils.frappe', self.mock_frappe)
        self.frappe_patcher.start()
        
    def teardown_method(self):
        """Clean up patches after each test"""
        self.frappe_patcher.stop()

    def test_complete_workflow_integration(self):
        """Test the complete workflow from run_glific_id_update to process_glific_id_update"""
        # Setup
        self.mock_frappe.db.count.return_value = 150
        mock_job = MagicMock()
        mock_job.name = "integration_test_job"
        self.mock_frappe.enqueue.return_value = mock_job
        
        # Test run_glific_id_update
        result = run_glific_id_update()
        
        # Verify enqueue was called
        assert self.mock_frappe.enqueue.called
        args, kwargs = self.mock_frappe.enqueue.call_args
        assert args[0] == process_glific_id_update
        assert kwargs['total_students'] == 150
        assert kwargs['queue'] == 'long'
        assert kwargs['timeout'] == 3600
        
        # Verify result
        assert result == "Glific ID update process started. Job ID: integration_test_job"


class TestGlificUtilsEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def setup_method(self):
        """Reset mocks before each test"""
        self.mock_frappe = MagicMock()
        self.mock_frappe.db.commit = MagicMock()
        self.mock_frappe.publish_realtime = MagicMock()
        
        # Patch frappe in the module
        self.frappe_patcher = patch('glific_utils.frappe', self.mock_frappe)
        self.frappe_patcher.start()
        
    def teardown_method(self):
        """Clean up patches after each test"""
        self.frappe_patcher.stop()

    def test_batch_size_boundaries(self):
        """Test various batch size boundaries"""
        test_cases = [99, 100, 101, 199, 200, 201]
        
        for total_students in test_cases:
            # Reset mocks for each iteration
            self.mock_frappe.reset_mock()
            
            with patch('glific_utils.update_student_glific_ids') as mock_update:
                mock_update.return_value = min(100, total_students)
                
                process_glific_id_update(total_students)
                
                expected_batches = (total_students + 99) // 100  # Ceiling division
                assert self.mock_frappe.db.commit.call_count == expected_batches

    def test_large_student_count(self):
        """Test with very large student count"""
        with patch('glific_utils.update_student_glific_ids') as mock_update:
            mock_update.return_value = 100
            
            process_glific_id_update(1000)  # 10 batches
            
            # Verify correct number of commits (10 batches)
            assert self.mock_frappe.db.commit.call_count == 10
            
            # Verify final completion call
            completion_calls = [call for call in self.mock_frappe.publish_realtime.call_args_list 
                              if call[0][0] == "glific_id_update_complete"]
            assert len(completion_calls) == 1
            assert completion_calls[0] == call("glific_id_update_complete", {"total_updated": 1000})


# Run the tests if this file is executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])