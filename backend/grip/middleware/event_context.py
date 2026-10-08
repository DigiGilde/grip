"""One correlation id per request, for the events it causes.

Everything a request writes to the event stream shares one correlation id.
A caller that sends a W3C ``traceparent`` header keeps its trace id, so a
chain of calls across systems can be followed (Logboek Dataverwerkingen).
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from grip.events import context


class EventContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        traceparent = None
        for name, value in scope.get("headers", []):
            if name == b"traceparent":
                traceparent = value.decode("latin-1")
                break
        correlation_id = context.correlation_from_traceparent(traceparent)
        # A fresh context per request: nothing of an earlier request stays.
        with context.scope(correlation_id=correlation_id):
            await self.app(scope, receive, send)
