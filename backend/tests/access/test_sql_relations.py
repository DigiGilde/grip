"""``SqlRelationSource`` against a real PostgreSQL.

Runs only when the ``pgserver`` wheel is importable (it is not a project
dependency and has no wheel for the newest Python):
``uv run --isolated --python 3.12 --with pgserver pytest tests/access``.
The server is a
throwaway instance in a temporary directory, reached over a unix socket, so
it cannot collide with a database on a TCP port.
"""

import hashlib
import tempfile
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

pgserver = pytest.importorskip("pgserver")

from grip.access import (  # noqa: E402
    Action,
    AssignmentRole,
    Context,
    DataClass,
    LocalDecider,
    PeerRole,
    Resource,
    Subject,
    decide,
)
from grip.access.sql import SqlRelationSource  # noqa: E402
from grip.core.database import Base  # noqa: E402
from grip.federation.models import Peer  # noqa: E402
from grip.models.assignment import (  # noqa: E402
    Allocation,
    Assignment,
    BudgetLine,
)
from grip.models.assignment import AssignmentRole as AssignmentRoleRow  # noqa: E402
from grip.models.cost import CostCoverage, CostItem  # noqa: E402
from grip.models.organisation import Organisation  # noqa: E402
from grip.models.person import Person  # noqa: E402
from grip.models.quote import Quote, QuoteInvitation  # noqa: E402

TODAY = date(2026, 10, 8)
OWN_BASE = "https://grip.contractor.example"
CLIENT_BASE = "https://grip.client.example"
CORPUS_BASE = "https://corpus.ministry.example"


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    # A short path: a unix socket path has a small length limit.
    with tempfile.TemporaryDirectory(prefix="grip-pg-", dir="/tmp") as pgdata:
        server = pgserver.get_server(pgdata, cleanup_mode="stop")
        try:
            uri = server.get_uri()
            yield uri.replace("postgresql://", "postgresql+asyncpg://", 1)
        finally:
            server.cleanup()


