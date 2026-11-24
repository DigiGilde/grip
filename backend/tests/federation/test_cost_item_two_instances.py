"""A cost item kept by the organisation that makes the expense (ADR 0052, 0053).

Two instances in this process, as in ``test_two_instances``: the client there
asks the contractor to make a cost item and keeps a reference; the
contractor owns the item, and the client reads it there when it needs it.
Also what happens when the contractor cannot be reached or refuses, and the
refusals: only the asking peer may ask under its own URIs, and only it reads
what it asked for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from grip.core.config import get_settings
from grip.federation import terms
from grip.federation.bridge import cost_items, providers
from grip.federation.bridge.organisations import from_reference
from grip.federation.contract_loader import SERVICE_OPDRACHTVERKEER, validation_errors
from grip.federation.models import FederationOutbox, Peer
from grip.federation.outbox import send_due
from grip.federation.outway import OutwayClient
from grip.models.cost import CostItem, InvoiceLine
from grip.models.organisation import Organisation
from grip.repositories.domain import CostRepository
from grip.services import (
    assignments,
    cost_overview,
    cost_references,
    costs,
    pricing,
    requested_cost_items,
)
from grip.services.cost_references import ReferenceState
from grip.services.errors import DomainValidationError
from tests.federation import test_two_instances
from tests.federation.test_two_instances import (
    PEER_HEADER,
    Instance,
    _deliver,
    _know,
    acting_as,
)

# Two instances that know nothing of each other yet.
instances = test_two_instances.instances

OTHER_BASE = "https://grip.ander.example"
OTHER_PEER_ID = "00000000000000000040"
GILDE = "Voorbeeldgilde"


@pytest.fixture(autouse=True)
def _outway_of_the_acting_instance(monkeypatch):
    """A read goes out through the outway of the instance that reads."""
    monkeypatch.setattr(
        cost_items, "outway_client", lambda: test_two_instances._active[-1].outway
    )
    cost_items.forget()
    yield
    cost_items.forget()


def _unreachable(instance: Instance) -> OutwayClient:
    """An outway of ``instance`` behind which nothing answers."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with acting_as(instance):
        return OutwayClient(
            get_settings(),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(refuse)),
        )


