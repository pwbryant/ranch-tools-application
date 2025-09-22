from datetime import datetime
import os

from django.conf import settings
from django.core.management import call_command

from ranch_tools.preg_check.models import CurrentBreedingSeason


class InitialzeDatabaseMixin:
    """Mixin to ensure the database is initialized"""
    def initialze_database_if_needed(self):
        db_path = settings.DATABASES['default']['NAME']
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            call_command('migrate', verbosity=0)
            if CurrentBreedingSeason.objects.count() == 0:
                current_season = CurrentBreedingSeason.load()
                current_season.breeding_season = datetime.now().year
                current_season.save()
