"""Tests for the current-weather dashboard at /weather/?lat=&lon=.

FR-3 AC-1/2/3/5/6, FR-8 AC-1..4, NFR-PERF-3, NFR-CACHE-4, NFR-FT-1/2/3, NFR-USE-4,
NFR-SEC-1/5. OpenWeatherClient methods are patched, so the real services and
cache run offline. The fixture is for Amarillo (UTC-5), fetched at 13:20 UTC.
"""
import time
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.utils.html import escape

from accounts.models import TemperatureUnit, UserProfile
from weather.services.client import OpenWeatherClient
from weather.services.exceptions import (
    AuthenticationError,
    RateLimitError,
    ServiceUnavailableError,
)
from weather.tests.base import OfflineTestCase, load_fixture

API_KEY = "test-key"
PARAMS = {"lat": "35.2220", "lon": "-101.8313"}
URL = "/weather/?lat=35.2220&lon=-101.8313"
NOW = datetime(2026, 10, 22, 13, 20, tzinfo=UTC)


@override_settings(OPENWEATHER_API_KEY=API_KEY, OPENWEATHER_ENABLE_ONECALL=False)
class DashboardTestCase(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.current = self.patch_client("current_weather", load_fixture("current_weather.json"))
        self.reverse = self.patch_client("reverse_geocode", load_fixture("reverse_geocode.json"))
        self.uv = self.patch_client("uv_index", 6.2)
        self.forecast = self.patch_client("forecast_5day", load_fixture("forecast_5day.json"))
        self.set_now(NOW)

    def patch_client(self, name, return_value):
        patcher = mock.patch.object(OpenWeatherClient, name, return_value=return_value)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def set_now(self, moment):
        patcher = mock.patch("django.utils.timezone.now", return_value=moment)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self):
        return self.client.get("/weather/", PARAMS)


class LocationTests(DashboardTestCase):
    def test_fr8_ac1_shows_location_name_state_and_country(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "weather/dashboard.html")
        self.assertContains(response, "<h1>Amarillo, Texas, US</h1>", html=True)
        self.assertContains(response, "35.22, -101.83")
        self.reverse.assert_called_once_with(35.222, -101.8313)

    def test_reverse_geocoding_failure_falls_back_to_coordinates(self):
        self.reverse.side_effect = ServiceUnavailableError()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1>35.22, -101.83</h1>", html=True)
        self.assertContains(response, "68°F")

    def test_unnamed_place_is_titled_by_its_coordinates(self):
        self.reverse.return_value = []
        self.assertContains(self.get(), "<h1>35.22, -101.83</h1>", html=True)

    def test_nfr_sec5_api_place_names_are_escaped(self):
        self.reverse.return_value = [
            {"name": "<b>Evil</b>", "lat": 35.2, "lon": -101.8, "country": "US"}
        ]
        response = self.get()
        self.assertNotContains(response, "<b>Evil</b>")
        self.assertContains(response, escape("<b>Evil</b>"))


class CurrentConditionsTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.response = self.get()

    def assertShows(self, text):
        self.assertContains(self.response, text)

    def test_fr8_ac1_temperature_feels_like_and_daily_high_low(self):
        self.assertShows('<p class="current-temp">68°F</p>')
        self.assertShows("Feels like 68°F")
        self.assertShows("High 72°F")
        self.assertShows("Low 65°F")

    def test_fr8_ac1_condition_description(self):
        self.assertShows("Light rain")

    def test_fr8_ac3_condition_icon_has_descriptive_alt_text(self):
        self.assertShows('src="https://openweathermap.org/img/wn/10d@2x.png"')
        self.assertShows('alt="light rain"')

    def test_fr8_ac1_humidity_wind_pressure_visibility_and_clouds(self):
        for label, value in (
            ("Humidity", "64%"),
            ("Wind", "13 mph NW"),
            ("Pressure", "1014 hPa"),
            ("Visibility", "6.2 mi"),
            ("Cloud cover", "75%"),
        ):
            with self.subTest(label=label):
                self.assertContains(self.response, f"<dt>{label}</dt><dd>{value}</dd>", html=True)

    def test_fr8_ac1_sunrise_and_sunset_in_local_time(self):
        self.assertContains(self.response, "<dt>Sunrise</dt><dd>7:41 AM</dd>", html=True)
        self.assertContains(self.response, "<dt>Sunset</dt><dd>6:57 PM</dd>", html=True)

    def test_fr8_ac1_nfr_cache4_last_updated_in_local_time(self):
        self.assertShows("Last updated Thu, Oct 22 · 8:20 AM")

    def test_fresh_data_has_no_stale_notice(self):
        self.assertNotContains(self.response, "Showing saved weather")

    def test_single_h1_and_labelled_sections(self):
        self.assertContains(self.response, "<h1", count=1)
        self.assertShows('aria-labelledby="current-heading"')


