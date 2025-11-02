## Quick orientation for AI coding agents

This repository contains a small Django app (preg_check) bundled with an Electron desktop wrapper. The guidance below highlights the most important, discoverable facts to be productive quickly.

Key entry points
- Django project root: `django_project/` — run management commands from here.
- Electron wrapper: `electron_wrapper/` — `package.json` scripts: `npm start` (dev), `npm run build` (packaging).
- Main Django app code: `django_project/ranch_tools/` (apps: `preg_check`, `database_management`, `users`).

Architecture & runtime
- Backend: Django 4.2 app backed by SQLite at `django_project/db.sqlite3`. Settings live under `django_project/config/settings/` (notably `base.py` and `dev.py`).
- Frontend/desktop: Electron loads a local Django server (http://localhost:8000/pregchecks). See `electron_wrapper/main.js` for how the Electron process starts Python and waits for the server.
- Packaging: `electron_wrapper/package.json` includes `extraResources` that embed the `django_project` and a `python-embed` folder in built artifacts.

Important project-specific patterns
- Singleton pattern: `ranch_tools/preg_check/models.py` defines `SingletonModel` and `CurrentBreedingSeason.load()` — the app expects a single row with `pk=1` to store the active season.
- Cow identity rules: `Cow` has `unique_together = [['ear_tag_id', 'birth_year']]` and `eid` is unique. Code frequently tries to match cows by `ear_tag_id`, `birth_year`, or `rfid` (`eid`). See `ranch_tools/preg_check/views.py:get_matching_cows`.
- Views use classic Django CBVs and JSON endpoints. Search parameters used across views: `search_ear_tag_id`, `search_rfid`, `search_birth_year`. The literal string `all` for `search_ear_tag_id` or `search_rfid` returns all records for the current season.
- DB auto-initialize: `ranch_tools/utils/mixins.py:InitialzeDatabaseMixin` calls `migrate` automatically when the sqlite file is missing/empty; some views call this mixin in `dispatch` (e.g., `PregCheckListView`).

Developer workflows (concrete commands — Windows PowerShell)
- Activate project venv (if present):
  .\v_env\Scripts\Activate.ps1
- Run Django server (development):
  python manage.py runserver --settings=config.settings.dev
  (Electron starts Django with `config.settings.base`; `electron_wrapper/main.js` sets SETTINGS_MODULE = 'config.settings.base')
- Run tests (pytest):
  pytest -q
  Note: `django_project/pytest.ini` sets `DJANGO_SETTINGS_MODULE = config.settings.dev`.
- Electron dev run (in project root):
  cd electron_wrapper; npm install; npm start
- Update breeding season (script):
  cd django_project; python update_breeding_season.py 2025

Debugging and logs
- Electron writes `debug.log` (root) and `electron_wrapper/debug.log` in development. Check those when Electron fails to start Django.
- The Django code sometimes imports `pdb.set_trace()` as `bp` in `preg_check/views.py` — you may encounter interactive breakpoints.

Where to make safe changes (and what to watch for)
- Avoid changing the singleton `CurrentBreedingSeason` semantics; many views call `.load()` and expect `pk=1`.
- When changing model fields, update migrations and be aware `InitialzeDatabaseMixin` will run `migrate` automatically in some flows.
- If you adjust settings module names, update `electron_wrapper/main.js` and `pytest.ini` accordingly.

Quick examples (patterns to follow)
- To find previous preg checks for a season: `PregCheck.objects.filter(breeding_season=<year>).order_by('-check_date', '-id')` (see `PreviousPregCheckListView`).
- To match cows by `ear_tag_id`/`birth_year` OR `eid`: use a Q object OR pattern like `get_matching_cows` in `preg_check/views.py`.

Files worth reading first
- `electron_wrapper/main.js` — desktop start-up and how Django is launched.
- `django_project/config/settings/base.py` — base settings and INSTALLED_APPS.
- `ranch_tools/preg_check/models.py` and `ranch_tools/preg_check/views.py` — core data model and business logic.
- `ranch_tools/utils/mixins.py` — DB auto-init behavior.

If anything here is unclear or you need additional examples (template locations, form field names used in views, or CI details), tell me which area and I will expand this file.
