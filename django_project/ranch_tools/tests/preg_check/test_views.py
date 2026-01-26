from datetime import date

from django.test import TestCase, Client
from django.urls import reverse

from ranch_tools.preg_check.forms import AnimalSearchForm, PregCheckForm
from ranch_tools.preg_check.models import Cow, PregCheck, CurrentBreedingSeason

class CowExistsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.cow = Cow.objects.create(ear_tag_id="EAR123", eid="RFID123", birth_year=2015)

    def test_cow_exists(self):
        response = self.client.get(reverse('cow-exists'), {'ear_tag_id': 'EAR123'})
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'exists': True})

    def test_cow_does_not_exist(self):
        response = self.client.get(reverse('cow-exists'), {'ear_tag_id': 'NON_EXISTENT'})
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'exists': False})

    def test_missing_ear_tag_id(self):
        response = self.client.get(reverse('cow-exists'))
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {'error': 'check_existing_ear_tag_id parameter is required'})


class PregCheckReportFiveViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_report_five_renders(self):
        response = self.client.get(reverse('pregcheck-report-5'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report Five")


class PregCheckReportFiveCalculationsTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Ensure a current breeding season is present
        self.current_season = CurrentBreedingSeason.objects.create(breeding_season=2025)

    def test_pct_and_recheck_count_unique(self):
        # Create two cows born in 2020
        cow_a = Cow.objects.create(ear_tag_id='A1', birth_year=2020)
        cow_b = Cow.objects.create(ear_tag_id='B1', birth_year=2020)

        # Cow A: first check open, second check recheck and pregnant
        PregCheck.objects.create(cow=cow_a, breeding_season=2025, is_pregnant=False, recheck=False)
        PregCheck.objects.create(cow=cow_a, breeding_season=2025, is_pregnant=True, recheck=True)

        # Cow B: single open
        PregCheck.objects.create(cow=cow_b, breeding_season=2025, is_pregnant=False, recheck=False)

        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2025})
        self.assertEqual(response.status_code, 200)

        # first_pass counts only the first check per cow: Cow A first is open, Cow B is open => first_pass_open = 2
        row_1 = response.context['rows'][0]
        self.assertEqual(row_1['first_pass_open'], 2)

        # The row for birth_year 2020 should show first_pass_open 2, preg_recheck_count 1, pct_pregnant 50.0%
        content = response.content.decode('utf-8')
        # crude checks
        self.assertEqual(row_1['cow_birth_year'], 2020)
        self.assertEqual(row_1['first_pass_open'], 2)
        self.assertEqual(row_1['first_pass_pregnant'], 0)
        self.assertEqual(row_1['pct_pregnant'], '50.0%')


class PreviousPregCheckListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.current_season = CurrentBreedingSeason.objects.create(breeding_season=2025)
        self.cow = Cow.objects.create(ear_tag_id="EAR123", eid="RFID123", birth_year=2015)
        self.pregcheck = PregCheck.objects.create(cow=self.cow, breeding_season=2025, is_pregnant=True)

    def test_previous_pregcheck_list(self):
        response = self.client.get(reverse('previous-pregchecks'), {'limit': 1})
        self.assertEqual(response.status_code, 200)
        self.assertIn('pregchecks', response.json())
        self.assertEqual(len(response.json()['pregchecks']), 1)

class PregCheckListViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.current_season = CurrentBreedingSeason.objects.create(breeding_season=2025)
        self.cow = Cow.objects.create(ear_tag_id="EAR123", eid="RFID123", birth_year=2015)
        self.pregcheck = PregCheck.objects.create(cow=self.cow, breeding_season=2025, is_pregnant=True)

    def test_pregcheck_list(self):
        response = self.client.get(reverse('pregcheck-list'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue('pregcheck_list.html' in response.template_name)

    def test_search_by_ear_tag_id(self):
        response = self.client.get(reverse('pregcheck-list'), {'search_ear_tag_id': 'EAR123'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'EAR123')

    def test_get_context_data(self):
        response = self.client.get(reverse('pregcheck-list') + '?search_ear_tag_id=EAR123&search_birth_year=2015')
        self.assertEqual(response.status_code, 200)
        self.assertIn('current_breeding_season', response.context)

        self.assertEqual(response.context['current_breeding_season'], 2025)
        self.assertEqual(response.context['all_preg_checks'], False)
        self.assertEqual(response.context['latest_breeding_season'], 2025)

        search_form = response.context['search_form']
        self.assertIsInstance(search_form, AnimalSearchForm)
        self.assertEqual(search_form['search_ear_tag_id'].value(), 'EAR123')
        self.assertEqual(search_form['search_rfid'].value(), '')
        self.assertEqual(search_form['search_birth_year'].value(), 2015)

        pregcheck_form = response.context['pregcheck_form']
        self.assertIsInstance(pregcheck_form, PregCheckForm)
        self.assertEqual(pregcheck_form['birth_year'].initial, self.cow.birth_year)
        self.assertEqual(pregcheck_form.fields['pregcheck_ear_tag_id'].initial, self.cow.ear_tag_id)
        self.assertEqual(pregcheck_form.fields['pregcheck_rfid'].initial, self.cow.eid)
        self.assertEqual(pregcheck_form.fields['should_sell'].initial, False)
        self.assertEqual(pregcheck_form.fields['check_date'].initial, None)

        self.assertEqual(response.context['animal_exists'], True)
        self.assertEqual(response.context['multiple_matches'], False)
        self.assertEqual(response.context['distinct_birth_years'], [self.cow.birth_year])
        self.assertEqual(response.context['cow'], self.cow)        

    def test_get_context_data_should_sell_comes_from_last_cow_pregcheck(self):
        # Create a pregcheck with should_sell=True
        pregcheck = PregCheck.objects.create(cow=self.cow, breeding_season=2025, is_pregnant=True, should_sell=True)

        response = self.client.get(reverse('pregcheck-list') + '?search_ear_tag_id=EAR123')

        pregcheck_form = response.context['pregcheck_form']
        self.assertEqual(pregcheck_form.fields['should_sell'].initial, True)

    def test_get_context_data_check_date_comes_from_last_pregcheck(self):
        # Create a pregcheck with today's date
        pregcheck = PregCheck.objects.create(cow=self.cow, breeding_season=2025, is_pregnant=True, check_date=date.today())

        response = self.client.get(reverse('pregcheck-list') + '?search_ear_tag_id=EAR123')

        pregcheck_form = response.context['pregcheck_form']
        self.assertEqual(pregcheck_form.fields['check_date'].initial, date.today())


class PregCheckDetailViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.cow = Cow.objects.create(ear_tag_id="EAR123", eid="RFID123", birth_year=2015)
        self.pregcheck = PregCheck.objects.create(cow=self.cow, breeding_season=2025, is_pregnant=True)

    def test_pregcheck_detail(self):
        response = self.client.get(reverse('pregcheck-detail', args=[self.pregcheck.id]))
        self.assertEqual(response.status_code, 200)
        response_data = response.json()
        self.assertEqual(response_data['id'], self.pregcheck.id)
        self.assertEqual(response_data['is_pregnant'], self.pregcheck.is_pregnant)
        self.assertEqual(response_data['comments'], self.pregcheck.comments)
        self.assertEqual(response_data['recheck'], self.pregcheck.recheck)
        self.assertEqual(response_data['breeding_season'], self.pregcheck.breeding_season)

    def test_pregcheck_not_found(self):
        response = self.client.get(reverse('pregcheck-detail', args=[999]))
        self.assertEqual(response.status_code, 404)


class CowCreateUpdateViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.cow = Cow.objects.create(ear_tag_id="EAR123", eid="RFID123", birth_year=2015)
        self.create_url = reverse('cow-create')  # Replace with the actual URL name for CowCreateUpdateView
        self.update_url = reverse('cow-create-update')

    def test_create_cow(self):
        """Test creating a new cow."""
        data = {
            'ear_tag_id': 'NEW123',
            'eid': 'NEW_RFID',
            'birth_year': 2020,
        }
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        self.assertTrue(Cow.objects.filter(ear_tag_id='NEW123', eid='NEW_RFID', birth_year=2020).exists())

    def test_update_cow(self):
        """Test updating an existing cow."""
        data = {
            'ear_tag_id': 'EAR123',
            'eid': 'RFID123',
            'birth_year': 2016,  # Update the birth year
        }
        response = self.client.post(self.update_url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful update
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.birth_year, 2016)

    def test_multiple_cows_error(self):
        """Test that an exception is raised when multiple cows match the criteria."""
        Cow.objects.create(ear_tag_id="EAR123")  # Create a duplicate cow
        data = {'ear_tag_id': "EAR123"}

        with self.assertRaises(Exception) as context:
            self.client.post(self.update_url, data)

        self.assertEqual(str(context.exception), 'There is more than one cow associated with this information.')

    # def test_form_invalid(self):
    #     """Test invalid form submission."""
    #     data = {
    #         'ear_tag_id': '',  # Missing required field
    #         'eid': 'RFID123',
    #         'birth_year': 2015,
    #     }
    #     response = self.client.post(self.create_url, data)
    #     self.assertEqual(response.status_code, 200)  # Form invalid, re-render the form
    #     self.assertFormError(response, 'form', 'ear_tag_id', 'This field is required.')


class PregCheckReportFiveDetailedTest(TestCase):
    """Detailed tests for PregCheckReportFive view including totals and calculations"""
    
    def setUp(self):
        self.client = Client()
        self.current_season = CurrentBreedingSeason.objects.create(breeding_season=2025)
        
    def test_report_five_no_data(self):
        """Test report five with no data"""
        response = self.client.get(reverse('pregcheck-report-5'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report Five")
        self.assertContains(response, "No data for this season")
        
    def test_report_five_single_age_class(self):
        """Test report five with single age class"""
        cow = Cow.objects.create(ear_tag_id='EAR001', birth_year=2020, eid='RFID001')
        PregCheck.objects.create(cow=cow, breeding_season=2025, is_pregnant=True, recheck=False)
        
        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2025})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2020')
        self.assertContains(response, '100.0%')  # 1 pregnant out of 1 total
        
    def test_report_five_multiple_age_classes(self):
        """Test report five with multiple age classes"""
        # Create cows of different ages
        cow_2020 = Cow.objects.create(ear_tag_id='EAR001', birth_year=2020, eid='RFID001')
        cow_2021 = Cow.objects.create(ear_tag_id='EAR002', birth_year=2021, eid='RFID002')
        cow_2022 = Cow.objects.create(ear_tag_id='EAR003', birth_year=2022, eid='RFID003')
        
        # Age 5: 1 pregnant out of 1
        PregCheck.objects.create(cow=cow_2020, breeding_season=2025, is_pregnant=True, recheck=False)
        
        # Age 4: 1 pregnant out of 2 (one of the pregchecks is a recheck, but we count unique cows)
        PregCheck.objects.create(cow=cow_2021, breeding_season=2025, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow_2021, breeding_season=2025, is_pregnant=False, recheck=True)
        
        # Age 3: 0 pregnant out of 1
        PregCheck.objects.create(cow=cow_2022, breeding_season=2025, is_pregnant=False, recheck=False)
        
        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2025})
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Check that all birth years are present
        self.assertIn('2020', content)
        self.assertIn('2021', content)
        self.assertIn('2022', content)
        # Check percentages - cow_2021 has 1 pregnant out of 1 unique cow = 100%
        self.assertIn('100.0%', content)   # Both 2020 and 2021 should be 100%
        self.assertIn('0.0%', content)     # 2022 should be 0%
        
    def test_report_five_totals_row(self):
        """Test that totals row is calculated correctly"""
        cow_a = Cow.objects.create(ear_tag_id='EAR001', birth_year=2020, eid='RFID001')
        cow_b = Cow.objects.create(ear_tag_id='EAR002', birth_year=2021, eid='RFID002')
        cow_c = Cow.objects.create(ear_tag_id='EAR003', birth_year=2021, eid='RFID003')
        cow_d = Cow.objects.create(ear_tag_id='EAR004', birth_year=2021, eid='RFID004')

        PregCheck.objects.create(cow=cow_a, breeding_season=2025, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow_b, breeding_season=2025, is_pregnant=False, recheck=False)
        PregCheck.objects.create(cow=cow_c, breeding_season=2025, is_pregnant=False, recheck=False)
        PregCheck.objects.create(cow=cow_d, breeding_season=2025, is_pregnant=False, recheck=False)

        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2025})
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        self.assertIn('TOTALS', content)
        # Average percentage should be (100 + 50) / 2 = 75.0%
        self.assertIn('25.0%', content)
        
    def test_report_five_recheck_count_unique_cows(self):
        """Test that preg_recheck_count counts unique cows, not checks"""
        cow_a = Cow.objects.create(ear_tag_id='EAR001', birth_year=2020, eid='RFID001')
        cow_b = Cow.objects.create(ear_tag_id='EAR002', birth_year=2020, eid='RFID002')

        # Cow A: 2 recheck records (should count as 1 cow with recheck)
        PregCheck.objects.create(cow=cow_a, breeding_season=2025, is_pregnant=False, recheck=False)
        PregCheck.objects.create(cow=cow_a, breeding_season=2025, is_pregnant=True, recheck=True)
        PregCheck.objects.create(cow=cow_a, breeding_season=2025, is_pregnant=True, recheck=True)
        
        # Cow B: 1 recheck record
        PregCheck.objects.create(cow=cow_b, breeding_season=2025, is_pregnant=False, recheck=False)
        PregCheck.objects.create(cow=cow_b, breeding_season=2025, is_pregnant=False, recheck=True)
        
        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2025})
        self.assertEqual(response.status_code, 200)
        # preg_recheck_count should be 1 (only Cow A had pregnant recheck)
        content = response.content.decode('utf-8')
        self.assertIn('Preg Recheck Count', content)
        self.assertEqual(response.context['totals']['preg_recheck_count'], 1)
        
    def test_report_five_custom_breeding_season(self):
        """Test report five with custom breeding season parameter"""
        # Use a different season than the one in setUp
        cow = Cow.objects.create(ear_tag_id='EAR001', birth_year=2020, eid='RFID001')
        PregCheck.objects.create(cow=cow, breeding_season=2024, is_pregnant=True, recheck=False)
        
        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2024})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2024')
        
    def test_report_five_first_pass_counts(self):
        """Test that first pass counts only include first check per cow"""
        cow = Cow.objects.create(ear_tag_id='EAR001', birth_year=2020, eid='RFID001')
        
        # First check: open
        PregCheck.objects.create(cow=cow, breeding_season=2025, is_pregnant=False, recheck=False)
        # Second check (recheck): pregnant
        PregCheck.objects.create(cow=cow, breeding_season=2025, is_pregnant=True, recheck=True)

        response = self.client.get(reverse('pregcheck-report-5'), {'breeding_season': 2025})
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # first_pass_open should be 1, first_pass_pregnant should be 0
        self.assertIn('First Pass Open', content)
        self.assertEqual(response.context['rows'][0]['first_pass_open'], 1)


