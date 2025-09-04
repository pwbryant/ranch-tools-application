import os
import sys
from django.core.management import execute_from_command_line

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.base')  # Update with your settings module path
import django
django.setup()

from ranch_tools.preg_check.models import CurrentBreedingSeason

def update_breeding_season(year):
    try:
        # Validate the year
        year = int(year)
        if year < 1900 or year > 2100:
            raise ValueError("Year must be between 1900 and 2100.")

        # Load or create the CurrentBreedingSeason object
        current_season, created = CurrentBreedingSeason.objects.get_or_create(id=1)
        current_season.breeding_season = year
        current_season.save()

        if created:
            print(f"Created a new CurrentBreedingSeason with breeding_season set to {year}.")
        else:
            print(f"Updated CurrentBreedingSeason to breeding_season {year}.")
    except ValueError as e:
        print(f"Invalid year: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_breeding_season.py <year>")
        sys.exit(1)

    year = sys.argv[1]
    update_breeding_season(year)