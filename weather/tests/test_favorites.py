"""Tests for the favorites list, add and remove endpoints (FR-10, FR-11, NFR-SEC-3/4).

OpenWeather calls are mocked; favorites are created through FavoriteLocation.add.
"""
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.cache import cache
from django.db import connection
from django.test import Client, override_settings
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

    def test_fr10_ac4_each_favorite_has_a_post_remove_button(self):
        favorite = FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.get(FAVORITES_URL)
        self.assertContains(
            response, f'<form method="post" action="/favorites/{favorite.pk}/delete/"'
        )
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "Remove<span class=\"visually-hidden\"> Amarillo, Texas, US")

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


DASHBOARD_PAGE = "/weather/?lat=35.2220&lon=-101.8313"
JSON = {"HTTP_ACCEPT": "application/json"}


def save_data(location=AMARILLO, next_url=DASHBOARD_PAGE, **overrides):
    data = {
        "name": location.name,
        "state": location.state,
        "country": location.country,
        "lat": str(location.latitude),
        "lon": str(location.longitude),
        "next": next_url,
    }
    data.update(overrides)
    return data


class AddFavoriteTests(FavoritesTestCase):
    def saved(self, user=None):
        return list(FavoriteLocation.objects.filter(user=user or self.alice))

    def test_fr11_ac3_form_post_saves_and_returns_to_the_page(self):
        response = self.client.post(FAVORITES_URL, save_data())
        self.assertRedirects(response, DASHBOARD_PAGE, fetch_redirect_response=False)
        self.assertEqual([str(f) for f in self.saved()], ["Amarillo, Texas, US"])
        self.assertIn("Saved Amarillo, Texas, US to favorites.", message_texts(response))

    def test_fr11_ac3_fetch_post_returns_201_json_with_the_remove_url(self):
        response = self.client.post(FAVORITES_URL, save_data(), **JSON)
        self.assertEqual(response.status_code, 201)
        favorite = self.saved()[0]
        self.assertEqual(
            response.json(),
            {
                "message": "Saved Amarillo, Texas, US to favorites.",
                "delete_url": f"/favorites/{favorite.pk}/delete/",
            },
        )
        # No flash message is queued for the next full page load.
        self.assertEqual(message_texts(response), [])

    def test_fr10_ac5_coordinates_are_rounded_before_saving(self):
        self.client.post(FAVORITES_URL, save_data(lat="35.22199", lon="-101.83129"), **JSON)
        favorite = self.saved()[0]
        self.assertEqual(
            (str(favorite.latitude), str(favorite.longitude)), ("35.2220", "-101.8313")
        )

    def test_fr10_ac5_duplicate_returns_409_already_in_favorites(self):
        favorite = FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.post(FAVORITES_URL, save_data(lat="35.22201"), **JSON)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"message": "Already in favorites", "delete_url": f"/favorites/{favorite.pk}/delete/"},
        )
        self.assertEqual(len(self.saved()), 1)

    def test_fr10_ac5_duplicate_form_post_shows_already_in_favorites(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.post(FAVORITES_URL, save_data())
        self.assertRedirects(response, DASHBOARD_PAGE, fetch_redirect_response=False)
        self.assertEqual(message_texts(response), ["Already in favorites"])

    def test_fr10_ac6_twenty_first_favorite_returns_400_with_a_limit_message(self):
        for index in range(20):
            FavoriteLocation.add(self.alice, place(index))
        response = self.client.post(FAVORITES_URL, save_data(), **JSON)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["message"],
            "Favorites limit reached. You can save up to 20 locations; "
            "remove one to add another.",
        )
        self.assertEqual(len(self.saved()), 20)

    def test_fr10_ac6_limit_form_post_shows_the_limit_message(self):
        for index in range(20):
            FavoriteLocation.add(self.alice, place(index))
        response = self.client.post(FAVORITES_URL, save_data())
        self.assertRedirects(response, DASHBOARD_PAGE, fetch_redirect_response=False)
        self.assertIn("Favorites limit reached", message_texts(response)[0])

    def test_fr11_ac4_anonymous_form_post_goes_to_login_then_back_to_the_page(self):
        self.client.logout()
        response = self.client.post(FAVORITES_URL, save_data())
        self.assertRedirects(
            response,
            "/accounts/login/?next=/weather/%3Flat%3D35.2220%26lon%3D-101.8313",
            fetch_redirect_response=False,
        )
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_fr11_ac4_anonymous_fetch_gets_401_with_the_login_url(self):
        self.client.logout()
        response = self.client.post(FAVORITES_URL, save_data(), **JSON)
        self.assertEqual(response.status_code, 401)
        login = urlsplit(response.json()["login_url"])
        self.assertEqual(login.path, "/accounts/login/")
        self.assertEqual(parse_qs(login.query), {"next": [DASHBOARD_PAGE]})
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_nfr_sec8_unsafe_next_falls_back_to_the_favorites_page(self):
        response = self.client.post(FAVORITES_URL, save_data(next_url="https://evil.example/"))
        self.assertRedirects(response, FAVORITES_URL, fetch_redirect_response=False)
        self.client.logout()
        response = self.client.post(FAVORITES_URL, save_data(next_url="//evil.example/"))
        self.assertRedirects(response, "/accounts/login/?next=/", fetch_redirect_response=False)

    def test_nfr_sec5_invalid_locations_are_rejected(self):
        cases = (
            {"lat": "91"},
            {"lon": "-180.1"},
            {"lat": "nan"},
            {"lat": ""},
            {"name": ""},
            {"name": "x" * 101},
            {"state": "x" * 101},
            {"country": "x" * 101},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                response = self.client.post(FAVORITES_URL, save_data(**overrides), **JSON)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(), {"message": "That location couldn't be saved."}
                )
        response = self.client.post(FAVORITES_URL, save_data(lat="91"))
        self.assertRedirects(response, DASHBOARD_PAGE, fetch_redirect_response=False)
        self.assertEqual(message_texts(response), ["That location couldn't be saved."])
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_nfr_sec4_favorite_is_always_saved_for_the_requesting_user(self):
        self.client.post(FAVORITES_URL, save_data(user=str(self.bob.pk)), **JSON)
        self.assertEqual(len(self.saved()), 1)
        self.assertEqual(self.saved(self.bob), [])

    def test_nfr_sec3_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        response = client.post(FAVORITES_URL, save_data(), **JSON)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_other_methods_are_not_allowed(self):
        self.assertEqual(self.client.put(FAVORITES_URL).status_code, 405)
        self.assertEqual(self.client.delete(FAVORITES_URL).status_code, 405)

    def test_saving_makes_no_openweather_calls(self):
        self.client.post(FAVORITES_URL, save_data(), **JSON)
        self.current.assert_not_called()
        self.reverse.assert_not_called()


