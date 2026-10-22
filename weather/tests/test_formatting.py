"""Tests for dashboard value formatting (FR-3 AC-6, FR-8 AC-1/2/3, NFR-USE-6, NFR-CACHE-4)."""
from datetime import UTC, date, datetime, timedelta, timezone

from django.template import Context, Template

from accounts.models import TemperatureUnit
from weather import formatting
from weather.tests.base import OfflineSimpleTestCase

IMPERIAL, METRIC = TemperatureUnit.IMPERIAL, TemperatureUnit.METRIC
LOCAL = timezone(timedelta(hours=-5))


class UnitFormattingTests(OfflineSimpleTestCase):
    def test_fr3_temperature_shows_the_selected_scale(self):
        self.assertEqual(formatting.format_temperature(68.4, IMPERIAL), "68°F")
        self.assertEqual(formatting.format_temperature(20.2, METRIC), "20°C")

    def test_temperature_rounds_half_up_and_never_shows_minus_zero(self):
        self.assertEqual(formatting.format_temperature(68.5, IMPERIAL), "69°F")
        self.assertEqual(formatting.format_temperature(-0.4, METRIC), "0°C")
        self.assertEqual(formatting.format_temperature(-3.6, METRIC), "-4°C")

    def test_unit_accepts_plain_strings(self):
        self.assertEqual(formatting.format_temperature(20, "metric"), "20°C")

    def test_fr3_ac6_wind_speed_is_mph_for_imperial_and_m_per_s_for_metric(self):
        self.assertEqual(formatting.format_speed(12.66, IMPERIAL), "13 mph")
        self.assertEqual(formatting.format_speed(5.66, METRIC), "5.7 m/s")

    def test_visibility_is_miles_for_imperial_and_km_for_metric(self):
        self.assertEqual(formatting.format_distance(10000, IMPERIAL), "6.2 mi")
        self.assertEqual(formatting.format_distance(10000, METRIC), "10 km")
        self.assertEqual(formatting.format_distance(2500, METRIC), "2.5 km")
        self.assertEqual(formatting.format_distance(800, IMPERIAL), "0.5 mi")


class TimeFormattingTests(OfflineSimpleTestCase):
    def test_nfr_use6_time_is_shown_in_the_datetimes_own_zone(self):
        self.assertEqual(formatting.format_time(datetime(2026, 10, 22, 7, 41, tzinfo=LOCAL)), "7:41 AM")
        self.assertEqual(formatting.format_time(datetime(2026, 10, 22, 18, 57, tzinfo=LOCAL)), "6:57 PM")
        self.assertEqual(formatting.format_time(datetime(2026, 10, 22, 0, 5, tzinfo=LOCAL)), "12:05 AM")

    def test_nfr_use6_date_and_time_format(self):
        moment = datetime(2026, 10, 20, 18, 42, tzinfo=LOCAL)
        self.assertEqual(formatting.format_datetime(moment), "Tue, Oct 20 · 6:42 PM")

    def test_nfr_cache4_data_age_in_plain_language(self):
        cases = {
            timedelta(seconds=20): "less than a minute",
            timedelta(minutes=1, seconds=30): "1 minute",
            timedelta(minutes=11): "11 minutes",
            timedelta(minutes=119): "119 minutes",
            timedelta(hours=2, minutes=5): "2 hours",
            timedelta(hours=26): "1 day",
            timedelta(days=3): "3 days",
            timedelta(seconds=-5): "less than a minute",
        }
        for age, text in cases.items():
            with self.subTest(age=age):
                self.assertEqual(formatting.format_age(age), text)


class IconTests(OfflineSimpleTestCase):
    def test_fr8_icon_url_for_valid_codes(self):
        self.assertEqual(
            formatting.icon_url("10d"), "https://openweathermap.org/img/wn/10d@2x.png"
        )

    def test_nfr_sec5_unexpected_icon_codes_produce_no_url(self):
        for code in ("", "10x", "../10d", "10d@2x.png", "100d", "1d"):
            with self.subTest(code=code):
                self.assertEqual(formatting.icon_url(code), "")


class TemplateFilterTests(OfflineSimpleTestCase):
    def render(self, source, **context):
        return Template("{% load weather_format %}" + source).render(Context(context))

    def test_unit_filters(self):
        output = self.render(
            "{{ t|temperature:unit }} {{ w|speed:unit }} {{ v|distance:unit }}",
            t=68.4, w=12.66, v=10000, unit=IMPERIAL,
        )
        self.assertEqual(output, "68°F 13 mph 6.2 mi")

    def test_time_filters_do_not_convert_to_the_server_time_zone(self):
        moment = datetime(2026, 10, 22, 7, 41, tzinfo=LOCAL)
        self.assertEqual(self.render("{{ m|local_time }}", m=moment), "7:41 AM")
        self.assertEqual(self.render("{{ m|local_datetime }}", m=moment), "Thu, Oct 22 · 7:41 AM")

    def test_in_zone_of_converts_to_another_datetimes_zone(self):
        utc_moment = datetime(2026, 10, 22, 13, 20, tzinfo=UTC)
        reference = datetime(2026, 10, 22, 7, 41, tzinfo=LOCAL)
        output = self.render("{{ m|in_zone_of:ref|local_datetime }}", m=utc_moment, ref=reference)
        self.assertEqual(output, "Thu, Oct 22 · 8:20 AM")

    def test_age_and_icon_filters(self):
        self.assertEqual(self.render("{{ a|age }}", a=timedelta(minutes=11)), "11 minutes")
        self.assertEqual(
            self.render("{{ c|icon_url }}", c="10d"), "https://openweathermap.org/img/wn/10d@2x.png"
        )


class ForecastFormattingTests(OfflineSimpleTestCase):
    def test_fr9_hour_labels_in_local_time(self):
        self.assertEqual(formatting.format_hour(datetime(2026, 10, 22, 10, 0, tzinfo=LOCAL)), "Thu 10 AM")
        self.assertEqual(formatting.format_hour(datetime(2026, 10, 23, 0, 0, tzinfo=LOCAL)), "Fri 12 AM")

    def test_fr9_ac2_day_labels(self):
        self.assertEqual(formatting.format_date(date(2026, 10, 22)), "Thu, Oct 22")

    def test_precipitation_amounts_with_units(self):
        self.assertEqual(formatting.format_precipitation(3.0, METRIC), "3 mm")
        self.assertEqual(formatting.format_precipitation(1.25, METRIC), "1.3 mm")
        self.assertEqual(formatting.format_precipitation(3.0, IMPERIAL), "0.12 in")
        self.assertEqual(formatting.format_precipitation(0, IMPERIAL), "0 in")

    def test_percent(self):
        self.assertEqual(formatting.format_percent(0.35), "35%")
        self.assertEqual(formatting.format_percent(0.805), "81%")
