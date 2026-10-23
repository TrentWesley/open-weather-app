"""Tests for "Save to favorites" on search results and the dashboard (FR-11, FR-6 AC-5).

The buttons are plain POST forms, so bookmarking works without JavaScript
(NFR-FT-6); favorites.js enhances them in place. OpenWeather calls are mocked.
"""
from html.parser import HTMLParser
from unittest import mock

from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.test import override_settings

from weather.models import FavoriteLocation
from weather.services.client import OpenWeatherClient
from weather.services.domain import Location
from weather.services.exceptions import ServiceUnavailableError
from weather.tests.base import OfflineTestCase, load_fixture

API_KEY = "test-key"
SEARCH_PAGE = "/search/?q=Springfield"
DASHBOARD_PAGE = "/weather/?lat=35.2220&lon=-101.8313"
MISSOURI = Location("Springfield", "Missouri", "US", 37.2081729, -93.2922715)
AMARILLO = Location("Amarillo", "Texas", "US", 35.222, -101.8313)


class FormCollector(HTMLParser):
    """Collect each <form>'s attributes, input values and button text."""

    def __init__(self):
        super().__init__()
        self.forms = []
        self._button = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.forms.append({"attrs": attrs, "inputs": {}, "buttons": []})
        elif tag == "input" and self.forms:
            self.forms[-1]["inputs"][attrs.get("name")] = attrs.get("value", "")
        elif tag == "button" and self.forms:
            self._button = []

    def handle_data(self, data):
        if self._button is not None:
            self._button.append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._button is not None:
            self.forms[-1]["buttons"].append(" ".join("".join(self._button).split()))
            self._button = None


def forms_marked(response, marker):
    collector = FormCollector()
    collector.feed(response.content.decode())
    return [form for form in collector.forms if marker in form["attrs"]]


@override_settings(OPENWEATHER_API_KEY=API_KEY, OPENWEATHER_ENABLE_ONECALL=False)
class BookmarkTestCase(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.alice = User.objects.create_user("alice", password="Correct-Horse-91")
        self.bob = User.objects.create_user("bob", password="Correct-Horse-91")
        self.client.force_login(self.alice)
        for name, fixture in (
            ("geocode_direct", "geocode_direct_multiple.json"),
            ("reverse_geocode", "reverse_geocode.json"),
            ("current_weather", "current_weather.json"),
            ("forecast_5day", "forecast_5day.json"),
        ):
            patcher = mock.patch.object(OpenWeatherClient, name, return_value=load_fixture(fixture))
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)


class SearchResultBookmarkTests(BookmarkTestCase):
    def test_fr11_ac1_each_result_has_a_save_to_favorites_form(self):
        response = self.client.get(SEARCH_PAGE)
        saves = forms_marked(response, "data-favorite-save")
        self.assertEqual(len(saves), 5)
        first = saves[0]
        self.assertEqual((first["attrs"]["method"], first["attrs"]["action"]), ("post", "/favorites/"))
        self.assertEqual(
            {key: first["inputs"][key] for key in ("name", "state", "country", "lat", "lon", "next")},
            {
                "name": "Springfield",
                "state": "Illinois",
                "country": "US",
                "lat": "39.7990175",
                "lon": "-89.6439575",
                "next": SEARCH_PAGE,
            },
        )
        self.assertIn("csrfmiddlewaretoken", first["inputs"])
        self.assertNotIn("hidden", first["attrs"])

    def test_nfr_ac_buttons_have_distinct_accessible_names(self):
        saves = forms_marked(self.client.get(SEARCH_PAGE), "data-favorite-save")
        self.assertEqual(saves[1]["buttons"], ["Save to favorites Springfield, Missouri, US"])
        self.assertEqual(len({form["buttons"][0] for form in saves}), 5)

    def test_fr11_ac4_anonymous_visitors_see_the_button_too(self):
        self.client.logout()
        self.assertEqual(len(forms_marked(self.client.get(SEARCH_PAGE), "data-favorite-save")), 5)

    def test_fr11_ac2_saved_result_shows_saved_with_a_remove_option(self):
        favorite = FavoriteLocation.add(self.alice, MISSOURI)
        response = self.client.get(SEARCH_PAGE)
        saves = forms_marked(response, "data-favorite-save")
        removes = forms_marked(response, "data-favorite-remove")
        self.assertIn("hidden", saves[1]["attrs"])
        self.assertNotIn("hidden", removes[1]["attrs"])
        self.assertEqual(removes[1]["attrs"]["action"], f"/favorites/{favorite.pk}/delete/")
        self.assertEqual(removes[1]["buttons"], ["Remove from favorites Springfield, Missouri, US"])
        self.assertEqual(removes[1]["inputs"]["next"], SEARCH_PAGE)
        # The other results are not saved.
        self.assertNotIn("hidden", saves[0]["attrs"])
        self.assertIn("hidden", removes[0]["attrs"])
        self.assertNotIn("action", removes[0]["attrs"])
        self.assertContains(response, ">Saved<", count=5)

    def test_nfr_sec4_another_users_favorites_do_not_show_as_saved(self):
        FavoriteLocation.add(self.bob, MISSOURI)
        removes = forms_marked(self.client.get(SEARCH_PAGE), "data-favorite-remove")
        self.assertTrue(all("hidden" in form["attrs"] for form in removes))

    def test_nfr_perf6_saved_state_is_looked_up_in_one_query(self):
        FavoriteLocation.add(self.alice, MISSOURI)
        self.client.get(SEARCH_PAGE)  # Warm up: the first request creates the profile.
        with self.assertNumQueries(3):  # session, user, favorites
            self.client.get(SEARCH_PAGE)


