"""Small in-memory rate limits.

Per process: enough to slow down someone hammering the login round trip, a
costly document or the language model. It does not replace a limit at the
edge, and with several replicas each one counts for itself.
"""

from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException, Request, status

# Past this many keys the oldest are dropped: a caller that keeps changing
# its address must not make the table grow without end.
_MAX_KEYS = 20_000


class KeyedLimiter:
    """At most ``limit`` calls per key in ``window`` seconds."""

    def __init__(self, *, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._calls: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """Count a call for ``key``; False when the key is over its limit."""
        now = time.monotonic()
        calls = self._calls.get(key)
        if calls is None:
            if len(self._calls) >= _MAX_KEYS:
                self._prune(now)
            calls = self._calls[key] = deque()
        while calls and now - calls[0] > self.window:
            calls.popleft()
        if len(calls) >= self.limit:
            return False
        calls.append(now)
        return True

    def _prune(self, now: float) -> None:
        idle = [
            key
            for key, calls in self._calls.items()
            if not calls or now - calls[-1] > self.window
        ]
        for key in idle:
            del self._calls[key]
        # Still full of active keys: let go of the oldest half.
        if len(self._calls) >= _MAX_KEYS:
            for key in list(self._calls)[: _MAX_KEYS // 2]:
                del self._calls[key]

    def reset(self) -> None:
        self._calls.clear()


class RateLimiter(KeyedLimiter):
    """A limit per client address, for routes that need no session.

    The address is the one ``TrustedProxyMiddleware`` settled on: behind a
    proxy that is not on ``TRUSTED_PROXIES`` every caller has the proxy's
    address and shares one limit.
    """

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        if not self.allow(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Te veel pogingen. Probeer het over een minuut opnieuw.",
            )


class PersonLimiter(KeyedLimiter):
    """A limit per person, for something costly a logged-in person asks for."""

    def __init__(self, *, limit: int, window: float, detail: str) -> None:
        super().__init__(limit=limit, window=window)
        self.detail = detail

    def check(self, key: object) -> None:
        if not self.allow(str(key)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=self.detail
            )


def caller_key() -> str:
    """Who makes this request, for a limit per person.

    A visitor of an example instance is counted by their own login, not by
    the example person they share with every other visitor.
    """
    from grip.events import context as event_context

    current = event_context.current()
    return str(current.via or current.actor_person_id or current.actor_ref or "-")
