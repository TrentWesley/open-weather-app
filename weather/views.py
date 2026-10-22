from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from weather.forms import CoordinatesForm, SearchForm
from weather.services.domain import Location
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
)
from weather.services.search import LocationSearchService

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
        context["error_message"] = search_error_message(error)
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
    """Landing page for a chosen location. The full dashboard is built in Phase 4."""
    form = CoordinatesForm(request.GET)
    if not form.is_valid():
        return render(request, "weather/invalid_location.html", status=400)
    return render(request, "weather/dashboard.html", form.cleaned_data)


def dashboard_url(location: Location) -> str:
    """Dashboard link with coordinates to 4 decimal places (about 11 m)."""
    params = {"lat": f"{location.latitude:.4f}", "lon": f"{location.longitude:.4f}"}
    return f"{reverse('dashboard')}?{urlencode(params)}"


def search_error_message(error: OpenWeatherError) -> str:
    """NFR-FT-1/4: a friendly message, distinct for rate limiting and key problems."""
    if isinstance(error, RateLimitError):
        return (
            "The weather service has received too many requests. "
            "Please try again in a minute."
        )
    if isinstance(error, AuthenticationError):
        return (
            "Location search is not configured correctly, so it can't run right now. "
            "Please try again later."
        )
    return "We couldn't reach the weather service. Please try again in a moment."
