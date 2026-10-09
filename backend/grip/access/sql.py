"""Relations read from the instance's own database.

A peer is matched to an organisation through the base URI it mints URIs
under: ``peer.base_uri`` equals ``organisation.instance_uri``. The TOOI URI
cannot do that job, because two units of one registered organisation share it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from grip.access.relations import Period, _overlaps
from grip.access.types import AssignmentRole, PeerRole
from grip.core import changes
from grip.federation.models import Peer
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.assignment import AssignmentRole as AssignmentRoleRow
from grip.models.cost import CostCoverage, CostItem
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.quote import QuoteInvitation


def _same_base(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.rstrip("/") == b.rstrip("/")  # type: ignore[union-attr]


class SqlRelationSource:
    """``RelationSource`` on async SQLAlchemy.

    ``instance_base_uri`` is this instance's own base URI; it decides for
    which assignments the instance itself is the client.
    """

    def __init__(self, db: AsyncSession, *, instance_base_uri: str) -> None:
        self._db = db
        self._instance_base_uri = instance_base_uri
        # What this request already read about a person, so a list of 400
        # rows does not ask 400 times. Dropped as soon as the session writes.
        self._read: dict[Any, Any] = {}
        self._read_at: int | None = None

    async def _exists(self, condition: ColumnElement[bool]) -> bool:
        return bool(await self._db.scalar(select(condition)))

    def _kept(self) -> dict[Any, Any] | None:
        """What was read so far, or None when it cannot be trusted now."""
        now = changes.generation(self._db)
        if now is None:
            self._read.clear()
            return None
        if now != self._read_at:
            self._read.clear()
            self._read_at = now
        return self._read

    async def _roles_of(self, person_id: UUID) -> dict[UUID, str] | None:
        """Every assignment role of a person, read once per request."""
        kept = self._kept()
        if kept is None:
            return None
        key = ("roles", person_id)
        if key not in kept:
            rows = await self._db.execute(
                select(AssignmentRoleRow.assignment_id, AssignmentRoleRow.role).where(
                    AssignmentRoleRow.person_id == person_id
                )
            )
            kept[key] = {row[0]: row[1] for row in rows}
        return kept[key]  # type: ignore[no-any-return]

    async def _allocations_of(
        self, person_id: UUID
    ) -> list[tuple[UUID, date, date]] | None:
        """(assignment, start, end) of every allocation of a person."""
        kept = self._kept()
        if kept is None:
            return None
        key = ("allocations", person_id)
        if key not in kept:
            rows = await self._db.execute(
                select(
                    BudgetLine.assignment_id, Allocation.start_date, Allocation.end_date
                )
                .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
                .where(Allocation.person_id == person_id)
            )
            kept[key] = [(row[0], row[1], row[2]) for row in rows]
        return kept[key]  # type: ignore[no-any-return]

    async def assignment_role(
        self, person_id: UUID, assignment_id: UUID
    ) -> AssignmentRole | None:
        roles = await self._roles_of(person_id)
        if roles is not None:
            role = roles.get(assignment_id)
        else:
            role = await self._db.scalar(
                select(AssignmentRoleRow.role).where(
                    AssignmentRoleRow.person_id == person_id,
                    AssignmentRoleRow.assignment_id == assignment_id,
                )
            )
        return (
            AssignmentRole(role)
            if role in (AssignmentRole.OWNER, AssignmentRole.MANAGER)
            else None
        )

    def _allocation_on(self, person_id: UUID, assignment_id: UUID) -> Select[Any]:
        return (
            select(Allocation.id)
            .join(BudgetLine, BudgetLine.id == Allocation.budget_line_id)
            .where(
                Allocation.person_id == person_id,
                BudgetLine.assignment_id == assignment_id,
            )
        )

    async def is_member(
        self, person_id: UUID, assignment_id: UUID, today: date
    ) -> bool:
        own = await self._allocations_of(person_id)
        if own is not None:
            return any(a == assignment_id and end >= today for a, _start, end in own)
        query = self._allocation_on(person_id, assignment_id).where(
            Allocation.end_date >= today
        )
        return await self._exists(exists(query))

    async def is_allocated(
        self, person_id: UUID, assignment_id: UUID, period: Period | None
    ) -> bool:
        own = await self._allocations_of(person_id)
        if own is not None:
            return any(
                a == assignment_id and _overlaps(start, end, period)
                for a, start, end in own
            )
        query = self._allocation_on(person_id, assignment_id)
        if period is not None:
            query = query.where(
                Allocation.start_date <= period[1], Allocation.end_date >= period[0]
            )
        return await self._exists(exists(query))

    async def is_line_manager(self, manager_id: UUID, person_id: UUID) -> bool:
        kept = self._kept()
        if kept is not None:
            key = ("reports", manager_id)
            if key not in kept:
                rows = await self._db.execute(
                    select(Person.id).where(Person.manager_id == manager_id)
                )
                kept[key] = {row[0] for row in rows}
            return person_id in kept[key]
        return await self._exists(
            exists(
                select(Person.id).where(
                    Person.id == person_id, Person.manager_id == manager_id
                )
            )
        )

    async def manages_any_assignment(self, person_id: UUID) -> bool:
        roles = await self._roles_of(person_id)
        if roles is not None:
            return bool(roles)
        return await self._exists(
            exists(
                select(AssignmentRoleRow.id).where(
                    AssignmentRoleRow.person_id == person_id
                )
            )
        )

    async def manages_cost_item(self, person_id: UUID, cost_item_id: UUID) -> bool:
        """Through an assignment whose budget covers it, or as its creator.

        The creator manages the item only while nothing covers it: once a
        budget line carries part of it, the managers of that assignment do.
        """
        kept = self._kept()
        if kept is not None:
            key = ("cost_items", person_id)
            if key not in kept:
                # Every item the person manages, read once: through an own
                # assignment that covers it, or made by the person and
                # covered by nothing.
                through = await self._db.execute(
                    select(CostCoverage.cost_item_id)
                    .join(BudgetLine, BudgetLine.id == CostCoverage.budget_line_id)
                    .join(
                        AssignmentRoleRow,
                        AssignmentRoleRow.assignment_id == BudgetLine.assignment_id,
                    )
                    .where(AssignmentRoleRow.person_id == person_id)
                )
                made = await self._db.execute(
                    select(CostItem.id).where(
                        CostItem.created_by_id == person_id,
                        ~exists().where(CostCoverage.cost_item_id == CostItem.id),
                    )
                )
                kept[key] = {row[0] for row in through} | {row[0] for row in made}
            return cost_item_id in kept[key]
        covered_by_own_assignment = (
            select(CostCoverage.id)
            .join(BudgetLine, BudgetLine.id == CostCoverage.budget_line_id)
            .join(
                AssignmentRoleRow,
                AssignmentRoleRow.assignment_id == BudgetLine.assignment_id,
            )
            .where(
                CostCoverage.cost_item_id == cost_item_id,
                AssignmentRoleRow.person_id == person_id,
            )
        )
        if await self._exists(exists(covered_by_own_assignment)):
            return True
        any_coverage = select(CostCoverage.id).where(
            CostCoverage.cost_item_id == cost_item_id
        )
        created_uncovered = select(CostItem.id).where(
            CostItem.id == cost_item_id,
            CostItem.created_by_id == person_id,
            ~exists(any_coverage),
        )
        return await self._exists(exists(created_uncovered))

    async def cost_item_is_uncovered(self, cost_item_id: UUID) -> bool:
        # The item has to exist: an id that names nothing is not an item
        # looking for a budget, and a caller may probe with one to learn
        # whether the reader sees every item.
        kept = self._kept()
        if kept is not None:
            if "uncovered_items" not in kept:
                rows = await self._db.execute(
                    select(CostItem.id).where(
                        ~exists().where(CostCoverage.cost_item_id == CostItem.id)
                    )
                )
                kept["uncovered_items"] = {row[0] for row in rows}
            return cost_item_id in kept["uncovered_items"]
        uncovered = select(CostItem.id).where(
            CostItem.id == cost_item_id,
            ~exists().where(CostCoverage.cost_item_id == CostItem.id),
        )
        return await self._exists(exists(uncovered))

    async def is_invited_signer(
        self,
        quote_id: UUID,
        *,
        invitation_id: UUID | None = None,
        email: str | None = None,
        person_id: UUID | None = None,
    ) -> bool:
        identity = []
        if invitation_id is not None:
            identity.append(QuoteInvitation.id == invitation_id)
        if email and email.strip():
            identity.append(func.lower(QuoteInvitation.email) == email.strip().lower())
        if person_id is not None:
            identity.append(QuoteInvitation.person_id == person_id)
        if not identity:
            return False
        now = datetime.now(UTC)
        query = select(QuoteInvitation.id).where(
            QuoteInvitation.quote_id == quote_id,
            QuoteInvitation.withdrawn_at.is_(None),
            or_(*identity),
            or_(QuoteInvitation.expires_at.is_(None), QuoteInvitation.expires_at > now),
        )
        return await self._exists(exists(query))

    async def _organisation_instance_uri(
        self, assignment_id: UUID, column: InstrumentedAttribute[UUID | None]
    ) -> str | None:
        return await self._db.scalar(
            select(Organisation.instance_uri)
            .join(Assignment, column == Organisation.id)
            .where(Assignment.id == assignment_id)
        )

    async def instance_is_client(self, assignment_id: UUID) -> bool:
        client_uri = await self._organisation_instance_uri(
            assignment_id, Assignment.client_organisation_id
        )
        return _same_base(client_uri, self._instance_base_uri)

    async def _peer(self, peer_id: str) -> Peer | None:
        return await self._db.scalar(
            select(Peer).where(Peer.peer_id == peer_id, Peer.is_active.is_(True))
        )

    async def peer_roles(self, peer_id: str) -> frozenset[PeerRole]:
        peer = await self._peer(peer_id)
        if peer is None:
            return frozenset()
        try:
            return frozenset({PeerRole(peer.role)})
        except ValueError:
            return frozenset()

    async def _peer_is_party(
        self,
        peer_id: str,
        assignment_id: UUID,
        column: InstrumentedAttribute[UUID | None],
    ) -> bool:
        peer = await self._peer(peer_id)
        if peer is None:
            return False
        party_uri = await self._organisation_instance_uri(assignment_id, column)
        return _same_base(party_uri, peer.base_uri)

    async def peer_is_client_of(self, peer_id: str, assignment_id: UUID) -> bool:
        return await self._peer_is_party(
            peer_id, assignment_id, Assignment.client_organisation_id
        )

    async def peer_is_contractor_of(self, peer_id: str, assignment_id: UUID) -> bool:
        return await self._peer_is_party(
            peer_id, assignment_id, Assignment.contractor_organisation_id
        )

    async def assignment_references_corpus(
        self, peer_id: str, assignment_id: UUID
    ) -> bool:
        peer = await self._peer(peer_id)
        if peer is None or not peer.base_uri:
            return False
        refs = await self._db.scalar(
            select(Assignment.context_refs).where(Assignment.id == assignment_id)
        )
        base = peer.base_uri.rstrip("/") + "/"
        return any(isinstance(ref, str) and ref.startswith(base) for ref in refs or [])

    async def assignment_ids_for_person(
        self, person_id: UUID, today: date
    ) -> set[UUID]:
        """Assignments the person owns, manages or is a member of.

        Not part of ``RelationSource``: a helper to scope a list query for a
        subject without a function that reads all assignments.
        """
        managed = select(AssignmentRoleRow.assignment_id).where(
            AssignmentRoleRow.person_id == person_id
        )
        member = (
            select(BudgetLine.assignment_id)
            .join(Allocation, Allocation.budget_line_id == BudgetLine.id)
            .where(Allocation.person_id == person_id, Allocation.end_date >= today)
        )
        rows = await self._db.execute(managed.union(member))
        return {row[0] for row in rows}
