"""The client side through the API, against a second instance.

Two grip instances run in this process, each with its own database, as in
``tests/federation/test_two_instances.py`` whose harness this reuses. Here
the people work through the routes of the main application: the requester
asks for a quote, the contractor sees the request come in, the tekenbevoegde
reads and accepts the quote, and the client follows progress and asks for
the spending.

Needs the databases ``grip_test_client_a`` and ``grip_test_client_b`` on the
same server as the test database. The test is skipped when they do not exist.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from grip.access import AANVRAGER, PLANNER, TEKENBEVOEGDE
from grip.core.auth import DEV_PERSON_COOKIE
from grip.core.database import get_db
from grip.federation import registry
from grip.federation.events import register_event_handlers
from grip.federation.models import Peer
from grip.federation.routes import get_outway_client
from grip.middleware.csrf import CSRF_COOKIE_NAME
from grip.repositories.domain import AssignmentRepository
from grip.services import assignments, quotes, rates
from grip.services import events as domain_events
from tests.conftest import InMemorySessionStore, _find_session_middleware
from tests.federation.test_two_instances import (
    RATE_D,
    Instance,
    _database_exists,
    _database_url,
    _deliver,
    _empty,
    _know,
    _listener,
    _migrate,
    _person,
    _restore,
    _stand_in_outway,
    acting_as,
)

NODE_URI = "https://corpus.voorbeeldministerie.example/id/node/0b6f1c1e-5a0e-4a53-9a43-0d3e1d6b2a03"


@pytest.fixture
async def instances():
    client = Instance(
        key="opdrachtgever",
        name="Voorbeelddirectie",
        base_uri="https://grip.opdrachtgever.example",
        peer_id="00000000000000000010",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
        database="grip_test_client_a",
        grant="$1$4$naar-opdrachtgever",
    )
    contractor = Instance(
        key="opdrachtnemer",
        name="Voorbeeldgilde",
        base_uri="https://grip.opdrachtnemer.example",
        peer_id="00000000000000000020",
        tooi_uri="https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
        database="grip_test_client_b",
        grant="$1$4$naar-opdrachtnemer",
    )
    for instance in (client, contractor):
        if not await _database_exists(instance.database):
            pytest.skip(f"database {instance.database} does not exist")
        url = _database_url(instance.database)
        _migrate(url)
        instance.engine = create_async_engine(url, poolclass=NullPool)
        instance.sessions = async_sessionmaker(instance.engine, expire_on_commit=False)
        await _empty(instance.engine)
        instance.app = _listener(instance)
    by_grant = {client.grant: client, contractor.grant: contractor}
    client.outway = _stand_in_outway(client, by_grant)
    contractor.outway = _stand_in_outway(contractor, by_grant)

    registry.clear_registries()
    domain_events.clear_handlers()
    register_event_handlers()
    try:
        yield client, contractor
    finally:
        domain_events.clear_handlers()
        registry.clear_registries()
        for instance in (client, contractor):
            assert instance.engine is not None
            await instance.engine.dispose()
        _restore()


@asynccontextmanager
async def api(app, instance: Instance, person):
    """The main application of ``instance``, used by ``person``."""

    async def _own_db():
        assert instance.sessions is not None
        async with instance.sessions() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[get_db] = _own_db
    app.dependency_overrides[get_outway_client] = lambda: instance.outway
    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()
    session_mw = _find_session_middleware(app)
    original_store = session_mw.store
    session_mw.store = InMemorySessionStore()
    csrf = {"token": ""}

    async def _inject_csrf(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and csrf["token"]:
            request.headers["X-CSRF-Token"] = csrf["token"]

    try:
        with acting_as(instance):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                event_hooks={"request": [_inject_csrf]},
            ) as http:
                http.cookies.set(DEV_PERSON_COOKIE, str(person.id))
                first = await http.get("/api/auth/status")
                csrf["token"] = first.cookies.get(CSRF_COOKIE_NAME, "")
                yield http
    finally:
        app.dependency_overrides.clear()
        session_mw.store = original_store


async def test_requesting_deciding_and_following_through_the_api(instances, _test_app):
    client, contractor = instances

    async with client.session() as db:
        requester = await _person(
            db, "aanvrager@opdrachtgever.example", "Aanvrager Voorbeeld", AANVRAGER
        )
        signer = await _person(
            db,
            "tekenbevoegde@opdrachtgever.example",
            "Tekenbevoegde Voorbeeld",
            TEKENBEVOEGDE,
        )
        contractor_peer = await _know(db, contractor)
        contractor_peer_id = str(contractor_peer.id)
    async with contractor.session() as db:
        planner = await _person(
            db, "planner@opdrachtnemer.example", "Planner Voorbeeld", PLANNER
        )
        manager = await _person(db, "manager@opdrachtnemer.example", "Opdrachtmanager")
        await _know(db, client)
        for year, cents in RATE_D.items():
            await rates.create_rate_card(db, year, actor=None)
            await rates.set_rate_band(db, year, "D", cents, actor=None)
            await rates.set_rate_card_status(db, year, "active", actor=None)

    # --- 1. the requester asks for a quote -------------------------------
    async with api(_test_app, client, requester) as http:
        options = (await http.get("/api/client/options")).json()
        assert options["may_request"] is True and options["problem"] is None
        assert [c["peer_id"] for c in options["contractors"]] == [contractor_peer_id]
        created = await http.post(
            "/api/client/requests",
            json={
                "contractor_peer_id": contractor_peer_id,
                "name": "Opdracht Alfa",
                "description": "Fictieve aanvraag.",
                "start_date": "2026-07-01",
                "end_date": "2027-06-30",
                "context_uris": [NODE_URI],
            },
        )
        assert created.status_code == 201, created.text
        assignment = created.json()
        assert assignment["request_delivery"]["status"] == "pending"
        assert assignment["uri"].startswith(f"{client.base_uri}/id/opdracht/")
    await _deliver(client)
    async with api(_test_app, client, requester) as http:
        (row,) = (await http.get("/api/client/assignments")).json()["items"]
        assert row["request_delivery"]["status"] == "sent"
        assert row["status"] == "requested" and not row.get("latest_quote")

    # --- 2. the contractor sees it come in, and issues a quote ------------
    async with api(_test_app, contractor, planner) as http:
        (incoming,) = (await http.get("/api/received-requests")).json()["items"]
        assert incoming["name"] == "Opdracht Alfa" and incoming["status"] == "requested"
        assert incoming["client_name"] == "Voorbeelddirectie"
        assert incoming["uri"] == assignment["uri"] and incoming["context_count"] == 1
        # What this instance asked for itself is not in this list, and the
        # other way round.
        assert (await http.get("/api/client/assignments")).json()["items"] == []
    async with contractor.session() as db:
        received = await AssignmentRepository(db).get_by_uri(assignment["uri"])
        await assignments.add_budget_line(
            db,
            received.id,
            description="Productmanager",
            kind="personnel",
            role="Productmanager",
            fte=Decimal("0.8"),
            rate_category="D",
            start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30),
            actor=manager,
        )
        quote = await quotes.issue_quote(db, received.id, actor=manager)
        total = quote.total_cents
        issued_hash_local = quote.snapshot_hash
        # Issuing sends nothing; the quote goes out when it is offered
        # through the client's grip.
        await quotes.offer_quote(db, quote.id, "client_instance", actor=manager)
    await _deliver(contractor)

    # --- 3. the tekenbevoegde reads and accepts ---------------------------
    async with api(_test_app, client, signer) as http:
        (listed,) = (await http.get("/api/received-quotes")).json()["items"]
        assert listed["id"] == str(quote.id) and listed["may_decide"] is True
        assert listed["contractor_name"] == "Voorbeeldgilde"
        assert listed["total_cents"] == total
        detail = (await http.get(f"/api/received-quotes/{quote.id}")).json()
        # The quote is the contractor's: the same bytes, so the same hash.
        assert detail["quote"]["snapshot_hash"] == issued_hash_local
        (line,) = detail["quote"]["content"]["lines"]
        assert line["description"] == "Productmanager"
        assert [rate["year"] for rate in line["monthly_rates"]] == [2026, 2027]
        accepted = await http.post(
            f"/api/received-quotes/{quote.id}/acceptance",
            json={"signer_function": "Directeur"},
        )
        assert accepted.status_code == 201, accepted.text
        detail = (await http.get(f"/api/received-quotes/{quote.id}")).json()
        assert detail["deliveries"][0]["status"] == "pending"
    # The requester does not sign.
    async with api(_test_app, client, requester) as http:
        again = await http.post(f"/api/received-quotes/{quote.id}/rejection", json={})
        assert again.status_code == 404
    await _deliver(client)
    async with api(_test_app, client, signer) as http:
        detail = (await http.get(f"/api/received-quotes/{quote.id}")).json()
        assert detail["deliveries"][0]["status"] == "sent"
        assert detail["quote"]["status"] == "accepted"

    # --- 4. the client follows the assignment -----------------------------
    assignment_id = assignment["id"]
    async with api(_test_app, client, requester) as http:
        progress = (
            await http.get(f"/api/client/assignments/{assignment_id}/progress")
        ).json()
        assert progress["available"] is True, progress
        assert progress["status"] == "accepted"

        # Spending is not part of the contract yet: said as such.
        refused = (
            await http.post(
                f"/api/client/assignments/{assignment_id}/budget-usage", json={}
            )
        ).json()
        assert refused["available"] is False and refused["not_in_contract"] is True

    async with contractor.session() as db:
        peer = await db.scalar(select(Peer).where(Peer.peer_id == client.peer_id))
        peer.financial_inspection = True

    async with api(_test_app, client, requester) as http:
        usage = (
            await http.post(
                f"/api/client/assignments/{assignment_id}/budget-usage", json={}
            )
        ).json()
        assert usage["available"] is True, usage
        assert usage["budgeted_cents"] == total and usage["used_cents"] == 0
        assert [line["description"] for line in usage["lines"]] == ["Productmanager"]
        assert "Opdrachtmanager" not in str(usage)
