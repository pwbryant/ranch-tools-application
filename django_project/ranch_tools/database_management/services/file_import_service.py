"""
Service for importing cow and pregnancy check data from Excel files.

Place this file in: your_app/services/pregcheck_import_service.py

Example usage in a view:
    from your_app.services.pregcheck_import_service import PregCheckImportService
    
    def upload_pregcheck_data(request):
        if request.method == 'POST' and request.FILES.get('excel_file'):
            excel_file = request.FILES['excel_file']
            service = PregCheckImportService()
            
            try:
                result = service.import_from_file(excel_file)
                messages.success(request, f"Successfully imported {result['pregchecks_created']} records")
                return redirect('success_page')
            except ValidationError as e:
                messages.error(request, str(e))
            except ImportError as e:
                messages.error(request, f"Import failed: {str(e)}")
        
        return render(request, 'upload_form.html')
"""
from io import BytesIO
import logging
from typing import Dict, Any, BinaryIO

from django.db import transaction
from django.core.exceptions import ValidationError
import pandas as pd

from ranch_tools.preg_check.models import Cow, PregCheck  # Replace 'your_app' with your actual app name

logger = logging.getLogger(__name__)

class ImportError(Exception):
    """Custom exception for import errors."""
    pass


class PregCheckImportService:
    """Service class for importing pregnancy check data from Excel files."""
    
    def __init__(self):
        """Initialize the service with empty statistics."""
        self.reset_stats()

    def reset_stats(self):
        """Reset import statistics."""
        self.stats = {
            'cows_created': 0,
            'pregchecks_created': 0,
            'errors': []
        }

    def import_from_file(self, file: BinaryIO, dry_run: bool = False) -> Dict[str, Any]:
        """
        Import pregnancy check data from an Excel file.
        
        Args:
            file: File object (e.g., from request.FILES)
            dry_run: If True, validate but don't save to database
            
        Returns:
            Dictionary with import statistics
            
        Raises:
            ValidationError: If the file format is invalid
            ImportError: If the import fails
        """
        self.reset_stats()
        logger.info('import from file')
        try:
            # Read Excel file with ear_tag_id and eid as strings to preserve leading zeros
            if '.csv' in getattr(file, 'name', '').lower():
                df = pd.read_csv(file, dtype={'ear_tag_id': str, 'eid': str})
            elif '.xlsx' in getattr(file, 'name', '').lower() or '.xls' in getattr(file, 'name', '').lower() or isinstance(file, BytesIO):
                df = pd.read_excel(file, dtype={'ear_tag_id': str, 'eid': str})
            else:
                raise ValidationError('Unsupported file format. Please upload an Excel or CSV file.')        


            from .file_import_dataframe_processors import CowDataFrameProcessor, PregcheckDataFrameProcessor

            # if import_type == 'pregchecks':
            dataframe_processor = PregcheckDataFrameProcessor()
            # elif import_type == 'cows':
            #     dataframe_processor = CowDataFrameProcessor()
            # else:
            #     raise Exception('Invalid import type. Supported types are "pregchecks" or "cows"')

            # Remove blank rows
            # df = self.remove_blank_rows(df)
            df = dataframe_processor.remove_blank_rows(df)

            # Standardize data
            # df = self.standardize_dataframe(df)
            df = dataframe_processor.standardize_dataframe(df)

            # Validate structure
            # self.validate_dataframe(df)
            dataframe_processor.validate_dataframe(df)
            
            # Process data within a transaction
            with transaction.atomic():
                # self.process_dataframe(df)
                dataframe_processor.process_dataframe(df)
                
                # Check for errors
                stats = dataframe_processor.stats.copy()
                if stats['errors']:
                    transaction.set_rollback(True)
                    error_summary = '\n'.join(stats['errors'][:5])  # Show first 5 errors
                    if len(stats['errors']) > 5:
                        error_summary += f"\n... and {len(stats['errors']) - 5} more errors"
                    raise ImportError(f"Import failed with {len(stats['errors'])} errors:\n{error_summary}")
                
                # Rollback if dry run
                if dry_run:
                    transaction.set_rollback(True)

            logger.info(f'Import file stats: {stats}')
            return stats
            
        except pd.errors.EmptyDataError:
            raise ValidationError('The Excel file is empty')
        except pd.errors.ParserError:
            raise ValidationError('Unable to parse Excel file. Please check the file format.')
        except Exception as e:
            if isinstance(e, (ValidationError, ImportError)):
                raise
            raise ImportError(f'Unexpected error during import: {str(e)}')

    def import_from_path(self, file_path: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Import pregnancy check data from an Excel file path.
        
        Useful for testing or batch processing.
        
        Args:
            file_path: Path to the Excel file
            dry_run: If True, validate but don't save to database
            
        Returns:
            Dictionary with import statistics
        """
        with open(file_path, 'rb') as f:
            return self.import_from_file(f, dry_run=dry_run)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get the current import statistics.
        
        Returns:
            Dictionary with import statistics
        """
        return self.stats.copy()

    def get_summary_message(self) -> str:
        """
        Get a human-readable summary of the import.
        
        Returns:
            Summary message string
        """
        if self.stats['errors']:
            return (f"Import completed with errors. "
                   f"Created {self.stats['pregchecks_created']} pregnancy checks, "
                   f"but {len(self.stats['errors'])} rows failed.")
        return (f"Successfully imported {self.stats['pregchecks_created']} pregnancy checks. "
               f"Created {self.stats['cows_created']} new cows.")