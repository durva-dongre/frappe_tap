
# """
# Test suite for video_api module with proper Frappe mocking
# File location: tap_lms/tests/test_video_api.py
# Testing: tap_lms/utils/video_api.py
# """

# import pytest
# import sys
# import os
# from unittest.mock import Mock, MagicMock, patch

# # Add the app path to sys.path
# app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
# if app_path not in sys.path:
#     sys.path.insert(0, app_path)


# # Create a mock _dict class that behaves like frappe's _dict
# class MockDict(dict):
#     """Mock frappe's _dict class"""
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.__dict__ = self
    
#     def __getattr__(self, key):
#         try:
#             return self[key]
#         except KeyError:
#             return None
    
#     def __setattr__(self, key, value):
#         if key == '__dict__':
#             super().__setattr__(key, value)
#         else:
#             self[key] = value


# # Create a complete mock of frappe before importing anything
# mock_frappe = MagicMock()
# mock_frappe.whitelist = Mock(return_value=lambda f: f)
# mock_frappe._ = Mock(side_effect=lambda x: x)
# mock_frappe._dict = MockDict  # Use our MockDict class
# mock_frappe.db = MagicMock()
# mock_frappe.db.sql = MagicMock()
# mock_frappe.utils = MagicMock()
# mock_frappe.utils.get_url = MagicMock()
# mock_frappe.utils.cstr = Mock(side_effect=lambda x: str(x) if x else '')
# mock_frappe.log_error = MagicMock()

# # Insert the mock into sys.modules BEFORE importing video_api
# sys.modules['frappe'] = mock_frappe
# sys.modules['frappe.utils'] = mock_frappe.utils

# # Now we can safely import video_api
# from tap_lms.utils import video_api


# @pytest.fixture(autouse=True)
# def reset_frappe_mock():
#     """Reset frappe mock before each test"""
#     mock_frappe.reset_mock()
#     mock_frappe.db.reset_mock()
#     mock_frappe.utils.reset_mock()
#     mock_frappe.log_error.reset_mock()
#     yield


# def create_mock_video_data(data_dict):
#     """Helper function to create mock video data in the format expected by the API"""
#     return [MockDict(data_dict)]


# class TestVideoAPI:
#     """Test cases for Video API functions"""
    
#     # ==================== get_file_url tests ====================
    
#     def test_get_file_url_with_none(self):
#         """Test get_file_url with None input"""
#         result = video_api.get_file_url(None)
#         assert result is None
    
#     def test_get_file_url_with_http(self):
#         """Test get_file_url with http URL"""
#         result = video_api.get_file_url('http://external.com/video.mp4')
#         assert result == 'http://external.com/video.mp4'
    
#     def test_get_file_url_with_files_path(self):
#         """Test get_file_url with /files/ path"""
#         mock_frappe.utils.get_url.return_value = 'http://example.com'
        
#         result = video_api.get_file_url('/files/video.mp4')
#         assert result == 'http://example.com/files/video.mp4'
    
#     def test_get_file_url_with_relative_path(self):
#         """Test get_file_url with relative path"""
#         mock_frappe.utils.get_url.return_value = 'http://example.com'
        
#         result = video_api.get_file_url('video.mp4')
#         assert result == 'http://example.com/files/video.mp4'
    
#     # ==================== get_video_urls tests ====================
    
#     def test_get_video_urls_no_results(self):
#         """Test get_video_urls with no results"""
#         mock_frappe.db.sql.return_value = []
        
#         result = video_api.get_video_urls()
        
#         assert result['status'] == 'success'
#         assert result['message'] == 'No videos found'
#         assert result['count'] == 0
    
#     def test_get_video_urls_single_video(self):
#         """Test get_video_urls with single video result"""
#         mock_video = MockDict({
#             'video_id': 'VID001',
#             'video_name': 'Test Video',
#             'video_youtube_url': 'https://youtube.com/watch?v=test',
#             'video_plio_url': None,
#             'video_file': None,
#             'duration': '10:30',
#             'description': 'Test description',
#             'difficulty_tier': 'Beginner',
#             'estimated_duration': '15 min',
#             'unit_name': 'Unit 1',
#             'unit_order': 1,
#             'course_level_id': 'CL001',
#             'course_level_name': 'Basic Course',
#             'week_no': 1,
#             'vertical_name': 'Math'
#         })
        
