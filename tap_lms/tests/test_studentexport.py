# import pytest
# import os
# import csv
# import json
# import tempfile
# import shutil
# import sys
# from unittest.mock import Mock, patch, MagicMock, call, mock_open, ANY
# from datetime import datetime
# from pathlib import Path

# # Mock frappe module before importing studentexport
# sys.modules['frappe'] = MagicMock()
# sys.modules['frappe.utils'] = MagicMock()

# # Now import the functions to test
# from ..utils.studentexport import (
#     export_students_simple,
#     create_index_file,
#     export_students_web
# )


# class TestExportStudentsSimple:
#     """Test cases for export_students_simple function"""
    
#     @pytest.fixture
#     def temp_dir(self):
#         """Create a temporary directory for test files"""
#         temp_dir = tempfile.mkdtemp()
#         yield temp_dir
#         shutil.rmtree(temp_dir)
    
#     @pytest.fixture(autouse=True)
#     def mock_frappe_modules(self):
#         """Ensure frappe modules are mocked for all tests"""
#         if 'frappe' not in sys.modules:
#             sys.modules['frappe'] = MagicMock()
#         if 'frappe.utils' not in sys.modules:
#             sys.modules['frappe.utils'] = MagicMock()
#         yield
    
#     def create_mock_student_data(self, count, with_enrollment=True):
#         """Helper to create mock student data"""
#         data = []
#         for i in range(1, count + 1):
#             record = {
#                 'student_id': f'STU{i:03d}',
#                 'student_name': f'Student {i}',
#                 'phone': f'987654{i:04d}',
#                 'school': f'School {(i % 3) + 1}',
#                 'glific_id': f'GLIF{i:03d}',
#                 'language': 'English' if i % 2 == 0 else 'Hindi',
#                 'student_grade': f'Grade {(i % 12) + 1}',
#                 'gender': 'Male' if i % 2 == 0 else 'Female',
#             }
#             if with_enrollment:
#                 record.update({
#                     'enrollment_id': f'ENR{i:03d}',
#                     'course': f'Course {(i % 5) + 1}',
#                     'date_joining': '2024-01-01',
#                     'batch': f'Batch {(i % 3) + 1}',
#                     'enrollment_grade': f'Grade {(i % 12) + 1}',
#                     'enrollment_school': f'School {(i % 3) + 1}'
#                 })
#             else:
#                 record.update({
#                     'enrollment_id': None,
#                     'course': None,
#                     'date_joining': None,
#                     'batch': None,
#                     'enrollment_grade': None,
#                     'enrollment_school': None
#                 })
#             data.append(record)
#         return data
    
#     @patch('tap_lms.utils.studentexport.create_index_file')
#     @patch('tap_lms.utils.studentexport.frappe')
#     def test_batch_processing(self, mock_frappe, mock_create_index, temp_dir):
#         """Test that large datasets are split into batches"""
#         # Setup directory
#         export_dir = os.path.join(temp_dir, 'student_exports')
#         os.makedirs(export_dir, exist_ok=True)
        
#         # Setup mocks for 250 records with batch size of 100
#         mock_frappe.get_site_path.return_value = temp_dir
#         mock_frappe.db.sql.side_effect = [
#             [{'count': 250}],  # Total count
#             self.create_mock_student_data(100),  # Batch 1
#             self.create_mock_student_data(100),  # Batch 2
#             self.create_mock_student_data(50),   # Batch 3
#         ]
        
#         mock_datetime = MagicMock()
#         mock_datetime.strftime.return_value = '20240101_120000'
#         mock_frappe.utils.now_datetime.return_value = mock_datetime
#         mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
#         # Run export with batch size of 100
#         with patch('os.path.getsize', return_value=1024*1024):  # Mock file size
#             result = export_students_simple(site_name='test_site', batch_size=100)
        
#         # Verify results
#         assert result is not None
#         assert result['total_records'] == 250
#         assert result['total_files'] == 3
#         assert len(result['files']) == 3
        
#         # Verify SQL queries (1 count + 3 data queries)
#         assert mock_frappe.db.sql.call_count == 4
    
