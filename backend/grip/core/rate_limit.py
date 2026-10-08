"""A small in-memory rate limit for routes that need no session.

Per process and per client address: enough to slow down someone hammering
the login round trip. It does not replace a limit at the edge.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    """At most ``limit`` calls per client address in ``window`` seconds."""

    def __init__(self, *, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def check(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        calls = self._calls[key]
        while calls and now - calls[0] > self.window:
            calls.popleft()
        if len(calls) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Te veel pogingen. Probeer het over een minuut opnieuw.",
            )
        calls.append(now)

    def reset(self) -> None:
        self._calls.clear()
