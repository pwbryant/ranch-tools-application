from io import BytesIO
import os
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import pandas as pd

from django.contrib.messages import get_messages
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.http import HttpResponse
from django.test import TestCase, RequestFactory, override_settings

from ranch_tools.database_management.views import DatabaseManagementView
from ranch_tools.preg_check.models import Cow, PregCheck
from datetime import date


class DatabaseExportTestCase(TestCase):
    """Test cases for database export functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.factory = RequestFactory()
        self.view = DatabaseManagementView()
        
        # Create test cows
        self.cow1 = Cow.objects.create(
            ear_tag_id='T001',
            birth_year=2020,
            eid='EID001'
        )
        
        self.cow2 = Cow.objects.create(
            ear_tag_id='T002',
            birth_year=2019,
            eid='EID002'
        )
        
        # Cow with missing identifiers
        self.cow_empty = Cow.objects.create(
            ear_tag_id='',
            birth_year=2021,
            eid=None
        )
        
        # Create test pregnancy checks
        self.pregcheck1 = PregCheck.objects.create(
            cow=self.cow1,
            breeding_season=2023,
            check_date=date(2023, 6, 15),
            comments='First check',
            is_pregnant=True,
            recheck=False
        )
        
        self.pregcheck2 = PregCheck.objects.create(
            cow=self.cow2,
            breeding_season=2023,
            check_date=date(2023, 6, 20),
            comments='Second check',
            is_pregnant=False,
            recheck=True
        )
        
        # Pregnancy check without cow
        self.pregcheck_no_cow = PregCheck.objects.create(
            cow=None,
            breeding_season=2023,
            check_date=date(2023, 6, 25),
            comments='No cow check',
            is_pregnant=True,
            recheck=False
        )

    def test_get_regular_page_display(self):
        """Test GET request displays the regular page when no export parameter"""
        request = self.factory.get('/database-management/')
        
        with patch.object(self.view, 'initialze_database_if_needed') as mock_init, \
             patch.object(self.view, 'get_context_data') as mock_context, \
             patch('ranch_tools.database_management.views.render') as mock_render:
            
            mock_context.return_value = {'test': 'data'}
            mock_render.return_value = HttpResponse('test')
            
            response = self.view.get(request)
            
            mock_init.assert_called_once()
            mock_context.assert_called_once()
            mock_render.assert_called_once_with(
                request, 
                self.view.template_name, 
                {'test': 'data'}
            )

    def test_get_export_request(self):
        """Test GET request with export parameter calls handle_export_request"""
        request = self.factory.get('/database-management/?export=true')
        
        with patch.object(self.view, 'initialze_database_if_needed') as mock_init, \
             patch.object(self.view, 'handle_export_request') as mock_export:
            
            mock_export.return_value = HttpResponse('export')
            
            response = self.view.get(request)
            
            mock_init.assert_called_once()
            mock_export.assert_called_once_with(request)

    def test_handle_export_request_include_empty_false(self):
        """Test handle_export_request with include_empty=false"""
        request = self.factory.get('/database-management/?export=true&include_empty=false')
        
        with patch.object(self.view, 'export_all_to_excel') as mock_export:
            mock_export.return_value = HttpResponse('export')
            
            response = self.view.handle_export_request(request)
            
            mock_export.assert_called_once_with(request)

    def test_handle_export_request_include_empty_true(self):
        """Test handle_export_request with include_empty=true"""
        request = self.factory.get('/database-management/?export=true&include_empty=true')
        
        with patch.object(self.view, 'export_all_to_excel') as mock_export:
            mock_export.return_value = HttpResponse('export')
            
            response = self.view.handle_export_request(request)
            
            mock_export.assert_called_once_with(request)

    def test_handle_export_request_include_empty_default(self):
        """Test handle_export_request without include_empty parameter defaults to false"""
        request = self.factory.get('/database-management/?export=true')
        
        with patch.object(self.view, 'export_all_to_excel') as mock_export:
            mock_export.return_value = HttpResponse('export')
            
            response = self.view.handle_export_request(request)
            
            mock_export.assert_called_once_with(request)

    @patch('ranch_tools.database_management.views.messages')
    @patch('ranch_tools.database_management.views.redirect')
    def test_handle_export_request_exception_handling(self, mock_redirect, mock_messages):
        """Test handle_export_request handles exceptions properly"""
        request = self.factory.get('/database-management/?export=true')
        mock_redirect.return_value = HttpResponse('redirect')
        
        with patch.object(self.view, 'export_all_to_excel') as mock_export:
            mock_export.side_effect = Exception('Test error')
            
            response = self.view.handle_export_request(request)
            
            mock_messages.error.assert_called_once_with(request, 'Export failed: Test error')
            mock_redirect.assert_called_once_with('database_management')

    def test_export_all_to_excel_response_headers(self):
        """Test export_all_to_excel sets correct response headers"""
        request = self.factory.get('/database-management/?export=true')
        
        response = self.view.export_all_to_excel(request)
        
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(
            response['Content-Type'], 
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertEqual(
            response['Content-Disposition'], 
            'attachment; filename="ranch_data_export.xlsx"'
        )

    def test_export_all_to_excel_data_content(self):
        """Test export_all_to_excel includes correct data"""
        request = self.factory.get('/database-management/?export=true')
        
        response = self.view.export_all_to_excel(request)
        
        # Read the Excel content
        excel_content = BytesIO(response.content)
        df = pd.read_excel(excel_content, sheet_name='Pregnancy_Checks')
        
        # Should have 3 pregnancy checks (including the one without cow)
        self.assertEqual(len(df), 3)
        
        # Check data structure
        expected_columns = [
            'ear_tag_id', 'birth_year', 'eid', 'breeding_season',
            'check_date', 'comments', 'is_pregnant', 'recheck'
        ]
        for col in expected_columns:
            self.assertIn(col, df.columns)
        
        # Check specific data
        cow1_row = df[df['ear_tag_id'] == 'T001'].iloc[0]
        self.assertEqual(cow1_row['birth_year'], 2020)
        self.assertEqual(cow1_row['eid'], 'EID001')
        self.assertEqual(cow1_row['breeding_season'], 2023)
        self.assertTrue(cow1_row['is_pregnant'])
        self.assertFalse(cow1_row['recheck'])

    def test_export_all_to_excel_handles_none_cow(self):
        """Test export handles pregnancy checks with no associated cow"""
        request = self.factory.get('/database-management/?export=true')
        
        response = self.view.export_all_to_excel(request)
        
        # Read the Excel content
        excel_content = BytesIO(response.content)
        df = pd.read_excel(excel_content, sheet_name='Pregnancy_Checks')
        df = df.fillna('')  # Replace NaN with empty string for easier checks
        
        # Find the row with no cow (should have empty strings for cow fields)
        no_cow_rows = df[df['ear_tag_id'] == '']
        self.assertEqual(len(no_cow_rows), 1)  # Should find the pregcheck_no_cow
        
        no_cow_row = no_cow_rows.iloc[0]
        self.assertEqual(no_cow_row['ear_tag_id'], '')
        self.assertEqual(no_cow_row['birth_year'], '')  # Should be empty string, not NaN
        self.assertEqual(no_cow_row['eid'], '')
        self.assertEqual(no_cow_row['comments'], 'No cow check')

    def test_export_all_to_excel_with_empty_database(self):
        """Test export works with empty database"""
        # Clear all data
        PregCheck.objects.all().delete()
        Cow.objects.all().delete()
        
        request = self.factory.get('/database-management/?export=true')
        
        response = self.view.export_all_to_excel(request)
        
        # Should still return a valid response
        self.assertIsInstance(response, HttpResponse)
        
        # Read the Excel content
        excel_content = BytesIO(response.content)
        df = pd.read_excel(excel_content, sheet_name='Pregnancy_Checks')
        
        # Should be empty DataFrame
        self.assertEqual(len(df), 0)

    def test_query_optimization(self):
        """Test that the export uses select_related for query optimization"""
        request = self.factory.get('/database-management/?export=true')
        
        with patch('ranch_tools.preg_check.models.PregCheck.objects') as mock_manager:
            mock_queryset = MagicMock()
            mock_manager.select_related.return_value = mock_queryset
            mock_queryset.all.return_value = []
            
            self.view.export_all_to_excel(request)
            
            # Verify select_related was called with 'cow'
            mock_manager.select_related.assert_called_once_with('cow')
            mock_queryset.all.assert_called_once()

    def test_date_formatting_in_export(self):
        """Test that dates are properly formatted in export"""
        request = self.factory.get('/database-management/?export=true')
        
        response = self.view.export_all_to_excel(request)
        
        # Read the Excel content
        excel_content = BytesIO(response.content)
        df = pd.read_excel(excel_content, sheet_name='Pregnancy_Checks')
        
        # Check that dates are present and properly formatted
        cow1_row = df[df['ear_tag_id'] == 'T001'].iloc[0]
        check_date = cow1_row['check_date']
        
        # Should be a valid date (pandas will parse it as datetime)
        self.assertIsNotNone(check_date)

    @patch('ranch_tools.database_management.views.pd.ExcelWriter')
    def test_excel_writer_exception_handling(self, mock_excel_writer):
        """Test that Excel writer exceptions are handled properly"""
        request = self.factory.get('/database-management/?export=true')
        
        # Mock ExcelWriter to raise an exception
        mock_excel_writer.side_effect = Exception('Excel write error')
        
        with self.assertRaises(Exception):
            self.view.export_all_to_excel(request)


class DatabaseManagementViewTestCase(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.view = DatabaseManagementView()
        
        # Create a temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a test SQLite database
        self.test_db_path = os.path.join(self.temp_dir, 'test.sqlite3')
        self.create_test_database(self.test_db_path)
        
    def tearDown(self):
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_database(self, db_path):
        """Create a test SQLite database with some tables"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        ''')
        cursor.execute("INSERT INTO test_table (name) VALUES ('test_data')")
        conn.commit()
        conn.close()

    @patch.object(DatabaseManagementView, 'handle_excel_upload')
    @patch.object(DatabaseManagementView, 'handle_database_upload')
    @patch.object(DatabaseManagementView, 'create_database_backup')
    def test_post_calls_expected_methods(self, mock_backup, mock_db_upload, mock_excel_upload):
        """Test that post calls the correct handler based on POST type"""
        # update_db (valid)
        file_content = b"excel content"
        uploaded_file = SimpleUploadedFile("update.xlsx", file_content)
        request = self.factory.post('/database-management/')
        request.FILES['update_db'] = uploaded_file
        self.add_session_and_messages_middleware(request)
        response = self.view.post(request)
        mock_excel_upload.assert_called_once_with(request)
        mock_db_upload.assert_not_called()
        mock_backup.assert_not_called()

        # upload_db (valid)
        mock_excel_upload.reset_mock()
        uploaded_file = SimpleUploadedFile("upload.sqlite3", b"sqlite content")
        request = self.factory.post('/database-management/')
        request.FILES['upload_db'] = uploaded_file
        self.add_session_and_messages_middleware(request)
        response = self.view.post(request)
        mock_db_upload.assert_called_once_with(request)
        mock_excel_upload.assert_not_called()
        mock_backup.assert_not_called()

        # create_backup
        mock_db_upload.reset_mock()
        request = self.factory.post('/database-management/', {'create_backup': '1'})
        self.add_session_and_messages_middleware(request)
        response = self.view.post(request)
        mock_backup.assert_called_once_with(request)
        mock_db_upload.assert_not_called()
        mock_excel_upload.assert_not_called()

        # update_db (invalid file type)
        mock_backup.reset_mock()
        uploaded_file = SimpleUploadedFile("update.txt", b"not excel")
        request = self.factory.post('/database-management/')
        request.FILES['update_db'] = uploaded_file
        self.add_session_and_messages_middleware(request)
        response = self.view.post(request)
        self.assertEqual(response.status_code, 302)
        messages_list = list(get_messages(request))
        self.assertTrue(any('Invalid file type' in str(m) for m in messages_list))
        mock_excel_upload.assert_not_called()

        # upload_db (invalid file type)
        uploaded_file = SimpleUploadedFile("upload.txt", b"not sqlite")
        request = self.factory.post('/database-management/')
        request.FILES['upload_db'] = uploaded_file
        self.add_session_and_messages_middleware(request)
        response = self.view.post(request)
        self.assertEqual(response.status_code, 302)
        messages_list = list(get_messages(request))
        self.assertTrue(any('Invalid file type' in str(m) for m in messages_list))
        mock_db_upload.assert_not_called()

    @patch('ranch_tools.preg_check.models.Cow.objects.get_or_create')
    @patch('ranch_tools.preg_check.models.PregCheck.objects.create')
    def test_handle_excel_upload(self, mock_pregcheck_create, mock_cow_get_or_create):
        """Test handle_excel_upload with valid Excel/CSV data"""

        mockCow = MagicMock()
        mock_cow_get_or_create.return_value = (mockCow, None,)

        # Create a DataFrame with valid data
        df = pd.DataFrame({
            'ear_tag_id': ['A123'],
            'birth_year': [2020],
            'eid': ['EID001'],
            'breeding_season': [2025],
            'check_date': ['2025-09-07'],
            'comments': ['Healthy'],
            'is_pregnant': ['P'],
            'recheck': [False]
        })
        # Save as CSV to temp file
        temp_file = os.path.join(self.temp_dir, 'test_import.csv')
        df.to_csv(temp_file, index=False)
        with open(temp_file, 'rb') as f:
            uploaded_file = SimpleUploadedFile('test_import.csv', f.read())

        request = self.factory.post('/database-management/')
        self.add_session_and_messages_middleware(request)

        request.FILES['update_db'] = uploaded_file        
        # Patch pandas.read_csv to return our DataFrame
        with patch('pandas.read_csv', return_value=df):
            response = self.view.handle_excel_upload(request)

        self.assertEqual(response.status_code, 302)  # Should redirect
        mock_cow_get_or_create.assert_called_once()
        mock_pregcheck_create.assert_called_once()
    
    def add_session_and_messages_middleware(self, request):
        """Add session and messages middleware to request"""
        # Add session
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        
        # Add messages
        messages_middleware = MessageMiddleware(lambda req: None)
        messages_middleware.process_request(request)
    
    def test_get_request_returns_context(self):
        """Test GET request returns proper context"""
        request = self.factory.get('/database-management/')
        self.add_session_and_messages_middleware(request)
        
        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            response = self.view.get(request)
            
        self.assertEqual(response.status_code, 200)
        # Check that context contains expected keys
        # Note: In a real test, you'd need to inspect the rendered context
    
    def test_get_context_data(self):
        """Test get_context_data returns correct information"""
        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            context = self.view.get_context_data()
            
        self.assertIn('current_db', context)
        self.assertIn('db_info', context)
        self.assertEqual(context['current_db'], 'test.sqlite3')
        self.assertEqual(context['db_info']['table_count'], 1)
    
    def test_get_database_info_valid_db(self):
        """Test get_database_info with valid database"""
        db_info = self.view.get_database_info(self.test_db_path)
        
        self.assertEqual(db_info['table_count'], 1)
        self.assertIn('test_table', db_info['sample_tables'])
        self.assertGreater(db_info['size_mb'], 0)
        self.assertIn('last_modified', db_info)
    
    def test_get_database_info_invalid_db(self):
        """Test get_database_info with invalid database path"""
        db_info = self.view.get_database_info('/nonexistent/path.sqlite3')
        
        self.assertIn('error', db_info)
    
    def test_save_temporary_file_success(self):
        """Test successful temporary file saving"""
        file_content = b"test file content"
        uploaded_file = SimpleUploadedFile("test.sqlite3", file_content)
        
        temp_path = self.view.save_temporary_file(uploaded_file)
        
        self.assertIsNotNone(temp_path)
        self.assertTrue(os.path.exists(temp_path))
        
        with open(temp_path, 'rb') as f:
            self.assertEqual(f.read(), file_content)
        
        # Clean up
        os.remove(temp_path)
    
    def test_validate_sqlite_file_valid(self):
        """Test validation of valid SQLite file"""
        result = self.view.validate_sqlite_file(self.test_db_path)
        
        self.assertTrue(result['is_valid'])
        self.assertNotIn('error_message', result)
    
    def test_validate_sqlite_file_empty_db(self):
        """Test validation of empty SQLite database"""
        empty_db_path = os.path.join(self.temp_dir, 'empty.sqlite3')
        conn = sqlite3.connect(empty_db_path)
        conn.close()
        
        result = self.view.validate_sqlite_file(empty_db_path)
        
        self.assertFalse(result['is_valid'])
        self.assertIn('empty database', result['error_message'])
    
    def test_validate_sqlite_file_invalid(self):
        """Test validation of invalid file"""
        invalid_file_path = os.path.join(self.temp_dir, 'invalid.txt')
        with open(invalid_file_path, 'w') as f:
            f.write("This is not a SQLite file")
        
        result = self.view.validate_sqlite_file(invalid_file_path)
        
        self.assertFalse(result['is_valid'])
        self.assertIn('Invalid database file', result['error_message'])
    
    def test_create_backup_path(self):
        """Test backup path creation"""
        backup_path = self.view.create_backup_path(self.test_db_path)
        
        self.assertTrue(backup_path.endswith('.sqlite3'))
        self.assertIn('backup_', backup_path)
        # Should contain timestamp pattern
        import re
        timestamp_pattern = r'\d{8}_\d{6}'
        self.assertTrue(re.search(timestamp_pattern, backup_path))
    
    def test_cleanup_temp_file(self):
        """Test temporary file cleanup"""
        # Create a temporary file
        temp_file = os.path.join(self.temp_dir, 'temp_test.txt')
        with open(temp_file, 'w') as f:
            f.write("temp content")
        
        self.assertTrue(os.path.exists(temp_file))
        
        self.view.cleanup_temp_file(temp_file)
        
        self.assertFalse(os.path.exists(temp_file))
    
    def test_cleanup_temp_file_nonexistent(self):
        """Test cleanup of nonexistent file doesn't raise error"""
        # Should not raise an exception
        self.view.cleanup_temp_file('/nonexistent/file.txt')
    
    @patch('shutil.copy2')
    @patch('shutil.move')
    @patch('django.db.connection.close')
    @patch('ranch_tools.database_management.views.call_command')
    def test_replace_current_database_success(self, mock_migrate, mock_close, 
                                            mock_move, mock_copy):
        """Test successful database replacement"""
        temp_path = os.path.join(self.temp_dir, 'new_db.sqlite3')
        self.create_test_database(temp_path)
        
        request = self.factory.post('/database-management/')
        self.add_session_and_messages_middleware(request)
        self.view.request = request

        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            result = self.view.replace_current_database(temp_path)
        
        self.assertTrue(result)
        mock_copy.assert_called_once()  # Backup creation
        mock_move.assert_called_once()  # Database replacement
        mock_close.assert_called_once()  # Connection close
        mock_migrate.assert_called_once()  # Migration
    
    @patch('shutil.copy2', side_effect=Exception("Copy failed"))
    def test_replace_current_database_failure(self, mock_copy):
        """Test database replacement failure"""
        temp_path = os.path.join(self.temp_dir, 'new_db.sqlite3')
        self.create_test_database(temp_path)
        
        request = self.factory.post('/database-management/')
        self.add_session_and_messages_middleware(request)
        self.view.request = request
        
        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            result = self.view.replace_current_database(temp_path)
        
        self.assertFalse(result)
    
    def test_post_upload_invalid_extension(self):
        """Test POST with invalid file extension"""

        file_content = b"fake content"
        uploaded_file = SimpleUploadedFile("test.txt", file_content)
        
        request = self.factory.post('/database-management/', {
            'upload_db': uploaded_file
        })
        self.add_session_and_messages_middleware(request)
        
        response = self.view.post(request)
        
        self.assertEqual(response.status_code, 302)  # Redirect
        messages = list(get_messages(request))
        self.assertTrue(any('Invalid file type. Please upload a .sqlite3 file.' in str(m) for m in messages))
    
    def test_post_upload_valid_file(self):
        """Test POST with valid SQLite file"""
        # Create a valid SQLite file content
        temp_upload_db = os.path.join(self.temp_dir, 'upload.sqlite3')
        self.create_test_database(temp_upload_db)
        
        with open(temp_upload_db, 'rb') as f:
            file_content = f.read()
        
        uploaded_file = SimpleUploadedFile("upload.sqlite3", file_content)
        
        request = self.factory.post('/database-management/')
        request.FILES['upload_db'] = uploaded_file
        self.add_session_and_messages_middleware(request)
        
        with patch.object(self.view, 'replace_current_database', return_value=True):
            response = self.view.post(request)
        
        self.assertEqual(response.status_code, 302)  # Redirect
    
    def test_post_create_backup(self):
        """Test POST request to create backup"""
        request = self.factory.post('/database-management/', {
            'create_backup': 'true'
        })
        self.add_session_and_messages_middleware(request)
        
        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            with patch('shutil.copy2') as mock_copy:
                response = self.view.post(request)
        
        self.assertEqual(response.status_code, 302)  # Redirect
        mock_copy.assert_called_once()
    
    def test_post_create_backup_ajax(self):
        """Test AJAX POST request to create backup"""
        request = self.factory.post('/database-management/', {
            'create_backup': 'true'
        }, HTTP_CONTENT_TYPE='application/json')
        self.add_session_and_messages_middleware(request)
        
        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            with patch('shutil.copy2') as mock_copy:
                response = self.view.create_database_backup(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        mock_copy.assert_called_once()
    
    @patch('shutil.copy2', side_effect=Exception("Backup failed"))
    def test_post_create_backup_failure(self, mock_copy):
        """Test backup creation failure"""
        request = self.factory.post('/database-management/', {
            'create_backup': 'true'
        })
        self.add_session_and_messages_middleware(request)
        
        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            response = self.view.post(request)
        
        self.assertEqual(response.status_code, 302)  # Redirect
        messages = list(get_messages(request))
        self.assertTrue(any('Backup failed' in str(m) for m in messages))
    
    def test_post_no_action(self):
        """Test POST with no valid action"""
        request = self.factory.post('/database-management/', {})
        self.add_session_and_messages_middleware(request)
        
        response = self.view.post(request)
        
        self.assertEqual(response.status_code, 302)  # Redirect back to page


class DatabaseManagementIntegrationTestCase(TestCase):
    """Integration tests using Django's test client"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, 'test.sqlite3')
        self.create_test_database(self.test_db_path)
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_database(self, db_path):
        """Create a test SQLite database"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        ''')
        cursor.execute("INSERT INTO test_table (name) VALUES ('test_data')")
        conn.commit()
        conn.close()
    
    @override_settings(DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}})
    def test_get_page_loads(self):
        """Test that the page loads successfully"""
        with patch.object(settings, 'DATABASES', {'default': {'NAME': self.test_db_path}}):
            response = self.client.get('/database-management/')
        
        self.assertEqual(response.status_code, 200)
    
    def test_upload_invalid_file_type(self):
        """Test uploading non-SQLite file"""
        with open(os.path.join(self.temp_dir, 'test.txt'), 'w') as f:
            f.write("Not a database")
        
        with open(os.path.join(self.temp_dir, 'test.txt'), 'rb') as f:
            response = self.client.post('/database-management/', {
                'upload_db': f
            })
        
        self.assertRedirects(response, '/database-management/')


