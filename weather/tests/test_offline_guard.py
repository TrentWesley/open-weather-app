"""Tests for the offline network guard used by all weather tests (NFR-REL-4)."""
import socket

import requests

from weather.tests.base import OfflineSimpleTestCase, OfflineTestCase


class OfflineSimpleTestCaseTests(OfflineSimpleTestCase):
    def test_requests_call_fails_loudly(self):
        # 192.0.2.1 is TEST-NET-1: never routable, and needs no DNS lookup.
        with self.assertRaisesMessage(AssertionError, "network access"):
            requests.get("http://192.0.2.1/", timeout=1)

    def test_dns_lookup_fails_loudly(self):
        with self.assertRaisesMessage(AssertionError, "network access"):
            socket.getaddrinfo("api.openweathermap.org", 443)

    def test_raw_socket_connect_fails_loudly(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        with self.assertRaisesMessage(AssertionError, "network access"):
            sock.connect(("192.0.2.1", 80))


class OfflineTestCaseTests(OfflineTestCase):
    def test_guard_applies_to_database_test_case(self):
        with self.assertRaisesMessage(AssertionError, "network access"):
            requests.get("http://192.0.2.1/", timeout=1)

    def test_guard_does_not_block_django_test_client(self):
        response = self.client.get("/missing/")
        self.assertEqual(response.status_code, 404)
