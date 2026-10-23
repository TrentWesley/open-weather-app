"""OpenWeatherClient: the only module that talks to OpenWeather (NFR-REL-1).

It owns the API key, the request timeout (NFR-PERF-2), one retry on transient
errors (NFR-FT-5), mapping HTTP failures to exceptions (NFR-FT-4), and logging
that names the endpoint and status code but never the key (NFR-REL-2).
"""
import logging
import time
from typing import Any

import requests
from django.conf import settings

from weather.services.domain import MapLayer
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openweathermap.org"
GEOCODE_DIRECT = "/geo/1.0/direct"
GEOCODE_ZIP = "/geo/1.0/zip"
GEOCODE_REVERSE = "/geo/1.0/reverse"
CURRENT_WEATHER = "/data/2.5/weather"
FORECAST_5DAY = "/data/2.5/forecast"
ONE_CALL = "/data/3.0/onecall"
TILE_BASE_URL = "https://tile.openweathermap.org"


class OpenWeatherClient:
    """Thin wrapper over the OpenWeather HTTP APIs: parsed JSON, or PNG bytes for tiles."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self._api_key: str = settings.OPENWEATHER_API_KEY
        self._session = session or requests.Session()
        self.timeout: int = settings.OPENWEATHER_TIMEOUT
        self.retries: int = settings.OPENWEATHER_RETRIES
        self._backoff: float = settings.OPENWEATHER_RETRY_BACKOFF

    def __repr__(self) -> str:
        return f"OpenWeatherClient(timeout={self.timeout}, retries={self.retries})"

    def geocode_direct(self, query: str, limit: int = 5) -> list[dict]:
        return self._get(GEOCODE_DIRECT, {"q": query, "limit": limit}, expect=list)

    def geocode_zip(self, zip_code: str, country: str = "US") -> dict:
        return self._get(GEOCODE_ZIP, {"zip": f"{zip_code},{country}"}, expect=dict)

    def reverse_geocode(self, lat: float, lon: float) -> list[dict]:
        return self._get(GEOCODE_REVERSE, {"lat": lat, "lon": lon, "limit": 1}, expect=list)

    def current_weather(self, lat: float, lon: float, units: str) -> dict:
        return self._get(CURRENT_WEATHER, {"lat": lat, "lon": lon, "units": units}, expect=dict)

    def forecast_5day(self, lat: float, lon: float, units: str) -> dict:
        return self._get(FORECAST_5DAY, {"lat": lat, "lon": lon, "units": units}, expect=dict)

    def uv_index(self, lat: float, lon: float) -> float | None:
        """Current UV index from One Call 3.0 (separate subscription), if it reports one."""
        params = {"lat": lat, "lon": lon, "exclude": "minutely,hourly,daily,alerts"}
        data = self._get(ONE_CALL, params, expect=dict)
        uvi = (data.get("current") or {}).get("uvi")
        return float(uvi) if isinstance(uvi, (int, float)) else None

    def map_tile(self, layer: MapLayer, z: int, x: int, y: int) -> bytes:
        """FR-12 AC-6: one Weather Maps 1.0 PNG tile, fetched with the key server-side.

        Logs name the layer only (`/map/<layer>`), never the key or the full URL.
        """
        endpoint = f"/map/{layer.tile_name}"
        url = f"{TILE_BASE_URL}{endpoint}/{z}/{x}/{y}.png"
        response = self._request(url, endpoint, {})
        if not response.headers.get("Content-Type", "").startswith("image/"):
            logger.warning(
                "OpenWeather %s returned a non-image tile (status=%s)",
                endpoint, response.status_code,
            )
            raise OpenWeatherError(
                "OpenWeather returned a malformed tile.",
                endpoint=endpoint,
                status_code=response.status_code,
            )
        return response.content

    def _get(self, endpoint: str, params: dict[str, Any], expect: type) -> Any:
        """GET a JSON endpoint and return its validated JSON."""
        response = self._request(BASE_URL + endpoint, endpoint, params)
        return self._parse(response, endpoint, expect)

    def _request(self, url: str, endpoint: str, params: dict[str, Any]) -> requests.Response:
        """GET `url` with the key added, retrying transient failures (NFR-FT-5).

        Returns the successful response; raises an OpenWeatherError subclass otherwise.
        """
        params = {**params, "appid": self._api_key}
        for attempt in range(self.retries + 1):
            try:
                response = self._session.request(
                    "GET", url, params=params, timeout=self.timeout
                )
            except requests.Timeout:
                error = ServiceUnavailableError("OpenWeather timed out.", endpoint=endpoint)
            except requests.ConnectionError:
                error = ServiceUnavailableError(
                    "Could not connect to OpenWeather.", endpoint=endpoint
                )
            except requests.RequestException:
                logger.warning("OpenWeather request to %s failed before a response", endpoint)
                raise OpenWeatherError(endpoint=endpoint) from None
            else:
                status = response.status_code
                if status < 400:
                    return response
                if status < 500:
                    raise self._client_error(endpoint, status)
                error = ServiceUnavailableError(endpoint=endpoint, status_code=status)

            logger.warning(
                "OpenWeather %s failed (status=%s, attempt %d of %d)",
                endpoint, error.status_code, attempt + 1, self.retries + 1,
            )
            if attempt < self.retries:
                time.sleep(self._backoff)
        raise error

    def _client_error(self, endpoint: str, status: int) -> OpenWeatherError:
        if status == 401:
            logger.error("OpenWeather rejected the API key (status=401) for %s", endpoint)
            return AuthenticationError(endpoint=endpoint, status_code=status)
        if status == 429:
            logger.warning("OpenWeather rate limit exceeded (status=429) for %s", endpoint)
            return RateLimitError(endpoint=endpoint, status_code=status)
        logger.info("OpenWeather %s returned status=%s", endpoint, status)
        return OpenWeatherError(endpoint=endpoint, status_code=status)

    def _parse(self, response: requests.Response, endpoint: str, expect: type) -> Any:
        try:
            data = response.json()
        except ValueError:
            data = None
        if not isinstance(data, expect):
            logger.warning(
                "OpenWeather %s returned a malformed response (status=%s)",
                endpoint, response.status_code,
            )
            raise OpenWeatherError(
                "OpenWeather returned a malformed response.",
                endpoint=endpoint,
                status_code=response.status_code,
            )
        return data
