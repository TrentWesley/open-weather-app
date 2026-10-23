# Open Weather Application

A Django web app for looking up current weather, a 5-day forecast with charts, and
an interactive weather map for any city, US ZIP code or international postal code.
Signed-in users can choose °F or °C and save up to 20 favorite locations.

Weather data comes from the [OpenWeather](https://openweathermap.org/api) APIs. Every
OpenWeather request is made by the server, so the API key never reaches the browser.

- **Requirements:** [`REQUIREMENTS.md`](REQUIREMENTS.md) (FR-1 to FR-12 and the NFRs)
- **Build instructions for contributors and AI agents:** [`AGENTS.md`](AGENTS.md)
- **UML diagrams:** [`docs/diagrams/`](docs/diagrams/)
- **Requirements audit (Phase 9):** [`docs/requirements-audit.md`](docs/requirements-audit.md)
- **Demo script:** [`docs/demo-script.md`](docs/demo-script.md)

---

## Features

| Area | What it does | Req |
|------|--------------|-----|
| Accounts | Register, log in and out. Login is rate-limited and redirects safely. | FR-1, FR-2 |
| Units | °F / °C toggle on the dashboard and a preferences page. Saved to the profile for signed-in users and to the session otherwise. | FR-3 |
| Search | One search box for `Amarillo`, `Amarillo, TX`, `Paris, FR`, `79015` or `SW1A 1AA, GB`. Several matches show a list to choose from. | FR-4, FR-5, FR-6 |
| Use my location | Browser geolocation, requested only on click, with a 10-second timeout. The server looks up the place name and opens the dashboard. | FR-7 |
| Current weather | Temperature, feels like, high/low, conditions with icon, humidity, wind with compass direction, pressure, visibility, cloud cover, UV index (when available), sunrise/sunset in local time, and when the data was last updated. | FR-8 |
| Forecast | Five days of daily summaries plus Chart.js temperature and precipitation charts. Each chart has a text summary and a data table. | FR-9 |
| Favorites | Save from search results or the dashboard, in place with JavaScript or as a normal form without it. The favorites page shows current weather; limit 20, no duplicates. | FR-10, FR-11 |
| Map | Leaflet map with temperature, precipitation, cloud and wind overlays and legends, plus markers for your favorites. Overlay tiles go through a server-side proxy. | FR-12 |

The app keeps working when things fail:
- OpenWeather errors show friendly messages, with separate wording for rate limiting and key problems.
- If OpenWeather is unreachable, the last saved data is shown with its age.
- If one dashboard section fails, the others still render.
- Search, the dashboard and favorites all work without JavaScript.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Language / framework | Python 3.14, Django 6.1 |
| Database | SQLite |
| Front end | Django templates, CSS, plain JavaScript (no build step) |
| Charts / map | Chart.js 4.4.7 and Leaflet 1.9.4, vendored under `static/vendor/` |
| HTTP / config | `requests` (server side only), `python-dotenv` |
| Cache | Django cache framework (`LocMemCache`) |
| Packages | [`uv`](https://docs.astral.sh/uv/) |

The only runtime dependencies are `django`, `python-dotenv` and `requests`.

---

## Getting started

### Prerequisites

- Python 3.14 and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- A free [OpenWeather API key](https://home.openweathermap.org/api_keys). New keys can
  take a short while to activate.
- An internet connection, for OpenWeather and the map's background tiles

### Setup

```bash
git clone <your-repo-url> open-weather-app
cd open-weather-app
uv sync                          # creates .venv and installs dependencies
cp .env.example .env             # Windows PowerShell: Copy-Item .env.example .env
```

Edit `.env`:

1. Set `OPENWEATHER_API_KEY` to your key.
2. Set `DJANGO_SECRET_KEY` to a long random value. You can generate one with:
   ```bash
   uv run python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```
3. For local development, set `DJANGO_DEBUG=true`. With `DEBUG` off, `runserver`
   doesn't serve CSS and JavaScript.

Then create the database and start the server:

```bash
uv run python manage.py migrate
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

> **Keep `.env` private.** It is git-ignored; never commit it or paste its values
> anywhere. `.env.example` contains placeholders only.

### Configuration

All settings come from environment variables, loaded from `.env`.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENWEATHER_API_KEY` | yes | — | OpenWeather key, used only on the server |
| `DJANGO_SECRET_KEY` | yes | — | Django signing key (use 50+ random characters) |
| `DJANGO_DEBUG` | no | `false` | `true` for local development only |
| `DJANGO_ALLOWED_HOSTS` | no | `localhost,127.0.0.1` | Comma-separated host names |
| `DJANGO_SECURE_COOKIES` | no | opposite of `DJANGO_DEBUG` | Send session and CSRF cookies over HTTPS only |
| `OPENWEATHER_ENABLE_ONECALL` | no | `false` | `true` only with a One Call 3.0 subscription (enables UV index) |
| `MAP_BASE_TILE_URL` | no | OpenStreetMap | Background map tiles. These need no key. |
| `MAP_BASE_ATTRIBUTION` | no | © OpenStreetMap contributors | Attribution shown on the map |
| `MAP_BASE_MAX_ZOOM` | no | `18` | Maximum map zoom |

Cache lifetimes are set in `config/settings.py` (`WEATHER_CACHE_TTL`):
- current weather: 10 minutes
- forecast: 30 minutes
- geocoding: 24 hours

---

## Running the tests

```bash
uv run python manage.py test     # 582 tests, about 75 s
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

The tests make **no network calls** and need **no real API key**:
- OpenWeather responses come from recorded fixtures in `weather/tests/fixtures/`.
- A shared base class (`weather/tests/base.py`) makes any unmocked network access fail
  the test.
- Tests run with the placeholder key `test-key` and check that it never appears in
  pages, JSON or logs.

Tests are named after the requirement they cover, for example
`test_fr10_ac5_duplicate_returns_409_already_in_favorites` or
`test_nfr_sec4_another_users_favorite_is_404_and_untouched`. Every FR acceptance
criterion has at least one test. See [`docs/requirements-audit.md`](docs/requirements-audit.md).

| Package | Tests | Covers |
|---------|-------|--------|
| `accounts/tests/` | 80 | Registration, login, rate limiting, unit preferences |
| `weather/tests/` | 442 | Client, cache, services, search, dashboard, forecast, geolocation, favorites, map, tile proxy |
| `config/tests/` | 60 | Settings, `.env` handling, templates, and Phase 9 audits (contrast, keyboard, page weight, migrations) |

There is no JavaScript test runner. The scripts keep their logic in small pure functions
so one could be added later. Until then, structural tests check them, and they were
exercised in headless Chrome and Edge.

---

## How it works

```
Browser ──(same-origin only)──► Django views (thin)
                                   │
                                   ├─► LocationSearchService ─┐
                                   ├─► WeatherService ────────┼─► WeatherCache (Django cache)
                                   │                          │
                                   │                          └─► OpenWeatherClient ─► OpenWeather API
                                   └─► SQLite (users, profiles, favorites)
```

- **`OpenWeatherClient`** (`weather/services/client.py`) is the only code that talks to
  OpenWeather. It holds the key, uses a 5-second timeout, retries transient failures
  once, maps 401/429/5xx to distinct exceptions, and logs only the endpoint and status code.
- **`WeatherCache`** keys entries by endpoint, coordinates rounded to 2 decimals, and
  units. It keeps a longer-lived stale copy for when OpenWeather is unavailable.
- **Map tiles:** the browser loads weather overlays from
  `/weather/tiles/<layer>/<z>/<x>/<y>/`. The server checks the layer name and tile
  numbers, then fetches the tile with the key added. The background map comes from
  OpenStreetMap, which needs no key, and follows its
  [tile usage policy](https://operations.osmfoundation.org/policies/tiles/): the
  browser sends the site's origin as the Referer, and the map shows attribution.

### Main URLs

| Path | Purpose |
|------|---------|
| `/` | Home and search |
| `/search/?q=` | Search results and choosing between matches |
| `/weather/?lat=&lon=` | Dashboard: current weather, forecast, charts, map panel |
| `/weather/map/?lat=&lon=` | Full-page map. Without coordinates it shows your favorites. |
| `/weather/reverse/?lat=&lon=` | "Use my location" → dashboard |
| `/favorites/` | Your favorites (GET); add a favorite (POST) |
| `/accounts/register/`, `/accounts/login/`, `/accounts/preferences/` | Accounts |

### Project layout

```
config/            settings, URLs, project-level tests
accounts/          registration, login, UserProfile and unit preference
weather/
  services/        OpenWeatherClient, WeatherCache, search and weather services, value objects
  models.py        FavoriteLocation
  maps.py          map configuration (markers, legends, base layer)
  static/weather/js/  loading, charts, geolocation, favorites, map scripts
  templates/weather/  dashboard, search, favorites, map
  tests/           tests and recorded OpenWeather fixtures
templates/         base layout, 404 and 500 pages
static/            site.css and the vendored Chart.js and Leaflet
docs/              UML diagrams, requirements audit, demo script
```

(`src/open_weather_app/` is leftover `uv init` scaffolding and isn't used.)

---

## Security

- The OpenWeather key and Django secret key come from `.env` only. They are never
  committed, logged, rendered in pages or JSON, or sent to the browser. A scan of the
  full git history found neither.
- All state-changing actions (register, login, logout, unit change, add or remove a
  favorite) are POST requests with CSRF protection. JavaScript `fetch` calls send the
  `X-CSRFToken` header.
- Every favorites query is limited to the signed-in user, so another user's favorite
  returns a 404.
- After 5 failed logins in 5 minutes, further attempts from that IP address or for that
  username are refused for a while. Login `next` redirects must stay on this site.
- Input is validated on the server: coordinate ranges, query length, tile parameters.
  Templates rely on auto-escaping, and there is no `|safe` or `mark_safe` on user or
  API data.

`manage.py check --deploy` with `DJANGO_DEBUG=false` reports only the HSTS and
HTTPS-redirect warnings (W004, W008), which apply to an HTTPS deployment. Deployment
is out of scope (REQUIREMENTS §5). It also warns (W009) if `DJANGO_SECRET_KEY` is
short, so use a generated key.

## Accessibility

- **Target:** WCAG 2.2 AA. An axe-core audit of every page, signed in and out, in light
  and dark themes, finds no violations.
- **Structure:** landmarks, a skip link, one `<h1>` per page, and labeled form fields
  with linked error messages.
- **Contrast and focus:** colors meet contrast minimums in both themes (checked by a
  test), and focus is always visible.
- **Charts and map:** charts have text summaries and data tables. The map has an
  accessible name, keyboard controls (arrow keys, +/−, Enter, Escape) and a text list of
  its places.
- **Live updates:** unit changes, favorite saves and errors are announced through an
  ARIA live region.
- **Layout and motion:** responsive from 320 px to 1920 px with no horizontal scrolling,
  and animations respect `prefers-reduced-motion`.

---

## UML diagrams

Mermaid sources (`.mmd`) and PNG exports are in [`docs/diagrams/`](docs/diagrams/):

| Diagram | Shows |
|---------|-------|
| [Use case](docs/diagrams/use-case.png) | Actors and use cases, FR-1 to FR-12 |
| [Class](docs/diagrams/class.png) | Models, value objects, services, client, cache, exceptions |
| [Activity](docs/diagrams/activity.png) | Location search, geolocation and dashboard loading |
| [Sequence](docs/diagrams/sequence.png) | Search, dashboard, map tiles, bookmarking |
| [State machine](docs/diagrams/state-machine.png) | UI states of the weather search |

If you edit a `.mmd` file, re-export its PNG in the same change. For example, use the
[Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) or <https://mermaid.live>.

## Known limitations

See [`docs/requirements-audit.md`](docs/requirements-audit.md#remaining-limitations).
In short:
- Built and demonstrated locally; HTTPS deployment is out of scope.
- The UV index needs a paid One Call 3.0 subscription. On the free plan the dashboard
  shows "UV index unavailable".
- OpenStreetMap's tile servers allow light, interactive use only. Busier deployments
  should set `MAP_BASE_TILE_URL` to another provider.
- Cross-browser testing covered Chrome and Edge. Firefox, Safari and screen readers
  still need manual checks.

## Credits

- Weather data and map overlays: [OpenWeather](https://openweathermap.org/)
- Background map: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
- [Leaflet](https://leafletjs.com/) (BSD-2-Clause) and [Chart.js](https://www.chartjs.org/)
  (MIT). License files are next to the vendored copies.

Author: Trent Wesley
