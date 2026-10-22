"""Plain value objects returned by the weather services (see docs/diagrams/class.mmd)."""
import math
from dataclasses import dataclass
from datetime import datetime

COMPASS_POINTS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)
# WHO UV index bands: highest whole-number index in each category.
UV_CATEGORIES = ((2, "Low"), (5, "Moderate"), (7, "High"), (10, "Very High"))


@dataclass(frozen=True)
class Location:
    """A place resolved to a name, region, country and coordinates."""

    name: str
    state: str
    country: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class CurrentWeather:
    """FR-8: conditions now at a location, in the units they were requested in.

    `uv_index` is None unless One Call 3.0 is enabled and reports it (FR-8 AC-4).
    Times are aware datetimes in the location's own UTC offset.
    """

    location: Location
    temperature: float
    feels_like: float
    temp_min: float
    temp_max: float
    description: str
    icon: str
    humidity: int
    wind_speed: float
    wind_deg: int
    pressure: int
    visibility: int
    clouds: int
    uv_index: float | None
    sunrise: datetime
    sunset: datetime
    retrieved_at: datetime
    is_stale: bool = False

    def wind_compass(self) -> str:
        """Wind direction as a 16-point compass label, e.g. 315 degrees -> "NW"."""
        return COMPASS_POINTS[round(self.wind_deg / 22.5) % 16]

    def uv_category(self) -> str | None:
        """WHO risk category for the UV index, or None when it is unavailable."""
        if self.uv_index is None:
            return None
        index = math.floor(self.uv_index + 0.5)  # Half up: 2.5 counts as 3.
        for highest, category in UV_CATEGORIES:
            if index <= highest:
                return category
        return "Extreme"


@dataclass(frozen=True)
class ForecastEntry:
    """One 3-hour step of the 5-day forecast (FR-9)."""

    timestamp: datetime
    temperature: float
    pop: float
    precipitation_mm: float
    icon: str
    description: str


@dataclass(frozen=True)
class Forecast:
    """FR-9: 3-hour forecast entries for a location, in the location's time zone."""

    location: Location
    entries: tuple[ForecastEntry, ...]
    retrieved_at: datetime
    is_stale: bool = False
