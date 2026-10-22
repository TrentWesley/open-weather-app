"""Tests for CurrentWeather.wind_compass() and uv_category() (FR-8 AC-1)."""
import dataclasses
from datetime import UTC, datetime

from weather.services.domain import CurrentWeather, Location
from weather.tests.base import OfflineSimpleTestCase

NOW = datetime(2026, 10, 22, 13, 20, tzinfo=UTC)
WEATHER = CurrentWeather(
    location=Location("Amarillo", "Texas", "US", 35.22, -101.83),
    temperature=68.4, feels_like=67.9, temp_min=65.1, temp_max=71.6,
    description="light rain", icon="10d", humidity=64, wind_speed=12.66, wind_deg=315,
    pressure=1014, visibility=10000, clouds=75, uv_index=None,
    sunrise=NOW, sunset=NOW, retrieved_at=NOW,
)


def weather(**changes):
    return dataclasses.replace(WEATHER, **changes)


class WindCompassTests(OfflineSimpleTestCase):
    def test_fr8_ac1_wind_direction_is_a_16_point_compass_label(self):
        cases = {
            0: "N", 22: "NNE", 45: "NE", 68: "ENE", 90: "E", 113: "ESE", 135: "SE",
            158: "SSE", 180: "S", 203: "SSW", 225: "SW", 248: "WSW", 270: "W",
            293: "WNW", 315: "NW", 338: "NNW", 360: "N",
        }
        for degrees, label in cases.items():
            with self.subTest(degrees=degrees):
                self.assertEqual(weather(wind_deg=degrees).wind_compass(), label)

    def test_sector_boundaries_round_to_the_nearest_point(self):
        self.assertEqual(weather(wind_deg=11).wind_compass(), "N")
        self.assertEqual(weather(wind_deg=12).wind_compass(), "NNE")
        self.assertEqual(weather(wind_deg=349).wind_compass(), "N")

    def test_out_of_range_degrees_wrap_around(self):
        self.assertEqual(weather(wind_deg=405).wind_compass(), "NE")


class UvCategoryTests(OfflineSimpleTestCase):
    def test_fr8_ac4_no_category_without_uv_index(self):
        self.assertIsNone(weather(uv_index=None).uv_category())

    def test_fr8_ac1_who_uv_risk_categories(self):
        cases = {
            0.0: "Low", 2.4: "Low", 2.5: "Moderate", 5.0: "Moderate", 6.0: "High",
            7.4: "High", 8.0: "Very High", 10.4: "Very High", 10.5: "Extreme", 14.0: "Extreme",
        }
        for uv, category in cases.items():
            with self.subTest(uv=uv):
                self.assertEqual(weather(uv_index=uv).uv_category(), category)
