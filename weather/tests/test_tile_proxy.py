"""Tests for the map tile proxy (FR-12 AC-6/7, NFR-SEC-1/5).

The browser asks our server for tiles; only the server talks to OpenWeather, adding
the key. Layer and z/x/y are validated so the proxy can't fetch arbitrary URLs.
OpenWeatherClient.map_tile is mocked.
"""
from unittest import mock

from django.test import override_settings

from weather.services.client import OpenWeatherClient
from weather.services.domain import MapLayer
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
    ServiceUnavailableError,
)
from weather.tests.base import FIXTURES_DIR, OfflineTestCase

API_KEY = "test-key"
TILE = (FIXTURES_DIR / "tile.png").read_bytes()


@override_settings(OPENWEATHER_API_KEY=API_KEY)
class TileProxyTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(OpenWeatherClient, "map_tile", return_value=TILE)
        self.map_tile = patcher.start()
        self.addCleanup(patcher.stop)

    def test_fr12_ac6_returns_the_tile_from_the_server_side_client(self):
        response = self.client.get("/weather/tiles/clouds/3/2/5/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response.content, TILE)
        self.map_tile.assert_called_once_with(MapLayer.CLOUDS, 3, 2, 5)

    def test_every_layer_is_served(self):
        for layer in MapLayer:
            with self.subTest(layer=layer):
                response = self.client.get(f"/weather/tiles/{layer.value}/0/0/0/")
                self.assertEqual(response.status_code, 200)

    def test_nfr_cache5_successful_tiles_are_cached_briefly_by_the_browser(self):
        response = self.client.get("/weather/tiles/wind/1/1/1/")
        self.assertIn("max-age=600", response["Cache-Control"])

    def test_nfr_sec5_unknown_layers_are_rejected_without_an_api_call(self):
        for layer in ("temp_new", "pressure", "TEMPERATURE", "..", "http:"):
            with self.subTest(layer=layer):
                self.assertEqual(self.client.get(f"/weather/tiles/{layer}/1/0/0/").status_code, 404)
        self.map_tile.assert_not_called()

    def test_nfr_sec5_tile_coordinates_are_bounded(self):
        cases = (
            "/weather/tiles/clouds/19/0/0/",  # zoom above the maximum
            "/weather/tiles/clouds/2/4/0/",  # x outside 0..2^z-1
            "/weather/tiles/clouds/2/0/4/",  # y outside 0..2^z-1
            "/weather/tiles/clouds/-1/0/0/",
            "/weather/tiles/clouds/1/a/0/",
            "/weather/tiles/clouds/1/0/0/extra/",
        )
        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.map_tile.assert_not_called()

    def test_largest_valid_tile_at_the_maximum_zoom_is_served(self):
        last = 2**18 - 1
        response = self.client.get(f"/weather/tiles/temperature/18/{last}/{last}/")
        self.assertEqual(response.status_code, 200)

    def test_fr12_ac7_openweather_failures_return_503_and_are_not_cached(self):
        for error in (
            ServiceUnavailableError(),
            RateLimitError(status_code=429),
            AuthenticationError(status_code=401),
            OpenWeatherError(status_code=404),
        ):
            with self.subTest(error=type(error).__name__):
                self.map_tile.side_effect = error
                response = self.client.get("/weather/tiles/precipitation/2/1/1/")
                self.assertEqual(response.status_code, 503)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertNotIn(API_KEY.encode(), response.content)

    def test_nfr_sec1_response_never_contains_the_key(self):
        response = self.client.get("/weather/tiles/clouds/0/0/0/")
        self.assertNotIn(API_KEY.encode(), response.content)
        self.assertNotIn(API_KEY, str(response.headers))

    def test_proxy_is_get_only(self):
        self.assertEqual(self.client.post("/weather/tiles/clouds/0/0/0/").status_code, 405)
        self.map_tile.assert_not_called()