class UvIndexTests(DashboardTestCase):
    def test_fr8_ac4_uv_index_unavailable_without_one_call(self):
        response = self.get()
        self.assertContains(response, "<dt>UV index</dt><dd>UV index unavailable</dd>", html=True)
        self.uv.assert_not_called()

    @override_settings(OPENWEATHER_ENABLE_ONECALL=True)
    def test_fr8_ac1_uv_index_and_risk_category_with_one_call(self):
        response = self.get()
        self.assertContains(response, "<dt>UV index</dt><dd>6.2 (High)</dd>", html=True)

    @override_settings(OPENWEATHER_ENABLE_ONECALL=True)
    def test_fr8_ac4_uv_failure_still_shows_other_metrics(self):
        self.uv.side_effect = RateLimitError(status_code=429)
        response = self.get()
        self.assertContains(response, "UV index unavailable")
        self.assertContains(response, "68°F")


class UnitPreferenceTests(DashboardTestCase):
    def test_fr3_ac4_default_is_fahrenheit(self):
        response = self.get()
        self.current.assert_called_once_with(35.222, -101.8313, "imperial")
        self.assertContains(response, "68°F")

    def test_fr3_ac3_anonymous_session_unit_is_used(self):
        session = self.client.session
        session["temperature_unit"] = "metric"
        session.save()
        response = self.get()
        self.current.assert_called_once_with(35.222, -101.8313, "metric")
        self.assertContains(response, "68°C")

    def test_fr3_ac2_logged_in_profile_unit_is_used(self):
        user = User.objects.create_user("alice", password="Correct-Horse-91")
        UserProfile.objects.create(user=user, temperature_unit=TemperatureUnit.METRIC)
        self.client.force_login(user)
        self.get()
        self.current.assert_called_once_with(35.222, -101.8313, "metric")

    def test_fr3_ac6_metric_shows_wind_in_m_per_s_and_visibility_in_km(self):
        self.client.post("/preferences/unit/", {"temperature_unit": "metric"})
        response = self.get()
        self.assertContains(response, "12.7 m/s NW")
        self.assertContains(response, "10 km")
        self.assertNotContains(response, " mph")

    def test_fr3_ac1_dashboard_has_a_unit_toggle(self):
        response = self.get()
        self.assertContains(response, 'action="/preferences/unit/"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'name="temperature_unit" value="imperial"')
        self.assertContains(response, 'name="temperature_unit" value="metric"')
        self.assertContains(response, f'name="next" value="{escape(URL)}"')

    def test_fr3_current_unit_is_marked_pressed(self):
        body = self.get().content.decode()
        imperial = body[body.index('value="imperial"') - 200: body.index('value="imperial"') + 200]
        metric = body[body.index('value="metric"') - 200: body.index('value="metric"') + 200]
        self.assertIn('aria-pressed="true"', imperial)
        self.assertIn('aria-pressed="false"', metric)

    def test_fr3_ac5_toggling_returns_to_the_same_location_in_the_new_unit(self):
        self.get()
        response = self.client.post(
            "/preferences/unit/", {"temperature_unit": "metric", "next": URL}
        )
        self.assertRedirects(response, URL, fetch_redirect_response=False)
        page = self.client.get(response["Location"])
        self.assertContains(page, "<h1>Amarillo, Texas, US</h1>", html=True)
        self.assertContains(page, "68°C")
        self.assertEqual(
            [c.args[2] for c in self.current.call_args_list], ["imperial", "metric"]
        )


class CachingAndCallBudgetTests(DashboardTestCase):
    def test_nfr_perf3_one_call_per_endpoint_per_page_load(self):
        self.get()
        self.assertEqual(self.current.call_count, 1)
        self.assertEqual(self.forecast.call_count, 1)

    def test_nfr_cache1_reload_is_served_from_cache(self):
        self.get()
        self.get()
        self.assertEqual(self.current.call_count, 1)
        self.assertEqual(self.reverse.call_count, 1)


class StaleAndErrorTests(DashboardTestCase):
    def expire_fresh_cache(self, minutes):
        later = time.time() + minutes * 60
        patcher = mock.patch("time.time", return_value=later)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.set_now(NOW + timedelta(minutes=minutes))

    def test_nfr_ft2_stale_data_is_shown_with_its_age(self):
        self.get()
        self.expire_fresh_cache(11)
        self.current.side_effect = ServiceUnavailableError()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Showing saved weather from 11 minutes ago")
        self.assertContains(response, "Last updated Thu, Oct 22 · 8:20 AM")
        self.assertContains(response, "68°F")

    def fail_both_sections(self, error):
        self.current.side_effect = error
        self.forecast.side_effect = error

    def test_nfr_ft1_error_without_cached_data_shows_friendly_message(self):
        self.fail_both_sections(ServiceUnavailableError())
        response = self.get()
        self.assertEqual(response.status_code, 503)
        self.assertTemplateUsed(response, "weather/dashboard.html")
        self.assertContains(response, 'role="alert"', status_code=503)
        self.assertContains(response, escape("couldn't reach the weather service"), status_code=503)
        self.assertContains(response, "<h1>Amarillo, Texas, US</h1>", html=True, status_code=503)
        self.assertNotContains(response, "Traceback", status_code=503)

    def test_nfr_ft4_rate_limit_and_key_errors_have_distinct_messages(self):
        self.fail_both_sections(RateLimitError(status_code=429))
        self.assertContains(self.get(), "too many requests", status_code=503)
        cache.clear()
        self.fail_both_sections(AuthenticationError(status_code=401))
        self.assertContains(self.get(), "not configured correctly", status_code=503)

    def test_error_page_keeps_the_unit_toggle(self):
        self.fail_both_sections(ServiceUnavailableError())
        self.assertContains(self.get(), 'action="/preferences/unit/"', status_code=503)


class SafetyAndLoadingTests(DashboardTestCase):
    def test_nfr_sec1_api_key_and_api_host_never_reach_the_page(self):
        pages = [self.get()]
        cache.clear()
        self.current.side_effect = AuthenticationError(status_code=401)
        pages.append(self.get())
        for response in pages:
            body = response.content.decode()
            self.assertNotIn(API_KEY, body)
            self.assertNotIn("api.openweathermap.org", body)

    def test_nfr_use4_loading_indicator_and_script_are_included(self):
        response = self.get()
        self.assertContains(response, 'id="loading-indicator"')
        self.assertRegex(response.content.decode(), r'<div id="loading-indicator"[^>]*\bhidden\b')
        self.assertRegex(
            response.content.decode(),
            r'<script src="/static/weather/js/loading\.js" defer></script>',
        )

    def test_nfr_use4_navigating_controls_opt_in_to_the_loading_indicator(self):
        response = self.get()
        self.assertRegex(response.content.decode(), r'<form class="unit-toggle"[^>]*data-loading')
        self.assertRegex(response.content.decode(), r'<form class="nav-search"[^>]*data-loading')

    def test_nfr_use4_search_result_links_opt_in_to_the_loading_indicator(self):
        patcher = mock.patch.object(
            OpenWeatherClient, "geocode_direct",
            return_value=load_fixture("geocode_direct_multiple.json"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        response = self.client.get("/search/", {"q": "Springfield"})
        self.assertRegex(response.content.decode(), r'<a href="/weather/\?[^"]+" data-loading>')

    def test_loading_script_is_a_discoverable_static_file(self):
        from django.contrib.staticfiles import finders

        self.assertIsNotNone(finders.find("weather/js/loading.js"))
