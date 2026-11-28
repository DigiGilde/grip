"""The FSC bootstrap enters the other examples in the peer registry (ADR 0062)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from grip.access import Action, Resource
from grip.access.decider import (
    MACHINE_FSC_BOOTSTRAP,
    PROPERTY_EXAMPLE_DATA,
    LocalDecider,
    decide,
)
from grip.access.relations import InMemoryRelationSource
from grip.access.types import ResourceKind, Subject
from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.config import get_settings
from grip.federation import signing
from grip.federation.models import Peer
from grip.federation.outway import OutwayClient
from grip.federation.routes import get_outway_client
from grip.models.audit_log import AuditLog

KEY = "sleutel-van-de-bootstrap"
AUTH = {"Authorization": f"Bearer {KEY}"}
PEER = {
    "peer_id": "01800000000000000005",
    "name": "NLDD voorbeeld",
    "organisation_tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre9002",
    "base_uri": "https://grip-nldd.voorbeeld.example/",
    "role": "counterpart",
    "grant_hashes": {"grip-opdrachtverkeer": "$1$4$eerste"},
    "financial_inspection": True,
}


@pytest.fixture
def configure(_test_app):
    def _configure(**update):
        settings = get_settings().model_copy(
            update={"PEER_REGISTRY_KEY": KEY, **update}
        )
        _test_app.dependency_overrides[get_settings] = lambda: settings
        return settings

    return _configure


def _outway(handler) -> OutwayClient:
    settings = get_settings().model_copy(
        update={
            "OUTWAY_URL": "http://outway.test",
            "INSTANCE_MODE": "voorbeeld",
            "EXAMPLE_FSC_GROUP": "grip-voorbeeld",
        }
    )
    return OutwayClient(
        settings, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def test_the_bootstrap_enters_a_peer_and_updates_it(
    client, db_session, configure
):
    configure(INSTANCE_MODE="voorbeeld")
    created = await client.put("/api/peers/registry", json=PEER, headers=AUTH)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["base_uri"] == "https://grip-nldd.voorbeeld.example"
    assert body["role"] == "counterpart"
    assert body["financial_inspection"] is True
    assert body["is_example"] is True and body["is_active"] is True

    # A beheerder switched it off; the bootstrap comes back every hour.
    row = await db_session.scalar(select(Peer).where(Peer.peer_id == PEER["peer_id"]))
    row.is_active = False
    row.financial_inspection = False
    await db_session.flush()

    again = await client.put(
        "/api/peers/registry",
        json={
            **PEER,
            "role": "parent",
            "grant_hashes": {"grip-opdrachtverkeer": "$1$4$tweede"},
        },
        headers=AUTH,
    )
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["role"] == "parent"
    assert body["grant_hashes"] == {"grip-opdrachtverkeer": "$1$4$tweede"}
    assert body["is_active"] is False and body["financial_inspection"] is False
    assert body["version"] == row.version

    audits = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.entity == "peer", AuditLog.entity_id == str(row.id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert [a.new_value["source"] for a in audits] == ["fsc-bootstrap"] * 2


async def test_the_same_call_twice_changes_nothing(client, db_session, configure):
    configure(INSTANCE_MODE="voorbeeld")
    first = (await client.put("/api/peers/registry", json=PEER, headers=AUTH)).json()
    second = await client.put("/api/peers/registry", json=PEER, headers=AUTH)
    assert second.status_code == 200
    assert second.json()["version"] == first["version"]
    count = (
        (await db_session.execute(select(AuditLog).where(AuditLog.entity == "peer")))
        .scalars()
        .all()
    )
    assert len(count) == 1


async def test_on_a_development_instance_the_peer_is_no_example(client, configure):
    configure()
    created = await client.put("/api/peers/registry", json=PEER, headers=AUTH)
    assert created.status_code == 201, created.text
    assert created.json()["is_example"] is False


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer verkeerd"}, {"Authorization": KEY}]
)
async def test_without_the_key_nothing_happens(client, db_session, configure, headers):
    configure(INSTANCE_MODE="voorbeeld")
    response = await client.put("/api/peers/registry", json=PEER, headers=headers)
    assert response.status_code == 403
    assert await db_session.scalar(select(Peer.id)) is None


async def test_without_a_configured_key_the_route_is_closed(
    client, db_session, configure
):
    configure(INSTANCE_MODE="voorbeeld", PEER_REGISTRY_KEY="")
    response = await client.put(
        "/api/peers/registry", json=PEER, headers={"Authorization": "Bearer "}
    )
    assert response.status_code == 403
    assert await db_session.scalar(select(Peer.id)) is None


async def test_an_instance_for_real_work_refuses_the_bootstrap(
    client, db_session, configure
):
    configure(
        DEV_NO_AUTH=False,
        OIDC_ISSUER="https://login.voorbeeld.example/realms/grip",
        PUBLIC_HOST="grip.voorbeeld.example",
    )
    response = await client.put("/api/peers/registry", json=PEER, headers=AUTH)
    assert response.status_code == 403
    assert await db_session.scalar(select(Peer.id)) is None
    test = await client.post(
        "/api/peers/registry/test-connection",
        json={"peer_id": PEER["peer_id"]},
        headers=AUTH,
    )
    assert test.status_code == 403


async def test_a_session_is_no_key(client, create_person, configure):
    configure(INSTANCE_MODE="voorbeeld")
    beheerder = await create_person("beheerder@example.org", functions=["beheerder"])
    client.cookies.set(DEV_PERSON_COOKIE, str(beheerder.id))
    response = await client.put("/api/peers/registry", json=PEER)
    assert response.status_code == 403


async def test_no_csrf_token_is_needed_for_a_key(client, configure):
    configure(INSTANCE_MODE="voorbeeld")
    client.event_hooks["request"] = []
    response = await client.put("/api/peers/registry", json=PEER, headers=AUTH)
    assert response.status_code == 201, response.text


async def test_the_role_is_one_between_instances(client, configure):
    configure(INSTANCE_MODE="voorbeeld")
    for role in ("corpus", "vriend"):
        response = await client.put(
            "/api/peers/registry", json={**PEER, "role": role}, headers=AUTH
        )
        assert response.status_code == 422, response.text


async def test_the_bootstrap_tests_the_connection(
    client, db_session, configure, _test_app
):
    configure(INSTANCE_MODE="voorbeeld")
    await client.put("/api/peers/registry", json=PEER, headers=AUTH)
    jwks = signing.own_jwks(get_settings())
    _test_app.dependency_overrides[get_outway_client] = lambda: _outway(
        lambda _request: httpx.Response(200, json=jwks)
    )
    result = await client.post(
        "/api/peers/registry/test-connection",
        json={"peer_id": PEER["peer_id"]},
        headers=AUTH,
    )
    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True and result.json()["key_count"] == 1

    unknown = await client.post(
        "/api/peers/registry/test-connection",
        json={"peer_id": "01800000000000000077"},
        headers=AUTH,
    )
    assert unknown.status_code == 404


def _instance(example_data: str) -> Resource:
    return Resource(
        ResourceKind.INSTANCE, properties=((PROPERTY_EXAMPLE_DATA, example_data),)
    )


async def test_only_the_bootstrap_registers_and_only_there():
    decider = LocalDecider(InMemoryRelationSource())
    bootstrap = Subject.for_machine(MACHINE_FSC_BOOTSTRAP)
    assert await decide(decider, bootstrap, Action.REGISTER_PEER, _instance("true"))
    refused = await decide(decider, bootstrap, Action.REGISTER_PEER, _instance("false"))
    assert not refused and refused.reason == "not_an_example_instance"
    other = Subject.for_machine("wies")
    assert not await decide(decider, other, Action.REGISTER_PEER, _instance("true"))
    # The key opens nothing else.
    for action in (Action.MANAGE_USERS, Action.READ):
        assert not await decide(decider, bootstrap, action, _instance("true"))
    # A person, even the beheerder, goes through Beheer > Koppelingen.
    beheerder = Subject.for_person(uuid.uuid4(), {"beheerder"})
    assert not await decide(decider, beheerder, Action.REGISTER_PEER, _instance("true"))
    assert not await decide(
        decider,
        Subject.for_peer("01800000000000000001"),
        Action.REGISTER_PEER,
        _instance("true"),
    )
