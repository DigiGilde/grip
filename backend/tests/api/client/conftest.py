"""Fixtures for the client side: requests, received quotes, nodes, inspection.

Everything is fictional. This instance is the client "Voorbeelddirectie";
the contractor "Voorbeeldgilde" and the corpus are peers that a stand-in
outway answers for.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.config import get_settings
from grip.federation import registry
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.contract_loader import CONTRACT_DIR
from grip.federation.models import Peer
from grip.federation.outway import OutwayClient
from grip.federation.routes import get_outway_client
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.quote import Quote
from grip.services import assignments, quotes, rates
from grip.services import events as domain_events

OWN_TOOI = "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000"
CONTRACTOR = {
    "tooi_uri": "https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
    "name": "Voorbeeldgilde",
    "instance_uri": "https://grip.opdrachtnemer.example",
}
CONTRACTOR_GRANT = "$1$4$naar-opdrachtnemer"
CORPUS_BASE = "https://corpus.voorbeeldministerie.example"
CORPUS_GRANT = "$1$4$naar-corpus"
NODE_URI = f"{CORPUS_BASE}/id/node/0b6f1c1e-5a0e-4a53-9a43-0d3e1d6b2a03"
OTHER_NODE_URI = "https://corpus.anderministerie.example/id/node/11111111-1111-4111-8111-111111111111"


def example(name: str) -> dict[str, Any]:
    """A valid example of the contract, as it crosses the boundary."""
    return json.loads(
        (CONTRACT_DIR / "examples" / "valid" / f"{name}.json").read_text()
    )


@pytest.fixture(autouse=True)
def _clean():
    registry.clear_registries()
    domain_events.clear_handlers()
    yield
    registry.clear_registries()
    domain_events.clear_handlers()


@pytest.fixture
def federated(monkeypatch):
    """This instance as a named organisation with an outway."""
    settings = get_settings()
    monkeypatch.setattr(settings, "INSTANCE_TOOI_URI", OWN_TOOI)
    monkeypatch.setattr(settings, "OUTWAY_URL", "http://outway.test")
    monkeypatch.setattr(settings, "FEDERATION_OUTBOUND_ENABLED", True)
    return settings


class StandInOutway:
    """Answers what this instance sends to its outway, and remembers it."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.handler: Callable[[httpx.Request], httpx.Response] = lambda _request: (
            httpx.Response(503, text="no handler")
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)

    def client(self) -> OutwayClient:
        return OutwayClient(
            get_settings(),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self._handle)),
        )


@pytest.fixture
def outway(federated, _test_app, client):
    """A stand-in outway, plugged into the app for this test."""
    stand_in = StandInOutway()
    shared = stand_in.client()
    _test_app.dependency_overrides[get_outway_client] = lambda: shared
    return stand_in


@pytest.fixture
def act_as(client: AsyncClient):
    def _as(person: Person) -> AsyncClient:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return client

    return _as


@dataclass
class Cast:
    beheerder: Person
    requester: Person
    signer: Person
    lezer: Person
    planner: Person
    outsider: Person
    contractor_peer: Peer
    corpus_peer: Peer


@pytest.fixture
async def cast(db_session: AsyncSession, create_person, federated) -> Cast:
    contractor_peer = Peer(
        peer_id="00000000000000000020",
        name=CONTRACTOR["name"],
        organisation_tooi_uri=CONTRACTOR["tooi_uri"],
        base_uri=CONTRACTOR["instance_uri"],
        role="counterpart",
        grant_hashes={"grip-opdrachtverkeer": CONTRACTOR_GRANT},
    )
    corpus_peer = Peer(
        peer_id="00000000000000000030",
        name="Corpus Voorbeeldministerie",
        base_uri=CORPUS_BASE,
        role="corpus",
        grant_hashes={"corpus-context": CORPUS_GRANT},
    )
    db_session.add_all([contractor_peer, corpus_peer])
    await db_session.flush()
    return Cast(
        beheerder=await create_person(
            "beheerder@example.org", name="Beheerder Voorbeeld", functions=["beheerder"]
        ),
        requester=await create_person(
            "aanvrager@example.org", name="Aanvrager Voorbeeld", functions=["aanvrager"]
        ),
        signer=await create_person(
            "tekenbevoegde@example.org",
            name="Tekenbevoegde Voorbeeld",
            functions=["tekenbevoegde"],
        ),
        lezer=await create_person(
            "lezer@example.org", name="Lezer Voorbeeld", functions=["lezer"]
        ),
        planner=await create_person(
            "planner@example.org", name="Planner Voorbeeld", functions=["planner"]
        ),
        outsider=await create_person("buiten@example.org", name="Buitenstaander"),
        contractor_peer=contractor_peer,
        corpus_peer=corpus_peer,
    )


@dataclass
class Received:
    assignment: Assignment
    quote: Quote


@pytest.fixture
async def received(db_session: AsyncSession, cast: Cast) -> Received:
    """An assignment this instance asked for, with a quote of the contractor."""
    await rates.create_rate_card(db_session, 2026, actor=cast.beheerder)
    await rates.set_rate_band(db_session, 2026, "D", 1800000, actor=cast.beheerder)
    await rates.set_rate_card_status(db_session, 2026, "active", actor=cast.beheerder)
    own = await own_organisation(db_session)
    contractor = await from_reference(db_session, CONTRACTOR)
    assignment, _ = await assignments.create_assignment_request(
        db_session,
        name="Opdracht Alfa",
        contractor_organisation_id=contractor.id,
        client_organisation_id=own.id,
        actor=cast.requester,
        description="Fictieve aanvraag.",
        context_refs=[NODE_URI],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 12, 31),
    )
    # The snapshot the contractor would have made, built here from a line.
    line = await assignments.add_budget_line(
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
    snapshot = await quotes.build_snapshot(db_session, assignment)
    await assignments.delete_budget_line(db_session, line.id, actor=None)
    quote = await quotes.receive_quote(
        db_session,
        assignment.id,
        quote_id=uuid.uuid4(),
        uri="https://grip.opdrachtnemer.example/id/offerte/x",
        snapshot=snapshot,
        claimed_hash=quotes.snapshot_hash(snapshot),
        issued_at=datetime(2026, 6, 1, 10, 0, tzinfo=UTC),
    )
    await db_session.flush()
    return Received(assignment=assignment, quote=quote)