#     @patch('tap_lms.utils.studentexport.create_index_file')
#     @patch('tap_lms.utils.studentexport.frappe')
#     def test_empty_dataset(self, mock_frappe, mock_create_index, temp_dir):
#         """Test export with no student data"""
#         # Setup directory
#         export_dir = os.path.join(temp_dir, 'student_exports')
#         os.makedirs(export_dir, exist_ok=True)
        
#         mock_frappe.get_site_path.return_value = temp_dir
#         mock_frappe.db.sql.side_effect = [
#             [{'count': 0}],  # Total count
#         ]
        
#         mock_datetime = MagicMock()
#         mock_datetime.strftime.return_value = '20240101_120000'
#         mock_frappe.utils.now_datetime.return_value = mock_datetime
#         mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
#         # Run export
#         result = export_students_simple(site_name='test_site', batch_size=100)
        
#         # Verify results
#         assert result is not None
#         assert result['total_records'] == 0
#         assert result['total_files'] == 0
#         assert len(result['files']) == 0
    
#     @patch('tap_lms.utils.studentexport.create_index_file')
#     @patch('tap_lms.utils.studentexport.frappe')
#     def test_students_without_enrollments(self, mock_frappe, mock_create_index, temp_dir):
#         """Test export of students without enrollment data"""
#         # Setup directory
#         export_dir = os.path.join(temp_dir, 'student_exports')
#         os.makedirs(export_dir, exist_ok=True)
        
#         mock_frappe.get_site_path.return_value = temp_dir
#         mock_frappe.db.sql.side_effect = [
#             [{'count': 10}],  # Total count
#             self.create_mock_student_data(10, with_enrollment=False)  # Data without enrollments
#         ]
        
#         mock_datetime = MagicMock()
#         mock_datetime.strftime.return_value = '20240101_120000'
#         mock_frappe.utils.now_datetime.return_value = mock_datetime
#         mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
#         # Run export
#         with patch('os.path.getsize', return_value=1024*1024):  # Mock file size
#             result = export_students_simple(site_name='test_site', batch_size=100)
        
#         # Verify results
#         assert result is not None
#         assert result['total_records'] == 10
#         assert result['total_files'] == 1
    
#     @patch('tap_lms.utils.studentexport.create_index_file')
#     @patch('builtins.print')
#     @patch('tap_lms.utils.studentexport.frappe')
#     def test_file_creation_error_handling(self, mock_frappe, mock_print, mock_create_index, temp_dir):
#         """Test handling of file creation errors"""
#         # Setup directory
#         export_dir = os.path.join(temp_dir, 'student_exports')
#         os.makedirs(export_dir, exist_ok=True)
        
#         mock_frappe.get_site_path.return_value = temp_dir
#         mock_frappe.db.sql.side_effect = [
#             [{'count': 10}],
#             self.create_mock_student_data(10)
#         ]
        
#         # Mock file doc insertion to raise error
#         mock_file_doc = MagicMock()
#         mock_file_doc.insert.side_effect = Exception("File creation error")
#         mock_frappe.get_doc.return_value = mock_file_doc
        
#         mock_datetime = MagicMock()
#         mock_datetime.strftime.return_value = '20240101_120000'
#         mock_frappe.utils.now_datetime.return_value = mock_datetime
#         mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
#         # Run export - should handle error gracefully
#         with patch('os.path.getsize', return_value=1024*1024):  # Mock file size
#             result = export_students_simple(site_name='test_site', batch_size=100)
        
#         # Should still return success despite file doc error
#         assert result is not None
#         assert result['total_records'] == 10
        
#         # Verify warning was printed
#         warning_printed = any('Warning: Could not create File record' in str(call) 
#                             for call in mock_print.call_args_list)
#         assert warning_printed
    
#     @patch('tap_lms.utils.studentexport.frappe')
#     def test_database_error_handling(self, mock_frappe, temp_dir):
#         """Test handling of database errors"""
#         mock_frappe.get_site_path.return_value = temp_dir
#         mock_frappe.db.sql.side_effect = Exception("Database connection error")
        
