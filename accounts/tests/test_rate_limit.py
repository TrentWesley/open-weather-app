"""Tests for login rate limiting (NFR-SEC-7): 5 failures per 5 minutes per IP and username."""
import time
from unittest import mock

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.ratelimit import LoginRateLimiter

LOGIN_URL = "/accounts/login/"
PASSWORD = "Correct-Horse-91"
BLOCKED_MESSAGE = "Too many failed login attempts"


class LoginRateLimiterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.limiter = LoginRateLimiter()

    def record_failures(self, times, ip="10.0.0.1", username="alice"):
        for _ in range(times):
            self.limiter.record_failure(ip, username)

    def test_nfr_sec7_defaults_are_five_failures_per_five_minutes(self):
        self.assertEqual(settings.LOGIN_RATE_LIMIT, {"max_failures": 5, "window": 300})

    def test_nfr_sec7_not_blocked_initially(self):
        self.assertFalse(self.limiter.is_blocked("10.0.0.1", "alice"))

    def test_nfr_sec7_four_failures_are_allowed(self):
        self.record_failures(4)
        self.assertFalse(self.limiter.is_blocked("10.0.0.1", "alice"))

    def test_nfr_sec7_five_failures_block_the_username_from_any_ip(self):
        for n in range(5):
            self.limiter.record_failure(f"10.0.0.{n}", "alice")
        self.assertTrue(self.limiter.is_blocked("192.168.1.1", "alice"))
        self.assertFalse(self.limiter.is_blocked("192.168.1.1", "bob"))

    def test_nfr_sec7_five_failures_block_the_ip_for_any_username(self):
        for name in ("a", "b", "c", "d", "e"):
            self.limiter.record_failure("10.0.0.1", name)
        self.assertTrue(self.limiter.is_blocked("10.0.0.1", "zed"))
        self.assertFalse(self.limiter.is_blocked("10.0.0.2", "zed"))

    def test_nfr_sec7_username_counter_ignores_case_and_whitespace(self):
        for n, name in enumerate(("alice", "ALICE", " Alice ", "aLiCe", "alicE")):
            self.limiter.record_failure(f"10.0.0.{n}", name)
        self.assertTrue(self.limiter.is_blocked("10.9.9.9", "alice"))

    def test_nfr_sec7_block_expires_after_the_window(self):
        self.record_failures(5)
        later = time.time() + 301
        with mock.patch("time.time", return_value=later):
            self.assertFalse(self.limiter.is_blocked("10.0.0.1", "alice"))

    def test_nfr_sec7_block_still_active_inside_the_window(self):
        self.record_failures(5)
        later = time.time() + 299
        with mock.patch("time.time", return_value=later):
            self.assertTrue(self.limiter.is_blocked("10.0.0.1", "alice"))

    def test_reset_clears_the_username_counter_only(self):
        self.record_failures(5)
        self.limiter.reset("alice")
        self.assertFalse(self.limiter.is_blocked("10.0.0.2", "alice"))
        self.assertTrue(self.limiter.is_blocked("10.0.0.1", "bob"))

    @override_settings(LOGIN_RATE_LIMIT={"max_failures": 2, "window": 60})
    def test_limits_come_from_settings(self):
        limiter = LoginRateLimiter()
        limiter.record_failure("10.0.0.1", "alice")
        self.assertFalse(limiter.is_blocked("10.0.0.1", "alice"))
        limiter.record_failure("10.0.0.1", "alice")
        self.assertTrue(limiter.is_blocked("10.0.0.1", "alice"))

    def test_cache_keys_do_not_contain_the_raw_username(self):
        self.assertNotIn("alice", self.limiter.username_key("alice"))


class LoginViewRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice", password=PASSWORD)

    def post(self, username="alice", password="wrong-password", ip="10.0.0.1"):
        return self.client.post(
            LOGIN_URL, {"username": username, "password": password}, REMOTE_ADDR=ip
        )

    def test_nfr_sec7_sixth_attempt_is_blocked_even_with_correct_password(self):
        for _ in range(5):
            self.assertEqual(self.post().status_code, 200)
        response = self.post(password=PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, BLOCKED_MESSAGE, status_code=429)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_nfr_sec7_blocked_attempt_does_not_check_credentials(self):
        for _ in range(5):
            self.post()
        with mock.patch("django.contrib.auth.forms.authenticate") as authenticate:
            self.post(password=PASSWORD)
        authenticate.assert_not_called()

    def test_nfr_sec7_same_username_from_new_ip_is_blocked(self):
        for n in range(5):
            self.post(ip=f"10.0.0.{n}")
        self.assertEqual(self.post(password=PASSWORD, ip="172.16.0.1").status_code, 429)

    def test_nfr_sec7_other_usernames_from_same_ip_are_blocked(self):
        for name in ("a", "b", "c", "d", "e"):
            self.post(username=name)
        self.assertEqual(self.post(password=PASSWORD).status_code, 429)

    def test_nfr_sec7_successful_login_resets_the_username_counter(self):
        for n in range(4):
            self.post(ip=f"10.0.0.{n}")
        self.post(password=PASSWORD, ip="10.0.1.1")
        self.client.logout()
        for n in range(4):
            self.post(ip=f"10.0.2.{n}")
        self.assertEqual(self.post(password=PASSWORD, ip="10.0.3.1").status_code, 302)

    def test_nfr_sec7_empty_submissions_are_not_counted(self):
        for _ in range(6):
            self.post(username="", password="")
        self.assertEqual(self.post(password=PASSWORD).status_code, 302)
