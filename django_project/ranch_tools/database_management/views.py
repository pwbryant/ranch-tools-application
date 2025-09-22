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

from ranch_tools.utils.mixins import InitialzeDatabaseMixin


class DatabaseManagementView(View, InitialzeDatabaseMixin):
    template_name = 'database_management/database_management.html'
    
    def get(self, request):
        """Display the database management page"""
        self.initialze_database_if_needed()
        context = self.get_context_data()
        return render(request, self.template_name, context)

    def post(self, request):
        """Handle POST requests for database operations"""

        if 'update_db' in request.FILES:
            uploaded_file = request.FILES['update_db']
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext not in ['.xlsx', '.xls', '.csv']:
                messages.error(request, 'Invalid file type. Please upload a .xlsx, .xls, or .csv file.')
                return redirect('database_management')
            return self.handle_excel_upload(request)
        elif 'upload_db' in request.FILES:
            uploaded_file = request.FILES['upload_db']
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            if ext != '.sqlite3':
                messages.error(request, 'Invalid file type. Please upload a .sqlite3 file.')
                return redirect('database_management')
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

    def handle_excel_upload(self, request):
        """Handle Excel/CSV file upload for Cow and PregCheck records"""
        uploaded_file = request.FILES['update_db']
        temp_path = self.save_temporary_file(uploaded_file)
        if not temp_path:
            return redirect('database_management')

        df = self.read_excel_or_csv(temp_path, uploaded_file.name, request)
        if df is None:
            self.cleanup_temp_file(temp_path)
            return redirect('database_management')

        missing = self.validate_excel_columns(df)
        if missing:
            messages.error(request, f'Missing columns: {", ".join(missing)}')
            self.cleanup_temp_file(temp_path)
            return redirect('database_management')

        errors = self.import_cow_pregcheck_records(df)
        if errors:
            messages.error(request, 'Some rows failed to import: ' + '; '.join(errors))
        else:
            messages.success(request, 'Excel/CSV data imported successfully.')

        self.cleanup_temp_file(temp_path)
        return redirect('database_management')

    def read_excel_or_csv(self, temp_path, filename, request):
        """Read Excel or CSV file into DataFrame"""
        import pandas as pd
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(temp_path)
            else:
                df = pd.read_excel(temp_path)
            return df
        except Exception as e:
            messages.error(request, f'Error reading file: {str(e)}')
            return None

    def validate_excel_columns(self, df):
        """Check for required columns in DataFrame"""
        required_columns = [
            'ear_tag_id', 'birth_year', 'eid', 'breeding_season',
            'check_date', 'comments', 'is_pregnant', 'recheck'
        ]
        missing = [col for col in required_columns if col not in df.columns]
        return missing

    def import_cow_pregcheck_records(self, df):
        """Validate and create Cow and PregCheck records from DataFrame"""
        from ranch_tools.preg_check.models import Cow, PregCheck
        import pandas as pd
        errors = []
        for idx, row in df.iterrows():
            try:
                ear_tag_id = str(row['ear_tag_id']).strip()
                birth_year = int(row['birth_year'])
                eid = str(row['eid']).strip() if pd.notnull(row['eid']) else None

                no_cow_id = not ear_tag_id and not eid
                if not no_cow_id and not birth_year:
                    errors.append(f'Row {idx+1}: birth_year is required when ear_tag_id or eid is provided')
                    continue
                
                breeding_season = int(row['breeding_season'])
                check_date = pd.to_datetime(row['check_date']).date()
                comments = str(row['comments']).strip() if pd.notnull(row['comments']) else ''
                is_pregnant = bool(row['is_pregnant'])
                recheck = bool(row['recheck']) if pd.notnull(row['recheck']) else False

                if no_cow_id:
                    cow = None
                else:
                    cow_id_params = {
                        'ear_tag_id': ear_tag_id,
                        'birth_year': birth_year,
                        'eid': eid
                    }
                    for id_field in ('ear_tag_id', 'eid'):
                        if not cow_id_params[id_field]:
                            del cow_id_params[id_field] 
                    cow, _ = Cow.objects.get_or_create(**cow_id_params)

                PregCheck.objects.create(
                    breeding_season=breeding_season,
                    check_date=check_date,
                    comments=comments,
                    cow=cow,
                    is_pregnant=is_pregnant,
                    recheck=recheck
                )
            except Exception as e:
                errors.append(f'Row {idx+1}: {str(e)}')
        return errors

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
        
        # Check if a custom backup path was provided from the form
        custom_backup_path = request.POST.get('backup_path', '').strip()
        
        if custom_backup_path:
            # Use the custom path provided by Electron file dialog
            backup_path = custom_backup_path
            
            # Ensure the directory exists
            backup_dir = os.path.dirname(backup_path)
            if not os.path.exists(backup_dir):
                try:
                    os.makedirs(backup_dir)
                except OSError as e:
                    if request.headers.get('content-type') == 'application/json':
                        return JsonResponse({'success': False, 'error': f'Could not create directory: {str(e)}'})
                    messages.error(request, f'Could not create directory: {str(e)}')
                    return redirect('database_management')
        else:
            # Use default backup path (your existing logic)
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
            
            if custom_backup_path:
                messages.success(request, f'Backup created successfully at: {backup_path}')
            else:
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
