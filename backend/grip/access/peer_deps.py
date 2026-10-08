"""Peers as subjects, and the one rule for peers that the matrix did not have.

The federation module asks its access questions here, so every answer to
another instance or a corpus system goes through the same decision point as
an answer to a person.

The addition is spending at a node. A corpus system may see, for an
assignment that refers to one of its nodes, the phase and the spending in
totals (budgeted and used), so the corpus can show what is being done for a
node. It gets no budget lines, no billing data and no names: this is a
narrower view than class B, granted only on the relation "the assignment
references this corpus".
"""

from __future__ import annotations

from uuid import UUID

from grip.access.decider import Decider, decide
from grip.access.relations import RelationSource
from grip.access.types import (
    Action,
    Context,
    DataClass,
    Decision,
    PeerRole,
    Resource,
    Subject,
)

# Reason codes of the added rule.
CORPUS_SPENDING = "relation:corpus_spending_totals"
NO_CORPUS_RELATION = "no_corpus_relation"


def peer_subject(peer_id: str) -> Subject:
    return Subject.for_peer(peer_id)


class PeerAccess:
    """Access questions about one peer, answered by the decision point."""

    def __init__(
        self, decider: Decider, relations: RelationSource, peer_id: str
    ) -> None:
        self._decider = decider
        self._relations = relations
        self.subject = peer_subject(peer_id)
        self.peer_id = peer_id

    async def may(
        self,
        action: Action,
        resource: Resource,
        data_class: DataClass | None = None,
        context: Context | None = None,
    ) -> Decision:
        return await decide(
            self._decider, self.subject, action, resource, data_class, context
        )

    async def reads(
        self,
        resource: Resource,
        data_class: DataClass,
        context: Context | None = None,
    ) -> bool:
        decision = await self.may(Action.READ, resource, data_class, context)
        return decision.allowed

    async def spending_totals(self, assignment_id: UUID) -> Decision:
        """May this peer see budgeted and used totals of the assignment?

        Whoever may read class B may. Beyond that only a corpus system the
        assignment refers to.
        """
        resource = Resource.assignment(assignment_id)
        financial = await self.may(
            Action.READ, resource, DataClass.ASSIGNMENT_FINANCIAL
        )
        if financial.allowed:
            return financial
        roles = await self._relations.peer_roles(self.peer_id)
        if PeerRole.CORPUS in roles and (
            await self._relations.assignment_references_corpus(
                self.peer_id, assignment_id
            )
        ):
            return Decision(True, CORPUS_SPENDING)
        return Decision(False, NO_CORPUS_RELATION)