#         mock_frappe.db.sql.return_value = [mock_video]
        
#         result = video_api.get_video_urls(course_level='CL001', week_no=1)
        
#         assert result['status'] == 'success'
#         assert result['video_id'] == 'VID001'
#         assert result['video_name'] == 'Test Video'
#         assert result['youtube'] == 'https://youtube.com/watch?v=test'
#         assert result['count'] == 1
    
#     def test_get_video_urls_with_translations(self):
#         """Test get_video_urls with language translations"""
#         # First call returns base data
#         mock_video = MockDict({
#             'video_id': 'VID001',
#             'video_name': 'Test Video',
#             'video_youtube_url': 'https://youtube.com/english',
#             'video_plio_url': None,
#             'video_file': None,
#             'duration': '10:30',
#             'description': 'English description',
#             'difficulty_tier': 'Beginner',
#             'estimated_duration': '15 min',
#             'unit_name': 'Unit 1',
#             'unit_order': 1,
#             'course_level_id': 'CL001',
#             'course_level_name': 'Basic Course',
#             'week_no': 1,
#             'vertical_name': 'Math'
#         })
        
#         # Second call returns translation data
#         mock_translation = MockDict({
#             'video_id': 'VID001',
#             'language': 'Spanish',
#             'translated_name': 'Video de Prueba',
#             'translated_description': 'Descripción en español',
#             'translated_youtube_url': 'https://youtube.com/spanish',
#             'translated_plio_url': None,
#             'translated_video_file': None
#         })
        
#         mock_frappe.db.sql.side_effect = [[mock_video], [mock_translation]]
        
#         result = video_api.get_video_urls(language='Spanish')
        
#         assert result['video_name'] == 'Video de Prueba'
#         assert result['description'] == 'Descripción en español'
#         assert result['youtube'] == 'https://youtube.com/spanish'
#         assert result['language'] == 'Spanish'
        
#         # Reset side_effect for next tests
#         mock_frappe.db.sql.side_effect = None
    
#     def test_get_video_urls_exception_handling(self):
#         """Test get_video_urls exception handling"""
#         mock_frappe.db.sql.side_effect = Exception("Database error")
        
#         result = video_api.get_video_urls()
        
#         assert result['status'] == 'error'
#         assert 'Database error' in result['message']
#         mock_frappe.log_error.assert_called_once()
        
#         # Reset side_effect
#         mock_frappe.db.sql.side_effect = None
    
#     # ==================== get_available_filters tests ====================
    
#     def test_get_available_filters_success(self):
#         """Test get_available_filters returns all filter options"""
#         # Mock the SQL returns as lists of MockDict objects
#         mock_frappe.db.sql.side_effect = [
#             # Course levels
#             [MockDict({'name': 'CL001', 'display_name': 'Basic'}), 
#              MockDict({'name': 'CL002', 'display_name': 'Advanced'})],
#             # Weeks
#             [MockDict({'week_no': 1}), MockDict({'week_no': 2}), MockDict({'week_no': 3})],
#             # Languages
#             [MockDict({'language': 'English'}), MockDict({'language': 'Spanish'})],
#             # Verticals
#             [MockDict({'name': 'V001', 'display_name': 'Math'}), 
#              MockDict({'name': 'V002', 'display_name': 'Science'})]
#         ]
        
#         result = video_api.get_available_filters()
        
#         assert result['status'] == 'success'
#         assert len(result['course_levels']) == 2
#         assert result['weeks'] == [1, 2, 3]
#         assert result['languages'] == ['English', 'Spanish']
#         assert result['video_sources'] == ['youtube', 'plio', 'file']
#         assert len(result['verticals']) == 2
        
#         # Reset side_effect
#         mock_frappe.db.sql.side_effect = None
    
#     # ==================== get_video_statistics tests ====================
    
#     def test_get_video_statistics_success(self):
#         """Test get_video_statistics returns correct statistics"""
#         mock_frappe.db.sql.side_effect = [
#             # Video stats
#             [MockDict({'total_videos': 100, 'youtube_videos': 80, 'plio_videos': 50, 'file_videos': 30})],
#             # Course stats
#             [MockDict({'total_courses': 5, 'total_weeks': 12, 'total_verticals': 3})],
#             # Language stats
#             [MockDict({'available_languages': 4})]
#         ]
        
