"""Tests for WeatherService current weather and forecast retrieval.

FR-3 AC-2, FR-8 AC-1/4, FR-9 AC-1, NFR-PERF-3, NFR-CACHE-1/2/4, NFR-FT-2/3.
OpenWeatherClient is replaced by a Mock; "now" is patched instead of sleeping.
"""
import time
from datetime import UTC, datetime, timedelta, timezone
from unittest import mock

from django.core.cache import cache
from django.test import override_settings

from accounts.models import TemperatureUnit
from weather.services.cache import WeatherCache
from weather.services.client import OpenWeatherClient
from weather.services.domain import CurrentWeather, Forecast, ForecastEntry, Location
from weather.services.exceptions import (
    OpenWeatherError,
    RateLimitError,
    ServiceUnavailableError,
)
from weather.services.weather import WeatherService
from weather.tests.base import OfflineSimpleTestCase, load_fixture

TTLS = {"geocode": 86400, "current": 600, "forecast": 1800}
AMARILLO = Location("Amarillo", "Texas", "US", 35.222, -101.8313)
LOCAL = timezone(timedelta(hours=-5))
NOW = datetime(2026, 10, 22, 20, 0, tzinfo=UTC)


@override_settings(
    OPENWEATHER_API_KEY="test-key",
    OPENWEATHER_ENABLE_ONECALL=False,
    WEATHER_CACHE_TTL=TTLS,
    WEATHER_CACHE_STALE_TTL=3600,
)
class WeatherServiceTestCase(OfflineSimpleTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client_ = mock.Mock(spec=OpenWeatherClient)
        self.client_.current_weather.return_value = load_fixture("current_weather.json")
        self.client_.forecast_5day.return_value = load_fixture("forecast_5day.json")
        self.client_.uv_index.return_value = 6.2
        self.cache = WeatherCache()
        self.service = WeatherService(client=self.client_, cache=self.cache)
        now = mock.patch("weather.services.weather.timezone.now", return_value=NOW)
        now.start()
        self.addCleanup(now.stop)

    def expire_fresh_entries(self):
        """Move LocMemCache's clock past the fresh TTLs but inside the stale window."""
        later = time.time() + 1801
        patcher = mock.patch("time.time", return_value=later)
        patcher.start()
        self.addCleanup(patcher.stop)


class CurrentWeatherTests(WeatherServiceTestCase):
    def test_fr8_ac1_returns_current_weather_with_all_metrics(self):
        weather = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertIsInstance(weather, CurrentWeather)
        self.assertEqual(weather.location, AMARILLO)
        self.assertEqual(weather.temperature, 68.4)
        self.assertEqual(weather.feels_like, 67.9)
        self.assertEqual((weather.temp_min, weather.temp_max), (65.1, 71.6))
        self.assertEqual(weather.description, "light rain")
        self.assertEqual(weather.icon, "10d")
        self.assertEqual(weather.humidity, 64)
        self.assertEqual(weather.wind_speed, 12.66)
        self.assertEqual(weather.wind_deg, 315)
        self.assertEqual(weather.pressure, 1014)
        self.assertEqual(weather.visibility, 10000)
        self.assertEqual(weather.clouds, 75)

    def test_fr8_ac1_sunrise_and_sunset_are_in_the_locations_time_zone(self):
        weather = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(weather.sunrise, datetime.fromtimestamp(1792672862, LOCAL))
        self.assertEqual(weather.sunset, datetime.fromtimestamp(1792713421, LOCAL))
        self.assertEqual(weather.sunrise.utcoffset(), timedelta(hours=-5))

    def test_nfr_cache4_records_when_the_data_was_retrieved(self):
        weather = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(weather.retrieved_at, NOW)
        self.assertFalse(weather.is_stale)

    def test_fr3_ac2_requests_the_users_units(self):
        self.service.current(AMARILLO, TemperatureUnit.METRIC)
        self.client_.current_weather.assert_called_once_with(35.222, -101.8313, "metric")

    def test_accepts_unit_as_plain_string(self):
        self.service.current(AMARILLO, "imperial")
        self.client_.current_weather.assert_called_once_with(35.222, -101.8313, "imperial")

    def test_nfr_perf3_one_current_weather_call_per_request(self):
        self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(self.client_.current_weather.call_count, 1)
        self.client_.forecast_5day.assert_not_called()


class UvIndexTests(WeatherServiceTestCase):
    def test_fr8_ac4_uv_index_is_none_without_one_call(self):
        weather = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertIsNone(weather.uv_index)
        self.client_.uv_index.assert_not_called()

    @override_settings(OPENWEATHER_ENABLE_ONECALL=True)
    def test_fr8_ac4_uv_index_comes_from_one_call_when_enabled(self):
        weather = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(weather.uv_index, 6.2)
        self.client_.uv_index.assert_called_once_with(35.222, -101.8313)

    @override_settings(OPENWEATHER_ENABLE_ONECALL=True)
    def test_one_call_is_requested_after_current_weather(self):
        self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        names = [call[0] for call in self.client_.method_calls]
        self.assertEqual(names, ["current_weather", "uv_index"])

    @override_settings(OPENWEATHER_ENABLE_ONECALL=True)
    def test_fr8_ac4_one_call_failure_leaves_other_metrics_intact(self):
        self.client_.uv_index.side_effect = RateLimitError(status_code=429)
        weather = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertIsNone(weather.uv_index)
        self.assertEqual(weather.temperature, 68.4)

    @override_settings(OPENWEATHER_ENABLE_ONECALL=True)
    def test_one_call_is_skipped_when_current_weather_fails(self):
        self.client_.current_weather.side_effect = ServiceUnavailableError(status_code=503)
        with self.assertRaises(ServiceUnavailableError):
            self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.client_.uv_index.assert_not_called()


class CurrentWeatherCacheTests(WeatherServiceTestCase):
    def test_nfr_cache2_current_weather_is_cached_for_10_minutes(self):
        with mock.patch.object(self.cache, "set", wraps=self.cache.set) as cache_set:
            self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        key, _, ttl = cache_set.call_args.args
        self.assertEqual(key, "weather:current:35.22:-101.83:imperial")
        self.assertEqual(ttl, 600)

    def test_nfr_cache1_repeat_request_is_served_from_cache(self):
        first = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        second = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(first, second)
        self.client_.current_weather.assert_called_once()

    def test_nfr_cache1_units_are_cached_separately(self):
        self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.service.current(AMARILLO, TemperatureUnit.METRIC)
        self.assertEqual(self.client_.current_weather.call_count, 2)

    def test_nfr_ft2_stale_data_is_served_when_the_api_fails(self):
        self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.expire_fresh_entries()
        self.client_.current_weather.side_effect = ServiceUnavailableError(status_code=503)
        weather = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertTrue(weather.is_stale)
        self.assertEqual(weather.retrieved_at, NOW)
        self.assertEqual(weather.temperature, 68.4)

    def test_nfr_ft1_error_is_raised_when_no_stale_data_exists(self):
        self.client_.current_weather.side_effect = RateLimitError(status_code=429)
        with self.assertRaises(RateLimitError):
            self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)

    def test_stale_data_is_not_used_while_fresh_data_is_cached(self):
        self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertFalse(self.service.current(AMARILLO, TemperatureUnit.IMPERIAL).is_stale)

    def test_api_is_retried_on_the_next_request_after_serving_stale_data(self):
        self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.expire_fresh_entries()
        self.client_.current_weather.side_effect = [
            ServiceUnavailableError(status_code=503),
            load_fixture("current_weather.json"),
        ]
        self.assertTrue(self.service.current(AMARILLO, TemperatureUnit.IMPERIAL).is_stale)
        self.assertFalse(self.service.current(AMARILLO, TemperatureUnit.IMPERIAL).is_stale)


