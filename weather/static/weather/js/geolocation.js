// FR-7: "Use my location". Location is requested only when the button is clicked
// (never on page load), and only the coordinates are sent to our own server, which
// reverse geocodes them and redirects to the dashboard. The button stays hidden
// where geolocation is unsupported or the page isn't a secure context.

const GEOLOCATION_TIMEOUT_MS = 10000;
const SLOW_NOTICE_MS = 300;
const SEARCH_HINT = " You can still search by city or postal code.";
const MESSAGES = {
  finding: "Finding your location…",
  found: "Location found. Loading weather…",
  denied: `Location access was denied.${SEARCH_HINT}`,
  unavailable: `Your location isn't available right now.${SEARCH_HINT}`,
  timeout: `Finding your location took longer than 10 seconds.${SEARCH_HINT}`,
  invalid: `Your device reported a location that isn't valid.${SEARCH_HINT}`,
};
// GeolocationPositionError codes.
const PERMISSION_DENIED = 1;
const TIMEOUT = 3;

// ---- Pure helpers (no DOM access) ----

function isGeolocationAvailable(win) {
  return Boolean(win.isSecureContext && win.navigator && "geolocation" in win.navigator);
}

function isValidCoordinate(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon)
    && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

function reverseGeocodeUrl(base, lat, lon) {
  const params = new URLSearchParams({ lat: lat.toFixed(4), lon: lon.toFixed(4) });
  return `${base}?${params}`;
}

function messageForError(code) {
  if (code === PERMISSION_DENIED) {
    return MESSAGES.denied;
  }
  if (code === TIMEOUT) {
    return MESSAGES.timeout;
  }
  return MESSAGES.unavailable;
}

// ---- DOM wiring ----

function requestLocation(button, status) {
  let settled = false;
  let slowNotice = null;
  let watchdog = null;

  function finish(message) {
    settled = true;
    clearTimeout(slowNotice);
    clearTimeout(watchdog);
    button.disabled = false;
    button.removeAttribute("aria-busy");
    status.textContent = message;
  }

  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  status.textContent = "";
  // NFR-USE-4: only show progress if it takes longer than 300 ms.
  slowNotice = setTimeout(() => {
    if (!settled) {
      status.textContent = MESSAGES.finding;
    }
  }, SLOW_NOTICE_MS);
  // The browser's own timeout starts after permission is granted; this one also
  // covers a permission prompt that is never answered (FR-7 AC-4).
  watchdog = setTimeout(() => {
    if (!settled) {
      finish(MESSAGES.timeout);
    }
  }, GEOLOCATION_TIMEOUT_MS);

  navigator.geolocation.getCurrentPosition(
    (position) => {
      if (settled) {
        return;
      }
      const { latitude, longitude } = position.coords;
      if (!isValidCoordinate(latitude, longitude)) {
        finish(MESSAGES.invalid);
        return;
      }
      finish(MESSAGES.found);
      window.location.assign(reverseGeocodeUrl(button.dataset.reverseUrl, latitude, longitude));
    },
    (error) => {
      if (!settled) {
        finish(messageForError(error.code));
      }
    },
    { enableHighAccuracy: false, timeout: GEOLOCATION_TIMEOUT_MS, maximumAge: 60000 },
  );
}

function setUpGeolocation() {
  const button = document.querySelector("[data-geolocate]");
  const status = document.querySelector("[data-geolocate-status]");
  if (!button || !status || !isGeolocationAvailable(window)) {
    return; // FR-7 AC-5: the button stays hidden.
  }
  button.hidden = false;
  button.addEventListener("click", () => requestLocation(button, status));
}

setUpGeolocation();