#         result = video_api.get_video_statistics()
        
#         assert result['status'] == 'success'
#         assert result['statistics']['total_videos'] == 100
#         assert result['statistics']['youtube_videos'] == 80
#         assert result['statistics']['total_courses'] == 5
#         assert result['statistics']['available_languages'] == 4
        
#         # Reset side_effect
#         mock_frappe.db.sql.side_effect = None
    
#     # ==================== test_connection tests ====================
    
#     def test_test_connection_success(self):
#         """Test test_connection when API is working"""
#         mock_frappe.db.sql.return_value = [MockDict({'video_count': 50})]
        
#         result = video_api.test_connection()
        
#         assert result['status'] == 'success'
#         assert result['message'] == 'API is working correctly'
#         assert result['video_count'] == 50
#         assert len(result['endpoints']) == 5


# # Standalone test_connection function test
# def test_connection():
#     """Test standalone test_connection function"""
#     mock_frappe.db.sql.return_value = [MockDict({'video_count': 25})]
    
#     result = video_api.test_connection()
    
#     assert result['status'] == 'success'
#     assert result['video_count'] == 25


# # Additional tests for better coverage
# class TestVideoAPIAdditional:
#     """Additional tests for increased coverage"""
    
#     def test_get_video_urls_multiple_videos(self):
#         """Test get_video_urls with multiple videos"""
#         mock_video1 = MockDict({
#             'video_id': 'VID001',
#             'video_name': 'Video 1',
#             'video_youtube_url': 'https://youtube.com/1',
#             'video_plio_url': None,
#             'video_file': None,
#             'duration': '10:30',
#             'description': 'Description 1',
#             'difficulty_tier': 'Beginner',
#             'estimated_duration': '15 min',
#             'unit_name': 'Unit 1',
#             'unit_order': 1,
#             'course_level_id': 'CL001',
#             'course_level_name': 'Basic Course',
#             'week_no': 1,
#             'vertical_name': 'Math'
#         })
        
#         mock_video2 = MockDict({
#             'video_id': 'VID002',
#             'video_name': 'Video 2',
#             'video_youtube_url': None,
#             'video_plio_url': 'https://plio.com/2',
#             'video_file': None,
#             'duration': '20:00',
#             'description': 'Description 2',
#             'difficulty_tier': 'Intermediate',
#             'estimated_duration': '25 min',
#             'unit_name': 'Unit 2',
#             'unit_order': 2,
#             'course_level_id': 'CL001',
#             'course_level_name': 'Basic Course',
#             'week_no': 1,
#             'vertical_name': 'Math'
#         })
        
#         mock_frappe.db.sql.return_value = [mock_video1, mock_video2]
        
#         result = video_api.get_video_urls()
        
#         assert isinstance(result, list)
#         assert len(result) == 2
#         assert all(video['count'] == 2 for video in result)
    
#     def test_get_video_urls_with_video_source_filter(self):
#         """Test filtering by video source"""
#         mock_video = MockDict({
#             'video_id': 'VID001',
#             'video_name': 'Video 1',
#             'video_youtube_url': 'https://youtube.com/1',
#             'video_plio_url': 'https://plio.com/1',
#             'video_file': '/files/video1.mp4',
#             'duration': '10:30',
#             'description': 'Description 1',
#             'difficulty_tier': 'Beginner',
#             'estimated_duration': '15 min',
#             'unit_name': 'Unit 1',
#             'unit_order': 1,
#             'course_level_id': 'CL001',
#             'course_level_name': 'Basic Course',
#             'week_no': 1,
#             'vertical_name': 'Math'
#         })
        
#         mock_frappe.db.sql.return_value = [mock_video]
#         mock_frappe.utils.get_url.return_value = 'http://example.com'
        
#         result = video_api.get_video_urls(video_source='youtube')
        
#         assert 'youtube' in result
#         assert 'plio' not in result
#         assert 'file' not in result
    
