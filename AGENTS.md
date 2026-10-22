# AGENTS.md — Open Weather Application

Instructions for AI coding agents and human contributors working in this repository.

**Sources of truth, in order:**
1. [`REQUIREMENTS.md`](REQUIREMENTS.md) — FR-1 to FR-12 and all NFR IDs.
2. [`docs/diagrams/`](docs/diagrams/) — UML: `use-case`, `class`, `activity`, `sequence`, `state-machine` (`.mmd` source + `.png` export).
3. This file — how to build it.

If code, diagrams, and requirements disagree, stop and flag the conflict. Do not silently
change a requirement to fit the code. When a requirement changes, update the affected
diagram `.mmd` files and re-export the PNGs in the same change.

---

## 1. Technology Stack

| Layer           | Choice                                                                  |
|-----------------|-------------------------------------------------------------------------|
| Language        | Python 3.14 (`.python-version`)                                         |
| Framework       | Django 6.1 (`config/` project, `accounts/` and `weather/` apps)         |
| Database        | SQLite (`db.sqlite3`, git-ignored)                                       |
| Frontend        | Django templates, HTML5, CSS3, plain JavaScript (ES2020+, no build step) |
| Charts / map    | Chart.js and Leaflet, exact pinned versions, vendored under `static/vendor/` |
| HTTP client     | `requests` (server side only)                                           |
| Config          | `python-dotenv` loads `.env` in `config/settings.py`                    |
| Cache           | Django cache framework (`LocMemCache` in development and tests)        |
| Package manager | `uv` (`pyproject.toml`, `uv.lock`)                                      |

Runtime dependencies are `django`, `python-dotenv`, and `requests`. **Do not add a Python
package or a JavaScript library without asking first.** Rate limiting, caching, and
retries are built on Django and `requests`, not third-party packages.

Common commands:

```bash
uv sync                                  # install dependencies
uv run python manage.py makemigrations   # after any model change
uv run python manage.py migrate
uv run python manage.py test             # full test suite (must pass offline)
uv run python manage.py runserver
```

The `src/open_weather_app/` package is leftover `uv init` scaffolding. Do not put
application code there.

---

## 2. Architecture

```
Browser (HTML/CSS/JS)
   │  same-origin requests only; never calls OpenWeather directly
   ▼
Django views (thin)  ──►  SQLite (User, UserProfile, FavoriteLocation)
   │
   ▼
Services:  LocationSearchService, WeatherService
   │              │
   │              ▼
   │         WeatherCache (Django cache)
   ▼
OpenWeatherClient (the only module that talks to OpenWeather)
   │
   ▼
OpenWeather API (Geocoding, Current Weather 2.5, Forecast 2.5, Map tiles, optional One Call 3.0)
```

Rules:
- **Views stay thin:** parse and validate input, call a service, choose a template or response.
  No raw HTTP calls, no cache keys, and no JSON parsing in views.
- **Services return domain objects** (`Location`, `CurrentWeather`, `Forecast`,
  `ForecastEntry`, `DailySummary`). These are plain `@dataclass` value objects, not models.
- **`OpenWeatherClient` is the single gateway** (NFR-REL-1). It owns the API key, the
  5-second timeout, one retry on transient errors, error mapping, and logging.
- **Class, method, and attribute names follow `docs/diagrams/class.mmd`.** If you need a
  new public method or class, update the class diagram too.

### Planned layout

```
config/
  settings.py            # env loading, cache, logging, OpenWeather settings
  urls.py                # includes accounts.urls and weather.urls
templates/
  base.html              # landmarks, skip link, nav, aria-live region, messages
  404.html, 500.html     # NFR-FT-7
static/
  css/site.css
  vendor/chartjs/, vendor/leaflet/
accounts/
  models.py              # UserProfile, TemperatureUnit
  forms.py               # RegistrationForm
  views.py, urls.py
  preferences.py         # get_unit(request) / set_unit(request, unit)
  templates/accounts/
  tests/
weather/
  models.py              # FavoriteLocation
  services/
    client.py            # OpenWeatherClient
    exceptions.py        # OpenWeatherError, RateLimitError, AuthenticationError, ServiceUnavailableError
    cache.py             # WeatherCache
    search.py            # LocationSearchService
    weather.py           # WeatherService
    domain.py            # Location, CurrentWeather, Forecast, ForecastEntry, DailySummary, MapLayer
  views.py, urls.py
  templates/weather/
  static/weather/js/     # charts.js, map.js, geolocation.js, favorites.js
  tests/
    fixtures/            # recorded OpenWeather JSON responses
```

