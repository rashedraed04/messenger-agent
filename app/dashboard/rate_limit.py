"""
In-memory sliding-window rate limiter for auth endpoints.

Slows down password guessing and reset-email flooding. State is per process
(Cloud Run instance); Supabase Auth applies its own limits on top.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Allow at most `max_attempts` hits per key within `window_seconds`."""

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str) -> int:
        """Drop expired hits for key and return how many remain (caller holds the lock)."""
        hits = self._hits.get(key)
        if not hits:
            return 0
        now = time.monotonic()
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if not hits:
            del self._hits[key]
        return len(hits)

    def is_limited(self, key: str) -> bool:
        with self._lock:
            return self._recent(key) >= self.max_attempts

    def hit(self, key: str) -> None:
        with self._lock:
            self._recent(key)
            self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


# Failed logins per (email, client)
login_limiter = RateLimiter(max_attempts=10, window_seconds=15 * 60)
# Password-reset emails requested per email address
reset_email_limiter = RateLimiter(max_attempts=3, window_seconds=15 * 60)
# Wrong "current password" entries on the account page, per user
reauth_limiter = RateLimiter(max_attempts=5, window_seconds=15 * 60)
# Password-reset form submissions per client (guards the token endpoint)
reset_submit_limiter = RateLimiter(max_attempts=10, window_seconds=15 * 60)
# Bot simulator messages from the public demo account (protects the Gemini quota)
demo_chat_limiter = RateLimiter(max_attempts=30, window_seconds=60 * 60)
# Messenger messages per sender PSID (protects the Gemini quota from spam)
webhook_sender_limiter = RateLimiter(max_attempts=30, window_seconds=10 * 60)
