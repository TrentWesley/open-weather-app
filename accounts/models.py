from django.conf import settings
from django.db import models


class TemperatureUnit(models.TextChoices):
    """FR-3: the two supported units; values match OpenWeather's `units` parameter."""

    IMPERIAL = "imperial", "Fahrenheit (°F)"
    METRIC = "metric", "Celsius (°C)"


class UserProfile(models.Model):
    """FR-3 AC-2: per-user settings, one-to-one with the auth user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    temperature_unit = models.CharField(
        max_length=8, choices=TemperatureUnit.choices, default=TemperatureUnit.IMPERIAL
    )

    def __str__(self) -> str:
        return f"Profile for {self.user}"

    def units_param(self) -> str:
        """Return the value to send as OpenWeather's `units` query parameter."""
        return TemperatureUnit(self.temperature_unit).value
