"""Turn weather values into display text in the user's unit (FR-3, FR-8, NFR-USE-6).

OpenWeather already returns temperatures and wind speed in the requested unit
(°F and mph for imperial, °C and m/s for metric); visibility is always metres.
Times are formatted in the zone they carry, which is the location's local time.
"""
import math
import re
from datetime import datetime, timedelta

from accounts.models import TemperatureUnit

METRES_PER_MILE = 1609.344
ICON_BASE_URL = "https://openweathermap.org/img/wn/"
_ICON_CODE = re.compile(r"\d{2}[dn]")


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _one_decimal(value: float) -> str:
    """One decimal place, dropping a trailing ".0" (10.0 -> "10")."""
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def format_temperature(value: float, unit: TemperatureUnit | str) -> str:
    symbol = "°F" if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL else "°C"
    return f"{_round_half_up(value)}{symbol}"


def format_speed(value: float, unit: TemperatureUnit | str) -> str:
    """FR-3 AC-6: mph for imperial, m/s for metric."""
    if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL:
        return f"{_round_half_up(value)} mph"
    return f"{value:.1f} m/s"


def format_distance(metres: float, unit: TemperatureUnit | str) -> str:
    if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL:
        return f"{_one_decimal(metres / METRES_PER_MILE)} mi"
    return f"{_one_decimal(metres / 1000)} km"


def format_time(moment: datetime) -> str:
    """e.g. "6:42 PM" (no leading zero)."""
    return moment.strftime("%I:%M %p").lstrip("0")


def format_datetime(moment: datetime) -> str:
    """NFR-USE-6: e.g. "Tue, Oct 20 · 6:42 PM"."""
    return f"{moment:%a, %b} {moment.day} · {format_time(moment)}"


def format_age(age: timedelta) -> str:
    """How old data is, e.g. "11 minutes" or "2 hours" (NFR-CACHE-4, NFR-FT-2)."""
    minutes = int(age.total_seconds() // 60)
    if minutes < 1:
        return "less than a minute"
    if minutes < 120:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''}"


def icon_url(code: str) -> str:
    """URL of OpenWeather's public icon image, or "" for an unexpected code."""
    if not _ICON_CODE.fullmatch(code or ""):
        return ""
    return f"{ICON_BASE_URL}{code}@2x.png"
