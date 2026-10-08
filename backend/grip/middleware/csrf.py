"""CSRF protection middleware (double-submit cookie pattern).

Generates a CSRF token per session and sets it as a readable cookie
(``grip_csrf``). State-changing requests (POST, PUT, PATCH, DELETE) must
include the token in an ``X-CSRF-Token`` header.
"""

from __future__ import annotations

import json
import secrets

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSRF_COOKIE_NAME = "grip_csrf"
_CSRF_HEADER = b"x-csrf-token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Paths exempt from CSRF checks (no session to protect yet).
_CSRF_EXEMPT_PREFIXES = (
    "/api/auth/callback",
    "/api/health/",
)


class CSRFMiddleware:
    """ASGI middleware that enforces CSRF tokens on state-changing requests."""

    def __init__(
        self,
        app: ASGIApp,
        cookie_domain: str = "",
        cookie_secure: bool = False,
    ) -> None:
        self.app = app
        self.cookie_domain = cookie_domain
        self.cookie_secure = cookie_secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        method: str = scope.get("method", "GET")

        if not path.startswith("/api/") or any(
            path.startswith(prefix) for prefix in _CSRF_EXEMPT_PREFIXES
        ):
            await self.app(scope, receive, send)
            return

        session: dict = scope.get("session", {})

        csrf_token = session.get("csrf_token")
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            session["csrf_token"] = csrf_token

        if method not in _SAFE_METHODS:
            raw_headers = dict(scope.get("headers", []))
            header_token = (
                raw_headers.get(_CSRF_HEADER, b"")
                .decode("utf-8", errors="ignore")
                .strip()
            )
            if not header_token or not secrets.compare_digest(header_token, csrf_token):
                body = json.dumps(
                    {"detail": "CSRF-token ontbreekt of is ongeldig"}
                ).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return

        async def send_with_csrf_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                resp_headers = MutableHeaders(scope=message)
                # No __Host- prefix and not HttpOnly: frontend and backend
                # are on sibling hostnames, and the frontend must read it.
                cookie_parts = [
                    f"{CSRF_COOKIE_NAME}={csrf_token}",
                    "Path=/",
                    "SameSite=Lax",
                ]
                if self.cookie_domain:
                    cookie_parts.append(f"Domain={self.cookie_domain}")
                if self.cookie_secure:
                    cookie_parts.append("Secure")
                resp_headers.append("set-cookie", "; ".join(cookie_parts))
            await send(message)

        await self.app(scope, receive, send_with_csrf_cookie)