You need to add `BASE_DIR / "templates"` to `TEMPLATES["DIRS"]` and `STATICFILES_DIRS`
when the project-level folders are created.

### Planned URLs

The `/search/`, `/weather/`, `/weather/tiles/...`, `POST /favorites/`, and
`/accounts/login/?next=` paths appear in `sequence.mmd`. Keep them in sync if they change.

| Method | Path                                       | Purpose                                     | Req          |
|--------|--------------------------------------------|---------------------------------------------|--------------|
| GET/POST | `/accounts/register/`                    | Registration                                | FR-1         |
| GET/POST | `/accounts/login/`                       | Login (validated `next`)                    | FR-2         |
| POST   | `/accounts/logout/`                        | Logout                                      | FR-2         |
| GET/POST | `/accounts/preferences/`                 | Unit preference page                        | FR-3         |
| POST   | `/preferences/unit/`                       | Unit toggle from the dashboard              | FR-3         |
| GET    | `/search/?q=`                              | City / postal search, disambiguation list   | FR-4/5/6     |
| GET    | `/weather/?lat=&lon=`                      | Dashboard (current, forecast, charts, map)  | FR-8/9/12    |
| GET    | `/weather/reverse/?lat=&lon=`              | Device geolocation → dashboard redirect    | FR-7         |
| GET    | `/weather/map/`                            | Full-page map                               | FR-12        |
| GET    | `/weather/tiles/<layer>/<z>/<x>/<y>/`      | Server-side tile proxy (adds API key)       | FR-12        |
| GET    | `/favorites/`                              | Favorites list                              | FR-10        |
| POST   | `/favorites/`                              | Add favorite (fetch or form POST)           | FR-11        |
| POST   | `/favorites/<id>/delete/`                  | Remove favorite                             | FR-10        |

---

## 3. App Responsibilities

### `accounts` — identity and preferences
- **FR-1 Registration:** a `RegistrationForm` with username, email, password, and
  confirmation. Usernames are unique case-insensitively. Passwords go through
  `AUTH_PASSWORD_VALIDATORS`. On success the user is logged in automatically, redirected
  home, and shown a success message.
- **FR-2 Login/logout:**
  - Use Django's auth views or thin wrappers around them.
  - Show the generic error "Invalid username or password".
  - Validate `next` with `url_has_allowed_host_and_scheme` (NFR-SEC-8).
  - Logout is POST only.
  - Rate-limit login to 5 failures per 5 minutes per IP and per username, using a
    cache-backed counter (NFR-SEC-7).
- **FR-3 Unit preference:**
  - `UserProfile` (one-to-one with `User`) stores `temperature_unit`, which is a
    `TemperatureUnit` (`IMPERIAL` | `METRIC`). The default is `IMPERIAL`.
  - Anonymous users keep the unit in the session.
  - `accounts.preferences.get_unit(request)` is the only way the rest of the code reads
    the unit.
  - Create the profile lazily with `get_or_create`, or with a `post_save` signal. Pick one
    and test it.
- **Owns:** `User` (Django built-in), `UserProfile`, `TemperatureUnit`.

### `weather` — locations, weather data, favorites, map
- **FR-4/5 Search:**
  - `LocationSearchService.search(query)` trims the query and rejects empty input before
    any API call.
  - It detects postal codes with `is_postal_code`. Postal codes go to `geocode_zip` with
    country defaulting to `US`; everything else goes to `geocode_direct(limit=5)`.
- **FR-6 Disambiguation:**
  - 0 matches: show "No locations found" or "Postal code not found".
  - 1 match: 302 redirect to the dashboard.
  - More than 1 match: list up to 5 results in API order (name, state, country, and
    coordinates to 2 decimals), each with a save button.
- **FR-7 Geolocation:**
  - Handled in `geolocation.js`. Request location only on a button click, with a
    10-second timeout. Hide the button when geolocation isn't supported or the page
    isn't a secure context.
  - The server reverse-geocodes the coordinates through `LocationSearchService.reverse`.
