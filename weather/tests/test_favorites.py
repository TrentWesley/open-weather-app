"""Tests for the favorites list, add and remove endpoints (FR-10, FR-11, NFR-SEC-3/4).

OpenWeather calls are mocked; favorites are created through FavoriteLocation.add.
"""
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from accounts.models import TemperatureUnit
from accounts.preferences import set_unit
from weather.models import FavoriteLocation
from weather.services.client import OpenWeatherClient
from weather.services.domain import Location
from weather.services.exceptions import ServiceUnavailableError
from weather.tests.base import OfflineTestCase, load_fixture

FAVORITES_URL = "/favorites/"
API_KEY = "test-key"
PASSWORD = "Correct-Horse-91"
AMARILLO = Location("Amarillo", "Texas", "US", 35.222, -101.8313)
LONDON = Location("London", "England", "GB", 51.5073, -0.1276)


def place(index: int) -> Location:
    return Location(f"Place {index}", "", "US", 10 + index / 10, -100 - index / 10)


def message_texts(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


@override_settings(OPENWEATHER_API_KEY=API_KEY, OPENWEATHER_ENABLE_ONECALL=False)
class FavoritesTestCase(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.alice = User.objects.create_user("alice", password=PASSWORD)
        self.bob = User.objects.create_user("bob", password=PASSWORD)
        self.client.force_login(self.alice)
        self.current = self.patch_client("current_weather", load_fixture("current_weather.json"))
        self.reverse = self.patch_client("reverse_geocode", load_fixture("reverse_geocode.json"))
        self.forecast = self.patch_client("forecast_5day", load_fixture("forecast_5day.json"))

    def patch_client(self, name, return_value):
        patcher = mock.patch.object(OpenWeatherClient, name, return_value=return_value)
        self.addCleanup(patcher.stop)
        return patcher.start()


class FavoritesPageTests(FavoritesTestCase):
    def test_nfr_sec4_anonymous_user_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(FAVORITES_URL)
        self.assertRedirects(
            response, f"/accounts/login/?next={FAVORITES_URL}", fetch_redirect_response=False
        )

    def test_fr10_ac2_lists_only_the_logged_in_users_favorites(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        FavoriteLocation.add(self.bob, LONDON)
        response = self.client.get(FAVORITES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "weather/favorites.html")
        self.assertContains(response, "Amarillo, Texas, US")
        self.assertNotContains(response, "London")

    def test_fr10_ac3_each_favorite_links_to_its_dashboard(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.get(FAVORITES_URL)
        self.assertContains(
            response, '<a href="/weather/?lat=35.2220&amp;lon=-101.8313"', count=1
        )

    def test_fr10_ac3_each_favorite_shows_current_temperature_and_condition(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.get(FAVORITES_URL)
        self.assertContains(response, "68°F")
        self.assertContains(response, "Light rain")
        self.current.assert_called_once_with(35.222, -101.8313, "imperial")

    def test_fr3_temperatures_use_the_users_unit(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        request = mock.Mock(user=self.alice)
        set_unit(request, TemperatureUnit.METRIC)
        self.client.get(FAVORITES_URL)
        self.current.assert_called_once_with(35.222, -101.8313, "metric")

    def test_nfr_ft3_unavailable_weather_does_not_break_the_page(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        self.current.side_effect = ServiceUnavailableError()
        response = self.client.get(FAVORITES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amarillo, Texas, US")
        self.assertContains(response, "Current weather unavailable")

    def test_nfr_perf4_cached_weather_is_reused(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        self.client.get(FAVORITES_URL)
        self.client.get(FAVORITES_URL)
        self.assertEqual(self.current.call_count, 1)

    def test_nfr_perf6_query_count_does_not_grow_with_the_number_of_favorites(self):
        FavoriteLocation.add(self.alice, place(0))
        self.client.get(FAVORITES_URL)  # Warm up: the first request creates the profile.
        with CaptureQueriesContext(connection) as one:
            self.client.get(FAVORITES_URL)
        for index in range(1, 20):
            FavoriteLocation.add(self.alice, place(index))
        with CaptureQueriesContext(connection) as twenty:
            response = self.client.get(FAVORITES_URL)
        self.assertContains(response, "Place 19")
        self.assertEqual(len(twenty), len(one))

    def test_fr10_ac6_page_shows_how_many_of_twenty_are_saved(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        FavoriteLocation.add(self.alice, LONDON)
        response = self.client.get(FAVORITES_URL)
        self.assertContains(response, "2 of 20 saved")

    def test_fr10_ac7_empty_state_links_to_search(self):
        response = self.client.get(FAVORITES_URL)
        self.assertContains(response, "You haven't saved any locations yet.")
        self.assertContains(response, 'href="/search/"')
        self.current.assert_not_called()

    def test_page_has_one_heading_and_a_nav_link(self):
        response = self.client.get(FAVORITES_URL)
        self.assertContains(response, "<h1", count=1)
        self.assertContains(response, '<a href="/favorites/">Favorites</a>', html=True)

    def test_nav_link_is_only_for_signed_in_users(self):
        self.client.logout()
        response = self.client.get("/")
        self.assertNotContains(response, 'href="/favorites/"')

    def test_nfr_sec5_saved_names_are_escaped(self):
        FavoriteLocation.add(self.alice, Location("<b>Evil</b>", "", "", 1, 1))
        response = self.client.get(FAVORITES_URL)
        self.assertNotContains(response, "<b>Evil</b>")
        self.assertContains(response, "&lt;b&gt;Evil&lt;/b&gt;")

    def test_nfr_sec1_page_never_contains_the_api_key(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.get(FAVORITES_URL)
        self.assertNotContains(response, API_KEY)
