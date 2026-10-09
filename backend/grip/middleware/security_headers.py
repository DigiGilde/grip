"""Middleware that adds standard security headers to all responses."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# What a response of the API may load or be loaded into: nothing. The API
# answers with data and files, never with a page that runs something. The
# two routes that do answer with a page (a proof statement, a report to
# print) set their own, equally closed policy and keep it.
API_CONTENT_SECURITY_POLICY = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


class SecurityHeadersMiddleware:
    """Add security headers to every HTTP response.

    Headers set:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: (restrictive defaults)
    - Content-Security-Policy: closed, unless the route set one. Not on a
      PDF (the browser's viewer shows it) and not on the interactive API
      documentation of local development (a page with scripts, which a
      deployed instance does not serve)
    - Cache-Control: private, no-store, unless the route chose otherwise:
      what the API answers is about people and money and belongs in no
      cache between the server and the person

    Strict-Transport-Security is intentionally omitted here because the
    reverse proxy (nginx / ZAD ingress) should own that header.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                headers["Permissions-Policy"] = (
                    "camera=(), microphone=(), geolocation=()"
                )
                # A PDF is shown by the browser's own viewer, which some
                # browsers build from parts a closed policy would block.
                shown_by_browser = headers.get("content-type", "").startswith(
                    ("text/html", "application/pdf")
                )
                if "content-security-policy" not in headers and not shown_by_browser:
                    headers["Content-Security-Policy"] = API_CONTENT_SECURITY_POLICY
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "private, no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)