- **FR-8 Current weather:**
  - `WeatherService.current()` returns `CurrentWeather`, including `wind_compass()` and
    `uv_category()`.
  - `uv_index` is `None` unless One Call 3.0 is enabled (`OPENWEATHER_ENABLE_ONECALL`).
    When it is `None`, the template shows "UV index unavailable".
  - Show sunrise and sunset in the location's timezone, using the `timezone` offset from
    the API response.
- **FR-9 Forecast:**
  - `WeatherService.forecast()` returns `Forecast` with 3-hour `ForecastEntry` items and
    `daily_summaries()` (up to 6 calendar days).
  - `chart_data()` produces JSON for the page. Embed it with `json_script`; never build
    JSON by string concatenation in templates.
  - Every chart also gets an accessible data table.
- **FR-10/11 Favorites:**
  - `FavoriteLocation` belongs to a `User`. Round coordinates to 4 decimals before saving.
    Enforce `UniqueConstraint(user, latitude, longitude)` and at most 20 per user
    (`MAX_PER_USER`).
  - Every query filters by `request.user`. Requests for another user's favorite return 404.
  - The add endpoint returns `201` (created), `409` ("Already in favorites"), or `400`
    ("Favorites limit reached") for `fetch`. It redirects with a message for the no-JS
    form POST.
  - An anonymous POST redirects to login with `next`.
- **FR-12 Map:**
  - Leaflet map with `MapLayer` overlays (`TEMPERATURE`, `PRECIPITATION`, `CLOUDS`,
    `WIND`) and a legend for each layer.
  - Tiles go through `/weather/tiles/...` → `OpenWeatherClient.map_tile`. Validate
    `layer` against `MapLayer` and `z`/`x`/`y` as bounded integers, so the proxy can't be
    used to fetch arbitrary URLs.
  - Logged-in users also see markers for their favorites.
- **Owns:** `FavoriteLocation`, all services, value objects, `MapLayer`, and exceptions.

### Behavior that must match the diagrams
- **`activity.mmd`:**
  - Decision order: empty? → postal pattern? → cache hit? → request succeeded? → match count.
  - Then fresh data? → stale cache exists? → UV available?
- **`state-machine.mmd`:**
  - Every state needs a visible UI representation: Idle, InvalidInput, NoResults,
    AwaitingSelection, LocationUnavailable, LoadingWeather (loading indicator after
    300 ms, NFR-USE-4), DisplayingWeather, DisplayingStale (age notice), SearchError.
  - Changing the unit redraws values and charts for the same location (FR-3 AC-5). A
    page reload for the same location is acceptable; asking the user to search again
    is not.
- **`sequence.mmd`:**
  - The dashboard makes at most one call per endpoint per page load (NFR-PERF-3): Current
    Weather, then Forecast, plus One Call only if enabled.
  - If the forecast fails, the current weather still renders (NFR-FT-3).

---

## 4. Test-Driven Development: Red → Green → Refactor

All production code is written test-first. For every acceptance criterion:

1. **Red:** write one small failing test that names the requirement, for example
   `test_fr6_ac3_shows_at_most_five_results`. Run it and **confirm it fails for the
   expected reason** (an assertion failure, not an import error or typo).
2. **Green:** write the minimum production code that makes the test pass. Don't add
   untested behavior. Run the full suite.
3. **Refactor:** with all tests green, clean up duplication, naming, and structure,
   with no change in behavior. Run the full suite again.
4. Repeat for the next acceptance criterion. Commit at green, after the refactor step.

Rules:
- **Traceability:** every FR acceptance criterion has at least one test, named or
  docstring-tagged with its ID (`FR-10 AC-5`). NFRs that can be tested (timeouts, cache
  TTLs, CSRF, authorization, error handling, `alt` text, labels) get tests too.
- **Test layers:**
  - *Unit tests* for services, value objects, and forms.
  - *View tests* using `django.test.Client`, covering status codes, templates, context,
    and messages.
  - *Model tests* for constraints.
- **Don't weaken tests:** never delete or loosen a test just to make it pass. If a test
  is wrong, fix it and explain why in the commit message.
