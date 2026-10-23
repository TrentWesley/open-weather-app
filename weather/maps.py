"""FR-12: what the Leaflet map shows, as JSON-safe data for json_script.

The map page and the dashboard panel share this. Tiles always come from our own
proxy (AC-6); the base map is OpenStreetMap, which needs no key.
"""
from dataclasses import asdict, dataclass

from accounts.models import TemperatureUnit
from weather import formatting
from weather.links import dashboard_url, tile_url_template
from weather.models import FavoriteLocation
from weather.services.domain import CurrentWeather, Location, MapLayer
from weather.services.weather import WeatherService
from weather.templatetags.weather_format import place_name

BASE_MAP = {
    "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "attribution": (
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        'contributors · Weather layers &copy; <a href="https://openweathermap.org/">OpenWeather</a>'
    ),
    "maxZoom": 18,
}
LOCATION_ZOOM = 8
DEFAULT_LAYER = MapLayer.TEMPERATURE


@dataclass(frozen=True)
class MapMarker:
    """One marker: the selected location or a favorite (FR-12 AC-1/5)."""

    kind: str
    name: str
    lat: float
    lon: float
    weather: str | None
    url: str


def weather_summary(weather: CurrentWeather | None, unit: TemperatureUnit | str) -> str | None:
    """e.g. "68°F, Light rain"; None when the weather isn't available."""
    if weather is None:
        return None
    description = weather.description[:1].upper() + weather.description[1:]
    return f"{formatting.format_temperature(weather.temperature, unit)}, {description}"


def selected_marker(
    location: Location, weather: CurrentWeather | None, unit: TemperatureUnit | str
) -> MapMarker:
    return MapMarker(
        "selected",
        place_name(location),
        location.latitude,
        location.longitude,
        weather_summary(weather, unit),
        dashboard_url(location),
    )


def favorite_markers(
    user, unit: TemperatureUnit | str, selected: MapMarker | None, fetch: bool
) -> list[MapMarker]:
    """FR-12 AC-5: the user's favorites, loaded in one query (NFR-PERF-6).

    With `fetch`, missing weather is fetched (the map page, NFR-PERF-4); otherwise
    only cached weather is used, so the dashboard keeps to one call per endpoint
    (NFR-PERF-3). A favorite at the selected location isn't drawn twice.
    """
    if not user.is_authenticated:
        return []
    skip = None
    if selected is not None:
        skip = (
            FavoriteLocation.round_coordinate(selected.lat),
            FavoriteLocation.round_coordinate(selected.lon),
        )
    saved = [
        favorite
        for favorite in FavoriteLocation.objects.filter(user=user)
        if (favorite.latitude, favorite.longitude) != skip
    ]
    locations = [favorite.to_location() for favorite in saved]
    service = WeatherService()
    if fetch:
        weather = service.current_many(locations, unit)
    else:
        weather = [service.cached_current(location, unit) for location in locations]
    return [
        MapMarker(
            "favorite",
            str(favorite),
            location.latitude,
            location.longitude,
            weather_summary(current, unit),
            dashboard_url(location),
        )
        for favorite, location, current in zip(saved, locations, weather)
    ]


def map_context(
    selected: MapMarker | None, favorites: list[MapMarker], unit: TemperatureUnit | str
) -> dict:
    """Template context for weather/includes/map_panel.html."""
    markers = ([selected] if selected else []) + favorites
    config = {
        "center": [selected.lat, selected.lon] if selected else None,
        "zoom": LOCATION_ZOOM,
        "base": BASE_MAP,
        "tileUrl": tile_url_template(),
        "defaultLayer": DEFAULT_LAYER.value,
        "markers": [asdict(marker) for marker in markers],
    }
    legends = [
        {"layer": layer, "stops": layer.legend(unit), "default": layer is DEFAULT_LAYER}
        for layer in MapLayer
    ]
    return {"config": config, "legends": legends, "selected": selected, "favorites": favorites}
