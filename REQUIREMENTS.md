# Open Weather Application — Requirements Specification

**Project:** Coding Project 1 — Open Weather Application
**Author:** Trent Wesley
**Status:** Draft (requirements only; no application features implemented yet)
**Last updated:** 2026-10-20

---

## 1. Purpose and Scope

The Open Weather Application is a web application that lets users look up current
weather conditions and multi-day forecasts for any location, using data from the
[OpenWeather](https://openweathermap.org/api) APIs. Registered users can set a
preferred temperature unit, save favorite locations, and view weather on an
interactive map.

This document defines **what** the system must do. It does not prescribe detailed
implementation, and no features described here have been built yet.

### 1.1 Planned Technology Stack

| Layer               | Technology                                                                 |
|---------------------|----------------------------------------------------------------------------|
| Language            | Python 3.14                                                                |
| Web framework       | Django 6.x (apps: `accounts`, `weather`; project package: `config`)        |
| Database            | SQLite (`db.sqlite3`)                                                      |
| Templates / styling | Django templates, HTML5, CSS3                                              |
| Client-side logic   | JavaScript (ES2020+), Chart.js for charts, Leaflet for the map             |
| HTTP client         | `requests` (server-side calls to OpenWeather)                              |
| Configuration       | `python-dotenv` (`.env` holds `OPENWEATHER_API_KEY`, `DJANGO_SECRET_KEY`)  |
| Caching             | Django cache framework (local-memory or database cache backend)            |
| External APIs       | OpenWeather Geocoding (direct + zip), Current Weather, 5-Day/3-Hour Forecast, Weather Map tiles |

### 1.2 Definitions

| Term              | Meaning                                                                       |
|-------------------|-------------------------------------------------------------------------------|
| User              | A person using the application, authenticated or not.                         |
| Registered user   | A user with an account who is logged in.                                      |
| Location          | A place resolved to a name, state/region, country, latitude and longitude.    |
| Favorite          | A location saved by a registered user to their personal list.                 |
| Dashboard         | The weather view for a single location (current conditions + forecast).      |
| Unit preference   | The user's chosen temperature unit: Fahrenheit (imperial) or Celsius (metric).|

---

## 2. Functional Requirements

Each requirement has a user story and testable acceptance criteria (AC).

### FR-1: User Registration

**User story:** As a new visitor, I want to create an account so that I can save my
preferences and favorite locations.

**Acceptance criteria:**
1. A registration page is reachable from the navigation bar for anonymous users.
2. The form collects a username, an email address, a password, and a password confirmation.
3. Usernames must be unique (case-insensitive); a duplicate shows a clear error on the field.
4. Passwords are validated by Django's configured password validators (minimum length,
   not too common, not entirely numeric, not too similar to the username).
5. If the password and confirmation do not match, the form is re-displayed with an
   error and all non-password fields keep their entered values.
6. On success, the account is created with a hashed password, the user is logged in
   automatically, and they are redirected to the home page with a success message.
7. The form is protected by a CSRF token.

### FR-2: User Login and Logout

**User story:** As a registered user, I want to log in and out securely so that my
account and saved data are only available to me.

**Acceptance criteria:**
1. A login page accepts a username and password.
2. Invalid credentials show a generic error ("Invalid username or password") that does
   not reveal which field was wrong.
3. On success, the user is redirected to the page they originally requested (`next`
   parameter, validated to be a same-site URL) or to the home page.
4. The navigation bar shows the logged-in username and a Logout control; anonymous
   users see Login and Register links instead.
5. Logout is performed by a POST request, ends the session, and redirects to the home
   page with a confirmation message.
6. Pages that require authentication (favorites, preferences) redirect anonymous users
   to the login page.

### FR-3: Temperature Unit Preference

**User story:** As a user, I want to choose between Fahrenheit and Celsius so that
temperatures appear in the unit I understand.

**Acceptance criteria:**
1. A unit toggle (°F / °C) is available on the dashboard and on a preferences page.
2. For registered users, the preference is stored in the database (a profile linked
   one-to-one with the user) and applied on every future visit and device.