- **Organization:** tests live in `accounts/tests/` and `weather/tests/` packages (replace
  the generated `tests.py` files), one module per area: `test_registration.py`,
  `test_client.py`, `test_search.py`, `test_favorites.py`, and so on.
- **JavaScript:** progressive enhancement means core flows are testable from the server
  side (NFR-FT-6). Keep JS logic in small pure functions (unit formatting, compass
  conversion, chart dataset building) so they can be tested if a JS test runner is added
  later. Ask before adding one.

---

## 5. Offline, Mocked OpenWeather Testing

**The test suite must never make real network calls and must pass with no internet and
no real API key** (NFR-REL-4).

- **Mock at the boundary:**
  - Patch the `requests` call inside `weather/services/client.py`, e.g.
    `@patch("weather.services.client.requests.Session.request")`, or inject a fake session
    into `OpenWeatherClient`.
  - Service and view tests may instead patch `OpenWeatherClient` methods.
- **Network guard:**
  - Provide a shared base class or mixin (e.g. `weather/tests/base.py: OfflineTestCase`)
    that makes any unmocked network access fail loudly.
  - It patches `requests.Session.request` / `socket.socket.connect` to raise an
    `AssertionError`.
  - All tests that touch weather code inherit from it.
- **Fixtures:**
  - Store representative JSON in `weather/tests/fixtures/`: `geocode_direct_multiple.json`,
    `geocode_direct_empty.json`, `geocode_zip.json`, `reverse_geocode.json`,
    `current_weather.json`, `forecast_5day.json`, `onecall_uvi.json`, and a tiny
    `tile.png`.
  - Fixtures must contain no real API keys. Keep them small and realistic, matching the
    documented response shape.
- **Fake settings:** tests run with
  `@override_settings(OPENWEATHER_API_KEY="test-key")`. Assert that `"test-key"` never
  appears in rendered HTML, JS context, or log output (NFR-SEC-1, NFR-REL-2).
- **Error paths to cover:**
  - `requests.Timeout`
  - `ConnectionError`, retried once and then raised (NFR-FT-5)
  - HTTP 401 → `AuthenticationError`, HTTP 429 → `RateLimitError`,
    5xx → `ServiceUnavailableError` (NFR-FT-4)
  - Malformed JSON
  - An empty result list
- **Cache in tests:**
  - Use `LocMemCache` and call `cache.clear()` in `setUp`.
  - Test hits, misses, TTL values, stale fallback (NFR-FT-2), and key composition
    (endpoint + coordinates rounded to 2 decimals + units).
  - Use `unittest.mock.patch` on `time`/`timezone.now`, or fixed TTL assertions, rather
    than sleeping.
- **Time:** freeze or inject `now` for sunrise/sunset, "last updated", and stale-age
  formatting.

---

## 6. Security Rules

- **`.env` and secrets (NFR-SEC-1):**
  - `OPENWEATHER_API_KEY` and `DJANGO_SECRET_KEY` come only from the environment, loaded
    by `python-dotenv` in `config/settings.py`.
  - Never commit `.env` (it is in `.gitignore`). Never print, log, echo, or paste its
    values.
  - Commit a `.env.example` with placeholder values only.
  - Read the key from `settings` inside `OpenWeatherClient`, and nowhere else.
- **Backend-only API calls:**
  - The browser never contacts `api.openweathermap.org` or `tile.openweathermap.org`.
  - The API key never appears in templates, JavaScript, `json_script` data, URLs sent to
    the client, or error messages.
  - Map tiles go through the Django proxy.
  - Strip the key from any logged URL; log the endpoint path and status code only.
- **CSRF (NFR-SEC-3):**
  - `CsrfViewMiddleware` stays enabled. Never use `@csrf_exempt`.
  - Every state-changing action is POST with `{% csrf_token %}`: register, login, logout,
    add/remove favorite, change unit.
  - JavaScript `fetch` calls read the token from the `csrftoken` cookie or a template
    value and send it as `X-CSRFToken`.
  - Use `@require_POST` / `@require_http_methods` on mutating views.
- **Authorization (NFR-SEC-4):**
  - `@login_required` on favorites and preferences views.
  - Look up objects with `get_object_or_404(FavoriteLocation, pk=pk, user=request.user)`.
