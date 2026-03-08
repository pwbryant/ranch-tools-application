# pregcheck/tests.py
from django.test import TestCase
from ranch_tools.preg_check.apps import create_superuser
from django.contrib.auth import get_user_model

User = get_user_model()


class AppConfigTests(TestCase):

    def test_creates_superuser_if_none_exists(self):
        # middleware runs pre-test so this should exist
        self.assertTrue(User.objects.filter(is_superuser=True).exists())

    def test_does_not_create_duplicate_superuser(self):
        create_superuser(sender=None)
        self.assertEqual(User.objects.filter(is_superuser=True).count(), 1)
