"""Tests for accounts.preferences.get_unit / set_unit (FR-3 AC-2..4).

Profiles are created lazily with get_or_create the first time a logged-in user's
unit is read or written; there is no post_save signal.
"""
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase

from accounts.models import TemperatureUnit, UserProfile
from accounts.preferences import SESSION_KEY, get_unit, set_unit


class PreferenceHelperTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="unused-pass-123")

    def make_request(self, user=None):
        request = RequestFactory().get("/")
        request.user = user or AnonymousUser()
        request.session = SessionStore()
        return request

    def test_fr3_ac4_anonymous_default_is_imperial(self):
        self.assertEqual(get_unit(self.make_request()), TemperatureUnit.IMPERIAL)

    def test_fr3_ac3_anonymous_unit_is_stored_in_session(self):
        request = self.make_request()
        set_unit(request, TemperatureUnit.METRIC)
        self.assertEqual(request.session[SESSION_KEY], "metric")
        self.assertEqual(get_unit(request), TemperatureUnit.METRIC)
        self.assertFalse(UserProfile.objects.exists())

    def test_fr3_ac3_invalid_session_value_falls_back_to_default(self):
        request = self.make_request()
        request.session[SESSION_KEY] = "kelvin"
        self.assertEqual(get_unit(request), TemperatureUnit.IMPERIAL)

    def test_fr3_ac4_new_user_default_is_imperial(self):
        self.assertEqual(get_unit(self.make_request(self.user)), TemperatureUnit.IMPERIAL)

    def test_profile_is_created_lazily_on_first_read(self):
        self.assertFalse(UserProfile.objects.filter(user=self.user).exists())
        get_unit(self.make_request(self.user))
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_fr3_ac2_user_unit_is_stored_in_profile(self):
        set_unit(self.make_request(self.user), TemperatureUnit.METRIC)
        self.assertEqual(self.user.profile.temperature_unit, TemperatureUnit.METRIC)

    def test_fr3_ac2_user_unit_applies_on_another_device(self):
        set_unit(self.make_request(self.user), TemperatureUnit.METRIC)
        fresh_user = User.objects.get(pk=self.user.pk)
        self.assertEqual(get_unit(self.make_request(fresh_user)), TemperatureUnit.METRIC)

    def test_fr3_ac2_user_unit_ignores_session_value(self):
        request = self.make_request(self.user)
        request.session[SESSION_KEY] = "metric"
        self.assertEqual(get_unit(request), TemperatureUnit.IMPERIAL)

    def test_set_unit_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            set_unit(self.make_request(), "kelvin")