- **Input and output (NFR-SEC-5):**
  - Validate everything server side with Django forms or explicit checks: `lat` in
    [-90, 90], `lon` in [-180, 180], query length ≤ 100, tile parameters bounded.
  - Rely on template auto-escaping. Never use `|safe` or `mark_safe` on user or API data.
  - Use the ORM only, no raw SQL.
- **Settings (NFR-SEC-6):**
  - `DEBUG` and `ALLOWED_HOSTS` come from the environment, with `DEBUG=False` by default
    outside development.
  - Set `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` when served over HTTPS.
  - `SESSION_COOKIE_HTTPONLY = True`.
- **Passwords:** use Django's default hasher only (NFR-SEC-2).

---

## 7. Caching Rules (NFR-CACHE)

- All caching goes through `WeatherCache`. Services never call `django.core.cache`
  directly.
- **Keys:** `WeatherCache.make_key(endpoint, lat, lon, units)`, with coordinates rounded
  to 2 decimals. Geocode keys use the normalized (trimmed, lower-cased) query plus
  country.
- **TTLs** are configured in `settings.py`, not hard-coded:

  ```python
  WEATHER_CACHE_TTL = {"geocode": 60 * 60 * 24, "current": 60 * 10, "forecast": 60 * 30}
  ```

- **Stale fallback:**
  - Store each value with its `retrieved_at` timestamp.
  - Keep a longer-lived stale copy (e.g. a second key holding the last good response) so
    `get_stale()` can serve it when the API fails.
  - The UI shows the data's age (`is_stale`, NFR-CACHE-4, NFR-FT-2).
  - Map tiles may be cached briefly or not at all. Never cache error responses.
- **Units:** the cache key includes units, so °F and °C entries are separate.
- **Favorites page (NFR-PERF-4):** reuse cached current weather for each favorite. Load
  favorites with a single query (no N+1, NFR-PERF-6).
- **Rate limits (NFR-CACHE-5):** caching must keep usage within OpenWeather free-tier
  limits.

### OpenWeather settings (`config/settings.py`)

```python
OPENWEATHER_API_KEY = os.environ["OPENWEATHER_API_KEY"]
OPENWEATHER_TIMEOUT = 5          # seconds, NFR-PERF-2
OPENWEATHER_RETRIES = 1          # NFR-FT-5
OPENWEATHER_ENABLE_ONECALL = os.environ.get("OPENWEATHER_ENABLE_ONECALL", "false").lower() == "true"
```

---

## 8. Coding Standards

- **Python style:**
  - PEP 8, 4-space indentation, lines ≤ 100 characters, double quotes (match
    `config/settings.py`).
  - Type hints on all public functions and methods. Short docstrings on public classes and
    services; reference the requirement ID where it helps (`"""FR-6: ..."""`).
- **Naming:** follow the class diagram exactly. Use `snake_case` functions, `PascalCase`
  classes, and `UPPER_CASE` constants.
- **Django conventions:**
  - Thin views; logic in services, forms, and model methods.
  - `TextChoices` for `TemperatureUnit`; `Enum` for `MapLayer`.
  - `DecimalField` for favorite coordinates.
  - `reverse()`/`{% url %}` instead of hard-coded paths.
  - Messages framework for user feedback.
  - `transaction.atomic` for favorite writes (NFR-REL-3).
- **Migrations:** every model change ships with its migration (NFR-REL-5). Never edit an
  applied migration.
- **Errors:**
  - Catch `OpenWeatherError` subclasses at the service or view boundary and render a
    friendly message. Never let them become a 500.
  - Don't catch bare `Exception` except at a single, logged boundary.
- **Logging:** use `logging.getLogger(__name__)`. Never log secrets or full request URLs
  that contain the key.
- **Templates:**
  - Extend `base.html`.
  - Use semantic landmarks, one `<h1>` per page, `<label>` for every control, and
    `aria-describedby` for errors.
  - Weather icons get `alt` text from the API description.
- **CSS:**
  - Mobile-first and responsive from 320 px to 1920 px.
  - Contrast ≥ 4.5:1, visible `:focus-visible` styles, and `prefers-reduced-motion`
    respected.
