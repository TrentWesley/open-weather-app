"""WeatherService: current conditions (FR-8) and the 5-day forecast (FR-9).

Each method makes at most one call per OpenWeather endpoint (NFR-PERF-3), caches
the result (NFR-CACHE-1/2), and falls back to the last good copy, marked stale,
when OpenWeather fails (NFR-FT-2).
"""
import dataclasses
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

from accounts.models import TemperatureUnit
from weather.services.cache import WeatherCache
from weather.services.client import CURRENT_WEATHER, FORECAST_5DAY, OpenWeatherClient
from weather.services.domain import CurrentWeather, Forecast, ForecastEntry, Location
from weather.services.exceptions import OpenWeatherError
from weather.services.validation import malformed, require, require_number

logger = logging.getLogger(__name__)


class WeatherService:
    """Fetch, validate and cache weather for a Location in the user's unit."""

    def __init__(
        self, client: OpenWeatherClient | None = None, cache: WeatherCache | None = None
    ) -> None:
        self._client = client or OpenWeatherClient()
        self._cache = cache or WeatherCache()

    def current(self, location: Location, unit: TemperatureUnit | str) -> CurrentWeather:
        """Return current conditions; raise OpenWeatherError if no data, fresh or stale."""
        units = TemperatureUnit(unit).value
        key = WeatherCache.make_key("current", location.latitude, location.longitude, units)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            data = self._client.current_weather(location.latitude, location.longitude, units)
            weather = _parse_current(data, location, self._uv_index(location), timezone.now())
        except OpenWeatherError as error:
            return self._stale_or_raise(key, error)
        self._cache.set(key, weather, self._cache.CURRENT_TTL)
        return weather

    def forecast(self, location: Location, unit: TemperatureUnit | str) -> Forecast:
        """Return the 3-hour forecast; raise OpenWeatherError if no data, fresh or stale."""
        units = TemperatureUnit(unit).value
        key = WeatherCache.make_key("forecast", location.latitude, location.longitude, units)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            data = self._client.forecast_5day(location.latitude, location.longitude, units)
            forecast = _parse_forecast(data, location, timezone.now())
        except OpenWeatherError as error:
            return self._stale_or_raise(key, error)
        self._cache.set(key, forecast, self._cache.FORECAST_TTL)
        return forecast

    def _uv_index(self, location: Location) -> float | None:
        """UV from One Call 3.0 when enabled; None otherwise or if that call fails."""
        if not settings.OPENWEATHER_ENABLE_ONECALL:
            return None
        try:
            return self._client.uv_index(location.latitude, location.longitude)
        except OpenWeatherError as error:
            logger.warning(
                "UV index unavailable: %s (status=%s)", error.endpoint, error.status_code
            )
            return None

    def _stale_or_raise(self, key: str, error: OpenWeatherError):
        """Serve the last good copy, marked stale, or re-raise the error (NFR-FT-2)."""
        stale = self._cache.get_stale(key)
        if stale is None:
            raise error
        logger.info("Serving stale cached data for %s", key)
        return dataclasses.replace(stale, is_stale=True)


def _local_time(timestamp: float, offset: dt_timezone) -> datetime:
    return datetime.fromtimestamp(timestamp, offset)


def _utc_offset(data: dict, path: str, endpoint: str) -> dt_timezone:
    seconds = require(data, path, int, endpoint)
    return dt_timezone(timedelta(seconds=seconds))


def _parse_current(
    data: dict, location: Location, uv_index: float | None, retrieved_at: datetime
) -> CurrentWeather:
    endpoint = CURRENT_WEATHER
    offset = _utc_offset(data, "timezone", endpoint)
    return CurrentWeather(
        location=location,
        temperature=require_number(data, "main.temp", endpoint),
        feels_like=require_number(data, "main.feels_like", endpoint),
        temp_min=require_number(data, "main.temp_min", endpoint),
        temp_max=require_number(data, "main.temp_max", endpoint),
        description=require(data, "weather.0.description", str, endpoint),
        icon=require(data, "weather.0.icon", str, endpoint),
        humidity=int(require_number(data, "main.humidity", endpoint)),
        wind_speed=require_number(data, "wind.speed", endpoint),
        wind_deg=int(require_number(data, "wind.deg", endpoint)),
        pressure=int(require_number(data, "main.pressure", endpoint)),
        visibility=int(require_number(data, "visibility", endpoint)),
        clouds=int(require_number(data, "clouds.all", endpoint)),
        uv_index=uv_index,
        sunrise=_local_time(require_number(data, "sys.sunrise", endpoint), offset),
        sunset=_local_time(require_number(data, "sys.sunset", endpoint), offset),
        retrieved_at=retrieved_at,
    )


def _parse_forecast(data: dict, location: Location, retrieved_at: datetime) -> Forecast:
    endpoint = FORECAST_5DAY
    offset = _utc_offset(data, "city.timezone", endpoint)
    items = require(data, "list", list, endpoint)
    if not items:
        raise malformed(endpoint, "no forecast entries")
    return Forecast(
        location=location,
        entries=tuple(_parse_forecast_entry(item, offset) for item in items),
        retrieved_at=retrieved_at,
    )


def _parse_forecast_entry(item: dict, offset: dt_timezone) -> ForecastEntry:
    endpoint = FORECAST_5DAY
    pop = require_number(item, "pop", endpoint)
    if not 0 <= pop <= 1:
        raise malformed(endpoint, "pop out of range")
    return ForecastEntry(
        timestamp=_local_time(require_number(item, "dt", endpoint), offset),
        temperature=require_number(item, "main.temp", endpoint),
        pop=pop,
        precipitation_mm=_precipitation(item, "rain") + _precipitation(item, "snow"),
        icon=require(item, "weather.0.icon", str, endpoint),
        description=require(item, "weather.0.description", str, endpoint),
    )


def _precipitation(item: dict, kind: str) -> float:
    """Rain or snow volume for the 3-hour step; absent means none fell."""
    if kind not in item:
        return 0.0
    return require_number(item, f"{kind}.3h", FORECAST_5DAY)
