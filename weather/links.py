"""URLs the weather pages link to, shared by the views and the map builder."""
from urllib.parse import urlencode

from django.urls import reverse

from weather.services.domain import Location


def coordinates_query(location: Location) -> str:
    """Coordinates to 4 decimal places (about 11 m), as a query string."""
    params = {"lat": f"{location.latitude:.4f}", "lon": f"{location.longitude:.4f}"}
    return urlencode(params)


def dashboard_url(location: Location) -> str:
    return f"{reverse('dashboard')}?{coordinates_query(location)}"


def map_url(location: Location) -> str:
    """FR-12: the full-page map centered on `location`."""
    return f"{reverse('map')}?{coordinates_query(location)}"


def tile_url_template() -> str:
    """The tile proxy URL with Leaflet's {layer}/{z}/{x}/{y} placeholders."""
    sample = reverse("map_tile", args=["layer", 1, 2, 3])
    return sample.replace("/layer/1/2/3/", "/{layer}/{z}/{x}/{y}/")
