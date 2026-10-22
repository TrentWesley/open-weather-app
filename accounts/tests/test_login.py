"""Tests for login, logout and the account navigation (FR-2, NFR-SEC-3, NFR-SEC-8)."""
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import Client, TestCase

LOGIN_URL = "/accounts/login/"
LOGOUT_URL = "/accounts/logout/"
PASSWORD = "Correct-Horse-91"
GENERIC_ERROR = "Invalid username or password"


class LoginTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", "alice@example.com", PASSWORD)

    def login(self, username="alice", password=PASSWORD, next_url=None):
        url = LOGIN_URL if next_url is None else f"{LOGIN_URL}?next={next_url}"
        return self.client.post(url, {"username": username, "password": password})


class LoginPageTests(LoginTestCase):
    def test_fr2_ac1_login_page_has_labelled_username_and_password(self):
        response = self.client.get(LOGIN_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")
        self.assertContains(response, '<label for="id_username"')
        self.assertContains(response, '<label for="id_password"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "<h1", count=1)

    def test_fr2_ac2_wrong_password_shows_generic_error(self):
        response = self.login(password="wrong-password")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_ERROR)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_fr2_ac2_unknown_username_shows_the_same_generic_error(self):
        response = self.login(username="nobody")
        self.assertContains(response, GENERIC_ERROR)
        form = response.context["form"]
        self.assertFalse(form.has_error("username"))
        self.assertFalse(form.has_error("password"))

    def test_fr2_ac3_success_redirects_home_by_default(self):
        response = self.login()
        self.assertRedirects(response, "/")
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))

    def test_fr2_ac3_success_redirects_to_same_site_next(self):
        response = self.login(next_url="/accounts/register/")
        self.assertRedirects(response, "/accounts/register/", fetch_redirect_response=False)

    def test_nfr_sec8_external_next_is_ignored(self):
        for next_url in ("https://evil.example/", "//evil.example/", "http:evil.example"):
            with self.subTest(next_url=next_url):
                self.client.logout()
                response = self.login(next_url=next_url)
                self.assertRedirects(response, "/")

    def test_fr2_ac3_next_is_carried_through_the_form(self):
        response = self.client.get(f"{LOGIN_URL}?next=/accounts/register/")
        self.assertContains(response, 'name="next" value="/accounts/register/"')

    def test_nfr_sec8_external_next_is_not_carried_through_the_form(self):
        response = self.client.get(f"{LOGIN_URL}?next=https://evil.example/")
        self.assertNotContains(response, "evil.example")

    def test_nfr_sec3_login_post_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(LOGIN_URL, {"username": "alice", "password": PASSWORD})
        self.assertEqual(response.status_code, 403)


class LogoutTests(LoginTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_fr2_ac5_logout_ends_session_and_redirects_home_with_message(self):
        response = self.client.post(LOGOUT_URL)
        self.assertRedirects(response, "/")
        self.assertNotIn(SESSION_KEY, self.client.session)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn("You have been logged out.", messages)

    def test_fr2_ac5_logout_rejects_get(self):
        response = self.client.get(LOGOUT_URL)
        self.assertEqual(response.status_code, 405)
        self.assertIn(SESSION_KEY, self.client.session)

    def test_nfr_sec3_logout_without_csrf_token_is_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(LOGOUT_URL).status_code, 403)


class NavigationTests(LoginTestCase):
    def test_fr2_ac4_anonymous_nav_shows_login_and_register(self):
        response = self.client.get("/")
        self.assertContains(response, f'href="{LOGIN_URL}"')
        self.assertContains(response, 'href="/accounts/register/"')
        self.assertNotContains(response, f'action="{LOGOUT_URL}"')

    def test_fr2_ac4_logged_in_nav_shows_username_and_logout_control(self):
        self.client.force_login(self.user)
        response = self.client.get("/")
        self.assertContains(response, "alice")
        self.assertContains(response, f'<form method="post" action="{LOGOUT_URL}"')
        self.assertNotContains(response, f'href="{LOGIN_URL}"')
        self.assertNotContains(response, 'href="/accounts/register/"')
