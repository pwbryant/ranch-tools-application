# pregcheck/tests.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock
from ranch_tools.preg_check.middleware import AutoLoginMiddleware

User = get_user_model()


class AutoLoginMiddlewareTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value=MagicMock())
        self.middleware = AutoLoginMiddleware(self.get_response)
        self.superuser = User.objects.filter(is_superuser=True).first()

    def test_sets_superuser_on_request(self):
        request = self.factory.get('/admin/')
        self.middleware(request)
        self.assertEqual(request.user, self.superuser)

    def test_sets_none_when_no_superuser_exists(self):
        self.superuser.delete()
        request = self.factory.get('/admin/')
        self.middleware(request)
        self.assertIsNone(request.user)

    def test_calls_get_response(self):
        request = self.factory.get('/admin/')
        self.middleware(request)
        self.get_response.assert_called_once_with(request)
