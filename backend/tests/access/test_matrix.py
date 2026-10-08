"""The access matrix, cell by cell.

Every row of the matrix in the access model is a subject here; every column
is one of the six data classes, for reading and for editing. A cell not named
as allowed must be denied.
"""

from uuid import uuid4

import pytest

from grip.access import (
    CORE_DATA_CLASSES,
    Action,
    DataClass,
    Resource,
    Subject,
    SubjectKind,
    decide,
)

LETTER = dict(zip("ABCDEF", CORE_DATA_CLASSES, strict=True))

# subject -> (classes readable, classes editable), about the staffed member.
MATRIX: dict[str, tuple[str, str]] = {
    "beheerder": ("ABCDEF", ""),
    "lezer": ("AB", ""),
    "planner": ("AC", "C"),
    "owner": ("ABCDE", "ABC"),
    "manager": ("ABCDE", "ABC"),
    # A fellow member of the assignment: basics only (the roster is a
    # narrower view, tested separately).
    "colleague": ("A", ""),
    # Line manager without any relation to the assignment.
    "boss": ("CDF", ""),
    # The staffed person looking at the own data: self plus member.
    "member": ("ACDF", ""),
    "former": ("", ""),
    # Staffed nowhere, and no relation to the member either.
    "solo": ("", ""),
    "outsider": ("", ""),
    "aanvrager": ("", ""),
    "tekenbevoegde": ("", ""),
    "guest": ("", ""),
    "uninvited_guest": ("", ""),
    "peer_client": ("A", ""),
    "peer_parent": ("AB", ""),
    "peer_corpus": ("A", ""),
    "peer_contractor": ("", ""),
    "peer_stranger": ("", ""),
    "peer_child": ("", ""),
    "peer_unknown": ("", ""),
}

CELLS = [
    (subject, letter, action)
    for subject in MATRIX
    for letter in LETTER
    for action in (Action.READ, Action.EDIT)
]


def _resource(world, letter: str) -> Resource:
    if letter in "AB":
        return Resource.assignment(world.own)
    if letter in "CDE":
        return Resource.allocation(world.own, world.member)
    return Resource.person(world.member)


@pytest.mark.parametrize(("subject", "letter", "action"), CELLS)
async def test_matrix_cell(world, subject: str, letter: str, action: Action) -> None:
    readable, editable = MATRIX[subject]
    expected = letter in (readable if action is Action.READ else editable)
    decision = await decide(
        world.decider,
        world.subject(subject),
        action,
        _resource(world, letter),
        LETTER[letter],
        world.context,
    )
    assert decision.allowed is expected, (
        f"{subject} {action} {letter}: {decision.reason}"
    )
    assert decision.reason


def test_matrix_covers_every_subject_kind(world) -> None:
    kinds = {world.subject(name).kind for name in MATRIX}
    assert kinds == set(SubjectKind)
    assert set(MATRIX) == set(world.subjects)


@pytest.mark.parametrize("letter", list(LETTER))
async def test_self_without_any_assignment(world, letter: str) -> None:
    """Pure "self": own staffing, rate and KPI, and nothing about assignments."""
    resource = (
        Resource.assignment(world.own)
        if letter in "AB"
        else Resource.person(world.solo)
    )
    decision = await decide(
        world.decider,
        world.subject("solo"),
        Action.READ,
        resource,
        LETTER[letter],
        world.context,
    )
    assert decision.allowed is (letter in "CDF")
    if decision.allowed:
        assert decision.reason == "relation:self"


@pytest.mark.parametrize("letter", list(LETTER))
@pytest.mark.parametrize("action", [Action.READ, Action.EDIT])
async def test_relations_do_not_carry_over_to_another_assignment(
    world, letter: str, action: Action
) -> None:
    """Owner, manager and member of one assignment get nothing on another."""
    other_person = uuid4()
    if letter in "AB":
        resource = Resource.assignment(world.other)
    elif letter in "CDE":
        resource = Resource.allocation(world.other, other_person)
    else:
        resource = Resource.person(other_person)
    for name in ("owner", "manager", "colleague", "member", "boss"):
        decision = await decide(
            world.decider,
            world.subject(name),
            action,
            resource,
            LETTER[letter],
            world.context,
        )
        assert not decision.allowed, f"{name} {action} {letter}"


@pytest.mark.parametrize("action", list(Action))
@pytest.mark.parametrize("data_class", [None, *DataClass])
async def test_no_function_and_no_relation_gets_nothing(
    world, action: Action, data_class
) -> None:
    """A subject that holds nothing and relates to nothing is denied everything.

    The one exception is by design: every active person may read rate cards.
    """
    someone = uuid4()
    resources = [
        Resource.assignment(world.own),
        Resource.assignment(None),
        Resource.allocation(world.own, world.member),
        Resource.person(world.member),
        Resource.person(None),
        Resource.quote(world.quote, world.own),
        Resource.cost_item(world.cost_item),
        Resource.cost_item(None),
        Resource.rate_card(),
        Resource.instance(),
    ]
    subjects = [
        Subject.for_person(someone),
        Subject.for_guest(email="nobody@elsewhere.example"),
        Subject.for_guest(),
        Subject.for_peer("peer-unknown"),
        Subject.for_peer(""),
        Subject(SubjectKind.PERSON),
    ]
    for subject in subjects:
        for resource in resources:
            decision = await decide(
                world.decider, subject, action, resource, data_class, world.context
            )
            rate_card_read = (
                subject.kind is SubjectKind.PERSON
                and subject.person_id is not None
                and action is Action.READ
                and data_class is DataClass.MASTER_DATA
                and resource == Resource.rate_card()
            )
            assert decision.allowed is rate_card_read, (
                f"{subject} {action} {resource} {data_class}"
            )


async def test_functions_and_relations_add_up(world) -> None:
    """A planner who is also line manager has the rights of both."""
    boss = world.subject("boss")
    both = Subject.for_person(boss.person_id, {"planner"})
    allocation = Resource.allocation(world.own, world.member)
    assert await decide(
        world.decider, both, Action.EDIT, allocation, DataClass.STAFFING, world.context
    )
    assert await decide(
        world.decider,
        both,
        Action.READ,
        allocation,
        DataClass.PERSON_RATE,
        world.context,
    )
    assert await decide(
        world.decider,
        both,
        Action.READ,
        Resource.person(world.member),
        DataClass.PERSON_KPI,
        world.context,
    )
    assert not await decide(
        world.decider,
        both,
        Action.READ,
        Resource.assignment(world.own),
        DataClass.ASSIGNMENT_FINANCIAL,
        world.context,
    )
