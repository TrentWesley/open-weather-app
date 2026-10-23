"""Tests for MapLayer and OpenWeatherClient.map_tile (FR-12 AC-3/4/6, NFR-SEC-1).

A fake session is injected into the client, so no tile request leaves the process.
"""
from unittest import mock

import requests
from django.test import override_settings

from accounts.models import TemperatureUnit
from weather.services.client import OpenWeatherClient
from weather.services.domain import MapLayer
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
    ServiceUnavailableError,
)
from weather.tests.base import FIXTURES_DIR, OfflineSimpleTestCase, make_response

API_KEY = "test-key"
TILE = (FIXTURES_DIR / "tile.png").read_bytes()


def tile_response(status=200, body=TILE, content_type="image/png"):
    response = make_response(status, raw=body)
    response.headers["Content-Type"] = content_type
    return response


class MapLayerTests(OfflineSimpleTestCase):
    def test_fr12_ac3_four_layers_with_url_slugs(self):
        self.assertEqual(
            [layer.value for layer in MapLayer],
            ["temperature", "precipitation", "clouds", "wind"],
        )

    def test_fr12_ac3_layers_map_to_openweather_tile_names(self):
        self.assertEqual(
            [layer.tile_name for layer in MapLayer],
            ["temp_new", "precipitation_new", "clouds_new", "wind_new"],
        )

    def test_layers_have_readable_labels(self):
        self.assertEqual(
            [layer.label for layer in MapLayer],
            ["Temperature", "Precipitation", "Clouds", "Wind speed"],
        )

    def test_fr12_ac4_temperature_legend_follows_the_unit(self):
        metric = MapLayer.TEMPERATURE.legend(TemperatureUnit.METRIC)
        imperial = MapLayer.TEMPERATURE.legend(TemperatureUnit.IMPERIAL)
        self.assertEqual(metric[0], ("-40°C", "rgb(130, 22, 146)"))
        self.assertEqual(metric[-1], ("30°C", "rgb(252, 128, 20)"))
        self.assertEqual(imperial[0][0], "-40°F")
        self.assertEqual(imperial[4][0], "32°F")
        self.assertEqual(imperial[-1][0], "86°F")
        self.assertEqual([color for _, color in metric], [color for _, color in imperial])

    def test_fr12_ac4_precipitation_and_wind_legends_convert_units(self):
        self.assertEqual(MapLayer.PRECIPITATION.legend(TemperatureUnit.METRIC)[-1][0], "140 mm/h")
        self.assertEqual(
            MapLayer.PRECIPITATION.legend(TemperatureUnit.IMPERIAL)[-1][0], "5.5 in/h"
        )
        self.assertEqual(MapLayer.WIND.legend(TemperatureUnit.METRIC)[0][0], "5 m/s")
        self.assertEqual(MapLayer.WIND.legend(TemperatureUnit.IMPERIAL)[0][0], "11 mph")

    def test_fr12_ac4_clouds_legend_is_in_percent(self):
        labels = [label for label, _ in MapLayer.CLOUDS.legend(TemperatureUnit.IMPERIAL)]
        self.assertEqual(labels, ["0%", "25%", "50%", "75%", "100%"])

    def test_every_legend_has_at_least_three_stops(self):
        for layer in MapLayer:
            for unit in TemperatureUnit:
                with self.subTest(layer=layer, unit=unit):
                    self.assertGreaterEqual(len(layer.legend(unit)), 3)


@override_settings(OPENWEATHER_API_KEY=API_KEY, OPENWEATHER_RETRY_BACKOFF=0.25)
class MapTileClientTests(OfflineSimpleTestCase):
    def setUp(self):
        super().setUp()
        self.session = mock.Mock(spec=requests.Session)
        self.client_ = OpenWeatherClient(session=self.session)
        sleep = mock.patch("weather.services.client.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def respond(self, *responses):
        self.session.request.side_effect = list(responses)

    def test_fr12_ac6_fetches_the_tile_with_the_key_added_server_side(self):
        self.respond(tile_response())
        self.assertEqual(self.client_.map_tile(MapLayer.CLOUDS, 3, 2, 5), TILE)
        args, kwargs = self.session.request.call_args
        self.assertEqual(args, ("GET", "https://tile.openweathermap.org/map/clouds_new/3/2/5.png"))
        self.assertEqual(kwargs["params"], {"appid": API_KEY})
        self.assertEqual(kwargs["timeout"], 5)

    def test_nfr_ft5_transient_failures_are_retried_once(self):
        self.respond(requests.ConnectionError("down"), tile_response())
        self.assertEqual(self.client_.map_tile(MapLayer.WIND, 0, 0, 0), TILE)
        self.assertEqual(self.session.request.call_count, 2)

    def test_nfr_ft4_errors_map_to_the_shared_exceptions(self):
        cases = (
            (401, AuthenticationError),
            (429, RateLimitError),
            (503, ServiceUnavailableError),
            (404, OpenWeatherError),
        )
        for status, error in cases:
            with self.subTest(status=status):
                self.respond(tile_response(status, b"{}", "application/json"),
                             tile_response(status, b"{}", "application/json"))
                with self.assertRaises(error):
                    self.client_.map_tile(MapLayer.TEMPERATURE, 1, 0, 0)

    def test_a_non_image_response_is_rejected(self):
        self.respond(tile_response(200, b"<html>oops</html>", "text/html"))
        with self.assertRaises(OpenWeatherError):
            self.client_.map_tile(MapLayer.TEMPERATURE, 1, 0, 0)

    def test_nfr_rel2_logs_name_the_layer_but_never_the_key(self):
        self.respond(tile_response(503, b"", "text/plain"), tile_response(503, b"", "text/plain"))
        with self.assertLogs("weather.services.client", "WARNING") as logs:
            with self.assertRaises(ServiceUnavailableError) as raised:
                self.client_.map_tile(MapLayer.TEMPERATURE, 1, 0, 0)
        self.assertIn("/map/temp_new", "\n".join(logs.output))
        self.assertNotIn(API_KEY, "\n".join(logs.output))
        self.assertNotIn(API_KEY, str(raised.exception))
