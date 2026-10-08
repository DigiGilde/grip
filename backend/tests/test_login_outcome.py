"""What a login leads to, why it is refused, and that both are on record."""

from typing import Any

import httpx
import pytest
from authlib.integrations.starlette_client import OAuthError
from sqlalchemy import select
from starlette.requests import Request

from grip.api.routes import auth as auth_routes
from grip.core import oidc_diagnostics as diagnostics
from grip.core.auth import (
    MATCHED_BY_EMAIL,
    MATCHED_BY_SUBJECT,
    REFUSED_EMAIL_UNVERIFIED,
    REFUSED_INACTIVE,
    REFUSED_NO_EMAIL,
    REFUSED_NO_SUBJECT,
    REFUSED_OTHER_SUBJECT,
    REFUSED_UNKNOWN,
    display_name_from_claims,
    email_verified_claim,
    match_login,
    organisation_from_claims,
)
from grip.core.config import Settings
from grip.models.stream_event import StreamEvent

SSO_SUB = "urn:collab:person:voorbeeld.example:pietje"


async def test_each_refusal_has_its_own_reason(db_session, create_person):
    await create_person("gebonden@example.org", oidc_subject="oud-sub")
    await create_person("weg@example.org", is_active=False)
    await create_person("uit@example.org", is_active=False, oidc_subject="sub-uit")

    async def reason(**kwargs: Any) -> str | None:
        defaults = {"sub": "s", "email": "x@example.org", "email_verified": True}
        return (await match_login(db_session, **{**defaults, **kwargs})).refusal

    assert await reason(sub="") == REFUSED_NO_SUBJECT
    assert await reason(email="") == REFUSED_NO_EMAIL
    assert await reason(email_verified=False) == REFUSED_EMAIL_UNVERIFIED
    assert await reason() == REFUSED_UNKNOWN
    assert await reason(email="weg@example.org") == REFUSED_INACTIVE
    assert await reason(sub="sub-uit") == REFUSED_INACTIVE
    assert await reason(email="gebonden@example.org") == REFUSED_OTHER_SUBJECT


async def test_an_absent_verified_claim_is_not_a_verified_address(
    db_session, create_person
):
    """Absent is treated like false: only a provider that says so counts.

    A person who changes their own address at the provider gets an
    unverified address; accepting "absent" would reopen that door.
    """
    person = await create_person("collega@example.org")
    assert email_verified_claim({"email": "collega@example.org"}) is None
    match = await match_login(
        db_session, sub=SSO_SUB, email="collega@example.org", email_verified=None
    )
    assert match.person is None and match.refusal == REFUSED_EMAIL_UNVERIFIED
    assert person.oidc_subject is None


async def test_the_address_matches_whatever_its_case(db_session, create_person):
    person = await create_person("Voor.Achternaam@Voorbeeld.example")
    match = await match_login(
        db_session,
        sub=SSO_SUB,
        email=" VOOR.achternaam@voorbeeld.EXAMPLE ",
        email_verified=True,
    )
    assert match.person is person and match.rule == MATCHED_BY_EMAIL
    again = await match_login(
        db_session, sub=SSO_SUB, email="iets@anders.example", email_verified=False
    )
    # Bound by subject: a later change of address at the provider is harmless.
    assert again.person is person and again.rule == MATCHED_BY_SUBJECT


async def test_a_changed_subject_for_a_known_address_binds_nothing(
    db_session, create_person
):
    person = await create_person("collega@example.org", oidc_subject="eerste-sub")
    match = await match_login(
        db_session, sub="tweede-sub", email="collega@example.org", email_verified=True
    )
    assert match.person is None and match.candidate is person
    assert person.oidc_subject == "eerste-sub"


def test_verified_claim_as_boolean_or_text():
    assert email_verified_claim({"email_verified": True}) is True
    assert email_verified_claim({"email_verified": "true"}) is True
    assert email_verified_claim({"email_verified": "false"}) is False
    assert email_verified_claim({"email_verified": False}) is False


