"""Tests for the dashboard's forecast section and charts.

FR-9 AC-1..7, FR-3 AC-5/6, NFR-FT-2/3/6, NFR-AC-6/7, NFR-PERF-3, NFR-SEC-1.
The forecast fixture has ten 3-hour steps from Thu Oct 22 10 AM to Fri Oct 23
1 PM, Amarillo local time (UTC-5). OpenWeather calls are mocked.
"""
import json
import re
import time
from datetime import timedelta
from unittest import mock

from django.contrib.staticfiles import finders
from django.core.cache import cache

from weather.services.exceptions import ServiceUnavailableError
from weather.tests.test_dashboard import API_KEY, NOW, DashboardTestCase

CHART_JS = "vendor/chartjs/4.4.7/chart.umd.js"


class ForecastTestCase(DashboardTestCase):
    def chart_data(self, response):
        match = re.search(
            r'<script id="forecast-chart-data" type="application/json">(.*?)</script>',
            response.content.decode(),
            re.S,
        )
        self.assertIsNotNone(match, "chart data json_script missing")
        return json.loads(match.group(1))


class DailySummaryRowTests(ForecastTestCase):
    def setUp(self):
        super().setUp()
        self.response = self.get()

    def test_fr9_ac1_forecast_section_is_labelled(self):
        self.assertContains(self.response, 'aria-labelledby="forecast-heading"')
        self.assertContains(self.response, '<h2 id="forecast-heading">5-day forecast</h2>', html=True)

    def test_fr9_ac2_one_entry_per_local_day_with_day_and_date(self):
        self.assertEqual(len(self.response.context["daily"]), 2)
        self.assertContains(self.response, "Thu, Oct 22")
        self.assertContains(self.response, "Fri, Oct 23")

    def test_fr9_ac2_daily_high_low_and_chance_of_precipitation(self):
        body = self.response.content.decode()
        thursday = body[body.index("Thu, Oct 22"):body.index("Fri, Oct 23")]
        self.assertIn("High 70°F", thursday)
        self.assertIn("Low 55°F", thursday)
        self.assertIn("80% chance of precipitation", thursday)
        self.assertContains(self.response, "45% chance of precipitation")

    def test_fr9_ac2_nfr_ac6_daily_icons_have_alt_text(self):
        self.assertContains(self.response, 'alt="scattered clouds"', count=2)


class ChartTests(ForecastTestCase):
    def test_fr9_ac3_ac4_chart_data_is_embedded_with_json_script(self):
        data = self.chart_data(self.get())
        self.assertEqual(len(data["labels"]), 10)
        self.assertEqual(data["labels"][0], "Thu 10 AM")
        self.assertEqual(data["temperature"][0], 70.2)
        self.assertEqual(data["pop"][4], 80)
        self.assertEqual(data["precipitation"][4], 0.12)
        self.assertEqual((data["temperature_unit"], data["precipitation_unit"]), ("°F", "in"))

    def test_fr9_ac6_charts_use_the_metric_unit_after_toggling(self):
        self.client.post("/preferences/unit/", {"temperature_unit": "metric"})
        data = self.chart_data(self.get())
        self.assertEqual((data["temperature_unit"], data["precipitation_unit"]), ("°C", "mm"))
        self.assertEqual(data["precipitation"][4], 3.0)
        self.forecast.assert_called_with(35.222, -101.8313, "metric")

    def test_fr9_ac3_ac4_two_chart_canvases_with_accessible_names(self):
        response = self.get()
        body = response.content.decode()
        for chart_id in ("temperature-chart", "precipitation-chart"):
            with self.subTest(chart=chart_id):
                canvas = re.search(rf'<canvas id="{chart_id}"[^>]*>', body)
                self.assertIsNotNone(canvas)
                self.assertIn('role="img"', canvas.group())
                self.assertIn("aria-label=", canvas.group())
                self.assertIn('tabindex="0"', canvas.group())

    def test_charts_stay_hidden_until_drawn(self):
        # The whole figure is hidden (not just the canvas) so no-JS visitors
        # don't see an empty fixed-height box.
        self.assertContains(self.get(), '<figure class="chart" hidden>', count=2)

    def test_each_canvas_has_its_own_height_constrained_container(self):
        """Regression: charts grew without limit.

        With maintainAspectRatio: false, Chart.js sizes the canvas to its parent and
        resizes when the parent changes. When the parent was the <figure>, whose
        height came from the canvas, every resize grew the figure and triggered
        another resize. Each canvas must be the only child of a container whose
        height doesn't depend on it.
        """
        body = self.get().content.decode()
        for chart_id in ("temperature-chart", "precipitation-chart"):
            with self.subTest(chart=chart_id):
                self.assertRegex(
                    body,
                    rf'<div class="chart-container">\s*<canvas id="{chart_id}"[^>]*></canvas>\s*</div>',
                )

    def test_nfr_ac7_charts_have_a_text_summary(self):
        self.assertContains(
            self.get(),
            "Temperatures range from 54°F to 70°F between Thu 10 AM and Fri 1 PM. "
            "Highest chance of precipitation: 80% at Thu 10 PM.",
        )

    def test_nfr_ft6_charts_degrade_with_a_visible_notice(self):
        self.assertContains(self.get(), "data-chart-fallback")

    def test_chart_scripts_load_vendored_chartjs_before_charts_js(self):
        body = self.get().content.decode()
        chart = body.index(f'<script src="/static/{CHART_JS}" defer></script>')
        charts = body.index('<script src="/static/weather/js/charts.js" defer></script>')
        self.assertLess(chart, charts)

    def test_nfr_sec1_no_third_party_script_hosts_or_key_in_page(self):
        body = self.get().content.decode()
        for forbidden in ("cdn.jsdelivr", "unpkg.com", "cdnjs", API_KEY, "api.openweathermap.org"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)


