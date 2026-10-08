"""A small fixed world for the access tests. No database."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4

import pytest

from grip.access import (
    AANVRAGER,
    BEHEERDER,
    LEZER,
    PLANNER,
    TEKENBEVOEGDE,
    AssignmentRole,
    Context,
    InMemoryRelationSource,
    LocalDecider,
    PeerRole,
    Subject,
)

TODAY = date(2026, 10, 8)


@dataclass(frozen=True)
class World:
    relations: InMemoryRelationSource
    decider: LocalDecider
    context: Context
    # Assignment this instance carries out; `client_peer` is its client.
    own: UUID
    # Another assignment nobody in the cast has a relation with.
    other: UUID
    # Assignment for which this instance is the client.
    commissioned: UUID
    quote: UUID
    commissioned_quote: UUID
    cost_item: UUID
    other_cost_item: UUID
    subjects: dict[str, Subject]
    # Staffed on `own` today; reports to `boss`.
    member: UUID
    # Reports to `boss`, staffed nowhere.
    solo: UUID
    # Was staffed on `own` until the end of 2025.
    former: UUID
    invitation: UUID

    def subject(self, name: str) -> Subject:
        return self.subjects[name]


def _person(*functions: str) -> Subject:
    return Subject.for_person(uuid4(), frozenset(functions))


@pytest.fixture
def world() -> World:
    own, other, commissioned = uuid4(), uuid4(), uuid4()
    quote, commissioned_quote = uuid4(), uuid4()
    cost_item, other_cost_item = uuid4(), uuid4()
    invitation = uuid4()

    people = {
        "beheerder": _person(BEHEERDER),
        "lezer": _person(LEZER),
        "planner": _person(PLANNER),
        "aanvrager": _person(AANVRAGER),
        "tekenbevoegde": _person(TEKENBEVOEGDE),
        "owner": _person(),
        "manager": _person(),
        "member": _person(),
        "colleague": _person(),
        "boss": _person(),
        "solo": _person(),
        "former": _person(),
        "outsider": _person(),
    }
    pid = {name: s.person_id for name, s in people.items()}

    relations = InMemoryRelationSource(
        assignment_roles={
            (pid["owner"], own): AssignmentRole.OWNER,
            (pid["manager"], own): AssignmentRole.MANAGER,
        },
        allocations=[
            (pid["member"], own, date(2026, 1, 1), date(2026, 12, 31)),
            (pid["colleague"], own, date(2026, 7, 1), date(2027, 6, 30)),
            (pid["former"], own, date(2025, 1, 1), date(2025, 12, 31)),
        ],
        line_managers={(pid["boss"], pid["member"]), (pid["boss"], pid["solo"])},
        cost_item_managers={(pid["owner"], cost_item), (pid["manager"], cost_item)},
        invitations={quote: [(invitation, "signer@client.example", None)]},
        client_assignments={commissioned},
        peers={
            "peer-client": frozenset({PeerRole.COUNTERPART}),
            "peer-contractor": frozenset({PeerRole.COUNTERPART}),
            "peer-stranger": frozenset({PeerRole.COUNTERPART}),
            "peer-parent": frozenset({PeerRole.PARENT}),
            "peer-child": frozenset({PeerRole.CHILD}),
            "peer-corpus": frozenset({PeerRole.CORPUS}),
        },
        peer_clients={("peer-client", own)},
        peer_contractors={("peer-contractor", commissioned)},
        corpus_references={("peer-corpus", own)},
    )

    subjects = dict(people)
    subjects["guest"] = Subject.for_guest(
        email="Signer@Client.example", invitation_id=invitation
    )
    subjects["uninvited_guest"] = Subject.for_guest(email="someone@elsewhere.example")
    for peer in (
        "client",
        "contractor",
        "stranger",
        "parent",
        "child",
        "corpus",
        "unknown",
    ):
        subjects[f"peer_{peer}"] = Subject.for_peer(f"peer-{peer}")

    return World(
        relations=relations,
        decider=LocalDecider(relations),
        context=Context(today=TODAY),
        own=own,
        other=other,
        commissioned=commissioned,
        quote=quote,
        commissioned_quote=commissioned_quote,
        cost_item=cost_item,
        other_cost_item=other_cost_item,
        subjects=subjects,
        member=pid["member"],  # type: ignore[arg-type]
        solo=pid["solo"],  # type: ignore[arg-type]
        former=pid["former"],  # type: ignore[arg-type]
        invitation=invitation,
    )
