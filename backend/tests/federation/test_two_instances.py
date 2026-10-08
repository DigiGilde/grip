"""Two grip instances exchange a request, a quote and an acceptance.

Both run in this process, each with its own database, settings and signing
key. They reach each other through a stand-in outway that forwards a call to
the other instance's federation listener and sets the peer id header, as an
FSC outway and inway would. Everything else is the real code: the domain
services, the event handlers, the outbox, the contract routes, the bridge,
the signature check and the access model.

Needs the databases ``grip_test_fed_a`` and ``grip_test_fed_b`` on the same
server as the test database. The test is skipped when they do not exist.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import rfc8785
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from grip.access import (
    AANVRAGER,
    TEKENBEVOEGDE,
    Action,
    LocalDecider,
    Resource,
    Subject,
    decide,
)
from grip.access.sql import SqlRelationSource
from grip.core.config import Settings, get_settings
from grip.core.database import get_db
from grip.federation import registry, signing, terms
from grip.federation.app import create_federation_app
from grip.federation.bridge.acceptance import accept_received_quote
from grip.federation.bridge.organisations import from_reference, own_organisation
from grip.federation.bridge.settings import get_bridge_settings
from grip.federation.contract_loader import (
    SERVICE_OPDRACHTVERKEER,
    operation,
    validation_errors,
)
from grip.federation.events import register_event_handlers
from grip.federation.models import FederationInbox, FederationOutbox, Peer
from grip.federation.outbox import send_due
from grip.federation.outway import OutwayClient
from grip.federation.routes import get_outway_client
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.quote import Quote, QuoteAcceptance
from grip.models.role import PersonRole
from grip.repositories.domain import AssignmentRepository
from grip.services import assignments, quotes, rates
from grip.services import events as domain_events

BACKEND = Path(__file__).resolve().parents[2]
PEER_HEADER = "Fsc-Request-Peer-Id"
NODE_URI = "https://corpus.voorbeeldministerie.example/id/node/0b6f1c1e-5a0e-4a53-9a43-0d3e1d6b2a03"
CORPUS_BASE = "https://corpus.voorbeeldministerie.example"
CORPUS_PEER_ID = "00000000000000000030"
RATE_D = {2026: 1800000, 2027: 1890000}


@dataclass
class Instance:
    """One grip instance: its identity, database and listener."""

    key: str
    name: str
    base_uri: str
    peer_id: str
    tooi_uri: str
    database: str
    grant: str
    signing_pem: str = field(default_factory=signing.generate_private_key_pem)
    engine: AsyncEngine | None = None
    sessions: async_sessionmaker[AsyncSession] | None = None
    app: Any = None
    outway: OutwayClient | None = None

    def env(self) -> dict[str, str]:
        return {
            "INSTANCE_NAME": self.name,
            "INSTANCE_BASE_URI": self.base_uri,
            "INSTANCE_TOOI_URI": self.tooi_uri,
            "INSTANCE_KEY": self.key,
            "FEDERATION_INBOUND_ENABLED": "1",
            "FEDERATION_OUTBOUND_ENABLED": "1",
            "OUTWAY_URL": f"http://outway.{self.key}.test",
            "FSC_PEER_ID_HEADER": PEER_HEADER,
            "FEDERATION_SIGNING_KEY": self.signing_pem,
            "FEDERATION_SIGNING_KID": f"{self.key}-2026",
            "HANDOVER_STAFFING_WITH_NAMES": "0",
        }

    def reference(self) -> dict[str, Any]:
        return {
            "tooi_uri": self.tooi_uri,
            "name": self.name,
            "unit_key": self.key,
            "instance_uri": self.base_uri,
        }

    @asynccontextmanager
    async def session(self):
        """A committed unit of work in this instance, with its settings."""
        assert self.sessions is not None
        with acting_as(self):
            async with self.sessions() as db:
                yield db
                await db.commit()

    def settings(self) -> Settings:
        with acting_as(self):
            return get_settings()


_active: list[Instance] = []


@contextmanager
def acting_as(instance: Instance):
    """Make ``instance`` the one whose settings the code sees.

    Settings are process-wide and cached, so two instances in one process
    take turns: the innermost ``acting_as`` wins and the previous one is
    restored on the way out. Calls are sequential, which makes this safe.
    """
    _active.append(instance)
    _apply(instance)
    try:
        yield
    finally:
        _active.pop()
        if _active:
            _apply(_active[-1])
        else:
            _restore()


_saved_env: dict[str, str | None] = {}


def _apply(instance: Instance) -> None:
    for name, value in instance.env().items():
        if name not in _saved_env:
            _saved_env[name] = os.environ.get(name)
        os.environ[name] = value
    get_settings.cache_clear()
    get_bridge_settings.cache_clear()


def _restore() -> None:
    for name, value in _saved_env.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    _saved_env.clear()
    get_settings.cache_clear()
    get_bridge_settings.cache_clear()


def _database_url(name: str) -> str:
    return (
        make_url(get_settings().DATABASE_URL)
        .set(database=name)
        .render_as_string(hide_password=False)
    )


async def _database_exists(name: str) -> bool:
    engine = create_async_engine(_database_url(name), poolclass=NullPool)
    try:
        async with engine.connect():
            return True
    except Exception:
        return False
    finally:
        await engine.dispose()


def _migrate(url: str) -> None:
    subprocess.run(  # noqa: S603 - fixed command, own interpreter
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": url, "DEV_NO_AUTH": "1"},
        check=True,
        capture_output=True,
    )


async def _empty(engine: AsyncEngine) -> None:
    """Remove every row except the seeded functions and the schema version."""
    async with engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename NOT IN ('alembic_version', 'role')"
                )
            )
        ).scalars()
        names = ", ".join(f'"{name}"' for name in tables)
        await conn.execute(text(f"TRUNCATE {names} CASCADE"))


def _stand_in_outway(source: Instance, routes: dict[str, Instance]) -> OutwayClient:
    """The outway of ``source``: forwards by grant hash to another listener."""

    async def forward(request: httpx.Request) -> httpx.Response:
        target = routes.get(request.headers.get("Fsc-Grant-Hash", ""))
        if target is None:
            return httpx.Response(403, text="no contract for this grant hash")
        headers = {PEER_HEADER: source.peer_id}
        if request.headers.get("content-type"):
            headers["content-type"] = request.headers["content-type"]
        with acting_as(target):
            async with AsyncClient(
                transport=ASGITransport(app=target.app, raise_app_exceptions=False),
                base_url="http://inway.test",
            ) as inway:
                response = await inway.request(
                    request.method,
                    request.url.raw_path.decode(),
                    content=request.content,
                    headers=headers,
                )
        return httpx.Response(
            response.status_code,
            content=response.content,
            headers={"content-type": response.headers.get("content-type", "")},
        )

    with acting_as(source):
        return OutwayClient(
            get_settings(),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(forward)),
        )


def _listener(instance: Instance) -> Any:
    app = create_federation_app()

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
    return app


@pytest.fixture
async def instances():
    client = Instance(
        key="opdrachtgever",
        name="Voorbeelddirectie",
        base_uri="https://grip.opdrachtgever.example",
        peer_id="00000000000000000010",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
        database="grip_test_fed_a",
        grant="$1$4$naar-opdrachtgever",
    )
    contractor = Instance(
        key="opdrachtnemer",
        name="Voorbeeldgilde",
        base_uri="https://grip.opdrachtnemer.example",
        peer_id="00000000000000000020",
        tooi_uri="https://identifier.overheid.nl/tooi/id/oorg/oorg00000",
        database="grip_test_fed_b",
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


async def _person(db: AsyncSession, email: str, name: str, *functions: str) -> Person:
    person = Person(name=name, email=email)
    db.add(person)
    await db.flush()
    for function in functions:
        db.add(PersonRole(person_id=person.id, role_id=function))
    await db.flush()
    return person


async def _know(db: AsyncSession, other: Instance, **kwargs: Any) -> Peer:
    peer = Peer(
        peer_id=other.peer_id,
        name=other.name,
        organisation_tooi_uri=other.tooi_uri,
        base_uri=other.base_uri,
        role="counterpart",
        grant_hashes={SERVICE_OPDRACHTVERKEER: other.grant},
        **kwargs,
    )
    db.add(peer)
    await db.flush()
    return peer


async def _deliver(instance: Instance) -> None:
    """What the worker of an instance does: send what is due."""
    async with instance.session() as db:
        stats = await send_due(db, instance.outway, get_settings())
    assert (stats.retried, stats.rejected, stats.dead) == (0, 0, 0), await _errors(
        instance
    )


async def _errors(instance: Instance) -> list[str]:
    async with instance.session() as db:
        rows = (await db.execute(select(FederationOutbox))).scalars().all()
        return [f"{row.operation}: {row.status} {row.last_error}" for row in rows]


async def _pull(
    source: Instance,
    target: Instance,
    operation_id: str,
    params: dict[str, Any] | None = None,
    **path: str,
) -> httpx.Response:
    async with source.session() as db:
        peer = await db.scalar(select(Peer).where(Peer.peer_id == target.peer_id))
        return await source.outway.request(
            peer,
            SERVICE_OPDRACHTVERKEER,
            "GET",
            operation(operation_id).url_path(**path),
            params=params,
        )


async def test_request_quote_acceptance_and_inspection(instances):
    client, contractor = instances

    # --- who knows whom --------------------------------------------------
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
        colleague = await _person(db, "collega@opdrachtgever.example", "Collega")
        await _know(db, contractor)
    async with contractor.session() as db:
        manager = await _person(db, "manager@opdrachtnemer.example", "Opdrachtmanager")
        await _know(db, client)
        db.add(
            Peer(
                peer_id=CORPUS_PEER_ID,
                name="Corpus Voorbeeldministerie",
                base_uri=CORPUS_BASE,
                role="corpus",
                grant_hashes={},
            )
        )
        for year, cents in RATE_D.items():
            await rates.create_rate_card(db, year, actor=None)
            await rates.set_rate_band(db, year, "D", cents, actor=None)
            await rates.set_rate_card_status(db, year, "active", actor=None)

    # --- 1. the client asks for a quote ----------------------------------
    async with client.session() as db:
        own = await own_organisation(db)
        other = await from_reference(db, contractor.reference())
        assignment, request_id = await assignments.create_assignment_request(
            db,
            name="Opdracht Alfa",
            contractor_organisation_id=other.id,
            client_organisation_id=own.id,
            actor=requester,
            description="Fictieve aanvraag.",
            context_refs=[NODE_URI],
            start_date=date(2026, 7, 1),
            end_date=date(2027, 6, 30),
        )
        assignment_uri = assignment.uri
        assignment_uuid = str(assignment.id)
        (queued,) = (await db.execute(select(FederationOutbox))).scalars().all()
        # What is queued is what crosses the boundary: Dutch terms.
        assert queued.path == "/v1/opdrachtaanvragen"
        assert queued.payload["opdracht_uri"] == assignment_uri
        assert queued.payload["context_uris"] == [NODE_URI]
        assert "assignment_uri" not in queued.payload
    assert assignment_uri == f"{client.base_uri}/id/opdracht/{assignment_uuid}"
    await _deliver(client)

    # --- 2. the contractor received it, budgets and issues a quote -------
    async with contractor.session() as db:
        received = await AssignmentRepository(db).get_by_uri(assignment_uri)
        assert received is not None and received.status == "requested"
        assert received.context_refs == [NODE_URI]
        assert received.id != assignment.id, "each side has its own row"
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
        quote = await quotes.issue_quote(
            db, received.id, actor=manager, request_id=request_id
        )
        quote_id = quote.id
        assert quote.total_cents == 6 * 1440000 + 6 * 1512000
        contractor_assignment_id = received.id
        issued_bytes = bytes(quote.canonical)
        issued_hash = quote.snapshot_hash
        assert issued_hash == hashlib.sha256(issued_bytes).hexdigest()

        # Issuing freezes the quote and sends nothing.
        assert (await db.execute(select(FederationOutbox))).scalars().all() == []
        # The request came from the client's instance, so offering it back
        # through the client's grip is possible and the suggestion.
        options = {o.channel: o for o in await quotes.channel_options(db, quote_id)}
        assert options["client_instance"].available
        assert options["client_instance"].suggested
        offer = await quotes.offer_quote(db, quote_id, "client_instance", actor=manager)
        assert offer.recipient == client.base_uri
        (out,) = (await db.execute(select(FederationOutbox))).scalars().all()
        assert out.operation == "sendQuote" and out.path == "/v1/offertes"
        # What goes out is the stored canonical form, not a new translation.
        assert rfc8785.dumps(out.payload["momentopname"]) == issued_bytes
        assert out.payload["momentopname_hash"] == issued_hash
    await _deliver(contractor)

    # --- 3. the client received the quote; a tekenbevoegde accepts -------
    async with client.session() as db:
        seen = await db.get(Quote, quote_id)
        assert seen is not None and seen.total_cents == quote.total_cents
        # One quote, one canonical form, one hash, on both sides.
        assert bytes(seen.canonical) == issued_bytes
        assert seen.snapshot_hash == issued_hash
        assert seen.snapshot == quote.snapshot
        line = seen.snapshot["lines"][0]
        assert [entry["year"] for entry in line["monthly_rates_per_year"]] == [
            2026,
            2027,
        ]
        mine = await db.get(Assignment, assignment.id)
        assert mine is not None and mine.status == "quoted"

        decider = LocalDecider(SqlRelationSource(db, instance_base_uri=client.base_uri))
        about = Resource.quote(seen.id, seen.assignment_id)
        allowed = await decide(
            decider,
            Subject.for_person(signer.id, {TEKENBEVOEGDE}),
            Action.ACCEPT_QUOTE,
            about,
        )
        refused = await decide(
            decider, Subject.for_person(colleague.id), Action.ACCEPT_QUOTE, about
        )
        assert allowed.allowed and not refused.allowed

        acceptance = await accept_received_quote(
            db, seen.id, actor=signer, signer_function="Directeur"
        )
        acceptance_id = acceptance.id
        assert acceptance.jws and acceptance.form == "own_instance"
        mine = await db.get(Assignment, assignment.id)
        assert mine is not None and mine.status == "accepted"
    await _deliver(client)

    # --- 4. the contractor sees a verified acceptance --------------------
    async with contractor.session() as db:
        stored = await db.get(QuoteAcceptance, acceptance_id)
        assert stored is not None and stored.form == "own_instance"
        assert stored.signer_email == "tekenbevoegde@opdrachtgever.example"
        agreed = await db.get(Assignment, contractor_assignment_id)
        assert agreed is not None and agreed.status == "accepted"
        assert agreed.quoted_amount_cents == quote.total_cents

        # The signature verifies against the keys the client publishes, over
        # the message as it crossed the boundary.
        wire = (
            await db.execute(
                select(FederationInbox).where(
                    FederationInbox.message_id == acceptance_id
                )
            )
        ).scalar_one()
        assert wire.processed_at is not None
        assert wire.payload["vorm"] == "eigen_instantie"
        # The signed acceptance cites the one hash of the quote.
        assert wire.payload["offerte_hash"] == issued_hash == stored.quote_hash
        assert validation_errors("akkoord", wire.payload) == []
        signing.verify_acceptance(wire.payload, signing.own_jwks(client.settings()))
        tampered = {**wire.payload, terms.term("quote_hash"): "0" * 64}
        with pytest.raises(signing.SignatureInvalidError):
            signing.verify_acceptance(tampered, signing.own_jwks(client.settings()))
        # The acceptance did not travel back: it came from the other side.
        assert (await db.execute(select(FederationOutbox))).scalars().all() != []
        back = (
            await db.execute(
                select(FederationOutbox).where(
                    FederationOutbox.operation == "sendAcceptance"
                )
            )
        ).scalars()
        assert list(back) == []

    # --- 5. the client pulls progress and budget usage --------------------
    progress = await _pull(
        client, contractor, "getProgress", opdrachtId=assignment_uuid
    )
    assert progress.status_code == 200, progress.text
    assert progress.json()["status"] == "akkoord"
    assert progress.json()["opdracht_uri"] == assignment_uri

    # Financial data is never a default: without the contract part, 403.
    usage = await _pull(
        client, contractor, "getBudgetUsage", opdrachtId=assignment_uuid
    )
    assert usage.status_code == 403, usage.text
    assert usage.headers["content-type"].startswith("application/problem+json")

    async with contractor.session() as db:
        peer = await db.scalar(select(Peer).where(Peer.peer_id == client.peer_id))
        peer.financial_inspection = True

    usage = await _pull(
        client, contractor, "getBudgetUsage", opdrachtId=assignment_uuid
    )
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["begroot"] == {"bedrag_centen": quote.total_cents, "valuta": "EUR"}
    assert body["uitputting"]["bedrag_centen"] == 0
    assert [regel["omschrijving"] for regel in body["regels"]] == ["Productmanager"]
    assert "manager@" not in usage.text and "Opdrachtmanager" not in usage.text

    # An assignment the caller has no relation with is simply not there.
    missing = await _pull(
        client,
        contractor,
        "getProgress",
        opdrachtId="00000000-0000-4000-8000-000000000000",
    )
    assert missing.status_code == 404

    # --- 6. the corpus sees phase and spending at its node ----------------
    with acting_as(contractor):
        async with AsyncClient(
            transport=ASGITransport(app=contractor.app, raise_app_exceptions=False),
            base_url="http://inway.test",
        ) as inway:
            at_node = await inway.get(
                "/v1/opdrachten",
                params={"nodeUri": NODE_URI},
                headers={PEER_HEADER: CORPUS_PEER_ID},
            )
            # A corpus is not a client: it gets no budget lines.
            lines = await inway.get(
                f"/v1/opdrachten/{assignment_uuid}/uitputting",
                headers={PEER_HEADER: CORPUS_PEER_ID},
            )
    assert at_node.status_code == 200, at_node.text
    (found,) = at_node.json()["resultaten"]
    assert found["uri"] == assignment_uri and found["status"] == "akkoord"
    assert found["besteding"]["begroot"]["bedrag_centen"] == quote.total_cents
    assert "regels" not in found
    assert lines.status_code == 403
