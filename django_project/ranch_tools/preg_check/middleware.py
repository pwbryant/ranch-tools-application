import logging
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


class AutoLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.User = get_user_model()

    def __call__(self, request):
        request.user = self.User.objects.filter(is_superuser=True).first()
        logger.info(f'Add super user to request: {request.user}')
        print(f'Add super user to request: {request.user}')
        return self.get_response(request)