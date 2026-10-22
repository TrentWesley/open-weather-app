"""WeatherCache: the only place OpenWeather results are cached (NFR-CACHE-1..3, NFR-FT-2).

Every value is written twice: a fresh entry that expires after its TTL, and a
last-good copy that lives WEATHER_CACHE_STALE_TTL longer so services can fall
back to it when OpenWeather fails. Cached weather objects carry their own
`retrieved_at`, so the age of stale data can be shown (NFR-CACHE-4).
"""
from typing import Any

from django.conf import settings
from django.core.cache import BaseCache, cache as default_cache

STALE_SUFFIX = ":stale"


class WeatherCache:
    """Fresh and stale storage over Django's cache framework."""

    def __init__(self, backend: BaseCache | None = None) -> None:
        self._cache = backend or default_cache

    @property
    def GEOCODE_TTL(self) -> int:
        return settings.WEATHER_CACHE_TTL["geocode"]

    @property
    def CURRENT_TTL(self) -> int:
        return settings.WEATHER_CACHE_TTL["current"]

    @property
    def FORECAST_TTL(self) -> int:
        return settings.WEATHER_CACHE_TTL["forecast"]

    def get(self, key: str) -> Any | None:
        """Return the fresh value for `key`, or None if it is missing or expired."""
        return self._cache.get(key)

    def get_stale(self, key: str) -> Any | None:
        """Return the last good value for `key`, even after its fresh entry expired."""
        return self._cache.get(key + STALE_SUFFIX)

    def set(self, key: str, value: Any, ttl: int) -> None:
        """Store a successful result. None is ignored, since it reads back as a miss."""
        if value is None:
            return
        self._cache.set(key, value, timeout=ttl)
        self._cache.set(key + STALE_SUFFIX, value, timeout=ttl + settings.WEATHER_CACHE_STALE_TTL)

    @staticmethod
    def make_key(endpoint: str, lat: float, lon: float, units: str) -> str:
        """Key on endpoint, coordinates rounded to 2 decimals, and units."""
        # Adding 0.0 turns -0.0 into 0.0, so "-0.00" and "0.00" share a key.
        lat_text = f"{round(lat, 2) + 0.0:.2f}"
        lon_text = f"{round(lon, 2) + 0.0:.2f}"
        return f"weather:{endpoint}:{lat_text}:{lon_text}:{units}"
