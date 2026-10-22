"""Tests for secret-handling files in the repository (NFR-SEC-1)."""
import os
import shutil
import subprocess
import unittest

from django.conf import settings
from django.test import SimpleTestCase

REQUIRED_ENV_KEYS = ("DJANGO_SECRET_KEY", "OPENWEATHER_API_KEY")
OPTIONAL_ENV_KEYS = (
    "DJANGO_DEBUG",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_SECURE_COOKIES",
    "OPENWEATHER_ENABLE_ONECALL",
)


def parse_env_file(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


class EnvExampleTests(SimpleTestCase):
    path = settings.BASE_DIR / ".env.example"

    def test_env_example_exists(self):
        self.assertTrue(self.path.is_file(), ".env.example is missing")

    def test_env_example_lists_every_setting(self):
        keys = parse_env_file(self.path).keys()
        for key in REQUIRED_ENV_KEYS + OPTIONAL_ENV_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, keys)

    def test_env_example_contains_only_placeholders(self):
        values = parse_env_file(self.path)
        for key in REQUIRED_ENV_KEYS:
            with self.subTest(key=key):
                # Compare without printing either value, so a failure never leaks a secret.
                real = os.environ.get(key)
                self.assertTrue(
                    real is None or values.get(key) != real,
                    f".env.example contains the real value of {key}",
                )
                self.assertTrue(
                    values.get(key, "").startswith("replace-with-"),
                    f"{key} in .env.example should be a 'replace-with-...' placeholder",
                )


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitIgnoreTests(SimpleTestCase):
    def is_ignored(self, path):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--no-index", path],
            cwd=settings.BASE_DIR,
            capture_output=True,
        )
        return result.returncode == 0

    def test_secrets_and_local_artifacts_are_ignored(self):
        for path in (".env", "db.sqlite3", "staticfiles/", ".venv/", "config/__pycache__/x.pyc"):
            with self.subTest(path=path):
                self.assertTrue(self.is_ignored(path), f"{path} should be git-ignored")

    def test_env_example_is_not_ignored(self):
        self.assertFalse(self.is_ignored(".env.example"))
