"""Unit tests for the environment-variable helpers used by settings (NFR-SEC-1, NFR-SEC-6)."""
import os
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.env import env_bool, env_list, env_required


class EnvBoolTests(SimpleTestCase):
    def test_returns_default_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(env_bool("FLAG", default=False))
            self.assertTrue(env_bool("FLAG", default=True))

    def test_parses_truthy_values(self):
        for value in ("1", "true", "True", "YES", "on", " true "):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"FLAG": value}):
                self.assertTrue(env_bool("FLAG", default=False))

    def test_parses_falsy_values(self):
        for value in ("0", "false", "False", "no", "OFF", ""):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"FLAG": value}):
                self.assertFalse(env_bool("FLAG", default=True))

    def test_rejects_unrecognized_values(self):
        with mock.patch.dict(os.environ, {"FLAG": "maybe"}):
            with self.assertRaisesMessage(ImproperlyConfigured, "FLAG"):
                env_bool("FLAG", default=False)


class EnvListTests(SimpleTestCase):
    def test_returns_copy_of_default_when_unset(self):
        default = ["localhost"]
        with mock.patch.dict(os.environ, {}, clear=True):
            result = env_list("HOSTS", default=default)
        self.assertEqual(result, ["localhost"])
        self.assertIsNot(result, default)

    def test_splits_on_commas_and_trims_whitespace(self):
        with mock.patch.dict(os.environ, {"HOSTS": " example.com , 127.0.0.1,,localhost "}):
            self.assertEqual(
                env_list("HOSTS", default=[]), ["example.com", "127.0.0.1", "localhost"]
            )


class EnvRequiredTests(SimpleTestCase):
    def test_returns_value_when_set(self):
        with mock.patch.dict(os.environ, {"TOKEN": "abc"}):
            self.assertEqual(env_required("TOKEN"), "abc")

    def test_raises_with_variable_name_when_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesMessage(ImproperlyConfigured, "TOKEN"):
                env_required("TOKEN")

    def test_raises_when_blank(self):
        with mock.patch.dict(os.environ, {"TOKEN": "   "}):
            with self.assertRaisesMessage(ImproperlyConfigured, "TOKEN"):
                env_required("TOKEN")
