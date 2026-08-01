import os
import sys

import django
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Make the Django project importable and initialise Django so the fixtures below
# can use the ORM. The `live_server` fixture starts a real HTTP server backed by
# pytest-django's isolated test database, so nothing here touches db.sqlite3.
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..')
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from ranch_tools.preg_check.models import Cow, PregCheck  # noqa: E402


@pytest.fixture
def driver():
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(10)
    yield driver
    driver.quit()


@pytest.fixture
def cow_with_pregchecks(transactional_db):
    """Create a cow with a couple of previous pregchecks for the test to find.

    Yields a dict with the created ``cow`` and its ``pregchecks`` so the test can
    assert against known values (ear tag, breeding seasons, etc.).

    Depends on ``transactional_db`` (not the plain ``db`` fixture) because the
    ``live_server`` runs in a separate thread and can only see committed data.
    pytest-django flushes the test database between tests, so no manual teardown
    is needed.
    """
    cow = Cow.objects.create(ear_tag_id='TEST001', birth_year=2019)
    pregchecks = [
        PregCheck.objects.create(
            cow=cow,
            breeding_season=2021,
            is_pregnant=True,
            comments='Test pregcheck 2021',
        ),
        PregCheck.objects.create(
            cow=cow,
            breeding_season=2022,
            is_pregnant=False,
            comments='Test pregcheck 2022',
        ),
    ]

    yield {'cow': cow, 'pregchecks': pregchecks}


def test_animal_search(live_server, driver, cow_with_pregchecks):
    cow = cow_with_pregchecks['cow']
    pregchecks = cow_with_pregchecks['pregchecks']

    driver.get(f'{live_server.url}/pregchecks')

    # Fill in the search input and submit.
    search_input = driver.find_element(By.ID, 'id_search_ear_tag_id')
    search_input.clear()
    search_input.send_keys(cow.ear_tag_id)

    # Scroll the button into view and wait for it to be clickable before
    # clicking, so a sticky/off-screen layout doesn't intercept the click.
    search_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, 'search-cow-button'))
    )
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', search_button)
    search_button.click()

    # Results load asynchronously, so wait for the table to render.
    table = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, 'cow-previous-pregcheck-table'))
    )
    table_text = table.text

    # Each pregcheck's status (Pregnant / Open) and comments should be shown.
    for pregcheck in pregchecks:
        expected_status = 'Pregnant' if pregcheck.is_pregnant else 'Open'
        assert expected_status in table_text, (
            f'Expected status "{expected_status}" in the pregcheck table, '
            f'but found:\n{table_text}'
        )
        assert pregcheck.comments in table_text, (
            f'Expected comments "{pregcheck.comments}" in the pregcheck table, '
            f'but found:\n{table_text}'
        )


def test_pregchecks_page_has_ranch_tools_header(live_server, driver):
    driver.get(f'{live_server.url}/pregchecks')

    headers = driver.find_elements(By.TAG_NAME, 'a')
    header_texts = [h.text.strip() for h in headers]

    assert 'Ranch Tools' in header_texts, (
        f'Expected an <a> reading "Ranch Tools" but found: {header_texts}'
    )
