from datetime import date

import pandas as pd

from django.test import TestCase

from ranch_tools.preg_check.models import Cow, PregCheck  # Replace 'your_app' with your actual app name
from ranch_tools.database_management.services.file_import_dataframe_processors import PregcheckDataFrameProcessor


class PregCheckDataFrameProcessorsTestCase(TestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.processor = PregcheckDataFrameProcessor()

    def test_extract_cow_data(self):
        """Test extract_cow_data method."""
        row = pd.Series({
            'ear_tag_id': '  123  ',
            'birth_year': 2020,
            'eid': '  EID123  '
        })
        
        result = self.processor.extract_cow_data(row)
        
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
        
        result = self.processor.extract_pregcheck_data(row, cow)
        
        self.assertEqual(result['cow'], cow)
        self.assertEqual(result['breeding_season'], 2024)
        self.assertEqual(result['check_date'], date(2024, 3, 15))
        self.assertEqual(result['comments'], 'Test comment')
        self.assertTrue(result['is_pregnant'])
        self.assertFalse(result['recheck'])
