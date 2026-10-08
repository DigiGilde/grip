"""Relations between a subject and an object, derived from data.

A relation is never assigned. It follows from who owns an assignment, who is
staffed on it, who reports to whom, who was invited to sign, and which
organisation a peer stands for. ``RelationSource`` is the only place the
decision function gets them from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol
from uuid import UUID

from grip.access.types import AssignmentRole, PeerRole

Period = tuple[date, date]


class RelationSource(Protocol):
    async def assignment_role(
        self, person_id: UUID, assignment_id: UUID
    ) -> AssignmentRole | None:
        """Owner or manager of the assignment, or neither."""
        ...

    async def is_member(
        self, person_id: UUID, assignment_id: UUID, today: date
    ) -> bool:
        """The person has an allocation on the assignment that has not ended."""
        ...

    async def is_allocated(
        self, person_id: UUID, assignment_id: UUID, period: Period | None
    ) -> bool:
        """The person has an allocation on the assignment overlapping the period.

        ``None`` means at any time.
        """
        ...

    async def is_line_manager(self, manager_id: UUID, person_id: UUID) -> bool:
        """The person reports directly to the manager."""
        ...

    async def manages_any_assignment(self, person_id: UUID) -> bool:
        """The person is owner or manager of at least one assignment."""
        ...

    async def manages_cost_item(self, person_id: UUID, cost_item_id: UUID) -> bool:
        """The person manages an assignment whose budget covers the cost item."""
        ...

    async def is_invited_signer(
        self,
        quote_id: UUID,
        *,
        invitation_id: UUID | None = None,
        email: str | None = None,
        person_id: UUID | None = None,
    ) -> bool:
        """There is an invitation to sign this quote for this identity."""
        ...

    async def instance_is_client(self, assignment_id: UUID) -> bool:
        """This instance is the client (opdrachtgever) of the assignment."""
        ...

    async def peer_roles(self, peer_id: str) -> frozenset[PeerRole]:
        """What the peer is to this instance. Empty for an unknown peer."""
        ...

    async def peer_is_client_of(self, peer_id: str, assignment_id: UUID) -> bool:
        """The peer stands for the client organisation of the assignment."""
        ...

    async def peer_is_contractor_of(self, peer_id: str, assignment_id: UUID) -> bool:
        """The peer stands for the contractor organisation of the assignment."""
        ...

    async def assignment_references_corpus(
        self, peer_id: str, assignment_id: UUID
    ) -> bool:
        """The assignment refers to a node in the corpus the peer manages."""
        ...


def _overlaps(start: date, end: date | None, period: Period | None) -> bool:
    if period is None:
        return True
    return start <= period[1] and (end is None or end >= period[0])


@dataclass
class InMemoryRelationSource:
    """Relations held in plain sets. For tests and for reasoning about the rules."""

    # (person_id, assignment_id) -> role
    assignment_roles: dict[tuple[UUID, UUID], AssignmentRole] = field(
        default_factory=dict
    )
    # (person_id, assignment_id, start, end)
    allocations: list[tuple[UUID, UUID, date, date | None]] = field(
        default_factory=list
    )
    # (manager_id, person_id)
    line_managers: set[tuple[UUID, UUID]] = field(default_factory=set)
    # (person_id, cost_item_id)
    cost_item_managers: set[tuple[UUID, UUID]] = field(default_factory=set)
    # quote_id -> invitations as (invitation_id, lowercased email, person_id)
    invitations: dict[UUID, list[tuple[UUID | None, str | None, UUID | None]]] = field(
        default_factory=dict
    )
    client_assignments: set[UUID] = field(default_factory=set)
    peers: dict[str, frozenset[PeerRole]] = field(default_factory=dict)
    # (peer_id, assignment_id)
    peer_clients: set[tuple[str, UUID]] = field(default_factory=set)
    peer_contractors: set[tuple[str, UUID]] = field(default_factory=set)
    corpus_references: set[tuple[str, UUID]] = field(default_factory=set)

    async def assignment_role(
        self, person_id: UUID, assignment_id: UUID
    ) -> AssignmentRole | None:
        return self.assignment_roles.get((person_id, assignment_id))

    async def is_member(
        self, person_id: UUID, assignment_id: UUID, today: date
    ) -> bool:
        return any(
            p == person_id and a == assignment_id and (end is None or end >= today)
            for p, a, _start, end in self.allocations
        )

    async def is_allocated(
        self, person_id: UUID, assignment_id: UUID, period: Period | None
    ) -> bool:
        return any(
            p == person_id and a == assignment_id and _overlaps(start, end, period)
            for p, a, start, end in self.allocations
        )

    async def is_line_manager(self, manager_id: UUID, person_id: UUID) -> bool:
        return (manager_id, person_id) in self.line_managers

    async def manages_any_assignment(self, person_id: UUID) -> bool:
        return any(p == person_id for p, _a in self.assignment_roles)

    async def manages_cost_item(self, person_id: UUID, cost_item_id: UUID) -> bool:
        return (person_id, cost_item_id) in self.cost_item_managers

    async def is_invited_signer(
        self,
        quote_id: UUID,
        *,
        invitation_id: UUID | None = None,
        email: str | None = None,
        person_id: UUID | None = None,
    ) -> bool:
        wanted_email = email.strip().lower() if email else None
        for inv_id, inv_email, inv_person in self.invitations.get(quote_id, []):
            if invitation_id is not None and inv_id == invitation_id:
                return True
            if wanted_email is not None and inv_email == wanted_email:
                return True
            if person_id is not None and inv_person == person_id:
                return True
        return False

    async def instance_is_client(self, assignment_id: UUID) -> bool:
        return assignment_id in self.client_assignments

    async def peer_roles(self, peer_id: str) -> frozenset[PeerRole]:
        return self.peers.get(peer_id, frozenset())

    async def peer_is_client_of(self, peer_id: str, assignment_id: UUID) -> bool:
        return (peer_id, assignment_id) in self.peer_clients

    async def peer_is_contractor_of(self, peer_id: str, assignment_id: UUID) -> bool:
        return (peer_id, assignment_id) in self.peer_contractors

    async def assignment_references_corpus(
        self, peer_id: str, assignment_id: UUID
    ) -> bool:
        return (peer_id, assignment_id) in self.corpus_references
