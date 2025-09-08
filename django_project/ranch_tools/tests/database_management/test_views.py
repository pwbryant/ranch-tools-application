import os
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

from django.contrib.messages import get_messages
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import TestCase, RequestFactory, override_settings

from ranch_tools.database_management.views import DatabaseManagementView


class DatabaseManagementViewTestCase(TestCase):
    @patch('ranch_tools.preg_check.models.Cow.objects.get_or_create')
    @patch('ranch_tools.preg_check.models.PregCheck.objects.create')
    def test_handle_excel_upload(self, mock_pregcheck_create, mock_cow_get_or_create):
        """Test handle_excel_upload with valid Excel/CSV data"""

        mockCow = MagicMock()
        mock_cow_get_or_create.return_value = (mockCow, None,)

        import pandas as pd
        # Create a DataFrame with valid data
        df = pd.DataFrame({
            'ear_tag_id': ['A123'],
            'birth_year': [2020],
            'eid': ['EID001'],
            'breeding_season': [2025],
            'check_date': ['2025-09-07'],
            'comments': ['Healthy'],
            'is_pregnant': [True],
            'recheck': [False]
        })
        # Save as CSV to temp file
        temp_file = os.path.join(self.temp_dir, 'test_import.csv')
        df.to_csv(temp_file, index=False)
        with open(temp_file, 'rb') as f:
            uploaded_file = SimpleUploadedFile('test_import.csv', f.read())

        request = self.factory.post('/database-management/')
        self.add_session_and_messages_middleware(request)

        # Patch pandas.read_csv to return our DataFrame
        with patch('pandas.read_csv', return_value=df):
            response = self.view.handle_excel_upload(request, uploaded_file)

        self.assertEqual(response.status_code, 302)  # Should redirect
        mock_cow_get_or_create.assert_called_once()
        mock_pregcheck_create.assert_called_once()
        messages_list = list(get_messages(request))
        self.assertTrue(any('imported successfully' in str(m) for m in messages_list))
    
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
        self.assertTrue(any('Invalid file type. Please upload a .sqlite3, .xlsx, .xls, or .csv file.' in str(m) for m in messages))
    
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