3. For anonymous users, the preference is stored in the session.
4. The default unit for new users and anonymous visitors is Fahrenheit (imperial).
5. Changing the unit updates all temperatures on the current page — current
   conditions, "feels like", forecast values, and chart axes — without requiring a new search.
6. Wind speed is displayed in units consistent with the selection (mph for imperial,
   m/s or km/h for metric).

### FR-4: Search by City Name

**User story:** As a user, I want to search for weather by typing a city name so that
I can quickly find conditions for a place I care about.

**Acceptance criteria:**
1. A search box is visible on the home page and in the navigation bar.
2. Input of the form `City`, `City, State`, or `City, Country` is accepted
   (for example, `Amarillo`, `Amarillo, TX`, `Paris, FR`).
3. The query is sent server-side to the OpenWeather Geocoding API; the API key is
   never exposed to the browser.
4. Leading/trailing whitespace is trimmed; empty input is rejected with a validation
   message and no API call is made.
5. When exactly one location matches, the user is taken directly to that location's dashboard.
6. When no location matches, the user sees a "No locations found" message with a
   suggestion to check spelling or try a postal code.

### FR-5: Search by Postal Code

**User story:** As a user, I want to search by postal/ZIP code so that I can get
weather for a precise area.

**Acceptance criteria:**
1. The same search box accepts a postal code, optionally followed by a country code
   (for example, `79015` or `79015, US`, `SW1A 1AA, GB`).
2. Input that matches a postal-code pattern is routed to the OpenWeather ZIP
   geocoding endpoint; the country defaults to `US` when none is given.
3. A valid code takes the user to the dashboard for the resolved location, showing the
   location name returned by the API.
4. An invalid or unknown code shows a clear "Postal code not found" message.

### FR-6: Location Disambiguation

**User story:** As a user, when my search matches several places with the same name,
I want to pick the right one so that I see weather for the correct location.

**Acceptance criteria:**
1. When the geocoding API returns more than one match, a results list is shown
   instead of a dashboard.
2. Each result displays city name, state/region (when available), country, and
   coordinates rounded to two decimal places.
3. Up to five results are shown, in the order returned by the API.
4. Selecting a result opens the dashboard for that exact latitude/longitude.
5. For registered users, each result has a "Save to favorites" control (see FR-11).

### FR-7: Device Geolocation

**User story:** As a user, I want to use my device's current location so that I can
see local weather without typing anything.

**Acceptance criteria:**
1. A "Use my location" button is shown next to the search box.
2. Clicking it calls the browser Geolocation API, which prompts the user for permission.
3. If permission is granted, the coordinates are sent to the server and the user is
   taken to the dashboard for that location, with the place name resolved by reverse geocoding.
4. If permission is denied, unavailable, or times out (10 seconds), a non-blocking
   message explains the problem and the search box remains usable.
5. The button is hidden or disabled when the browser does not support geolocation or
   the page is not served from a secure context.
6. The application never requests location automatically on page load.

### FR-8: Current Weather Metrics

**User story:** As a user, I want to see the current weather conditions for a location
so that I know what it is like there right now.

**Acceptance criteria:**
1. The dashboard displays, for the selected location:
   - Location name, state/region, and country
   - Current temperature and "feels like" temperature
   - Daily high and low temperature
   - Weather condition description and matching icon
   - Humidity (%)
   - Wind speed and direction (compass point, e.g., "NW")
   - Atmospheric pressure (hPa)
   - Visibility
   - Cloud cover (%)
   - UV index, with a risk category (Low, Moderate, High, Very High, Extreme), when available
   - Sunrise and sunset times in the location's local time zone
   - The time the data was last updated
2. All values use the user's unit preference (FR-3).
3. Every icon has descriptive alternative text (for example, "light rain").
4. UV index availability depends on the OpenWeather endpoint and subscription plan:
   the free Current Weather API (2.5) does not return UV index, while the One Call API 3.0
   (separate subscription) does. When the configured endpoint or plan does not provide
   UV index, the dashboard shows "UV index unavailable" instead of a value, and all
   other metrics display normally.

### FR-9: Multi-Day Forecast with Charts

**User story:** As a user, I want to see a forecast for the next several days with
charts so that I can plan ahead and spot trends at a glance.

