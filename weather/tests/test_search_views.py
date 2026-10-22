"""Tests for the search page and search boxes (FR-4, FR-5, FR-6, NFR-FT-1/4, NFR-SEC-1/5).

OpenWeatherClient methods are patched, so the real LocationSearchService and
WeatherCache run while nothing leaves the process. States from state-machine.mmd:
Idle, InvalidInput, NoResults, AwaitingSelection, SearchError.
"""
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.core.cache import cache
from django.test import override_settings
from django.utils.html import escape

from weather.services.client import OpenWeatherClient
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
    ServiceUnavailableError,
)
from weather.tests.base import OfflineTestCase, load_fixture

SEARCH_URL = "/search/"
API_KEY = "test-key"


@override_settings(OPENWEATHER_API_KEY=API_KEY)
class SearchViewTestCase(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.direct = self.patch_client("geocode_direct", load_fixture("geocode_direct_multiple.json"))
        self.zip = self.patch_client("geocode_zip", load_fixture("geocode_zip.json"))

    def patch_client(self, name, return_value):
        patcher = mock.patch.object(OpenWeatherClient, name, return_value=return_value)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def search(self, q):
        return self.client.get(SEARCH_URL, {"q": q})

    def assertNoApiCalls(self):
        self.direct.assert_not_called()
        self.zip.assert_not_called()

    def assertRedirectsToDashboard(self, response, lat, lon):
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response["Location"])
        self.assertEqual(url.path, "/weather/")
        self.assertEqual(parse_qs(url.query), {"lat": [lat], "lon": [lon]})


class SearchBoxTests(SearchViewTestCase):
    def test_fr4_ac1_home_page_has_a_labelled_search_box(self):
        response = self.client.get("/")
        self.assertContains(response, 'action="/search/"', count=2)  # home + nav
        self.assertContains(response, '<label for="id_q"')
        self.assertContains(response, 'name="q"', count=2)

    def test_fr4_ac1_nav_has_a_labelled_search_box_on_every_page(self):
        response = self.client.get("/accounts/login/")
        self.assertContains(response, 'action="/search/"')
        self.assertContains(response, '<label for="nav-search-q"')
        self.assertContains(response, 'role="search"')

    def test_search_forms_use_get_and_limit_length(self):
        response = self.client.get("/")
        self.assertContains(response, 'method="get"', count=2)
        self.assertContains(response, 'maxlength="100"', count=2)


class IdleAndInvalidInputTests(SearchViewTestCase):
    def test_idle_search_page_shows_form_without_errors(self):
        response = self.client.get(SEARCH_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "weather/search.html")
        self.assertNotContains(response, "field-errors")
        self.assertNoApiCalls()

    def test_fr4_ac4_empty_query_shows_validation_message_without_api_call(self):
        for q in ("", "   "):
            with self.subTest(q=q):
                response = self.search(q)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Enter a city name or postal code.", status_code=400)
        self.assertNoApiCalls()

    def test_nfr_ac5_validation_error_is_linked_to_the_field(self):
        response = self.search(" ")
        self.assertContains(response, 'id="id_q_error"', status_code=400)
        self.assertContains(response, 'aria-describedby="id_q_error"', status_code=400)

    def test_nfr_sec5_overlong_query_is_rejected_without_api_call(self):
        response = self.search("a" * 101)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "100 characters", status_code=400)
        self.assertNoApiCalls()

    def test_search_is_get_only(self):
        self.assertEqual(self.client.post(SEARCH_URL, {"q": "Springfield"}).status_code, 405)


class SingleMatchTests(SearchViewTestCase):
    def test_fr4_ac5_single_city_match_redirects_to_its_dashboard(self):
        self.direct.return_value = load_fixture("geocode_direct_single.json")
        response = self.search("Paris, FR")
        self.assertRedirectsToDashboard(response, "48.8589", "2.3200")

    def test_fr5_ac3_valid_postal_code_redirects_to_its_dashboard(self):
        response = self.search("79015")
        self.zip.assert_called_once_with("79015", "US")
        self.assertRedirectsToDashboard(response, "34.9803", "-101.9188")

    def test_fr4_ac4_query_is_trimmed(self):
        self.direct.return_value = load_fixture("geocode_direct_single.json")
        self.search("   Paris, FR  ")
        self.direct.assert_called_once_with("Paris,FR", limit=5)

    def test_fr4_ac2_city_and_state_code_redirects_to_its_dashboard(self):
        """Regression: "Amarillo, TX" showed "No locations found"."""
        self.direct.return_value = [
            {"name": "Amarillo", "lat": 35.2219971, "lon": -101.8312969,
             "country": "US", "state": "Texas"}
        ]
        response = self.search("Amarillo, TX")
        self.direct.assert_called_once_with("Amarillo,TX,US", limit=5)
        self.assertRedirectsToDashboard(response, "35.2220", "-101.8313")


