"""The access rules for vacancies, form templates and the language model."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from grip.access import (
    Action,
    AssignmentRole,
    DataClass,
    InMemoryRelationSource,
    LocalDecider,
    Subject,
    decide,
)
from grip.access.vacancies import (
    form_template_resource,
    language_model_resource,
    vacancy_resource,
)

FULL, NO_NAMES, PUBLIC = (
    DataClass.STAFFING,
    DataClass.STAFFING_COUNTS,
    DataClass.OPEN_ROLE,
)


class World:
    def __init__(self) -> None:
        self.assignment = uuid4()
        self.other_assignment = uuid4()
        self.vacancy = uuid4()
        self.owner = uuid4()
        self.manager = uuid4()
        self.member = uuid4()
        self.adviser = uuid4()
        self.relations = InMemoryRelationSource(
            assignment_roles={
                (self.owner, self.assignment): AssignmentRole.OWNER,
                (self.manager, self.assignment): AssignmentRole.MANAGER,
            },
            allocations=[(self.member, self.assignment, date(2026, 1, 1), None)],
        )
        self.decider = LocalDecider(self.relations)
        self.subjects = {
            "beheerder": Subject.for_person(uuid4(), {"beheerder"}),
            "planner": Subject.for_person(uuid4(), {"planner"}),
            "lezer": Subject.for_person(uuid4(), {"lezer"}),
            "aanvrager": Subject.for_person(uuid4(), {"aanvrager"}),
            "tekenbevoegde": Subject.for_person(uuid4(), {"tekenbevoegde"}),
            "owner": Subject.for_person(self.owner),
            "manager": Subject.for_person(self.manager),
            "member": Subject.for_person(self.member),
            "adviser": Subject.for_person(self.adviser),
            "nobody": Subject.for_person(uuid4()),
        }

    def resource(self, *, open_role=False, decision_kind=None, assignment=True):
        return vacancy_resource(
            self.vacancy,
            assignment_id=self.assignment if assignment else None,
            open_role=open_role,
            named={"hr_advice": self.adviser, "approval": None},
            decision_kind=decision_kind,
        )

    async def ask(self, who, action, resource, data_class=None) -> bool:
        return bool(
            await decide(self.decider, self.subjects[who], action, resource, data_class)
        )


@pytest.fixture
def world() -> World:
    return World()


EDITORS = {"beheerder", "planner", "owner", "manager"}
EVERYONE = EDITORS | {
    "lezer",
    "aanvrager",
    "tekenbevoegde",
    "member",
    "adviser",
    "nobody",
}


@pytest.mark.parametrize("who", sorted(EVERYONE))
async def test_edit(world, who) -> None:
    assert await world.ask(who, Action.EDIT, world.resource()) is (who in EDITORS)


@pytest.mark.parametrize("who", sorted(EVERYONE))
async def test_edit_without_budget_line(world, who) -> None:
    """No assignment: only the two functions edit."""
    allowed = who in {"beheerder", "planner"}
    assert (
        await world.ask(who, Action.EDIT, world.resource(assignment=False)) is allowed
    )
    assert await world.ask(who, Action.EDIT, vacancy_resource(None)) is allowed


async def test_manager_of_another_assignment_does_not_edit(world) -> None:
    resource = vacancy_resource(world.vacancy, assignment_id=world.other_assignment)
    assert not await world.ask("owner", Action.EDIT, resource)
    assert not await world.ask("owner", Action.READ, resource, NO_NAMES)


@pytest.mark.parametrize("who", sorted(EVERYONE))
@pytest.mark.parametrize("open_role", [False, True])
async def test_read_views(world, who, open_role) -> None:
    resource = world.resource(open_role=open_role)
    full = who in EDITORS | {"adviser"}
    no_names = full or who == "lezer"
    public = no_names or open_role
    assert await world.ask(who, Action.READ, resource, FULL) is full
    assert await world.ask(who, Action.READ, resource, NO_NAMES) is no_names
    assert await world.ask(who, Action.READ, resource, PUBLIC) is public


@pytest.mark.parametrize("who", sorted(EVERYONE))
async def test_value_lists_for_everyone(world, who) -> None:
    assert await world.ask(
        who, Action.READ, vacancy_resource(None), DataClass.MASTER_DATA
    )


@pytest.mark.parametrize(
    "data_class",
    [
        DataClass.ASSIGNMENT_BASIC,
        DataClass.ASSIGNMENT_FINANCIAL,
        DataClass.PERSON_RATE,
        DataClass.PERSON_COST,
        DataClass.PERSON_KPI,
        DataClass.STAFFING_ROSTER,
        DataClass.RATE_MISMATCH_SIGNAL,
        None,
    ],
)
async def test_other_classes_do_not_apply(world, data_class) -> None:
    for who in EVERYONE:
        assert not await world.ask(who, Action.READ, world.resource(), data_class)


@pytest.mark.parametrize("who", sorted(EVERYONE))
async def test_record_decision(world, who) -> None:
    hr = world.resource(decision_kind="hr_advice")
    approval = world.resource(decision_kind="approval")
    assert await world.ask(who, Action.RECORD_DECISION, hr) is (
        who in {"beheerder", "adviser"}
    )
    # Named for the HR advice is not named for the approval.
    assert await world.ask(who, Action.RECORD_DECISION, approval) is (
        who == "beheerder"
    )


async def test_record_decision_needs_a_kind(world) -> None:
    assert not await world.ask("adviser", Action.RECORD_DECISION, world.resource())
    odd = world.resource(decision_kind="iets_anders")
    assert not await world.ask("adviser", Action.RECORD_DECISION, odd)


@pytest.mark.parametrize("who", sorted(EVERYONE))
@pytest.mark.parametrize("action", [Action.READ, Action.EDIT])
async def test_setup_is_for_the_beheerder(world, who, action) -> None:
    for resource in (form_template_resource(), language_model_resource()):
        allowed = await world.ask(who, action, resource, DataClass.MASTER_DATA)
        assert allowed is (who == "beheerder")


@pytest.mark.parametrize("action", list(Action))
async def test_other_actions_do_not_apply(world, action) -> None:
    if action in (Action.READ, Action.EDIT, Action.RECORD_DECISION):
        return
    for who in EVERYONE - {"beheerder"}:
        assert not await world.ask(who, action, world.resource(open_role=True))
    assert not await world.ask("beheerder", action, world.resource())


async def test_guests_and_peers_get_nothing(world) -> None:
    subjects = [
        Subject.for_guest(email="gast@elders.example"),
        Subject.for_peer("12345678901234567890"),
    ]
    resources = [
        world.resource(open_role=True),
        form_template_resource(),
        language_model_resource(),
    ]
    for subject in subjects:
        for resource in resources:
            for action in Action:
                for data_class in [None, *DataClass]:
                    assert not await decide(
                        world.decider, subject, action, resource, data_class
                    )


def test_facts_travel_as_resource_properties(world) -> None:
    from grip.access import AccessRequest

    request = AccessRequest(
        world.subjects["adviser"],
        Action.RECORD_DECISION,
        world.resource(open_role=True, decision_kind="hr_advice"),
    )
    properties = request.to_authzen()["resource"]["properties"]
    assert properties["open_role"] == "true"
    assert properties["hr_advice_person_id"] == str(world.adviser)
    assert properties["decision_kind"] == "hr_advice"
    assert "approval_person_id" not in properties
