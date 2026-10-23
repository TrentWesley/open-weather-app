from django import forms

from accounts.forms import AccessibleErrorsMixin
from weather.services.domain import Location
from weather.services.search import MAX_QUERY_LENGTH


class SearchForm(AccessibleErrorsMixin, forms.Form):
    """FR-4/FR-5: one box for a city name or a postal code."""

    q = forms.CharField(
        label="City or postal code",
        max_length=MAX_QUERY_LENGTH,
        error_messages={
            "required": "Enter a city name or postal code.",
            "max_length": f"Search text must be {MAX_QUERY_LENGTH} characters or fewer.",
        },
        widget=forms.TextInput(
            attrs={"type": "search", "placeholder": "e.g. Amarillo, TX or 79015"}
        ),
    )


class CoordinatesForm(forms.Form):
    """NFR-SEC-5: finite latitude in [-90, 90] and longitude in [-180, 180]."""

    lat = forms.FloatField(min_value=-90, max_value=90)
    lon = forms.FloatField(min_value=-180, max_value=180)


class FavoriteForm(CoordinatesForm):
    """FR-11: the place a "Save to favorites" button submits (NFR-SEC-5)."""

    name = forms.CharField(max_length=100)
    state = forms.CharField(max_length=100, required=False)
    country = forms.CharField(max_length=100, required=False)

    def location(self) -> Location:
        data = self.cleaned_data
        return Location(data["name"], data["state"], data["country"], data["lat"], data["lon"])