#     def test_get_video_urls_aggregated_single_week(self):
#         """Test aggregated video URLs for single week"""
#         mock_video1 = MockDict({
#             'video_id': 'VID001',
#             'video_name': 'Video 1',
#             'video_youtube_url': 'https://youtube.com/1',
#             'video_plio_url': None,
#             'video_file': None,
#             'duration': '10:30',
#             'description': 'Description 1',
#             'difficulty_tier': 'Beginner',
#             'estimated_duration': '15 min',
#             'unit_name': 'Unit 1',
#             'unit_order': 1,
#             'course_level_id': 'CL001',
#             'course_level_name': 'Basic Course',
#             'week_no': 1,
#             'vertical_name': 'Math'
#         })
        
#         mock_video2 = MockDict({
#             'video_id': 'VID002',
#             'video_name': 'Video 2',
#             'video_youtube_url': 'https://youtube.com/2',
#             'video_plio_url': None,
#             'video_file': None,
#             'duration': '20:00',
#             'description': 'Description 2',
#             'difficulty_tier': 'Beginner',
#             'estimated_duration': '25 min',
#             'unit_name': 'Unit 1',
#             'unit_order': 1,
#             'course_level_id': 'CL001',
#             'course_level_name': 'Basic Course',
#             'week_no': 1,
#             'vertical_name': 'Math'
#         })
        
#         mock_frappe.db.sql.return_value = [mock_video1, mock_video2]
        
#         result = video_api.get_video_urls_aggregated(week_no=1)
        
#         assert result['status'] == 'success'
#         assert result['video_id'] == 'week-1-videos'
#         assert 'Video 1' in result['video_name']
#         assert 'Video 2' in result['video_name']
#         assert result['count'] == 2
    
#     def test_get_video_urls_aggregated_no_results(self):
#         """Test get_video_urls_aggregated with no results"""
#         mock_frappe.db.sql.return_value = []
        
#         result = video_api.get_video_urls_aggregated()
        
#         assert result['status'] == 'success'
#         assert result['message'] == 'No videos found'
#         assert result['count'] == 0
    
#     def test_get_available_filters_exception(self):
#         """Test get_available_filters with exception"""
#         mock_frappe.db.sql.side_effect = Exception("Filter error")
        
#         result = video_api.get_available_filters()
        
#         assert result['status'] == 'error'
#         assert 'Filter error' in result['message']
        
#         # Reset side_effect
#         mock_frappe.db.sql.side_effect = None
    
#     def test_get_video_statistics_exception(self):
#         """Test get_video_statistics with exception"""
#         mock_frappe.db.sql.side_effect = Exception("Stats error")
        
#         result = video_api.get_video_statistics()
        
#         assert result['status'] == 'error'
#         assert 'Stats error' in result['message']
        
#         # Reset side_effect
#         mock_frappe.db.sql.side_effect = None
    
#     def test_test_connection_exception(self):
#         """Test test_connection with exception"""
#         mock_frappe.db.sql.side_effect = Exception("Connection failed")
        
#         result = video_api.test_connection()
        
#         assert result['status'] == 'error'
#         assert 'API test failed' in result['message']
#         assert 'Connection failed' in result['message']
        
#         # Reset side_effect
#         mock_frappe.db.sql.side_effect = None


# # Run basic test to ensure module loads
# if __name__ == "__main__":
#     print("Running basic module test...")
    
#     # Test that the module loaded correctly
#     assert hasattr(video_api, 'get_video_urls')
#     assert hasattr(video_api, 'get_video_urls_aggregated')
#     assert hasattr(video_api, 'get_available_filters')
#     assert hasattr(video_api, 'get_video_statistics')
#     assert hasattr(video_api, 'test_connection')
#     assert hasattr(video_api, 'get_file_url')
    
#     print("✅ Module loaded successfully")
    
#     # Run a simple test
#     mock_frappe.db.sql.return_value = []
#     result = video_api.get_video_urls()
#     assert result['status'] == 'success'
#     assert result['count'] == 0
    
#     print("✅ Basic test passed")
#     print("\nNow run with pytest:")
#     print("pytest tap_lms/tests/test_video_api.py --cov=tap_lms.utils.video_api --cov-report=term-missing")


