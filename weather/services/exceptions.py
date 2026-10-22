"""Errors raised by OpenWeatherClient (NFR-FT-1, NFR-FT-4).

Messages are fixed strings written here, never text from a response or from
`requests`, so they can't carry the API key into logs or pages.
"""


class OpenWeatherError(Exception):
    """An OpenWeather request failed or returned data we can't use."""

    default_message = "OpenWeather request failed."

    def __init__(
        self, message: str = "", *, endpoint: str = "", status_code: int | None = None
    ) -> None:
        self.endpoint = endpoint
        self.status_code = status_code
        super().__init__(message or self.default_message)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}({str(self)!r}, endpoint={self.endpoint!r}, "
            f"status_code={self.status_code!r})"
        )


class RateLimitError(OpenWeatherError):
    """HTTP 429: the account's call limit was exceeded."""

    default_message = "OpenWeather rate limit exceeded."


class AuthenticationError(OpenWeatherError):
    """HTTP 401: the API key is missing, invalid, or not yet active."""

    default_message = "OpenWeather rejected the API key."


class ServiceUnavailableError(OpenWeatherError):
    """HTTP 5xx, a timeout, or a connection failure."""

    default_message = "OpenWeather is unavailable."
