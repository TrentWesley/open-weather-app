"""Tests for LocationSearchService (FR-4, FR-5, FR-6 AC-2/3, FR-7 AC-3, NFR-CACHE-1/2).

OpenWeatherClient is replaced by a Mock, so nothing leaves the process.
"""
from unittest import mock

from django.core.cache import cache
from django.test import override_settings

from weather.services.cache import WeatherCache
from weather.services.client import OpenWeatherClient
from weather.services.domain import Location
from weather.services.exceptions import OpenWeatherError, RateLimitError
from weather.services.search import LocationSearchService
from weather.tests.base import OfflineSimpleTestCase, load_fixture

TTLS = {"geocode": 86400, "current": 600, "forecast": 1800}


@override_settings(OPENWEATHER_API_KEY="test-key", WEATHER_CACHE_TTL=TTLS)
class SearchTestCase(OfflineSimpleTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client_ = mock.Mock(spec=OpenWeatherClient)
        self.client_.geocode_direct.return_value = load_fixture("geocode_direct_multiple.json")
        self.client_.geocode_zip.return_value = load_fixture("geocode_zip.json")
        self.client_.reverse_geocode.return_value = load_fixture("reverse_geocode.json")
        self.cache = WeatherCache()
        self.service = LocationSearchService(client=self.client_, cache=self.cache)

    def assertNoApiCalls(self):
        self.assertEqual(self.client_.method_calls, [])


class QueryValidationTests(SearchTestCase):
    def test_fr4_ac4_empty_query_is_rejected_without_api_call(self):
        for query in ("", "   ", "\t\n"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                self.service.search(query)
        self.assertNoApiCalls()

    def test_nfr_sec5_overlong_query_is_rejected_without_api_call(self):
        with self.assertRaises(ValueError):
            self.service.search("a" * 101)
        self.assertNoApiCalls()

    def test_query_of_exactly_100_characters_is_accepted(self):
        self.service.search("a" * 100)
        self.client_.geocode_direct.assert_called_once()

    def test_fr4_ac4_query_is_trimmed_before_the_api_call(self):
        self.service.search("  Springfield  ")
        self.client_.geocode_direct.assert_called_once_with("Springfield", limit=5)


class CitySearchTests(SearchTestCase):
    def test_fr4_ac3_city_query_uses_direct_geocoding_with_limit_five(self):
        self.service.search("Springfield")
        self.client_.geocode_direct.assert_called_once_with("Springfield", limit=5)
        self.client_.geocode_zip.assert_not_called()

    def test_fr4_ac2_city_state_and_city_country_forms_use_direct_geocoding(self):
        for query in ("Amarillo, TX", "Paris, FR", "Route 66", "St. John's"):
            with self.subTest(query=query):
                self.client_.reset_mock()
                cache.clear()
                self.service.search(query)
                self.client_.geocode_direct.assert_called_once_with(query, limit=5)
                self.client_.geocode_zip.assert_not_called()

    def test_fr6_ac2_results_are_locations_with_name_state_country_and_coordinates(self):
        first = self.service.search("Springfield")[0]
        self.assertEqual(
            first, Location("Springfield", "Illinois", "US", 39.7990175, -89.6439575)
        )

    def test_fr6_ac3_results_keep_api_order(self):
        states = [loc.state for loc in self.service.search("Springfield")]
        self.assertEqual(states, ["Illinois", "Missouri", "Massachusetts", "Oregon", "Ohio"])

    def test_fr6_ac3_at_most_five_results(self):
        extra = load_fixture("geocode_direct_multiple.json")
        self.client_.geocode_direct.return_value = extra + extra
        self.assertEqual(len(self.service.search("Springfield")), 5)

    def test_fr4_ac5_single_match_returns_one_location(self):
        self.client_.geocode_direct.return_value = load_fixture("geocode_direct_single.json")
        self.assertEqual(len(self.service.search("Paris, FR")), 1)

    def test_fr4_ac6_no_match_returns_empty_list(self):
        self.client_.geocode_direct.return_value = load_fixture("geocode_direct_empty.json")
        self.assertEqual(self.service.search("Nowhereville"), [])

    def test_missing_state_becomes_empty_string(self):
        entry = {"name": "Monaco", "lat": 43.73, "lon": 7.42, "country": "MC"}
        self.client_.geocode_direct.return_value = [entry]
        self.assertEqual(self.service.search("Monaco")[0].state, "")

    def test_api_errors_propagate(self):
        self.client_.geocode_direct.side_effect = RateLimitError(status_code=429)
        with self.assertRaises(RateLimitError):
            self.service.search("Springfield")


class PostalSearchTests(SearchTestCase):
    def test_fr5_ac2_postal_code_defaults_country_to_us(self):
        self.service.search("79015")
        self.client_.geocode_zip.assert_called_once_with("79015", "US")
        self.client_.geocode_direct.assert_not_called()

    def test_fr5_ac1_postal_code_with_country(self):
        cases = {
            "79015, US": ("79015", "US"),
            "SW1A 1AA, GB": ("SW1A 1AA", "GB"),
            "sw1a 1aa,gb": ("SW1A 1AA", "GB"),
            "K1A 0B6, ca": ("K1A 0B6", "CA"),
            "75008, FR": ("75008", "FR"),
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.client_.reset_mock()
                cache.clear()
                self.service.search(query)
                self.client_.geocode_zip.assert_called_once_with(*expected)

    def test_fr5_us_zip_plus_four_uses_the_five_digit_zip(self):
        self.service.search("79015-1234")
        self.client_.geocode_zip.assert_called_once_with("79015", "US")

    def test_fr5_ac3_valid_code_returns_location_named_by_the_api(self):
        self.assertEqual(
            self.service.search("79015"), [Location("Canyon", "", "US", 34.9803, -101.9188)]
        )

    def test_fr5_ac4_unknown_code_returns_empty_list(self):
        for status in (404, 400):
            with self.subTest(status=status):
                cache.clear()
                self.client_.geocode_zip.side_effect = OpenWeatherError(status_code=status)
                self.assertEqual(self.service.search("00000"), [])

    def test_other_zip_errors_propagate(self):
        self.client_.geocode_zip.side_effect = RateLimitError(status_code=429)
        with self.assertRaises(RateLimitError):
            self.service.search("79015")


class GeocodeCacheTests(SearchTestCase):
    def test_nfr_cache2_results_are_cached_for_24_hours(self):
        with mock.patch.object(self.cache, "set", wraps=self.cache.set) as cache_set:
            self.service.search("Springfield")
        self.assertEqual(cache_set.call_args.args[2], 86400)

    def test_nfr_cache1_repeat_search_is_served_from_cache(self):
        first = self.service.search("Springfield")
        second = self.service.search("Springfield")
        self.assertEqual(first, second)
        self.client_.geocode_direct.assert_called_once()

    def test_nfr_cache1_cache_key_uses_normalized_query(self):
        self.service.search("Springfield")
        self.service.search("  SPRINGFIELD ")
        self.client_.geocode_direct.assert_called_once()

    def test_postal_cache_key_includes_country(self):
        self.service.search("79015")
        self.service.search("79015, MX")
        self.assertEqual(self.client_.geocode_zip.call_count, 2)

    def test_postal_and_city_entries_do_not_collide(self):
        self.service.search("79015")
        self.client_.geocode_direct.return_value = []
        self.service.search("79015 city")
        self.client_.geocode_direct.assert_called_once()

    def test_empty_city_result_is_cached(self):
        self.client_.geocode_direct.return_value = []
        self.service.search("Nowhereville")
        self.service.search("Nowhereville")
        self.client_.geocode_direct.assert_called_once()

    def test_errors_are_not_cached(self):
        self.client_.geocode_direct.side_effect = [
            RateLimitError(status_code=429),
            load_fixture("geocode_direct_single.json"),
        ]
        with self.assertRaises(RateLimitError):
            self.service.search("Paris")
        self.assertEqual(len(self.service.search("Paris")), 1)

    def test_unknown_postal_code_is_not_cached(self):
        self.client_.geocode_zip.side_effect = [
            OpenWeatherError(status_code=404),
            load_fixture("geocode_zip.json"),
        ]
        self.assertEqual(self.service.search("79015"), [])
        self.assertEqual(len(self.service.search("79015")), 1)


class ResponseValidationTests(SearchTestCase):
    def test_entry_without_coordinates_is_rejected(self):
        self.client_.geocode_direct.return_value = [{"name": "Nowhere", "country": "US"}]
        with self.assertRaises(OpenWeatherError):
            self.service.search("Nowhere")

    def test_entry_with_out_of_range_coordinates_is_rejected(self):
        bad = {"name": "Bad", "lat": 95.0, "lon": 10.0, "country": "US"}
        self.client_.geocode_direct.return_value = [bad]
        with self.assertRaises(OpenWeatherError):
            self.service.search("Bad")

    def test_entry_with_non_numeric_coordinates_is_rejected(self):
        bad = {"name": "Bad", "lat": "north", "lon": 10.0, "country": "US"}
        self.client_.geocode_direct.return_value = [bad]
        with self.assertRaises(OpenWeatherError):
            self.service.search("Bad")

    def test_entry_without_name_is_rejected(self):
        self.client_.geocode_zip.return_value = {"lat": 34.98, "lon": -101.92, "country": "US"}
        with self.assertRaises(OpenWeatherError):
            self.service.search("79015")

    def test_invalid_response_is_not_cached(self):
        self.client_.geocode_direct.return_value = [{"name": "Nowhere"}]
        with self.assertRaises(OpenWeatherError):
            self.service.search("Nowhere")
        self.client_.geocode_direct.return_value = load_fixture("geocode_direct_single.json")
        self.assertEqual(len(self.service.search("Nowhere")), 1)


class ReverseGeocodeTests(SearchTestCase):
    def test_fr7_ac3_reverse_resolves_place_name_for_the_given_coordinates(self):
        location = self.service.reverse(35.2, -101.8)
        self.client_.reverse_geocode.assert_called_once_with(35.2, -101.8)
        self.assertEqual(location, Location("Amarillo", "Texas", "US", 35.2, -101.8))

    def test_reverse_without_a_named_place_falls_back_to_coordinates(self):
        self.client_.reverse_geocode.return_value = []
        location = self.service.reverse(10.5, -140.25)
        self.assertEqual(location, Location("10.50, -140.25", "", "", 10.5, -140.25))

    def test_nfr_sec5_reverse_rejects_out_of_range_coordinates(self):
        for lat, lon in ((90.1, 0), (-90.1, 0), (0, 180.1), (0, -180.1)):
            with self.subTest(lat=lat, lon=lon), self.assertRaises(ValueError):
                self.service.reverse(lat, lon)
        self.assertNoApiCalls()

    def test_nfr_cache2_reverse_results_are_cached(self):
        self.service.reverse(35.221, -101.831)
        self.service.reverse(35.224, -101.834)
        self.client_.reverse_geocode.assert_called_once()

    def test_reverse_errors_propagate(self):
        self.client_.reverse_geocode.side_effect = RateLimitError(status_code=429)
        with self.assertRaises(RateLimitError):
            self.service.reverse(35.2, -101.8)


class IsPostalCodeTests(SearchTestCase):
    """is_postal_code from class.mmd (activity.mmd: "Matches postal-code pattern?")."""

    def test_postal_codes_are_detected(self):
        for query in ("79015", " 79015 ", "79015, US", "79015-1234", "SW1A 1AA, GB", "K1A 0B6"):
            with self.subTest(query=query):
                self.assertTrue(self.service.is_postal_code(query))

    def test_place_names_are_not_postal_codes(self):
        for query in ("Amarillo", "Paris, FR", "Amarillo, TX", "Route 66", "79015, Texas"):
            with self.subTest(query=query):
                self.assertFalse(self.service.is_postal_code(query))
