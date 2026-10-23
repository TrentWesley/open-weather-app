"""Phase 9 audit: cross-cutting requirements checked across the whole project.

NFR-AC-3/4, NFR-USE-2/3, NFR-PERF-1/5, NFR-REL-5, FR-8 AC-2. OpenWeather is mocked.
"""
import io
import pathlib
import re
import time
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings

from accounts.models import TemperatureUnit
from accounts.preferences import set_unit
from weather.services.client import OpenWeatherClient
from weather.tests.base import OfflineTestCase, load_fixture

DASHBOARD = "/weather/?lat=35.2220&lon=-101.8313"
CSS = pathlib.Path(finders.find("css/site.css")).read_text(encoding="utf-8")


def tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--color-([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


LIGHT = tokens(CSS.split("@media (prefers-color-scheme: dark)")[0])
DARK = {
    **LIGHT,
    **tokens(re.search(r"prefers-color-scheme: dark\)\s*{\s*:root\s*{(.*?)}", CSS, re.S).group(1)),
}


def contrast(foreground: str, background: str) -> float:
    def luminance(colour: str) -> float:
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    high, low = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ContrastTests(OfflineTestCase):
    """NFR-AC-4: text 4.5:1; focus ring and chart lines (UI components) 3:1."""

    PAIRS = (
        ("text", "bg", 4.5), ("text", "surface", 4.5),
        ("muted", "bg", 4.5), ("muted", "surface", 4.5),
        ("link", "bg", 4.5), ("link", "surface", 4.5),
        ("error", "bg", 4.5), ("error", "surface", 4.5),
        ("button-text", "link", 4.5),
        ("focus", "bg", 3.0), ("focus", "surface", 3.0),
        ("muted", "bg", 3.0),  # form field borders
        ("chart-2", "bg", 3.0),
    )

    def test_nfr_ac4_colour_tokens_meet_wcag_aa_in_light_and_dark_themes(self):
        for theme_name, theme in (("light", LIGHT), ("dark", DARK)):
            for foreground, background, minimum in self.PAIRS:
                with self.subTest(theme=theme_name, pair=f"{foreground} on {background}"):
                    self.assertGreaterEqual(
                        contrast(theme[foreground], theme[background]), minimum
                    )


class KeyboardTests(OfflineTestCase):
    """NFR-AC-3: visible focus and a logical tab order."""

    def template_sources(self):
        roots = [settings.BASE_DIR / "templates", settings.BASE_DIR / "accounts" / "templates",
                 settings.BASE_DIR / "weather" / "templates"]
        return {path: path.read_text("utf-8") for root in roots for path in root.rglob("*.html")}

    def test_nfr_ac3_no_positive_tabindex_reorders_focus(self):
        for path, source in self.template_sources().items():
            with self.subTest(template=path.name):
                self.assertNotRegex(source, r'tabindex="[1-9]')

    def test_nfr_ac3_focus_is_always_visible(self):
        self.assertRegex(CSS, r":focus-visible\s*{\s*outline: 3px solid var\(--color-focus\)")
        # The only outline removal is on <main>, which is focused by the skip link.
        removed = re.findall(r"([^{}]+){\s*outline:\s*(?:none|0)", CSS)
        self.assertEqual([selector.strip() for selector in removed], ["main:focus"])

    def test_nfr_ac3_no_inline_event_handlers(self):
        for path, source in self.template_sources().items():
            with self.subTest(template=path.name):
                self.assertNotRegex(source, r"\son[a-z]+=")


class MigrationTests(OfflineTestCase):
    def test_nfr_rel5_every_model_change_has_a_migration(self):
        output = io.StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=output)
        self.assertIn("No changes detected", output.getvalue())


@override_settings(OPENWEATHER_API_KEY="test-key", OPENWEATHER_ENABLE_ONECALL=False)
class DashboardAuditTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        for name, fixture in (
            ("reverse_geocode", "reverse_geocode.json"),
            ("current_weather", "current_weather.json"),
            ("forecast_5day", "forecast_5day.json"),
        ):
            patcher = mock.patch.object(OpenWeatherClient, name, return_value=load_fixture(fixture))
            patcher.start()
            self.addCleanup(patcher.stop)

    def metrics(self, response) -> str:
        return re.search(r'<dl class="metrics">.*?</dl>', response.content.decode(), re.S).group()

    def test_fr8_ac2_metrics_use_the_unit_preference(self):
        imperial = self.metrics(self.client.get(DASHBOARD))
        self.assertIn(" mph", imperial)
        self.assertIn(" mi", imperial)
        user = User.objects.create_user("alice", password="Correct-Horse-91")
        set_unit(mock.Mock(user=user), TemperatureUnit.METRIC)
        self.client.force_login(user)
        cache.clear()
        response = self.client.get(DASHBOARD)
        metric = self.metrics(response)
        self.assertIn(" m/s", metric)
        self.assertIn(" km", metric)
        self.assertNotIn("mph", metric)
        self.assertIn("68°C", response.content.decode())

    def test_nfr_use2_primary_actions_are_one_click_from_the_dashboard(self):
        content = self.client.get(DASHBOARD).content.decode()
        self.assertIn('class="nav-search"', content)  # search
        self.assertIn("data-geolocate", content)  # use my location
        self.assertIn('action="/preferences/unit/"', content)  # unit toggle
        self.assertIn("data-favorite-save", content)  # save to favorites

    def test_nfr_perf1_server_side_render_time(self):
        """Render cost only: OpenWeather is mocked, so network latency isn't included."""
        start = time.perf_counter()
        self.assertEqual(self.client.get(DASHBOARD).status_code, 200)
        miss = time.perf_counter() - start
        start = time.perf_counter()
        self.client.get(DASHBOARD)
        hit = time.perf_counter() - start
        self.assertLess(miss, 2.0)
        self.assertLess(hit, 0.5)

    def test_nfr_perf5_first_load_weight_excluding_map_tiles_is_under_1_mb(self):
        response = self.client.get(DASHBOARD)
        content = response.content.decode()
        assets = re.findall(r'(?:src|href)="/static/([^"]+)"', content)
        self.assertGreaterEqual(len(assets), 8)
        total = len(response.content) + sum(
            pathlib.Path(finders.find(asset)).stat().st_size for asset in assets
        )
        self.assertLess(total, 1_000_000)


class FormErrorTests(OfflineTestCase):
    def test_nfr_use3_errors_appear_inside_the_field_they_belong_to(self):
        response = self.client.post(
            "/accounts/register/",
            {"username": "alice", "email": "a@example.com",
             "password1": "Correct-Horse-91", "password2": "Different-Horse-92"},
        )
        field = re.search(
            r'<div class="field field-invalid">\s*<label for="id_password2">.*?</div>\s*(?=<div|<button)',
            response.content.decode(),
            re.S,
        )
        self.assertIsNotNone(field, "password confirmation field with its error not found")
        self.assertIn('class="field-errors" id="id_password2_error"', field.group())
