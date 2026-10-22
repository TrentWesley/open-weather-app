"""Helpers for reading settings from environment variables (NFR-SEC-1, NFR-SEC-6)."""
import os

from django.core.exceptions import ImproperlyConfigured

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}


def env_required(name: str) -> str:
    """Return a required variable, failing with its name (never its value) if missing."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"Set the {name} environment variable (see .env.example)."
        )
    return value


def env_bool(name: str, default: bool) -> bool:
    """Parse a boolean variable such as 'true', '0' or 'off'."""
    if name not in os.environ:
        return default
    value = os.environ[name].strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ImproperlyConfigured(f"{name} must be true or false.")


def env_list(name: str, default: list[str]) -> list[str]:
    """Parse a comma-separated variable, ignoring blank entries."""
    if name not in os.environ:
        return list(default)
    return [item.strip() for item in os.environ[name].split(",") if item.strip()]