def test_a_user_id_is_never_shown_as_a_name():
    # The platform realm overrides preferred_username with the SSO Rijk id.
    assert display_name_from_claims({"preferred_username": SSO_SUB}) == ""
    assert display_name_from_claims({"preferred_username": "a@b.example"}) == ""
    assert display_name_from_claims({"given_name": "Pia", "family_name": "Pen"}) == (
        "Pia Pen"
    )
    assert display_name_from_claims({"name": " Pia Pen ", "given_name": "X"}) == (
        "Pia Pen"
    )


def test_organisation_is_read_nested_and_flat():
    nested = {"organization": {"name": "Voorbeelddienst", "number": "00000001"}}
    flat = {"organization.name": "Voorbeelddienst", "organization.number": 1}
    assert organisation_from_claims(nested) == {
        "name": "Voorbeelddienst",
        "number": "00000001",
    }
    assert organisation_from_claims(flat) == {"name": "Voorbeelddienst", "number": "1"}
    assert organisation_from_claims({"email": "x"}) == {}


# -- the callback, with the provider's answer faked ---------------------------


def _settings(**extra: Any) -> Settings:
    return Settings(
        _env_file=None,
        DEV_NO_AUTH=False,
        OIDC_ISSUER="https://idp.example/realms/x",
        OIDC_CLIENT_ID="grip",
        SESSION_SECRET_KEY="s" * 40,
        FRONTEND_URL="https://grip.example",
        BACKEND_URL="https://grip.example",
        **extra,
    )


def _request(session: dict[str, Any], query: str = "state=abc") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/auth/callback",
        "query_string": query.encode(),
        "headers": [(b"host", b"grip.example")],
        "scheme": "https",
        "server": ("grip.example", 443),
        "client": ("203.0.113.9", 1234),
        "session": session,
    }
    return Request(scope)


