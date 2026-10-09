"""What an attacker tries at the edges: tokens, headers, sizes and limits.

Each test is a finding of the security review (docs/beveiliging.md) with
the fix that closes it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from grip.core import rate_limit
from grip.core.auth import validate_jwt_locally
from grip.core.config import Settings
from grip.middleware.body_limit import (
    MAX_BODY_BYTES,
    MAX_UPLOAD_BYTES,
    BodyLimitMiddleware,
    limit_for,
)
from grip.middleware.csrf import CSRF_COOKIE_NAME, CSRFMiddleware
from grip.middleware.csrf import _starts as csrf_starts
from grip.middleware.security_headers import (
    API_CONTENT_SECURITY_POLICY,
    SecurityHeadersMiddleware,
)
from grip.middleware.session import COOKIE_NAME, ServerSideSessionMiddleware

ISSUER = "https://idp.example/realms/x"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "DEV_NO_AUTH": False,
        "OIDC_ISSUER": ISSUER,
        "OIDC_CLIENT_ID": "grip",
        "SESSION_SECRET_KEY": "s" * 40,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# -- the token of a session ----------------------------------------------------


@pytest.fixture(scope="module")
def provider_key() -> Any:
    return JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "k1"})


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _claims(**changes: Any) -> dict[str, Any]:
    claims = {"iss": ISSUER, "aud": "grip", "sub": "x", "exp": int(time.time()) + 600}
    claims.update(changes)
    return {key: value for key, value in claims.items() if value is not None}


def _signed(key: Any, claims: dict[str, Any]) -> str:
    return (
        JsonWebToken(["RS256"])
        .encode({"alg": "RS256", "kid": "k1"}, claims, key)
        .decode()
    )


def _key_set(key: Any) -> Any:
    return JsonWebKey.import_key_set({"keys": [key.as_dict(is_private=False)]})


def test_a_token_of_the_provider_is_accepted(provider_key) -> None:
    token = _signed(provider_key, _claims())
    assert validate_jwt_locally(token, _key_set(provider_key), _settings())


def test_an_unsigned_token_is_refused(provider_key) -> None:
    header = _b64(json.dumps({"alg": "none", "kid": "k1"}).encode())
    token = f"{header}.{_b64(json.dumps(_claims()).encode())}."
    assert validate_jwt_locally(token, _key_set(provider_key), _settings()) is None


def test_a_token_signed_with_the_public_key_as_secret_is_refused(provider_key) -> None:
    # Algorithm confusion: HS256 with the published key as the shared secret.
    # It used to end in an error nobody caught.
    head = _b64(json.dumps({"alg": "HS256", "kid": "k1"}).encode())
    signed = f"{head}.{_b64(json.dumps(_claims()).encode())}"
    secret = provider_key.as_pem(is_private=False)
    mac = hmac.new(secret, signed.encode(), hashlib.sha256).digest()
    token = f"{signed}.{_b64(mac)}"
    assert validate_jwt_locally(token, _key_set(provider_key), _settings()) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"exp": None},
        {"exp": int(time.time()) - 10},
        {"aud": "another-client", "azp": "another-client"},
        {"iss": "https://idp.example/realms/other"},
    ],
)
def test_a_token_without_end_or_for_someone_else_is_refused(
    provider_key, changes
) -> None:
    token = _signed(provider_key, _claims(**changes))
    assert validate_jwt_locally(token, _key_set(provider_key), _settings()) is None


# -- what a deployed instance refuses to start with ----------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"SESSION_SECRET_KEY": "short-secret"},
        {"SESSION_SECRET_KEY": "lokale-omgeving-geen-geheim-9f3b1c-and-more"},
        {"DEBUG": True},
    ],
)
def test_a_deployed_instance_refuses_weak_settings(overrides) -> None:
    with pytest.raises(ValidationError):
        _settings(PUBLIC_HOST="https://grip.example", **overrides)
    # The same values are fine on a developer's machine.
    _settings(**overrides)


# -- headers on every answer ---------------------------------------------------


def _edge_app(*routes: Route) -> Starlette:
    app = Starlette(routes=list(routes))
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(ServerSideSessionMiddleware, store=_Store(), secret_key="k" * 40)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    return app


class _Store:
    """Keeps sessions in memory and counts what was stored."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    async def get(self, session_id: str) -> dict[str, Any] | None:
        return self.rows.get(session_id)

    async def set(self, session_id: str, data: dict[str, Any]) -> None:
        self.rows[session_id] = dict(data)

    async def delete(self, session_id: str) -> None:
        self.rows.pop(session_id, None)

    async def cleanup(self) -> int:
        return 0


