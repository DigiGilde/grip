"""Behaviour with an identity provider configured.

The token round trips to the provider are not exercised here: a session that
was validated moments ago is accepted without a network call, which is the
state these tests set up.
"""

import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from grip.core.auth import resolve_person
from grip.core.config import Settings
from grip.middleware.auth_required import AuthRequiredMiddleware


def _oidc_settings() -> Settings:
    return Settings(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER="https://idp.example/realms/x",
        SESSION_SECRET_KEY="s" * 40,
    )


def _fresh_session(person_id: str) -> dict:
    return {
        "access_token": "token",
        "person_id": person_id,
        "token_validated_at": time.time(),
    }


class _InjectSession:
    """Stands in for the session middleware with a fixed session."""

    def __init__(self, app, session: dict) -> None:
        self.app = app
        self.session = session

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope["session"] = self.session
        await self.app(scope, receive, send)


def _client(session: dict) -> TestClient:
    async def ok(_request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    paths = ["/api/instance", "/api/auth/status", "/api/health/", "/assets/app.js"]
    app = Starlette(routes=[Route(p, ok) for p in paths])
    guarded = AuthRequiredMiddleware(app, settings=_oidc_settings())
    return TestClient(_InjectSession(guarded, session))


def test_without_session_api_is_refused():
    session: dict = {}
    resp = _client(session).get("/api/instance")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Niet ingelogd"}


def test_public_and_non_api_paths_pass_without_session():
    client = _client({})
    assert client.get("/api/auth/status").status_code == 200
    assert client.get("/api/health/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200


def test_validated_session_passes():
    assert _client(_fresh_session("x")).get("/api/instance").status_code == 200


def test_session_without_person_is_refused_and_cleared():
    """Tokens alone are not enough: login must have matched a person."""
    session = {"access_token": "token", "token_validated_at": time.time()}
    assert _client(session).get("/api/instance").status_code == 401
    assert session == {}


def test_preflight_passes_without_session():
    assert _client({}).options("/api/instance").status_code != 401


def _request(session: dict) -> Request:
    return Request({"type": "http", "headers": [], "session": session})


async def test_resolve_person_loads_the_person_from_the_session(
    db_session, create_person
):
    person = await create_person("a@example.org")
    session = _fresh_session(str(person.id))

    found = await resolve_person(_request(session), db_session, _oidc_settings())

    assert found is not None and found.id == person.id


async def test_deactivated_person_loses_the_session(db_session, create_person):
    person = await create_person("a@example.org", is_active=False)
    session = _fresh_session(str(person.id))

    found = await resolve_person(_request(session), db_session, _oidc_settings())

    assert found is None
    assert session == {}


async def test_dev_cookie_is_ignored_with_oidc(db_session, create_person):
    """The development person picker must not work on a real instance."""
    person = await create_person("a@example.org", functions=["beheerder"])
    request = Request(
        {
            "type": "http",
            "headers": [(b"cookie", f"grip_dev_person={person.id}".encode())],
            "session": {},
        }
    )
    assert await resolve_person(request, db_session, _oidc_settings()) is None
