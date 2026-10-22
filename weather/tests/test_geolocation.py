"""Tests for device geolocation (FR-7): the reverse-geocode endpoint and the button.

The browser half lives in geolocation.js (no JS test runner yet), so these tests
cover everything the server controls: coordinate validation, reverse geocoding,
redirecting to the existing dashboard, error pages, and the button markup.
OpenWeather calls are mocked.
"""
import re
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.test import override_settings
from django.utils.html import escape

from weather.services.client import OpenWeatherClient
from weather.services.exceptions import (
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
)
from weather.tests.base import OfflineTestCase, load_fixture

REVERSE_URL = "/weather/reverse/"
API_KEY = "test-key"


@override_settings(OPENWEATHER_API_KEY=API_KEY, OPENWEATHER_ENABLE_ONECALL=False)
class GeolocationTestCase(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.reverse = self.patch_client("reverse_geocode", load_fixture("reverse_geocode.json"))
        self.current = self.patch_client("current_weather", load_fixture("current_weather.json"))
        self.forecast = self.patch_client("forecast_5day", load_fixture("forecast_5day.json"))

    def patch_client(self, name, return_value):
        patcher = mock.patch.object(OpenWeatherClient, name, return_value=return_value)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def locate(self, **params):
        return self.client.get(REVERSE_URL, params)


class ReverseGeocodeEndpointTests(GeolocationTestCase):
    def test_fr7_ac3_device_coordinates_redirect_to_the_dashboard(self):
        response = self.locate(lat="35.22199", lon="-101.83129")
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response["Location"])
        self.assertEqual(url.path, "/weather/")
        self.assertEqual(parse_qs(url.query), {"lat": ["35.2220"], "lon": ["-101.8313"]})

    def test_fr7_ac3_place_name_is_resolved_by_reverse_geocoding(self):
        self.locate(lat="35.2220", lon="-101.8313")
        self.reverse.assert_called_once_with(35.222, -101.8313)

    def test_fr7_ac3_dashboard_shows_the_resolved_place_without_a_second_lookup(self):
        response = self.client.get(REVERSE_URL, {"lat": "35.2220", "lon": "-101.8313"}, follow=True)
        self.assertContains(response, "<h1>Amarillo, Texas, US</h1>", html=True)
        self.assertEqual(self.reverse.call_count, 1)

    def test_unnamed_place_still_opens_the_dashboard(self):
        self.reverse.return_value = []
        response = self.locate(lat="10.5", lon="-140.25")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/weather/?"))

    def test_nfr_sec5_invalid_coordinates_are_rejected_without_an_api_call(self):
        cases = (
            {},
            {"lat": "35.2"},
            {"lat": "91", "lon": "0"},
            {"lat": "0", "lon": "-180.5"},
            {"lat": "nan", "lon": "0"},
            {"lat": "inf", "lon": "0"},
            {"lat": "north", "lon": "west"},
        )
        for params in cases:
            with self.subTest(params=params):
                response = self.locate(**params)
                self.assertEqual(response.status_code, 400)
                self.assertTemplateUsed(response, "weather/invalid_location.html")
                self.assertContains(response, 'href="/search/"', status_code=400)
        self.reverse.assert_not_called()

    def test_nfr_sec5_invalid_input_is_not_echoed_unescaped(self):
        response = self.locate(lat="<script>x</script>", lon="0")
        self.assertNotContains(response, "<script>x</script>", status_code=400)

    def test_endpoint_is_get_only(self):
        response = self.client.post(REVERSE_URL, {"lat": "35.2", "lon": "-101.8"})
        self.assertEqual(response.status_code, 405)

    def test_nfr_sec1_redirect_never_carries_the_api_key(self):
        response = self.locate(lat="35.2220", lon="-101.8313")
        self.assertNotIn(API_KEY, response["Location"])
        self.assertNotIn("appid", response["Location"])


