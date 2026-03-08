from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_superuser(sender, **kwargs):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if not User.objects.filter(is_superuser=True).exists():
        User.objects.create_superuser(username='admin', password='admin', email='')


class PregCheckConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ranch_tools.preg_check'

    def ready(self):
        print('app ready - create super user if needed.')
        post_migrate.connect(create_superuser, sender=self)

# List of validators needed
# 1. Cow has to have a valid birth year
# 2. There cannot be a lone recheck in a breeding season
# 2. There cannot be a recheck with a None cow
# 3. Cow has to have a valid ear tag
# 4. There cannot be duplicate ear tag birth year combos
# 5. There cannot be duplicate eids
