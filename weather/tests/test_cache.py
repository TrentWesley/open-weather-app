"""Tests for WeatherCache (NFR-CACHE-1..3, NFR-FT-2).

Expiry is checked by patching time.time, which Django's LocMemCache reads, instead
of sleeping.
"""
import time
from unittest import mock

from django.core.cache import cache
from django.test import override_settings

from accounts.models import TemperatureUnit
from weather.services.cache import WeatherCache
from weather.tests.base import OfflineSimpleTestCase

TTLS = {"geocode": 86400, "current": 600, "forecast": 1800}


@override_settings(WEATHER_CACHE_TTL=TTLS, WEATHER_CACHE_STALE_TTL=3600)
class WeatherCacheTests(OfflineSimpleTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.cache = WeatherCache()
        self.now = time.time()

    def at(self, seconds_later):
        return mock.patch("time.time", return_value=self.now + seconds_later)

    def test_nfr_cache2_ttls_match_requirements(self):
        self.assertEqual(self.cache.GEOCODE_TTL, 24 * 60 * 60)
        self.assertEqual(self.cache.CURRENT_TTL, 10 * 60)
        self.assertEqual(self.cache.FORECAST_TTL, 30 * 60)

    def test_nfr_cache3_ttls_are_read_from_settings(self):
        with override_settings(
            WEATHER_CACHE_TTL={"geocode": 1, "current": 2, "forecast": 3}
        ):
            weather_cache = WeatherCache()
            self.assertEqual(
                (weather_cache.GEOCODE_TTL, weather_cache.CURRENT_TTL, weather_cache.FORECAST_TTL),
                (1, 2, 3),
            )

    def test_miss_returns_none(self):
        self.assertIsNone(self.cache.get("weather:current:1.00:2.00:imperial"))

    def test_hit_returns_stored_value(self):
        self.cache.set("k", {"temp": 70}, 600)
        self.assertEqual(self.cache.get("k"), {"temp": 70})

    def test_fresh_entry_expires_after_its_ttl(self):
        with self.at(0):
            self.cache.set("k", "value", 600)
        with self.at(599):
            self.assertEqual(self.cache.get("k"), "value")
        with self.at(601):
            self.assertIsNone(self.cache.get("k"))

    def test_nfr_ft2_stale_copy_outlives_the_fresh_entry(self):
        with self.at(0):
            self.cache.set("k", "value", 600)
        with self.at(601):
            self.assertIsNone(self.cache.get("k"))
            self.assertEqual(self.cache.get_stale("k"), "value")

    def test_nfr_ft2_stale_copy_expires_after_ttl_plus_stale_ttl(self):
        with self.at(0):
            self.cache.set("k", "value", 600)
        with self.at(600 + 3600 + 1):
            self.assertIsNone(self.cache.get_stale("k"))

    def test_stale_copy_is_replaced_by_newer_value(self):
        self.cache.set("k", "old", 600)
        self.cache.set("k", "new", 600)
        self.assertEqual(self.cache.get_stale("k"), "new")

    def test_get_stale_miss_returns_none(self):
        self.assertIsNone(self.cache.get_stale("never-set"))

    def test_none_is_never_cached(self):
        self.cache.set("k", None, 600)
        self.assertIsNone(self.cache.get_stale("k"))


class MakeKeyTests(OfflineSimpleTestCase):
    def test_nfr_cache1_key_has_endpoint_rounded_coordinates_and_units(self):
        key = WeatherCache.make_key("current", 35.22199, -101.83129, "imperial")
        self.assertEqual(key, "weather:current:35.22:-101.83:imperial")

    def test_nfr_cache1_nearby_coordinates_share_a_key(self):
        self.assertEqual(
            WeatherCache.make_key("forecast", 35.2211, -101.8312, "metric"),
            WeatherCache.make_key("forecast", 35.2249, -101.8349, "metric"),
        )

    def test_nfr_cache1_units_are_part_of_the_key(self):
        self.assertNotEqual(
            WeatherCache.make_key("current", 35.22, -101.83, "imperial"),
            WeatherCache.make_key("current", 35.22, -101.83, "metric"),
        )

    def test_endpoint_is_part_of_the_key(self):
        self.assertNotEqual(
            WeatherCache.make_key("current", 35.22, -101.83, "imperial"),
            WeatherCache.make_key("forecast", 35.22, -101.83, "imperial"),
        )

    def test_accepts_temperature_unit_enum(self):
        self.assertEqual(
            WeatherCache.make_key("current", 1, 2, TemperatureUnit.METRIC),
            "weather:current:1.00:2.00:metric",
        )

    def test_negative_zero_is_normalized(self):
        self.assertEqual(
            WeatherCache.make_key("current", -0.001, -0.004, "metric"),
            WeatherCache.make_key("current", 0.0, 0.0, "metric"),
        )
