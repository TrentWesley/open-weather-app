"""Tests for OpenWeatherClient, the single gateway to OpenWeather.

NFR-REL-1/2, NFR-PERF-2, NFR-FT-1/4/5, NFR-SEC-1. A fake session is injected, so
no request ever leaves the process; OfflineSimpleTestCase fails loudly if one does.
"""
from unittest import mock

import requests
from django.test import override_settings

from weather.services.client import OpenWeatherClient
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
    ServiceUnavailableError,
)
from weather.tests.base import OfflineSimpleTestCase, load_fixture, make_response

API_KEY = "test-key"
BASE = "https://api.openweathermap.org"


@override_settings(OPENWEATHER_API_KEY=API_KEY, OPENWEATHER_RETRY_BACKOFF=0.25)
class ClientTestCase(OfflineSimpleTestCase):
    def setUp(self):
        super().setUp()
        self.session = mock.Mock(spec=requests.Session)
        self.client_ = OpenWeatherClient(session=self.session)
        sleep = mock.patch("weather.services.client.time.sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def respond(self, *responses):
        self.session.request.side_effect = list(responses)

    def last_call(self):
        args, kwargs = self.session.request.call_args
        return args, kwargs

    def assertKeyNotIn(self, text):
        self.assertNotIn(API_KEY, str(text))


class RequestTests(ClientTestCase):
    def test_nfr_perf2_every_request_uses_five_second_timeout(self):
        self.respond(make_response(200, load_fixture("current_weather.json")))
        self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(self.last_call()[1]["timeout"], 5)

    def test_timeout_and_retries_come_from_settings(self):
        self.assertEqual(self.client_.timeout, 5)
        self.assertEqual(self.client_.retries, 1)
        with override_settings(OPENWEATHER_TIMEOUT=3, OPENWEATHER_RETRIES=0):
            client = OpenWeatherClient(session=self.session)
        self.assertEqual((client.timeout, client.retries), (3, 0))

    def test_nfr_sec1_api_key_is_sent_as_a_query_parameter_from_settings(self):
        self.respond(make_response(200, load_fixture("current_weather.json")))
        self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(self.last_call()[1]["params"]["appid"], API_KEY)

    def test_nfr_sec1_api_key_is_private_and_not_in_repr(self):
        self.assertFalse(hasattr(self.client_, "api_key"))
        self.assertKeyNotIn(repr(self.client_))

    def test_uses_a_requests_session_by_default(self):
        with mock.patch(
            "weather.services.client.requests.Session.request",
            return_value=make_response(200, load_fixture("current_weather.json")),
        ) as request:
            OpenWeatherClient().current_weather(35.22, -101.83, "imperial")
        request.assert_called_once()


class EndpointTests(ClientTestCase):
    def test_geocode_direct_calls_direct_endpoint_with_limit_five(self):
        self.respond(make_response(200, load_fixture("geocode_direct_multiple.json")))
        result = self.client_.geocode_direct("Springfield")
        args, kwargs = self.last_call()
        self.assertEqual(args, ("GET", f"{BASE}/geo/1.0/direct"))
        self.assertEqual(kwargs["params"]["q"], "Springfield")
        self.assertEqual(kwargs["params"]["limit"], 5)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["state"], "Illinois")

    def test_geocode_direct_returns_empty_list(self):
        self.respond(make_response(200, load_fixture("geocode_direct_empty.json")))
        self.assertEqual(self.client_.geocode_direct("Nowhereville"), [])

    def test_geocode_zip_defaults_country_to_us(self):
        self.respond(make_response(200, load_fixture("geocode_zip.json")))
        result = self.client_.geocode_zip("79015")
        args, kwargs = self.last_call()
        self.assertEqual(args, ("GET", f"{BASE}/geo/1.0/zip"))
        self.assertEqual(kwargs["params"]["zip"], "79015,US")
        self.assertEqual(result["name"], "Canyon")

    def test_geocode_zip_with_explicit_country(self):
        self.respond(make_response(200, load_fixture("geocode_zip.json")))
        self.client_.geocode_zip("SW1A 1AA", country="GB")
        self.assertEqual(self.last_call()[1]["params"]["zip"], "SW1A 1AA,GB")

    def test_reverse_geocode_calls_reverse_endpoint(self):
        self.respond(make_response(200, load_fixture("reverse_geocode.json")))
        result = self.client_.reverse_geocode(35.22, -101.83)
        args, kwargs = self.last_call()
        self.assertEqual(args, ("GET", f"{BASE}/geo/1.0/reverse"))
        self.assertEqual((kwargs["params"]["lat"], kwargs["params"]["lon"]), (35.22, -101.83))
        self.assertEqual(kwargs["params"]["limit"], 1)
        self.assertEqual(result[0]["name"], "Amarillo")

    def test_current_weather_calls_2_5_weather_with_units(self):
        self.respond(make_response(200, load_fixture("current_weather.json")))
        result = self.client_.current_weather(35.22, -101.83, "metric")
        args, kwargs = self.last_call()
        self.assertEqual(args, ("GET", f"{BASE}/data/2.5/weather"))
        self.assertEqual(kwargs["params"]["units"], "metric")
        self.assertEqual(result["name"], "Amarillo")

    def test_forecast_5day_calls_2_5_forecast_with_units(self):
        self.respond(make_response(200, load_fixture("forecast_5day.json")))
        result = self.client_.forecast_5day(35.22, -101.83, "imperial")
        args, kwargs = self.last_call()
        self.assertEqual(args, ("GET", f"{BASE}/data/2.5/forecast"))
        self.assertEqual(kwargs["params"]["units"], "imperial")
        self.assertEqual(len(result["list"]), 10)

    def test_uv_index_reads_current_uvi_from_one_call(self):
        self.respond(make_response(200, load_fixture("onecall_uvi.json")))
        self.assertEqual(self.client_.uv_index(35.22, -101.83), 6.2)
        args, kwargs = self.last_call()
        self.assertEqual(args, ("GET", f"{BASE}/data/3.0/onecall"))
        self.assertIn("daily", kwargs["params"]["exclude"])

    def test_uv_index_is_none_when_response_has_no_uvi(self):
        self.respond(make_response(200, {"current": {"temp": 60}}))
        self.assertIsNone(self.client_.uv_index(35.22, -101.83))


