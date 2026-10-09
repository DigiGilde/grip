"""The version a save started from, for the length of the request.

A form sends ``If-Match: "<id>:<version>"`` with a save. The service that
changes the record compares it (``grip.services.stale``).
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from grip.services import stale


class ExpectedVersionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = None
        for name, value in scope.get("headers", []):
            if name == b"if-match":
                raw = value.decode("latin-1")
                break
        with stale.expecting(raw):
            await self.app(scope, receive, send)
