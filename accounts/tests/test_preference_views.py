"""Tests for the preferences page and the unit toggle endpoint (FR-3, FR-2 AC-6, NFR-SEC-3/4)."""
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import Client, TestCase

from accounts.models import TemperatureUnit, UserProfile
from accounts.preferences import SESSION_KEY

PREFERENCES_URL = "/accounts/preferences/"
TOGGLE_URL = "/preferences/unit/"
PASSWORD = "Correct-Horse-91"


def message_texts(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


class PreferencesPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password=PASSWORD)
        self.client.force_login(self.user)

    def test_fr2_ac6_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(PREFERENCES_URL)
        self.assertRedirects(
            response, f"/accounts/login/?next={PREFERENCES_URL}", fetch_redirect_response=False
        )

    def test_fr3_ac1_page_offers_fahrenheit_and_celsius(self):
        response = self.client.get(PREFERENCES_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/preferences.html")
        self.assertContains(response, 'value="imperial"')
        self.assertContains(response, 'value="metric"')
        self.assertContains(response, "°F")
        self.assertContains(response, "°C")
        self.assertContains(response, "<legend")
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "<h1", count=1)

    def test_fr3_ac4_current_unit_is_preselected_default_imperial(self):
        response = self.client.get(PREFERENCES_URL)
        self.assertEqual(response.context["form"].initial["temperature_unit"], "imperial")

    def test_fr3_ac2_saving_stores_unit_in_profile(self):
        response = self.client.post(PREFERENCES_URL, {"temperature_unit": "metric"})
        self.assertRedirects(response, PREFERENCES_URL)
        self.assertEqual(
            UserProfile.objects.get(user=self.user).temperature_unit, TemperatureUnit.METRIC
        )
        self.assertIn("Temperature unit set to Celsius (°C).", message_texts(response))

    def test_fr3_ac2_saved_unit_is_preselected_on_next_visit(self):
        self.client.post(PREFERENCES_URL, {"temperature_unit": "metric"})
        response = self.client.get(PREFERENCES_URL)
        self.assertEqual(response.context["form"].initial["temperature_unit"], "metric")

    def test_invalid_unit_redisplays_form_with_error(self):
        response = self.client.post(PREFERENCES_URL, {"temperature_unit": "kelvin"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].has_error("temperature_unit"))
        self.assertFalse(
            UserProfile.objects.filter(user=self.user, temperature_unit="kelvin").exists()
        )

    def test_nfr_sec4_saving_changes_only_the_current_users_profile(self):
        other = User.objects.create_user("bob", password=PASSWORD)
        UserProfile.objects.create(user=other)
        self.client.post(PREFERENCES_URL, {"temperature_unit": "metric"})
        self.assertEqual(other.profile.temperature_unit, TemperatureUnit.IMPERIAL)

    def test_nfr_sec3_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(PREFERENCES_URL, {"temperature_unit": "metric"})
        self.assertEqual(response.status_code, 403)

    def test_nav_links_to_preferences_for_logged_in_users(self):
        self.assertContains(self.client.get("/"), f'href="{PREFERENCES_URL}"')

    def test_nav_hides_preferences_link_from_anonymous_users(self):
        self.client.logout()
        self.assertNotContains(self.client.get("/"), f'href="{PREFERENCES_URL}"')


class UnitToggleTests(TestCase):
    def test_fr3_ac3_anonymous_toggle_stores_unit_in_session(self):
        response = self.client.post(TOGGLE_URL, {"temperature_unit": "metric"})
        self.assertRedirects(response, "/")
        self.assertEqual(self.client.session[SESSION_KEY], "metric")

    def test_fr3_ac2_logged_in_toggle_stores_unit_in_profile(self):
        user = User.objects.create_user("alice", password=PASSWORD)
        self.client.force_login(user)
        self.client.post(TOGGLE_URL, {"temperature_unit": "metric"})
        self.assertEqual(user.profile.temperature_unit, TemperatureUnit.METRIC)

    def test_fr3_ac5_toggle_returns_to_the_same_page(self):
        next_url = "/weather/?lat=35.22&lon=-101.83"
        response = self.client.post(
            TOGGLE_URL, {"temperature_unit": "metric", "next": next_url}
        )
        self.assertRedirects(response, next_url, fetch_redirect_response=False)

    def test_nfr_sec8_toggle_ignores_external_next(self):
        response = self.client.post(
            TOGGLE_URL, {"temperature_unit": "metric", "next": "https://evil.example/"}
        )
        self.assertRedirects(response, "/")

    def test_toggle_rejects_unknown_unit(self):
        response = self.client.post(TOGGLE_URL, {"temperature_unit": "kelvin"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_nfr_sec3_toggle_is_post_only(self):
        self.assertEqual(self.client.get(TOGGLE_URL).status_code, 405)

    def test_nfr_sec3_toggle_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(TOGGLE_URL, {"temperature_unit": "metric"})
        self.assertEqual(response.status_code, 403)
