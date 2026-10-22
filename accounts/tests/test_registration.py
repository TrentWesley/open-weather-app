"""Tests for user registration (FR-1, NFR-SEC-2, NFR-SEC-3, NFR-AC-5)."""
import re

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import Client, TestCase

from accounts.forms import RegistrationForm

REGISTER_URL = "/accounts/register/"
STRONG_PASSWORD = "Correct-Horse-91"


def registration_data(**overrides):
    data = {
        "username": "alice",
        "email": "alice@example.com",
        "password1": STRONG_PASSWORD,
        "password2": STRONG_PASSWORD,
    }
    data.update(overrides)
    return data


class RegistrationFormTests(TestCase):
    def test_fr1_ac2_collects_username_email_and_two_passwords(self):
        self.assertEqual(
            list(RegistrationForm().fields), ["username", "email", "password1", "password2"]
        )

    def test_fr1_ac2_email_is_required(self):
        form = RegistrationForm(data=registration_data(email=""))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_fr1_ac3_username_must_be_unique_case_insensitively(self):
        User.objects.create_user("Alice", password=STRONG_PASSWORD)
        form = RegistrationForm(data=registration_data(username="aLiCe"))
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_fr1_ac4_rejects_short_password(self):
        form = RegistrationForm(data=registration_data(password1="Ab1-x", password2="Ab1-x"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_fr1_ac4_rejects_common_password(self):
        form = RegistrationForm(data=registration_data(password1="password", password2="password"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_fr1_ac4_rejects_entirely_numeric_password(self):
        form = RegistrationForm(data=registration_data(password1="83920174", password2="83920174"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_fr1_ac4_rejects_password_similar_to_username(self):
        form = RegistrationForm(
            data=registration_data(
                username="weatherwatcher",
                password1="weatherwatcher1",
                password2="weatherwatcher1",
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)


class RegistrationViewTests(TestCase):
    def test_fr1_ac1_register_link_in_nav_for_anonymous_users(self):
        response = self.client.get("/")
        self.assertContains(response, f'href="{REGISTER_URL}"')

    def test_fr1_ac2_renders_form_with_labelled_fields(self):
        response = self.client.get(REGISTER_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register.html")
        for field in ("username", "email", "password1", "password2"):
            with self.subTest(field=field):
                self.assertContains(response, f'<label for="id_{field}"')
        self.assertContains(response, "<h1", count=1)

    def test_fr1_ac3_duplicate_username_error_is_shown_on_the_field(self):
        User.objects.create_user("alice", password=STRONG_PASSWORD)
        response = self.client.post(REGISTER_URL, registration_data(username="ALICE"))
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "username", "A user with that username already exists."
        )
        self.assertEqual(User.objects.count(), 1)

    def test_fr1_ac5_mismatched_passwords_redisplay_form_keeping_other_fields(self):
        response = self.client.post(
            REGISTER_URL, registration_data(password2="Different-Horse-92")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["password2"])
        self.assertContains(response, 'value="alice"')
        self.assertContains(response, 'value="alice@example.com"')
        self.assertNotContains(response, STRONG_PASSWORD)
        self.assertFalse(User.objects.exists())

    def test_nfr_ac5_field_errors_are_linked_with_aria_describedby(self):
        response = self.client.post(
            REGISTER_URL, registration_data(password2="Different-Horse-92")
        )
        self.assertContains(response, 'id="id_password2_error"')
        match = re.search(r'<input[^>]*\bid="id_password2"[^>]*>', response.content.decode())
        self.assertIsNotNone(match)
        self.assertIn('aria-invalid="true"', match.group())
        self.assertRegex(match.group(), r'aria-describedby="[^"]*\bid_password2_error\b')

    def test_fr1_ac6_success_creates_user_with_hashed_password(self):
        self.client.post(REGISTER_URL, registration_data())
        user = User.objects.get(username="alice")
        self.assertEqual(user.email, "alice@example.com")
        self.assertNotEqual(user.password, STRONG_PASSWORD)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))  # NFR-SEC-2
        self.assertTrue(user.check_password(STRONG_PASSWORD))

    def test_fr1_ac6_success_logs_in_and_redirects_home_with_message(self):
        response = self.client.post(REGISTER_URL, registration_data())
        self.assertRedirects(response, "/")
        user = User.objects.get(username="alice")
        self.assertEqual(self.client.session[SESSION_KEY], str(user.pk))
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("alice" in m and "created" in m.lower() for m in messages))

    def test_fr1_ac7_form_includes_csrf_token(self):
        response = self.client.get(REGISTER_URL)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')

    def test_fr1_ac7_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(REGISTER_URL, registration_data())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.exists())

    def test_logged_in_user_is_redirected_away_from_register(self):
        user = User.objects.create_user("bob", password=STRONG_PASSWORD)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(REGISTER_URL), "/")