#         # Run export
#         result = export_students_simple(site_name='test_site', batch_size=100)
        
#         # Should return None on error
#         assert result is None
        
#         # Verify error was logged and rollback was called
#         mock_frappe.log_error.assert_called()
#         mock_frappe.db.rollback.assert_called()
#         mock_frappe.destroy.assert_called()
    
#     @patch('tap_lms.utils.studentexport.create_index_file')
#     @patch('tap_lms.utils.studentexport.frappe')
#     def test_csv_file_structure(self, mock_frappe, mock_create_index, temp_dir):
#         """Test that CSV files have correct structure and data"""
#         # Create actual directory
#         export_dir = os.path.join(temp_dir, 'student_exports')
#         os.makedirs(export_dir, exist_ok=True)
        
#         mock_frappe.get_site_path.return_value = temp_dir
#         test_data = self.create_mock_student_data(5)
#         mock_frappe.db.sql.side_effect = [
#             [{'count': 5}],
#             test_data
#         ]
        
#         mock_datetime = MagicMock()
#         mock_datetime.strftime.return_value = '20240101_120000'
#         mock_frappe.utils.now_datetime.return_value = mock_datetime
#         mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
#         # Run export
#         with patch('os.path.getsize', return_value=1024):  # Mock file size
#             result = export_students_simple(site_name='test_site', batch_size=100)
        
#         # Check if CSV file was created
#         csv_files = list(Path(export_dir).glob('*.csv'))
#         assert len(csv_files) == 1
        
#         # Read and verify CSV content
#         with open(csv_files[0], 'r', encoding='utf-8') as f:
#             reader = csv.DictReader(f)
#             rows = list(reader)
            
#             # Verify headers
#             expected_headers = [
#                 'student_id', 'student_name', 'phone', 'school', 'glific_id',
#                 'language', 'student_grade', 'gender', 'enrollment_id',
#                 'course', 'date_joining', 'batch', 'enrollment_grade', 'enrollment_school'
#             ]
#             assert reader.fieldnames == expected_headers
            
#             # Verify data
#             assert len(rows) == 5
#             assert rows[0]['student_id'] == 'STU001'
#             assert rows[0]['student_name'] == 'Student 1'
    
#     @patch('tap_lms.utils.studentexport.create_index_file')
#     @patch('tap_lms.utils.studentexport.frappe')
#     def test_site_initialization(self, mock_frappe, mock_create_index, temp_dir):
#         """Test site initialization with and without site_name"""
#         # Setup directory
#         export_dir = os.path.join(temp_dir, 'student_exports')
#         os.makedirs(export_dir, exist_ok=True)
        
#         mock_frappe.get_site_path.return_value = temp_dir
#         mock_frappe.db.sql.side_effect = [
#             [{'count': 0}],
#         ]
        
#         mock_datetime = MagicMock()
#         mock_datetime.strftime.return_value = '20240101_120000'
#         mock_frappe.utils.now_datetime.return_value = mock_datetime
#         mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
#         # Test with site_name
#         export_students_simple(site_name='test_site', batch_size=100)
#         mock_frappe.init.assert_called_with('test_site')
        
#         # Reset mocks
#         mock_frappe.reset_mock()
#         mock_frappe.get_site_path.return_value = temp_dir
#         mock_frappe.db.sql.side_effect = [
#             [{'count': 0}],
#         ]
#         mock_frappe.utils.now_datetime.return_value = mock_datetime
#         mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
#         # Test without site_name
#         export_students_simple(site_name=None, batch_size=100)
#         mock_frappe.init_site.assert_called()


# class TestCreateIndexFile:
#     """Test cases for create_index_file function"""
    
#     @pytest.fixture
#     def temp_dir(self):
#         """Create a temporary directory for test files"""
#         temp_dir = tempfile.mkdtemp()
#         yield temp_dir
#         shutil.rmtree(temp_dir)
    