async def _call(
    target: Instance,
    peer_id: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """A call on the listener of ``target`` as the inway would make it."""
    with acting_as(target):
        async with AsyncClient(
            transport=ASGITransport(app=target.app, raise_app_exceptions=False),
            base_url="http://inway.test",
        ) as inway:
            return await inway.request(
                method,
                f"/v1{path}",
                json=body,
                params=params,
                headers={PEER_HEADER: peer_id},
            )


def _request(uri: str, instance_uri: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "verwijzing_uri": uri,
        "volgnummer": 1,
        "organisatie": {
            "tooi_uri": "https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
            "naam": "Voorbeeldprogramma",
            "eenheid_kenmerk": "programma",
            "instantie_uri": instance_uri,
        },
        "omschrijving": "Zaal voor een bijeenkomst",
        "begroot": {"bedrag_centen": 100000, "valuta": "EUR"},
        "verzonden_op": "2026-02-02T09:30:00+01:00",
        **extra,
    }


async def _connected(client: Instance, contractor: Instance) -> uuid.UUID:
    """Both know each other; returns the contractor as organisation at the client."""
    async with client.session() as db:
        await _know(db, contractor)
        executor = await from_reference(db, contractor.reference())
        executor_id = executor.id
    async with contractor.session() as db:
        await _know(db, client)
    return executor_id


async def _programme(client: Instance, executor_id: uuid.UUID) -> tuple[Any, Any]:
    """A budget line of 10,000 and a reference to the contractor fully on it."""
    async with client.session() as db:
        assignment = await assignments.create_assignment(
            db,
            name="Voorbeeldprogramma 2026",
            actor=None,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        line = await assignments.add_budget_line(
            db,
            assignment.id,
            description="Bijeenkomsten",
            kind="fixed",
            amount_cents=1_000_000,
            year=2026,
            actor=None,
        )
        assert executor_id in await cost_references.possible_executor_ids(db)
        item = await costs.create_cost_item(
            db,
            description="Zaal en catering",
            budgeted_cents=450000,
            executor_organisation_id=executor_id,
            period=date(2026, 3, 1),
            actor=None,
        )
        await costs.set_coverage(db, item.id, line.id, Decimal("100"), actor=None)
        return assignment.id, item.id


async def _line_figures(client: Instance, assignment_id: uuid.UUID) -> Any:
    cost_items.forget()
    async with client.session() as db:
        (line,) = (await pricing.assignment_overview(db, assignment_id)).lines
        return line


async def _overview(client: Instance, item_id: uuid.UUID):
    cost_items.forget()
    async with client.session() as db:
        (overview,) = await cost_overview.cost_item_overviews(db, cost_item_id=item_id)
        return overview


async def _outbox(instance: Instance) -> list[FederationOutbox]:
    async with instance.session() as db:
        return list((await db.execute(select(FederationOutbox))).scalars().all())


async def test_request_create_read_book_and_change(instances):
    client, contractor = instances
    executor_id = await _connected(client, contractor)
    assignment_id, item_id = await _programme(client, executor_id)
    uri = f"{client.base_uri}/id/kostenpost/{item_id}"

    # --- the request waits for the worker; until then the total is not whole
    assert await _outbox(client) == []
    overview = await _overview(client, item_id)
    assert overview.reference.state is ReferenceState.WAITING
    assert overview.description == "Zaal en catering"
    assert overview.budgeted_cents == 450000
    assert not overview.counts
    line = await _line_figures(client, assignment_id)
    assert (line.coverage_cents, line.incomplete_by) == (0, (GILDE,))

    # --- the worker sends it; the contractor makes the item ----------------
    await _deliver(client)
    (sent,) = await _outbox(client)
    assert (sent.operation, sent.path) == ("requestCostItem", "/v1/kostenpostverzoeken")
    assert sent.payload["verwijzing_uri"] == uri
    assert sent.payload["volgnummer"] == 1
    assert sent.payload["periode"] == "2026-03-01"
    async with contractor.session() as db:
        owned = await CostRepository(db).by_reference_uri(uri)
        assert owned is not None
        assert (owned.description, owned.budgeted_cents) == ("Zaal en catering", 450000)
        requester = await db.get(Organisation, owned.requester_organisation_id)
        assert requester is not None and requester.instance_uri == client.base_uri
        (expected,) = await CostRepository(db).invoice_lines([owned.id])
        assert (expected.kind, expected.amount_cents, expected.period) == (
            "estimate",
            450000,
            date(2026, 3, 1),
        )
        owned_id, expected_id = owned.id, expected.id
    # Making the item sends nothing back.
    assert await _outbox(contractor) == []

    # --- the reference keeps nothing of the contractor's ---------------------
    async with client.session() as db:
        item = await db.get(CostItem, item_id)
        assert item is not None
        assert (item.request_status, item.executor_has_item) == ("applied", True)
        assert (item.description, item.budgeted_cents, item.request_period) == (
            None,
            None,
            None,
        )
        assert await CostRepository(db).invoice_lines([item_id]) == []

    # --- the client reads it there and counts it ----------------------------
    overview = await _overview(client, item_id)
    assert overview.reference.state is ReferenceState.FOUND
    assert (overview.description, overview.forecast_cents) == (
        "Zaal en catering",
        450000,
    )
    line = await _line_figures(client, assignment_id)
    assert (line.coverage_cents, line.incomplete_by) == (450000, ())

    # --- the invoice arrives at the contractor; the client reads it --------
    async with contractor.session() as db:
        await costs.add_invoice_line(
            db,
            owned_id,
            kind="actual",
            amount_cents=285000,
            reference="ZAAL-2026-031",
            period=date(2026, 3, 1),
            actor=None,
        )
        await costs.delete_invoice_line(db, expected_id, actor=None)
    overview = await _overview(client, item_id)
    assert [(line.kind, line.amount_cents) for line in overview.fetched_lines] == [
        ("actual", 285000)
    ]
    assert (overview.actual_cents, overview.forecast_cents) == (285000, 285000)
    line = await _line_figures(client, assignment_id)
    assert line.coverage_cents == 285000
    # No invoice lines of its own on a reference.
    async with client.session() as db:
        with pytest.raises(DomainValidationError):
            await costs.add_invoice_line(
                db, item_id, kind="estimate", amount_cents=1, actor=None
            )

    # --- a change is a request; the contractor applies it -------------------
    async with client.session() as db:
        await costs.update_cost_item(
            db, item_id, description="Zaal, catering en lunch", actor=None
        )
    overview = await _overview(client, item_id)
    assert overview.reference.change == "waiting"
    assert overview.description == "Zaal en catering"
    await _deliver(client)
    async with contractor.session() as db:
        owned = await db.get(CostItem, owned_id)
        assert owned is not None
        assert (owned.description, owned.budgeted_cents) == (
            "Zaal, catering en lunch",
            450000,
        )
        assert owned.reference_sequence == 2
        # Invoices and coverage stay the contractor's.
        assert len(await CostRepository(db).invoice_lines([owned_id])) == 1
    overview = await _overview(client, item_id)
    assert overview.reference.change is None
    assert overview.description == "Zaal, catering en lunch"


async def test_a_request_waits_while_the_contractor_cannot_be_reached(instances):
    client, contractor = instances
    executor_id = await _connected(client, contractor)
    assignment_id, item_id = await _programme(client, executor_id)
    reachable, client.outway = client.outway, _unreachable(client)
    try:
        async with client.session() as db:
            stats = await send_due(db, client.outway, get_settings())
        assert (stats.sent, stats.retried) == (0, 1)
        (row,) = await _outbox(client)
        assert (row.status, row.attempts) == ("pending", 1)
        overview = await _overview(client, item_id)
        assert overview.reference.state is ReferenceState.WAITING
        line = await _line_figures(client, assignment_id)
        assert line.incomplete_by == (GILDE,)
    finally:
        client.outway = reachable

    # Later, the contractor answers: the same message goes out once more.
    async with client.session() as db:
        queued = await db.get(FederationOutbox, row.id)
        assert queued is not None
        queued.next_attempt_at = datetime.now(UTC)
    await _deliver(client)
    assert len(await _outbox(client)) == 1
    overview = await _overview(client, item_id)
    assert overview.reference.state is ReferenceState.FOUND
    line = await _line_figures(client, assignment_id)
    assert (line.coverage_cents, line.incomplete_by) == (450000, ())


async def test_what_cannot_be_read_does_not_count(instances):
    client, contractor = instances
    executor_id = await _connected(client, contractor)
    assignment_id, item_id = await _programme(client, executor_id)
    await _deliver(client)
    reachable, client.outway = client.outway, _unreachable(client)
    try:
        overview = await _overview(client, item_id)
        assert overview.reference.state is ReferenceState.UNREACHABLE
        assert overview.budgeted_cents is None and not overview.counts
        line = await _line_figures(client, assignment_id)
        assert (line.coverage_cents, line.incomplete_by) == (0, (GILDE,))
        async with client.session() as db:
            totals = await pricing.assignment_overview(db, assignment_id)
        assert totals.incomplete_by == (GILDE,)
    finally:
        client.outway = reachable
    line = await _line_figures(client, assignment_id)
    assert (line.coverage_cents, line.incomplete_by) == (450000, ())


async def test_what_is_passed_on_says_what_could_not_be_read(instances, monkeypatch):
    """The uitputting for a client and the handover to a parent instance name
    the organisation whose cost items are missing from their amounts."""
    client, contractor = instances
    executor_id = await _connected(client, contractor)
    assignment_id, _item_id = await _programme(client, executor_id)
    await _deliver(client)
    async with client.session() as db:
        assignment = await assignments.get_assignment(db, assignment_id)

    async def may_read(*_args: Any) -> bool:
        return True

    async def financial(*_args: Any) -> Any:
        return assignment

    monkeypatch.setattr(providers, "_parent_reads", may_read)
    monkeypatch.setattr(providers, "_financial", financial)
    peer: Any = None

    async def passed_on() -> tuple[dict[str, Any], dict[str, Any]]:
        cost_items.forget()
        async with client.session() as db:
            usage = await providers.get_budget_usage(
                db, peer, {"assignmentId": assignment_id, "year": 2026}
            )
            handover = await providers.get_handover_costs(db, peer, {"year": 2026})
        assert usage is not None and handover is not None
        return terms.to_contract(usage), terms.to_contract(handover)

    usage, handover = await passed_on()
    assert "onvolledig_door" not in usage and "onvolledig_door" not in handover
    assert [r["omschrijving"] for r in handover["resultaten"]] == ["Zaal en catering"]

    reachable, client.outway = client.outway, _unreachable(client)
    try:
        usage, handover = await passed_on()
    finally:
        client.outway = reachable
    assert usage["onvolledig_door"] == [GILDE]
    assert usage["uitputting"]["bedrag_centen"] == 0
    assert handover["onvolledig_door"] == [GILDE]
    assert handover["resultaten"] == []
    assert validation_errors("uitputting", usage) == []
    assert validation_errors("doorgifte-kosten", handover) == []


async def test_a_refused_request(instances):
    client, contractor = instances
    async with client.session() as db:
        await _know(db, contractor)
        executor_id = (await from_reference(db, contractor.reference())).id
    # The contractor knows the client, but not as a counterparty it serves.
    async with contractor.session() as db:
        await _know(db, client, is_active=False)
    assignment_id, item_id = await _programme(client, executor_id)
    async with client.session() as db:
        stats = await send_due(db, client.outway, get_settings())
    assert stats.rejected == 1
    overview = await _overview(client, item_id)
    assert overview.reference.state is ReferenceState.REFUSED
    # What was asked stays readable; a refused item is no expense.
    assert overview.description == "Zaal en catering"
    line = await _line_figures(client, assignment_id)
    assert (line.coverage_cents, line.incomplete_by) == (0, ())
    async with contractor.session() as db:
        assert (await db.execute(select(CostItem))).scalars().all() == []
    # The client removes the reference; its coverage goes with it.
    async with client.session() as db:
        await costs.delete_reference(db, item_id, actor=None)
    async with client.session() as db:
        assert await db.get(CostItem, item_id) is None
        own = await costs.create_cost_item(db, description="Eigen", actor=None)
        with pytest.raises(DomainValidationError):
            await costs.delete_reference(db, own.id, actor=None)


async def _other_peer(db: Any) -> None:
    db.add(
        Peer(
            peer_id=OTHER_PEER_ID,
            name="Ander voorbeeld",
            base_uri=OTHER_BASE,
            role="counterpart",
            grant_hashes={SERVICE_OPDRACHTVERKEER: "$1$4$naar-ander"},
        )
    )


async def test_only_the_asker_reads_what_it_asked_for(instances):
    client, contractor = instances
    executor_id = await _connected(client, contractor)
    _assignment_id, item_id = await _programme(client, executor_id)
    await _deliver(client)
    async with contractor.session() as db:
        await _other_peer(db)
    uri = f"{client.base_uri}/id/kostenpost/{item_id}"
    unknown = f"{client.base_uri}/id/kostenpost/{uuid.uuid4()}"

    response = await _call(
        contractor,
        client.peer_id,
        "GET",
        "/kostenposten",
        params={"verwijzingUri": [uri, unknown]},
    )
    assert response.status_code == 200, response.text
    found, missing = response.json()["kostenposten"]
    assert (found["verwijzing_uri"], found["aangemaakt"]) == (uri, True)
    assert found["omschrijving"] == "Zaal en catering"
    assert missing == {"verwijzing_uri": unknown, "aangemaakt": False}

    # Another counterparty asks for the same reference: as if there were none.
    response = await _call(
        contractor, OTHER_PEER_ID, "GET", "/kostenposten", params={"verwijzingUri": uri}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "kostenposten": [{"verwijzing_uri": uri, "aangemaakt": False}]
    }

    # A peer that is no counterparty may not ask at all.
    response = await _call(
        contractor, "00000000000000000099", "GET", "/kostenposten", params={}
    )
    assert response.status_code in (400, 403, 422)


async def test_a_request_is_bound_to_the_calling_peer(instances):
    client, contractor = instances
    await _connected(client, contractor)
    async with contractor.session() as db:
        await _other_peer(db)

    # A reference under another instance than the caller's.
    foreign = f"{OTHER_BASE}/id/kostenpost/{uuid.uuid4()}"
    response = await _call(
        contractor,
        client.peer_id,
        "POST",
        "/kostenpostverzoeken",
        _request(foreign, client.base_uri),
    )
    assert response.status_code == 403, response.text

    # The organisation in the message names another instance than the caller.
    own = f"{client.base_uri}/id/kostenpost/{uuid.uuid4()}"
    response = await _call(
        contractor,
        client.peer_id,
        "POST",
        "/kostenpostverzoeken",
        _request(own, OTHER_BASE),
    )
    assert response.status_code == 403, response.text

    # The real asker, naming itself differently: the peer decides who asked.
    renamed = _request(own, client.base_uri)
    renamed["organisatie"]["naam"] = "Een andere naam"
    renamed["organisatie"]["tooi_uri"] = (
        "https://identifier.overheid.nl/tooi/id/oorg/oorg12345"
    )
    response = await _call(
        contractor, client.peer_id, "POST", "/kostenpostverzoeken", renamed
    )
    assert response.status_code == 201, response.text
    async with contractor.session() as db:
        item = await CostRepository(db).by_reference_uri(own)
        assert item is not None
        requester = await db.get(Organisation, item.requester_organisation_id)
        assert requester is not None
        assert requester.instance_uri == client.base_uri
        assert requester.name != "Een andere naam"

    # Another peer tries to change that item under the asker's URI.
    response = await _call(
        contractor,
        OTHER_PEER_ID,
        "POST",
        "/kostenpostverzoeken",
        _request(own, OTHER_BASE, volgnummer=2, omschrijving="Overgenomen"),
    )
    assert response.status_code == 403, response.text

    # An older request that arrives late changes nothing.
    response = await _call(
        contractor,
        client.peer_id,
        "POST",
        "/kostenpostverzoeken",
        _request(own, client.base_uri, omschrijving="Ouder verzoek"),
    )
    assert response.status_code == 201, response.text
    async with contractor.session() as db:
        item = await CostRepository(db).by_reference_uri(own)
        assert item is not None and item.description == "Zaal voor een bijeenkomst"
        # Neither does the service take a reference of another organisation.
        other = await from_reference(
            db, {"name": "Ander voorbeeld", "instance_uri": OTHER_BASE}
        )
        with pytest.raises(DomainValidationError):
            await requested_cost_items.receive_request(
                db,
                requester_organisation_id=other.id,
                reference_uri=own,
                sequence=9,
                description="Overgenomen",
                budgeted_cents=0,
            )
    assert len(await _items(contractor)) == 1
    lines = await _lines(contractor)
    assert [(line.kind, line.amount_cents) for line in lines] == [("estimate", 100000)]


async def _items(instance: Instance) -> list[CostItem]:
    async with instance.session() as db:
        return list((await db.execute(select(CostItem))).scalars().all())


async def _lines(instance: Instance) -> list[InvoiceLine]:
    async with instance.session() as db:
        return list((await db.execute(select(InvoiceLine))).scalars().all())