**Acceptance criteria:**
1. The dashboard shows a forecast covering at least the next five days, using the
   OpenWeather 5-Day/3-Hour Forecast API.
2. A daily summary row shows, for each day: day of week, date, high, low, condition
   icon, and chance of precipitation.
3. A line chart (Chart.js) plots temperature over the forecast period in 3-hour steps.
4. A second chart (bar or line) plots precipitation probability and/or amount over the
   same period.
5. Charts have labeled axes with units, a legend, and tooltips showing exact values on hover or focus.
6. Charts redraw in the correct unit when the unit preference changes (FR-3).
7. The underlying chart data is also available as an accessible data table (see NFR-AC).

### FR-10: User-Specific Favorites

**User story:** As a registered user, I want a list of my favorite locations so that I
can check weather for places I care about with one click.

**Acceptance criteria:**
1. Each favorite stores: owner (user), display name, state/region, country, latitude,
   longitude, and date added.
2. A favorites page lists only the logged-in user's favorites; no user can view,
   modify, or delete another user's favorites (enforced server-side).
3. Each favorite shows its name and current temperature/condition, and links to its dashboard.
4. The user can remove a favorite; removal requires a POST request and shows a confirmation message.
5. A user cannot save the same location twice (unique on user + coordinates rounded to
   four decimal places); a duplicate attempt shows "Already in favorites".
6. A user may store up to 20 favorites; attempting to add more shows a clear limit message.
7. The favorites page shows a helpful empty state with a link to search when the list is empty.

### FR-11: Bookmark from Search Results and Dashboard

**User story:** As a registered user, I want to save a location directly from search
results or the weather dashboard so that I don't have to navigate elsewhere to bookmark it.

**Acceptance criteria:**
1. Each disambiguation result (FR-6) has a "Save to favorites" button.
2. The dashboard (FR-8) has a "Save to favorites" button; if the location is already a
   favorite, it shows "Saved" with an option to remove it.
3. Saving or removing uses an asynchronous JavaScript request (with CSRF token) and
   updates the button state without a full page reload; it falls back to a normal form
   POST if JavaScript is disabled.
4. Anonymous users who click the button are sent to the login page and, after logging
   in, returned to the page they were on.
5. Success and error outcomes are announced to assistive technologies (ARIA live region).

### FR-12: Interactive Weather Map

**User story:** As a user, I want to view weather on an interactive map so that I can
see conditions across a region visually.

**Acceptance criteria:**
1. A map page (and a map panel on the dashboard) renders an interactive Leaflet map
   centered on the selected location with a marker.
2. The map supports pan and zoom with mouse, touch, and keyboard.
3. The user can switch between OpenWeather map tile layers: temperature,
   precipitation, clouds, and wind.
4. Each overlay layer shows a legend explaining its color scale.
5. For registered users, favorites appear as markers; clicking a marker shows a popup
   with the name, current temperature, and a link to its dashboard.
6. Tile requests are proxied or signed server-side so the OpenWeather API key is not
   embedded in client-side source.
7. If tiles fail to load, the base map remains usable and a message indicates the
   overlay is unavailable.

---

## 3. Non-Functional Requirements

### 3.1 Performance (NFR-PERF)

| ID         | Requirement                                                                                     |
|------------|-------------------------------------------------------------------------------------------------|
| NFR-PERF-1 | Dashboard pages render server-side in under 2 seconds at the 95th percentile on a cache miss, and under 500 ms on a cache hit, in the local development environment. |
| NFR-PERF-2 | Every outbound request to OpenWeather has a timeout of 5 seconds.                              |
| NFR-PERF-3 | Current weather and forecast for a dashboard are fetched with no more than one call per endpoint per page load. |
| NFR-PERF-4 | The favorites page loads current conditions for all favorites in under 3 seconds for 20 favorites (using the cache where possible). |
| NFR-PERF-5 | Static assets (CSS, JS) are minified or served with cache headers; total first-load page weight excluding map tiles stays under 1 MB. |
| NFR-PERF-6 | Database queries use indexes on foreign keys and the favorite uniqueness constraint; no page issues N+1 queries for favorites. |

### 3.2 Caching (NFR-CACHE)