#     def test_index_file_creation(self, temp_dir):
#         """Test HTML index file creation"""
#         timestamp = '20240101_120000'
#         file_info = [
#             {
#                 'filename': 'students_export_20240101_120000_batch_001.csv',
#                 'file_url': '/private/files/student_exports/students_export_20240101_120000_batch_001.csv',
#                 'records': 100,
#                 'file_size_mb': 1.5
#             },
#             {
#                 'filename': 'students_export_20240101_120000_batch_002.csv',
#                 'file_url': '/private/files/student_exports/students_export_20240101_120000_batch_002.csv',
#                 'records': 50,
#                 'file_size_mb': 0.8
#             }
#         ]
#         summary = {
#             'export_time': '2024-01-01 12:00:00',
#             'total_records': 150,
#             'total_files': 2,
#             'batch_size': 100
#         }
        
#         # Create index file
#         create_index_file(temp_dir, timestamp, file_info, summary)
        
#         # Verify file was created
#         index_file = os.path.join(temp_dir, f'index_{timestamp}.html')
#         assert os.path.exists(index_file)
        
#         # Read and verify content
#         with open(index_file, 'r', encoding='utf-8') as f:
#             content = f.read()
            
#             # Check key elements
#             assert '<title>Student Export - 20240101_120000</title>' in content
#             assert 'Total Records:</strong> 150' in content
#             assert 'Total Files:</strong> 2' in content
#             assert 'Batch Size:</strong> 100' in content
            
#             # Check file table entries
#             assert 'students_export_20240101_120000_batch_001.csv' in content
#             assert 'students_export_20240101_120000_batch_002.csv' in content
#             assert '<td>100</td>' in content  # Records count formatting changed
#             assert '<td>50</td>' in content   # Records count formatting changed
#             assert '<td>1.5</td>' in content  # File size
#             assert '<td>0.8</td>' in content  # File size
            
#             # Check download links
#             assert 'href="/private/files/student_exports/students_export_20240101_120000_batch_001.csv"' in content
#             assert 'href="/private/files/student_exports/students_export_20240101_120000_batch_002.csv"' in content
            
#             # Check CSV structure documentation
#             assert '<li><strong>student_id</strong>' in content
#             assert '<li><strong>enrollment_id</strong>' in content
    
#     def test_index_file_with_empty_data(self, temp_dir):
#         """Test index file creation with no export files"""
#         timestamp = '20240101_120000'
#         file_info = []
#         summary = {
#             'export_time': '2024-01-01 12:00:00',
#             'total_records': 0,
#             'total_files': 0,
#             'batch_size': 100
#         }
        
#         # Create index file
#         create_index_file(temp_dir, timestamp, file_info, summary)
        
#         # Verify file was created
#         index_file = os.path.join(temp_dir, f'index_{timestamp}.html')
#         assert os.path.exists(index_file)
        
#         # Read and verify content
#         with open(index_file, 'r', encoding='utf-8') as f:
#             content = f.read()
#             assert 'Total Records:</strong> 0' in content
#             assert 'Total Files:</strong> 0' in content



import pytest
import os
import csv
import json
import tempfile
import shutil
import sys
from unittest.mock import Mock, patch, MagicMock, call, mock_open, ANY
from datetime import datetime
from pathlib import Path

# Mock frappe module before importing studentexport
sys.modules['frappe'] = MagicMock()
sys.modules['frappe.utils'] = MagicMock()

# Now import the functions to test
from ..utils.studentexport import (
    export_students_simple,
    create_index_file,
    export_students_web
)


