"""Tests for the map page and the dashboard map panel (FR-12, NFR-AC-8, NFR-FT-3/6).

Leaflet runs in the browser, so these cover what the server controls: the map
configuration passed with json_script, the layer switcher and legends, favorite
markers, the text alternative, and failure states. OpenWeather calls are mocked.
"""
import json
import re
from unittest import mock

from django.contrib.auth.models import User
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

API_KEY = "test-key"
MAP_URL = "/weather/map/"
AMARILLO_QUERY = {"lat": "35.2220", "lon": "-101.8313"}
DASHBOARD_PAGE = "/weather/?lat=35.2220&lon=-101.8313"
LONDON = Location("London", "England", "GB", 51.5073, -0.1276)
PARIS = Location("Paris", "Ile-de-France", "FR", 48.8566, 2.3522)


def map_config(response) -> dict:
    match = re.search(
        r'<script id="map-config" type="application/json">(.*?)</script>',
        response.content.decode(),
        re.S,
    )
    assert match, "map-config json_script missing"
    return json.loads(match.group(1))


@override_settings(OPENWEATHER_API_KEY=API_KEY, OPENWEATHER_ENABLE_ONECALL=False)
class MapTestCase(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.alice = User.objects.create_user("alice", password="Correct-Horse-91")
        self.bob = User.objects.create_user("bob", password="Correct-Horse-91")
        for name, fixture in (
            ("reverse_geocode", "reverse_geocode.json"),
            ("current_weather", "current_weather.json"),
            ("forecast_5day", "forecast_5day.json"),
        ):
            patcher = mock.patch.object(
                OpenWeatherClient, name, return_value=load_fixture(fixture)
            )
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def get_map(self, **params):
        return self.client.get(MAP_URL, params or AMARILLO_QUERY)


class MapPageTests(MapTestCase):
    def test_fr12_ac1_map_page_is_centered_on_the_selected_location(self):
        response = self.get_map()
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "weather/map.html")
        self.assertContains(response, "<h1>Weather map for Amarillo, Texas, US</h1>", html=True)
        config = map_config(response)
        self.assertEqual(config["center"], [35.222, -101.8313])
        self.assertGreaterEqual(config["zoom"], 6)

    def test_fr12_ac1_selected_location_has_a_marker_with_its_weather(self):
        selected = map_config(self.get_map())["markers"][0]
        self.assertEqual(
            selected,
            {
                "kind": "selected",
                "name": "Amarillo, Texas, US",
                "lat": 35.222,
                "lon": -101.8313,
                "weather": "68°F, Light rain",
                "url": DASHBOARD_PAGE,
            },
        )

    def test_nfr_ac8_map_has_an_accessible_name_and_keyboard_focus(self):
        response = self.get_map()
        self.assertRegex(
            response.content.decode(),
            r'<div id="weather-map" class="map" data-map role="region" tabindex="0"\s+'
            r'aria-label="Interactive weather map centered on Amarillo, Texas, US"',
        )
        self.assertContains(response, 'aria-describedby="map-keyboard-help map-places"')
        self.assertContains(response, "arrow keys to pan")

    def test_fr12_ac3_layer_switcher_offers_the_four_overlays(self):
        response = self.get_map()
        content = response.content.decode()
        for value, label in (
            ("temperature", "Temperature"),
            ("precipitation", "Precipitation"),
            ("clouds", "Clouds"),
            ("wind", "Wind speed"),
        ):
            with self.subTest(layer=value):
                self.assertRegex(
                    content,
                    rf'<input type="radio" name="map-layer" id="map-layer-{value}" '
                    rf'value="{value}"[^>]*>\s*<label for="map-layer-{value}">{label}</label>',
                )
        self.assertContains(response, 'value="temperature" checked')
        self.assertContains(response, "<legend>Map layer</legend>", html=True)
        self.assertEqual(map_config(response)["defaultLayer"], "temperature")

    def test_fr12_ac4_each_layer_has_a_legend_with_labelled_stops(self):
        response = self.get_map()
        content = response.content.decode()
        self.assertEqual(content.count('class="map-legend"'), 4)
        self.assertRegex(content, r'data-legend="precipitation"[^>]*hidden')
        self.assertNotRegex(content, r'data-legend="temperature"[^>]*hidden')
        self.assertContains(response, "-40°F")
        self.assertContains(response, "86°F")
        self.assertContains(response, 'style="background: rgb(130, 22, 146)"')

    def test_fr3_legend_and_temperatures_follow_the_unit_preference(self):
        set_unit(mock.Mock(user=self.alice), TemperatureUnit.METRIC)
        self.client.force_login(self.alice)
        response = self.get_map()
        self.assertContains(response, "-40°C")
        self.assertContains(response, "140 mm/h")
        self.current_weather.assert_called_once_with(35.222, -101.8313, "metric")

    def test_fr3_map_page_has_the_unit_toggle_returning_to_the_same_map(self):
        response = self.get_map()
        self.assertContains(response, 'action="/preferences/unit/"')
        self.assertContains(
            response, '<input type="hidden" name="next" value="/weather/map/?lat=35.2220&amp;lon=-101.8313">'
        )

    def test_fr12_ac6_tiles_come_from_our_proxy_and_the_page_has_no_key(self):
        response = self.get_map()
        config = map_config(response)
        self.assertEqual(config["tileUrl"], "/weather/tiles/{layer}/{z}/{x}/{y}/")
        self.assertEqual(config["base"]["url"], "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertIn("OpenStreetMap", config["base"]["attribution"])
        self.assertNotContains(response, "tile.openweathermap.org")
        self.assertNotContains(response, "api.openweathermap.org")
        self.assertNotContains(response, API_KEY)

    def test_nfr_ac8_text_alternative_lists_the_selected_location(self):
        response = self.get_map()
        self.assertContains(response, 'id="map-places"')
        self.assertContains(response, "Amarillo, Texas, US")
        self.assertContains(response, "68°F, Light rain")
        self.assertContains(response, f'<a href="{DASHBOARD_PAGE.replace("&", "&amp;")}"')

    def test_nfr_ft6_map_needs_javascript_notice_and_deferred_scripts(self):
        response = self.get_map()
        self.assertContains(response, "data-map-fallback")
        self.assertContains(response, "The interactive map needs JavaScript")
        self.assertContains(
            response, '<link rel="stylesheet" href="/static/vendor/leaflet/1.9.4/leaflet.css">'
        )
        self.assertContains(
            response, '<script src="/static/vendor/leaflet/1.9.4/leaflet.js" defer></script>'
        )
        self.assertContains(response, '<script src="/static/weather/js/map.js" defer></script>')
        # The layer switcher and legends only make sense once the map exists.
        self.assertRegex(response.content.decode(), r"<div class=\"map-controls\" data-map-controls hidden>")

    def test_nfr_ft6_empty_map_box_stays_hidden_until_leaflet_runs(self):
        content = self.get_map().content.decode()
        self.assertRegex(content, r'<div id="weather-map"[^>]*aria-describedby="map-keyboard-help map-places"\s+hidden>')
        self.assertRegex(content, r'<p id="map-keyboard-help" class="map-help" hidden>')

    def test_nfr_use4_loading_and_overlay_status_regions(self):
        response = self.get_map()
        self.assertContains(response, 'class="map-status" role="status" data-map-status')
        self.assertContains(response, "data-map-loading hidden")

    def test_nfr_ft3_weather_failure_still_shows_the_map(self):
        self.current_weather.side_effect = ServiceUnavailableError()
        response = self.get_map()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(map_config(response)["markers"][0]["weather"])
        self.assertContains(response, "Current weather unavailable")

    def test_nfr_sec5_invalid_coordinates_are_rejected(self):
        for params in ({"lat": "91", "lon": "0"}, {"lat": "35"}, {"lat": "x", "lon": "y"}):
            with self.subTest(params=params):
                response = self.client.get(MAP_URL, params)
                self.assertEqual(response.status_code, 400)
        self.current_weather.assert_not_called()

    def test_map_without_a_location_shows_the_world(self):
        response = self.client.get(MAP_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<h1>Weather map</h1>", html=True)
        config = map_config(response)
        self.assertIsNone(config["center"])
        self.assertEqual(config["markers"], [])
        self.assertContains(response, "Search for a location")
        self.current_weather.assert_not_called()

    def test_map_page_is_get_only(self):
        self.assertEqual(self.client.post(MAP_URL, AMARILLO_QUERY).status_code, 405)


class FavoriteMarkerTests(MapTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.alice)
        self.london = FavoriteLocation.add(self.alice, LONDON)
        FavoriteLocation.add(self.bob, PARIS)

    def test_fr12_ac5_favorites_appear_as_markers_with_weather_and_a_link(self):
        markers = map_config(self.get_map())["markers"]
        self.assertEqual(len(markers), 2)
        self.assertEqual(
            markers[1],
            {
                "kind": "favorite",
                "name": "London, England, GB",
                "lat": 51.5073,
                "lon": -0.1276,
                "weather": "68°F, Light rain",
                "url": "/weather/?lat=51.5073&lon=-0.1276",
            },
        )

    def test_nfr_sec4_only_the_users_own_favorites_are_shown(self):
        response = self.get_map()
        self.assertNotIn("Paris", json.dumps(map_config(response)))
        self.assertNotContains(response, "Paris")

    def test_fr12_ac5_anonymous_visitors_see_no_favorite_markers(self):
        self.client.logout()
        markers = map_config(self.get_map())["markers"]
        self.assertEqual([marker["kind"] for marker in markers], ["selected"])

    def test_nfr_ac8_text_alternative_lists_favorites(self):
        response = self.get_map()
        self.assertContains(response, "Your favorites on this map")
        self.assertContains(response, '<a href="/weather/?lat=51.5073&amp;lon=-0.1276"')

    def test_saved_selected_location_is_not_duplicated_as_a_favorite_marker(self):
        FavoriteLocation.add(self.alice, Location("Amarillo", "Texas", "US", 35.222, -101.8313))
        kinds = [marker["kind"] for marker in map_config(self.get_map())["markers"]]
        self.assertEqual(kinds, ["selected", "favorite"])

    def test_map_without_a_location_fits_the_favorites(self):
        response = self.client.get(MAP_URL)
        config = map_config(response)
        self.assertIsNone(config["center"])
        self.assertEqual([marker["name"] for marker in config["markers"]], ["London, England, GB"])
        self.assertNotContains(response, "Search for a location")

    def test_nfr_perf6_favorites_are_loaded_in_one_query(self):
        self.get_map()  # Warm up: profile and caches.
        with CaptureQueriesContext(connection) as one:
            self.get_map()
        for index in range(5):
            FavoriteLocation.add(self.alice, Location(f"P{index}", "", "US", index, index))
        self.get_map()
        with CaptureQueriesContext(connection) as six:
            self.get_map()
        self.assertEqual(len(six), len(one))

    def test_favorites_page_links_to_the_map(self):
        response = self.client.get("/favorites/")
        self.assertContains(response, '<a href="/weather/map/">Show your favorites on a map</a>', html=True)


class DashboardMapPanelTests(MapTestCase):
    def test_fr12_ac1_dashboard_has_a_map_panel_for_the_location(self):
        response = self.client.get(DASHBOARD_PAGE)
        self.assertContains(response, '<h2 id="map-heading">Weather map</h2>', html=True)
        self.assertContains(response, 'id="weather-map"')
        self.assertEqual(map_config(response)["center"], [35.222, -101.8313])
        self.assertContains(
            response, '<a href="/weather/map/?lat=35.2220&amp;lon=-101.8313">Open the full map</a>', html=True
        )

    def test_nfr_perf3_panel_uses_only_cached_weather_for_favorites(self):
        self.client.force_login(self.alice)
        FavoriteLocation.add(self.alice, LONDON)
        response = self.client.get(DASHBOARD_PAGE)
        self.assertEqual(self.current_weather.call_count, 1)  # the dashboard's own location
        london = map_config(response)["markers"][1]
        self.assertEqual(london["name"], "London, England, GB")
        self.assertIsNone(london["weather"])

        self.client.get("/favorites/")  # caches London's current weather
        response = self.client.get(DASHBOARD_PAGE)
        self.assertEqual(map_config(response)["markers"][1]["weather"], "68°F, Light rain")

    def test_nfr_ft3_map_panel_renders_when_weather_fails(self):
        self.current_weather.side_effect = ServiceUnavailableError()
        self.forecast_5day.side_effect = ServiceUnavailableError()
        response = self.client.get(DASHBOARD_PAGE)
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, 'id="weather-map"', status_code=503)

    def test_map_scripts_load_on_the_dashboard(self):
        response = self.client.get(DASHBOARD_PAGE)
        self.assertContains(response, '<script src="/static/weather/js/map.js" defer></script>')

    def test_nav_links_to_the_map_page(self):
        response = self.client.get("/")
        self.assertContains(response, '<a href="/weather/map/">Map</a>', html=True)


class MapScriptContractTests(MapTestCase):
    """Structural checks on map.js until a JS test runner is approved."""

    def setUp(self):
        super().setUp()
        from django.contrib.staticfiles import finders

        with open(finders.find("weather/js/map.js"), encoding="utf-8") as handle:
            self.source = handle.read()

    def test_fr12_reads_its_configuration_from_json_script(self):
        self.assertIn('getElementById("map-config")', self.source)
        self.assertIn("JSON.parse(", self.source)

    def test_fr12_ac2_keyboard_navigation_is_enabled(self):
        self.assertIn("keyboard: true", self.source)

    def test_fr12_ac7_tile_errors_show_an_overlay_unavailable_message(self):
        self.assertIn('"tileerror"', self.source)
        self.assertIn("unavailable right now", self.source)

    def test_nfr_ft6_missing_leaflet_leaves_a_visible_notice(self):
        self.assertIn('typeof L === "undefined"', self.source)

    def test_nfr_ac10_respects_reduced_motion(self):
        self.assertIn("prefers-reduced-motion: reduce", self.source)

    def test_nfr_use4_loading_indicator_after_300_ms(self):
        self.assertIn("SLOW_NOTICE_MS = 300", self.source)

    def test_nfr_sec1_never_contacts_openweather_or_writes_html(self):
        self.assertNotIn("openweathermap.org", self.source)
        self.assertNotIn("appid", self.source)
        self.assertNotIn("innerHTML", self.source)
        self.assertNotIn("insertAdjacentHTML", self.source)

    def test_scripts_do_not_redeclare_each_others_top_level_constants(self):
        """Classic scripts share one global scope; a repeated `const` stops a script loading."""
        import pathlib
        import re as regex

        from django.contrib.staticfiles import finders

        folder = pathlib.Path(finders.find("weather/js/map.js")).parent
        seen = {}
        for script in sorted(folder.glob("*.js")):
            for name in regex.findall(r"^(?:const|let|class) (\w+)", script.read_text("utf-8"), regex.M):
                with self.subTest(name=name, script=script.name):
                    self.assertNotIn(name, seen, f"{name} also declared in {seen.get(name)}")
                seen[name] = script.name

    def test_nfr_ft6_script_reveals_the_map_box_only_when_leaflet_is_available(self):
        leaflet_check = self.source.index('typeof L === "undefined"')
        reveal = self.source.index("container.hidden = false")
        self.assertLess(leaflet_check, reveal)
        self.assertLess(reveal, self.source.index("L.map(container"))


class BaseMapPolicyTests(MapTestCase):
    """OpenStreetMap tile usage policy (operations.osmfoundation.org/policies/tiles/).

    Tiles requested without a Referer get an "Access blocked" image, and the site's
    Referrer-Policy (same-origin) strips it from cross-origin requests.
    """

    def test_base_tiles_send_the_sites_origin_as_referer(self):
        base = map_config(self.get_map())["base"]
        self.assertEqual(base["referrerPolicy"], "strict-origin-when-cross-origin")

    def test_site_wide_referrer_policy_stays_same_origin(self):
        # Only the base-map layer opts in, so other links never get the page path.
        self.assertEqual(self.get_map()["Referrer-Policy"], "same-origin")

    def test_default_base_map_follows_the_policy(self):
        base = map_config(self.get_map())["base"]
        self.assertEqual(base["url"], "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertIn(
            '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            base["attribution"],
        )
        self.assertLessEqual(base["maxZoom"], 19)

    @override_settings(
        MAP_BASE_TILE_URL="https://tiles.example.org/{z}/{x}/{y}.png",
        MAP_BASE_ATTRIBUTION="&copy; Example Maps",
        MAP_BASE_MAX_ZOOM=16,
    )
    def test_base_map_provider_is_configurable_without_code_changes(self):
        base = map_config(self.get_map())["base"]
        self.assertEqual(base["url"], "https://tiles.example.org/{z}/{x}/{y}.png")
        self.assertTrue(base["attribution"].startswith("&copy; Example Maps"))
        self.assertIn("OpenWeather", base["attribution"])
        self.assertEqual(base["maxZoom"], 16)

    def test_map_script_passes_the_referrer_policy_to_the_base_layer(self):
        from django.contrib.staticfiles import finders

        with open(finders.find("weather/js/map.js"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("referrerPolicy: config.base.referrerPolicy", source)
