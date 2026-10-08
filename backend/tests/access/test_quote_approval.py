"""The access rules for the internal approval of a quote: the whole matrix."""

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
    Resource,
    Subject,
    decide,
)
from grip.access.quote_approval import OFFERTEGOEDKEURDER, quote_resource

ALL_CLASSES = (
    DataClass.ASSIGNMENT_BASIC,
    DataClass.ASSIGNMENT_FINANCIAL,
    DataClass.STAFFING,
    DataClass.PERSON_RATE,
    DataClass.PERSON_COST,
    DataClass.PERSON_KPI,
)
A, B = DataClass.ASSIGNMENT_BASIC, DataClass.ASSIGNMENT_FINANCIAL


class World:
    def __init__(self) -> None:
        self.assignment = uuid4()
        self.quote = uuid4()
        self.owner, self.manager, self.member = uuid4(), uuid4(), uuid4()
        self.relations = InMemoryRelationSource(
            assignment_roles={
                (self.owner, self.assignment): AssignmentRole.OWNER,
                (self.manager, self.assignment): AssignmentRole.MANAGER,
            },
            allocations=[(self.member, self.assignment, date(2026, 1, 1), None)],
        )
        self.decider = LocalDecider(self.relations)
        self.subjects = {
            "goedkeurder": Subject.for_person(uuid4(), {OFFERTEGOEDKEURDER}),
            "beheerder": Subject.for_person(uuid4(), {"beheerder"}),
            "planner": Subject.for_person(uuid4(), {"planner"}),
            "lezer": Subject.for_person(uuid4(), {"lezer"}),
            "aanvrager": Subject.for_person(uuid4(), {"aanvrager"}),
            "tekenbevoegde": Subject.for_person(uuid4(), {"tekenbevoegde"}),
            "owner": Subject.for_person(self.owner),
            "manager": Subject.for_person(self.manager),
            "member": Subject.for_person(self.member),
            "nobody": Subject.for_person(uuid4()),
            "guest": Subject.for_guest(email="gast@klant.example"),
            "peer": Subject.for_peer("00000000000000000010"),
        }

    def quote_asked(self) -> Resource:
        return quote_resource(self.quote, self.assignment, approval_requested=True)

    def quote_not_asked(self) -> Resource:
        return quote_resource(self.quote, self.assignment, approval_requested=False)

    async def may(self, who, action, resource, data_class=None) -> bool:
        decision = await decide(
            self.decider, self.subjects[who], action, resource, data_class
        )
        return decision.allowed


@pytest.fixture
def world() -> World:
    return World()


SUBJECTS = (
    "goedkeurder",
    "beheerder",
    "planner",
    "lezer",
    "aanvrager",
    "tekenbevoegde",
    "owner",
    "manager",
    "member",
    "nobody",
    "guest",
    "peer",
)


async def test_only_the_holder_of_the_right_decides(world):
    for who in SUBJECTS:
        allowed = await world.may(
            who, Action.DECIDE_QUOTE_APPROVAL, world.quote_asked()
        )
        assert allowed is (who == "goedkeurder"), who


async def test_only_owner_and_manager_ask(world):
    for who in SUBJECTS:
        allowed = await world.may(
            who, Action.REQUEST_QUOTE_APPROVAL, world.quote_asked()
        )
        assert allowed is (who in ("owner", "manager")), who


async def test_the_approver_reads_a_and_b_of_a_quote_put_before_an_approver(world):
    for data_class in ALL_CLASSES:
        allowed = await world.may(
            "goedkeurder", Action.READ, world.quote_asked(), data_class
        )
        assert allowed is (data_class in (A, B)), data_class


async def test_the_approver_reads_nothing_of_a_quote_nobody_asked_about(world):
    for data_class in ALL_CLASSES:
        assert not await world.may(
            "goedkeurder", Action.READ, world.quote_not_asked(), data_class
        ), data_class


async def test_the_right_opens_nothing_else_of_the_assignment(world):
    assignment = Resource.assignment(world.assignment)
    for data_class in ALL_CLASSES:
        assert not await world.may("goedkeurder", Action.READ, assignment, data_class)
    for action in (
        Action.EDIT,
        Action.ISSUE_QUOTE,
        Action.ACCEPT_QUOTE,
        Action.CLOSE_MONTH,
        Action.REQUEST_QUOTE_APPROVAL,
    ):
        assert not await world.may("goedkeurder", action, world.quote_asked(), A)
    allocation = Resource.allocation(world.assignment, world.member)
    assert not await world.may(
        "goedkeurder", Action.READ, allocation, DataClass.STAFFING
    )


async def test_the_rule_changes_nothing_for_who_could_already_read(world):
    """With or without the fact, the matrix answers as before for the others."""
    for who in SUBJECTS:
        if who == "goedkeurder":
            continue
        for data_class in ALL_CLASSES:
            with_fact = await world.may(
                who, Action.READ, world.quote_asked(), data_class
            )
            without = await world.may(
                who,
                Action.READ,
                Resource.quote(world.quote, world.assignment),
                data_class,
            )
            assert with_fact is without, (who, data_class)


async def test_actions_need_a_quote(world):
    assignment = Resource.assignment(world.assignment)
    assert not await world.may("goedkeurder", Action.DECIDE_QUOTE_APPROVAL, assignment)
    assert not await world.may("owner", Action.REQUEST_QUOTE_APPROVAL, assignment)


async def test_reason_names_the_right(world):
    decision = await decide(
        world.decider,
        world.subjects["goedkeurder"],
        Action.DECIDE_QUOTE_APPROVAL,
        world.quote_asked(),
    )
    assert decision.reason == f"function:{OFFERTEGOEDKEURDER}"
