"""An invited signer without a person record: the signing pages and nothing else.

Three layers are tested: the login decides who becomes a guest, the
middleware keeps a guest session on the signing routes, and the signing
routes themselves show a guest only the quote the address was invited for.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI, routing
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from grip.api.routes import api_router
from grip.api.routes import auth as auth_routes
from grip.core.auth import GUEST_API_PREFIX, GUEST_SESSION_KEY
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.core.problem import install_exception_handlers
from grip.middleware.auth_required import AuthRequiredMiddleware, is_public_path
from grip.middleware.session import ServerSideSessionMiddleware
from grip.services import quotes as quote_service

GUEST_EMAIL = "gast@opdrachtgever.example"


async def _issued_and_invited(
    act_as, world, email: str = GUEST_EMAIL, **invite
) -> dict:
    client = act_as(world.manager)
    quote = (
        await client.post(f"/api/assignments/{world.assignment.id}/quotes", json={})
    ).json()
    response = await client.post(
        f"/api/quotes/{quote['id']}/invitations", json={"email": email, **invite}
    )
    assert response.status_code == 201, response.text
    return quote


# --- the login decides who becomes a guest ---------------------------------


class _FakeProvider:
    def __init__(self) -> None:
        self.userinfo: dict = {}

    async def authorize_redirect(self, _request, redirect_uri):
        return RedirectResponse("https://idp.example/auth", status_code=302)

    async def authorize_access_token(self, _request):
        return {"access_token": "a", "refresh_token": "r", "userinfo": self.userinfo}


class _FakeOAuth:
    def __init__(self, provider: _FakeProvider) -> None:
        self.keycloak = provider


@pytest.fixture
def provider(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setattr(auth_routes, "get_oauth", lambda _s: _FakeOAuth(fake))
    revoked: list[str] = []

    async def _revoke(*_args, **kwargs) -> None:
        revoked.append(kwargs.get("access_token", ""))

    monkeypatch.setattr(auth_routes, "revoke_tokens", _revoke)
    fake.revoked = revoked  # type: ignore[attr-defined]
    return fake


def _sessions(client: AsyncClient) -> list[dict]:
    """Every session the app holds for this test."""
    mw = client._transport.app.middleware_stack  # type: ignore[attr-defined]
    while mw is not None and not isinstance(mw, ServerSideSessionMiddleware):
        mw = getattr(mw, "app", None)
    assert mw is not None
    return list(mw.store._data.values())


def _userinfo(email: str = GUEST_EMAIL, *, verified: bool = True) -> dict:
    return {
        "sub": f"sub-{uuid4()}",
        "email": email,
        "email_verified": verified,
        "name": "Gast Tekenaar",
    }


async def test_invited_unknown_identity_becomes_a_guest(
    client, act_as, world, provider
):
    await _issued_and_invited(act_as, world)
    provider.userinfo = _userinfo(GUEST_EMAIL.upper())

    response = await client.get("/api/auth/callback?code=c&state=s")
    assert response.status_code == 302
    assert response.headers["location"].endswith("/tekenen")
    assert provider.revoked == []

    guests = [s for s in _sessions(client) if GUEST_SESSION_KEY in s]
    assert len(guests) == 1
    session = guests[0]
    assert session[GUEST_SESSION_KEY] == {
        "email": GUEST_EMAIL,
        "name": "Gast Tekenaar",
        "email_verified": True,
    }
    # A guest is not a person of this instance.
    assert "person_id" not in session
    assert session["access_token"] == "a"


async def test_guest_lands_on_the_quote_the_link_pointed_at(
    client, act_as, world, provider
):
    quote = await _issued_and_invited(act_as, world)
    provider.userinfo = _userinfo()
    await client.get(f"/api/auth/login?next=/tekenen/{quote['id']}")
    response = await client.get("/api/auth/callback?code=c&state=s")
    assert response.headers["location"].endswith(f"/tekenen/{quote['id']}")


async def test_guest_never_lands_inside_the_application(
    client, act_as, world, provider
):
    await _issued_and_invited(act_as, world)
    provider.userinfo = _userinfo()
    await client.get("/api/auth/login?next=/opdrachten")
    response = await client.get("/api/auth/callback?code=c&state=s")
    assert response.headers["location"].endswith("/tekenen")


@pytest.mark.parametrize(
    ("case", "userinfo", "invite"),
    [
        ("unverified email", _userinfo(verified=False), {}),
        ("no invitation for this address", _userinfo("ander@elders.example"), {}),
        (
            "expired invitation",
            _userinfo(),
            {"expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()},
        ),
        ("no email at all", {**_userinfo(), "email": ""}, {}),
    ],
)
async def test_everyone_else_is_refused(
    client, act_as, world, provider, case, userinfo, invite
):
    await _issued_and_invited(act_as, world, **invite)
    provider.userinfo = userinfo

    response = await client.get("/api/auth/callback?code=c&state=s")
    assert response.status_code == 302, case
    assert response.headers["location"].endswith("login_error=geen_toegang"), case
    assert provider.revoked == ["a"], case
    assert not [s for s in _sessions(client) if GUEST_SESSION_KEY in s], case


# --- a guest session against the whole API ----------------------------------


def _oidc_settings() -> Settings:
    return Settings(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER="https://idp.example/realms/x",
        SESSION_SECRET_KEY="s" * 40,
    )


class _InjectSession:
    """Stands in for the session middleware with a fixed session."""

    def __init__(self, app, session: dict) -> None:
        self.app = app
        self.session = session

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            scope["session"] = self.session
        await self.app(scope, receive, send)


def _guest_session(email: str = GUEST_EMAIL) -> dict:
    return {
        "access_token": "token",
        # Validated a moment ago, so no round trip to the provider.
        "token_validated_at": time.time(),
        GUEST_SESSION_KEY: {
            "email": email,
            "name": "Gast Tekenaar",
            "email_verified": True,
        },
    }


@pytest.fixture
def guest_api(db_session):
    """The real API behind the real middleware, with an identity provider
    configured and a fixed session."""

    def _build(session: dict) -> AsyncClient:
        settings = _oidc_settings()
        app = FastAPI()
        install_exception_handlers(app)
        app.include_router(api_router, prefix="/api")

        async def _db():
            yield db_session

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_settings] = lambda: settings
        app.add_middleware(AuthRequiredMiddleware, settings=settings)
        return AsyncClient(
            transport=ASGITransport(app=_InjectSession(app, session)),
            base_url="http://test",
        )

    return _build


def _all_routes() -> list[tuple[str, str]]:
    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    found: list[tuple[str, str]] = []
    iter_contexts = getattr(routing, "iter_route_contexts", None)
    if iter_contexts is None:
        routes = [r for r in app.routes if isinstance(r, APIRoute)]
        for route in routes:
            found.extend((m, route.path) for m in route.methods)
    else:
        for context in iter_contexts(app.router.routes):
            route = context.original_route
            if isinstance(route, APIRoute):
                found.extend((m, context.path) for m in context.methods or [])
    return sorted(set(found))


def _concrete(path: str) -> str:
    """The path with every parameter filled in."""
    parts = []
    for part in path.split("/"):
        if part.startswith("{"):
            name = part.strip("{}").split(":")[0]
            if name == "month":
                parts.append("2026-03")
            elif name == "year":
                parts.append("2026")
            else:
                parts.append(str(uuid4()))
        else:
            parts.append(part)
    return "/".join(parts)


def test_the_route_table_is_read_in_full():
    routes = _all_routes()
    paths = {path for _method, path in routes}
    # A vacuous loop would make the test below pass for the wrong reason.
    assert len(routes) > 80
    assert "/api/assignments" in paths
    assert any(path.startswith(GUEST_API_PREFIX) for path in paths)


async def test_a_guest_session_reaches_no_route_outside_signing(guest_api):
    session = _guest_session()
    refused = 0
    async with guest_api(session) as client:
        for method, path in _all_routes():
            if is_public_path(path) or path.startswith(GUEST_API_PREFIX):
                continue
            response = await client.request(method, _concrete(path), json={})
            assert response.status_code == 403, (method, path, response.status_code)
            assert response.headers["content-type"].startswith(
                "application/problem+json"
            )
            refused += 1
    assert refused > 80
    # A stray request does not end the guest's session.
    assert GUEST_SESSION_KEY in session


async def test_a_guest_reaches_the_invited_quote_and_nothing_else(
    guest_api, act_as, world, db_session
):
    quote = await _issued_and_invited(act_as, world)
    # A second quote, on the same assignment, that the guest was not invited
    # for: issuing again supersedes the first, so invite on the first only.
    other = await quote_service.issue_quote(
        db_session, world.assignment.id, actor=world.manager
    )
    await quote_service.invite_signer(
        db_session, other.id, email="iemand.anders@elders.example", actor=world.manager
    )

    async with guest_api(_guest_session()) as client:
        listed = (await client.get("/api/signing/invitations")).json()["invitations"]
        assert [entry["quote_id"] for entry in listed] == [quote["id"]]

        seen = await client.get(f"/api/signing/quotes/{quote['id']}")
        assert seen.status_code == 200, seen.text
        document = await client.get(f"/api/signing/quotes/{quote['id']}/document")
        assert document.status_code == 200

        for path in (
            f"/api/signing/quotes/{other.id}",
            f"/api/signing/quotes/{other.id}/document",
            f"/api/signing/quotes/{uuid4()}",
        ):
            assert (await client.get(path)).status_code == 404, path
        refused = await client.post(
            f"/api/signing/quotes/{other.id}/accept",
            json={
                "quote_hash": other.snapshot_hash,
                "signer_function": "Directeur",
                "confirm_mandate": True,
            },
        )
        assert refused.status_code == 404

        # The same quote through the routes of the application: not for a guest.
        assert (await client.get(f"/api/quotes/{quote['id']}")).status_code == 403


async def test_a_guest_signs_without_a_person_record(guest_api, act_as, world):
    quote = await _issued_and_invited(act_as, world)
    async with guest_api(_guest_session()) as client:
        response = await client.post(
            f"/api/signing/quotes/{quote['id']}/accept",
            json={
                "quote_hash": quote["snapshot_hash"],
                "signer_function": "Directeur",
                "confirm_mandate": True,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "accepted"

    seen = (await act_as(world.manager).get(f"/api/quotes/{quote['id']}")).json()
    assert seen["acceptance"]["form"] == "signing_link"
    assert seen["acceptance"]["signer_name"] == "Gast Tekenaar"


async def test_a_guest_for_another_address_sees_nothing(guest_api, act_as, world):
    quote = await _issued_and_invited(act_as, world)
    async with guest_api(_guest_session("ander@elders.example")) as client:
        assert (await client.get("/api/signing/invitations")).json() == {
            "invitations": []
        }
        assert (
            await client.get(f"/api/signing/quotes/{quote['id']}")
        ).status_code == 404


@pytest.mark.parametrize(
    "broken",
    [
        {"email_verified": False},
        {"email": ""},
    ],
)
async def test_a_guest_session_that_does_not_qualify_is_refused(
    guest_api, act_as, world, broken
):
    await _issued_and_invited(act_as, world)
    session = _guest_session()
    session[GUEST_SESSION_KEY].update(broken)
    async with guest_api(session) as client:
        response = await client.get("/api/signing/invitations")
        assert response.status_code == 401


async def test_status_reports_a_guest_distinctly(guest_api):
    async with guest_api(_guest_session()) as client:
        body = (await client.get("/api/auth/status")).json()
    assert body["authenticated"] is False
    assert body["person"] is None and body["functions"] == []
    assert body["guest"] == {"name": "Gast Tekenaar", "email": GUEST_EMAIL}


async def test_status_without_a_session_reports_no_guest(guest_api):
    async with guest_api({}) as client:
        body = (await client.get("/api/auth/status")).json()
    assert body["authenticated"] is False and body["guest"] is None
