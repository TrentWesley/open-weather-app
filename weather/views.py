from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.preferences import get_unit
from weather.forms import CoordinatesForm, SearchForm
from weather.models import FavoriteLocation
from weather.services.domain import Location
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
)
from weather.services.search import LocationSearchService
from weather.services.weather import WeatherService

FORECAST_UNAVAILABLE = "The forecast isn't available right now. "
LOCATION_LOOKUP_FAILED = "We couldn't look up your location. "
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
    """FR-8/FR-9: current weather and forecast for a location in the user's unit (FR-3).

    Each section loads on its own, so one failing doesn't hide the other
    (NFR-FT-3). The page is a 503 only when neither can be shown.
    """
    form = CoordinatesForm(request.GET)
    if not form.is_valid():
        return render(request, "weather/invalid_location.html", status=400)
    lat, lon = form.cleaned_data["lat"], form.cleaned_data["lon"]
    unit = get_unit(request)
    location = place_for(lat, lon)
    service = WeatherService()
    context = {"location": location, "lat": lat, "lon": lon, "unit": unit}

    try:
        weather = service.current(location, unit)
        context.update(weather=weather, data_age=timezone.now() - weather.retrieved_at)
    except OpenWeatherError as error:
        context["current_error"] = service_error_message(error)

    try:
        forecast = service.forecast(location, unit)
        context.update(
            forecast=forecast,
            forecast_age=timezone.now() - forecast.retrieved_at,
            daily=forecast.daily_summaries(),
            chart_data=forecast.chart_data(unit),
        )
    except OpenWeatherError as error:
        context["forecast_error"] = FORECAST_UNAVAILABLE + service_error_message(error)

    status = 503 if "current_error" in context and "forecast_error" in context else 200
    return render(request, "weather/dashboard.html", context, status=status)


@require_GET
def reverse_geocode(request: HttpRequest) -> HttpResponse:
    """FR-7 AC-3: device coordinates -> place name -> the existing dashboard.

    The browser sends only coordinates to this endpoint; reverse geocoding (and
    the API key) stay on the server.
    """
    form = CoordinatesForm(request.GET)
    if not form.is_valid():
        return render(request, "weather/invalid_location.html", status=400)
    try:
        location = LocationSearchService().reverse(
            form.cleaned_data["lat"], form.cleaned_data["lon"]
        )
    except OpenWeatherError as error:
        context = {
            "form": SearchForm(),
            "error_message": LOCATION_LOOKUP_FAILED + service_error_message(error),
        }
        return render(request, "weather/search.html", context, status=503)
    return redirect(dashboard_url(location))


@login_required
@require_GET
def favorites(request: HttpRequest) -> HttpResponse:
    """FR-10 AC-2/3/7: the user's own favorites, each with its current weather.

    One query loads the favorites (NFR-PERF-6); weather comes from the cache
    where possible (NFR-PERF-4).
    """
    saved = list(FavoriteLocation.objects.filter(user=request.user))
    unit = get_unit(request)
    locations = [favorite.to_location() for favorite in saved]
    weather = WeatherService().current_many(locations, unit)
    context = {
        "favorites": [
            {"favorite": favorite, "weather": current, "url": dashboard_url(location)}
            for favorite, location, current in zip(saved, locations, weather)
        ],
        "unit": unit,
        "max_favorites": FavoriteLocation.MAX_PER_USER,
    }
    return render(request, "weather/favorites.html", context)


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
