import pytest
from unittest.mock import patch, MagicMock, call
from frappe.utils.background_jobs import enqueue
from tap_lms.glific_utils import run_glific_id_update, process_glific_id_update


class TestGlificUtils:
    """Test cases for glific_utils.py to achieve 100% code coverage"""

    @patch('tap_lms.glific_utils.frappe')
    def test_run_glific_id_update_with_students_found(self, mock_frappe):
        """Test run_glific_id_update when students are found"""
        # Mock frappe.db.count to return students found
        mock_frappe.db.count.return_value = 5
        
        # Mock enqueue function
        mock_job = MagicMock()
        mock_job.id = "test_job_123"
        
        with patch('tap_lms.glific_utils.enqueue', return_value=mock_job) as mock_enqueue:
            result = run_glific_id_update()
            
            # Verify frappe.db.count was called with correct parameters
            mock_frappe.db.count.assert_called_once_with(
                "Student", 
                {"glific_id": ["in", ["", None]]}
            )
            
            # Verify enqueue was called with correct parameters
            mock_enqueue.assert_called_once_with(
                process_glific_id_update,
                queue='long',
                timeout=3600,
                total_students=5
            )
            
            # Verify return value
            assert result == "Glific ID update process started. Job ID: test_job_123"

    @patch('tap_lms.glific_utils.frappe')
    def test_run_glific_id_update_no_students_found(self, mock_frappe):
        """Test run_glific_id_update when no students are found"""
        # Mock frappe.db.count to return 0 students
        mock_frappe.db.count.return_value = 0
        
        result = run_glific_id_update()
        
        # Verify frappe.db.count was called
        mock_frappe.db.count.assert_called_once_with(
            "Student", 
            {"glific_id": ["in", ["", None]]}
        )
        
        # Verify return value when no students found
        assert result == "No students found without Glific ID."

    @patch('tap_lms.glific_utils.frappe')
    def test_process_glific_id_update_complete_batch_processing(self, mock_frappe):
        """Test process_glific_id_update with complete batch processing"""
        total_students = 250  # More than one batch
        
        # Mock update_student_glific_ids to return different values for different calls
        mock_frappe.get_doc().update_student_glific_ids.side_effect = [100, 100, 50]
        
        process_glific_id_update(total_students)
        
        # Verify frappe.db.commit was called 3 times (once per batch)
        assert mock_frappe.db.commit.call_count == 3
        
        # Verify publish_realtime was called for progress updates
        progress_calls = mock_frappe.publish_realtime.call_args_list
        
        # Should have 3 progress calls and 1 completion call
        assert len(progress_calls) == 4
        
        # Verify progress calls
        assert progress_calls[0] == call("glific_id_update_progress", {"processed": 100, "total": 250})
        assert progress_calls[1] == call("glific_id_update_progress", {"processed": 200, "total": 250})
        assert progress_calls[2] == call("glific_id_update_progress", {"processed": 250, "total": 250})
        
        # Verify completion call
        assert progress_calls[3] == call("glific_id_update_complete", {"total_updated": 250})

    @patch('tap_lms.glific_utils.frappe')
    def test_process_glific_id_update_single_batch(self, mock_frappe):
        """Test process_glific_id_update with single batch (less than 100 students)"""
        total_students = 50
        
        # Mock update_student_glific_ids to return updated count
        mock_frappe.get_doc().update_student_glific_ids.return_value = 50
        
        process_glific_id_update(total_students)
        
        # Verify frappe.db.commit was called once
        mock_frappe.db.commit.assert_called_once()
        
        # Verify publish_realtime calls
        progress_calls = mock_frappe.publish_realtime.call_args_list
        
        # Should have 1 progress call and 1 completion call
        assert len(progress_calls) == 2
        
        # Verify calls
        assert progress_calls[0] == call("glific_id_update_progress", {"processed": 50, "total": 50})
        assert progress_calls[1] == call("glific_id_update_complete", {"total_updated": 50})

    @patch('tap_lms.glific_utils.frappe')
    def test_process_glific_id_update_exact_batch_size(self, mock_frappe):
        """Test process_glific_id_update with exactly 100 students (one complete batch)"""
        total_students = 100
        
        # Mock update_student_glific_ids to return updated count
        mock_frappe.get_doc().update_student_glific_ids.return_value = 100
        
        process_glific_id_update(total_students)
        
        # Verify frappe.db.commit was called once
        mock_frappe.db.commit.assert_called_once()
        
        # Verify publish_realtime calls
        progress_calls = mock_frappe.publish_realtime.call_args_list
        assert len(progress_calls) == 2
        
        # Verify calls
        assert progress_calls[0] == call("glific_id_update_progress", {"processed": 100, "total": 100})
        assert progress_calls[1] == call("glific_id_update_complete", {"total_updated": 100})

    @patch('tap_lms.glific_utils.frappe')
    def test_process_glific_id_update_with_zero_students(self, mock_frappe):
        """Test process_glific_id_update with zero total students"""
        total_students = 0
        
        process_glific_id_update(total_students)
        
        # Verify no database operations were performed
        mock_frappe.db.commit.assert_not_called()
        mock_frappe.get_doc.assert_not_called()
        
        # Verify only completion call was made
        mock_frappe.publish_realtime.assert_called_once_with(
            "glific_id_update_complete", 
            {"total_updated": 0}
        )

    @patch('tap_lms.glific_utils.frappe')
    def test_process_glific_id_update_partial_update_in_batch(self, mock_frappe):
        """Test process_glific_id_update when update_student_glific_ids returns less than batch size"""
        total_students = 300
        
        # Mock update_student_glific_ids to return partial updates
        mock_frappe.get_doc().update_student_glific_ids.side_effect = [80, 90, 70]  # Total: 240 < 300
        
        process_glific_id_update(total_students)
        
        # Verify progress tracking with actual processed counts
        progress_calls = mock_frappe.publish_realtime.call_args_list
        
        # Should have 3 progress calls and 1 completion call
        assert len(progress_calls) == 4
        
        # Verify progress calls reflect actual processed amounts
        assert progress_calls[0] == call("glific_id_update_progress", {"processed": 80, "total": 300})
        assert progress_calls[1] == call("glific_id_update_progress", {"processed": 170, "total": 300})
        assert progress_calls[2] == call("glific_id_update_progress", {"processed": 240, "total": 300})
        assert progress_calls[3] == call("glific_id_update_complete", {"total_updated": 240})


