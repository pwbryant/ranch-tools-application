"""
Unit tests for PregCheckImportService.

Place this file in: your_app/tests/test_pregcheck_import_service.py

Run tests with:
    python manage.py test your_app.tests.test_pregcheck_import_service
"""

from django.test import TestCase
from django.core.exceptions import ValidationError
from ranch_tools.preg_check.models import Cow, PregCheck  # Replace 'your_app' with your actual app name
from ranch_tools.database_management.services.file_import_service import PregCheckImportService, ImportError
import pandas as pd
from io import BytesIO
from datetime import date


class PregCheckImportServiceTestCase(TestCase):
    """Test cases for PregCheckImportService."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.service = PregCheckImportService()
    
    def create_excel_file(self, data):
        """
        Helper method to create an in-memory Excel file from data.
        
        Args:
            data: List of dictionaries representing rows
            
        Returns:
            BytesIO object containing Excel file
        """
        df = pd.DataFrame(data)
        excel_file = BytesIO()
        df.to_excel(excel_file, index=False, engine='openpyxl')
        excel_file.seek(0)
        return excel_file
    
    def test_successful_import_creates_cow_and_pregcheck(self):
        """Test that a valid import creates both Cow and PregCheck records."""
        data = [{
            'ear_tag_id': '123',
            'birth_year': 2020,
            'eid': 'EID123',
            'breeding_season': 2024,
            'check_date': '2024-03-15',
            'comments': 'Test comment',
            'is_pregnant': 'P',
            'recheck': False
        }]
        
        excel_file = self.create_excel_file(data)
        result = self.service.import_from_file(excel_file)
        
        self.assertEqual(result['cows_created'], 1)
        self.assertEqual(result['pregchecks_created'], 1)
        self.assertEqual(Cow.objects.count(), 1)
        self.assertEqual(PregCheck.objects.count(), 1)
        
        cow = Cow.objects.first()
        self.assertEqual(cow.ear_tag_id, '123')
        self.assertEqual(cow.birth_year, 2020)
        self.assertEqual(cow.eid, 'EID123')
        
        pregcheck = PregCheck.objects.first()
        self.assertEqual(pregcheck.cow, cow)
        self.assertEqual(pregcheck.breeding_season, 2024)
        self.assertTrue(pregcheck.is_pregnant)
        
    def test_import_multiple_pregchecks_for_same_cow(self):
        """Test importing multiple pregnancy checks for the same cow."""
        data = [
            {
                'ear_tag_id': '123',
                'birth_year': 2020,
                'eid': 'EID123',
                'breeding_season': 2024,
                'check_date': '2024-03-15',
                'comments': 'First check',
                'is_pregnant': 'P',
                'recheck': False
            },
            {
                'ear_tag_id': '123',
                'birth_year': 2020,
                'eid': 'EID123',
                'breeding_season': 2024,
                'check_date': '2024-04-20',
                'comments': 'Second check',
                'is_pregnant': 'P',
                'recheck': False
            }
        ]
        
        excel_file = self.create_excel_file(data)
        result = self.service.import_from_file(excel_file)
        
        self.assertEqual(result['cows_created'], 1)
        self.assertEqual(result['pregchecks_created'], 2)
        self.assertEqual(Cow.objects.count(), 1)
        self.assertEqual(PregCheck.objects.count(), 2)
    
    def test_missing_required_columns_raises_validation_error(self):
        """Test that missing required columns raises ValidationError."""
        data = [{
            'ear_tag_id': '123',
            'birth_year': 2020,
            # Missing other required columns
        }]
        
        excel_file = self.create_excel_file(data)
        with self.assertRaises(ValidationError) as context:
            self.service.import_from_file(excel_file)
        
        self.assertIn('Missing required columns', str(context.exception))
    
    def test_duplicate_ear_tag_birth_year_check_date_raises_error(self):
        """Test that duplicate ear_tag_id, birth_year, and check_date raises ValidationError."""
        data = [
            {
                'ear_tag_id': '123',
                'birth_year': 2020,
                'eid': 'EID123',
                'breeding_season': 2024,
                'check_date': '2024-03-15',
                'comments': 'First',
                'is_pregnant': 'P',
                'recheck': False
            },
            {
                'ear_tag_id': '123',
                'birth_year': 2020,
                'eid': 'EID456',  # Different EID
                'breeding_season': 2024,
                'check_date': '2024-03-15',  # Same check_date
                'comments': 'Second',
                'is_pregnant': 'O',
                'recheck': True
            }
        ]
        
        excel_file = self.create_excel_file(data)
        
        with self.assertRaises(ValidationError) as context:
            self.service.import_from_file(excel_file)
        
        self.assertIn('Duplicate. Ear Tag: 123, Birth Year: 2020, Check Date: 2024-03-15', 
                      str(context.exception))
    
    def test_duplicate_eid_check_date_raises_error(self):
        """Test that duplicate eid and check_date raises ValidationError."""
        data = [
            {
                'ear_tag_id': '123',
                'birth_year': 2020,
                'eid': 'EID123',
                'breeding_season': 2024,
                'check_date': '2024-03-15',
                'comments': 'First',
                'is_pregnant': 'P',
                'recheck': False
            },
            {
                'ear_tag_id': '456',  # Different ear tag
                'birth_year': 2021,  # Different birth year
                'eid': 'EID123',  # Same EID
                'breeding_season': 2024,
                'check_date': '2024-03-15',  # Same check_date
                'comments': 'Second',
                'is_pregnant': 'O',
                'recheck': True
            }
        ]
        
        excel_file = self.create_excel_file(data)
        
        with self.assertRaises(ValidationError) as context:
            self.service.import_from_file(excel_file)
        
        self.assertIn('Duplicate. EID: EID123, Check Date: 2024-03-15', str(context.exception))
    
    def test_empty_eid_not_checked_for_eid_duplicates(self):
        """Test that rows with empty eid are not checked for duplicates."""
        data = [
            {
                'ear_tag_id': '123',
                'birth_year': 2020,
                'eid': '',
                'breeding_season': 2024,
                'check_date': '2024-03-15',
                'comments': 'First',
                'is_pregnant': 'P',
                'recheck': False
            },
            {
                'ear_tag_id': '456',
                'birth_year': 2021,
                'eid': '',
                'breeding_season': 2024,
                'check_date': '2024-03-15',
                'comments': 'Second',
                'is_pregnant': 'O',
                'recheck': True
            }
        ]
        
        excel_file = self.create_excel_file(data)
        
        # Should not raise ValidationError for EID duplicates
        result = self.service.import_from_file(excel_file)
        self.assertEqual(result['pregchecks_created'], 2)
    
    def test_dry_run_does_not_save_to_database(self):
        """Test that dry_run mode validates but doesn't save to database."""
        data = [{
            'ear_tag_id': '123',
            'birth_year': 2020,
            'eid': 'EID123',
            'breeding_season': 2024,
            'check_date': '2024-03-15',
            'comments': 'Test',
            'is_pregnant': 'P',
            'recheck': False
        }]
        
        excel_file = self.create_excel_file(data)
        result = self.service.import_from_file(excel_file, dry_run=True)
        
        # Stats should show what would have been created
        self.assertEqual(result['cows_created'], 1)
        self.assertEqual(result['pregchecks_created'], 1)
        
        # But nothing should be in database
        self.assertEqual(Cow.objects.count(), 0)
        self.assertEqual(PregCheck.objects.count(), 0)
    
    def test_extract_cow_data(self):
        """Test extract_cow_data method."""
        row = pd.Series({
            'ear_tag_id': '  123  ',
            'birth_year': 2020,
            'eid': '  EID123  '
        })
        
        result = self.service.extract_cow_data(row)
        
        self.assertEqual(result['ear_tag_id'], '123')
        self.assertEqual(result['birth_year'], 2020)
        self.assertEqual(result['eid'], 'EID123')
    
    def test_extract_pregcheck_data(self):
        """Test extract_pregcheck_data method."""
        cow = Cow.objects.create(ear_tag_id='123', birth_year=2020)
        
        row = pd.Series({
            'breeding_season': 2024,
            'check_date': '2024-03-15',
            'comments': '  Test comment  ',
            'is_pregnant': 'P',
            'recheck': False
        })
        
        result = self.service.extract_pregcheck_data(row, cow)
        
        self.assertEqual(result['cow'], cow)
        self.assertEqual(result['breeding_season'], 2024)
        self.assertEqual(result['check_date'], date(2024, 3, 15))
        self.assertEqual(result['comments'], 'Test comment')
        self.assertTrue(result['is_pregnant'])
        self.assertFalse(result['recheck'])
    
    def test_get_summary_message_success(self):
        """Test get_summary_message for successful import."""
        self.service.stats = {
            'cows_created': 2,
            'cows_updated': 1,
            'pregchecks_created': 3,
            'errors': []
        }
        
        message = self.service.get_summary_message()
        
        self.assertIn('Successfully imported', message)
        self.assertIn('3 pregnancy checks', message)
        self.assertIn('2 new cows', message)
    
    def test_get_summary_message_with_errors(self):
        """Test get_summary_message when there are errors."""
        self.service.stats = {
            'cows_created': 1,
            'cows_updated': 0,
            'pregchecks_created': 1,
            'errors': ['Row 2: Error message']
        }
        
        message = self.service.get_summary_message()
        
        self.assertIn('completed with errors', message)
        self.assertIn('1 rows failed', message)
    
    def test_transaction_rollback_on_error(self):
        """Test that transaction is rolled back when an error occurs during processing."""
        # Create data where one row will fail (e.g., invalid date format)
        data = [
            {
                'ear_tag_id': '123',
                'birth_year': 2020,
                'eid': 'EID123',
                'breeding_season': 2024,
                'check_date': '2024-03-15',
                'comments': 'Valid',
                'is_pregnant': 'P',
                'recheck': False
            },
            {
                'ear_tag_id': '456',
                'birth_year': 2021,
                'eid': 'EID456',
                'breeding_season': 2024,
                'check_date': 'invalid-date',
                'comments': 'Invalid date',
                'is_pregnant': 'P',
                'recheck': False
            }
        ]
        
        excel_file = self.create_excel_file(data)
        with self.assertRaises(ImportError):
            self.service.import_from_file(excel_file)
        # Verify nothing was saved due to transaction rollback
        self.assertEqual(Cow.objects.count(), 0)
        self.assertEqual(PregCheck.objects.count(), 0)