class DatabaseExportIntegrationTestCase(TestCase):
    """Integration tests for the complete export workflow"""
    
    def setUp(self):
        """Set up test data for integration tests"""
        self.cow = Cow.objects.create(
            ear_tag_id='INT001',
            birth_year=2022,
            eid='INTEID001'
        )
        
        self.pregcheck = PregCheck.objects.create(
            cow=self.cow,
            breeding_season=2024,
            check_date=date(2024, 7, 1),
            comments='Integration test',
            is_pregnant=True,
            recheck=False
        )

    def test_full_export_workflow_via_get_request(self):
        """Test the complete export workflow from GET request to Excel response"""
        # Create a view instance with mocked initialization
        view = DatabaseManagementView()
        
        with patch.object(view, 'initialze_database_if_needed'):
            request = RequestFactory().get('/database-management/?export=true&include_empty=false')
            
            response = view.get(request)
            
            # Should get an Excel response
            self.assertIsInstance(response, HttpResponse)
            self.assertEqual(
                response['Content-Type'],
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
            # Verify Excel content is readable
            excel_content = BytesIO(response.content)
            df = pd.read_excel(excel_content, sheet_name='Pregnancy_Checks')
            
            # Should contain our test data
            self.assertEqual(len(df), 1)
            self.assertEqual(df.iloc[0]['ear_tag_id'], 'INT001')
            self.assertEqual(df.iloc[0]['breeding_season'], 2024)