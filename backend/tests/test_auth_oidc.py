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

    paths = [
        "/api/protected",
        "/api/instance",
        "/api/instances",
        "/api/auth/status",
        "/api/health/",
        "/assets/app.js",
    ]
    app = Starlette(routes=[Route(p, ok) for p in paths])
    guarded = AuthRequiredMiddleware(app, settings=_oidc_settings())
    return TestClient(_InjectSession(guarded, session))


def test_without_session_api_is_refused():
    session: dict = {}
    resp = _client(session).get("/api/protected")
    assert resp.status_code == 401
    assert resp.headers["content-type"] == "application/problem+json"
    assert resp.json() == {
        "type": "about:blank",
        "title": "Niet ingelogd",
        "status": 401,
        "detail": "Niet ingelogd",
    }


def test_public_and_non_api_paths_pass_without_session():
    client = _client({})
    assert client.get("/api/auth/status").status_code == 200
    assert client.get("/api/instance").status_code == 200
    assert client.get("/api/health/").status_code == 200
    assert client.get("/assets/app.js").status_code == 200


def test_public_exact_path_does_not_open_its_prefix():
    """/api/instance is public; a later /api/instances must not be."""
    assert _client({}).get("/api/instances").status_code == 401


def test_validated_session_passes():
    assert _client(_fresh_session("x")).get("/api/protected").status_code == 200


def test_session_without_person_is_refused_and_cleared():
    """Tokens alone are not enough: login must have matched a person."""
    session = {"access_token": "token", "token_validated_at": time.time()}
    assert _client(session).get("/api/protected").status_code == 401
    assert session == {}


def test_preflight_passes_without_session():
    assert _client({}).options("/api/protected").status_code != 401


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


# --- the provider's own endpoints must be https --------------------------------


def _metadata(**overrides) -> dict:
    base = "https://idp.example/realms/x/protocol/openid-connect"
    return {
        "issuer": "https://idp.example/realms/x",
        "authorization_endpoint": f"{base}/auth",
        "token_endpoint": f"{base}/token",
        "userinfo_endpoint": f"{base}/userinfo",
        "jwks_uri": f"{base}/certs",
        "end_session_endpoint": f"{base}/logout",
        **overrides,
    }


async def test_startup_refuses_a_provider_that_publishes_http_endpoints(monkeypatch):
    import pytest

    from grip.core import auth

    async def _published(_settings):
        return _metadata(
            jwks_uri="http://idp.internal:8080/realms/x/certs",
            userinfo_endpoint="http://idp.internal:8080/realms/x/userinfo",
        )

    monkeypatch.setattr(auth, "get_oidc_metadata", _published)
    with pytest.raises(auth.InsecureOidcEndpointError) as excinfo:
        await auth.check_oidc_transport(_oidc_settings())
    message = str(excinfo.value)
    assert "jwks_uri" in message and "userinfo_endpoint" in message
    assert "token_endpoint" not in message
    assert "OIDC_ALLOW_INSECURE_HTTP" in message


async def test_startup_accepts_https_endpoints(monkeypatch):
    from grip.core import auth

    async def _published(_settings):
        return _metadata()

    monkeypatch.setattr(auth, "get_oidc_metadata", _published)
    await auth.check_oidc_transport(_oidc_settings())


async def test_startup_does_not_fail_on_an_unreachable_provider(monkeypatch):
    """An outage is not a configuration error; the app must still start."""
    from grip.core import auth

    async def _unreachable(_settings):
        return None

    monkeypatch.setattr(auth, "get_oidc_metadata", _unreachable)
    await auth.check_oidc_transport(_oidc_settings())


async def test_startup_check_is_skipped_without_a_provider_or_with_the_opt_out(
    monkeypatch,
):
    from grip.core import auth

    async def _must_not_be_called(_settings):
        raise AssertionError("no discovery document should be fetched")

    monkeypatch.setattr(auth, "get_oidc_metadata", _must_not_be_called)
    await auth.check_oidc_transport(Settings(_env_file=None, DEV_NO_AUTH=True))
    local = Settings(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER="http://localhost:9080/realms/grip",
        OIDC_ALLOW_INSECURE_HTTP=True,
        SESSION_SECRET_KEY="s" * 40,
    )
    await auth.check_oidc_transport(local)


def test_credentials_go_over_http_only_with_the_opt_out():
    from grip.core.auth import require_https

    strict = _oidc_settings()
    local = Settings(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER="http://localhost:9080/realms/grip",
        OIDC_ALLOW_INSECURE_HTTP=True,
        SESSION_SECRET_KEY="s" * 40,
    )
    assert require_https("https://idp.example/token", "Token endpoint", strict)
    assert not require_https("http://idp.example/token", "Token endpoint", strict)
    assert require_https("http://localhost:9080/token", "Token endpoint", local)
