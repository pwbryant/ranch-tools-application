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
            'pregchecks_created': 0,
            'errors': []
        }

    def assert_required_columns(self, df: pd.DataFrame) -> None:
        """
        Assert that the dataframe has all required columns.
        
        Args:
            df: The pandas DataFrame to check
            
        Raises:
            ValidationError: If required columns are missing
        """
        missing_columns = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_columns:
            raise ValidationError(f'Missing required columns: {", ".join(missing_columns)}')

    def remove_blank_rows(self, df: pd.DataFrame) -> pd.DataFrame:

        # Check for missing columns
        self.assert_required_columns(df)

        # Remove fully blank rows: rows where all required columns are NaN or empty/whitespace-only
        def _is_blank(val):
            return pd.isna(val) or (isinstance(val, str) and val.strip() == '')

        # Build mask of blank rows across required columns
        required_cols = [c for c in self.REQUIRED_COLUMNS if c in df.columns]
        if required_cols:
            blank_mask = df[required_cols].applymap(_is_blank).all(axis=1)
            # Keep only non-blank rows
            df = df.loc[~blank_mask].reset_index(drop=True)
            logger.debug(f"Removed {blank_mask.sum()} blank rows from dataframe")
        return df

    def standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        # 'is_pregant' needs to be lowercase
        df['is_pregnant'] = df['is_pregnant'].apply(
            lambda x: str(x).strip().lower() if pd.notna(x) else x
        )
        # convert is_pregnant to boolean
        df['is_pregnant'] = df['is_pregnant'].map(
            {'t': True, 'f': False, 'p': True, 'o': False}
        )

        # assert that is_pregnant only contains True, False, or NaN
        if not df['is_pregnant'].isin([True, False]).all():
            raise ValidationError('Invalid values in "is_pregnant" column. Use T/F or P/O.')
        return df
    
    def validate_dataframe(self, df: pd.DataFrame) -> None:
        """
        Validate that the dataframe has all required columns and no duplicates.
        
        Args:
            df: The pandas DataFrame to validate
            
        Raises:
            ValidationError: If required columns are missing or duplicates exist
        """
        # Check for missing columns
        self.assert_required_columns(df)
        
        # Check for empty values in required fields
        required_fields = ['check_date', 'is_pregnant']
        for field in required_fields:
            if df[field].isnull().any() or (df[field].apply(lambda x: isinstance(x, str) and x.strip() == '')).any():
                raise ValidationError(f'Required field "{field}" contains empty values')

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
        ear_tag_duplicates = self._check_duplicates_by_ear_tag(df_check)
        
        # Check for duplicates based on eid and check_date
        eid_duplicates = self._check_duplicates_by_eid(df_check)

        duplicates = []
        if ear_tag_duplicates:
            duplicates.extend(ear_tag_duplicates)
        if eid_duplicates:
            duplicates.extend(eid_duplicates)

        if duplicates:
            from django.utils.html import mark_safe
            error_list = '<ul>' + ''.join(f'<li>{d}</li>' for d in duplicates) + '</ul>'
            error_msg = mark_safe(f'Found {len(duplicates)} duplicate records:<br>{error_list}')
            raise ValidationError(error_msg)
    
    def _check_duplicates_by_ear_tag(self, df_check: pd.DataFrame) -> list[str]:
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
                    f"Duplicate. Ear Tag: {ear_tag}, Birth Year: {birth_year}, "
                    f"Check Date: {check_date} (rows: {rows_str})"
                )
            
            return error_details
    
    def _check_duplicates_by_eid(self, df_check: pd.DataFrame) -> list[str]:
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
        error_details = []
        if not duplicates.empty:
            # Group duplicates to show which records are duplicated
            duplicate_groups = duplicates.groupby(duplicate_columns).size()
            
            for (eid, check_date), count in duplicate_groups.items():
                # Find the row numbers for this duplicate group in the original dataframe
                mask = (
                    (df_check['eid'] == eid) &
                    (df_check['check_date'] == check_date)
                )
                row_numbers = df_check[mask].index + 2  # +2 for Excel row numbers (1-indexed + header)
                rows_str = ', '.join(map(str, row_numbers))
                error_details.append(
                    f"Duplicate. EID: {eid}, Check Date: {check_date} (rows: {rows_str})"
                )
            
        return error_details

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

    def get_or_create_cow(self, cow_data: Dict[str, Any]) -> tuple[Cow, bool]:
        """
        Get or create a cow, updating EID if necessary.
        
        Args:
            cow_data: Dictionary containing cow data
            
        Returns:
            Tuple of (cow instance, was_created)
        """
        if cow_data['eid']:
            cow, created = Cow.objects.get_or_create(
                eid=cow_data['eid'],
                birth_year=cow_data['birth_year'],
                ear_tag_id=cow_data['ear_tag_id']
            )
        elif cow_data['ear_tag_id'] and cow_data['birth_year']:
            cow, created = Cow.objects.get_or_create(
                ear_tag_id=cow_data['ear_tag_id'],
                birth_year=cow_data['birth_year']
            )
        else:
            cow = None # Cow can be None if both eid and ear_tag_id/birth_year are missing
            created = False

        return cow, created

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
        cow, created = self.get_or_create_cow(cow_data)
        
        pregcheck_data = self.extract_pregcheck_data(row, cow)
        pc = PregCheck.objects.create(**pregcheck_data)
        
        return {
            'cow_created': created,
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
            # Read Excel file with ear_tag_id and eid as strings to preserve leading zeros
            if '.csv' in getattr(file, 'name', '').lower():
                df = pd.read_csv(file, dtype={'ear_tag_id': str, 'eid': str})
            elif '.xlsx' in getattr(file, 'name', '').lower() or '.xls' in getattr(file, 'name', '').lower() or isinstance(file, BytesIO):
                df = pd.read_excel(file, dtype={'ear_tag_id': str, 'eid': str})
            else:
                raise ValidationError('Unsupported file format. Please upload an Excel or CSV file.')        

            # Remove blank rows
            df = self.remove_blank_rows(df)
            # Standardize data
            df = self.standardize_dataframe(df)

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
               f"Created {self.stats['cows_created']} new cows.")