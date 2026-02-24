from django.apps import AppConfig


class PregCheckConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ranch_tools.preg_check'


# List of validators needed
# 1. Cow has to have a valid birth year
# 2. There cannot be a lone recheck in a breeding season
# 2. There cannot be a recheck with a None cow
# 3. Cow has to have a valid ear tag
# 4. There cannot be duplicate ear tag birth year combos
# 5. There cannot be duplicate eids
