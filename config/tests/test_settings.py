"""Tests for config/settings.py (Phase 0: NFR-SEC-1, NFR-SEC-3, NFR-SEC-6, NFR-CACHE-2/3, NFR-PERF-2).

Environment-dependent settings are evaluated in a fresh subprocess so each case gets
a clean environment. DJANGO_DOTENV_PATH points at a missing file so the developer's
real .env is never loaded, and only non-secret values are printed back.
"""
import json
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

FAKE_ENV = {
    "DJANGO_SECRET_KEY": "test-secret-key-not-real",
    "OPENWEATHER_API_KEY": "test-key",
}

PRINT_SETTINGS = (
    "import json, config.settings as s; print(json.dumps({"
    "'DEBUG': s.DEBUG, 'ALLOWED_HOSTS': s.ALLOWED_HOSTS,"
    "'SESSION_COOKIE_SECURE': s.SESSION_COOKIE_SECURE,"
    "'CSRF_COOKIE_SECURE': s.CSRF_COOKIE_SECURE,"
    "'OPENWEATHER_ENABLE_ONECALL': s.OPENWEATHER_ENABLE_ONECALL}))"
)


def load_settings(**overrides):
    """Import config.settings in a subprocess with only the given env vars set."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "OPENWEATHER_"))
    }
    env["DJANGO_DOTENV_PATH"] = os.path.join(settings.BASE_DIR, "does-not-exist.env")
    env.update(FAKE_ENV)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [sys.executable, "-c", PRINT_SETTINGS],
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def load_settings_json(**overrides):
    result = load_settings(**overrides)
    if result.returncode != 0:
        raise AssertionError(f"settings import failed:\n{result.stderr}")
    return json.loads(result.stdout)


class EnvironmentSettingsTests(SimpleTestCase):
    def test_debug_defaults_to_false(self):
        self.assertFalse(load_settings_json(DJANGO_DEBUG=None)["DEBUG"])

    def test_debug_can_be_enabled_from_environment(self):
        self.assertTrue(load_settings_json(DJANGO_DEBUG="true")["DEBUG"])

    def test_allowed_hosts_default_to_local_hosts(self):
        values = load_settings_json(DJANGO_ALLOWED_HOSTS=None)
        self.assertEqual(values["ALLOWED_HOSTS"], ["localhost", "127.0.0.1"])

    def test_allowed_hosts_read_from_environment(self):
        values = load_settings_json(DJANGO_ALLOWED_HOSTS="weather.example.com, localhost")
        self.assertEqual(values["ALLOWED_HOSTS"], ["weather.example.com", "localhost"])

    def test_secure_cookies_enabled_when_debug_is_off(self):
        values = load_settings_json(DJANGO_DEBUG="false")
        self.assertTrue(values["SESSION_COOKIE_SECURE"])
        self.assertTrue(values["CSRF_COOKIE_SECURE"])

    def test_secure_cookies_disabled_for_local_debug(self):
        values = load_settings_json(DJANGO_DEBUG="true")
        self.assertFalse(values["SESSION_COOKIE_SECURE"])
        self.assertFalse(values["CSRF_COOKIE_SECURE"])

    def test_secure_cookies_can_be_overridden(self):
        values = load_settings_json(DJANGO_DEBUG="false", DJANGO_SECURE_COOKIES="false")
        self.assertFalse(values["SESSION_COOKIE_SECURE"])

    def test_one_call_disabled_by_default(self):
        values = load_settings_json(OPENWEATHER_ENABLE_ONECALL=None)
        self.assertFalse(values["OPENWEATHER_ENABLE_ONECALL"])

    def test_missing_secret_key_fails_with_clear_message(self):
        result = load_settings(DJANGO_SECRET_KEY=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ImproperlyConfigured", result.stderr)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_missing_openweather_key_fails_with_clear_message(self):
        result = load_settings(OPENWEATHER_API_KEY=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ImproperlyConfigured", result.stderr)
        self.assertIn("OPENWEATHER_API_KEY", result.stderr)

    def test_error_message_does_not_leak_other_secrets(self):
        result = load_settings(OPENWEATHER_API_KEY=None)
        self.assertNotIn(FAKE_ENV["DJANGO_SECRET_KEY"], result.stderr)


class StaticSettingsTests(SimpleTestCase):
    def test_project_templates_directory_configured(self):
        self.assertIn(settings.BASE_DIR / "templates", settings.TEMPLATES[0]["DIRS"])

    def test_project_static_directory_configured(self):
        self.assertIn(settings.BASE_DIR / "static", settings.STATICFILES_DIRS)
        self.assertEqual(settings.STATIC_ROOT, settings.BASE_DIR / "staticfiles")

    def test_csrf_middleware_enabled(self):
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)

    def test_session_cookie_http_only(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    def test_csrf_cookie_readable_by_javascript_for_fetch(self):
        # AGENTS.md: fetch() reads the csrftoken cookie and sends X-CSRFToken.
        self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)

    def test_password_validators_configured(self):
        names = {v["NAME"].rsplit(".", 1)[-1] for v in settings.AUTH_PASSWORD_VALIDATORS}
        self.assertEqual(
            names,
            {
                "UserAttributeSimilarityValidator",
                "MinimumLengthValidator",
                "CommonPasswordValidator",
                "NumericPasswordValidator",
            },
        )

    def test_cache_uses_local_memory_backend(self):
        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.locmem.LocMemCache",
        )

    def test_weather_cache_ttls(self):
        self.assertEqual(
            settings.WEATHER_CACHE_TTL,
            {"geocode": 60 * 60 * 24, "current": 60 * 10, "forecast": 60 * 30},
        )

    def test_openweather_timeout_and_retries(self):
        self.assertEqual(settings.OPENWEATHER_TIMEOUT, 5)
        self.assertEqual(settings.OPENWEATHER_RETRIES, 1)

    def test_weather_logger_configured(self):
        self.assertIn("weather", settings.LOGGING["loggers"])