async def _data(_request: Request) -> Response:
    return JSONResponse({"ok": True})


async def _pdf(_request: Request) -> Response:
    return Response(b"%PDF-1.7", media_type="application/pdf")


async def _page(_request: Request) -> Response:
    return Response(
        "<p>x</p>",
        media_type="text/html",
        headers={"Content-Security-Policy": "default-src 'none'"},
    )


async def _cached(_request: Request) -> Response:
    return JSONResponse({}, headers={"Cache-Control": "max-age=60"})


async def _echo(request: Request) -> Response:
    return JSONResponse({"bytes": len(await request.body())})


def _store_of(app: Starlette) -> _Store:
    return next(m.kwargs["store"] for m in app.user_middleware if "store" in m.kwargs)


def test_an_answer_of_the_api_is_closed_and_not_kept() -> None:
    client = TestClient(_edge_app(Route("/api/x", _data)))
    headers = client.get("/api/x").headers
    assert headers["content-security-policy"] == API_CONTENT_SECURITY_POLICY
    assert headers["cache-control"] == "private, no-store"
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


def test_a_refusal_by_a_middleware_carries_the_headers_too() -> None:
    client = TestClient(_edge_app(Route("/api/x", _data, methods=["POST"])))
    refused = client.post("/api/x", json={})
    assert refused.status_code == 403
    assert refused.headers["content-security-policy"] == API_CONTENT_SECURITY_POLICY
    assert refused.headers["x-frame-options"] == "DENY"


def test_a_route_keeps_the_policy_and_the_cache_rule_it_chose() -> None:
    client = TestClient(
        _edge_app(Route("/api/page", _page), Route("/api/cached", _cached))
    )
    assert client.get("/api/page").headers["content-security-policy"] == (
        "default-src 'none'"
    )
    assert client.get("/api/cached").headers["cache-control"] == "max-age=60"


def test_a_pdf_gets_no_policy_that_would_stop_the_viewer() -> None:
    client = TestClient(_edge_app(Route("/api/doc", _pdf)))
    headers = client.get("/api/doc").headers
    assert "content-security-policy" not in headers
    assert headers["x-content-type-options"] == "nosniff"


# -- how much a request may carry ------------------------------------------------


def test_the_ceiling_depends_on_what_is_sent() -> None:
    assert limit_for("/api/assignments", "application/json") == MAX_BODY_BYTES
    assert limit_for("/api/costs/x", "multipart/form-data; boundary=b") == (
        MAX_UPLOAD_BYTES
    )
    assert limit_for("/api/proof/verify", "application/json") > MAX_UPLOAD_BYTES


def _with_token(app: Starlette) -> TestClient:
    client = TestClient(app)
    client.get("/api/auth/status")
    client.headers["X-CSRF-Token"] = client.cookies.get(CSRF_COOKIE_NAME)
    return client


def test_a_body_over_the_ceiling_is_refused_before_it_is_read() -> None:
    csrf_starts.reset()
    app = _edge_app(
        Route("/api/auth/status", _data), Route("/api/x", _echo, methods=["POST"])
    )
    client = _with_token(app)
    fits = client.post("/api/x", content=b"x" * 1000)
    assert fits.json() == {"bytes": 1000}
    too_large = client.post("/api/x", content=b"x" * (MAX_BODY_BYTES + 1))
    assert too_large.status_code == 413
    assert too_large.headers["content-type"].startswith("application/problem+json")