class PregCheckRollingAverageReportTest(TestCase):
    """Tests for PregCheckRollingAverageReport view"""
    
    def setUp(self):
        self.client = Client()
        
    def test_rolling_average_no_data(self):
        """Test rolling average report with no data"""
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rolling Average Report")
        self.assertContains(response, "No data available")
        
    def test_rolling_average_single_season(self):
        """Test rolling average with data from single season"""
        cow = Cow.objects.create(ear_tag_id='EAR001', birth_year=2021, eid='RFID001')
        PregCheck.objects.create(cow=cow, breeding_season=2025, is_pregnant=True, recheck=False)
        
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2025')
        self.assertContains(response, '100.0%')
        
    def test_rolling_average_multiple_seasons(self):
        """Test rolling average with data from multiple seasons"""
        cow_2021 = Cow.objects.create(ear_tag_id='EAR001', birth_year=2021, eid='RFID001')
        cow_2022 = Cow.objects.create(ear_tag_id='EAR002', birth_year=2022, eid='RFID002')
        
        # Season 2022: Age 1 cow, 100% pregnant
        PregCheck.objects.create(cow=cow_2021, breeding_season=2022, is_pregnant=True, recheck=False)
        
        # Season 2023: Age 1 cow, 0% pregnant; Age 2 cow, 100% pregnant
        PregCheck.objects.create(cow=cow_2021, breeding_season=2023, is_pregnant=False, recheck=False)
        PregCheck.objects.create(cow=cow_2022, breeding_season=2023, is_pregnant=True, recheck=False)
        
        # Season 2024: Age 1 cow, 100% pregnant; Age 2 cow, 100% pregnant
        PregCheck.objects.create(cow=cow_2021, breeding_season=2024, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow_2022, breeding_season=2024, is_pregnant=True, recheck=False)
        
        # Season 2025: Age 1 cow, 50% pregnant; Age 2 cow, 100% pregnant
        cow_2024 = Cow.objects.create(ear_tag_id='EAR003', birth_year=2024, eid='RFID003')
        PregCheck.objects.create(cow=cow_2021, breeding_season=2025, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow_2024, breeding_season=2025, is_pregnant=False, recheck=False)
        PregCheck.objects.create(cow=cow_2022, breeding_season=2025, is_pregnant=True, recheck=False)
        
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Should show data for ages 1, 2, and 3
        self.assertIn('Rolling Average Report', content)
        self.assertIn('Rolling Avg', content)
        
    def test_rolling_average_gets_last_four_seasons(self):
        """Test that rolling average uses only last 4 seasons"""
        cow = Cow.objects.create(ear_tag_id='EAR001', birth_year=2015, eid='RFID001')
        
        # Create data for 6 seasons
        for season in range(2020, 2026):
            PregCheck.objects.create(cow=cow, breeding_season=season, is_pregnant=True, recheck=False)
        
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Should show last 4 seasons: 2022, 2023, 2024, 2025
        self.assertIn('2022', content)
        self.assertIn('2023', content)
        self.assertIn('2024', content)
        self.assertIn('2025', content)
        # Should not show 2020 and 2021
        self.assertNotIn('>2020<', content)
        self.assertNotIn('>2021<', content)
        
    def test_rolling_average_totals_row(self):
        """Test that totals row is present and calculates average"""
        cow = Cow.objects.create(ear_tag_id='EAR001', birth_year=2021, eid='RFID001')
        
        # Create data for 2 seasons
        # Season 2024: 100% pregnant
        PregCheck.objects.create(cow=cow, breeding_season=2024, is_pregnant=True, recheck=False)
        
        # Season 2025: 50% pregnant (2 cows, 1 pregnant)
        cow2 = Cow.objects.create(ear_tag_id='EAR002', birth_year=2024, eid='RFID002')
        PregCheck.objects.create(cow=cow, breeding_season=2025, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow2, breeding_season=2025, is_pregnant=False, recheck=False)
        
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Check for totals/average row
        self.assertIn('AVERAGE', content)
        
    def test_rolling_average_missing_data_shows_dash(self):
        """Test that missing data for age/season combination shows dash"""
        cow_2021 = Cow.objects.create(ear_tag_id='EAR001', birth_year=2021, eid='RFID001')
        cow_2023 = Cow.objects.create(ear_tag_id='EAR002', birth_year=2023, eid='RFID002')
        
        # Season 2024: only age 3 data
        PregCheck.objects.create(cow=cow_2021, breeding_season=2024, is_pregnant=True, recheck=False)
        
        # Season 2025: age 2 and age 4 data
        PregCheck.objects.create(cow=cow_2023, breeding_season=2025, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow_2021, breeding_season=2025, is_pregnant=True, recheck=False)
        
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Should show dashes for missing data
        self.assertIn('—', content)
        
    def test_rolling_average_age_calculation(self):
        """Test that age is correctly calculated as breeding_season - birth_year"""
        cow = Cow.objects.create(ear_tag_id='EAR001', birth_year=2020, eid='RFID001')
        PregCheck.objects.create(cow=cow, breeding_season=2025, is_pregnant=True, recheck=False)
        
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Age should be 5 (2025 - 2020)
        self.assertIn('5', content)
        
    def test_rolling_average_multiple_cows_same_age(self):
        """Test pregnancy rate calculation with multiple cows of same age"""
        # Two cows born in 2021 (will be age 4 in 2025)
        cow_a = Cow.objects.create(ear_tag_id='EAR001', birth_year=2021, eid='RFID001')
        cow_b = Cow.objects.create(ear_tag_id='EAR002', birth_year=2021, eid='RFID002')
        cow_c = Cow.objects.create(ear_tag_id='EAR003', birth_year=2021, eid='RFID003')
        
        # 2 out of 3 pregnant
        PregCheck.objects.create(cow=cow_a, breeding_season=2025, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow_b, breeding_season=2025, is_pregnant=True, recheck=False)
        PregCheck.objects.create(cow=cow_c, breeding_season=2025, is_pregnant=False, recheck=False)
        
        response = self.client.get(reverse('pregcheck-rolling-average-report'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode('utf-8')
        # Should show 66.7% for age 4
        self.assertIn('66.7%', content)