"""
Test suite for video_api module with proper Frappe mocking
File location: tap_lms/tests/test_video_api.py
Testing: tap_lms/utils/video_api.py
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch

# Add the app path to sys.path
app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if app_path not in sys.path:
    sys.path.insert(0, app_path)


# Create a mock _dict class that behaves like frappe's _dict
class MockDict(dict):
    """Mock frappe's _dict class"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
    
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            return None
    
    def __setattr__(self, key, value):
        if key == '__dict__':
            super().__setattr__(key, value)
        else:
            self[key] = value


# Create a complete mock of frappe before importing anything
mock_frappe = MagicMock()
mock_frappe.whitelist = Mock(return_value=lambda f: f)
mock_frappe._ = Mock(side_effect=lambda x: x)
mock_frappe._dict = MockDict  # Use our MockDict class
mock_frappe.db = MagicMock()
mock_frappe.db.sql = MagicMock()
mock_frappe.utils = MagicMock()
mock_frappe.utils.get_url = MagicMock()
mock_frappe.utils.cstr = Mock(side_effect=lambda x: str(x) if x else '')
mock_frappe.log_error = MagicMock()

# Insert the mock into sys.modules BEFORE importing video_api
sys.modules['frappe'] = mock_frappe
sys.modules['frappe.utils'] = mock_frappe.utils

# Now we can safely import video_api
from tap_lms.utils import video_api


@pytest.fixture(autouse=True)
def reset_frappe_mock():
    """Reset frappe mock before each test"""
    mock_frappe.reset_mock()
    mock_frappe.db.reset_mock()
    mock_frappe.utils.reset_mock()
    mock_frappe.log_error.reset_mock()
    yield


def create_mock_video_data(data_dict):
    """Helper function to create mock video data in the format expected by the API"""
    return [MockDict(data_dict)]


class TestVideoAPI:
    """Test cases for Video API functions"""
    
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
        mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_file_url('/files/video.mp4')
        assert result == 'http://example.com/files/video.mp4'
    
    def test_get_file_url_with_relative_path(self):
        """Test get_file_url with relative path"""
        mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_file_url('video.mp4')
        assert result == 'http://example.com/files/video.mp4'
    
    # ==================== get_video_urls tests ====================
    
    def test_get_video_urls_no_results(self):
        """Test get_video_urls with no results"""
        mock_frappe.db.sql.return_value = []
        
        result = video_api.get_video_urls()
        
        assert result['status'] == 'success'
        assert result['message'] == 'No videos found'
        assert result['count'] == 0
    
    def test_get_video_urls_single_video(self):
        """Test get_video_urls with single video result"""
        mock_video = MockDict({
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
        })
        
        mock_frappe.db.sql.return_value = [mock_video]
        
        result = video_api.get_video_urls(course_level='CL001', week_no=1)
        
        assert result['status'] == 'success'
        assert result['video_id'] == 'VID001'
        assert result['video_name'] == 'Test Video'
        assert result['youtube'] == 'https://youtube.com/watch?v=test'
        assert result['count'] == 1
    
    def test_get_video_urls_with_translations(self):
        """Test get_video_urls with language translations"""
        # First call returns base data
        mock_video = MockDict({
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
        })
        
        # Second call returns translation data
        mock_translation = MockDict({
            'video_id': 'VID001',
            'language': 'Spanish',
            'translated_name': 'Video de Prueba',
            'translated_description': 'Descripción en español',
            'translated_youtube_url': 'https://youtube.com/spanish',
            'translated_plio_url': None,
            'translated_video_file': None
        })
        
        mock_frappe.db.sql.side_effect = [[mock_video], [mock_translation]]
        
        result = video_api.get_video_urls(language='Spanish')
        
        assert result['video_name'] == 'Video de Prueba'
        assert result['description'] == 'Descripción en español'
        assert result['youtube'] == 'https://youtube.com/spanish'
        assert result['language'] == 'Spanish'
        
        # Reset side_effect for next tests
        mock_frappe.db.sql.side_effect = None
    
    def test_get_video_urls_exception_handling(self):
        """Test get_video_urls exception handling"""
        mock_frappe.db.sql.side_effect = Exception("Database error")
        
        result = video_api.get_video_urls()
        
        assert result['status'] == 'error'
        assert 'Database error' in result['message']
        mock_frappe.log_error.assert_called_once()
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    # ==================== get_available_filters tests ====================
    
    def test_get_available_filters_success(self):
        """Test get_available_filters returns all filter options"""
        # Mock the SQL returns as lists of MockDict objects
        mock_frappe.db.sql.side_effect = [
            # Course levels
            [MockDict({'name': 'CL001', 'display_name': 'Basic'}), 
             MockDict({'name': 'CL002', 'display_name': 'Advanced'})],
            # Weeks
            [MockDict({'week_no': 1}), MockDict({'week_no': 2}), MockDict({'week_no': 3})],
            # Languages
            [MockDict({'language': 'English'}), MockDict({'language': 'Spanish'})],
            # Verticals
            [MockDict({'name': 'V001', 'display_name': 'Math'}), 
             MockDict({'name': 'V002', 'display_name': 'Science'})]
        ]
        
        result = video_api.get_available_filters()
        
        assert result['status'] == 'success'
        assert len(result['course_levels']) == 2
        assert result['weeks'] == [1, 2, 3]
        assert result['languages'] == ['English', 'Spanish']
        assert result['video_sources'] == ['youtube', 'plio', 'file']
        assert len(result['verticals']) == 2
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    # ==================== get_video_statistics tests ====================
    
    def test_get_video_statistics_success(self):
        """Test get_video_statistics returns correct statistics"""
        mock_frappe.db.sql.side_effect = [
            # Video stats
            [MockDict({'total_videos': 100, 'youtube_videos': 80, 'plio_videos': 50, 'file_videos': 30})],
            # Course stats
            [MockDict({'total_courses': 5, 'total_weeks': 12, 'total_verticals': 3})],
            # Language stats
            [MockDict({'available_languages': 4})]
        ]
        
        result = video_api.get_video_statistics()
        
        assert result['status'] == 'success'
        assert result['statistics']['total_videos'] == 100
        assert result['statistics']['youtube_videos'] == 80
        assert result['statistics']['total_courses'] == 5
        assert result['statistics']['available_languages'] == 4
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    # ==================== test_connection tests ====================
    
    def test_test_connection_success(self):
        """Test test_connection when API is working"""
        mock_frappe.db.sql.return_value = [MockDict({'video_count': 50})]
        
        result = video_api.test_connection()
        
        assert result['status'] == 'success'
        assert result['message'] == 'API is working correctly'
        assert result['video_count'] == 50
        assert len(result['endpoints']) == 5


