from .base import *


ALLOWED_HOSTS = ['*']
NOTEBOOK_ARGUMENTS = [
    '--ip',
    '0.0.0.0',
    '--port',
    '8887',
    '--allow-root',
    '--no-browser'
]
CSRF_TRUSTED_ORIGINS = ['https://*.ngrok-free.app']
