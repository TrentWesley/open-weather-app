"""Tests for value-object behaviour: CurrentWeather (FR-8) and Forecast (FR-9)."""
import dataclasses
import json
from datetime import UTC, date, datetime, timedelta, timezone

from accounts.models import TemperatureUnit
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


class ChartDataTests(OfflineSimpleTestCase):
    """FR-9 AC-3/4/5/6: series and axis units for the Chart.js charts."""

    def setUp(self):
        super().setUp()
        self.forecast = forecast([
            entry(22, 10, 70.24, pop=0.0),
            entry(22, 13, 66.8, pop=0.1),
            entry(22, 22, 55.3, pop=0.8, rain=3.0),
            entry(23, 1, 54.1, pop=0.45, rain=1.25),
        ])

    def test_fr9_ac3_labels_are_local_3_hour_steps(self):
        data = self.forecast.chart_data(TemperatureUnit.IMPERIAL)
        self.assertEqual(data["labels"], ["Thu 10 AM", "Thu 1 PM", "Thu 10 PM", "Fri 1 AM"])

    def test_fr9_ac3_temperature_series(self):
        data = self.forecast.chart_data(TemperatureUnit.IMPERIAL)
        self.assertEqual(data["temperature"], [70.2, 66.8, 55.3, 54.1])

    def test_fr9_ac4_precipitation_probability_as_percent(self):
        self.assertEqual(self.forecast.chart_data("imperial")["pop"], [0, 10, 80, 45])

    def test_fr9_ac4_precipitation_amount_in_mm_for_metric_and_inches_for_imperial(self):
        self.assertEqual(self.forecast.chart_data("metric")["precipitation"], [0, 0, 3.0, 1.25])
        self.assertEqual(self.forecast.chart_data("imperial")["precipitation"], [0, 0, 0.12, 0.05])

    def test_fr9_ac5_ac6_axis_units_follow_the_unit_preference(self):
        imperial = self.forecast.chart_data(TemperatureUnit.IMPERIAL)
        metric = self.forecast.chart_data(TemperatureUnit.METRIC)
        self.assertEqual((imperial["temperature_unit"], imperial["precipitation_unit"]), ("°F", "in"))
        self.assertEqual((metric["temperature_unit"], metric["precipitation_unit"]), ("°C", "mm"))

    def test_nfr_ac7_text_summary_of_the_charts(self):
        summary = self.forecast.chart_data(TemperatureUnit.IMPERIAL)["summary"]
        self.assertEqual(
            summary,
            "Temperatures range from 54°F to 70°F between Thu 10 AM and Fri 1 AM. "
            "Highest chance of precipitation: 80% at Thu 10 PM.",
        )

    def test_chart_data_is_json_serializable(self):
        json.dumps(self.forecast.chart_data(TemperatureUnit.METRIC))
