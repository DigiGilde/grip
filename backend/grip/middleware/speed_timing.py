"""What a request cost the database, as a ``Server-Timing`` header.

Development only (``DEV_SPEED_TIMING=1`` next to ``DEV_NO_AUTH=1``): the
tool ``just check-speed`` reads the header to say how many statements a
request ran and how long the database and the whole request took. A deployed
instance never adds it: the header would tell a visitor how the server works.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass
class _Cost:
    statements: int = 0
    seconds: float = 0.0
    started: float = 0.0


_cost: ContextVar[_Cost | None] = ContextVar("speed_timing_cost", default=None)


def _before(*_: Any) -> None:
    cost = _cost.get()
    if cost is not None:
        cost.started = time.perf_counter()


def _after(*_: Any) -> None:
    cost = _cost.get()
    if cost is not None:
        cost.statements += 1
        cost.seconds += time.perf_counter() - cost.started


def watch(engine: Engine) -> None:
    """Count the statements of ``engine`` for the request they belong to."""
    event.listen(engine, "before_cursor_execute", _before)
    event.listen(engine, "after_cursor_execute", _after)


class SpeedTimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cost = _Cost()
        token = _cost.set(cost)
        started = time.perf_counter()

        async def send_timed(message: Message) -> None:
            if message["type"] == "http.response.start":
                total = (time.perf_counter() - started) * 1000
                value = (
                    f'sql;dur={cost.seconds * 1000:.1f};desc="{cost.statements}", '
                    f"app;dur={total:.1f}"
                )
                message.setdefault("headers", []).append(
                    (b"server-timing", value.encode("latin-1"))
                )
            await send(message)

        try:
            await self.app(scope, receive, send_timed)
        finally:
            _cost.reset(token)