class ReverseGeocodeErrorTests(GeolocationTestCase):
    def assertFriendlyError(self, error, text):
        self.reverse.side_effect = error
        response = self.locate(lat="35.2220", lon="-101.8313")
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, 'role="alert"', status_code=503)
        self.assertContains(response, escape("We couldn't look up your location."), status_code=503)
        self.assertContains(response, escape(text), status_code=503)
        # FR-7 AC-4: the search box remains usable.
        self.assertContains(response, 'name="q"', status_code=503)
        self.assertNotContains(response, "Traceback", status_code=503)
        self.assertNotContains(response, API_KEY, status_code=503)

    def test_state_machine_reverse_geocoding_api_error_shows_search_error(self):
        self.assertFriendlyError(ServiceUnavailableError(), "couldn't reach the weather service")

    def test_nfr_ft4_rate_limit_and_key_errors_have_distinct_messages(self):
        self.assertFriendlyError(RateLimitError(status_code=429), "too many requests")
        cache.clear()
        self.assertFriendlyError(AuthenticationError(status_code=401), "not configured correctly")


class UseMyLocationButtonTests(GeolocationTestCase):
    def setUp(self):
        super().setUp()
        self.body = self.client.get("/").content.decode()

    def button(self):
        match = re.search(r"<button[^>]*\bdata-geolocate\b[^>]*>(.*?)</button>", self.body, re.S)
        self.assertIsNotNone(match, "Use my location button missing")
        return match

    def test_fr7_ac1_button_is_next_to_the_search_box(self):
        search = self.body.index('class="nav-search"')
        button = self.body.index("data-geolocate")
        account = self.body.index('class="nav-account"')
        self.assertLess(search, button)
        self.assertLess(button, account)
        self.assertEqual(self.button().group(1).strip(), "Use my location")

    def test_fr7_ac1_button_is_on_the_dashboard_too(self):
        dashboard = self.client.get("/weather/", {"lat": "35.2220", "lon": "-101.8313"})
        self.assertContains(dashboard, "data-geolocate")

    def test_fr7_ac5_button_is_hidden_until_script_confirms_support(self):
        tag = self.button().group(0)
        self.assertIn('type="button"', tag)
        self.assertRegex(tag, r"\bhidden\b")

    def test_fr7_ac3_button_knows_the_server_endpoint(self):
        self.assertIn(f'data-reverse-url="{REVERSE_URL}"', self.button().group(0))

    def test_fr7_ac4_messages_have_a_polite_status_region(self):
        self.assertRegex(self.body, r'<p class="geolocate-status"[^>]*role="status"[^>]*data-geolocate-status')

    def test_geolocation_script_is_deferred_and_discoverable(self):
        self.assertIn('<script src="/static/weather/js/geolocation.js" defer></script>', self.body)
        self.assertIsNotNone(finders.find("weather/js/geolocation.js"))

    def test_nfr_sec1_page_never_references_openweather_api_hosts(self):
        self.assertNotIn("api.openweathermap.org", self.body)
        self.assertNotIn(API_KEY, self.body)


class GeolocationScriptContractTests(GeolocationTestCase):
    """Structural checks on geolocation.js until a JS test runner is approved."""

    def setUp(self):
        super().setUp()
        with open(finders.find("weather/js/geolocation.js"), encoding="utf-8") as handle:
            self.source = handle.read()

    def test_fr7_ac4_ten_second_timeout(self):
        self.assertIn("GEOLOCATION_TIMEOUT_MS = 10000", self.source)

    def test_fr7_ac5_checks_support_and_secure_context(self):
        self.assertIn("isSecureContext", self.source)
        self.assertIn('"geolocation" in', self.source)

    def test_fr7_ac6_location_is_only_requested_from_the_click_handler(self):
        self.assertEqual(self.source.count("getCurrentPosition("), 1)
        handler = self.source.index('addEventListener("click"')
        request_function = self.source.index("function requestLocation(")
        self.assertIn("requestLocation(", self.source[handler:])
        self.assertLess(request_function, self.source.index("getCurrentPosition("))