class RemoveFavoriteTests(FavoritesTestCase):
    def setUp(self):
        super().setUp()
        self.favorite = FavoriteLocation.add(self.alice, AMARILLO)
        self.url = f"/favorites/{self.favorite.pk}/delete/"

    def test_fr10_ac4_post_removes_and_confirms(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, FAVORITES_URL, fetch_redirect_response=False)
        self.assertFalse(FavoriteLocation.objects.exists())
        self.assertEqual(message_texts(response), ["Removed Amarillo, Texas, US from favorites."])

    def test_fr11_ac2_form_post_returns_to_the_page_it_came_from(self):
        response = self.client.post(self.url, {"next": DASHBOARD_PAGE})
        self.assertRedirects(response, DASHBOARD_PAGE, fetch_redirect_response=False)

    def test_nfr_sec8_unsafe_next_falls_back_to_the_favorites_page(self):
        response = self.client.post(self.url, {"next": "https://evil.example/"})
        self.assertRedirects(response, FAVORITES_URL, fetch_redirect_response=False)

    def test_fr11_ac3_fetch_remove_returns_json(self):
        response = self.client.post(self.url, **JSON)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"message": "Removed Amarillo, Texas, US from favorites."}
        )
        self.assertEqual(message_texts(response), [])
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_nfr_sec4_another_users_favorite_is_404_and_untouched(self):
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, **JSON).status_code, 404)
        self.assertTrue(FavoriteLocation.objects.filter(pk=self.favorite.pk).exists())

    def test_missing_favorite_is_404(self):
        response = self.client.post(f"/favorites/{self.favorite.pk + 100}/delete/")
        self.assertEqual(response.status_code, 404)

    def test_nfr_sec3_remove_is_post_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertTrue(FavoriteLocation.objects.exists())

    def test_nfr_sec3_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        self.assertEqual(client.post(self.url).status_code, 403)
        self.assertTrue(FavoriteLocation.objects.exists())

    def test_fr11_ac4_anonymous_user_goes_to_login_then_back_to_the_page(self):
        self.client.logout()
        response = self.client.post(self.url, {"next": DASHBOARD_PAGE})
        login = urlsplit(response["Location"])
        self.assertEqual((response.status_code, login.path), (302, "/accounts/login/"))
        self.assertEqual(parse_qs(login.query), {"next": [DASHBOARD_PAGE]})
        self.assertEqual(self.client.post(self.url, **JSON).status_code, 401)
        self.assertTrue(FavoriteLocation.objects.exists())

    def test_removing_from_the_favorites_page_shows_the_updated_list(self):
        response = self.client.post(self.url, {"next": FAVORITES_URL}, follow=True)
        self.assertContains(response, "Removed Amarillo, Texas, US from favorites.")
        self.assertContains(response, "You haven't saved any locations yet.")
