from .base import *

DEBUG = False
STATIC_ROOT = Path(BASE_DIR, 'staticfiles')
NOTEBOOK_ARGUMENTS = [
    '--ip',
    '0.0.0.0',
    '--port',
    '8887',
    '--allow-root',
    '--no-browser',
	'--NotebookApp.token=""',
	'--NotebookApp.password=""',

]
INTERNAL_IPS = ['127.0.0.1']  # Update with your server's IP if needed
