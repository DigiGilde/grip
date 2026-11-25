"""Who closes, reopens or keeps open the dossier of an assignment (ADR 0057)."""

from grip.access import Action, DataClass, Resource, Subject, decide
from tests.access.test_rules import ALL_SUBJECTS


async def _allowed(world, resource: Resource) -> set[str]:
    return {
        name
        for name in ALL_SUBJECTS
        if await decide(
            world.decider,
            world.subject(name),
            Action.CLOSE_DOSSIER,
            resource,
            None,
            world.context,
        )
    }


async def test_the_owner_a_manager_and_the_beheerder_close_a_dossier(world) -> None:
    assert await _allowed(world, Resource.assignment(world.own)) == {
        "beheerder",
        "owner",
        "manager",
    }
    # Nobody in the cast relates to this one: only the beheerder, by function.
    assert await _allowed(world, Resource.assignment(world.other)) == {"beheerder"}


async def test_closing_a_dossier_needs_one_assignment(world) -> None:
    assert await _allowed(world, Resource.assignment(None)) == set()
    assert await _allowed(world, Resource.person(world.member)) == set()


async def test_the_reason_names_the_relation_before_the_function(world) -> None:
    from grip.access import BEHEERDER

    own = Resource.assignment(world.own)
    manager = world.subject("manager")
    both = Subject.for_person(manager.person_id, {BEHEERDER})
    decision = await decide(world.decider, both, Action.CLOSE_DOSSIER, own)
    assert decision.allowed and decision.reason == "relation:manager"
    alone = await decide(
        world.decider,
        world.subject("beheerder"),
        Action.CLOSE_DOSSIER,
        Resource.assignment(world.other),
    )
    assert alone.reason == "function:beheerder"


async def test_closing_a_dossier_is_no_right_to_edit_it(world) -> None:
    beheerder = world.subject("beheerder")
    resource = Resource.assignment(world.other)
    assert await decide(world.decider, beheerder, Action.CLOSE_DOSSIER, resource)
    assert not await decide(
        world.decider, beheerder, Action.EDIT, resource, DataClass.ASSIGNMENT_BASIC
    )