| ID          | Requirement                                                                                    |
|-------------|------------------------------------------------------------------------------------------------|
| NFR-CACHE-1 | OpenWeather responses are cached using Django's cache framework, keyed by endpoint, coordinates (rounded to 2 decimals), and units. |
| NFR-CACHE-2 | Cache lifetimes: current weather 10 minutes; forecast 30 minutes; geocoding results 24 hours. |
| NFR-CACHE-3 | Cache lifetimes and backend are configurable in `config/settings.py` without code changes elsewhere. |
| NFR-CACHE-4 | The dashboard displays the time the data was retrieved so users know how fresh it is.        |
| NFR-CACHE-5 | Caching keeps total API usage within the OpenWeather free tier (60 calls/minute, 1,000,000 calls/month). |

### 3.3 Security (NFR-SEC)

| ID        | Requirement                                                                                      |
|-----------|--------------------------------------------------------------------------------------------------|
| NFR-SEC-1 | The OpenWeather API key and Django `SECRET_KEY` are loaded from environment variables (`.env`), never committed to version control, and never sent to the browser. `.env` is listed in `.gitignore`. |
| NFR-SEC-2 | Passwords are stored only as salted hashes using Django's default password hasher.             |
| NFR-SEC-3 | All state-changing requests (register, login, logout, add/remove favorite, change preference) use POST with CSRF protection. |
| NFR-SEC-4 | Authorization checks ensure users can only access and modify their own favorites and preferences; requests for another user's objects return 404. |
| NFR-SEC-5 | All user input is validated server-side; templates rely on Django auto-escaping to prevent XSS; the ORM is used for all database access to prevent SQL injection. |
| NFR-SEC-6 | `DEBUG` is `False` outside local development; `ALLOWED_HOSTS` is explicitly set; session and CSRF cookies are `Secure` and `HttpOnly` (where applicable) when served over HTTPS. |
| NFR-SEC-7 | Login attempts are rate-limited (for example, 5 failed attempts per 5 minutes per IP/username). |
| NFR-SEC-8 | Login redirects (`next`) are validated to prevent open redirects.                               |

### 3.4 Reliability (NFR-REL)

| ID        | Requirement                                                                                      |
|-----------|--------------------------------------------------------------------------------------------------|
| NFR-REL-1 | All OpenWeather calls go through a single service module in the `weather` app that handles errors consistently. |
| NFR-REL-2 | API errors and timeouts are logged server-side with the endpoint and status code, but without the API key. |
| NFR-REL-3 | Database writes for favorites and preferences are atomic; a failure leaves no partial records.  |
| NFR-REL-4 | Automated tests (Django `TestCase`) cover each functional requirement, with OpenWeather responses mocked so tests run offline. |
| NFR-REL-5 | Database schema changes are managed exclusively through Django migrations.                      |

### 3.5 Fault Tolerance (NFR-FT)

| ID       | Requirement                                                                                       |
|----------|---------------------------------------------------------------------------------------------------|
| NFR-FT-1 | If OpenWeather is unavailable, times out, or returns an error, the application shows a friendly error message instead of a server error page. |
| NFR-FT-2 | If fresh data cannot be fetched but stale cached data exists, the stale data is shown with a notice indicating its age. |
| NFR-FT-3 | A failure in one dashboard section (for example, the forecast or map) does not prevent the others (for example, current weather) from displaying. |
| NFR-FT-4 | HTTP 429 (rate limited) and 401 (invalid key) responses from OpenWeather are detected and reported with distinct log entries and user messages. |
| NFR-FT-5 | Transient network errors on idempotent GET requests are retried once with a short backoff before failing. |
| NFR-FT-6 | Core features (search, dashboard, favorites list) work without JavaScript; charts, the map, geolocation, and in-place bookmarking degrade gracefully with a visible notice. |
| NFR-FT-7 | Custom 404 and 500 error pages are provided that match the site layout and link back to home.   |

### 3.6 Usability (NFR-USE)