class NoResultsTests(SearchViewTestCase):
    def test_fr4_ac6_no_city_match_shows_message_and_suggestion(self):
        self.direct.return_value = load_fixture("geocode_direct_empty.json")
        response = self.search("Nowhereville")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No locations found")
        self.assertContains(response, "check the spelling")
        self.assertContains(response, "postal code")
        self.assertNotContains(response, "Postal code not found")

    def test_fr5_ac4_unknown_postal_code_shows_postal_code_not_found(self):
        self.zip.side_effect = OpenWeatherError(status_code=404)
        response = self.search("00000")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Postal code not found")
        self.assertNotContains(response, "No locations found")

    def test_no_results_page_keeps_the_query_for_a_new_search(self):
        self.direct.return_value = []
        response = self.search("Nowhereville")
        self.assertContains(response, 'value="Nowhereville"')


class MultipleMatchTests(SearchViewTestCase):
    def test_fr6_ac1_multiple_matches_show_a_results_list(self):
        response = self.search("Springfield")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "weather/search.html")
        self.assertContains(response, "5 locations match")

    def test_fr6_ac2_each_result_shows_name_state_country_and_coordinates(self):
        response = self.search("Springfield")
        self.assertContains(response, "Springfield, Illinois, US")
        self.assertContains(response, "39.80, -89.64")
        self.assertContains(response, "Springfield, Ohio, US")

    def test_fr6_ac2_state_is_omitted_when_missing(self):
        self.direct.return_value = [
            {"name": "Monaco", "lat": 43.7384, "lon": 7.4246, "country": "MC"},
            {"name": "Monaco", "lat": 43.7311, "lon": 7.4197, "country": "MC"},
        ]
        response = self.search("Monaco")
        self.assertContains(response, "Monaco, MC")
        self.assertNotContains(response, "Monaco, , MC")

    def test_fr6_ac3_results_appear_in_api_order(self):
        body = self.search("Springfield").content.decode()
        positions = [body.index(f"Springfield, {s}, US") for s in
                     ("Illinois", "Missouri", "Massachusetts", "Oregon", "Ohio")]
        self.assertEqual(positions, sorted(positions))

    def test_fr6_ac3_at_most_five_results(self):
        self.direct.return_value = load_fixture("geocode_direct_multiple.json") * 2
        response = self.search("Springfield")
        self.assertEqual(len(response.context["results"]), 5)

    def test_fr6_ac4_each_result_links_to_the_dashboard_for_its_coordinates(self):
        response = self.search("Springfield")
        self.assertContains(response, 'href="/weather/?lat=39.7990&amp;lon=-89.6440"')
        self.assertContains(response, 'href="/weather/?lat=37.2082&amp;lon=-93.2923"')

    def test_results_are_an_accessible_list(self):
        response = self.search("Springfield")
        self.assertContains(response, '<ol class="search-results"')
        self.assertContains(response, "<h1", count=1)


class SearchErrorTests(SearchViewTestCase):
    """NFR-FT-1/4: friendly messages, distinct for rate limiting and key problems."""

    def assertFriendlyError(self, error, expected_text):
        self.direct.side_effect = error
        response = self.search("Springfield")
        self.assertEqual(response.status_code, 503)
        self.assertTemplateUsed(response, "weather/search.html")
        # Templates escape apostrophes, so compare against the escaped text.
        self.assertContains(response, escape(expected_text), status_code=503)
        self.assertContains(response, 'role="alert"', status_code=503)
        self.assertNotContains(response, "Traceback", status_code=503)
        return response

    def test_nfr_ft4_rate_limit_has_its_own_message(self):
        self.assertFriendlyError(RateLimitError(status_code=429), "too many requests")

    def test_nfr_ft4_authentication_failure_has_its_own_message(self):
        self.assertFriendlyError(AuthenticationError(status_code=401), "not configured correctly")

    def test_nfr_ft1_unavailable_service_shows_friendly_message(self):
        self.assertFriendlyError(ServiceUnavailableError(), "couldn't reach the weather service")

    def test_nfr_ft1_malformed_response_shows_friendly_message(self):
        self.assertFriendlyError(OpenWeatherError(status_code=200), "couldn't reach the weather service")

    def test_error_page_keeps_the_search_form(self):
        response = self.assertFriendlyError(ServiceUnavailableError(), "couldn't reach")
        self.assertContains(response, 'value="Springfield"', status_code=503)


class SearchSafetyTests(SearchViewTestCase):
    def test_nfr_sec5_query_is_html_escaped(self):
        self.direct.return_value = []
        response = self.search('<script>alert("x")</script>')
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_nfr_sec5_api_data_is_html_escaped(self):
        self.direct.return_value = [
            {"name": "<b>Evil</b>", "lat": 1.0, "lon": 2.0, "country": "US"},
            {"name": "Good", "lat": 3.0, "lon": 4.0, "country": "US"},
        ]
        response = self.search("Evil")
        self.assertNotContains(response, "<b>Evil</b>")
        self.assertContains(response, "&lt;b&gt;Evil&lt;/b&gt;")

    def test_nfr_sec1_api_key_never_appears_in_any_search_page(self):
        pages = [self.search("Springfield"), self.search("")]
        self.direct.return_value = []
        pages.append(self.search("Nowhere"))
        self.direct.side_effect = AuthenticationError(status_code=401)
        pages.append(self.search("Elsewhere"))
        for response in pages:
            self.assertNotIn(API_KEY, response.content.decode())
            self.assertNotIn("api.openweathermap.org", response.content.decode())

    def test_repeat_search_is_served_from_cache(self):
        self.search("Springfield")
        self.search("springfield")
        self.direct.assert_called_once()
