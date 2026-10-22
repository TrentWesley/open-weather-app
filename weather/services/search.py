"""LocationSearchService: city and postal-code geocoding (FR-4, FR-5, FR-6) and
reverse geocoding for device location (FR-7)."""
import dataclasses
import hashlib
import re

from weather.services.cache import WeatherCache
from weather.services.client import (
    GEOCODE_DIRECT,
    GEOCODE_REVERSE,
    GEOCODE_ZIP,
    OpenWeatherClient,
)
from weather.services.domain import Location
from weather.services.exceptions import OpenWeatherError
from weather.services.validation import check_coordinates, malformed, require, require_number

MAX_QUERY_LENGTH = 100
MAX_RESULTS = 5
DEFAULT_COUNTRY = "US"
# OpenWeather answers an unknown or badly formed postal code with 404 or 400.
POSTAL_NOT_FOUND_STATUSES = {400, 404}

# USPS codes for the 50 states and DC; OpenWeather accepts these with country US.
US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE "
    "NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
# State codes that are also ISO 3166-1 country codes (CA = Canada, DE = Germany, ...).
STATE_CODES_THAT_ARE_COUNTRIES = frozenset(
    "AL AR AZ CA CO DE GA ID IL IN KY LA MA MD ME MN MO MS MT NC NE PA SC SD TN VA".split()
)

_COUNTRY_CODE = re.compile(r"[A-Za-z]{2}")
_POSTAL_CHARS = re.compile(r"[A-Za-z0-9 -]{2,10}")
_US_ZIP_PLUS_FOUR = re.compile(r"(\d{5})-\d{4}")


class LocationSearchService:
    """Turn a typed query or coordinates into Location objects, cached for 24 hours."""

    def __init__(
        self, client: OpenWeatherClient | None = None, cache: WeatherCache | None = None
    ) -> None:
        self._client = client or OpenWeatherClient()
        self._cache = cache or WeatherCache()

    def search(self, query: str) -> list[Location]:
        """Return up to five matches in API order, or [] when nothing matches.

        Raises ValueError for an empty or overlong query, before any API call, and
        OpenWeatherError when OpenWeather fails.
        """
        query = query.strip()
        if not query:
            raise ValueError("Enter a city name or postal code.")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError(f"Search text must be {MAX_QUERY_LENGTH} characters or fewer.")
        postal = _split_postal_code(query)
        if postal:
            return self._search_postal_code(*postal)
        return self._search_city(query)

    def reverse(self, lat: float, lon: float) -> Location:
        """Name the place at the given coordinates (FR-7 AC-3).

        The result keeps the caller's coordinates; only the name, state and country
        come from OpenWeather. Unnamed places such as open water are named by their
        coordinates.
        """
        check_coordinates(lat, lon)
        key = WeatherCache.make_key("reverse", lat, lon, "none")
        place = self._cache.get(key)
        if place is None:
            matches = self._client.reverse_geocode(lat, lon)
            if matches:
                place = _parse_location(matches[0], GEOCODE_REVERSE)
            else:
                place = Location(f"{lat:.2f}, {lon:.2f}", "", "", lat, lon)
            self._cache.set(key, place, self._cache.GEOCODE_TTL)
        return dataclasses.replace(place, latitude=lat, longitude=lon)

    def is_postal_code(self, query: str) -> bool:
        """True if search() would treat the query as a postal code (FR-5 AC-2).

        Lets callers say "Postal code not found" rather than "No locations found".
        """
        return _split_postal_code(query.strip()) is not None

    def _search_city(self, query: str) -> list[Location]:
        api_queries = _direct_queries(query)
        key = _geocode_key("direct", "|".join(api_queries), "")
        locations = self._cache.get(key)
        if locations is None:
            locations = []
            for api_query in api_queries:
                for match in self._client.geocode_direct(api_query, limit=MAX_RESULTS):
                    location = _parse_location(match, GEOCODE_DIRECT)
                    if location not in locations:
                        locations.append(location)
            locations = locations[:MAX_RESULTS]
            self._cache.set(key, locations, self._cache.GEOCODE_TTL)
        return locations

    def _search_postal_code(self, code: str, country: str) -> list[Location]:
        key = _geocode_key("zip", code, country)
        locations = self._cache.get(key)
        if locations is None:
            try:
                match = self._client.geocode_zip(code, country)
            except OpenWeatherError as error:
                if error.status_code in POSTAL_NOT_FOUND_STATUSES:
                    return []
                raise
            locations = [_parse_location(match, GEOCODE_ZIP)]
            self._cache.set(key, locations, self._cache.GEOCODE_TTL)
        return locations


def _direct_queries(query: str) -> list[str]:
    """Return the `q` value(s) to send to direct geocoding for a city query.

    OpenWeather expects "city", "city,country" or "city,state,US"; a state code is
    only honoured together with country US. So "Amarillo, TX" becomes
    "Amarillo,TX,US". A code that is both a state and a country ("London, CA")
    is searched both ways, the US reading first. Spacing around commas is
    dropped and two-letter codes are upper-cased.
    """
    parts = [part.strip() for part in query.split(",") if part.strip()]
    parts = [parts[0]] + [p.upper() if _COUNTRY_CODE.fullmatch(p) else p for p in parts[1:]]
    if len(parts) == 2 and parts[1] in US_STATE_CODES:
        city, code = parts
        state_query = f"{city},{code},US"
        if code in STATE_CODES_THAT_ARE_COUNTRIES:
            return [state_query, f"{city},{code}"]
        return [state_query]
    return [",".join(parts)]


def _split_postal_code(query: str) -> tuple[str, str] | None:
    """Return (code, country) if the query looks like a postal code, else None.

    Accepts "CODE" or "CODE, CC". Every word of the code must contain a digit, so
    "SW1A 1AA" and "79015" match while "Paris, FR" and "Route 66" do not.
    """
    code, country = query, DEFAULT_COUNTRY
    if "," in query:
        code, country = (part.strip() for part in query.rsplit(",", 1))
        if not _COUNTRY_CODE.fullmatch(country):
            return None
    if not _POSTAL_CHARS.fullmatch(code):
        return None
    if not all(any(char.isdigit() for char in word) for word in code.split()):
        return None
    code, country = code.upper(), country.upper()
    zip_plus_four = _US_ZIP_PLUS_FOUR.fullmatch(code)
    if country == "US" and zip_plus_four:
        code = zip_plus_four.group(1)
    return code, country


def _geocode_key(kind: str, query: str, country: str) -> str:
    """Key on the normalized query plus country, hashed so any text is key-safe."""
    normalized = f"{query.strip().lower()}|{country.upper()}"
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"weather:geocode:{kind}:{digest}"


def _parse_location(data: dict, endpoint: str) -> Location:
    name = require(data, "name", str, endpoint).strip()
    if not name:
        raise malformed(endpoint, "empty name")
    lat = require_number(data, "lat", endpoint)
    lon = require_number(data, "lon", endpoint)
    try:
        check_coordinates(lat, lon)
    except ValueError:
        raise malformed(endpoint, "coordinates out of range") from None
    state = data.get("state")
    country = data.get("country")
    return Location(
        name=name,
        state=state if isinstance(state, str) else "",
        country=country if isinstance(country, str) else "",
        latitude=lat,
        longitude=lon,
    )
