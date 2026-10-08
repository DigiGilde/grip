"""The seam between backend and frontend.

Covers what the two sides agreed on: errors as problem documents, the
return path after login, the callback origin, and forwarded headers from a
trusted proxy only.
"""

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from grip.api.routes import auth as auth_routes
from grip.api.routes.auth import _callback_url, safe_next_path
from grip.core.config import Settings
from grip.core.problem import install_exception_handlers
from grip.middleware.proxy_headers import (
    TrustedProxyMiddleware,
    parse_trusted_proxies,
)

PROBLEM = "application/problem+json"


# --- problem+json ---------------------------------------------------------


def _problem_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)

    class Body(BaseModel):
        amount: int

    @app.get("/forbidden")
    async def _forbidden() -> None:
        raise HTTPException(status_code=403, detail="Dit mag je niet inzien")

    @app.get("/bare")
    async def _bare() -> None:
        raise HTTPException(status_code=404)

    @app.get("/structured")
    async def _structured() -> None:
        raise HTTPException(status_code=409, detail={"field": "name"})

    @app.post("/validate")
    async def _validate(_body: Body) -> None:
        return None

    @app.get("/boom")
    async def _boom() -> None:
        raise RuntimeError("database password is hunter2")

    return app


def test_http_exception_is_a_problem_document():
    resp = TestClient(_problem_app()).get("/forbidden")
    assert resp.status_code == 403
    assert resp.headers["content-type"] == PROBLEM
    assert resp.json() == {
        "type": "about:blank",
        "title": "Geen toegang",
        "status": 403,
        "detail": "Dit mag je niet inzien",
    }


def test_default_status_phrase_is_not_repeated_as_detail():
    body = TestClient(_problem_app()).get("/bare").json()
    assert body == {"type": "about:blank", "title": "Niet gevonden", "status": 404}


def test_unknown_route_is_a_problem_document():
    resp = TestClient(_problem_app()).get("/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == PROBLEM


def test_structured_detail_goes_into_an_extension():
    body = TestClient(_problem_app()).get("/structured").json()
    assert "detail" not in body
    assert body["errors"] == {"field": "name"}


def test_validation_error_lists_fields_without_echoing_input():
    resp = TestClient(_problem_app()).post("/validate", json={"amount": "geheim"})
    assert resp.status_code == 422
    assert resp.headers["content-type"] == PROBLEM
    body = resp.json()
    assert body["title"] == "Ongeldige invoer"
    assert body["errors"][0]["loc"] == ["body", "amount"]
    assert set(body["errors"][0]) == {"loc", "msg", "type"}
    assert "geheim" not in resp.text


def test_unhandled_error_does_not_leak_internals():
    client = TestClient(_problem_app(), raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.headers["content-type"] == PROBLEM
    assert resp.json()["title"] == "Interne fout"
    assert "hunter2" not in resp.text
    assert "RuntimeError" not in resp.text


async def test_real_app_answers_with_problem_documents(client):
    not_found = await client.get("/api/bestaat-niet")
    assert not_found.status_code == 404
    assert not_found.headers["content-type"] == PROBLEM

    no_login = await client.get("/api/auth/login")
    assert no_login.status_code == 501
    assert no_login.json()["detail"] == "Inloggen is niet geconfigureerd"


# --- return path ----------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["/", "/opdrachten", "/opdrachten/123?tab=inzet", "/tarieven#2026", "/apikeys"],
)
def test_next_accepts_paths_within_the_application(value):
    assert safe_next_path(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "opdrachten",
        "//evil.example",
        "//evil.example/pad",
        "/\\evil.example",
        "/pad\\..\\x",
        "https://evil.example",
        "http:/evil.example",
        "javascript:alert(1)",
        "/pad\nSet-Cookie: x=1",
        "/pad\tx",
        "/api",
        "/api/auth/logout",
        "/" + "a" * 2000,
        123,
    ],
)
def test_next_rejects_everything_else(value):
    assert safe_next_path(value) == ""


# --- callback origin ------------------------------------------------------


def _settings(**overrides) -> Settings:
    values = {
        "DEV_NO_AUTH": True,
        "FRONTEND_URL": "https://grip.example",
        "BACKEND_URL": "https://api.grip.example",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _request(scheme: str, host: str) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": scheme,
            "path": "/api/auth/login",
            "query_string": b"",
            "server": ("internal", 8080),
            "headers": [(b"host", host.encode())],
        }
    )


def test_callback_goes_through_the_frontend_origin_when_the_request_did():
    url = _callback_url(_request("https", "grip.example"), _settings())
    assert url == "https://grip.example/api/auth/callback"


@pytest.mark.parametrize(
    ("scheme", "host"),
    [
        ("https", "api.grip.example"),
        ("https", "evil.example"),
        ("http", "grip.example"),
        ("https", "grip.example.evil.example"),
    ],
)
def test_callback_falls_back_to_the_configured_backend(scheme, host):
    url = _callback_url(_request(scheme, host), _settings())
    assert url == "https://api.grip.example/api/auth/callback"


# --- login round trip -----------------------------------------------------


