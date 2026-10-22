"""Base test classes that make any real network access fail loudly (NFR-REL-4).

Every test that touches weather code inherits from one of these, so a missing mock
shows up as a failure instead of a real call to OpenWeather.
"""
import json
import socket
from pathlib import Path
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase


def _block_network(*args, **kwargs):
    raise AssertionError(
        "Test attempted real network access; mock OpenWeatherClient or requests instead."
    )


class OfflineMixin:
    """Patch DNS lookups and socket connections for the duration of each test."""

    def setUp(self):
        super().setUp()
        for target, attribute in (
            (socket, "getaddrinfo"),
            (socket, "create_connection"),
            (socket.socket, "connect"),
            (socket.socket, "connect_ex"),
        ):
            patcher = mock.patch.object(target, attribute, _block_network)
            patcher.start()
            self.addCleanup(patcher.stop)


class OfflineSimpleTestCase(OfflineMixin, SimpleTestCase):
    """For tests that don't use the database."""


class OfflineTestCase(OfflineMixin, TestCase):
    """For tests that use the database."""


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str):
    """Return the parsed JSON of a recorded OpenWeather response."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def make_response(status_code: int = 200, body=None, *, raw: bytes | None = None):
    """Build a real requests.Response so .json() and status handling behave normally."""
    response = requests.Response()
    response.status_code = status_code
    response._content = raw if raw is not None else json.dumps(body).encode()
    response.headers["Content-Type"] = "application/json"
    response.encoding = "utf-8"
    return response