class CurrentWeatherValidationTests(WeatherServiceTestCase):
    def payload_without(self, *path):
        data = load_fixture("current_weather.json")
        target = data
        for part in path[:-1]:
            target = target[part]
        del target[path[-1]]
        return data

    def test_missing_required_fields_raise_openweather_error(self):
        for path in (("main", "temp"), ("weather",), ("sys", "sunrise"), ("timezone",)):
            with self.subTest(path=path):
                cache.clear()
                self.client_.current_weather.return_value = self.payload_without(*path)
                with self.assertRaises(OpenWeatherError):
                    self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)

    def test_non_numeric_temperature_raises_openweather_error(self):
        data = load_fixture("current_weather.json")
        data["main"]["temp"] = "warm"
        self.client_.current_weather.return_value = data
        with self.assertRaises(OpenWeatherError):
            self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)

    def test_malformed_response_falls_back_to_stale_data(self):
        self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.expire_fresh_entries()
        self.client_.current_weather.return_value = self.payload_without("main")
        self.assertTrue(self.service.current(AMARILLO, TemperatureUnit.IMPERIAL).is_stale)

    def test_malformed_response_is_not_cached(self):
        self.client_.current_weather.return_value = self.payload_without("main")
        with self.assertRaises(OpenWeatherError):
            self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertIsNone(self.cache.get_stale("weather:current:35.22:-101.83:imperial"))