- **JavaScript:**
  - `defer`-loaded modules in `weather/static/weather/js/`.
  - Progressive enhancement: every feature has a server-rendered fallback or a visible
    notice.
  - No inline event handlers. Announce results through the shared `aria-live` region.
- **Accessibility:** WCAG 2.2 AA. Charts have a text summary and a data table; the map
  has a text alternative and keyboard controls (NFR-AC-1..10).
- **Commits:** small, one behavior per commit, test and code together, with messages that
  reference the requirement (`FR-10: enforce per-user favorite uniqueness`).

---

## 9. Implementation Phases

Do phases in order. A phase is done only when all of its acceptance criteria have passing
tests, the full suite passes offline, and the diagrams still match the code.

| Phase | Scope | Requirements |
|-------|-------|--------------|
| **0. Foundations** | Settings: env-based `DEBUG`/`ALLOWED_HOSTS`, cache, logging, `TEMPLATES["DIRS"]`, static, OpenWeather settings. Add `.env.example`, `base.html` (landmarks, skip link, nav, live region), custom 404/500 pages, test packages, the `OfflineTestCase` network guard, and fixtures folder. | NFR-SEC-1, NFR-SEC-6, NFR-FT-7, NFR-REL-4/5, NFR-AC-2 |
| **1. Accounts** | Registration, login/logout, `next` validation, login rate limiting, `UserProfile` + `TemperatureUnit` model. | FR-1, FR-2, NFR-SEC-2/3/7/8 |
| **2. OpenWeather client and cache** | `OpenWeatherClient`, exception hierarchy, timeout/retry, key-safe logging, `WeatherCache` with TTLs and stale storage, value objects in `domain.py`. | NFR-REL-1/2, NFR-PERF-2, NFR-FT-1/4/5, NFR-CACHE-1..3 |
| **3. Location search** | Search form and view, postal-code detection, city/ZIP geocoding, 0/1/many handling, disambiguation list. | FR-4, FR-5, FR-6 |
| **4. Dashboard: current weather and units** | Dashboard view, `CurrentWeather` metrics, wind compass, UV index with One Call flag and "UV index unavailable" fallback, local-time sunrise/sunset, last-updated/stale notice, unit preference (profile + session) and toggle. | FR-3, FR-8, NFR-CACHE-4, NFR-FT-2 |
| **5. Forecast and charts** | Forecast service, daily summaries, `chart_data()` + `json_script`, Chart.js temperature and precipitation charts, accessible tables, redraw on unit change, partial-failure handling. | FR-9, NFR-FT-3, NFR-AC-7 |
| **6. Device geolocation** | `geolocation.js` (click only, 10 s timeout, support/secure-context check), reverse-geocode endpoint, error messaging. | FR-7 |
| **7. Favorites and bookmarking** | `FavoriteLocation` model + constraint + 20 limit, list/add/remove views, ownership checks, save buttons on results and dashboard, `fetch` + CSRF with no-JS fallback, login redirect for anonymous users, live-region announcements. | FR-10, FR-11, NFR-SEC-4, NFR-REL-3, NFR-PERF-4/6 |
| **8. Interactive map** | Leaflet map page and dashboard panel, layer switcher + legends, validated tile proxy, favorite markers and popups, tile-failure notice, keyboard/text alternative. | FR-12, NFR-AC-8 |
| **9. Hardening** | Accessibility audit (keyboard, contrast, 200 % zoom, screen-reader labels), responsive checks, performance checks against NFR-PERF targets, cross-browser smoke test, README update. | NFR-PERF, NFR-USE, NFR-AC |

---

## 10. Agent Checklist (before finishing any task)

- [ ] Tests were written first, seen failing, then passing; the full suite passes with
      networking disabled.
- [ ] No real OpenWeather calls in tests; no API key or secret in code, templates, JS,
      fixtures, logs, or commits.
- [ ] Every mutating view is POST-only with CSRF; every user-owned query filters by
      `request.user`.
- [ ] OpenWeather is reached only through `OpenWeatherClient`, and cached only through
      `WeatherCache`.
- [ ] Migrations are included for model changes.
- [ ] `REQUIREMENTS.md` and `docs/diagrams/*.mmd` (+ re-exported PNGs) are updated if
      behavior or structure changed.
- [ ] No new dependencies added without approval.