# Additional integration test
class TestGlificUtilsIntegration:
    """Integration tests for the complete workflow"""
    
    @patch('tap_lms.glific_utils.frappe')
    @patch('tap_lms.glific_utils.enqueue')
    def test_complete_workflow_integration(self, mock_enqueue, mock_frappe):
        """Test the complete workflow from run_glific_id_update to process_glific_id_update"""
        # Setup
        mock_frappe.db.count.return_value = 150
        mock_job = MagicMock()
        mock_job.id = "integration_test_job"
        mock_enqueue.return_value = mock_job
        
        # Test run_glific_id_update
        result = run_glific_id_update()
        
        # Verify enqueue was called
        assert mock_enqueue.called
        args, kwargs = mock_enqueue.call_args
        assert args[0] == process_glific_id_update
        assert kwargs['total_students'] == 150
        assert kwargs['queue'] == 'long'
        assert kwargs['timeout'] == 3600
        
        # Verify result
        assert result == "Glific ID update process started. Job ID: integration_test_job"


# Test fixtures and helpers
@pytest.fixture
def mock_glific_integration():
    """Fixture to mock Glific Integration document"""
    mock_doc = MagicMock()
    mock_doc.update_student_glific_ids.return_value = 100
    return mock_doc


# Edge case tests
class TestGlificUtilsEdgeCases:
    """Test edge cases and error scenarios"""
    
    @patch('tap_lms.glific_utils.frappe')
    def test_large_student_count(self, mock_frappe):
        """Test with very large student count"""
        total_students = 10000  # 100 batches
        
        # Mock consistent returns
        mock_frappe.get_doc().update_student_glific_ids.return_value = 100
        
        process_glific_id_update(total_students)
        
        # Verify correct number of commits (100 batches)
        assert mock_frappe.db.commit.call_count == 100
        
        # Verify final completion call
        completion_calls = [call for call in mock_frappe.publish_realtime.call_args_list 
                          if call[0][0] == "glific_id_update_complete"]
        assert len(completion_calls) == 1
        assert completion_calls[0] == call("glific_id_update_complete", {"total_updated": 10000})

    @patch('tap_lms.glific_utils.frappe')
    def test_batch_size_boundary(self, mock_frappe):
        """Test exactly at batch size boundaries"""
        test_cases = [99, 100, 101, 199, 200, 201]
        
        for total_students in test_cases:
            mock_frappe.reset_mock()
            mock_frappe.get_doc().update_student_glific_ids.return_value = min(100, total_students)
            
            process_glific_id_update(total_students)
            
            expected_batches = (total_students + 99) // 100  # Ceiling division
            assert mock_frappe.db.commit.call_count == expected_batches