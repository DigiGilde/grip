"""Who takes a typed text out of a moment of an assignment (ADR 0057)."""

from grip.access import Action, DataClass, Resource, decide
from tests.access.test_rules import ALL_SUBJECTS


async def _allowed(world, resource: Resource) -> set[str]:
    return {
        name
        for name in ALL_SUBJECTS
        if await decide(
            world.decider,
            world.subject(name),
            Action.RESTATE_FACT,
            resource,
            None,
            world.context,
        )
    }


async def test_only_the_beheerder_takes_a_text_out(world) -> None:
    # Not who runs the case: the record of a case is not theirs to rewrite.
    assert await _allowed(world, Resource.assignment(world.own)) == {"beheerder"}
    assert await _allowed(world, Resource.assignment(world.other)) == {"beheerder"}


async def test_taking_a_text_out_needs_one_assignment(world) -> None:
    assert await _allowed(world, Resource.assignment(None)) == set()
    assert await _allowed(world, Resource.quote(world.quote, world.own)) == set()
    assert await _allowed(world, Resource.person(world.member)) == set()


async def test_taking_a_text_out_is_no_right_to_edit(world) -> None:
    beheerder = world.subject("beheerder")
    resource = Resource.assignment(world.other)
    decision = await decide(world.decider, beheerder, Action.RESTATE_FACT, resource)
    assert decision.allowed and decision.reason == "function:beheerder"
    assert not await decide(
        world.decider, beheerder, Action.EDIT, resource, DataClass.ASSIGNMENT_BASIC
    )