class ChartTableTests(ForecastTestCase):
    def setUp(self):
        super().setUp()
        self.response = self.get()
        body = self.response.content.decode()
        self.table = body[body.index('<table class="forecast-table"'):body.index("</table>")]

    def test_fr9_ac7_data_table_has_caption_and_column_headers(self):
        self.assertIn("<caption>", self.table)
        for header in ("Time", "Temperature", "Chance of precipitation", "Precipitation", "Conditions"):
            with self.subTest(header=header):
                self.assertIn(f'<th scope="col">{header}</th>', self.table)

    def test_fr9_ac7_table_has_a_row_per_3_hour_step(self):
        self.assertEqual(self.table.count('<th scope="row">'), 10)
        self.assertIn('<th scope="row">Thu 10 AM</th>', self.table)

    def test_fr9_ac7_table_values_match_the_charts_in_the_users_unit(self):
        self.assertIn("<td>70°F</td>", self.table)
        self.assertIn("<td>80%</td>", self.table)
        self.assertIn("<td>0.12 in</td>", self.table)
        self.assertIn("<td>Light rain</td>", self.table)


class ForecastFailureTests(ForecastTestCase):
    def test_nfr_ft3_forecast_failure_still_shows_current_weather(self):
        self.forecast.side_effect = ServiceUnavailableError()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<p class="current-temp">68°F</p>')
        self.assertContains(response, "The forecast isn")
        self.assertNotContains(response, "forecast-chart-data")
        self.assertNotContains(response, "charts.js")

    def test_nfr_ft3_current_weather_failure_still_shows_forecast(self):
        self.current.side_effect = ServiceUnavailableError()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')
        self.assertContains(response, "Thu, Oct 22")
        self.chart_data(response)

    def test_nfr_ft2_stale_forecast_is_shown_with_its_age(self):
        self.get()
        later = time.time() + 31 * 60
        patcher = mock.patch("time.time", return_value=later)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.set_now(NOW + timedelta(minutes=31))
        self.forecast.side_effect = ServiceUnavailableError()
        response = self.get()
        self.assertContains(response, "Showing a saved forecast from 31 minutes ago")
        self.assertContains(response, "Thu, Oct 22")

    def test_nfr_perf3_forecast_is_served_from_cache_on_reload(self):
        self.get()
        self.get()
        self.assertEqual(self.forecast.call_count, 1)


class ChartStylesheetTests(DashboardTestCase):
    """The CSS half of the resize-loop regression fix."""

    def setUp(self):
        super().setUp()
        with open(finders.find("css/site.css"), encoding="utf-8") as handle:
            self.css = handle.read()

    def rule(self, selector):
        match = re.search(rf"(?m)^{re.escape(selector)} \{{([^}}]*)\}}", self.css)
        self.assertIsNotNone(match, f"no CSS rule for {selector}")
        return match.group(1)

    def test_chart_container_is_relative_with_a_fixed_height(self):
        rule = self.rule(".chart-container")
        self.assertIn("position: relative;", rule)
        self.assertRegex(rule, r"(?<![\w-])height: \d+(\.\d+)?rem;")

    def test_no_css_sizes_the_canvas_itself(self):
        # Chart.js owns the canvas size; a CSS height on it fights the container.
        self.assertNotRegex(self.css, r"canvas[^{,]*\{[^}]*(?<![\w-])height:")


class VendoredChartJsTests(DashboardTestCase):
    def test_chartjs_is_vendored_at_an_exact_version_with_its_licence(self):
        path = finders.find(CHART_JS)
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as handle:
            self.assertIn("Chart.js v4.4.7", handle.read(200))
        self.assertIsNotNone(finders.find("vendor/chartjs/4.4.7/LICENSE.md"))

    def test_charts_script_is_discoverable(self):
        self.assertIsNotNone(finders.find("weather/js/charts.js"))

    def tearDown(self):
        cache.clear()
        super().tearDown()
