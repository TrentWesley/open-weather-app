"""NFR-SEC-7: cache-backed counters that throttle failed logins per IP and per username."""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class LoginRateLimiter:
    """Block logins after too many failures from one IP or against one username.

    Each counter starts its window at the first failure and expires with it, so a
    block lifts `window` seconds after the first failure in the run.
    """

    def __init__(self) -> None:
        config = settings.LOGIN_RATE_LIMIT
        self.max_failures: int = config["max_failures"]
        self.window: int = config["window"]

    def ip_key(self, ip: str) -> str:
        return f"login-failures:ip:{ip}"

    def username_key(self, username: str) -> str:
        # Hashed so usernames never appear in cache keys and any input is key-safe.
        normalized = username.strip().lower().encode()
        return f"login-failures:user:{hashlib.sha256(normalized).hexdigest()}"

    def is_blocked(self, ip: str, username: str) -> bool:
        counts = cache.get_many([self.ip_key(ip), self.username_key(username)])
        return any(count >= self.max_failures for count in counts.values())

    def record_failure(self, ip: str, username: str) -> None:
        for key in (self.ip_key(ip), self.username_key(username)):
            cache.add(key, 0, timeout=self.window)
            try:
                cache.incr(key)
            except ValueError:  # Expired between add() and incr().
                cache.set(key, 1, timeout=self.window)
        if self.is_blocked(ip, username):
            logger.warning("Login rate limit reached for a client or account.")

    def reset(self, username: str) -> None:
        """Clear the username counter after a successful login.

        The IP counter is kept, so logging in to one account can't reset the limit
        on guessing other accounts from the same address.
        """
        cache.delete(self.username_key(username))