def test_a_body_without_a_stated_length_is_counted() -> None:
    csrf_starts.reset()
    app = _edge_app(
        Route("/api/auth/status", _data), Route("/api/x", _echo, methods=["POST"])
    )
    client = _with_token(app)

    def chunks():
        for _ in range(MAX_BODY_BYTES // 65536 + 2):
            yield b"y" * 65536

    assert client.post("/api/x", content=chunks()).status_code == 413


# -- sessions nobody logged in with ----------------------------------------------


def test_a_request_without_a_session_stores_none() -> None:
    csrf_starts.reset()
    app = _edge_app(
        Route("/api/instance", _data),
        Route("/api/auth/status", _data),
        Route("/api/x", _data, methods=["POST"]),
    )
    store = _store_of(app)
    anonymous = TestClient(app)
    assert COOKIE_NAME not in anonymous.get("/api/instance").cookies
    assert anonymous.post("/api/x", json={}).status_code == 403
    assert store.rows == {}

    # A browser opens the application by asking who is logged in.
    browser = TestClient(app)
    assert browser.get("/api/auth/status").cookies.get(CSRF_COOKIE_NAME)
    assert len(store.rows) == 1
    # From then on every request belongs to that session.
    browser.get("/api/instance")
    assert len(store.rows) == 1


def test_sessions_without_a_login_are_limited_per_address() -> None:
    csrf_starts.reset()
    app = _edge_app(Route("/api/auth/status", _data))
    store = _store_of(app)
    for _ in range(csrf_starts.limit + 30):
        assert TestClient(app).get("/api/auth/status").status_code == 200
    assert len(store.rows) == csrf_starts.limit
    csrf_starts.reset()


async def test_a_session_without_a_login_is_kept_shorter(db_session) -> None:
    from contextlib import asynccontextmanager

    from sqlalchemy import select

    from grip.core.session_store import ANONYMOUS_TTL_SECONDS, DatabaseSessionStore
    from grip.models.http_session import HttpSession

    @asynccontextmanager
    async def factory():
        yield db_session

    store = DatabaseSessionStore(session_factory=factory, ttl_seconds=7 * 86400)
    await store.set("anon", {"csrf_token": "t"})
    await store.set("login", {"csrf_token": "t", "person_id": "p"})
    rows = {
        row.session_id: row.expires_at
        for row in (await db_session.execute(select(HttpSession))).scalars()
    }
    assert (rows["login"] - rows["anon"]).total_seconds() == pytest.approx(
        7 * 86400 - ANONYMOUS_TTL_SECONDS, abs=5
    )


# -- limits ----------------------------------------------------------------------


def test_the_table_of_a_limit_does_not_grow_without_end(monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "_MAX_KEYS", 100)
    limiter = rate_limit.KeyedLimiter(limit=2, window=60)
    for number in range(1000):
        limiter.allow(f"203.0.113.{number}")
    assert len(limiter._calls) <= 100
    # A key over its limit stays refused while it keeps calling.
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")


def test_a_person_is_limited_and_another_is_not() -> None:
    limiter = rate_limit.PersonLimiter(limit=2, window=60, detail="Te vaak.")
    limiter.check("one")
    limiter.check("one")
    with pytest.raises(HTTPException) as refused:
        limiter.check("one")
    assert refused.value.status_code == 429
    limiter.check("two")


def test_the_language_model_is_limited_per_caller() -> None:
    from grip.events import context as event_context
    from grip.services.llm import client as llm

    llm.reset_call_counts()
    try:
        with event_context.scope():
            event_context.set_visitor("bezoeker:a@voorbeeld.example")
            for _ in range(llm.CALLS_PER_PERSON_PER_HOUR):
                llm.count_call()
            with pytest.raises(llm.LlmBusyError):
                llm.count_call()
        # Another visitor through the same example person still gets through.
        with event_context.scope():
            event_context.set_visitor("bezoeker:b@voorbeeld.example")
            llm.count_call()
    finally:
        llm.reset_call_counts()


# -- what a document may load ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://example.org/x.png",
        "file:///etc/passwd",
        "file:///app/.env",
        "ftp://example.org/x",
    ],
)
def test_a_document_loads_nothing_from_outside_itself(url) -> None:
    from grip.services.quote_document import (
        ResourceRefusedError,
        _find_homebrew_libraries,
        document_resource_allowed,
        document_url_fetcher,
    )

    assert not document_resource_allowed(url)
    _find_homebrew_libraries()
    pytest.importorskip("weasyprint")
    with pytest.raises(ResourceRefusedError):
        document_url_fetcher().fetch(url)