@pytest.fixture
async def db(database_url: str) -> AsyncIterator[AsyncSession]:
    """A session in a transaction that is rolled back after the test."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


class Seed:
    def __init__(self) -> None:
        self.ids: dict[str, UUID] = {}

    def __getattr__(self, name: str) -> UUID:
        try:
            return self.ids[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


async def _add(db: AsyncSession, seed: Seed, name: str, row) -> None:
    db.add(row)
    await db.flush()
    seed.ids[name] = row.id


@pytest.fixture
async def seed(db: AsyncSession) -> Seed:
    s = Seed()
    for name in ("owner", "manager", "boss", "outsider"):
        await _add(db, s, name, Person(name=name, email=f"{name}@contractor.example"))
    for name in ("member", "former"):
        await _add(
            db,
            s,
            name,
            Person(name=name, email=f"{name}@contractor.example", manager_id=s.boss),
        )

    await _add(db, s, "own_org", Organisation(name="Contractor", instance_uri=OWN_BASE))
    await _add(
        db, s, "client_org", Organisation(name="Client", instance_uri=CLIENT_BASE + "/")
    )
    await _add(db, s, "plain_org", Organisation(name="No instance"))

    def assignment(key: str, client: UUID, contractor: UUID, refs: list[str]):
        return Assignment(
            uri=f"{OWN_BASE}/id/opdracht/{key}",
            name=f"Assignment {key}",
            client_organisation_id=client,
            contractor_organisation_id=contractor,
            context_refs=refs,
        )

    await _add(
        db,
        s,
        "own",
        assignment("own", s.client_org, s.own_org, [f"{CORPUS_BASE}/id/node/1"]),
    )
    await _add(db, s, "other", assignment("other", s.plain_org, s.own_org, []))
    await _add(
        db, s, "commissioned", assignment("commissioned", s.own_org, s.client_org, [])
    )

    for key in ("own", "other"):
        await _add(
            db,
            s,
            f"{key}_line",
            BudgetLine(
                assignment_id=s.ids[key],
                description="Developer",
                kind="personnel",
                role="Developer",
                fte=1,
                rate_category="C",
                start_date=date(2025, 1, 1),
                end_date=date(2026, 12, 31),
            ),
        )

    db.add_all(
        [
            AssignmentRoleRow(assignment_id=s.own, person_id=s.owner, role="owner"),
            AssignmentRoleRow(assignment_id=s.own, person_id=s.manager, role="manager"),
            Allocation(
                person_id=s.member,
                budget_line_id=s.own_line,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                fte_pct=80,
            ),
            Allocation(
                person_id=s.former,
                budget_line_id=s.own_line,
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
                fte_pct=100,
            ),
        ]
    )

    await _add(db, s, "cost_item", CostItem(description="Hosting", budgeted_cents=0))
    await _add(
        db, s, "loose_cost_item", CostItem(description="Other", budgeted_cents=0)
    )
    db.add(CostCoverage(cost_item_id=s.cost_item, budget_line_id=s.own_line, pct=30))

    now = datetime.now(UTC)
    await _add(
        db,
        s,
        "quote",
        Quote(
            uri=f"{OWN_BASE}/id/offerte/1",
            assignment_id=s.own,
            canonical=b"{}",
            snapshot_hash=hashlib.sha256(b"{}").hexdigest(),
            total_cents=0,
            issued_at=now,
        ),
    )
    await _add(
        db,
        s,
        "invitation",
        QuoteInvitation(quote_id=s.quote, email="Signer@Client.example"),
    )
    await _add(
        db,
        s,
        "expired_invitation",
        QuoteInvitation(
            quote_id=s.quote,
            email="late@client.example",
            person_id=s.outsider,
            expires_at=now - timedelta(days=1),
        ),
    )

    db.add_all(
        [
            Peer(
                peer_id="1" * 20,
                name="Client",
                base_uri=CLIENT_BASE,
                role="counterpart",
            ),
            Peer(
                peer_id="2" * 20,
                name="Parent",
                base_uri="https://grip.parent.example",
                role="parent",
            ),
            Peer(peer_id="3" * 20, name="Corpus", base_uri=CORPUS_BASE, role="corpus"),
            Peer(
                peer_id="4" * 20,
                name="Switched off",
                base_uri=CLIENT_BASE,
                role="counterpart",
                is_active=False,
            ),
        ]
    )
    await db.flush()
    return s


@pytest.fixture
def relations(db: AsyncSession) -> SqlRelationSource:
    return SqlRelationSource(db, instance_base_uri=OWN_BASE)


async def test_assignment_roles_and_membership(relations, seed) -> None:
    assert await relations.assignment_role(seed.owner, seed.own) is AssignmentRole.OWNER
    assert (
        await relations.assignment_role(seed.manager, seed.own)
        is AssignmentRole.MANAGER
    )
    assert await relations.assignment_role(seed.owner, seed.other) is None
    assert await relations.assignment_role(seed.member, seed.own) is None

    assert await relations.is_member(seed.member, seed.own, TODAY)
    assert not await relations.is_member(seed.member, seed.other, TODAY)
    assert not await relations.is_member(seed.former, seed.own, TODAY)
    assert await relations.is_member(seed.former, seed.own, date(2025, 12, 31))
    assert not await relations.is_member(seed.member, seed.own, date(2027, 1, 1))

    assert await relations.manages_any_assignment(seed.owner)
    assert not await relations.manages_any_assignment(seed.member)


async def test_allocation_in_a_period(relations, seed) -> None:
    year_2025 = (date(2025, 1, 1), date(2025, 12, 31))
    year_2026 = (date(2026, 1, 1), date(2026, 12, 31))
    assert await relations.is_allocated(seed.member, seed.own, None)
    assert await relations.is_allocated(seed.member, seed.own, year_2026)
    assert not await relations.is_allocated(seed.member, seed.own, year_2025)
    assert await relations.is_allocated(seed.former, seed.own, year_2025)
    assert not await relations.is_allocated(seed.former, seed.own, year_2026)
    assert await relations.is_allocated(
        seed.former, seed.own, (date(2025, 12, 31), date(2026, 1, 1))
    )
    assert not await relations.is_allocated(seed.member, seed.other, None)


async def test_line_manager_and_cost_items(relations, seed) -> None:
    assert await relations.is_line_manager(seed.boss, seed.member)
    assert not await relations.is_line_manager(seed.member, seed.boss)
    assert not await relations.is_line_manager(seed.boss, seed.owner)

    assert await relations.manages_cost_item(seed.owner, seed.cost_item)
    assert await relations.manages_cost_item(seed.manager, seed.cost_item)
    assert not await relations.manages_cost_item(seed.owner, seed.loose_cost_item)
    assert not await relations.manages_cost_item(seed.member, seed.cost_item)


async def test_invitations(relations, seed) -> None:
    assert await relations.is_invited_signer(seed.quote, invitation_id=seed.invitation)
    assert await relations.is_invited_signer(
        seed.quote, email=" signer@client.EXAMPLE "
    )
    assert not await relations.is_invited_signer(
        seed.quote, email="other@client.example"
    )
    assert not await relations.is_invited_signer(seed.quote)
    assert not await relations.is_invited_signer(seed.quote, email="  ")
    # Expired, on every way of matching.
    assert not await relations.is_invited_signer(
        seed.quote, email="late@client.example"
    )
    assert not await relations.is_invited_signer(seed.quote, person_id=seed.outsider)
    assert not await relations.is_invited_signer(
        seed.quote, invitation_id=seed.expired_invitation
    )
    # An invitation is for one quote.
    assert not await relations.is_invited_signer(
        seed.own, invitation_id=seed.invitation
    )


async def test_instance_and_peers(relations, seed) -> None:
    assert await relations.instance_is_client(seed.commissioned)
    assert not await relations.instance_is_client(seed.own)
    assert not await relations.instance_is_client(seed.other)

    client, parent, corpus, off = "1" * 20, "2" * 20, "3" * 20, "4" * 20
    assert await relations.peer_roles(client) == {PeerRole.COUNTERPART}
    assert await relations.peer_roles(parent) == {PeerRole.PARENT}
    assert await relations.peer_roles(corpus) == {PeerRole.CORPUS}
    assert await relations.peer_roles(off) == frozenset()
    assert await relations.peer_roles("9" * 20) == frozenset()

    assert await relations.peer_is_client_of(client, seed.own)
    assert not await relations.peer_is_client_of(client, seed.other)
    assert not await relations.peer_is_client_of(client, seed.commissioned)
    assert await relations.peer_is_contractor_of(client, seed.commissioned)
    assert not await relations.peer_is_contractor_of(client, seed.own)
    assert not await relations.peer_is_client_of(off, seed.own)
    assert not await relations.peer_is_client_of(parent, seed.own)

    assert await relations.assignment_references_corpus(corpus, seed.own)
    assert not await relations.assignment_references_corpus(corpus, seed.other)
    assert not await relations.assignment_references_corpus(client, seed.own)


async def test_visible_assignments_for_a_person(relations, seed) -> None:
    assert await relations.assignment_ids_for_person(seed.owner, TODAY) == {seed.own}
    assert await relations.assignment_ids_for_person(seed.member, TODAY) == {seed.own}
    assert await relations.assignment_ids_for_person(seed.former, TODAY) == set()
    assert await relations.assignment_ids_for_person(seed.outsider, TODAY) == set()


async def test_decider_on_real_data(relations, seed) -> None:
    """The same rules hold on SQL relations as on the in-memory ones."""
    decider = LocalDecider(relations)
    context = Context(today=TODAY)
    owner = Subject.for_person(seed.owner)
    member = Subject.for_person(seed.member)
    own = Resource.assignment(seed.own)
    about_member = Resource.allocation(seed.own, seed.member)
    about_former = Resource.allocation(seed.own, seed.former)

    assert await decide(
        decider, owner, Action.EDIT, own, DataClass.ASSIGNMENT_FINANCIAL, context
    )
    assert await decide(
        decider, owner, Action.READ, about_member, DataClass.PERSON_COST, context
    )
    assert not await decide(
        decider, owner, Action.READ, about_former, DataClass.PERSON_COST, context
    )
    assert not await decide(
        decider,
        owner,
        Action.READ,
        Resource.person(seed.member),
        DataClass.PERSON_KPI,
        context,
    )
    assert await decide(
        decider, member, Action.READ, own, DataClass.STAFFING_ROSTER, context
    )
    assert not await decide(
        decider, member, Action.READ, own, DataClass.ASSIGNMENT_FINANCIAL, context
    )

    client = Subject.for_peer("1" * 20)
    assert await decide(
        decider, client, Action.READ, own, DataClass.ASSIGNMENT_BASIC, context
    )
    assert not await decide(
        decider, client, Action.READ, own, DataClass.ASSIGNMENT_FINANCIAL, context
    )
    assert not await decide(
        decider, client, Action.READ, about_member, DataClass.STAFFING, context
    )
    guest = Subject.for_guest(email="signer@client.example")
    assert await decide(
        decider, guest, Action.ACCEPT_QUOTE, Resource.quote(seed.quote, seed.own)
    )