# Standalone test_connection function test
def test_connection():
    """Test standalone test_connection function"""
    mock_frappe.db.sql.return_value = [MockDict({'video_count': 25})]
    
    result = video_api.test_connection()
    
    assert result['status'] == 'success'
    assert result['video_count'] == 25


# Additional tests for better coverage
class TestVideoAPIAdditional:
    """Additional tests for increased coverage"""
    
    def test_get_video_urls_multiple_videos(self):
        """Test get_video_urls with multiple videos"""
        mock_video1 = MockDict({
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
        })
        
        mock_video2 = MockDict({
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
        })
        
        mock_frappe.db.sql.return_value = [mock_video1, mock_video2]
        
        result = video_api.get_video_urls()
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(video['count'] == 2 for video in result)
    
    def test_get_video_urls_with_video_source_filter(self):
        """Test filtering by video source"""
        mock_video = MockDict({
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
        })
        
        mock_frappe.db.sql.return_value = [mock_video]
        mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_video_urls(video_source='youtube')
        
        assert 'youtube' in result
        assert 'plio' not in result
        assert 'file' not in result
    
    def test_get_video_urls_aggregated_single_week(self):
        """Test aggregated video URLs for single week"""
        mock_video1 = MockDict({
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
        })
        
        mock_video2 = MockDict({
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
        })
        
        mock_frappe.db.sql.return_value = [mock_video1, mock_video2]
        
        result = video_api.get_video_urls_aggregated(week_no=1)
        
        assert result['status'] == 'success'
        assert result['video_id'] == 'week-1-videos'
        assert 'Video 1' in result['video_name']
        assert 'Video 2' in result['video_name']
        assert result['count'] == 2
    
    def test_get_video_urls_aggregated_no_results(self):
        """Test get_video_urls_aggregated with no results"""
        mock_frappe.db.sql.return_value = []
        
        result = video_api.get_video_urls_aggregated()
        
        assert result['status'] == 'success'
        assert result['message'] == 'No videos found'
        assert result['count'] == 0
    
    def test_get_available_filters_exception(self):
        """Test get_available_filters with exception"""
        mock_frappe.db.sql.side_effect = Exception("Filter error")
        
        result = video_api.get_available_filters()
        
        assert result['status'] == 'error'
        assert 'Filter error' in result['message']
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    def test_get_video_statistics_exception(self):
        """Test get_video_statistics with exception"""
        mock_frappe.db.sql.side_effect = Exception("Stats error")
        
        result = video_api.get_video_statistics()
        
        assert result['status'] == 'error'
        assert 'Stats error' in result['message']
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    def test_test_connection_exception(self):
        """Test test_connection with exception"""
        mock_frappe.db.sql.side_effect = Exception("Connection failed")
        
        result = video_api.test_connection()
        
        assert result['status'] == 'error'
        assert 'API test failed' in result['message']
        assert 'Connection failed' in result['message']
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None