class ForecastTests(WeatherServiceTestCase):
    def test_fr9_ac1_returns_forecast_with_3_hour_entries(self):
        forecast = self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertIsInstance(forecast, Forecast)
        self.assertEqual(forecast.location, AMARILLO)
        self.assertEqual(len(forecast.entries), 10)
        steps = {b.timestamp - a.timestamp for a, b in zip(forecast.entries, forecast.entries[1:])}
        self.assertEqual(steps, {timedelta(hours=3)})

    def test_fr9_entries_carry_temperature_pop_icon_and_description(self):
        first = self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL).entries[0]
        self.assertEqual(
            first,
            ForecastEntry(
                timestamp=datetime(2026, 10, 22, 10, 0, tzinfo=LOCAL),
                temperature=70.2,
                pop=0.0,
                precipitation_mm=0.0,
                icon="03d",
                description="scattered clouds",
            ),
        )

    def test_fr9_entry_times_are_in_the_locations_time_zone(self):
        entries = self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL).entries
        self.assertTrue(all(e.timestamp.utcoffset() == timedelta(hours=-5) for e in entries))

    def test_fr9_precipitation_adds_rain_and_snow(self):
        entries = self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL).entries
        self.assertEqual(entries[3].precipitation_mm, 1.25)
        self.assertEqual(entries[4].precipitation_mm, 3.0)
        self.assertEqual(entries[4].pop, 0.8)

    def test_fr3_ac2_requests_the_users_units(self):
        self.service.forecast(AMARILLO, TemperatureUnit.METRIC)
        self.client_.forecast_5day.assert_called_once_with(35.222, -101.8313, "metric")

    def test_nfr_cache4_records_when_the_data_was_retrieved(self):
        forecast = self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(forecast.retrieved_at, NOW)
        self.assertFalse(forecast.is_stale)

    def test_nfr_perf3_one_forecast_call_per_request(self):
        self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(self.client_.forecast_5day.call_count, 1)
        self.client_.current_weather.assert_not_called()


class ForecastCacheTests(WeatherServiceTestCase):
    def test_nfr_cache2_forecast_is_cached_for_30_minutes(self):
        with mock.patch.object(self.cache, "set", wraps=self.cache.set) as cache_set:
            self.service.forecast(AMARILLO, TemperatureUnit.METRIC)
        key, _, ttl = cache_set.call_args.args
        self.assertEqual(key, "weather:forecast:35.22:-101.83:metric")
        self.assertEqual(ttl, 1800)

    def test_nfr_cache1_repeat_request_is_served_from_cache(self):
        self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.client_.forecast_5day.assert_called_once()

    def test_nfr_ft2_stale_forecast_is_served_when_the_api_fails(self):
        self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.expire_fresh_entries()
        self.client_.forecast_5day.side_effect = ServiceUnavailableError()
        forecast = self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertTrue(forecast.is_stale)
        self.assertEqual(len(forecast.entries), 10)

    def test_nfr_ft1_error_is_raised_when_no_stale_forecast_exists(self):
        self.client_.forecast_5day.side_effect = ServiceUnavailableError()
        with self.assertRaises(ServiceUnavailableError):
            self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)

    def test_nfr_ft3_forecast_failure_does_not_affect_current_weather(self):
        self.client_.forecast_5day.side_effect = ServiceUnavailableError()
        with self.assertRaises(ServiceUnavailableError):
            self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)
        self.assertEqual(self.service.current(AMARILLO, TemperatureUnit.IMPERIAL).temperature, 68.4)


