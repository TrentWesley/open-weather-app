"""Turn weather values into display text in the user's unit (FR-3, FR-8, NFR-USE-6).

OpenWeather already returns temperatures and wind speed in the requested unit
(°F and mph for imperial, °C and m/s for metric); visibility is always metres.
Times are formatted in the zone they carry, which is the location's local time.
"""
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from accounts.models import TemperatureUnit

METRES_PER_MILE = 1609.344
MM_PER_INCH = 25.4
ICON_BASE_URL = "https://openweathermap.org/img/wn/"
_ICON_CODE = re.compile(r"\d{2}[dn]")


def round_half_up(value: float, places: int = 0) -> float:
    """Round like people expect (1.25 -> 1.3), not banker's rounding (1.25 -> 1.2)."""
    step = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(step, rounding=ROUND_HALF_UP))


def whole(value: float) -> int:
    return int(round_half_up(value))


def trimmed(value: float, places: int) -> str:
    """Fixed decimals without trailing zeros: 0.10 -> "0.1", 3.00 -> "3"."""
    text = f"{round_half_up(value, places):.{places}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def precipitation_in_unit(mm: float, unit: TemperatureUnit | str) -> float:
    """Millimetres for metric, inches (2 decimals) for imperial."""
    if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL:
        return round_half_up(mm / MM_PER_INCH, 2)
    return round_half_up(mm, 2)


def precipitation_unit(unit: TemperatureUnit | str) -> str:
    return "in" if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL else "mm"


def temperature_symbol(unit: TemperatureUnit | str) -> str:
    return "°F" if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL else "°C"


def format_temperature(value: float, unit: TemperatureUnit | str) -> str:
    return f"{whole(value)}{temperature_symbol(unit)}"


def format_speed(value: float, unit: TemperatureUnit | str) -> str:
    """FR-3 AC-6: mph for imperial, m/s for metric."""
    if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL:
        return f"{whole(value)} mph"
    return f"{value:.1f} m/s"


def format_distance(metres: float, unit: TemperatureUnit | str) -> str:
    if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL:
        return f"{trimmed(metres / METRES_PER_MILE, 1)} mi"
    return f"{trimmed(metres / 1000, 1)} km"


def format_precipitation(mm: float, unit: TemperatureUnit | str) -> str:
    """e.g. "1.3 mm" or "0.05 in"."""
    places = 2 if TemperatureUnit(unit) == TemperatureUnit.IMPERIAL else 1
    return f"{trimmed(precipitation_in_unit(mm, unit), places)} {precipitation_unit(unit)}"


def format_percent(fraction: float) -> str:
    """A 0-1 probability as a whole percentage, e.g. 0.35 -> "35%"."""
    return f"{whole(fraction * 100)}%"


def format_time(moment: datetime) -> str:
    """e.g. "6:42 PM" (no leading zero)."""
    return moment.strftime("%I:%M %p").lstrip("0")


def format_datetime(moment: datetime) -> str:
    """NFR-USE-6: e.g. "Tue, Oct 20 · 6:42 PM"."""
    return f"{moment:%a, %b} {moment.day} · {format_time(moment)}"


def format_hour(moment: datetime) -> str:
    """Forecast step label, e.g. "Thu 10 AM"."""
    hour = moment.strftime("%I").lstrip("0")
    return f"{moment:%a} {hour} {moment:%p}"


def format_date(day: date) -> str:
    """Daily summary label, e.g. "Thu, Oct 22"."""
    return f"{day:%a, %b} {day.day}"


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
