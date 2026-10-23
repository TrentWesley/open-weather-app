# Requirements Audit (Phase 9)

**Date:** 2026-10-23 · **Scope:** FR-1 to FR-12 and all 48 NFRs in
[`REQUIREMENTS.md`](../REQUIREMENTS.md) · **Result:** 582 tests pass offline; every FR
acceptance criterion has at least one test tagged with its ID.

How each requirement was checked:

- **Automated tests:** `uv run python manage.py test`, offline, with OpenWeather
  mocked.
- **Browser checks:** headless Chrome 141 and Edge 141 against the running app, with
  OpenWeather mocked and real OpenStreetMap tiles. These covered axe-core 4.10.2
  (WCAG 2.0/2.1/2.2 A and AA), horizontal overflow at 320, 640 and 1920 px, and
  keyboard and map behavior.
- **Live smoke test:** the development server with a real OpenWeather key, kept on the
  server and never printed.
- **Review:** reading the code, templates and diagrams.

---

## Functional requirements

Test refs counts test names and docstrings tagged with the requirement's acceptance
criteria (`fr10_ac5`, `FR-10 AC-5`).

| Req | Criteria | Test refs | Notes |
|-----|---------:|----------:|-------|
| FR-1 Registration | 7 | 15 | Case-insensitive unique usernames, Django password validators, auto-login |
| FR-2 Login / logout | 6 | 12 | Generic error message, validated `next`, POST-only logout |
| FR-3 Unit preference | 6 | 30 | Profile or session, °F default, redraw on toggle, mph or m/s |
| FR-4 City search | 6 | 15 | `City`, `City, ST` and `City, CC`; empty input makes no API call |
| FR-5 Postal code | 4 | 6 | US default; `SW1A 1AA, GB` works; "Postal code not found" |
| FR-6 Disambiguation | 5 | 13 | Up to 5 matches in API order, with save buttons |
| FR-7 Geolocation | 6 | 15 | Click only, 10 s timeout, hidden when unsupported or insecure; verified in browser |
| FR-8 Current weather | 4 | 23 | All metrics; "UV index unavailable" without One Call |
| FR-9 Forecast and charts | 7 | 23 | Daily summaries, two Chart.js charts, data table |
| FR-10 Favorites | 7 | 23 | Unique per user, limit 20, 404 for other users' favorites, empty state |
| FR-11 Bookmarking | 5 | 19 | `fetch` with CSRF, form fallback without JS, return after login, announcements |
| FR-12 Map | 7 | 21 | Layers, legends, favorite markers, validated tile proxy, notice when tiles fail |

## Non-functional requirements

| ID | Status | How verified |
|----|--------|--------------|
| PERF-1 | Met | Live: dashboard 505 ms on a cache miss, 4 ms on a hit (targets 2 s / 500 ms). Render-time test with mocks. |
| PERF-2 | Met | Client tests: 5 s timeout on every request |
| PERF-3 | Met | Tests: one call per endpoint per load; the dashboard map uses cached favorite weather only |
| PERF-4 | Met | Favorites served from cache; uncached ones fetched 5 at a time (`current_many`) |
| PERF-5 | Met (dev) | Dashboard HTML plus every static asset is under 1 MB (test). Chart.js and Leaflet are minified; the project's own CSS and JS (about 40 KB) are not. Cache headers would come from the production web server, and deployment is out of scope. |
| PERF-6 | Met | Unique constraint used as the index; query count constant from 1 to 20 favorites (tests) |
| CACHE-1 to 4 | Met | Cache tests: key composition, TTLs from settings, "Last updated" shown |
| CACHE-5 | Met by design | 10/30 min and 24 h caching, plus 10 min browser caching for tiles. No load test was run. |
| SEC-1 | Met | Key never rendered (tests); `.env` never committed (scan of all commits); live run found the key in 0 of 18 responses and not in the server log |
| SEC-2 | Met | Django's default PBKDF2 hasher (test) |
| SEC-3 | Met | POST + CSRF on every state change; CSRF enforced in tests |
| SEC-4 | Met | `get_object_or_404(..., user=request.user)`; another user's favorite is a 404 (tests) |
| SEC-5 | Met | Forms and explicit validation; auto-escaping; ORM only; greps find no `\|safe`, `mark_safe`, `csrf_exempt` or `innerHTML` |
| SEC-6 | Met | `DEBUG` and `ALLOWED_HOSTS` from env (default off); Secure and HttpOnly cookies. `check --deploy`: only HSTS and SSL-redirect warnings remain (HTTPS deployment, out of scope). |
| SEC-7 | Met | 5 failures in 5 min per IP and per username (tests) |
| SEC-8 | Met | `url_has_allowed_host_and_scheme` for login, unit toggle and favorites `next` (tests) |
| REL-1 to 5 | Met | Single client gateway, key-safe logging, atomic writes, offline guard, migrations check (tests) |
| FT-1 to 7 | Met | Friendly errors, stale fallback with age, independent sections, distinct 401/429 messages, one retry, no-JS fallbacks, custom 404/500 pages (tests and browser) |
| USE-1 | Met | No horizontal overflow on any of 15 page and auth combinations at 320, 640 and 1920 px (browser) |
| USE-2 | Met | Search, use my location, unit toggle and save are all on the dashboard (test) |
| USE-3 | Met | Errors render inside their field and are linked with `aria-describedby` (tests) |
| USE-4 | Met | Loading indicators after 300 ms for navigation, geolocation, bookmarking (added in Phase 9) and the map (tests and browser) |
| USE-5 | Met (review) | One base layout and nav; shared `.button` / `.button-secondary` styles; consistent wording ("Save to favorites", "Use my location") |
| USE-6 | Met | Local times such as "Tue, Oct 20 · 6:42 PM" from the location's UTC offset (tests) |
| USE-7 | Partly | Chrome and Edge 141 verified. Firefox and Safari not tested (not installed). |
| AC-1 | Met (automated) | axe-core finds no WCAG A/AA violations on 15 page and auth combinations in light and dark themes. Manual screen-reader pass still recommended. |
| AC-2 | Met | Landmarks, skip link, one `<h1>` (tests) |
| AC-3 | Met | No positive tabindex; visible focus ring; map, markers and charts reachable by keyboard (tests and browser) |
| AC-4 | Met | Every color pair meets AA in both themes (test; lowest margin 4.93:1, chart line in light mode); map attribution links underlined |
| AC-5 to 9 | Met | Labels and linked errors, icon alt text, chart summaries and tables, map text alternative, live-region announcements (tests) |
| AC-10 | Met | Layout at 640 px (equivalent to 200 % zoom at 1280 px) has no overflow; reduced motion turns off chart and map animation (browser) |

