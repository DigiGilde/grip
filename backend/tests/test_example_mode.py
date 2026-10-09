"""An example instance: the gates between example data and real work."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from starlette.requests import Request

from grip.api.routes import auth as auth_routes
from grip.core import example
from grip.core.auth import DEV_PERSON_COOKIE, resolve_person
from grip.core.config import Settings
from grip.events import context as event_context
from grip.models.instance_setting import InstanceSetting
from grip.models.person import Person
from grip.models.stream_event import StreamEvent
from grip.schema.auth import ExamplePersonChoice


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("DEV_NO_AUTH", "OIDC_ISSUER", "PUBLIC_HOST", "INSTANCE_MODE"):
        monkeypatch.delenv(key, raising=False)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _example(**overrides) -> Settings:
    return _settings(
        OIDC_ISSUER="https://idp.example/realms/x",
        SESSION_SECRET_KEY="s" * 40,
        PUBLIC_HOST="https://grip.example",
        INSTANCE_MODE="voorbeeld",
        **overrides,
    )


def _real() -> Settings:
    return _settings(
        OIDC_ISSUER="https://idp.example/realms/x",
        SESSION_SECRET_KEY="s" * 40,
        PUBLIC_HOST="https://grip.example",
    )


def test_an_unknown_mode_is_refused() -> None:
    with pytest.raises(ValueError, match="INSTANCE_MODE"):
        _settings(DEV_NO_AUTH=True, INSTANCE_MODE="demo")


@pytest.mark.parametrize(
    "linked",
    [
        {"FEDERATION_OUTBOUND_ENABLED": True},
        {"FEDERATION_INBOUND_ENABLED": True},
        {"WIES_BASE_URL": "https://wies.example"},
        {"GRIP_EXPORT_KEY": "k"},
        {"EVENTS_FEED_KEY": "k"},
        {"BOOTSTRAP_BEHEERDER_EMAILS": "iemand@voorbeeld.example"},
    ],
)
def test_an_example_instance_talks_to_no_other_system(linked) -> None:
    with pytest.raises(ValueError, match="voorbeeldinstantie"):
        _example(**linked)


def test_an_example_instance_never_mails_notifies_or_carries_the_logo() -> None:
    s = _example(
        SMTP_HOST="relay.example",
        SMTP_FROM="x@voorbeeld.example",
        PUSH_VAPID_PRIVATE_KEY="k" * 43,
        LETTERHEAD_LOGO_PATH="/app/huisstijl/rijkslogo.svg",
        DOCUMENT_FONT_DIR="/app/huisstijl/fonts",
    )
    assert s.SMTP_HOST == "" and s.PUSH_VAPID_PRIVATE_KEY == ""
    assert s.LETTERHEAD_LOGO_PATH == "" and s.DOCUMENT_FONT_DIR == ""

    from grip.services.quote_document import letterhead_from_settings

    head = letterhead_from_settings(s)
    assert head.example is True and head.ribbon_data_uri is None


def test_the_development_provider_stays_refused_when_deployed() -> None:
    with pytest.raises(ValueError, match="claude_cli"):
        _example(LLM_PROVIDER="claude_cli")


def test_who_may_visit() -> None:
    s = _example(EXAMPLE_VISITORS="voorbeeld.example, iemand@elders.example")
    assert example.visitor_allowed("Jan@Voorbeeld.example", s)
    assert example.visitor_allowed("iemand@elders.example", s)
    assert not example.visitor_allowed("ander@elders.example", s)
    assert not example.visitor_allowed("jan@sub.voorbeeld.example", s)
    assert not example.visitor_allowed("", s)
    # Nobody until the list is set.
    assert not example.visitor_allowed("jan@voorbeeld.example", _example())


async def test_real_work_starts_on_an_empty_database_and_leaves_it_empty(
    db_session,
) -> None:
    assert await example.prepare(db_session, _real()) == "normal"
    assert await example.marker(db_session) is None


async def test_real_work_refuses_a_database_that_was_an_example(db_session) -> None:
    db_session.add(InstanceSetting(key=example.MARKER_KEY, value={"seeded_at": "x"}))
    await db_session.flush()
    with pytest.raises(example.ExampleModeError, match="echt werk"):
        await example.prepare(db_session, _real())


async def test_an_example_refuses_a_database_with_people(db_session) -> None:
    db_session.add(Person(name="Iemand", email="iemand@voorbeeld.example"))
    await db_session.flush()
    with pytest.raises(example.ExampleModeError, match="lege database"):
        await example.prepare(db_session, _example())


async def test_an_example_fills_itself_once(db_session) -> None:
    settings = _example()
    assert await example.prepare(db_session, settings) == "seeded"
    people = (await db_session.execute(select(Person))).scalars().all()
    assert len(people) > 5
    assert await example.marker(db_session) is not None
    assert await example.prepare(db_session, settings) == "kept"
    assert await example.default_person(db_session) is not None


async def test_an_example_has_no_stand_in_of_the_developer(db_session) -> None:
    from grip.core.bootstrap import DEV_BEHEERDER_EMAIL

    await example.prepare(db_session, _example())

    emails = (await db_session.execute(select(Person.email))).scalars().all()
    assert emails
    assert DEV_BEHEERDER_EMAIL not in emails
    # A visitor still comes in as a beheerder of the example.
    assert await example.default_person(db_session) is not None


async def test_reset_only_in_an_example_instance(db_session) -> None:
    with pytest.raises(example.ExampleModeError):
        await example.reset(db_session, _real())
    with pytest.raises(example.ExampleModeError, match="markering"):
        await example.reset(db_session, _example())


def test_the_seed_still_refuses_a_deployed_instance_for_real_work() -> None:
    from grip.dev.seed import SeedRefusedError, ensure_local_instance

    with pytest.raises(SeedRefusedError):
        ensure_local_instance(_real())
    ensure_local_instance(_example())
    ensure_local_instance(_settings(DEV_NO_AUTH=True))


# -- a visitor: a real login, looking as an example person --------------------


class _Provider:
    def __init__(self, answer: Any) -> None:
        self.answer = answer

    async def authorize_access_token(self, _request: Request) -> Any:
        return self.answer


@pytest.fixture
def provider(monkeypatch):
    """Let the callback believe the identity provider answered with these claims."""
    auth_routes._rate_limiter.reset()

    def _install(**claims: Any) -> None:
        token = {
            "access_token": "a",
            "refresh_token": "r",
            "id_token": "i",
            "userinfo": {"sub": "urn:collab:person:voorbeeld.example:x", **claims},
        }

        class _OAuth:
            keycloak = _Provider(token)

        monkeypatch.setattr(auth_routes, "get_oauth", lambda _settings: _OAuth())

    async def _nothing(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def _valid(*_args: Any, **_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(auth_routes, "revoke_tokens", _nothing)
    monkeypatch.setattr(auth_routes, "get_jwks", _nothing)
    monkeypatch.setattr("grip.core.auth.validate_session_token", _valid)
    return _install


def _request(session: dict[str, Any], cookie: str = "") -> Request:
    headers = [(b"host", b"grip.example")]
    if cookie:
        headers.append((b"cookie", cookie.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/callback",
            "query_string": b"state=abc",
            "headers": headers,
            "scheme": "https",
            "server": ("grip.example", 443),
            "client": ("203.0.113.9", 1234),
            "session": session,
        }
    )


async def _login_events(db_session) -> list[StreamEvent]:
    await db_session.flush()
    rows = (await db_session.execute(select(StreamEvent))).scalars().all()
    return [row for row in rows if row.type.startswith("login.")]


async def test_a_listed_visitor_comes_in_as_an_example_person(db_session, provider):
    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    await example.prepare(db_session, settings)
    provider(email="Bezoeker@Voorbeeld.example", email_verified=True, name="Be Zoeker")
    session: dict[str, Any] = {}
    response = await auth_routes.callback(_request(session), db_session, settings)

    assert response.headers["location"] == "https://grip.example"
    default = await example.default_person(db_session)
    assert session["person_id"] == str(default.id)
    assert session[example.VISITOR_SESSION_KEY] == {
        "email": "bezoeker@voorbeeld.example",
        "name": "Be Zoeker",
    }
    # No person record was made for the visitor.
    people = (await db_session.execute(select(Person))).scalars().all()
    assert all(p.email != "bezoeker@voorbeeld.example" for p in people)
    (event,) = await _login_events(db_session)
    assert event.type == "login.visited"
    assert event.payload == {
        "email": "bezoeker@voorbeeld.example",
        "as": str(default.id),
    }

    status = await auth_routes.auth_status(_request(session), db_session, settings)
    assert status.authenticated and status.example
    assert status.example_visitor == "Be Zoeker"
    assert status.person.id == default.id


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "iemand@elders.example", "email_verified": True},
        # On the list, but the provider does not vouch for the address.
        {"email": "bezoeker@voorbeeld.example", "email_verified": False},
        {"email": "bezoeker@voorbeeld.example"},
    ],
)
async def test_anyone_else_is_refused(db_session, provider, claims):
    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    await example.prepare(db_session, settings)
    provider(**claims)
    session: dict[str, Any] = {}
    response = await auth_routes.callback(_request(session), db_session, settings)
    assert response.headers["location"].endswith("login_error=geen_toegang")
    assert session == {}
    (event,) = await _login_events(db_session)
    assert event.type == "login.refused"


async def test_the_list_means_nothing_outside_an_example_instance(db_session, provider):
    settings = _settings(
        OIDC_ISSUER="https://idp.example/realms/x",
        SESSION_SECRET_KEY="s" * 40,
        PUBLIC_HOST="https://grip.example",
        EXAMPLE_VISITORS="voorbeeld.example",
    )
    provider(email="bezoeker@voorbeeld.example", email_verified=True)
    session: dict[str, Any] = {}
    response = await auth_routes.callback(_request(session), db_session, settings)
    assert response.headers["location"].endswith("login_error=geen_toegang")
    assert session == {}


async def _visitor_session(db_session, settings) -> dict[str, Any]:
    await example.prepare(db_session, settings)
    default = await example.default_person(db_session)
    return {
        "access_token": "a",
        "person_id": str(default.id),
        example.VISITOR_SESSION_KEY: {
            "email": "bezoeker@voorbeeld.example",
            "name": "Be Zoeker",
        },
    }


async def test_a_visitor_chooses_whom_to_look_as(db_session, provider):
    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    session = await _visitor_session(db_session, settings)
    request = _request(session)

    listed = await auth_routes.example_persons(request, None, db_session, settings)
    assert len(listed) > 5
    other = next(p for p in listed if str(p.id) != session["person_id"])
    status = await auth_routes.choose_example_person(
        ExamplePersonChoice(person_id=other.id), request, None, db_session, settings
    )
    assert session["person_id"] == str(other.id)
    assert status.person.id == other.id and status.example_visitor == "Be Zoeker"
    (event,) = await _login_events(db_session)
    assert event.type == "login.switched"
    assert event.payload == {"email": "bezoeker@voorbeeld.example", "as": str(other.id)}
    # Recorded as done by the example person, through the real login.
    assert event.actor_person_id is None or event.actor_ref


async def test_what_a_visitor_does_carries_both_identities(db_session, provider):
    from grip.access.deps import get_subject
    from grip.core.audit import UPDATE, record_audit

    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    session = await _visitor_session(db_session, settings)
    with event_context.scope():
        person = await resolve_person(_request(session), db_session, settings)
        await get_subject(person, db_session)
        record_audit(
            db_session,
            actor=person,
            action=UPDATE,
            entity="person",
            entity_id=person.id,
            new_value={"name": person.name},
        )
        await db_session.flush()
    rows = (await db_session.execute(select(StreamEvent))).scalars().all()
    event = next(row for row in rows if row.type == "person.updated")
    assert event.actor_person_id == person.id
    assert event.actor_ref == "bezoeker:bezoeker@voorbeeld.example"


async def test_only_a_visitor_of_an_example_reaches_the_choice(db_session, provider):
    from fastapi import HTTPException

    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    session = await _visitor_session(db_session, settings)
    # An ordinary session in an example instance.
    plain = {k: v for k, v in session.items() if k != example.VISITOR_SESSION_KEY}
    with pytest.raises(HTTPException) as refused:
        await auth_routes.example_persons(_request(plain), None, db_session, settings)
    assert refused.value.status_code == 404
    # A visitor's session on an instance for real work is no session at all.
    with pytest.raises(HTTPException) as refused:
        await auth_routes.example_persons(_request(session), None, db_session, _real())
    assert refused.value.status_code == 404
    assert await resolve_person(_request(dict(session)), db_session, _real()) is None


@pytest.mark.parametrize("make", [_example, _real])
async def test_the_development_cookie_does_nothing_when_deployed(
    db_session, create_person, make
):
    person = await create_person("a@example.org", functions=["beheerder"])
    request = _request({}, cookie=f"{DEV_PERSON_COOKIE}={person.id}")
    assert await resolve_person(request, db_session, make()) is None


async def test_reset_brings_back_the_starting_state(db_session):
    settings = _example()
    await example.prepare(db_session, settings)
    before = len((await db_session.execute(select(Person))).scalars().all())
    db_session.add(Person(name="Toegevoegd", email="toegevoegd@voorbeeld.example"))
    await db_session.flush()
    await example.reset(db_session, settings)
    people = (await db_session.execute(select(Person))).scalars().all()
    assert len(people) == before
    assert all(p.name != "Toegevoegd" for p in people)
    assert (await example.marker(db_session))["reset"] is True


def test_when_the_nightly_reset_runs():
    from datetime import UTC, datetime

    from grip.core import clock

    settings = _example(EXAMPLE_RESET_HOUR="3", INSTANCE_TIMEZONE="Europe/Amsterdam")
    with clock.at(datetime(2026, 3, 10, 2, 30, tzinfo=UTC)):  # 03:30 local
        assert example.reset_due(None, settings)
        assert not example.reset_due(datetime(2026, 3, 10, 2, 5, tzinfo=UTC), settings)
        assert example.reset_due(datetime(2026, 3, 9, 2, 5, tzinfo=UTC), settings)
        assert not example.reset_due(None, _example(EXAMPLE_RESET_HOUR=""))
        assert not example.reset_due(None, _real())
    with clock.at(datetime(2026, 3, 10, 12, 0, tzinfo=UTC)):
        assert not example.reset_due(None, settings)


# -- what an attacker with a visit would try -----------------------------------


async def test_an_example_person_with_the_visitors_address_is_still_a_visitor(
    db_session, provider
):
    # A visitor acting as the beheerder can give an example person their own
    # address. The next login is a visit all the same, with both identities.
    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    await example.prepare(db_session, settings)
    default = await example.default_person(db_session)
    default.email = "bezoeker@voorbeeld.example"
    await db_session.flush()
    provider(email="bezoeker@voorbeeld.example", email_verified=True, name="Be Zoeker")
    session: dict[str, Any] = {}
    await auth_routes.callback(_request(session), db_session, settings)
    assert session[example.VISITOR_SESSION_KEY]["email"] == "bezoeker@voorbeeld.example"

    # Without the list the same address gets nothing.
    session = {}
    closed = _example(EXAMPLE_VISITORS="elders.example")
    response = await auth_routes.callback(_request(session), db_session, closed)
    assert response.headers["location"].endswith("login_error=geen_toegang")
    assert session == {}


async def test_a_visitor_taken_off_the_list_loses_the_session(db_session, provider):
    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    session = await _visitor_session(db_session, settings)
    assert await resolve_person(_request(session), db_session, settings) is not None
    narrowed = _example(EXAMPLE_VISITORS="elders.example")
    assert await resolve_person(_request(session), db_session, narrowed) is None
    assert session == {}


async def test_an_example_instance_has_no_session_without_a_visitor(
    db_session, provider
):
    settings = _example(EXAMPLE_VISITORS="voorbeeld.example")
    session = await _visitor_session(db_session, settings)
    plain = {k: v for k, v in session.items() if k != example.VISITOR_SESSION_KEY}
    assert await resolve_person(_request(plain), db_session, settings) is None


def test_an_example_instance_has_no_passkeys() -> None:
    from grip.services import passkeys

    keys = {"PASSKEY_RP_ID": "grip.example", "PASSKEY_ORIGIN": "https://grip.example"}
    assert not passkeys.configured(_example(**keys))
    assert not passkeys.login_enabled(_example(**keys))
    assert passkeys.configured(
        _settings(
            OIDC_ISSUER="https://idp.example/realms/x",
            SESSION_SECRET_KEY="s" * 40,
            PUBLIC_HOST="https://grip.example",
            **keys,
        )
    )
