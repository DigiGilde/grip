"""Global authentication middleware.

When OIDC is configured, this middleware rejects unauthenticated requests to
``/api/`` routes with a 401, except for the public paths below. The session
token is revalidated against the identity provider with caching, refresh and
a grace period (see :func:`grip.core.auth.validate_session_token`).

Whether the person behind the session may still use this instance (active,
right function) is decided per route by the dependencies in
:mod:`grip.core.auth`. ``tests/test_route_authorization_inventory.py`` fails
the build when a route has no such dependency.

Without OIDC (local development, DEV_NO_AUTH) the middleware is a no-op.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from grip.core.config import Settings
from grip.core.problem import PROBLEM_MEDIA_TYPE, problem_bytes

# Paths reachable without authentication. Keep this list small: everything
# else under /api/ needs a valid session.
PUBLIC_PREFIXES = (
    "/api/auth/login",
    "/api/auth/callback",
    "/api/auth/logout",
    "/api/auth/status",
    "/api/health/",
)

# Public paths that must match exactly, so a later route under the same
# prefix does not become public by accident.
PUBLIC_EXACT = (
    # Name and base URI of the instance: the login page shows the name.
    "/api/instance",
)


def is_public_path(path: str) -> bool:
    """Return True for routes that are reachable without authentication."""
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


async def _deny(send: Send, *, status_code: int, detail: str) -> None:
    body = problem_bytes(status_code, detail)
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", PROBLEM_MEDIA_TYPE.encode()),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AuthRequiredMiddleware:
    """ASGI middleware that enforces authentication on API routes."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Let CORS preflight through so CORSMiddleware can answer it.
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if not path.startswith("/api/") or is_public_path(path):
            await self.app(scope, receive, send)
            return

        if not self.settings.OIDC_ISSUER:
            await self.app(scope, receive, send)
            return

        session: dict = scope.get("session", {})
        if session.get("access_token") and session.get("person_id"):
            from grip.core.auth import validate_session_token

            if await validate_session_token(session, self.settings):
                await self.app(scope, receive, send)
                return

        session.clear()
        await _deny(send, status_code=401, detail="Niet ingelogd")
