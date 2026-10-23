from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.db import transaction
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.cache import add_never_cache_headers, patch_cache_control
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.preferences import get_unit
from weather import maps
from weather.forms import CoordinatesForm, FavoriteForm, SearchForm
from weather.links import dashboard_url, map_url
from weather.models import FavoriteLocation
from weather.services.client import OpenWeatherClient
from weather.services.domain import Location, MapLayer
from weather.services.exceptions import (
    AuthenticationError,
    OpenWeatherError,
    RateLimitError,
)
from weather.services.search import LocationSearchService
from weather.services.weather import WeatherService

ALREADY_SAVED = "Already in favorites"
FAVORITE_INVALID = "That location couldn't be saved."
FAVORITES_LIMIT_REACHED = (
    f"Favorites limit reached. You can save up to {FavoriteLocation.MAX_PER_USER} locations; "
    "remove one to add another."
)
MAX_TILE_ZOOM = 18
TILE_BROWSER_CACHE_SECONDS = 600
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
    saved = saved_favorites(request)
    context["results"] = [
        {
            "location": location,
            "url": dashboard_url(location),
            "favorite": saved.get(coordinates_key(location.latitude, location.longitude)),
        }
        for location in locations
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
    context = {
        "location": location,
        "lat": lat,
        "lon": lon,
        "unit": unit,
        "favorite": favorite_at(request, lat, lon),
    }

    weather = None
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

    # FR-12: the map panel shows even if both sections failed (NFR-FT-3).
    selected = maps.selected_marker(location, weather, unit)
    context["map"] = maps.map_context(
        selected, maps.favorite_markers(request.user, unit, selected, fetch=False), unit
    )
    context["map_url"] = map_url(location)

    status = 503 if "current_error" in context and "forecast_error" in context else 200
    return render(request, "weather/dashboard.html", context, status=status)


@require_GET
def map_page(request: HttpRequest) -> HttpResponse:
    """FR-12: the full-page map, centered on ?lat=&lon= when given.

    Without coordinates it shows the user's favorites, or the whole world.
    """
    selected = None
    unit = get_unit(request)
    if "lat" in request.GET or "lon" in request.GET:
        form = CoordinatesForm(request.GET)
        if not form.is_valid():
            return render(request, "weather/invalid_location.html", status=400)
        location = place_for(form.cleaned_data["lat"], form.cleaned_data["lon"])
        try:
            weather = WeatherService().current(location, unit)
        except OpenWeatherError:
            weather = None
        selected = maps.selected_marker(location, weather, unit)
    favorites = maps.favorite_markers(request.user, unit, selected, fetch=True)
    context = {"map": maps.map_context(selected, favorites, unit), "unit": unit}
    return render(request, "weather/map.html", context)


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


@require_http_methods(["GET", "POST"])
def favorites(request: HttpRequest) -> HttpResponse:
    """GET lists the user's favorites (FR-10); POST adds one (FR-11)."""
    if request.method == "POST":
        return add_favorite(request)
    return favorites_list(request)


@login_required
def favorites_list(request: HttpRequest) -> HttpResponse:
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


def add_favorite(request: HttpRequest) -> HttpResponse:
    """FR-11 AC-3/4: save a place, answering fetch with JSON and forms with a redirect.

    fetch gets 201, 409 "Already in favorites" or 400 (sequence.mmd); a form
    POST returns to the page it came from with a message. Anonymous users are
    sent to log in and then back to that page.
    """
    as_json = wants_json(request)
    if not request.user.is_authenticated:
        return login_first(request, as_json)

    next_url = safe_next(request, reverse("favorites"))
    form = FavoriteForm(request.POST)
    if not form.is_valid():
        return favorite_outcome(request, as_json, next_url, 400, messages.ERROR, FAVORITE_INVALID)
    location = form.location()
    try:
        favorite = FavoriteLocation.add(request.user, location)
    except FavoriteLocation.AlreadySaved:
        favorite = favorite_at(request, location.latitude, location.longitude)
        return favorite_outcome(
            request, as_json, next_url, 409, messages.INFO, ALREADY_SAVED, favorite
        )
    except FavoriteLocation.LimitReached:
        return favorite_outcome(
            request, as_json, next_url, 400, messages.ERROR, FAVORITES_LIMIT_REACHED
        )
    saved = f"Saved {favorite} to favorites."
    return favorite_outcome(
        request, as_json, next_url, 201, messages.SUCCESS, saved, favorite
    )


@require_POST
def delete_favorite(request: HttpRequest, pk: int) -> HttpResponse:
    """FR-10 AC-4: remove one of the user's own favorites; anyone else's is a 404."""
    as_json = wants_json(request)
    if not request.user.is_authenticated:
        return login_first(request, as_json)
    favorite = get_object_or_404(FavoriteLocation, pk=pk, user=request.user)
    name = str(favorite)
    with transaction.atomic():
        favorite.delete()
    return favorite_outcome(
        request,
        as_json,
        safe_next(request, reverse("favorites")),
        200,
        messages.SUCCESS,
        f"Removed {name} from favorites.",
    )


def login_first(request: HttpRequest, as_json: bool) -> HttpResponse:
    """FR-11 AC-4: send an anonymous user to log in, then back to the page they were on."""
    login = redirect_to_login(safe_next(request, reverse("home")))
    if as_json:
        return JsonResponse(
            {"message": "Log in to save favorites.", "login_url": login.url}, status=401
        )
    return login


def favorite_outcome(
    request: HttpRequest,
    as_json: bool,
    next_url: str,
    status: int,
    level: int,
    message: str,
    favorite: FavoriteLocation | None = None,
) -> HttpResponse:
    """JSON (status, message, remove URL) for fetch; a flash message and redirect otherwise."""
    if as_json:
        data = {"message": message}
        if favorite is not None:
            data["delete_url"] = reverse("favorite_delete", args=[favorite.pk])
        return JsonResponse(data, status=status)
    messages.add_message(request, level, message)
    return redirect(next_url)


def saved_favorites(request: HttpRequest) -> dict[tuple, FavoriteLocation]:
    """The user's favorites keyed by rounded coordinates, in one query (NFR-PERF-6)."""
    if not request.user.is_authenticated:
        return {}
    owned = FavoriteLocation.objects.filter(user=request.user)
    return {(favorite.latitude, favorite.longitude): favorite for favorite in owned}


def favorite_at(request: HttpRequest, lat: float, lon: float) -> FavoriteLocation | None:
    """The user's favorite at these (rounded) coordinates, if they saved one."""
    if not request.user.is_authenticated:
        return None
    latitude, longitude = coordinates_key(lat, lon)
    return FavoriteLocation.objects.filter(
        user=request.user, latitude=latitude, longitude=longitude
    ).first()


def coordinates_key(lat: float, lon: float) -> tuple:
    """Match a place to a saved favorite the way FavoriteLocation stores it (FR-10 AC-5)."""
    return (FavoriteLocation.round_coordinate(lat), FavoriteLocation.round_coordinate(lon))


def wants_json(request: HttpRequest) -> bool:
    """True for favorites.js fetch requests, which ask for JSON explicitly."""
    return request.headers.get("Accept", "").startswith("application/json")


def safe_next(request: HttpRequest, default: str) -> str:
    """The POSTed `next` page if it is on this site (NFR-SEC-8), else `default`."""
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return default


@require_GET
def map_tile(request: HttpRequest, layer: str, z: int, x: int, y: int) -> HttpResponse:
    """FR-12 AC-6: proxy one OpenWeather overlay tile, adding the key server-side.

    The layer must be a MapLayer and z/x/y a real tile (NFR-SEC-5), so this can't
    be used to fetch arbitrary URLs. Tiles are cached briefly by the browser;
    failures are never cached, and Leaflet shows them as an unavailable overlay.
    """
    try:
        map_layer = MapLayer(layer)
    except ValueError:
        raise Http404("Unknown map layer.") from None
    if z > MAX_TILE_ZOOM or x >= 2**z or y >= 2**z:
        raise Http404("No such tile.")
    try:
        tile = OpenWeatherClient().map_tile(map_layer, z, x, y)
    except OpenWeatherError:
        response = HttpResponse(
            "Map overlay unavailable.", status=503, content_type="text/plain; charset=utf-8"
        )
        add_never_cache_headers(response)
        return response
    response = HttpResponse(tile, content_type="image/png")
    patch_cache_control(response, public=True, max_age=TILE_BROWSER_CACHE_SECONDS)
    return response


def place_for(lat: float, lon: float) -> Location:
    """Name the location by reverse geocoding, or by its coordinates if that fails.

    The place name is cosmetic, so a geocoding failure must not hide the weather
    (NFR-FT-3).
    """
    try:
        return LocationSearchService().reverse(lat, lon)
    except OpenWeatherError:
        return Location(f"{lat:.2f}, {lon:.2f}", "", "", lat, lon)


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
