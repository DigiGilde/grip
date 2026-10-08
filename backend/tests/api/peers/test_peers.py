"""Peer management and deciding on a received quote, through the API."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.config import get_settings
from grip.federation import registry, signing, terms
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.events import register_event_handlers
from grip.federation.models import FederationOutbox, Peer
from grip.federation.outway import OutwayClient
from grip.federation.routes import get_outway_client
from grip.models.audit_log import AuditLog
from grip.models.quote import QuoteAcceptance
from grip.services import assignments, quotes, rates
from grip.services import events as domain_events

CONTRACTOR = {
    "tooi_uri": "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
    "name": "Voorbeeldgilde",
    "unit_key": "voorbeeldgilde",
    "instance_uri": "https://grip.opdrachtnemer.example",
}
PEER = {
    "peer_id": "00000000000000000020",
    "name": "Voorbeeldgilde",
    "organisation_tooi_uri": CONTRACTOR["tooi_uri"],
    "base_uri": "https://grip.opdrachtnemer.example/",
    "role": "counterpart",
    "grant_hashes": {"grip-opdrachtverkeer": "$1$4$grant", "corpus-context": " "},
}


@pytest.fixture(autouse=True)
def _clean():
    registry.clear_registries()
    domain_events.clear_handlers()
    yield
    registry.clear_registries()
    domain_events.clear_handlers()


@pytest.fixture
def act_as(client):
    def _as(person):
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))

    return _as


@pytest.fixture
async def beheerder(create_person):
    return await create_person("beheerder@example.org", functions=["beheerder"])


async def test_only_the_beheerder_manages_peers(client, create_person, act_as):
    planner = await create_person("planner@example.org", functions=["planner"])
    act_as(planner)
    assert (await client.get("/api/peers")).status_code == 403
    assert (await client.post("/api/peers", json=PEER)).status_code == 403


async def test_create_list_update_and_deactivate(client, db_session, beheerder, act_as):
    act_as(beheerder)
    created = await client.post("/api/peers", json=PEER)
    assert created.status_code == 201, created.text
    peer = created.json()
    assert peer["base_uri"] == "https://grip.opdrachtnemer.example"
    assert peer["grant_hashes"] == {"grip-opdrachtverkeer": "$1$4$grant"}
    assert peer["financial_inspection"] is False and peer["key_count"] == 0

    listed = (await client.get("/api/peers")).json()
    assert [item["peer_id"] for item in listed["items"]] == [PEER["peer_id"]]
    assert listed["services"] == ["grip-opdrachtverkeer", "corpus-context"]

    again = await client.post("/api/peers", json=PEER)
    assert again.status_code in (400, 409, 422)

    changed = await client.patch(
        f"/api/peers/{peer['id']}",
        json={"financial_inspection": True, "is_active": False},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["financial_inspection"] is True
    assert changed.json()["is_active"] is False
    assert changed.json()["name"] == PEER["name"], "what was not sent stays"

    audit = (
        (await db_session.execute(select(AuditLog).where(AuditLog.entity == "peer")))
        .scalars()
        .all()
    )
    assert {row.action for row in audit} == {"create", "update"}

    assert (await client.get(f"/api/peers/{peer['id']}")).status_code == 200
    missing = await client.get("/api/peers/00000000-0000-4000-8000-000000000000")
    assert missing.status_code == 404


async def test_invalid_peer_is_refused(client, beheerder, act_as):
    act_as(beheerder)
    for change in ({"role": "vriend"}, {"base_uri": "geen-uri"}, {"peer_id": ""}):
        response = await client.post("/api/peers", json={**PEER, **change})
        assert response.status_code in (400, 422), response.text


def _outway(handler) -> OutwayClient:
    settings = get_settings().model_copy(update={"OUTWAY_URL": "http://outway.test"})
    return OutwayClient(
        settings, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def test_connection_test_fetches_and_keeps_the_keys(
    client, db_session, beheerder, act_as, _test_app
):
    act_as(beheerder)
    peer = (await client.post("/api/peers", json=PEER)).json()
    jwks = signing.own_jwks(get_settings())
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=jwks)

    _test_app.dependency_overrides[get_outway_client] = lambda: _outway(answer)
    result = await client.post(f"/api/peers/{peer['id']}/test-connection")
    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True and result.json()["key_count"] == 1
    assert seen[0].url.path == "/v1/jwks"
    assert seen[0].headers["Fsc-Grant-Hash"] == "$1$4$grant"
    row = await db_session.scalar(select(Peer).where(Peer.peer_id == PEER["peer_id"]))
    assert row.jwks == jwks and row.jwks_fetched_at is not None


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (403, {"title": "Geen toegang"}, "status 403"),
        (200, {"geen": "sleutels"}, "geen geldige sleutelset"),
    ],
)
async def test_connection_test_says_what_went_wrong(
    client, beheerder, act_as, _test_app, status, body, expected
):
    act_as(beheerder)
    peer = (await client.post("/api/peers", json=PEER)).json()
    _test_app.dependency_overrides[get_outway_client] = lambda: _outway(
        lambda _request: httpx.Response(status, json=body)
    )
    result = (await client.post(f"/api/peers/{peer['id']}/test-connection")).json()
    assert result["ok"] is False and expected in result["detail"]


async def test_connection_test_without_grant_or_outway(
    client, beheerder, act_as, _test_app
):
    act_as(beheerder)
    peer = (await client.post("/api/peers", json={**PEER, "grant_hashes": {}})).json()
    _test_app.dependency_overrides[get_outway_client] = lambda: _outway(
        lambda _request: httpx.Response(200, json={})
    )
    result = (await client.post(f"/api/peers/{peer['id']}/test-connection")).json()
    assert result["ok"] is False and "grant hash" in result["detail"]

    _test_app.dependency_overrides[get_outway_client] = lambda: OutwayClient(
        get_settings().model_copy(update={"OUTWAY_URL": ""})
    )
    result = (await client.post(f"/api/peers/{peer['id']}/test-connection")).json()
    assert result["ok"] is False and "outway" in result["detail"]


# --- a received quote ------------------------------------------------------


@pytest.fixture
async def received_quote(db_session, beheerder, monkeypatch):
    """A quote of a contractor, on an assignment this instance is client of."""
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "INSTANCE_TOOI_URI",
        "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
    )
    await rates.create_rate_card(db_session, 2026, actor=beheerder)
    await rates.set_rate_band(db_session, 2026, "D", 1800000, actor=beheerder)
    await rates.set_rate_card_status(db_session, 2026, "active", actor=beheerder)
    own = await own_organisation(db_session)
    contractor = await from_reference(db_session, CONTRACTOR)
    assignment = await assignments.create_assignment(
        db_session,
        name="Opdracht Alfa",
        actor=None,
        client_organisation_id=own.id,
        contractor_organisation_id=contractor.id,
        uri=f"{settings.INSTANCE_BASE_URI}/id/opdracht/3f2a8c54-6d1b-4f0e-9a77-1c2b3d4e5f60",
    )
    await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
        rate_category="D",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
        actor=None,
    )
    # The quote came from the contractor's instance: the assignment is shared
    # with it, which is why a decision goes back there.
    assignments.share_with_instance(assignment, CONTRACTOR["instance_uri"])
    snapshot = await quotes.build_snapshot(db_session, assignment)
    quote = await quotes.receive_quote(
        db_session,
        assignment.id,
        quote_id=uuid.uuid4(),
        uri="https://grip.opdrachtnemer.example/id/offerte/x",
        snapshot=snapshot,
        claimed_hash=quotes.snapshot_hash(snapshot),
        issued_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )
    db_session.add(
        Peer(
            peer_id=PEER["peer_id"],
            name="Voorbeeldgilde",
            base_uri=CONTRACTOR["instance_uri"],
            role="counterpart",
            grant_hashes={"grip-opdrachtverkeer": "$1$4$grant"},
        )
    )
    await db_session.flush()
    return quote


async def test_tekenbevoegde_accepts_and_the_signed_message_is_queued(
    client, db_session, create_person, act_as, received_quote
):
    register_event_handlers()
    signer = await create_person(
        "tekenbevoegde@example.org",
        name="Tekenbevoegde Voorbeeld",
        functions=["tekenbevoegde"],
    )
    act_as(signer)
    response = await client.post(
        f"/api/received-quotes/{received_quote.id}/acceptance",
        json={"signer_function": "Directeur"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision"] == "accepted" and body["sent_to_contractor"] is True

    acceptance = await db_session.scalar(
        select(QuoteAcceptance).where(QuoteAcceptance.quote_id == received_quote.id)
    )
    assert (
        acceptance.form == "own_instance" and acceptance.signer_person_id == signer.id
    )
    (queued,) = (await db_session.execute(select(FederationOutbox))).scalars().all()
    assert queued.operation == "sendAcceptance"
    assert queued.path == f"/v1/offertes/{received_quote.id}/akkoorden"
    message = queued.payload
    # The queued message is in contract terms, carries the one hash of the
    # quote, and its signature covers exactly what is sent.
    assert message[terms.term("quote_hash")] == received_quote.snapshot_hash
    assert message[terms.term("signer")]["functie"] == "Directeur"
    signing.verify_acceptance(message, signing.own_jwks(get_settings()))

    again = await client.post(
        f"/api/received-quotes/{received_quote.id}/acceptance", json={}
    )
    assert again.status_code in (400, 409, 422), "a decided quote stays decided"


async def test_rejection_goes_to_the_contractor_with_the_reason(
    client, db_session, create_person, act_as, received_quote
):
    register_event_handlers()
    signer = await create_person("t@example.org", functions=["tekenbevoegde"])
    act_as(signer)
    response = await client.post(
        f"/api/received-quotes/{received_quote.id}/rejection",
        json={"reason": "Past niet in het budget."},
    )
    assert response.status_code == 201, response.text
    (queued,) = (await db_session.execute(select(FederationOutbox))).scalars().all()
    assert queued.operation == "sendRejection"
    assert queued.payload[terms.term("reason")] == "Past niet in het budget."


async def test_someone_without_the_function_cannot_decide(
    client, create_person, act_as, received_quote
):
    planner = await create_person("planner@example.org", functions=["planner"])
    act_as(planner)
    response = await client.post(
        f"/api/received-quotes/{received_quote.id}/acceptance", json={}
    )
    assert response.status_code == 404, "as if the quote is not there"
    missing = await client.post(
        "/api/received-quotes/00000000-0000-4000-8000-000000000000/acceptance",
        json={},
    )
    assert missing.status_code == 404
