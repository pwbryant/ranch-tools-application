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

from ranch_tools.preg_check.models import (  # noqa: E402
    Cow,
    CurrentBreedingSeason,
    PregCheck,
)


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
def cow(transactional_db):
    cow = Cow.objects.create(ear_tag_id='TEST001', birth_year=2019)
    yield cow


@pytest.fixture
def cow_with_pregchecks(cow, transactional_db):
    """Create a cow with a couple of previous pregchecks for the test to find.

    Yields a dict with the created ``cow`` and its ``pregchecks`` so the test can
    assert against known values (ear tag, breeding seasons, etc.).

    Depends on ``transactional_db`` (not the plain ``db`` fixture) because the
    ``live_server`` runs in a separate thread and can only see committed data.
    pytest-django flushes the test database between tests, so no manual teardown
    is needed.
    """

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


def nav_pregchecks(live_server, driver):
    driver.get(f'{live_server.url}/pregchecks')


def search_cow(cow, driver):
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

    # The search submits a plain GET form, so the whole page reloads. Wait for
    # the old page to go stale before locating elements on the reloaded page,
    # otherwise references grabbed mid-navigation raise StaleElementReference.
    WebDriverWait(driver, 10).until(EC.staleness_of(search_button))


def test_animal_search_check_previous_pregchecks(live_server, driver, cow_with_pregchecks):
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


def test_submit_pregchecks(live_server, driver, cow): 

    nav_pregchecks(live_server=live_server, driver=driver)

    search_cow(cow, driver)

    # Enter date. check_date is a native <input type="date">, whose value must
    # be set in ISO (YYYY-MM-DD) format; send_keys with slashes is unreliable and
    # locale-dependent, so set the value via JS and fire a change event.
    date_input = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.ID, 'id_check_date'))
    )
    driver.execute_script(
        "arguments[0].value = arguments[1];"
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
        date_input,
        '2026-08-01',
    )

    # Assert ear tag id is populated
    ear_tag_input = driver.find_element(By.ID, 'id_pregcheck_ear_tag_id')
    assert ear_tag_input.get_attribute('value') == cow.ear_tag_id

    # Select Pregnant radio option
    radio_is_preg_true = driver.find_element(By.ID, 'id_is_pregnant_0')
    radio_is_preg_true.click()

    # Assert no pregchecks prior to submission
    assert PregCheck.objects.filter(cow=cow).count() == 0

    submit_button = driver.find_element(By.ID, 'pregcheck-form-submit-btn')
    submit_button.click()

    # wait until page reloads to continut testing
    WebDriverWait(driver, 10).until(EC.staleness_of(submit_button))

    assert PregCheck.objects.filter(cow=cow).count() == 1


def test_click_previous_pregcheck_and_edit_pregcheck(driver, live_server, cow_with_pregchecks):
    # The "Previous Pregchecks" list only shows pregchecks for the current
    # breeding season, so align it with one of the fixture's pregchecks (2022),
    # otherwise the table renders empty and there is no row to click.
    CurrentBreedingSeason.objects.update_or_create(
        pk=1, defaults={'breeding_season': 2022}
    )

    nav_pregchecks(live_server, driver)

    pregchecks = cow_with_pregchecks['pregchecks']
    pregcheck = pregchecks[-1]

    # The list is built by an async fetch on page load and is collapsed by
    # default. Wait for its toggle icon, then click it to expand the section.
    toggle_icon = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '#previous-pregcheck-content .toggle-icon')
        )
    )
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', toggle_icon)
    toggle_icon.click()

    # Once expanded, click the first row of the previous-pregcheck table.
    row = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '#pregcheck-entries-table tbody tr')
        )
    )
    driver.execute_script('arguments[0].scrollIntoView({block: "center"});', row)
    row.click()

    # Clicking a row calls populateEditModal(), which displays the edit modal.
    modal = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, 'edit-modal'))
    )
    assert modal.is_displayed()

    # change check date to check edit functionality
    breeding_season_input = driver.find_element(By.ID, 'edit-breeding-season')
    current_value = breeding_season_input.get_attribute('value')
    assert current_value == str(pregcheck.breeding_season)

    new_breeding_season = 2023
    # clear() first: send_keys appends, so without it the field would become
    # "20222023" rather than the new value.
    breeding_season_input.clear()
    breeding_season_input.send_keys(str(new_breeding_season))

    submit_button = driver.find_element(By.ID, 'edit-pregcheck-submit-btn')
    submit_button.click()

    # wait until page reloads to continut testing
    WebDriverWait(driver, 10).until(EC.staleness_of(submit_button))

    updated_pregcheck = PregCheck.objects.get(id=pregcheck.id)
    assert updated_pregcheck.breeding_season == new_breeding_season