## Phase 9 findings and fixes

| Finding | Fix |
|---------|-----|
| No tests tagged for FR-7 AC-2 or FR-8 AC-2, and 11 NFRs untagged | Added `config/tests/test_audit.py` and a geolocation test; each was checked against a deliberate defect |
| axe: `link-in-text-block` on map attribution links (Leaflet removes the underline; contrast 2.55:1) | Underlined the attribution links |
| `check --deploy`: `mail.E001` (console email backend outside debug) | Console backend in `DEBUG` only, SMTP otherwise; the app sends no email |
| Activity diagram missing two geolocation error paths | Added invalid-coordinates and reverse-geocoding-failure branches; PNG re-exported |
| Async bookmark had no loading indicator (NFR-USE-4 names it) | "Saving…" / "Removing…" after 300 ms; verified in Chrome |
| README was empty | Wrote README; updated the `REQUIREMENTS.md` status line |

Earlier phases had already fixed the OpenStreetMap "Access blocked" tiles (missing
Referer), a `map.js` global-name clash, and the Chart.js resize loop.

## Diagrams

All five `.mmd` sources parse and render with Mermaid 11.4.1, and every PNG matches its
source:
- **class.mmd:** a script checked all 94 classes, attributes and methods against the code.
- **use-case, sequence, state-machine:** reviewed and found to match the implemented behavior.
- **activity.mmd:** updated, as noted above.

## Live smoke test (real OpenWeather, 2026-10-23)

| Check | Result |
|-------|--------|
| `Amarillo, TX` / `79015` / `SW1A 1AA, GB` | Redirect to the dashboard |
| `Paris, FR` / `Springfield` | Lists of 4 and 5 matches |
| Nonsense query | "No locations found" |
| Dashboard | Real data, 5 days, charts, no section errors; UV unavailable on the free plan, as expected |
| Reverse geocoding, map page | Working |
| 8 overlay tiles (4 layers × 2 zooms) | Real 256×256 PNGs through the proxy |
| API key in responses or server log | Not found |

## Remaining limitations

1. **Local only.** HTTPS deployment, HSTS, SSL redirect and production static-file
   serving are out of scope (REQUIREMENTS §5).
2. **UV index** needs a One Call 3.0 subscription (`OPENWEATHER_ENABLE_ONECALL=true`);
   the free plan shows "UV index unavailable".
3. **Background map.** OpenStreetMap's tile servers allow light, interactive use only.
   Set `MAP_BASE_TILE_URL` to another provider for heavier use.
4. **Browsers.** Firefox and Safari are untested; Chrome and Edge passed.
5. **No JavaScript test runner** (adding one needs approval). The scripts are covered by
   structural tests and headless-browser runs.
6. **Our own CSS and JS aren't minified** (about 40 KB); first load is still well under 1 MB.
7. **Rate limiting and cache are per process** (`LocMemCache`). That suits the
   single-instance local setup but not several servers.
8. **The map's highest overlay zooms** depend on what OpenWeather serves; tiles beyond
   that show the "layer unavailable" notice.

## Manual checks still recommended

- A screen reader (NVDA or VoiceOver) across search, dashboard, favorites and map
- Real touch gestures on a phone (map pan and pinch, scrolling past the map)
- Firefox and Safari smoke tests
- 200 % browser zoom by hand, in light and dark themes
- "Use my location" with a real device location