class ErrorMappingTests(ClientTestCase):
    """NFR-FT-4: 401 and 429 are distinct; 5xx means the service is unavailable."""

    def test_nfr_ft4_401_raises_authentication_error_without_retry(self):
        self.respond(make_response(401, {"cod": 401, "message": "Invalid API key."}))
        with self.assertRaises(AuthenticationError) as ctx:
            self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.endpoint, "/data/2.5/weather")
        self.assertEqual(self.session.request.call_count, 1)

    def test_nfr_ft4_429_raises_rate_limit_error_without_retry(self):
        self.respond(make_response(429, {"cod": 429}))
        with self.assertRaises(RateLimitError) as ctx:
            self.client_.forecast_5day(35.22, -101.83, "imperial")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(self.session.request.call_count, 1)

    def test_nfr_ft4_5xx_raises_service_unavailable_after_one_retry(self):
        self.respond(make_response(502, {}), make_response(503, {}))
        with self.assertRaises(ServiceUnavailableError) as ctx:
            self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(self.session.request.call_count, 2)

    def test_other_4xx_raises_base_error_with_status(self):
        self.respond(make_response(404, load_fixture("geocode_zip_not_found.json")))
        with self.assertRaises(OpenWeatherError) as ctx:
            self.client_.geocode_zip("00000")
        self.assertEqual(type(ctx.exception), OpenWeatherError)
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(self.session.request.call_count, 1)

    def test_subclasses_share_the_base_error(self):
        for cls in (AuthenticationError, RateLimitError, ServiceUnavailableError):
            self.assertTrue(issubclass(cls, OpenWeatherError))


class RetryTests(ClientTestCase):
    """NFR-FT-5: transient errors are retried once with a short backoff."""

    def test_nfr_ft5_connection_error_is_retried_once_then_raised(self):
        self.respond(requests.ConnectionError("down"), requests.ConnectionError("down"))
        with self.assertRaises(ServiceUnavailableError) as ctx:
            self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertIsNone(ctx.exception.status_code)
        self.assertEqual(self.session.request.call_count, 2)
        self.sleep.assert_called_once_with(0.25)

    def test_nfr_ft5_connection_error_then_success_returns_data(self):
        self.respond(
            requests.ConnectionError("blip"),
            make_response(200, load_fixture("current_weather.json")),
        )
        result = self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(result["name"], "Amarillo")
        self.assertEqual(self.session.request.call_count, 2)

    def test_nfr_ft1_timeout_is_retried_once_then_raised(self):
        self.respond(requests.Timeout(), requests.Timeout())
        with self.assertRaises(ServiceUnavailableError):
            self.client_.forecast_5day(35.22, -101.83, "imperial")
        self.assertEqual(self.session.request.call_count, 2)

    def test_5xx_then_success_returns_data(self):
        self.respond(make_response(500, {}), make_response(200, load_fixture("reverse_geocode.json")))
        self.assertEqual(self.client_.reverse_geocode(35.22, -101.83)[0]["name"], "Amarillo")

    def test_no_sleep_after_the_final_attempt(self):
        self.respond(requests.Timeout(), requests.Timeout())
        with self.assertRaises(ServiceUnavailableError):
            self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(self.sleep.call_count, 1)

    @override_settings(OPENWEATHER_RETRIES=0)
    def test_retries_can_be_disabled(self):
        client = OpenWeatherClient(session=self.session)
        self.respond(requests.ConnectionError("down"))
        with self.assertRaises(ServiceUnavailableError):
            client.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(self.session.request.call_count, 1)
        self.sleep.assert_not_called()


