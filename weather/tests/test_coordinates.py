"""Tests for coordinate validation and the /weather/ landing page (FR-6 AC-4, NFR-SEC-5).

These tests pin down the dashboard URL contract (`/weather/?lat=&lon=`) and that
bad coordinates never get through.
"""
from unittest import mock

from django.core.cache import cache
from django.test import override_settings

from weather.forms import CoordinatesForm
from weather.services.client import OpenWeatherClient
from weather.tests.base import OfflineSimpleTestCase, OfflineTestCase, load_fixture

DASHBOARD_URL = "/weather/"


class CoordinatesFormTests(OfflineSimpleTestCase):
    def test_valid_coordinates(self):
        form = CoordinatesForm({"lat": "35.2220", "lon": "-101.8313"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data, {"lat": 35.222, "lon": -101.8313})

    def test_boundaries_are_inclusive(self):
        for lat, lon in (("90", "180"), ("-90", "-180")):
            with self.subTest(lat=lat, lon=lon):
                self.assertTrue(CoordinatesForm({"lat": lat, "lon": lon}).is_valid())

    def test_nfr_sec5_out_of_range_coordinates_are_rejected(self):
        for lat, lon in (("90.01", "0"), ("-90.01", "0"), ("0", "180.01"), ("0", "-180.01")):
            with self.subTest(lat=lat, lon=lon):
                self.assertFalse(CoordinatesForm({"lat": lat, "lon": lon}).is_valid())

    def test_nfr_sec5_non_numeric_and_non_finite_values_are_rejected(self):
        for value in ("abc", "nan", "inf", "-inf", "1e400", ""):
            with self.subTest(value=value):
                self.assertFalse(CoordinatesForm({"lat": value, "lon": "0"}).is_valid())

    def test_both_coordinates_are_required(self):
        self.assertFalse(CoordinatesForm({"lat": "35.2"}).is_valid())


@override_settings(OPENWEATHER_API_KEY="test-key", OPENWEATHER_ENABLE_ONECALL=False)
class DashboardLandingTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        # The page now loads weather (Phase 4), so OpenWeather calls are mocked.
        for name, fixture in (
            ("current_weather", "current_weather.json"),
            ("reverse_geocode", "reverse_geocode.json"),
        ):
            patcher = mock.patch.object(
                OpenWeatherClient, name, return_value=load_fixture(fixture)
            )
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_fr6_ac4_valid_coordinates_open_the_location_page(self):
        response = self.client.get(DASHBOARD_URL, {"lat": "39.7990", "lon": "-89.6440"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "weather/dashboard.html")
        self.assertContains(response, "39.80, -89.64")
        self.assertContains(response, "<h1", count=1)

    def test_nfr_sec5_invalid_coordinates_return_400_with_a_way_back(self):
        for params in ({}, {"lat": "91", "lon": "0"}, {"lat": "x", "lon": "y"}, {"lat": "nan", "lon": "0"}):
            with self.subTest(params=params):
                response = self.client.get(DASHBOARD_URL, params)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, 'href="/search/"', status_code=400)

    def test_nfr_sec5_invalid_input_is_not_echoed_unescaped(self):
        response = self.client.get(DASHBOARD_URL, {"lat": "<script>x</script>", "lon": "0"})
        self.assertNotContains(response, "<script>x</script>", status_code=400)

    def test_dashboard_is_get_only(self):
        self.assertEqual(self.client.post(DASHBOARD_URL, {"lat": "1", "lon": "1"}).status_code, 405)
