"""Tests for UserProfile and TemperatureUnit (FR-3)."""
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from accounts.models import TemperatureUnit, UserProfile


class TemperatureUnitTests(TestCase):
    def test_fr3_has_imperial_and_metric_values(self):
        self.assertEqual(TemperatureUnit.IMPERIAL, "imperial")
        self.assertEqual(TemperatureUnit.METRIC, "metric")

    def test_fr3_labels_name_the_scale(self):
        self.assertIn("°F", TemperatureUnit.IMPERIAL.label)
        self.assertIn("°C", TemperatureUnit.METRIC.label)


class UserProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="unused-pass-123")

    def test_fr3_ac4_default_unit_is_imperial(self):
        profile = UserProfile.objects.create(user=self.user)
        self.assertEqual(profile.temperature_unit, TemperatureUnit.IMPERIAL)

    def test_fr3_ac2_profile_is_one_to_one_with_user(self):
        UserProfile.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            UserProfile.objects.create(user=self.user)

    def test_profile_is_reachable_from_user(self):
        profile = UserProfile.objects.create(user=self.user)
        self.assertEqual(self.user.profile, profile)

    def test_units_param_matches_openweather_units(self):
        profile = UserProfile(user=self.user, temperature_unit=TemperatureUnit.METRIC)
        self.assertEqual(profile.units_param(), "metric")
        profile.temperature_unit = TemperatureUnit.IMPERIAL
        self.assertEqual(profile.units_param(), "imperial")
