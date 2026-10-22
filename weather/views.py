from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.preferences import get_unit
from weather.forms import CoordinatesForm, SearchForm
from weather.services.domain import Location
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
)
from weather.services.search import LocationSearchService
from weather.services.weather import WeatherService

NO_LOCATIONS = ("No locations found.", "Please check the spelling or try a postal code.")
NO_POSTAL_CODE = (
    "Postal code not found.",
    "Check the code and add a country if it isn't in the US, for example SW1A 1AA, GB.",
)


def home(request: HttpRequest) -> HttpResponse:
    """Home page with the location search box (FR-4 AC-1)."""
    return render(request, "weather/home.html", {"form": SearchForm()})


@require_GET
def search(request: HttpRequest) -> HttpResponse:
    """FR-4/5/6: geocode a query, then redirect, list matches, or explain why not."""
    if "q" not in request.GET:
        return render(request, "weather/search.html", {"form": SearchForm()})
    form = SearchForm(request.GET)
    if not form.is_valid():
        return render(request, "weather/search.html", {"form": form}, status=400)

    query = form.cleaned_data["q"]
    service = LocationSearchService()
    context = {"form": form, "query": query}
    try:
        locations = service.search(query)
    except OpenWeatherError as error:
        context["error_message"] = service_error_message(error)
        return render(request, "weather/search.html", context, status=503)

    if len(locations) == 1:
        return redirect(dashboard_url(locations[0]))
    if not locations:
        context["no_results"] = NO_POSTAL_CODE if service.is_postal_code(query) else NO_LOCATIONS
    context["results"] = [
        {"location": location, "url": dashboard_url(location)} for location in locations
    ]
    return render(request, "weather/search.html", context)


@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    """FR-8: current weather for a location, in the user's unit (FR-3)."""
    form = CoordinatesForm(request.GET)
    if not form.is_valid():
        return render(request, "weather/invalid_location.html", status=400)
    lat, lon = form.cleaned_data["lat"], form.cleaned_data["lon"]
    unit = get_unit(request)
    location = place_for(lat, lon)
    context = {"location": location, "lat": lat, "lon": lon, "unit": unit}
    try:
        weather = WeatherService().current(location, unit)
    except OpenWeatherError as error:
        context["error_message"] = service_error_message(error)
        return render(request, "weather/dashboard.html", context, status=503)
    context["weather"] = weather
    context["data_age"] = timezone.now() - weather.retrieved_at
    return render(request, "weather/dashboard.html", context)


def place_for(lat: float, lon: float) -> Location:
    """Name the location by reverse geocoding, or by its coordinates if that fails.

    The place name is cosmetic, so a geocoding failure must not hide the weather
    (NFR-FT-3).
    """
    try:
        return LocationSearchService().reverse(lat, lon)
    except OpenWeatherError:
        return Location(f"{lat:.2f}, {lon:.2f}", "", "", lat, lon)


def dashboard_url(location: Location) -> str:
    """Dashboard link with coordinates to 4 decimal places (about 11 m)."""
    params = {"lat": f"{location.latitude:.4f}", "lon": f"{location.longitude:.4f}"}
    return f"{reverse('dashboard')}?{urlencode(params)}"


def service_error_message(error: OpenWeatherError) -> str:
    """NFR-FT-1/4: a friendly message, distinct for rate limiting and key problems."""
    if isinstance(error, RateLimitError):
        return (
            "The weather service has received too many requests. "
            "Please try again in a minute."
        )
    if isinstance(error, AuthenticationError):
        return (
            "The weather service is not configured correctly, so it can't be used right now. "
            "Please try again later."
        )
    return "We couldn't reach the weather service. Please try again in a moment."