class _FakeProvider:
    def __init__(self, userinfo: dict | None = None) -> None:
        self.userinfo = userinfo or {}
        self.redirect_uri = ""

    async def authorize_redirect(self, _request, redirect_uri):
        self.redirect_uri = redirect_uri
        return RedirectResponse("https://idp.example/auth", status_code=302)

    async def authorize_access_token(self, _request):
        return {"access_token": "a", "refresh_token": "r", "userinfo": self.userinfo}


class _FakeOAuth:
    def __init__(self, provider: _FakeProvider) -> None:
        self.keycloak = provider


@pytest.fixture
def fake_oauth(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(auth_routes, "get_oauth", lambda _s: _FakeOAuth(provider))

    async def _no_revoke(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(auth_routes, "revoke_tokens", _no_revoke)
    return provider


async def test_login_returns_to_the_requested_page(client, create_person, fake_oauth):
    person = await create_person("a@example.org")
    fake_oauth.userinfo = {
        "sub": "sub-1",
        "email": "a@example.org",
        "email_verified": True,
        "name": "A",
    }

    started = await client.get(
        "/api/auth/login", params={"next": "/tarieven?jaar=2026"}
    )
    assert started.status_code == 302
    assert fake_oauth.redirect_uri.endswith("/api/auth/callback")

    done = await client.get("/api/auth/callback")
    assert done.status_code == 302
    assert done.headers["location"] == "http://localhost:5183/tarieven?jaar=2026"
    assert person.oidc_subject == "sub-1"


async def test_login_drops_an_unsafe_return_path(client, create_person, fake_oauth):
    await create_person("a@example.org")
    fake_oauth.userinfo = {"sub": "s", "email": "a@example.org", "email_verified": True}

    await client.get("/api/auth/login", params={"next": "//evil.example/x"})
    done = await client.get("/api/auth/callback")

    assert done.headers["location"] == "http://localhost:5183"


async def test_return_path_does_not_survive_into_a_later_login(
    client, create_person, fake_oauth
):
    await create_person("a@example.org")
    fake_oauth.userinfo = {"sub": "s", "email": "a@example.org", "email_verified": True}

    await client.get("/api/auth/login", params={"next": "/team"})
    await client.get("/api/auth/login")
    done = await client.get("/api/auth/callback")

    assert done.headers["location"] == "http://localhost:5183"


async def test_unknown_identity_is_sent_back_with_the_reason(client, fake_oauth):
    fake_oauth.userinfo = {"sub": "x", "email": "x@example.org", "email_verified": True}

    await client.get("/api/auth/login", params={"next": "/team"})
    done = await client.get("/api/auth/callback")

    assert done.headers["location"] == "http://localhost:5183/?login_error=geen_toegang"
    assert (await client.get("/api/auth/status")).json()["authenticated"] is False


# --- forwarded headers ----------------------------------------------------


def _echo_app(trusted: str):
    async def echo(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "scheme": request.url.scheme,
                "host": request.headers.get("host"),
                "client": request.client.host if request.client else None,
            }
        )

    return TrustedProxyMiddleware(Starlette(routes=[Route("/", echo)]), trusted)


async def _get(app, peer: str, headers: dict) -> dict:
    transport = httpx.ASGITransport(app=app, client=(peer, 40000))
    async with httpx.AsyncClient(transport=transport, base_url="http://inner") as ac:
        return (await ac.get("/", headers=headers)).json()


_FORWARDED = {
    "X-Forwarded-Proto": "https",
    "X-Forwarded-Host": "grip.example",
    "X-Forwarded-For": "203.0.113.7, 10.0.0.9",
}


async def test_forwarded_headers_are_applied_from_a_trusted_proxy():
    seen = await _get(_echo_app("10.0.0.0/8"), "10.0.0.5", _FORWARDED)
    assert seen == {"scheme": "https", "host": "grip.example", "client": "203.0.113.7"}


async def test_forwarded_headers_are_ignored_from_anyone_else():
    seen = await _get(_echo_app("10.0.0.0/8"), "198.51.100.1", _FORWARDED)
    assert seen == {"scheme": "http", "host": "inner", "client": "198.51.100.1"}


async def test_nothing_is_trusted_by_default():
    seen = await _get(_echo_app(""), "127.0.0.1", _FORWARDED)
    assert seen == {"scheme": "http", "host": "inner", "client": "127.0.0.1"}


async def test_bad_forwarded_values_are_ignored():
    headers = {
        "X-Forwarded-Proto": "javascript",
        "X-Forwarded-Host": "evil.example/pad?x",
        "X-Forwarded-For": "not-an-address",
    }
    seen = await _get(_echo_app("10.0.0.5"), "10.0.0.5", headers)
    assert seen == {"scheme": "http", "host": "inner", "client": "10.0.0.5"}


def test_trusted_proxies_must_parse():
    assert len(parse_trusted_proxies("10.0.0.0/8, 127.0.0.1 ,::1")) == 3
    with pytest.raises(ValueError):
        parse_trusted_proxies("10.0.0.0/8, nonsense")