class _Provider:
    def __init__(self, answer: Any) -> None:
        self.answer = answer

    async def authorize_access_token(self, _request: Request) -> Any:
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def provider(monkeypatch):
    """Let the callback believe the provider answered with ``answer``."""
    auth_routes._rate_limiter.reset()

    def _install(answer: Any) -> None:
        class _OAuth:
            keycloak = _Provider(answer)

        monkeypatch.setattr(auth_routes, "get_oauth", lambda _settings: _OAuth())

    async def _nothing(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(auth_routes, "revoke_tokens", _nothing)
    monkeypatch.setattr(auth_routes, "get_jwks", _nothing)
    return _install


def _token(**claims: Any) -> dict[str, Any]:
    return {
        "access_token": "a",
        "refresh_token": "r",
        "id_token": "i",
        "userinfo": {"sub": SSO_SUB, **claims},
    }


async def _events(db_session) -> list[StreamEvent]:
    await db_session.flush()
    rows = (await db_session.execute(select(StreamEvent))).scalars().all()
    return [row for row in rows if row.type.startswith("login.")]


async def test_a_login_is_an_event(db_session, create_person, provider):
    person = await create_person("collega@example.org")
    provider(_token(email="Collega@Example.org", email_verified=True, name="Co"))
    session: dict[str, Any] = {}
    response = await auth_routes.callback(_request(session), db_session, _settings())

    assert response.headers["location"] == "https://grip.example"
    assert session["person_id"] == str(person.id)
    (event,) = await _events(db_session)
    assert event.type == "login.succeeded"
    assert event.payload == {"rule": MATCHED_BY_EMAIL}
    assert event.actor_person_id == person.id


async def test_a_refused_login_is_on_record_with_its_reason(
    db_session, create_person, provider
):
    """The first real login must not fail silently."""
    await create_person("collega@example.org")
    provider(_token(email="Collega@Example.org"))  # no email_verified at all
    session: dict[str, Any] = {"login_next": "/opdrachten"}
    response = await auth_routes.callback(_request(session), db_session, _settings())

    assert response.headers["location"].endswith("login_error=geen_toegang")
    assert "person_id" not in session and "access_token" not in session
    (event,) = await _events(db_session)
    assert event.type == "login.refused"
    assert event.payload == {
        "reason": REFUSED_EMAIL_UNVERIFIED,
        "email": "collega@example.org",
    }


async def test_cancelling_at_the_provider_is_not_an_error_page(db_session, provider):
    provider(OAuthError(error="access_denied", description="user cancelled"))
    session: dict[str, Any] = {"x": 1}
    response = await auth_routes.callback(_request(session), db_session, _settings())
    assert response.headers["location"].endswith("login_error=geannuleerd")
    assert session == {}


async def test_an_expired_state_or_unreachable_provider_ends_calmly(
    db_session, provider
):
    for failure in (
        OAuthError(error="mismatching_state", description="CSRF"),
        OAuthError(error="login_required"),
        httpx.ConnectError("no route"),
    ):
        provider(failure)
        session: dict[str, Any] = {"x": 1}
        response = await auth_routes.callback(
            _request(session), db_session, _settings()
        )
        assert response.headers["location"].endswith("login_error=mislukt")
        assert session == {}


# -- diagnostics --------------------------------------------------------------


def test_the_report_gives_shapes_and_never_values():
    userinfo = {
        "sub": SSO_SUB,
        "email": "Pia.Pen@Voorbeeld.example",
        "email_verified": True,
        "name": "Pia Pen",
        "preferred_username": SSO_SUB.lower(),
        "organization": {"name": "Voorbeelddienst", "number": "00000001"},
    }
    first = diagnostics.snapshot(
        id_claims={"iss": "https://idp.example", "auth_time": 1000, "acr": "1"},
        userinfo=userinfo,
        token={"id_token": "SECRET-ID", "access_token": "SECRET-A", "expires_in": 300},
        outcome={"code": "onbekend"},
    )
    second = diagnostics.snapshot(
        id_claims={"auth_time": 1042}, userinfo=userinfo, token={}
    )
    report = diagnostics.render(
        {"first": first, "second": second, "reauth_seconds": 40}
    )
    for secret in ("pietje", "Pia", "Pen", "SECRET-ID", "SECRET-A"):
        assert secret not in report
    assert "email: <7 tekens>@Voorbeeld.example (bevat hoofdletters)" in report
    assert "sub: urn:collab:person:voorbeeld.example:<6 tekens>" in report
    assert "email_verified: true" in report
    assert "Voorbeelddienst" in report and "00000001" in report
    assert "JA: auth_time is 42 seconden nieuwer" in report
    assert "geen persoon met dit e-mailadres" in report


def test_the_report_says_when_the_claim_is_absent_or_nothing_was_new():
    shot = diagnostics.snapshot(
        id_claims={"auth_time": 1000}, userinfo={"sub": "x"}, token={}
    )
    report = diagnostics.render({"first": shot, "second": shot})
    assert "email_verified: ONTBREEKT" in report
    assert "NEE: auth_time is gelijk gebleven" in report
    assert "geen claim over de organisatie" in report
    assert "Nog geen aanmelding gezien" in diagnostics.render(None)


async def test_diagnostics_are_kept_only_when_switched_on(
    db_session, create_person, provider
):
    await create_person("collega@example.org")
    provider(_token(email="collega@example.org", email_verified=True))
    plain: dict[str, Any] = {}
    await auth_routes.callback(_request(plain), db_session, _settings())
    assert diagnostics.SESSION_KEY not in plain

    refused: dict[str, Any] = {}
    provider(_token(sub="ander-sub", email="vreemd@example.org", email_verified=True))
    await auth_routes.callback(
        _request(refused), db_session, _settings(OIDC_DIAGNOSTICS=True)
    )
    kept = refused[diagnostics.SESSION_KEY]["first"]
    assert kept["outcome"] == {"code": REFUSED_UNKNOWN}
    assert "vreemd" not in str(kept)


def test_diagnostics_are_refused_when_deployed():
    with pytest.raises(ValueError, match="OIDC_DIAGNOSTICS"):
        _settings(OIDC_DIAGNOSTICS=True, PUBLIC_HOST="https://grip.example")


async def test_the_diagnostic_page_does_not_exist_by_default(client):
    assert (await client.get("/api/auth/diagnose")).status_code == 404
    assert (await client.get("/api/auth/diagnose/reauth")).status_code == 404


def test_the_login_round_trip_has_a_brake():
    from fastapi import HTTPException

    from grip.core.rate_limit import RateLimiter

    brake = RateLimiter(limit=2, window=60)
    request = _request({})
    brake.check(request)
    brake.check(request)
    with pytest.raises(HTTPException) as refused:
        brake.check(request)
    assert refused.value.status_code == 429
