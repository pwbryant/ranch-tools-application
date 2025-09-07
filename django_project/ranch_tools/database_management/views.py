import os
import shutil
import sqlite3
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.db import connection
from django.core.management import call_command


class DatabaseManagementView(View):
    template_name = 'database_management/database_management.html'
    
    def get(self, request):
        """Display the database management page"""
        context = self.get_context_data()
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Handle POST requests for database operations"""
        if 'upload_db' in request.FILES:
            return self.handle_database_upload(request)
        elif 'create_backup' in request.POST:
            return self.create_database_backup(request)
        
        # If no valid action, redirect back to the page
        return redirect('database_management')
    
    def get_context_data(self):
        """Get context data for the template"""
        current_db = settings.DATABASES['default']['NAME']
        current_db_name = os.path.basename(current_db)
        db_info = self.get_database_info(current_db)
        
        return {
            'current_db': current_db_name,
            'db_info': db_info,
        }
    
    def handle_database_upload(self, request):
        """Handle database file upload"""
        uploaded_file = request.FILES['upload_db']
        
        # Validate file extension
        if not uploaded_file.name.endswith('.sqlite3'):
            messages.error(request, 'Please upload a valid SQLite database file (.sqlite3)')
            return redirect('database_management')
        
        # Validate file content
        temp_path = self.save_temporary_file(uploaded_file)
        if not temp_path:
            return redirect('database_management')
        
        validation_result = self.validate_sqlite_file(temp_path)
        if not validation_result['is_valid']:
            messages.error(request, validation_result['error_message'])
            self.cleanup_temp_file(temp_path)
            return redirect('database_management')
        
        # Replace current database
        success = self.replace_current_database(temp_path)
        if success:
            messages.success(request, 'Database successfully uploaded and activated.')
        
        return redirect('database_management')
    
    def save_temporary_file(self, uploaded_file):
        """Save uploaded file to temporary location"""
        try:
            # Use a safer temporary directory
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            
            with open(temp_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            return temp_path
        except Exception as e:
            messages.error(self.request if hasattr(self, 'request') else None, 
                          f'Failed to save uploaded file: {str(e)}')
            return None
    
    def validate_sqlite_file(self, file_path):
        """Validate that the file is a proper SQLite database"""
        try:
            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            conn.close()
            
            if not tables:
                return {
                    'is_valid': False,
                    'error_message': 'Uploaded file appears to be an empty database'
                }
            
            return {'is_valid': True}
            
        except Exception as e:
            return {
                'is_valid': False,
                'error_message': f'Invalid database file: {str(e)}'
            }
    
    def replace_current_database(self, temp_path):
        """Replace the current database with the uploaded one"""
        current_db_path = settings.DATABASES['default']['NAME']
        backup_path = self.create_backup_path(current_db_path)
        try:
            # Create backup
            shutil.copy2(current_db_path, backup_path)
            
            # Close current database connections
            connection.close()
            
            # Replace current database
            shutil.move(temp_path, current_db_path)
            
            # Run migrations to ensure schema compatibility
            call_command('migrate', verbosity=0)
            
            messages.success(
                getattr(self, 'request', None),
                f'Backup saved as {os.path.basename(backup_path)}'
            )
            return True
            
        except Exception as e:
            messages.error(
                getattr(self, 'request', None),
                f'Error replacing database: {str(e)}'
            )
            # Restore backup if something went wrong
            if os.path.exists(backup_path):
                try:
                    shutil.copy2(backup_path, current_db_path)
                except Exception as restore_error:
                    messages.error(
                        getattr(self, 'request', None),
                        f'Failed to restore backup: {str(restore_error)}'
                    )
            return False
    
    def create_database_backup(self, request):
        """Create a backup of current database"""
        current_db_path = settings.DATABASES['default']['NAME']
        backup_path = self.create_backup_path(current_db_path, prefix='db_backup_')
        try:
            shutil.copy2(current_db_path, backup_path)
            backup_name = os.path.basename(backup_path)
            
            # Handle AJAX requests
            if request.headers.get('content-type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'backup_path': backup_path,
                    'backup_name': backup_name
                })
            
            messages.success(request, f'Backup created successfully: {backup_name}')
            
        except Exception as e:
            if request.headers.get('content-type') == 'application/json':
                return JsonResponse({'success': False, 'error': str(e)})
            
            messages.error(request, f'Backup failed: {str(e)}')
        return redirect('database_management')
    
    def create_backup_path(self, db_path, prefix='backup_'):
        """Generate a backup file path with timestamp"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if hasattr(settings, 'BACKUP_DIR'):
            backup_dir = settings.BACKUP_DIR
        else:
            backup_dir = os.path.dirname(db_path)
        
        backup_name = f"{prefix}{timestamp}.sqlite3"
        return os.path.join(backup_dir, backup_name)
    
    def cleanup_temp_file(self, file_path):
        """Safely remove temporary file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass  # Ignore cleanup errors
    
    def get_database_info(self, db_path):
        """Get information about the current database"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get table count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
            table_count = cursor.fetchone()[0]
            
            # Get database size
            db_size = os.path.getsize(db_path)
            db_size_mb = round(db_size / (1024 * 1024), 2)
            
            # Get some sample table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 5;")
            tables = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
            return {
                'table_count': table_count,
                'size_mb': db_size_mb,
                'sample_tables': tables,
                'last_modified': os.path.getmtime(db_path)
            }
            
        except Exception as e:
            return {'error': str(e)}




# Alternative: Using Django's generic FormView for more structure
from django.views.generic import FormView
from django import forms

class DatabaseUploadForm(forms.Form):
    upload_db = forms.FileField(
        widget=forms.FileInput(attrs={'accept': '.sqlite3'}),
        help_text='Select a SQLite database file (.sqlite3)'
    )

class DatabaseManagementFormView(FormView):
    template_name = 'database_management.html'
    form_class = DatabaseUploadForm
    success_url = '/database-management/'  # Update with your URL name
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_db = settings.DATABASES['default']['NAME']
        context.update({
            'current_db': os.path.basename(current_db),
            'db_info': self.get_database_info(current_db),
        })
        return context
    
    def form_valid(self, form):
        # Handle file upload logic here
        # Similar to handle_database_upload method above
        return super().form_valid(form)
    
    def get_database_info(self, db_path):
        # Same as above method
        pass
