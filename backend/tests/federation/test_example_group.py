"""Example instances federate only with each other (ADR 0054).

Both directions are tested: what goes out through the outway client and the
outbox, and what comes in at the listener, for pushed messages and for pull
operations.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from grip.core import clock
from grip.core.config import Settings, get_settings
from grip.federation import group
from grip.federation.bridge.settings import get_bridge_settings
from grip.federation.models import FederationOutbox
from grip.federation.outbox import enqueue, send_due
from grip.federation.outway import PeerOutsideGroupError
from grip.federation.peers import find_peer_for_organisation
from tests.federation.conftest import (
    CONTRACTOR_BASE,
    CONTRACTOR_PEER_ID,
    as_peer,
    code_example,
    example,
)

GROUP = "grip-voorbeeld"


def token(claims: dict[str, object]) -> str:
    """An FSC access token as the inway passes it on; the signature is not read."""

    def part(value: dict[str, object]) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"Bearer {part({'alg': 'RS512'})}.{part(claims)}.c2lnbmF0dXVy"


def in_group(peer_id: str, group_id: str = GROUP) -> dict[str, str]:
    authorization = token({"gid": group_id})
    return {**as_peer(peer_id), group.FSC_AUTHORIZATION_HEADER: authorization}


def as_example(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"INSTANCE_MODE": "voorbeeld", "EXAMPLE_FSC_GROUP": GROUP}
    )


@pytest.fixture
def example_settings(fed_settings: Settings) -> Settings:
    return as_example(fed_settings)


@pytest.fixture
def listener_as_example(fed_app, example_settings):
    fed_app.dependency_overrides[get_settings] = lambda: example_settings
    return example_settings


# -- the token the inway passes on ---------------------------------------------


def test_the_group_is_read_from_the_access_token():
    assert group.token_group(token({"gid": GROUP})) == GROUP
    assert group.token_group(token({"gid": GROUP}).removeprefix("Bearer ")) == GROUP
    assert group.token_group(token({"sub": "x"})) is None
    assert group.token_group(token({"gid": 7})) is None
    assert group.token_group("") is None
    assert group.token_group("Bearer niet-een-token") is None
    assert group.token_group("Bearer a.!!!.c") is None


# -- calls in -------------------------------------------------------------------


async def test_real_work_refuses_an_example_peer(fed_client, make_peer):
    await make_peer(is_example=True)
    for method, path, body in (
        ("POST", "/v1/offertes", example("quote")),
        ("GET", "/v1/jwks", None),
        ("GET", "/v1/kostenposten", None),
    ):
        response = await fed_client.request(
            method, path, json=body, headers=as_peer(CONTRACTOR_PEER_ID)
        )
        assert response.status_code == 403, (path, response.text)


async def test_an_example_refuses_a_peer_that_is_not_one(
    fed_client, make_peer, listener_as_example
):
    await make_peer()
    response = await fed_client.get("/v1/jwks", headers=in_group(CONTRACTOR_PEER_ID))
    assert response.status_code == 403


async def test_an_example_accepts_an_example_peer_through_its_group(
    fed_client, make_peer, listener_as_example
):
    await make_peer(is_example=True)
    accepted = await fed_client.get("/v1/jwks", headers=in_group(CONTRACTOR_PEER_ID))
    assert accepted.status_code == 200, accepted.text
    pushed = await fed_client.post(
        "/v1/offertes", json=example("quote"), headers=in_group(CONTRACTOR_PEER_ID)
    )
    assert pushed.status_code == 201, pushed.text


async def test_an_example_refuses_a_call_from_another_group(
    fed_client, make_peer, listener_as_example
):
    await make_peer(is_example=True)
    other = await fed_client.get(
        "/v1/jwks", headers=in_group(CONTRACTOR_PEER_ID, "fsc-default")
    )
    without = await fed_client.get("/v1/jwks", headers=as_peer(CONTRACTOR_PEER_ID))
    unknown = await fed_client.get("/v1/jwks", headers=in_group("99999999999999999999"))
    # The same answer as for an unknown peer: nothing is revealed.
    assert other.status_code == without.status_code == 403
    assert other.json() == unknown.json()


# -- calls out ------------------------------------------------------------------


async def test_real_work_sends_nothing_to_an_example(
    make_peer, fake_outway, fed_settings
):
    peer = await make_peer(is_example=True)
    outway = fake_outway.client(fed_settings)
    with pytest.raises(PeerOutsideGroupError):
        await outway.request(peer, "grip-opdrachtverkeer", "GET", "/v1/jwks")
    assert fake_outway.requests == []


async def test_an_example_sends_only_to_examples(make_peer, fake_outway, fed_settings):
    settings = as_example(fed_settings)
    real = await make_peer()
    other_example = await make_peer(
        "00000000000000000003", base_uri="https://grip.ander.example", is_example=True
    )
    fake_outway.handler = lambda _request: httpx.Response(200, json={"keys": []})
    outway = fake_outway.client(settings)
    with pytest.raises(PeerOutsideGroupError):
        await outway.request(real, "grip-opdrachtverkeer", "GET", "/v1/jwks")
    assert fake_outway.requests == []
    response = await outway.request(
        other_example, "grip-opdrachtverkeer", "GET", "/v1/jwks"
    )
    assert response.status_code == 200
    assert len(fake_outway.requests) == 1


async def test_the_outbox_does_not_deliver_across_the_boundary(
    db_session, make_peer, fake_outway, fed_settings
):
    peer = await make_peer(is_example=True)
    await enqueue(db_session, peer, "sendQuote", code_example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(201, json={})
    stats = await send_due(db_session, fake_outway.client(fed_settings), fed_settings)
    assert (stats.sent, stats.retried) == (0, 1)
    assert fake_outway.requests == []
    row = (await db_session.execute(select(FederationOutbox))).scalar_one()
    assert row.status == "pending"
    assert row.last_error.startswith("configuration: ")

    # Between two examples the same message goes out.
    settings = as_example(fed_settings)
    row.next_attempt_at = datetime.now(UTC)
    stats = await send_due(db_session, fake_outway.client(settings), settings)
    assert stats.sent == 1 and len(fake_outway.requests) == 1


async def test_the_outbox_of_an_example_waits_while_the_examples_go_back(
    db_session, make_peer, fake_outway, fed_settings
):
    settings = as_example(fed_settings).model_copy(
        update={"EXAMPLE_RESET_HOUR": "3", "INSTANCE_TIMEZONE": "Europe/Amsterdam"}
    )
    peer = await make_peer(is_example=True)
    await enqueue(db_session, peer, "sendQuote", code_example("quote"))
    fake_outway.handler = lambda _request: httpx.Response(201, json={})
    with clock.at(datetime(2026, 3, 10, 2, 5, tzinfo=UTC)):  # 03:05 local
        quiet = await send_due(db_session, fake_outway.client(settings), settings)
    assert quiet.total == 0 and fake_outway.requests == []


async def test_the_other_side_is_as_good_as_unknown_to_the_domain(
    db_session, make_peer
):
    await make_peer(is_example=True)
    reference = {"instance_uri": CONTRACTOR_BASE}
    assert await find_peer_for_organisation(db_session, reference) is None


# -- after the nightly reset ------------------------------------------------------

GUILD_BASE = "https://digigilde.voorbeeld.example"
GUILD_PEER_ID = "01800000000000000001"


@pytest.fixture
def programma_example(monkeypatch):
    """The process acts as the example instance with the programma dataset."""
    for name, value in {
        "INSTANCE_MODE": "voorbeeld",
        "EXAMPLE_FSC_GROUP": GROUP,
        "SEED_DATASET": "programma",
        "INSTANCE_NAME": "Voorbeeldprogramma",
        "INSTANCE_KEY": "programma",
        "INSTANCE_TOOI_URI": "https://identifier.overheid.nl/tooi/id/ministerie/mnre9001",
        "INSTANCE_BASE_URI": "https://programma.voorbeeld.example",
        "EXAMPLE_INSTANCE_URIS": f"digigilde={GUILD_BASE}",
        "EXAMPLE_RESET_HOUR": "",
        "FEDERATION_INBOUND_ENABLED": "1",
        "FEDERATION_OUTBOUND_ENABLED": "1",
        "OUTWAY_URL": "http://outway.test",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    get_bridge_settings.cache_clear()
    yield get_settings()
    monkeypatch.undo()
    get_settings.cache_clear()
    get_bridge_settings.cache_clear()
    # Cached again under the environment of the run, as the rest expects.
    get_settings()


async def test_after_the_reset_the_waiting_request_goes_out_again(
    db_session, make_peer, fake_outway, programma_example
):
    from grip.core import example as example_mode
    from grip.federation.bridge import register_bridge
    from grip.services import events

    settings = programma_example
    events.clear_handlers()
    register_bridge()
    try:
        assert await example_mode.prepare(db_session, settings) == "seeded"
        await make_peer(
            GUILD_PEER_ID,
            base_uri=GUILD_BASE,
            organisation_tooi_uri="https://identifier.overheid.nl/tooi/id/oorg/oorg99002",
            is_example=True,
        )
        fake_outway.handler = lambda _request: httpx.Response(201, json={})
        outway = fake_outway.client(settings)
        await send_due(db_session, outway, settings)
        before = [r.url.path for r in fake_outway.requests]

        await example_mode.reset(db_session, settings)
        fake_outway.requests.clear()
        stats = await send_due(db_session, outway, settings)
    finally:
        events.clear_handlers()

    assert before and stats.sent == len(before)
    rows = (await db_session.execute(select(FederationOutbox))).scalars().all()
    assert {row.operation for row in rows} == {"requestCostItem"}
    assert all(row.peer.peer_id == GUILD_PEER_ID for row in rows)
    assert all(row.status == "sent" for row in rows)
