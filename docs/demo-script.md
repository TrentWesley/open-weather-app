# Demo Script: Open Weather Application (about 4½ minutes)

A walkthrough of every functional requirement, ending with how the app was built and
tested. The times are targets; the "Say" lines are suggestions.

## Before you start (not part of the timed demo)

- [ ] `.env` has your OpenWeather key and `DJANGO_DEBUG=true`. Don't open `.env` on screen.
- [ ] Run `uv run python manage.py migrate`, then `uv run python manage.py runserver`.
- [ ] Create a demo account (for example `demo` / a strong password) and save **one**
      favorite beforehand (for example Lubbock, TX), so the map has a favorite marker.
- [ ] Log out. Use a normal (non-private) browser window at <http://127.0.0.1:8000/>,
      zoomed to 100–125 % so the audience can read it.
- [ ] If you'll demo "Use my location", allow location access for `127.0.0.1` beforehand,
      or plan to show the "denied" message instead.
- [ ] Open a terminal in the project folder for the last segment. Optionally run the
      tests beforehand so you can show the result without waiting about 75 s.
- [ ] Close tabs and notifications that could show personal information.

---

## 0:00–0:20 · Introduction

**Say:** "This is a Django weather app built on the OpenWeather APIs. You can search by
city or postal code, see current weather and a five-day forecast, save favorites and
explore a weather map. It was built test-first from a written requirements document and
five UML diagrams."

## 0:20–0:50 · Search and the API key (FR-4, FR-5)

1. In the nav search box, type **`Amarillo, TX`** and press Enter. Exactly one match, so
   it goes straight to the dashboard.
2. Search **`SW1A 1AA, GB`** to show international postal codes.

**Say:** "Every OpenWeather call happens on the server. The browser only talks to this
app, so the API key never reaches the page." Optionally press Ctrl+U and search the page
source for `appid`: there are no matches.

## 0:50–1:40 · Dashboard and units (FR-8, FR-9, FR-3)

1. Go back to Amarillo (browser Back, or search again).
2. Point out the current temperature, feels like, high/low, conditions and icon,
   humidity, wind with compass direction, pressure, visibility, cloud cover, and sunrise
   and sunset in Amarillo's local time.
3. Point out **"UV index unavailable"**. **Say:** "The free Current Weather API doesn't
   include UV. With a One Call subscription, one setting turns it on."
4. Point out **"Last updated"**. **Say:** "Responses are cached, 10 minutes for current
   weather and 30 for the forecast, to stay within the free tier."
5. Scroll to the **5-day forecast** and the two charts. Tab to the temperature chart and
   press the arrow keys: values are announced. Open **"Show the forecast as a table"**.
6. Click **°C**. The page reloads at the same location, and the values, chart axes and
   wind units (m/s) change.

## 1:40–2:20 · Choosing between matches and saving favorites (FR-6, FR-11, FR-2)

1. Search **`Springfield`**. A list of matches appears with states and coordinates.
2. Click **"Save to favorites"** on Springfield, Missouri. You're signed out, so the app
   sends you to the login page.
3. Log in as `demo`. You land back on the Springfield results.
4. Click **"Save to favorites"** again. The button switches to **"Saved"** without a page
   reload, and the result is announced to screen readers.
5. Optional: in a tab you opened *before* saving, click **"Save to favorites"** for the
   same place. It shows **"Already in favorites"**.

**Say:** "Saving uses fetch with a CSRF token. Without JavaScript it falls back to a
normal form post."

## 2:20–2:50 · Favorites page (FR-10)

1. Click **Favorites** in the nav. Each favorite shows its current temperature and
   conditions and links to its dashboard.
2. Point out **"2 of 20 saved"**. **Say:** "There's a limit of 20, and the same place
   can't be saved twice. That's enforced by a database constraint, not just the UI."
3. Click **Remove** on one favorite. A confirmation message appears.

**Say:** "Favorites are private. Asking for another user's favorite returns a 404."

## 2:50–3:30 · Weather map (FR-12)

1. Click **"Show your favorites on a map"** (or **Map** in the nav).
2. Switch the layer from **Temperature** to **Precipitation** to **Wind speed**. The
   legend changes and uses your unit.
3. Click a favorite's **star marker**. The popup shows its name, current weather and a
   link to its forecast.
4. Click the map and press the **arrow keys** and **+ / −**. It's keyboard accessible.

**Say:** "The weather tiles come through a proxy on this server that adds the API key.
The background map is OpenStreetMap, used within their tile policy."

## 3:30–3:50 · Use my location (FR-7)

1. Click **"Use my location"**. If permission is granted, the dashboard opens for where
   you are.
2. If it's denied or slow, the message explains why, and the search box still works.
   That's also a requirement.

## 3:50–4:30 · How it was built

1. In the terminal, show the result of `uv run python manage.py test`: **582 tests, OK**.
   **Say:** "The tests never touch the network. OpenWeather responses are recorded
   fixtures, and any real network call fails the test. Each test is named after the
   requirement it covers."
2. Optionally show `docs/diagrams/sequence.png` or `class.png`. **Say:** "The code
   follows the class and sequence diagrams. A Phase 9 audit checked every requirement,
   ran an accessibility scanner on every page, and confirmed the API key isn't anywhere
   in the git history."

## 4:30–4:45 · Close

**Say:** "Limitations: it's built for local use, UV needs a paid OpenWeather plan, and
I've tested Chrome and Edge but not yet Firefox or Safari. Thanks."

---

## If something goes wrong live

| Problem | What to do |
|---------|------------|
| OpenWeather is slow or down | The dashboard shows a friendly error, or saved data with its age. Mention that's fault tolerance (NFR-FT-1/2) and move on. |
| "Too many requests" message | You've hit the free-tier rate limit. Wait a minute or use already-cached locations (Amarillo). |
| Map background is blank | Check the internet connection. The weather layers and markers still work, and the text list under the map names every place. |
| Location permission denied | Show the message and say it's the required fallback (FR-7 AC-4). |
| Login refused after typos | 5 failures in 5 minutes triggers rate limiting (NFR-SEC-7). Restart the server to clear it. |
