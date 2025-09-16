import unittest
from unittest.mock import patch, MagicMock, call
import frappe
from frappe.utils import get_url


class TestVideoAPIs(unittest.TestCase):
    """Test cases for Video API functions"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Mock frappe.whitelist decorator
        self.whitelist_patcher = patch('frappe.whitelist', lambda **kwargs: lambda func: func)
        self.whitelist_patcher.start()
        
    def tearDown(self):
        """Clean up after each test"""
        self.whitelist_patcher.stop()

    # ============= Test get_video_urls =============
    
    @patch('tap_lms.utils.video_api.frappe.log_error')
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_no_filters(self, mock_sql, mock_log_error):
        """Test get_video_urls without any filters"""
        from tap_lms.utils.video_api import get_video_urls
        
        # Mock empty result
        mock_sql.return_value = []
        
        result = get_video_urls()
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'No videos found')
        self.assertEqual(result['count'], 0)
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_with_course_filter(self, mock_sql):
        """Test get_video_urls with course_level filter"""
        from tap_lms.utils.video_api import get_video_urls
        
        # Mock video data
        mock_base_data = [{
            'video_id': 'VID001',
            'video_name': 'Introduction to Python',
            'video_youtube_url': 'https://youtube.com/watch?v=123',
            'video_plio_url': None,
            'video_file': None,
            'duration': '10:30',
            'description': 'Learn Python basics',
            'difficulty_tier': 'Beginner',
            'estimated_duration': '10 minutes',
            'unit_name': 'Unit 1',
            'unit_order': 1,
            'course_level_id': 'CL001',
            'course_level_name': 'Python Fundamentals',
            'week_no': 1,
            'vertical_name': 'Programming'
        }]
        
        mock_sql.return_value = mock_base_data
        
        result = get_video_urls(course_level='CL001')
        
        # Should call SQL with course filter
        call_args = mock_sql.call_args[0]
        self.assertIn('AND cl.name = %s', call_args[0])
        self.assertIn('CL001', call_args[1])
        
        # Check result structure
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['video_id'], 'VID001')
        self.assertEqual(result['youtube'], 'https://youtube.com/watch?v=123')
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_with_week_filter(self, mock_sql):
        """Test get_video_urls with week_no filter"""
        from tap_lms.utils.video_api import get_video_urls
        
        mock_base_data = [{
            'video_id': 'VID002',
            'video_name': 'Advanced Python',
            'video_youtube_url': 'https://youtube.com/watch?v=456',
            'video_plio_url': None,
            'video_file': None,
            'duration': '15:00',
            'description': 'Advanced concepts',
            'difficulty_tier': 'Advanced',
            'estimated_duration': '15 minutes',
            'unit_name': 'Unit 5',
            'unit_order': 5,
            'course_level_id': 'CL002',
            'course_level_name': 'Python Advanced',
            'week_no': 3,
            'vertical_name': 'Programming'
        }]
        
        mock_sql.return_value = mock_base_data
        
        result = get_video_urls(week_no='3')
        
        # Check SQL was called with week filter
        call_args = mock_sql.call_args[0]
        self.assertIn('AND lul.week_no = %s', call_args[0])
        self.assertIn(3, call_args[1])
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_with_translation(self, mock_sql):
        """Test get_video_urls with language translation"""
        from tap_lms.utils.video_api import get_video_urls
        
        # First call returns base data
        base_data = [{
            'video_id': 'VID003',
            'video_name': 'Database Basics',
            'video_youtube_url': 'https://youtube.com/watch?v=789',
            'video_plio_url': None,
            'video_file': None,
            'duration': '20:00',
            'description': 'Learn databases',
            'difficulty_tier': 'Intermediate',
            'estimated_duration': '20 minutes',
            'unit_name': 'Unit 3',
            'unit_order': 3,
            'course_level_id': 'CL003',
            'course_level_name': 'Database Course',
            'week_no': 2,
            'vertical_name': 'Data'
        }]
        
        # Second call returns translation data
        translation_data = [{
            'video_id': 'VID003',
            'language': 'Spanish',
            'translated_name': 'Conceptos Básicos de Base de Datos',
            'translated_description': 'Aprende bases de datos',
            'translated_youtube_url': 'https://youtube.com/watch?v=789_es',
            'translated_plio_url': None,
            'translated_video_file': None
        }]
        
        mock_sql.side_effect = [base_data, translation_data]
        
        result = get_video_urls(language='Spanish')
        
        # Check translated content is used
        self.assertEqual(result['video_name'], 'Conceptos Básicos de Base de Datos')
        self.assertEqual(result['description'], 'Aprende bases de datos')
        self.assertEqual(result['youtube'], 'https://youtube.com/watch?v=789_es')
        self.assertEqual(result['language'], 'Spanish')
        
    @patch('tap_lms.utils.video_api.get_file_url')
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_with_video_source_filter(self, mock_sql, mock_get_file_url):
        """Test filtering by video source"""
        from tap_lms.utils.video_api import get_video_urls
        
        mock_get_file_url.return_value = 'https://example.com/files/video.mp4'
        
        mock_data = [{
            'video_id': 'VID004',
            'video_name': 'Multi-source Video',
            'video_youtube_url': 'https://youtube.com/watch?v=multi',
            'video_plio_url': 'https://plio.in/video/multi',
            'video_file': '/files/video.mp4',
            'duration': '25:00',
            'description': 'Video with multiple sources',
            'difficulty_tier': 'Intermediate',
            'estimated_duration': '25 minutes',
            'unit_name': 'Unit 4',
            'unit_order': 4,
            'course_level_id': 'CL004',
            'course_level_name': 'Multi Course',
            'week_no': 2,
            'vertical_name': 'General'
        }]
        
        mock_sql.return_value = mock_data
        
        # Test filtering for YouTube only
        result = get_video_urls(video_source='youtube')
        
        self.assertIn('youtube', result)
        self.assertNotIn('plio', result)
        self.assertNotIn('file', result)
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_multiple_videos(self, mock_sql):
        """Test when multiple videos are returned"""
        from tap_lms.utils.video_api import get_video_urls
        
        mock_data = [
            {
                'video_id': 'VID005',
                'video_name': 'Video 1',
                'video_youtube_url': 'https://youtube.com/watch?v=1',
                'video_plio_url': None,
                'video_file': None,
                'duration': '10:00',
                'description': 'First video',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '10 minutes',
                'unit_name': 'Unit 1',
                'unit_order': 1,
                'course_level_id': 'CL005',
                'course_level_name': 'Course 1',
                'week_no': 1,
                'vertical_name': 'Tech'
            },
            {
                'video_id': 'VID006',
                'video_name': 'Video 2',
                'video_youtube_url': 'https://youtube.com/watch?v=2',
                'video_plio_url': None,
                'video_file': None,
                'duration': '15:00',
                'description': 'Second video',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '15 minutes',
                'unit_name': 'Unit 2',
                'unit_order': 2,
                'course_level_id': 'CL005',
                'course_level_name': 'Course 1',
                'week_no': 1,
                'vertical_name': 'Tech'
            }
        ]
        
        mock_sql.return_value = mock_data
        
        result = get_video_urls()
        
        # Should return array for multiple videos
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['count'], 2)
        self.assertEqual(result[1]['count'], 2)
        
    @patch('tap_lms.utils.video_api.frappe.log_error')
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_error_handling(self, mock_sql, mock_log_error):
        """Test error handling in get_video_urls"""
        from tap_lms.utils.video_api import get_video_urls
        
        mock_sql.side_effect = Exception("Database error")
        
        result = get_video_urls()
        
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Database error')
        mock_log_error.assert_called_once()

    # ============= Test get_video_urls_aggregated =============
    
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_aggregated_single_week(self, mock_sql):
        """Test aggregated API with single week"""
        from tap_lms.utils.video_api import get_video_urls_aggregated
        
        mock_data = [
            {
                'video_id': 'VID007',
                'video_name': 'Week 1 Video 1',
                'video_youtube_url': 'https://youtube.com/watch?v=w1v1',
                'video_plio_url': None,
                'video_file': None,
                'duration': '10:00',
                'description': 'First video of week 1',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '10 minutes',
                'unit_name': 'Unit 1',
                'unit_order': 1,
                'course_level_id': 'CL006',
                'course_level_name': 'Weekly Course',
                'week_no': 1,
                'vertical_name': 'Tech'
            },
            {
                'video_id': 'VID008',
                'video_name': 'Week 1 Video 2',
                'video_youtube_url': 'https://youtube.com/watch?v=w1v2',
                'video_plio_url': None,
                'video_file': None,
                'duration': '15:00',
                'description': 'Second video of week 1',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '15 minutes',
                'unit_name': 'Unit 2',
                'unit_order': 2,
                'course_level_id': 'CL006',
                'course_level_name': 'Weekly Course',
                'week_no': 1,
                'vertical_name': 'Tech'
            }
        ]
        
        mock_sql.return_value = mock_data
        
        result = get_video_urls_aggregated(week_no=1)
        
        # Should return single object for single week
        self.assertIsInstance(result, dict)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['week_no'], 1)
        self.assertEqual(result['count'], 2)
        # URLs should be comma-separated
        self.assertIn(',', result['youtube'])
        self.assertEqual(result['youtube'], 'https://youtube.com/watch?v=w1v1,https://youtube.com/watch?v=w1v2')
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_urls_aggregated_multiple_weeks(self, mock_sql):
        """Test aggregated API with multiple weeks"""
        from tap_lms.utils.video_api import get_video_urls_aggregated
        
        mock_data = [
            {
                'video_id': 'VID009',
                'video_name': 'Week 1 Video',
                'video_youtube_url': 'https://youtube.com/watch?v=w1',
                'video_plio_url': None,
                'video_file': None,
                'duration': '10:00',
                'description': 'Week 1 content',
                'difficulty_tier': 'Beginner',
                'estimated_duration': '10 minutes',
                'unit_name': 'Unit 1',
                'unit_order': 1,
                'course_level_id': 'CL007',
                'course_level_name': 'Multi Week Course',
                'week_no': 1,
                'vertical_name': 'Tech'
            },
            {
                'video_id': 'VID010',
                'video_name': 'Week 2 Video',
                'video_youtube_url': 'https://youtube.com/watch?v=w2',
                'video_plio_url': None,
                'video_file': None,
                'duration': '15:00',
                'description': 'Week 2 content',
                'difficulty_tier': 'Intermediate',
                'estimated_duration': '15 minutes',
                'unit_name': 'Unit 3',
                'unit_order': 3,
                'course_level_id': 'CL007',
                'course_level_name': 'Multi Week Course',
                'week_no': 2,
                'vertical_name': 'Tech'
            }
        ]
        
        mock_sql.return_value = mock_data
        
        result = get_video_urls_aggregated()
        
        # Should return array for multiple weeks
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['week_no'], 1)
        self.assertEqual(result[1]['week_no'], 2)

    # ============= Test get_file_url helper =============
    
    @patch('tap_lms.utils.video_api.frappe.utils.get_url')
    def test_get_file_url(self, mock_get_url):
        """Test file URL generation"""
        from tap_lms.utils.video_api import get_file_url
        
        mock_get_url.return_value = 'https://example.com'
        
        # Test with /files/ prefix
        result = get_file_url('/files/video.mp4')
        self.assertEqual(result, 'https://example.com/files/video.mp4')
        
        # Test with http prefix
        result = get_file_url('https://cdn.example.com/video.mp4')
        self.assertEqual(result, 'https://cdn.example.com/video.mp4')
        
        # Test with plain filename
        result = get_file_url('video.mp4')
        self.assertEqual(result, 'https://example.com/files/video.mp4')
        
        # Test with None
        result = get_file_url(None)
        self.assertIsNone(result)
        
        # Test with empty string
        result = get_file_url('')
        self.assertIsNone(result)

    # ============= Test get_available_filters =============
    
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_available_filters_success(self, mock_sql):
        """Test getting available filter options"""
        from tap_lms.utils.video_api import get_available_filters
        
        # Mock responses for each SQL query
        mock_sql.side_effect = [
            # Course levels
            [{'name': 'CL001', 'display_name': 'Python Course'},
             {'name': 'CL002', 'display_name': 'Java Course'}],
            # Weeks
            [{'week_no': 1}, {'week_no': 2}, {'week_no': 3}],
            # Languages
            [{'language': 'English'}, {'language': 'Spanish'}, {'language': 'French'}],
            # Verticals
            [{'name': 'VERT001', 'display_name': 'Programming'},
             {'name': 'VERT002', 'display_name': 'Data Science'}]
        ]
        
        result = get_available_filters()
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(result['course_levels']), 2)
        self.assertEqual(result['weeks'], [1, 2, 3])
        self.assertEqual(result['languages'], ['English', 'Spanish', 'French'])
        self.assertEqual(result['video_sources'], ['youtube', 'plio', 'file'])
        self.assertEqual(len(result['verticals']), 2)
        
    @patch('tap_lms.utils.video_api.frappe.log_error')
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_available_filters_error(self, mock_sql, mock_log_error):
        """Test error handling in get_available_filters"""
        from tap_lms.utils.video_api import get_available_filters
        
        mock_sql.side_effect = Exception("Database connection failed")
        
        result = get_available_filters()
        
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Database connection failed')
        mock_log_error.assert_called_once()

    # ============= Test get_video_statistics =============
    
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_statistics_success(self, mock_sql):
        """Test getting video statistics"""
        from tap_lms.utils.video_api import get_video_statistics
        
        mock_sql.side_effect = [
            # Video stats
            [{'total_videos': 100, 'youtube_videos': 80, 'plio_videos': 50, 'file_videos': 30}],
            # Course stats
            [{'total_courses': 10, 'total_weeks': 12, 'total_verticals': 5}],
            # Language stats
            [{'available_languages': 3}]
        ]
        
        result = get_video_statistics()
        
        self.assertEqual(result['status'], 'success')
        stats = result['statistics']
        self.assertEqual(stats['total_videos'], 100)
        self.assertEqual(stats['youtube_videos'], 80)
        self.assertEqual(stats['plio_videos'], 50)
        self.assertEqual(stats['file_videos'], 30)
        self.assertEqual(stats['total_courses'], 10)
        self.assertEqual(stats['total_weeks'], 12)
        self.assertEqual(stats['total_verticals'], 5)
        self.assertEqual(stats['available_languages'], 3)
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_get_video_statistics_empty_data(self, mock_sql):
        """Test statistics with empty database"""
        from tap_lms.utils.video_api import get_video_statistics
        
        mock_sql.side_effect = [[], [], []]
        
        result = get_video_statistics()
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['statistics'], {})

    # ============= Test test_connection =============
    
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_test_connection_success(self, mock_sql):
        """Test connection test endpoint"""
        from tap_lms.utils.video_api import test_connection
        
        mock_sql.return_value = [{'video_count': 50}]
        
        result = test_connection()
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'API is working correctly')
        self.assertEqual(result['video_count'], 50)
        self.assertIn('endpoints', result)
        self.assertEqual(len(result['endpoints']), 5)
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_test_connection_failure(self, mock_sql):
        """Test connection test with database error"""
        from tap_lms.utils.video_api import test_connection
        
        mock_sql.side_effect = Exception("Cannot connect to database")
        
        result = test_connection()
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Cannot connect to database', result['message'])


class TestVideoAPIIntegration(unittest.TestCase):
    """Integration tests for complex scenarios"""
    
    def setUp(self):
        """Set up test environment before each test"""
        # Mock frappe.whitelist decorator
        self.whitelist_patcher = patch('frappe.whitelist', lambda **kwargs: lambda func: func)
        self.whitelist_patcher.start()
        
    def tearDown(self):
        """Clean up after each test"""
        self.whitelist_patcher.stop()
    
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_complex_filter_combination(self, mock_sql):
        """Test combining multiple filters"""
        from tap_lms.utils.video_api import get_video_urls
        
        mock_data = [{
            'video_id': 'VID011',
            'video_name': 'Complex Filter Test',
            'video_youtube_url': 'https://youtube.com/watch?v=complex',
            'video_plio_url': 'https://plio.in/complex',
            'video_file': '/files/complex.mp4',
            'duration': '30:00',
            'description': 'Testing multiple filters',
            'difficulty_tier': 'Advanced',
            'estimated_duration': '30 minutes',
            'unit_name': 'Unit X',
            'unit_order': 10,
            'course_level_id': 'CL008',
            'course_level_name': 'Advanced Course',
            'week_no': 5,
            'vertical_name': 'Advanced Tech'
        }]
        
        # First call for base data, second for translations
        mock_sql.side_effect = [
            mock_data,
            []  # No translations
        ]
        
        result = get_video_urls(
            course_level='CL008',
            week_no='5',
            language='English',
            video_source='plio'
        )
        
        # Verify all filters were applied
        first_call = mock_sql.call_args_list[0]
        query = first_call[0][0]
        params = first_call[0][1]
        
        self.assertIn('AND cl.name = %s', query)
        self.assertIn('AND lul.week_no = %s', query)
        self.assertIn('CL008', params)
        self.assertIn(5, params)
        
        # Verify only plio URL is returned
        self.assertIn('plio', result)
        self.assertNotIn('youtube', result)
        self.assertNotIn('file', result)
        
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_video_without_any_urls(self, mock_sql):
        """Test handling videos with no valid URLs"""
        from tap_lms.utils.video_api import get_video_urls
        
        mock_data = [{
            'video_id': 'VID012',
            'video_name': 'No URLs Video',
            'video_youtube_url': None,
            'video_plio_url': None,
            'video_file': None,
            'duration': None,
            'description': 'Video without URLs',
            'difficulty_tier': 'Beginner',
            'estimated_duration': '0 minutes',
            'unit_name': 'Unit 0',
            'unit_order': 0,
            'course_level_id': 'CL009',
            'course_level_name': 'Empty Course',
            'week_no': 1,
            'vertical_name': 'None'
        }]
        
        mock_sql.return_value = mock_data
        
        result = get_video_urls()
        
        # Should return empty list as no valid video URLs
        self.assertEqual(result, [])
    
    @patch('tap_lms.utils.video_api.frappe.db.sql')
    def test_special_characters_in_data(self, mock_sql):
        """Test handling of special characters in video data"""
        from tap_lms.utils.video_api import get_video_urls
        
        mock_data = [{
            'video_id': 'VID_SPECIAL',
            'video_name': "Video with 'quotes' and \"double quotes\"",
            'video_youtube_url': 'https://youtube.com/watch?v=abc&feature=related',
            'video_plio_url': None,
            'video_file': '/files/video with spaces.mp4',
            'duration': '10:30',
            'description': 'Description with <html> tags & special chars',
            'difficulty_tier': 'Beginner',
            'estimated_duration': '10 minutes',
            'unit_name': 'Unit & Module',
            'unit_order': 1,
            'course_level_id': 'CL-001',
            'course_level_name': 'Course: Advanced Topics',
            'week_no': 1,
            'vertical_name': 'Tech & Science'
        }]
        
        mock_sql.return_value = mock_data
        
        result = get_video_urls()
        
        # Should handle special characters correctly
        self.assertEqual(result['video_name'], "Video with 'quotes' and \"double quotes\"")
        self.assertEqual(result['description'], 'Description with <html> tags & special chars')