class ResponseValidationTests(ClientTestCase):
    def test_malformed_json_raises_openweather_error(self):
        self.respond(make_response(200, raw=b"<html>not json</html>"))
        with self.assertRaises(OpenWeatherError) as ctx:
            self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertEqual(ctx.exception.status_code, 200)

    def test_list_endpoint_returning_an_object_is_rejected(self):
        self.respond(make_response(200, {"unexpected": "object"}))
        with self.assertRaises(OpenWeatherError):
            self.client_.geocode_direct("Springfield")

    def test_object_endpoint_returning_a_list_is_rejected(self):
        self.respond(make_response(200, []))
        with self.assertRaises(OpenWeatherError):
            self.client_.current_weather(35.22, -101.83, "imperial")

    def test_malformed_json_is_not_retried(self):
        self.respond(make_response(200, raw=b"{"))
        with self.assertRaises(OpenWeatherError):
            self.client_.forecast_5day(35.22, -101.83, "imperial")
        self.assertEqual(self.session.request.call_count, 1)


class KeySafetyTests(ClientTestCase):
    """NFR-SEC-1 / NFR-REL-2: the key never appears in errors or logs."""

    LEAKY_MESSAGE = f"Max retries exceeded with url: /data/2.5/weather?appid={API_KEY}"

    def test_nfr_rel2_errors_are_logged_with_endpoint_and_status_only(self):
        self.respond(make_response(503, {}), make_response(503, {}))
        with self.assertLogs("weather.services.client", "WARNING") as logs:
            with self.assertRaises(ServiceUnavailableError):
                self.client_.current_weather(35.22, -101.83, "imperial")
        output = "\n".join(logs.output)
        self.assertIn("/data/2.5/weather", output)
        self.assertIn("503", output)
        self.assertKeyNotIn(output)
        self.assertNotIn("appid", output)

    def test_nfr_ft4_401_and_429_have_distinct_log_entries(self):
        self.respond(make_response(401, {}))
        with self.assertLogs("weather.services.client", "WARNING") as auth_logs:
            with self.assertRaises(AuthenticationError):
                self.client_.current_weather(35.22, -101.83, "imperial")
        self.respond(make_response(429, {}))
        with self.assertLogs("weather.services.client", "WARNING") as rate_logs:
            with self.assertRaises(RateLimitError):
                self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertIn("API key", "\n".join(auth_logs.output))
        self.assertIn("rate limit", "\n".join(rate_logs.output).lower())

    def test_nfr_sec1_connection_error_text_with_key_never_leaks(self):
        self.respond(
            requests.ConnectionError(self.LEAKY_MESSAGE),
            requests.ConnectionError(self.LEAKY_MESSAGE),
        )
        with self.assertLogs("weather.services.client", "WARNING") as logs:
            with self.assertRaises(ServiceUnavailableError) as ctx:
                self.client_.current_weather(35.22, -101.83, "imperial")
        error = ctx.exception
        self.assertKeyNotIn(error)
        self.assertKeyNotIn(repr(error))
        # The original requests exception (whose text has the key) must not be chained.
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__context__ is None or error.__suppress_context__)
        self.assertKeyNotIn("\n".join(logs.output))

    def test_nfr_sec1_http_error_message_never_contains_key(self):
        self.respond(make_response(401, {"message": f"Invalid API key {API_KEY}"}))
        with self.assertRaises(AuthenticationError) as ctx:
            self.client_.current_weather(35.22, -101.83, "imperial")
        self.assertKeyNotIn(ctx.exception)
