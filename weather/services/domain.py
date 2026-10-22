"""Plain value objects returned by the weather services (see docs/diagrams/class.mmd)."""
import math
from dataclasses import dataclass
from datetime import date, datetime
from itertools import groupby

from weather import formatting

COMPASS_POINTS = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)
MAX_FORECAST_DAYS = 6
MIDDAY_MINUTES = 12 * 60
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
class DailySummary:
    """FR-9 AC-2: one calendar day of the forecast in the location's local time."""

    date: date
    high: float
    low: float
    icon: str
    description: str
    max_pop: float


@dataclass(frozen=True)
class Forecast:
    """FR-9: 3-hour forecast entries for a location, in the location's time zone."""

    location: Location
    entries: tuple[ForecastEntry, ...]
    retrieved_at: datetime
    is_stale: bool = False

    def daily_summaries(self) -> list[DailySummary]:
        """Group entries by local calendar day (up to six days, partial days included).

        The day's condition is the one nearest midday, so a rainy night doesn't
        label a sunny day.
        """
        summaries = []
        for day, group in groupby(self.entries, key=lambda e: e.timestamp.date()):
            entries = list(group)
            midday = min(entries, key=_minutes_from_midday)
            summaries.append(
                DailySummary(
                    date=day,
                    high=max(e.temperature for e in entries),
                    low=min(e.temperature for e in entries),
                    icon=midday.icon,
                    description=midday.description,
                    max_pop=max(e.pop for e in entries),
                )
            )
        return summaries[:MAX_FORECAST_DAYS]

    def chart_data(self, unit: str) -> dict:
        """JSON-ready series for the temperature and precipitation charts (FR-9 AC-3..6).

        Labels are local times; temperatures are already in `unit` (OpenWeather
        was asked for it); precipitation is converted to mm or inches to match.
        Embed with `json_script`, never by string concatenation.
        """
        labels = [formatting.format_hour(e.timestamp) for e in self.entries]
        temperatures = [e.temperature for e in self.entries]
        wettest = max(range(len(self.entries)), key=lambda i: self.entries[i].pop)
        summary = (
            f"Temperatures range from {formatting.format_temperature(min(temperatures), unit)} "
            f"to {formatting.format_temperature(max(temperatures), unit)} "
            f"between {labels[0]} and {labels[-1]}. "
            f"Highest chance of precipitation: "
            f"{formatting.format_percent(self.entries[wettest].pop)} at {labels[wettest]}."
        )
        return {
            "labels": labels,
            "temperature": [formatting.round_half_up(t, 1) for t in temperatures],
            "pop": [int(formatting.round_half_up(e.pop * 100)) for e in self.entries],
            "precipitation": [
                formatting.precipitation_in_unit(e.precipitation_mm, unit) for e in self.entries
            ],
            "temperature_unit": formatting.temperature_symbol(unit),
            "precipitation_unit": formatting.precipitation_unit(unit),
            "summary": summary,
        }


def _minutes_from_midday(entry: ForecastEntry) -> int:
    return abs(entry.timestamp.hour * 60 + entry.timestamp.minute - MIDDAY_MINUTES)