| ID        | Requirement                                                                                      |
|-----------|--------------------------------------------------------------------------------------------------|
| NFR-USE-1 | The layout is responsive and usable on screen widths from 320 px (phone) to 1920 px (desktop) with no horizontal scrolling. |
| NFR-USE-2 | Primary actions — search, use my location, unit toggle, save to favorites — are reachable within one click from the dashboard. |
| NFR-USE-3 | Form validation errors appear next to the relevant field in plain language.                     |
| NFR-USE-4 | Loading indicators are shown for any operation that takes longer than 300 ms (geolocation, async bookmark, chart/map load). |
| NFR-USE-5 | Navigation, terminology, and button styles are consistent across all pages.                     |
| NFR-USE-6 | Dates and times are shown in the location's local time with a clear format (for example, "Tue, Oct 20 · 6:42 PM"). |
| NFR-USE-7 | The application works in the current versions of Chrome, Firefox, Edge, and Safari.            |

### 3.7 Accessibility (NFR-AC)

| ID       | Requirement                                                                                       |
|----------|---------------------------------------------------------------------------------------------------|
| NFR-AC-1 | The application meets WCAG 2.2 Level AA.                                                          |
| NFR-AC-2 | Pages use semantic HTML landmarks (`header`, `nav`, `main`, `footer`), a logical heading hierarchy, and a "Skip to main content" link. |
| NFR-AC-3 | All functionality is operable by keyboard alone, with a visible focus indicator and logical tab order. |
| NFR-AC-4 | Text has a contrast ratio of at least 4.5:1 (3:1 for large text and UI components); information is never conveyed by color alone. |
| NFR-AC-5 | Every form control has an associated `<label>`; errors are linked to fields with `aria-describedby`. |
| NFR-AC-6 | Weather icons have meaningful `alt` text; decorative images use empty `alt=""`.                 |
| NFR-AC-7 | Charts have a text summary and an equivalent data table available to screen readers.            |
| NFR-AC-8 | The map has an accessible name, keyboard-operable controls, and a text alternative listing the selected location and favorites. |
| NFR-AC-9 | Dynamic updates (unit change, bookmark result, errors) are announced via ARIA live regions.     |
| NFR-AC-10| The interface remains usable at 200% browser zoom and respects `prefers-reduced-motion`.        |

---

## 4. Traceability Matrix

| Requirement | Feature                              | Django app | Primary NFRs                         |
|-------------|--------------------------------------|------------|--------------------------------------|
| FR-1        | Registration                         | `accounts` | SEC-2, SEC-3, SEC-5, USE-3, AC-5     |
| FR-2        | Login / logout                       | `accounts` | SEC-3, SEC-7, SEC-8                  |
| FR-3        | Temperature unit preference          | `accounts` | CACHE-1, AC-9                        |
| FR-4        | City search                          | `weather`  | PERF-2, CACHE-2, SEC-1, FT-1         |
| FR-5        | Postal-code search                   | `weather`  | PERF-2, CACHE-2, FT-1                |
| FR-6        | Location disambiguation              | `weather`  | USE-2, AC-3                          |
| FR-7        | Device geolocation                   | `weather`  | FT-6, USE-4                          |
| FR-8        | Current weather metrics              | `weather`  | PERF-1, CACHE-2, FT-2, AC-6          |
| FR-9        | Multi-day forecast with charts       | `weather`  | CACHE-2, FT-3, AC-7                  |
| FR-10       | User-specific favorites              | `weather`  | SEC-4, PERF-4, PERF-6, REL-3         |
| FR-11       | Bookmark from search and dashboard   | `weather`  | SEC-3, FT-6, AC-9                    |
| FR-12       | Interactive weather map              | `weather`  | SEC-1, FT-3, AC-8                    |

---

## 5. Assumptions and Constraints

- The application uses the free OpenWeather plan; features requiring paid endpoints
  (for example, One Call 3.0 daily forecasts beyond 5 days) are out of scope.
- The application is developed and demonstrated locally; production deployment is out of scope.
- SQLite is sufficient for the expected single-instance, low-concurrency usage.
- Users need an internet connection; offline use is out of scope.
- Weather data accuracy is the responsibility of OpenWeather.

## 6. Out of Scope

- Severe weather alerts and push notifications
- Historical weather data
- Social login (Google, GitHub, etc.) and password reset by email
- Native mobile applications
- Internationalization beyond the °F/°C unit choice
