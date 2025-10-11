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

from django.db import transaction
from django.core.exceptions import ValidationError
from ranch_tools.preg_check.models import Cow, PregCheck  # Replace 'your_app' with your actual app name
import pandas as pd
from typing import Dict, Any, BinaryIO, List


class ImportError(Exception):
    """Custom exception for import errors."""
    pass


class PregCheckImportService:
    """Service class for importing pregnancy check data from Excel files."""
    
    REQUIRED_COLUMNS = [
        'ear_tag_id', 'birth_year', 'eid', 'breeding_season',
        'check_date', 'comments', 'is_pregnant', 'recheck'
    ]

    def __init__(self):
        """Initialize the service with empty statistics."""
        self.reset_stats()

    def reset_stats(self):
        """Reset import statistics."""
        self.stats = {
            'cows_created': 0,
            'cows_updated': 0,
            'pregchecks_created': 0,
            'errors': []
        }

    def validate_dataframe(self, df: pd.DataFrame) -> None:
        """
        Validate that the dataframe has all required columns and no duplicates.
        
        Args:
            df: The pandas DataFrame to validate
            
        Raises:
            ValidationError: If required columns are missing or duplicates exist
        """
        # Check for missing columns
        missing_columns = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            raise ValidationError(f'Missing required columns: {", ".join(missing_columns)}')
        
        # Create a temporary dataframe with cleaned data for duplicate checking
        df_check = df.copy()
        df_check['ear_tag_id'] = df_check['ear_tag_id'].apply(
            lambda x: str(x).strip() if pd.notna(x) else None
        )
        df_check['birth_year'] = df_check['birth_year'].apply(
            lambda x: int(x) if pd.notna(x) else None
        )
        df_check['eid'] = df_check['eid'].apply(
            lambda x: str(x).strip() if pd.notna(x) else None
        )
        df_check['check_date'] = df_check['check_date'].apply(
            lambda x: pd.to_datetime(x).date() if pd.notna(x) else None
        )
        
        # Check for duplicates based on ear_tag_id, birth_year, and check_date
        self._check_duplicates_by_ear_tag(df_check)
        
        # Check for duplicates based on eid and check_date
        self._check_duplicates_by_eid(df_check)
    
    def _check_duplicates_by_ear_tag(self, df_check: pd.DataFrame) -> None:
        """
        Check for duplicate records based on ear_tag_id, birth_year, and check_date.
        
        Args:
            df_check: DataFrame with cleaned data
            
        Raises:
            ValidationError: If duplicates are found
        """
        duplicate_columns = ['ear_tag_id', 'birth_year', 'check_date']
        
        # Filter out rows where any of the duplicate-check columns are None/empty
        df_check_filtered = df_check[
            df_check['ear_tag_id'].notna() & 
            (df_check['ear_tag_id'] != '') &
            df_check['birth_year'].notna() & 
            df_check['check_date'].notna()
        ].copy()
        
        # Only check for duplicates if we have rows with complete data
        if df_check_filtered.empty:
            return
        
        # Find duplicates in the filtered data
        duplicates = df_check_filtered[df_check_filtered.duplicated(subset=duplicate_columns, keep=False)]
        
        if not duplicates.empty:
            # Group duplicates to show which records are duplicated
            duplicate_groups = duplicates.groupby(duplicate_columns).size()
            error_details = []
            
            for (ear_tag, birth_year, check_date), count in duplicate_groups.items():
                # Find the row numbers for this duplicate group in the original dataframe
                mask = (
                    (df_check['ear_tag_id'] == ear_tag) &
                    (df_check['birth_year'] == birth_year) &
                    (df_check['check_date'] == check_date)
                )
                row_numbers = df_check[mask].index + 2  # +2 for Excel row numbers (1-indexed + header)
                rows_str = ', '.join(map(str, row_numbers))
                error_details.append(
                    f"  - Ear Tag: {ear_tag}, Birth Year: {birth_year}, "
                    f"Check Date: {check_date} (rows: {rows_str})"
                )
            
            error_message = (
                f"Found {len(duplicate_groups)} duplicate record(s) with the same "
                f"ear_tag_id, birth_year, and check_date:\n" +
                '\n'.join(error_details[:10])  # Show first 10 duplicates
            )
            
            if len(duplicate_groups) > 10:
                error_message += f"\n  ... and {len(duplicate_groups) - 10} more duplicates"
            
            raise ValidationError(error_message)
    
    def _check_duplicates_by_eid(self, df_check: pd.DataFrame) -> None:
        """
        Check for duplicate records based on eid and check_date.
        
        Args:
            df_check: DataFrame with cleaned data
            
        Raises:
            ValidationError: If duplicates are found
        """
        duplicate_columns = ['eid', 'check_date']
        
        # Filter out rows where any of the duplicate-check columns are None/empty
        df_check_filtered = df_check[
            df_check['eid'].notna() & 
            (df_check['eid'] != '') &
            df_check['check_date'].notna()
        ].copy()
        
        # Only check for duplicates if we have rows with complete data
        if df_check_filtered.empty:
            return
        
        # Find duplicates in the filtered data
        duplicates = df_check_filtered[df_check_filtered.duplicated(subset=duplicate_columns, keep=False)]
        
        if not duplicates.empty:
            # Group duplicates to show which records are duplicated
            duplicate_groups = duplicates.groupby(duplicate_columns).size()
            error_details = []
            
            for (eid, check_date), count in duplicate_groups.items():
                # Find the row numbers for this duplicate group in the original dataframe
                mask = (
                    (df_check['eid'] == eid) &
                    (df_check['check_date'] == check_date)
                )
                row_numbers = df_check[mask].index + 2  # +2 for Excel row numbers (1-indexed + header)
                rows_str = ', '.join(map(str, row_numbers))
                error_details.append(
                    f"  - EID: {eid}, Check Date: {check_date} (rows: {rows_str})"
                )
            
            error_message = (
                f"Found {len(duplicate_groups)} duplicate record(s) with the same "
                f"eid and check_date:\n" +
                '\n'.join(error_details[:10])  # Show first 10 duplicates
            )
            
            if len(duplicate_groups) > 10:
                error_message += f"\n  ... and {len(duplicate_groups) - 10} more duplicates"
            
            raise ValidationError(error_message)

    def extract_cow_data(self, row: pd.Series) -> Dict[str, Any]:
        """
        Extract and clean cow data from a dataframe row.
        
        Args:
            row: A pandas Series representing one row
            
        Returns:
            Dictionary with cleaned cow data
        """
        return {
            'ear_tag_id': str(row['ear_tag_id']).strip() if pd.notna(row['ear_tag_id']) else '',
            'birth_year': int(row['birth_year']) if pd.notna(row['birth_year']) else None,
            'eid': str(row['eid']).strip() if pd.notna(row['eid']) else None,
            'comments': str(row.get('cow_comments', '')).strip() if pd.notna(row.get('cow_comments')) else ''
        }

    def extract_pregcheck_data(self, row: pd.Series, cow: Cow) -> Dict[str, Any]:
        """
        Extract and clean pregnancy check data from a dataframe row.
        
        Args:
            row: A pandas Series representing one row
            cow: The Cow instance to associate with this pregnancy check
            
        Returns:
            Dictionary with cleaned pregnancy check data
        """
        return {
            'cow': cow,
            'breeding_season': int(row['breeding_season']) if pd.notna(row['breeding_season']) else None,
            'check_date': pd.to_datetime(row['check_date']).date() if pd.notna(row['check_date']) else None,
            'comments': str(row['comments']).strip() if pd.notna(row['comments']) else '',
            'is_pregnant': bool(row['is_pregnant']) if pd.notna(row['is_pregnant']) else None,
            'recheck': bool(row['recheck']) if pd.notna(row['recheck']) else False,
        }

    def get_or_create_cow(self, cow_data: Dict[str, Any]) -> tuple[Cow, bool, bool]:
        """
        Get or create a cow, updating EID if necessary.
        
        Args:
            cow_data: Dictionary containing cow data
            
        Returns:
            Tuple of (cow instance, was_created, was_updated)
        """
        cow, created = Cow.objects.get_or_create(
            ear_tag_id=cow_data['ear_tag_id'],
            birth_year=cow_data['birth_year'],
            defaults={
                'eid': cow_data['eid'],
                'comments': cow_data['comments']
            }
        )

        updated = False
        if not created and cow_data['eid'] and cow.eid != cow_data['eid']:
            cow.eid = cow_data['eid']
            cow.save()
            updated = True

        return cow, created, updated

    def process_row(self, idx: int, row: pd.Series) -> Dict[str, bool]:
        """
        Process a single row from the dataframe.
        
        Args:
            idx: The row index
            row: A pandas Series representing one row
            
        Returns:
            Dictionary with processing results
        """
        cow_data = self.extract_cow_data(row)
        cow, created, updated = self.get_or_create_cow(cow_data)
        
        pregcheck_data = self.extract_pregcheck_data(row, cow)
        PregCheck.objects.create(**pregcheck_data)
        
        return {
            'cow_created': created,
            'cow_updated': updated,
            'pregcheck_created': True
        }

    def process_dataframe(self, df: pd.DataFrame) -> None:
        """
        Process all rows in the dataframe and update statistics.
        
        Args:
            df: The pandas DataFrame to process
        """
        for idx, row in df.iterrows():
            try:
                result = self.process_row(idx, row)
                if result['cow_created']:
                    self.stats['cows_created'] += 1
                if result['cow_updated']:
                    self.stats['cows_updated'] += 1
                if result['pregcheck_created']:
                    self.stats['pregchecks_created'] += 1
            except Exception as e:
                error_msg = f'Row {idx + 2}: {str(e)}'
                self.stats['errors'].append(error_msg)

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
        
        try:
            # Read Excel file
            df = pd.read_excel(file)
            
            # Validate structure
            self.validate_dataframe(df)
            
            # Process data within a transaction
            with transaction.atomic():
                self.process_dataframe(df)
                
                # Check for errors
                if self.stats['errors']:
                    transaction.set_rollback(True)
                    error_summary = '\n'.join(self.stats['errors'][:5])  # Show first 5 errors
                    if len(self.stats['errors']) > 5:
                        error_summary += f"\n... and {len(self.stats['errors']) - 5} more errors"
                    raise ImportError(f"Import failed with {len(self.stats['errors'])} errors:\n{error_summary}")
                
                # Rollback if dry run
                if dry_run:
                    transaction.set_rollback(True)
            
            return self.stats
            
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
               f"Created {self.stats['cows_created']} new cows, "
               f"updated {self.stats['cows_updated']} existing cows.")