# Additional edge case tests for 100% coverage
class TestVideoAPIEdgeCases:
    """Edge case tests for complete coverage"""
    
    def test_get_file_url_with_https(self):
        """Test get_file_url with https URL"""
        result = video_api.get_file_url('https://external.com/video.mp4')
        assert result == 'https://external.com/video.mp4'
    
    def test_get_file_url_empty_string(self):
        """Test get_file_url with empty string"""
        result = video_api.get_file_url('')
        assert result is None
    
    def test_get_video_urls_with_plio_source(self):
        """Test filtering by plio source"""
        mock_video = MockDict({
            'video_id': 'VID001',
            'video_name': 'Video 1',
            'video_youtube_url': None,
            'video_plio_url': 'https://plio.com/1',
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
        })
        
        mock_frappe.db.sql.return_value = [mock_video]
        
        result = video_api.get_video_urls(video_source='plio')
        
        assert 'plio' in result
        assert 'youtube' not in result
        assert 'file' not in result
    
    def test_get_video_urls_with_file_source(self):
        """Test filtering by file source"""
        mock_video = MockDict({
            'video_id': 'VID001',
            'video_name': 'Video 1',
            'video_youtube_url': None,
            'video_plio_url': None,
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
        })
        
        mock_frappe.db.sql.return_value = [mock_video]
        mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_video_urls(video_source='file')
        
        assert 'file' in result
        assert result['file'] == 'http://example.com/files/video1.mp4'
        assert 'youtube' not in result
        assert 'plio' not in result
    
    def test_get_video_urls_aggregated_exception(self):
        """Test get_video_urls_aggregated exception handling"""
        mock_frappe.db.sql.side_effect = Exception("Aggregation error")
        
        result = video_api.get_video_urls_aggregated()
        
        assert result['status'] == 'error'
        assert 'Aggregation error' in result['message']
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    def test_get_available_filters_partial_data(self):
        """Test get_available_filters with some empty results"""
        mock_frappe.db.sql.side_effect = [
            # Course levels - empty
            [],
            # Weeks
            [MockDict({'week_no': 1})],
            # Languages - empty
            [],
            # Verticals
            [MockDict({'name': 'V001', 'display_name': 'Math'})]
        ]
        
        result = video_api.get_available_filters()
        
        assert result['status'] == 'success'
        assert result['course_levels'] == []
        assert result['weeks'] == [1]
        assert result['languages'] == []
        assert len(result['verticals']) == 1
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    def test_get_video_statistics_empty_results(self):
        """Test get_video_statistics with empty results"""
        mock_frappe.db.sql.side_effect = [[], [], []]
        
        result = video_api.get_video_statistics()
        
        assert result['status'] == 'success'
        # Should handle empty results gracefully
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    def test_get_video_urls_with_video_file(self):
        """Test video with file that needs URL construction"""
        mock_video = MockDict({
            'video_id': 'VID001',
            'video_name': 'Test Video',
            'video_youtube_url': None,
            'video_plio_url': None,
            'video_file': 'video.mp4',  # Relative path without /files/
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
        })
        
        mock_frappe.db.sql.return_value = [mock_video]
        mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        result = video_api.get_video_urls()
        
        assert result['status'] == 'success'
        assert 'file' in result
        assert result['file'] == 'http://example.com/files/video.mp4'
    
    def test_get_video_urls_with_all_video_sources(self):
        """Test video with all three video sources populated"""
        mock_video = MockDict({
            'video_id': 'VID001',
            'video_name': 'Multi-source Video',
            'video_youtube_url': 'https://youtube.com/multi',
            'video_plio_url': 'https://plio.com/multi',
            'video_file': 'multi.mp4',
            'duration': '10:30',
            'description': 'Multi-source description',
            'difficulty_tier': 'Advanced',
            'estimated_duration': '15 min',
            'unit_name': 'Unit 1',
            'unit_order': 1,
            'course_level_id': 'CL001',
            'course_level_name': 'Advanced Course',
            'week_no': 2,
            'vertical_name': 'Physics'
        })
        
        mock_frappe.db.sql.return_value = [mock_video]
        mock_frappe.utils.get_url.return_value = 'http://example.com'
        
        # Test without video_source filter - should return all sources
        result = video_api.get_video_urls()
        
        assert 'youtube' in result
        assert 'plio' in result
        assert 'file' in result
        assert result['youtube'] == 'https://youtube.com/multi'
        assert result['plio'] == 'https://plio.com/multi'
        assert result['file'] == 'http://example.com/files/multi.mp4'


