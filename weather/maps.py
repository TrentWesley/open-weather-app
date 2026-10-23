"""FR-12: what the Leaflet map shows, as JSON-safe data for json_script.

The map page and the dashboard panel share this. Tiles always come from our own
proxy (AC-6); the base map comes from settings (OpenStreetMap by default) and
needs no key.
"""
from dataclasses import asdict, dataclass

from django.conf import settings

from accounts.models import TemperatureUnit
from weather import formatting
from weather.links import dashboard_url, tile_url_template
from weather.models import FavoriteLocation
from weather.services.domain import CurrentWeather, Location, MapLayer
from weather.services.weather import WeatherService
from weather.templatetags.weather_format import place_name

OPENWEATHER_ATTRIBUTION = (
    'Weather layers &copy; <a href="https://openweathermap.org/">OpenWeather</a>'
)
# Tile servers such as OpenStreetMap's block requests without a Referer, and the
# site-wide Referrer-Policy (same-origin) sends none cross-origin. The base layer
# alone sends the site's origin: never the page path, which contains coordinates.
BASE_MAP_REFERRER_POLICY = "strict-origin-when-cross-origin"
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


def base_map() -> dict:
    """The base layer from settings, so the provider can change without a code change."""
    return {
        "url": settings.MAP_BASE_TILE_URL,
        "attribution": f"{settings.MAP_BASE_ATTRIBUTION} · {OPENWEATHER_ATTRIBUTION}",
        "maxZoom": settings.MAP_BASE_MAX_ZOOM,
        "referrerPolicy": BASE_MAP_REFERRER_POLICY,
    }


def map_context(
    selected: MapMarker | None, favorites: list[MapMarker], unit: TemperatureUnit | str
) -> dict:
    """Template context for weather/includes/map_panel.html."""
    markers = ([selected] if selected else []) + favorites
    config = {
        "center": [selected.lat, selected.lon] if selected else None,
        "zoom": LOCATION_ZOOM,
        "base": base_map(),
        "tileUrl": tile_url_template(),
        "defaultLayer": DEFAULT_LAYER.value,
        "markers": [asdict(marker) for marker in markers],
    }
    legends = [
        {"layer": layer, "stops": layer.legend(unit), "default": layer is DEFAULT_LAYER}
        for layer in MapLayer
    ]
    return {"config": config, "legends": legends, "selected": selected, "favorites": favorites}
