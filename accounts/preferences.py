"""FR-3: the single place the rest of the code reads or changes the unit preference.

Logged-in users keep the unit in their UserProfile, created lazily here with
get_or_create. Anonymous visitors keep it in the session.
"""
from django.db import transaction
from django.http import HttpRequest

from accounts.models import TemperatureUnit, UserProfile

SESSION_KEY = "temperature_unit"
DEFAULT_UNIT = TemperatureUnit.IMPERIAL


def get_unit(request: HttpRequest) -> TemperatureUnit:
    """Return the request's unit preference, defaulting to imperial (FR-3 AC-4)."""
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        return TemperatureUnit(profile.temperature_unit)
    try:
        return TemperatureUnit(request.session.get(SESSION_KEY, DEFAULT_UNIT))
    except ValueError:
        return DEFAULT_UNIT


def set_unit(request: HttpRequest, unit: str) -> TemperatureUnit:
    """Store the unit for this user or session; raise ValueError if it is unknown."""
    unit = TemperatureUnit(unit)
    if request.user.is_authenticated:
        with transaction.atomic():
            UserProfile.objects.update_or_create(
                user=request.user, defaults={"temperature_unit": unit}
            )
    else:
        request.session[SESSION_KEY] = unit.value
    return unit