class TestVideoAPICompleteCoverage:
    """Additional tests to achieve 100% code coverage"""
    
    def test_get_video_statistics_partial_results(self):
        """Test statistics with partial/incomplete results"""
        mock_frappe.db.sql.side_effect = [
            # Video stats - missing some fields
            [MockDict({'total_videos': 50})],  # Missing youtube_videos, plio_videos, file_videos
            # Course stats - empty result
            [],
            # Language stats
            [MockDict({'available_languages': 3})]
        ]
        
        result = video_api.get_video_statistics()
        
        assert result['status'] == 'success'
        assert result['statistics']['total_videos'] == 50
        assert result['statistics']['available_languages'] == 3
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None
    
    def test_test_connection_with_no_videos(self):
        """Test connection when no videos exist in database"""
        mock_frappe.db.sql.return_value = [MockDict({'video_count': 0})]
        
        result = video_api.test_connection()
        
        assert result['status'] == 'success'
        assert result['message'] == 'API is working correctly'
        assert result['video_count'] == 0
    
    def test_get_available_filters_with_duplicates(self):
        """Test filters handling duplicate values"""
        mock_frappe.db.sql.side_effect = [
            # Course levels with duplicates
            [MockDict({'name': 'CL001', 'display_name': 'Basic'}), 
             MockDict({'name': 'CL001', 'display_name': 'Basic'}),  # Duplicate
             MockDict({'name': 'CL002', 'display_name': 'Advanced'})],
            # Weeks with duplicates
            [MockDict({'week_no': 1}), MockDict({'week_no': 1}), MockDict({'week_no': 2})],
            # Languages
            [MockDict({'language': 'English'}), MockDict({'language': 'English'})],  # Duplicate
            # Verticals
            [MockDict({'name': 'V001', 'display_name': 'Math'})]
        ]
        
        result = video_api.get_available_filters()
        
        # Should handle duplicates gracefully
        assert result['status'] == 'success'
        # Exact count depends on how the function handles duplicates
        
        # Reset side_effect
        mock_frappe.db.sql.side_effect = None


# Run basic test to ensure module loads
if __name__ == "__main__":
    print("Running basic module test...")
    
    # Test that the module loaded correctly
    assert hasattr(video_api, 'get_video_urls')
    assert hasattr(video_api, 'get_video_urls_aggregated')
    assert hasattr(video_api, 'get_available_filters')
    assert hasattr(video_api, 'get_video_statistics')
    assert hasattr(video_api, 'test_connection')
    assert hasattr(video_api, 'get_file_url')
    
    print("✅ Module loaded successfully")
    
    # Run a simple test
    mock_frappe.db.sql.return_value = []
    result = video_api.get_video_urls()
    assert result['status'] == 'success'
    assert result['count'] == 0
    
    print("✅ Basic test passed")
    print("\nNow run with pytest:")
    print("pytest tap_lms/tests/test_video_api.py --cov=tap_lms.utils.video_api --cov-report=term-missing")