class TestExportStudentsSimple:
    """Test cases for export_students_simple function"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture(autouse=True)
    def mock_frappe_modules(self):
        """Ensure frappe modules are mocked for all tests"""
        if 'frappe' not in sys.modules:
            sys.modules['frappe'] = MagicMock()
        if 'frappe.utils' not in sys.modules:
            sys.modules['frappe.utils'] = MagicMock()
        yield
    
    def create_mock_student_data(self, count, with_enrollment=True):
        """Helper to create mock student data"""
        data = []
        for i in range(1, count + 1):
            record = {
                'student_id': f'STU{i:03d}',
                'student_name': f'Student {i}',
                'phone': f'987654{i:04d}',
                'school': f'School {(i % 3) + 1}',
                'glific_id': f'GLIF{i:03d}',
                'language': 'English' if i % 2 == 0 else 'Hindi',
                'student_grade': f'Grade {(i % 12) + 1}',
                'gender': 'Male' if i % 2 == 0 else 'Female',
            }
            if with_enrollment:
                record.update({
                    'enrollment_id': f'ENR{i:03d}',
                    'course': f'Course {(i % 5) + 1}',
                    'date_joining': '2024-01-01',
                    'batch': f'Batch {(i % 3) + 1}',
                    'enrollment_grade': f'Grade {(i % 12) + 1}',
                    'enrollment_school': f'School {(i % 3) + 1}'
                })
            else:
                record.update({
                    'enrollment_id': None,
                    'course': None,
                    'date_joining': None,
                    'batch': None,
                    'enrollment_grade': None,
                    'enrollment_school': None
                })
            data.append(record)
        return data
    
    @patch('tap_lms.utils.studentexport.create_index_file')
    @patch('tap_lms.utils.studentexport.frappe')
    def test_batch_processing(self, mock_frappe, mock_create_index, temp_dir):
        """Test that large datasets are split into batches"""
        # Setup directory
        export_dir = os.path.join(temp_dir, 'student_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        # Setup mocks for 250 records with batch size of 100
        mock_frappe.get_site_path.return_value = temp_dir
        mock_frappe.db.sql.side_effect = [
            [{'count': 250}],  # Total count
            self.create_mock_student_data(100),  # Batch 1
            self.create_mock_student_data(100),  # Batch 2
            self.create_mock_student_data(50),   # Batch 3
        ]
        
        mock_datetime = MagicMock()
        mock_datetime.strftime.return_value = '20240101_120000'
        mock_frappe.utils.now_datetime.return_value = mock_datetime
        mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
        # Run export with batch size of 100
        with patch('os.path.getsize', return_value=1024*1024):  # Mock file size
            result = export_students_simple(site_name='test_site', batch_size=100)
        
        # Verify results
        assert result is not None
        assert result['total_records'] == 250
        assert result['total_files'] == 3
        assert len(result['files']) == 3
        
        # Verify SQL queries (1 count + 3 data queries)
        assert mock_frappe.db.sql.call_count == 4
    
    @patch('tap_lms.utils.studentexport.create_index_file')
    @patch('tap_lms.utils.studentexport.frappe')
    def test_empty_dataset(self, mock_frappe, mock_create_index, temp_dir):
        """Test export with no student data"""
        # Setup directory
        export_dir = os.path.join(temp_dir, 'student_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        mock_frappe.get_site_path.return_value = temp_dir
        mock_frappe.db.sql.side_effect = [
            [{'count': 0}],  # Total count
        ]
        
        mock_datetime = MagicMock()
        mock_datetime.strftime.return_value = '20240101_120000'
        mock_frappe.utils.now_datetime.return_value = mock_datetime
        mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
        # Run export
        result = export_students_simple(site_name='test_site', batch_size=100)
        
        # Verify results
        assert result is not None
        assert result['total_records'] == 0
        assert result['total_files'] == 0
        assert len(result['files']) == 0
    
    @patch('tap_lms.utils.studentexport.create_index_file')
    @patch('tap_lms.utils.studentexport.frappe')
    def test_students_without_enrollments(self, mock_frappe, mock_create_index, temp_dir):
        """Test export of students without enrollment data"""
        # Setup directory
        export_dir = os.path.join(temp_dir, 'student_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        mock_frappe.get_site_path.return_value = temp_dir
        mock_frappe.db.sql.side_effect = [
            [{'count': 10}],  # Total count
            self.create_mock_student_data(10, with_enrollment=False)  # Data without enrollments
        ]
        
        mock_datetime = MagicMock()
        mock_datetime.strftime.return_value = '20240101_120000'
        mock_frappe.utils.now_datetime.return_value = mock_datetime
        mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
        # Run export
        with patch('os.path.getsize', return_value=1024*1024):  # Mock file size
            result = export_students_simple(site_name='test_site', batch_size=100)
        
        # Verify results
        assert result is not None
        assert result['total_records'] == 10
        assert result['total_files'] == 1
    
    @patch('tap_lms.utils.studentexport.create_index_file')
    @patch('builtins.print')
    @patch('tap_lms.utils.studentexport.frappe')
    def test_file_creation_error_handling(self, mock_frappe, mock_print, mock_create_index, temp_dir):
        """Test handling of file creation errors"""
        # Setup directory
        export_dir = os.path.join(temp_dir, 'student_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        mock_frappe.get_site_path.return_value = temp_dir
        mock_frappe.db.sql.side_effect = [
            [{'count': 10}],
            self.create_mock_student_data(10)
        ]
        
        # Mock file doc insertion to raise error
        mock_file_doc = MagicMock()
        mock_file_doc.insert.side_effect = Exception("File creation error")
        mock_frappe.get_doc.return_value = mock_file_doc
        
        mock_datetime = MagicMock()
        mock_datetime.strftime.return_value = '20240101_120000'
        mock_frappe.utils.now_datetime.return_value = mock_datetime
        mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
        # Run export - should handle error gracefully
        with patch('os.path.getsize', return_value=1024*1024):  # Mock file size
            result = export_students_simple(site_name='test_site', batch_size=100)
        
        # Should still return success despite file doc error
        assert result is not None
        assert result['total_records'] == 10
        
        # Verify warning was printed
        warning_printed = any('Warning: Could not create File record' in str(call) 
                            for call in mock_print.call_args_list)
        assert warning_printed
    
    @patch('tap_lms.utils.studentexport.frappe')
    def test_database_error_handling(self, mock_frappe, temp_dir):
        """Test handling of database errors"""
        mock_frappe.get_site_path.return_value = temp_dir
        mock_frappe.db.sql.side_effect = Exception("Database connection error")
        
        # Run export
        result = export_students_simple(site_name='test_site', batch_size=100)
        
        # Should return None on error
        assert result is None
        
        # Verify error was logged and rollback was called
        mock_frappe.log_error.assert_called()
        mock_frappe.db.rollback.assert_called()
        mock_frappe.destroy.assert_called()
    
    @patch('tap_lms.utils.studentexport.create_index_file')
    @patch('tap_lms.utils.studentexport.frappe')
    def test_csv_file_structure(self, mock_frappe, mock_create_index, temp_dir):
        """Test that CSV files have correct structure and data"""
        # Create actual directory
        export_dir = os.path.join(temp_dir, 'student_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        mock_frappe.get_site_path.return_value = temp_dir
        test_data = self.create_mock_student_data(5)
        mock_frappe.db.sql.side_effect = [
            [{'count': 5}],
            test_data
        ]
        
        mock_datetime = MagicMock()
        mock_datetime.strftime.return_value = '20240101_120000'
        mock_frappe.utils.now_datetime.return_value = mock_datetime
        mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
        # Run export
        with patch('os.path.getsize', return_value=1024):  # Mock file size
            result = export_students_simple(site_name='test_site', batch_size=100)
        
        # Check if CSV file was created
        csv_files = list(Path(export_dir).glob('*.csv'))
        assert len(csv_files) == 1
        
        # Read and verify CSV content
        with open(csv_files[0], 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            # Verify headers
            expected_headers = [
                'student_id', 'student_name', 'phone', 'school', 'glific_id',
                'language', 'student_grade', 'gender', 'enrollment_id',
                'course', 'date_joining', 'batch', 'enrollment_grade', 'enrollment_school'
            ]
            assert reader.fieldnames == expected_headers
            
            # Verify data
            assert len(rows) == 5
            assert rows[0]['student_id'] == 'STU001'
            assert rows[0]['student_name'] == 'Student 1'
    
    @patch('tap_lms.utils.studentexport.create_index_file')
    @patch('tap_lms.utils.studentexport.frappe')
    def test_site_initialization(self, mock_frappe, mock_create_index, temp_dir):
        """Test site initialization with and without site_name"""
        # Setup directory
        export_dir = os.path.join(temp_dir, 'student_exports')
        os.makedirs(export_dir, exist_ok=True)
        
        mock_frappe.get_site_path.return_value = temp_dir
        mock_frappe.db.sql.side_effect = [
            [{'count': 0}],
        ]
        
        mock_datetime = MagicMock()
        mock_datetime.strftime.return_value = '20240101_120000'
        mock_frappe.utils.now_datetime.return_value = mock_datetime
        mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
        # Test with site_name
        export_students_simple(site_name='test_site', batch_size=100)
        mock_frappe.init.assert_called_with('test_site')
        
        # Reset mocks
        mock_frappe.reset_mock()
        mock_frappe.get_site_path.return_value = temp_dir
        mock_frappe.db.sql.side_effect = [
            [{'count': 0}],
        ]
        mock_frappe.utils.now_datetime.return_value = mock_datetime
        mock_frappe.utils.now.return_value = '2024-01-01 12:00:00'
        
        # Test without site_name
        export_students_simple(site_name=None, batch_size=100)
        mock_frappe.init_site.assert_called()


class TestCreateIndexFile:
    """Test cases for create_index_file function"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_index_file_creation(self, temp_dir):
        """Test HTML index file creation"""
        timestamp = '20240101_120000'
        file_info = [
            {
                'filename': 'students_export_20240101_120000_batch_001.csv',
                'file_url': '/private/files/student_exports/students_export_20240101_120000_batch_001.csv',
                'records': 100,
                'file_size_mb': 1.5
            },
            {
                'filename': 'students_export_20240101_120000_batch_002.csv',
                'file_url': '/private/files/student_exports/students_export_20240101_120000_batch_002.csv',
                'records': 50,
                'file_size_mb': 0.8
            }
        ]
        summary = {
            'export_time': '2024-01-01 12:00:00',
            'total_records': 150,
            'total_files': 2,
            'batch_size': 100
        }
        
        # Create index file
        create_index_file(temp_dir, timestamp, file_info, summary)
        
        # Verify file was created
        index_file = os.path.join(temp_dir, f'index_{timestamp}.html')
        assert os.path.exists(index_file)
        
        # Read and verify content
        with open(index_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Check key elements
            assert '<title>Student Export - 20240101_120000</title>' in content
            assert 'Total Records:</strong> 150' in content
            assert 'Total Files:</strong> 2' in content
            assert 'Batch Size:</strong> 100' in content
            
            # Check file table entries
            assert 'students_export_20240101_120000_batch_001.csv' in content
            assert 'students_export_20240101_120000_batch_002.csv' in content
            assert '<td>100</td>' in content  # Records count formatting changed
            assert '<td>50</td>' in content   # Records count formatting changed
            assert '<td>1.5</td>' in content  # File size
            assert '<td>0.8</td>' in content  # File size
            
            # Check download links
            assert 'href="/private/files/student_exports/students_export_20240101_120000_batch_001.csv"' in content
            assert 'href="/private/files/student_exports/students_export_20240101_120000_batch_002.csv"' in content
            
            # Check CSV structure documentation
            assert '<li><strong>student_id</strong>' in content
            assert '<li><strong>enrollment_id</strong>' in content
    
    def test_index_file_with_empty_data(self, temp_dir):
        """Test index file creation with no export files"""
        timestamp = '20240101_120000'
        file_info = []
        summary = {
            'export_time': '2024-01-01 12:00:00',
            'total_records': 0,
            'total_files': 0,
            'batch_size': 100
        }
        
        # Create index file
        create_index_file(temp_dir, timestamp, file_info, summary)
        
        # Verify file was created
        index_file = os.path.join(temp_dir, f'index_{timestamp}.html')
        assert os.path.exists(index_file)
        
        # Read and verify content
        with open(index_file, 'r', encoding='utf-8') as f:
            content = f.read()
            assert 'Total Records:</strong> 0' in content
            assert 'Total Files:</strong> 0' in content