class DashboardBookmarkTests(BookmarkTestCase):
    def test_fr11_ac2_dashboard_has_a_save_to_favorites_form(self):
        response = self.client.get(DASHBOARD_PAGE)
        (save,) = forms_marked(response, "data-favorite-save")
        self.assertEqual(save["attrs"]["action"], "/favorites/")
        self.assertEqual(
            {key: save["inputs"][key] for key in ("name", "state", "country", "lat", "lon", "next")},
            {
                "name": "Amarillo",
                "state": "Texas",
                "country": "US",
                "lat": "35.222",
                "lon": "-101.8313",
                "next": DASHBOARD_PAGE,
            },
        )
        self.assertEqual(save["buttons"], ["Save to favorites Amarillo, Texas, US"])

    def test_fr11_ac2_saved_location_shows_saved_and_remove(self):
        favorite = FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.get(DASHBOARD_PAGE)
        (save,) = forms_marked(response, "data-favorite-save")
        (remove,) = forms_marked(response, "data-favorite-remove")
        self.assertIn("hidden", save["attrs"])
        self.assertNotIn("hidden", remove["attrs"])
        self.assertEqual(remove["attrs"]["action"], f"/favorites/{favorite.pk}/delete/")

    def test_fr10_ac5_nearby_coordinates_that_round_the_same_count_as_saved(self):
        FavoriteLocation.add(self.alice, AMARILLO)
        response = self.client.get("/weather/", {"lat": "35.22204", "lon": "-101.83126"})
        (remove,) = forms_marked(response, "data-favorite-remove")
        self.assertNotIn("hidden", remove["attrs"])

    def test_fr11_ac3_no_js_save_then_remove_round_trip(self):
        (save,) = forms_marked(self.client.get(DASHBOARD_PAGE), "data-favorite-save")
        response = self.client.post(save["attrs"]["action"], save["inputs"], follow=True)
        self.assertEqual(response.redirect_chain[-1][0], DASHBOARD_PAGE)
        self.assertContains(response, "Saved Amarillo, Texas, US to favorites.")
        (remove,) = forms_marked(response, "data-favorite-remove")
        self.assertNotIn("hidden", remove["attrs"])

        response = self.client.post(remove["attrs"]["action"], remove["inputs"], follow=True)
        self.assertEqual(response.redirect_chain[-1][0], DASHBOARD_PAGE)
        self.assertContains(response, "Removed Amarillo, Texas, US from favorites.")
        self.assertFalse(FavoriteLocation.objects.exists())

    def test_location_named_by_coordinates_can_still_be_saved(self):
        self.reverse_geocode.side_effect = ServiceUnavailableError()
        (save,) = forms_marked(self.client.get(DASHBOARD_PAGE), "data-favorite-save")
        self.assertEqual(save["inputs"]["name"], "35.22, -101.83")
        response = self.client.post("/favorites/", save["inputs"], HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 201)

    def test_fr11_ac5_control_has_a_visible_message_area(self):
        response = self.client.get(DASHBOARD_PAGE)
        self.assertContains(response, 'class="favorite-message" data-favorite-message></p>')

    def test_save_button_shows_even_when_the_weather_service_fails(self):
        self.current_weather.side_effect = ServiceUnavailableError()
        self.forecast_5day.side_effect = ServiceUnavailableError()
        response = self.client.get(DASHBOARD_PAGE)
        self.assertEqual(len(forms_marked(response, "data-favorite-save")), 1)


class FavoritesScriptTests(BookmarkTestCase):
    """FR-11 AC-3/5: structural checks on favorites.js until a JS test runner is approved."""

    def setUp(self):
        super().setUp()
        with open(finders.find("weather/js/favorites.js"), encoding="utf-8") as handle:
            self.source = handle.read()

    def test_script_is_deferred_on_pages_with_favorite_controls(self):
        tag = '<script src="/static/weather/js/favorites.js" defer></script>'
        self.assertContains(self.client.get(SEARCH_PAGE), tag)
        self.assertContains(self.client.get(DASHBOARD_PAGE), tag)

    def test_fr11_ac3_submits_with_fetch_and_the_csrf_header(self):
        self.assertIn("fetch(", self.source)
        self.assertIn('"X-CSRFToken"', self.source)
        self.assertIn('Accept: "application/json"', self.source)
        self.assertIn('credentials: "same-origin"', self.source)
        self.assertIn("preventDefault()", self.source)

    def test_fr11_ac3_without_fetch_the_forms_submit_normally(self):
        self.assertIn('"fetch" in window', self.source)

    def test_fr11_ac2_handles_saved_duplicate_and_removed_outcomes(self):
        for status in ("201", "409", "401"):
            with self.subTest(status=status):
                self.assertIn(f"=== {status}", self.source)

    def test_fr11_ac5_outcomes_are_announced_in_the_shared_live_region(self):
        self.assertIn('getElementById("live-region")', self.source)

    def test_nfr_sec5_never_writes_html(self):
        self.assertNotIn("innerHTML", self.source)
        self.assertNotIn("insertAdjacentHTML", self.source)
