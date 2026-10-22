"""Tests for value-object behaviour: CurrentWeather (FR-8) and Forecast (FR-9)."""
import dataclasses
from datetime import UTC, date, datetime, timedelta, timezone

from weather.services.domain import CurrentWeather, Forecast, ForecastEntry, Location
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


LOCAL = timezone(timedelta(hours=-5))


def entry(day, hour, temp, pop=0.0, icon="03d", description="scattered clouds", rain=0.0):
    return ForecastEntry(
        timestamp=datetime(2026, 10, day, hour, 0, tzinfo=LOCAL),
        temperature=temp, pop=pop, precipitation_mm=rain, icon=icon, description=description,
    )


def forecast(entries):
    return Forecast(
        location=WEATHER.location, entries=tuple(entries), retrieved_at=NOW
    )


class DailySummaryTests(OfflineSimpleTestCase):
    def test_fr9_ac2_entries_are_grouped_by_local_calendar_day(self):
        summaries = forecast([
            entry(22, 19, 60), entry(22, 22, 55), entry(23, 1, 50), entry(23, 4, 48),
        ]).daily_summaries()
        self.assertEqual([s.date for s in summaries], [date(2026, 10, 22), date(2026, 10, 23)])

    def test_fr9_ac2_high_low_and_highest_chance_of_precipitation(self):
        summary = forecast([
            entry(22, 10, 70.2, pop=0.0), entry(22, 13, 66.8, pop=0.1),
            entry(22, 22, 55.3, pop=0.8),
        ]).daily_summaries()[0]
        self.assertEqual((summary.high, summary.low, summary.max_pop), (70.2, 55.3, 0.8))

    def test_fr9_ac2_condition_comes_from_the_entry_nearest_midday(self):
        summary = forecast([
            entry(22, 7, 50, icon="01d", description="clear sky"),
            entry(22, 13, 60, icon="10d", description="light rain"),
            entry(22, 22, 52, icon="01n", description="clear sky"),
        ]).daily_summaries()[0]
        self.assertEqual((summary.icon, summary.description), ("10d", "light rain"))

    def test_partial_day_uses_its_closest_entry_to_midday(self):
        summary = forecast([entry(22, 19, 60, icon="02n", description="few clouds"),
                            entry(22, 22, 55, icon="01n")]).daily_summaries()[0]
        self.assertEqual(summary.icon, "02n")
        self.assertEqual(summary.description, "few clouds")

    def test_fr9_at_most_six_days(self):
        entries = [entry(day, 12, 60) for day in range(20, 28)]
        summaries = forecast(entries).daily_summaries()
        self.assertEqual(len(summaries), 6)
        self.assertEqual(summaries[0].date, date(2026, 10, 20))

    def test_days_use_the_locations_time_zone_not_utc(self):
        # 22:00 at UTC-5 is 03:00 UTC the next day; it still belongs to the 22nd.
        summaries = forecast([entry(22, 13, 60), entry(22, 22, 50)]).daily_summaries()
        self.assertEqual(len(summaries), 1)
