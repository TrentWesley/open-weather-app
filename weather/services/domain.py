"""Plain value objects returned by the weather services (see docs/diagrams/class.mmd)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    """A place resolved to a name, region, country and coordinates."""

    name: str
    state: str
    country: str
    latitude: float
    longitude: float
