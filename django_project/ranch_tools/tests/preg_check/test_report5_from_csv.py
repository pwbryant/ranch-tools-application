import csv
from django.test import TestCase, Client
from django.urls import reverse

from ranch_tools.preg_check.models import Cow, PregCheck, CurrentBreedingSeason
from pathlib import Path


class ReportFiveFromCSVTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_report_from_csv(self):
        # locate test data file relative to this test module (no 'django_project' in path)
        path = Path(__file__).resolve().parent / 'data' / 'test_data.csv'
        path = str(path)  # open() accepts a path-like, but keep it as str for compatibility
        with open(path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                season = int(row['breeding_season'])
                ear = row['cow_ear_tag'].strip() if row['cow_ear_tag'] else ''
                birth_year = row['birth_year'].strip()
                birth_year_val = int(birth_year) if birth_year and birth_year != '' else None
                is_pregnant = row['is_pregnant'].strip().lower() == 'true'
                recheck = row['recheck'].strip().lower() == 'true'

                cow = None
                if ear:
                    cow, _ = Cow.objects.get_or_create(ear_tag_id=ear, defaults={'birth_year': birth_year_val})
                    # ensure birth_year is set
                    if birth_year_val is not None and cow.birth_year != birth_year_val:
                        cow.birth_year = birth_year_val
                        cow.save()

                PregCheck.objects.create(
                    breeding_season=season,
                    cow=cow,
                    is_pregnant=is_pregnant,
                    recheck=recheck
                )

        # Request report for 2025
        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2025})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Check that 2020 row exists and has expected values
        self.assertIn('2020', content)
        # first_pass_open should be 2 (cow A first open, cow B open)
        row_1 = response.context['rows'][0]
        self.assertEqual(row_1['first_pass_open'], 2)
        # preg_recheck_count should be 1 (cow A has a recheck)
        self.assertEqual(row_1['preg_recheck_count'], 1)
        # pct_pregnant should be 50.0%
        self.assertIn('50.0%', content)

        # Unknown Cow should appear for unassociated pregchecks
        self.assertIn('None', content)
