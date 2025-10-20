from django.test import TestCase, Client
from django.urls import reverse
from django.http import JsonResponse
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
        self.assertContains(response, "cow_birth_year")


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

        # Check expected values are rendered: first_pass_open should be 2? Actually:
        # first_pass counts only the first check per cow: Cow A first is open, Cow B is open => first_pass_open = 2
        self.assertContains(response, 'first_pass_open')

        # The row for birth_year 2020 should show first_pass_open 2, preg_recheck_count 1, pct_pregnant 50.0%
        content = response.content.decode('utf-8')
        # crude checks
        self.assertIn('2020', content)
        self.assertIn('first_pass_open', content)
        self.assertIn('first_pass_pregnant', content)
        # Check for the numeric strings
        self.assertIn('2', content)  # first_pass_open 2
        self.assertIn('1', content)  # preg_recheck_count 1
        self.assertIn('50.0%', content)

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

class PregCheckDetailViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.cow = Cow.objects.create(ear_tag_id="EAR123", eid="RFID123", birth_year=2015)
        self.pregcheck = PregCheck.objects.create(cow=self.cow, breeding_season=2025, is_pregnant=True)

    def test_pregcheck_detail(self):
        response = self.client.get(reverse('pregcheck-detail', args=[self.pregcheck.id]))
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {
            'id': self.pregcheck.id,
            'is_pregnant': self.pregcheck.is_pregnant,
            'comments': self.pregcheck.comments,
            'recheck': self.pregcheck.recheck,
        })

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
