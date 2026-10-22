"""Plain value objects returned by the weather services (see docs/diagrams/class.mmd)."""
from dataclasses import dataclass
from datetime import datetime


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
