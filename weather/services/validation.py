"""Checks applied to OpenWeather payloads and coordinates before building value objects.

A payload that fails these checks raises OpenWeatherError, so callers handle it
like any other failed request, and it is never cached.
"""
from typing import Any

from weather.services.exceptions import OpenWeatherError


def check_coordinates(lat: float, lon: float) -> None:
    """Raise ValueError unless lat is in [-90, 90] and lon in [-180, 180] (NFR-SEC-5)."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(
            "Latitude must be between -90 and 90 and longitude between -180 and 180."
        )


def require(data: Any, path: str, kind: type | tuple[type, ...], endpoint: str) -> Any:
    """Return the value at a dotted `path` (e.g. "weather.0.icon") or raise OpenWeatherError."""
    value = data
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise malformed(endpoint, f"missing {path}")
    # bool is an int subclass, but never a valid number in these payloads.
    if isinstance(value, bool) or not isinstance(value, kind):
        raise malformed(endpoint, f"unexpected type for {path}")
    return value


def require_number(data: Any, path: str, endpoint: str) -> float:
    return float(require(data, path, (int, float), endpoint))


def malformed(endpoint: str, detail: str) -> OpenWeatherError:
    return OpenWeatherError(
        f"OpenWeather returned a malformed response ({detail}).", endpoint=endpoint
    )
