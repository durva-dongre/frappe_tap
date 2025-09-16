"""
Test suite for video_api module with 60%+ coverage target
Run with: pytest test_video_api.py --cov=video_api --cov-report=term-missing
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock frappe at module level before any imports
sys.modules['frappe'] = MagicMock()


# Import the module to test (adjust the import based on your actual module name)
import video_api


class TestVideoAPI:
    """Test cases for Video API functions"""
    
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """Setup test environment before each test"""
        # Create mock frappe module with all required attributes
        self.mock_frappe = MagicMock()
        self.mock_frappe.whitelist = Mock(return_value=lambda f: f)
        self.mock_frappe.db = MagicMock()
        self.mock_frappe.utils = MagicMock()
        self.mock_frappe.log_error = MagicMock()
        
        # Monkeypatch frappe in the video_api module
        monkeypatch.setattr('video_api.frappe', self.mock_frappe)
        
        # Reset mocks before each test
        self.mock_frappe.reset_mock()
        yield
    
    # ==================== get_file_url tests ====================
    
    def test_get_file_url_with_none(self):
        """Test get_file_url with None input"""
        result = video_api.get_file_url(None)
        assert result is None
    
    def test_get_file_url_with_http(self):
        """Test get_file_url with http URL"""
        result = video_api.get_file_url('http://external.com/video.mp4')
        assert result == 'http://external.com/video.mp4'
    
    def test_get_file_url_with_files_path(self):
        """Test get_file_url with /files/ path"""
        self.mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_file_url('/files/video.mp4')
        assert result == 'http://example.com/files/video.mp4'
    
    def test_get_file_url_with_relative_path(self):
        """Test get_file_url with relative path"""
        self.mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_file_url('video.mp4')
        assert result == 'http://example.com/files/video.mp4'
    
    # ==================== get_video_urls tests ====================
    
    def test_get_video_urls_no_results(self):
        """Test get_video_urls with no results"""
        self.mock_frappe.db.sql.return_value = []
        
        result = video_api.get_video_urls()
        
        assert result['status'] == 'success'
        assert result['message'] == 'No videos found'
        assert result['count'] == 0
    
    def test_get_video_urls_single_video(self):
        """Test get_video_urls with single video result"""
        mock_video_data = [{
            'video_id': 'VID001',
            'video_name': 'Test Video',
            'video_youtube_url': 'https://youtube.com/watch?v=test',
            'video_plio_url': None,
            'video_file': None,
            'duration': '10:30',
            'description': 'Test description',
            'difficulty_tier': 'Beginner',
            'estimated_duration': '15 min',
            'unit_name': 'Unit 1',
            'unit_order': 1,
            'course_level_id': 'CL001',
            'course_level_name': 'Basic Course',
            'week_no': 1,
            'vertical_name': 'Math'
        }]
        
        self.mock_frappe.db.sql.return_value = mock_video_data
        self.mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_video_urls(course_level='CL001', week_no=1)
        
        assert result['status'] == 'success'
        assert result['video_id'] == 'VID001'
        assert result['video_name'] == 'Test Video'
        assert result['youtube'] == 'https://youtube.com/watch?v=test'
        assert result['count'] == 1
    
    def test_get_video_urls_with_translations(self):
        """Test get_video_urls with language translations"""
        # First call returns base data
        mock_video_data = [{
            'video_id': 'VID001',
            'video_name': 'Test Video',
            'video_youtube_url': 'https://youtube.com/english',
            'video_plio_url': None,
            'video_file': None,
            'duration': '10:30',
            'description': 'English description',
            'difficulty_tier': 'Beginner',
            'estimated_duration': '15 min',
            'unit_name': 'Unit 1',
            'unit_order': 1,
            'course_level_id': 'CL001',
            'course_level_name': 'Basic Course',
            'week_no': 1,
            'vertical_name': 'Math'
        }]
        
        # Second call returns translation data
        mock_translation_data = [{
            'video_id': 'VID001',
            'language': 'Spanish',
            'translated_name': 'Video de Prueba',
            'translated_description': 'Descripción en español',
            'translated_youtube_url': 'https://youtube.com/spanish',
            'translated_plio_url': None,
            'translated_video_file': None
        }]
        
        self.mock_frappe.db.sql.side_effect = [mock_video_data, mock_translation_data]
        
        result = video_api.get_video_urls(language='Spanish')
        
        assert result['video_name'] == 'Video de Prueba'
        assert result['description'] == 'Descripción en español'
        assert result['youtube'] == 'https://youtube.com/spanish'
        assert result['language'] == 'Spanish'
    
    def test_get_video_urls_exception_handling(self):
        """Test get_video_urls exception handling"""
        self.mock_frappe.db.sql.side_effect = Exception("Database error")
        
        result = video_api.get_video_urls()
        
        assert result['status'] == 'error'
        assert 'Database error' in result['message']
        self.mock_frappe.log_error.assert_called_once()
    
    # ==================== get_available_filters tests ====================
    
    def test_get_available_filters_success(self):
        """Test get_available_filters returns all filter options"""
        self.mock_frappe.db.sql.side_effect = [
            # Course levels
            [{'name': 'CL001', 'display_name': 'Basic'}, {'name': 'CL002', 'display_name': 'Advanced'}],
            # Weeks
            [{'week_no': 1}, {'week_no': 2}, {'week_no': 3}],
            # Languages
            [{'language': 'English'}, {'language': 'Spanish'}],
            # Verticals
            [{'name': 'V001', 'display_name': 'Math'}, {'name': 'V002', 'display_name': 'Science'}]
        ]
        
        result = video_api.get_available_filters()
        
        assert result['status'] == 'success'
        assert len(result['course_levels']) == 2
        assert result['weeks'] == [1, 2, 3]
        assert result['languages'] == ['English', 'Spanish']
        assert result['video_sources'] == ['youtube', 'plio', 'file']
        assert len(result['verticals']) == 2
    
    # ==================== get_video_statistics tests ====================
    
    def test_get_video_statistics_success(self):
        """Test get_video_statistics returns correct statistics"""
        self.mock_frappe.db.sql.side_effect = [
            # Video stats
            [{'total_videos': 100, 'youtube_videos': 80, 'plio_videos': 50, 'file_videos': 30}],
            # Course stats
            [{'total_courses': 5, 'total_weeks': 12, 'total_verticals': 3}],
            # Language stats
            [{'available_languages': 4}]
        ]
        
        result = video_api.get_video_statistics()
        
        assert result['status'] == 'success'
        assert result['statistics']['total_videos'] == 100
        assert result['statistics']['youtube_videos'] == 80
        assert result['statistics']['total_courses'] == 5
        assert result['statistics']['available_languages'] == 4
    
    # ==================== test_connection tests ====================
    
    def test_test_connection_success(self):
        """Test test_connection when API is working"""
        self.mock_frappe.db.sql.return_value = [{'video_count': 50}]
        
        result = video_api.test_connection()
        
        assert result['status'] == 'success'
        assert result['message'] == 'API is working correctly'
        assert result['video_count'] == 50
        assert len(result['endpoints']) == 5


# Standalone test_connection function test (outside class)
def test_connection():
    """Test standalone test_connection function"""
    with patch('video_api.frappe') as mock_frappe:
        mock_frappe.db.sql.return_value = [{'video_count': 25}]
        
        result = video_api.test_connection()
        
        assert result['status'] == 'success'
        assert result['video_count'] == 25


# Additional tests for better coverage
class TestVideoAPIAdditional:
    """Additional tests for increased coverage"""
    
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        """Setup test environment"""
        self.mock_frappe = MagicMock()
        monkeypatch.setattr('video_api.frappe', self.mock_frappe)
        yield
    
    def test_get_video_urls_multiple_videos(self):
        """Test get_video_urls with multiple videos"""
        mock_video_data = [
            {
                'video_id': 'VID001',
                'video_name': 'Video 1',
                'video_youtube_url': 'https://youtube.com/1',
                'video_plio_url': None,
                'video_file': None,
                'duration': '10:30',
                'description': 'Description 1',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '15 min',
                'unit_name': 'Unit 1',
                'unit_order': 1,
                'course_level_id': 'CL001',
                'course_level_name': 'Basic Course',
                'week_no': 1,
                'vertical_name': 'Math'
            },
            {
                'video_id': 'VID002',
                'video_name': 'Video 2',
                'video_youtube_url': None,
                'video_plio_url': 'https://plio.com/2',
                'video_file': None,
                'duration': '20:00',
                'description': 'Description 2',
                'difficulty_tier': 'Intermediate',
                'estimated_duration': '25 min',
                'unit_name': 'Unit 2',
                'unit_order': 2,
                'course_level_id': 'CL001',
                'course_level_name': 'Basic Course',
                'week_no': 1,
                'vertical_name': 'Math'
            }
        ]
        
        self.mock_frappe.db.sql.return_value = mock_video_data
        
        result = video_api.get_video_urls()
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(video['count'] == 2 for video in result)
    
    def test_get_video_urls_with_video_source_filter(self):
        """Test filtering by video source"""
        mock_video_data = [{
            'video_id': 'VID001',
            'video_name': 'Video 1',
            'video_youtube_url': 'https://youtube.com/1',
            'video_plio_url': 'https://plio.com/1',
            'video_file': '/files/video1.mp4',
            'duration': '10:30',
            'description': 'Description 1',
            'difficulty_tier': 'Beginner',
            'estimated_duration': '15 min',
            'unit_name': 'Unit 1',
            'unit_order': 1,
            'course_level_id': 'CL001',
            'course_level_name': 'Basic Course',
            'week_no': 1,
            'vertical_name': 'Math'
        }]
        
        self.mock_frappe.db.sql.return_value = mock_video_data
        self.mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_video_urls(video_source='youtube')
        
        assert 'youtube' in result
        assert 'plio' not in result
        assert 'file' not in result
    
    def test_get_video_urls_aggregated_single_week(self):
        """Test aggregated video URLs for single week"""
        mock_video_data = [
            {
                'video_id': 'VID001',
                'video_name': 'Video 1',
                'video_youtube_url': 'https://youtube.com/1',
                'video_plio_url': None,
                'video_file': None,
                'duration': '10:30',
                'description': 'Description 1',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '15 min',
                'unit_name': 'Unit 1',
                'unit_order': 1,
                'course_level_id': 'CL001',
                'course_level_name': 'Basic Course',
                'week_no': 1,
                'vertical_name': 'Math'
            },
            {
                'video_id': 'VID002',
                'video_name': 'Video 2',
                'video_youtube_url': 'https://youtube.com/2',
                'video_plio_url': None,
                'video_file': None,
                'duration': '20:00',
                'description': 'Description 2',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '25 min',
                'unit_name': 'Unit 1',
                'unit_order': 1,
                'course_level_id': 'CL001',
                'course_level_name': 'Basic Course',
                'week_no': 1,
                'vertical_name': 'Math'
            }
        ]
        
        self.mock_frappe.db.sql.return_value = mock_video_data
        
        result = video_api.get_video_urls_aggregated(week_no=1)
        
        assert result['status'] == 'success'
        assert result['video_id'] == 'week-1-videos'
        assert 'Video 1' in result['video_name']
        assert 'Video 2' in result['video_name']
        assert result['count'] == 2
    
    def test_get_available_filters_exception(self):
        """Test get_available_filters with exception"""
        self.mock_frappe.db.sql.side_effect = Exception("Filter error")
        
        result = video_api.get_available_filters()
        
        assert result['status'] == 'error'
        assert 'Filter error' in result['message']
    
    def test_get_video_statistics_exception(self):
        """Test get_video_statistics with exception"""
        self.mock_frappe.db.sql.side_effect = Exception("Stats error")
        
        result = video_api.get_video_statistics()
        
        assert result['status'] == 'error'
        assert 'Stats error' in result['message']


if __name__ == "__main__":
    # Run with coverage report
    import subprocess
    import sys
    
    try:
        # Try to run with pytest and coverage
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            __file__, 
            '--cov=video_api',
            '--cov-report=term-missing',
            '--cov-report=html',
            '-v'
        ], capture_output=True, text=True)
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
            
    except:
        print("Please install pytest and pytest-cov:")
        print("pip install pytest pytest-cov")
        print("\nThen run:")
        print(f"pytest {__file__} --cov=video_api --cov-report=term-missing")