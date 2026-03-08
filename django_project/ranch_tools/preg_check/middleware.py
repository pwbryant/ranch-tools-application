import logging
from django.contrib.auth import get_user_model
from django.db import OperationalError

logger = logging.getLogger(__name__)


class AutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.User = get_user_model()

    def __call__(self, request):
        try:
            request.user = self.User.objects.filter(is_superuser=True).first()
        except OperationalError:
            pass # If user table doesn't exist yet
        logger.info(f'Add super user to request: {request.user}')
        print(f'Add super user to request: {request.user}')
        return self.get_response(request)