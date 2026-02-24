from datetime import datetime

from django.test import TestCase

from ranch_tools.preg_check.models import Cow, PregCheck


class PregCheckTestCase(TestCase):

    def test_recheck_save_logic(self):

        cow = Cow.objects.create(ear_tag_id='1234', birth_year=1983)       
        with self.assertRaises(Exception) as ctx:
            PregCheck.objects.create(
                cow=cow,
                breeding_season=2026,
                check_date=datetime.now(),
                is_pregnant=True,
                recheck=True
            )
        expected_error = 'Cannot mark as recheck: no previous non-recheck PregCheck found for "1234-1983" in breeding season 2026'
        self.assertEqual(str(ctx.exception), expected_error)