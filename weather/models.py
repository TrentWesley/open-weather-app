from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, models, transaction

from weather.services.domain import Location

COORDINATE_PLACES = Decimal("0.0001")


class FavoriteLocation(models.Model):
    """FR-10: a location saved by one user, unique per user and rounded coordinates."""

    MAX_PER_USER = 20

    class AlreadySaved(Exception):
        """FR-10 AC-5: the user already saved these (rounded) coordinates."""

    class LimitReached(Exception):
        """FR-10 AC-6: the user already has MAX_PER_USER favorites."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    name = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=7, decimal_places=4)
    longitude = models.DecimalField(max_digits=8, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            # NFR-PERF-6: also the index used to look a favorite up by coordinates.
            models.UniqueConstraint(
                fields=["user", "latitude", "longitude"], name="unique_favorite_per_user"
            ),
        ]

    def __str__(self) -> str:
        return ", ".join(part for part in (self.name, self.state, self.country) if part)

    @staticmethod
    def round_coordinate(value: float | str | Decimal) -> Decimal:
        """Round to 4 decimal places (about 11 m), halves away from zero."""
        return Decimal(str(value)).quantize(COORDINATE_PLACES, rounding=ROUND_HALF_UP)

    @classmethod
    def add(cls, user, location: Location) -> "FavoriteLocation":
        """Save `location` for `user` atomically (NFR-REL-3).

        Raises AlreadySaved for a duplicate, checked before LimitReached.
        """
        latitude = cls.round_coordinate(location.latitude)
        longitude = cls.round_coordinate(location.longitude)
        try:
            with transaction.atomic():
                owned = cls.objects.filter(user=user)
                if owned.filter(latitude=latitude, longitude=longitude).exists():
                    raise cls.AlreadySaved
                if owned.count() >= cls.MAX_PER_USER:
                    raise cls.LimitReached
                return cls.objects.create(
                    user=user,
                    name=location.name,
                    state=location.state,
                    country=location.country,
                    latitude=latitude,
                    longitude=longitude,
                )
        except IntegrityError:
            # A concurrent request saved the same place between the check and the insert.
            raise cls.AlreadySaved from None

    def to_location(self) -> Location:
        """The saved place as the value object the weather services take."""
        return Location(
            self.name, self.state, self.country, float(self.latitude), float(self.longitude)
        )
