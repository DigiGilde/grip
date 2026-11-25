"""Who closes, keeps open or reopens the dossier of an assignment (ADR 0057)."""

from grip.access import Action, DataClass, Resource, Subject, decide
from tests.access.test_rules import ALL_SUBJECTS


async def _allowed(
    world, resource: Resource, action: Action = Action.CLOSE_DOSSIER
) -> set[str]:
    return {
        name
        for name in ALL_SUBJECTS
        if await decide(
            world.decider,
            world.subject(name),
            action,
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


# --- reopening ---------------------------------------------------------------


async def test_only_the_beheerder_reopens_a_dossier(world) -> None:
    for assignment_id in (world.own, world.other):
        resource = Resource.assignment(assignment_id)
        assert await _allowed(world, resource, Action.REOPEN_DOSSIER) == {"beheerder"}


async def test_the_owner_and_a_manager_close_but_do_not_reopen(world) -> None:
    own = Resource.assignment(world.own)
    for name in ("owner", "manager"):
        subject = world.subject(name)
        assert await decide(world.decider, subject, Action.CLOSE_DOSSIER, own), name
        refused = await decide(world.decider, subject, Action.REOPEN_DOSSIER, own)
        assert not refused.allowed and refused.reason == "no_grant", name


async def test_the_beheerder_reopens_on_the_function(world) -> None:
    from grip.access import BEHEERDER

    own = Resource.assignment(world.own)
    decision = await decide(
        world.decider, world.subject("beheerder"), Action.REOPEN_DOSSIER, own
    )
    assert decision.allowed and decision.reason == "function:beheerder"
    # Managing the assignment as well adds nothing: no relation reopens.
    manager = world.subject("manager")
    both = Subject.for_person(manager.person_id, {BEHEERDER})
    decision = await decide(world.decider, both, Action.REOPEN_DOSSIER, own)
    assert decision.allowed and decision.reason == "function:beheerder"


async def test_reopening_a_dossier_needs_one_assignment(world) -> None:
    beheerder = world.subject("beheerder")
    for resource in (
        Resource.assignment(None),
        Resource.quote(world.quote, world.own),
        Resource.person(world.member),
    ):
        decision = await decide(
            world.decider, beheerder, Action.REOPEN_DOSSIER, resource
        )
        assert not decision.allowed and decision.reason == "not_applicable", resource
    nobody = await _allowed(world, Resource.assignment(None), Action.REOPEN_DOSSIER)
    assert nobody == set()


async def test_a_guest_and_a_peer_do_not_reopen(world) -> None:
    own = Resource.assignment(world.own)
    for name, resource in (
        ("guest", own),
        ("guest", Resource.quote(world.quote, world.own)),
        ("peer_client", own),
        ("peer_parent", own),
        ("peer_corpus", own),
    ):
        decision = await decide(
            world.decider,
            world.subject(name),
            Action.REOPEN_DOSSIER,
            resource,
            None,
            world.context,
        )
        assert not decision.allowed, (name, resource)
