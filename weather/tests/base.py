"""Base test classes that make any real network access fail loudly (NFR-REL-4).

Every test that touches weather code inherits from one of these, so a missing mock
shows up as a failure instead of a real call to OpenWeather.
"""
import socket
from unittest import mock

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