def test_a_document_loads_its_own_ribbon_and_typeface(tmp_path) -> None:
    from grip.services.quote_document import (
        _find_homebrew_libraries,
        document_resource_allowed,
        document_url_fetcher,
    )

    typeface = tmp_path / "RijksSansWeb-Regular.woff2"
    typeface.write_bytes(b"wOF2")
    assert document_resource_allowed(typeface.as_uri())
    assert document_resource_allowed("data:image/svg+xml;base64,PHN2Zy8+")
    _find_homebrew_libraries()
    pytest.importorskip("weasyprint")
    fetcher = document_url_fetcher()
    assert fetcher.fetch(typeface.as_uri()) is not None
    assert fetcher.fetch("data:text/plain;base64,eA==") is not None


def test_a_remote_picture_in_a_page_is_not_fetched() -> None:
    # The whole path: a page that names a remote address renders, and the
    # address is never asked for.
    from grip.services.quote_document import (
        _find_homebrew_libraries,
        document_url_fetcher,
    )

    _find_homebrew_libraries()
    weasyprint = pytest.importorskip("weasyprint")
    asked: list[str] = []
    fetcher = document_url_fetcher()
    allowed = fetcher.open

    def _open(*args: Any, **kwargs: Any) -> Any:
        asked.append(str(args[0] if args else kwargs))
        return allowed(*args, **kwargs)

    fetcher.open = _open
    page = '<p>x<img src="http://127.0.0.1:9/a.png"></p><style>p{background:url(file:///etc/passwd)}</style>'
    pdf = weasyprint.HTML(string=page, base_url=None, url_fetcher=fetcher).write_pdf()
    assert pdf.startswith(b"%PDF")
    assert asked == []


# -- the frontend's nginx -----------------------------------------------------------


def test_every_location_of_the_frontend_sends_the_page_policy() -> None:
    # nginx drops the headers of the server block in a location that sets a
    # header of its own, so each such location has to repeat them.
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "frontend"
    template = (root / "nginx.conf.template").read_text()
    assert "script-src 'self';" in template
    assert "'unsafe-eval'" not in template
    assert "frame-ancestors 'none'" in template
    blocks = re.findall(r"location [^{]+\{([^}]*)\}", template)
    assert len(blocks) >= 4
    for block in blocks:
        if "add_header" in block:
            assert "Content-Security-Policy $grip_csp" in block
            assert 'X-Frame-Options "DENY"' in block
            assert "X-Content-Type-Options" in block

    # The API location keeps the backend's own, closed policy: it sets a
    # header of its own so the page policy is not added on top.
    script = (root / "docker-api-proxy.sh").read_text()
    proxy = script.split("location /api/ {", 1)[1].split("CONF", 1)[0]
    assert "add_header X-Content-Type-Options" in proxy
    assert "Content-Security-Policy" not in proxy
    assert "/.well-known/security.txt" in script
    assert "include /tmp/grip-security.conf;" in template