class ForecastValidationTests(WeatherServiceTestCase):
    def test_empty_entry_list_raises_openweather_error(self):
        data = load_fixture("forecast_5day.json")
        data["list"] = []
        self.client_.forecast_5day.return_value = data
        with self.assertRaises(OpenWeatherError):
            self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)

    def test_missing_city_timezone_raises_openweather_error(self):
        data = load_fixture("forecast_5day.json")
        del data["city"]["timezone"]
        self.client_.forecast_5day.return_value = data
        with self.assertRaises(OpenWeatherError):
            self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)

    def test_entry_missing_temperature_raises_openweather_error(self):
        data = load_fixture("forecast_5day.json")
        del data["list"][2]["main"]["temp"]
        self.client_.forecast_5day.return_value = data
        with self.assertRaises(OpenWeatherError):
            self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)

    def test_out_of_range_pop_raises_openweather_error(self):
        data = load_fixture("forecast_5day.json")
        data["list"][0]["pop"] = 1.5
        self.client_.forecast_5day.return_value = data
        with self.assertRaises(OpenWeatherError):
            self.service.forecast(AMARILLO, TemperatureUnit.IMPERIAL)


class CurrentManyTests(WeatherServiceTestCase):
    """FR-10 AC-3, NFR-PERF-4: current weather for every favorite on one page."""

    PLACES = [Location(f"Place {i}", "", "US", 10.0 + i, -100.0 - i) for i in range(4)]

    def test_fr10_ac3_returns_weather_for_each_location_in_order(self):
        results = self.service.current_many(self.PLACES, TemperatureUnit.IMPERIAL)
        self.assertEqual([weather.location for weather in results], self.PLACES)
        self.assertTrue(all(isinstance(weather, CurrentWeather) for weather in results))

    def test_nfr_perf4_cached_locations_are_not_fetched_again(self):
        self.service.current(self.PLACES[1], TemperatureUnit.IMPERIAL)
        self.client_.current_weather.reset_mock()
        self.service.current_many(self.PLACES, TemperatureUnit.IMPERIAL)
        fetched = {call.args[:2] for call in self.client_.current_weather.call_args_list}
        self.assertEqual(len(fetched), 3)
        self.assertNotIn((11.0, -101.0), fetched)

    def test_nfr_perf4_uncached_locations_are_fetched_concurrently(self):
        self.assertGreater(WeatherService.MAX_PARALLEL_REQUESTS, 1)
        with mock.patch("weather.services.weather.ThreadPoolExecutor") as executor:
            executor.return_value.__enter__.return_value.map.side_effect = map
            self.service.current_many(self.PLACES, TemperatureUnit.IMPERIAL)
        executor.assert_called_once_with(max_workers=WeatherService.MAX_PARALLEL_REQUESTS)

    def test_nfr_ft3_one_failure_does_not_hide_the_others(self):
        good = load_fixture("current_weather.json")
        self.client_.current_weather.side_effect = lambda lat, lon, units: (
            (_ for _ in ()).throw(ServiceUnavailableError()) if lat == 12.0 else good
        )
        results = self.service.current_many(self.PLACES, TemperatureUnit.IMPERIAL)
        self.assertIsNone(results[2])
        self.assertEqual(sum(weather is not None for weather in results), 3)

    def test_empty_list_makes_no_requests(self):
        self.assertEqual(self.service.current_many([], TemperatureUnit.METRIC), [])
        self.client_.current_weather.assert_not_called()


class CachedCurrentTests(WeatherServiceTestCase):
    """FR-12 AC-5 with NFR-PERF-3: dashboard map markers use cached weather only."""

    def test_returns_none_without_calling_openweather_when_not_cached(self):
        self.assertIsNone(self.service.cached_current(AMARILLO, TemperatureUnit.IMPERIAL))
        self.client_.current_weather.assert_not_called()

    def test_returns_cached_weather_for_the_same_unit(self):
        fresh = self.service.current(AMARILLO, TemperatureUnit.IMPERIAL)
        self.client_.current_weather.reset_mock()
        self.assertEqual(self.service.cached_current(AMARILLO, TemperatureUnit.IMPERIAL), fresh)
        self.assertIsNone(self.service.cached_current(AMARILLO, TemperatureUnit.METRIC))
        self.client_.current_weather.assert_not_called()
