"""The reasoning behind the matrix, and the actions that are not read or edit."""

from datetime import date
from uuid import uuid4

import pytest

from grip.access import (
    AccessRequest,
    Action,
    Context,
    DataClass,
    Decision,
    Resource,
    Subject,
    decide,
    permitted_classes,
)
from grip.models import role as role_model


async def _read(
    world,
    subject: str,
    resource: Resource,
    data_class: DataClass,
    context: Context | None = None,
):
    return await decide(
        world.decider,
        world.subject(subject),
        Action.READ,
        resource,
        data_class,
        context or world.context,
    )


def test_function_ids_match_the_seeded_roles() -> None:
    from grip.access import AANVRAGER, BEHEERDER, LEZER, PLANNER, TEKENBEVOEGDE

    assert {BEHEERDER, PLANNER, LEZER, AANVRAGER, TEKENBEVOEGDE} == set(
        role_model.FUNCTIONS
    )


# --- planner ---------------------------------------------------------------


async def test_planner_sees_no_amounts_and_no_category(world) -> None:
    allocation = Resource.allocation(world.own, world.member)
    assert not await _read(world, "planner", allocation, DataClass.PERSON_RATE)
    assert not await _read(world, "planner", allocation, DataClass.PERSON_COST)
    assert not await _read(
        world, "planner", Resource.assignment(world.own), DataClass.ASSIGNMENT_FINANCIAL
    )
    assert not await _read(
        world, "planner", Resource.person(world.member), DataClass.PERSON_KPI
    )


async def test_planner_gets_the_mismatch_signal_without_the_category(world) -> None:
    allocation = Resource.allocation(world.own, world.member)
    signal = await _read(world, "planner", allocation, DataClass.RATE_MISMATCH_SIGNAL)
    assert signal.allowed and signal.reason == "function:planner"
    assert not await _read(world, "planner", allocation, DataClass.PERSON_RATE)


async def test_mismatch_signal_follows_from_the_rate_class(world) -> None:
    allocation = Resource.allocation(world.own, world.member)
    for name in ("beheerder", "owner", "manager", "boss", "member"):
        assert await _read(world, name, allocation, DataClass.RATE_MISMATCH_SIGNAL), (
            name
        )
    for name in (
        "lezer",
        "colleague",
        "outsider",
        "peer_client",
        "peer_parent",
        "guest",
    ):
        assert not await _read(
            world, name, allocation, DataClass.RATE_MISMATCH_SIGNAL
        ), name


async def test_planner_edits_staffing_everywhere(world) -> None:
    planner = world.subject("planner")
    for assignment in (world.own, world.other):
        assert await decide(
            world.decider,
            planner,
            Action.EDIT,
            Resource.assignment(assignment),
            DataClass.STAFFING,
            world.context,
        )


# --- member ----------------------------------------------------------------


async def test_member_sees_the_roster_but_no_percentages_and_no_money(world) -> None:
    team = Resource.assignment(world.own)
    roster = await _read(world, "colleague", team, DataClass.STAFFING_ROSTER)
    assert roster.allowed and roster.reason == "relation:member"
    assert not await _read(world, "colleague", team, DataClass.STAFFING)
    assert not await _read(world, "colleague", team, DataClass.STAFFING_COUNTS)
    assert not await _read(world, "colleague", team, DataClass.ASSIGNMENT_FINANCIAL)
    assert not await _read(
        world,
        "colleague",
        Resource.allocation(world.own, world.member),
        DataClass.PERSON_RATE,
    )


async def test_membership_ends_with_the_allocation(world) -> None:
    team = Resource.assignment(world.own)
    assert not await _read(world, "former", team, DataClass.ASSIGNMENT_BASIC)
    assert not await _read(world, "former", team, DataClass.STAFFING_ROSTER)
    back_then = Context(today=date(2025, 6, 1))
    assert await _read(world, "former", team, DataClass.ASSIGNMENT_BASIC, back_then)


async def test_roster_is_implied_by_full_staffing(world) -> None:
    team = Resource.assignment(world.own)
    for name in ("beheerder", "planner", "owner", "manager"):
        assert await _read(world, name, team, DataClass.STAFFING_ROSTER), name
        assert await _read(world, name, team, DataClass.STAFFING_COUNTS), name
    assert not await _read(world, "lezer", team, DataClass.STAFFING_ROSTER)
    assert not await _read(world, "lezer", team, DataClass.STAFFING_COUNTS)


# --- owner and manager -----------------------------------------------------


async def test_owner_cannot_read_the_kpi_of_someone_on_the_assignment(world) -> None:
    for resource in (
        Resource.person(world.member),
        Resource.allocation(world.own, world.member),
    ):
        for name in ("owner", "manager"):
            assert not await _read(world, name, resource, DataClass.PERSON_KPI)


async def test_owner_reads_rate_only_of_people_on_the_own_assignment(world) -> None:
    assert await _read(
        world,
        "owner",
        Resource.allocation(world.own, world.member),
        DataClass.PERSON_RATE,
    )
    not_staffed = await _read(
        world,
        "owner",
        Resource.allocation(world.own, world.solo),
        DataClass.PERSON_RATE,
    )
    assert not not_staffed.allowed and not_staffed.reason == "not_allocated"
    # Outside the context of the assignment there is no relation at all.
    assert not await _read(
        world, "owner", Resource.person(world.member), DataClass.PERSON_RATE
    )
    # The whole assignment at once: every row is someone staffed on it.
    assert await _read(
        world, "owner", Resource.assignment(world.own), DataClass.PERSON_RATE
    )


async def test_cost_and_margin_only_for_people_staffed_in_the_period_shown(
    world,
) -> None:
    member = Resource.allocation(world.own, world.member)
    former = Resource.allocation(world.own, world.former)

    assert await _read(world, "owner", member, DataClass.PERSON_COST)

    now = await _read(world, "owner", former, DataClass.PERSON_COST)
    assert not now.allowed and now.reason == "not_allocated_in_period"

    last_year = Context(
        today=world.context.today, period=(date(2025, 1, 1), date(2025, 12, 31))
    )
    assert await _read(world, "owner", former, DataClass.PERSON_COST, last_year)

    next_year = Context(
        today=world.context.today, period=(date(2027, 1, 1), date(2027, 12, 31))
    )
    assert not await _read(world, "owner", member, DataClass.PERSON_COST, next_year)

    whole = await _read(
        world, "owner", Resource.assignment(world.own), DataClass.PERSON_COST
    )
    assert not whole.allowed and whole.reason == "person_required"

    for name in ("boss", "member", "planner", "lezer", "colleague"):
        assert not await _read(world, name, member, DataClass.PERSON_COST), name


async def test_person_master_data_is_not_changed_with_edit(world) -> None:
    for name in ("beheerder", "owner", "boss", "member"):
        for data_class in (
            DataClass.PERSON_RATE,
            DataClass.PERSON_COST,
            DataClass.PERSON_KPI,
        ):
            decision = await decide(
                world.decider,
                world.subject(name),
                Action.EDIT,
                Resource.person(world.member),
                data_class,
            )
            assert not decision.allowed and decision.reason == "use_manage_users"


# --- line manager and self -------------------------------------------------


async def test_line_manager_reads_own_staff_only(world) -> None:
    for data_class in (DataClass.STAFFING, DataClass.PERSON_RATE, DataClass.PERSON_KPI):
        assert await _read(world, "boss", Resource.person(world.member), data_class)
        assert await _read(world, "boss", Resource.person(world.solo), data_class)
        assert not await _read(world, "boss", Resource.person(world.former), data_class)
        assert not await _read(world, "boss", Resource.person(None), data_class)
    assert not await _read(
        world, "boss", Resource.person(world.member), DataClass.PERSON_COST
    )


async def test_nobody_reads_the_kpi_of_a_colleague(world) -> None:
    for name in (
        "colleague",
        "planner",
        "lezer",
        "owner",
        "manager",
        "outsider",
        "solo",
    ):
        assert not await _read(
            world, name, Resource.person(world.member), DataClass.PERSON_KPI
        ), name


# --- person directory, cost items, rate cards ------------------------------


async def test_names_are_readable_by_whoever_staffs(world) -> None:
    anyone = Resource.person(None)
    for name in ("beheerder", "planner", "owner", "manager"):
        assert await _read(world, name, anyone, DataClass.STAFFING_ROSTER), name
    for name in ("lezer", "colleague", "outsider", "aanvrager", "tekenbevoegde"):
        assert not await _read(world, name, anyone, DataClass.STAFFING_ROSTER), name


async def test_cost_items(world) -> None:
    covered = Resource.cost_item(world.cost_item)
    elsewhere = Resource.cost_item(world.other_cost_item)
    financial = DataClass.ASSIGNMENT_FINANCIAL
    for name in ("beheerder", "lezer", "owner", "manager"):
        assert await _read(world, name, covered, financial), name
    for name in ("planner", "colleague", "boss", "outsider"):
        assert not await _read(world, name, covered, financial), name
    assert not await _read(world, "owner", elsewhere, financial)

    edit = Action.EDIT
    assert await decide(world.decider, world.subject("owner"), edit, covered, financial)
    assert await decide(
        world.decider, world.subject("owner"), edit, Resource.cost_item(None), financial
    )
    assert not await decide(
        world.decider, world.subject("owner"), edit, elsewhere, financial
    )
    assert not await decide(
        world.decider, world.subject("beheerder"), edit, covered, financial
    )
    assert not await decide(
        world.decider, world.subject("lezer"), edit, covered, financial
    )


async def test_rate_cards(world) -> None:
    card = Resource.rate_card()
    for name in ("beheerder", "lezer", "planner", "owner", "colleague", "outsider"):
        assert await _read(world, name, card, DataClass.MASTER_DATA), name
        expected = name == "beheerder"
        assert (
            await decide(world.decider, world.subject(name), Action.MANAGE_RATES, card)
        ).allowed is expected
        assert not await decide(
            world.decider, world.subject(name), Action.EDIT, card, DataClass.MASTER_DATA
        )
    for name in ("guest", "peer_client", "peer_parent"):
        assert not await _read(world, name, card, DataClass.MASTER_DATA), name


# --- specific actions ------------------------------------------------------

ALL_SUBJECTS = [
    "beheerder",
    "lezer",
    "planner",
    "aanvrager",
    "tekenbevoegde",
    "owner",
    "manager",
    "member",
    "colleague",
    "boss",
    "solo",
    "former",
    "outsider",
    "guest",
    "uninvited_guest",
    "peer_client",
    "peer_contractor",
    "peer_stranger",
    "peer_parent",
    "peer_child",
    "peer_corpus",
    "peer_unknown",
]


async def _allowed_subjects(world, action: Action, resource: Resource) -> set[str]:
    return {
        name
        for name in ALL_SUBJECTS
        if await decide(
            world.decider, world.subject(name), action, resource, None, world.context
        )
    }


async def test_subject_list_is_complete(world) -> None:
    assert set(ALL_SUBJECTS) == set(world.subjects)


async def test_manage_users_and_rates_are_for_the_beheerder(world) -> None:
    assert await _allowed_subjects(
        world, Action.MANAGE_USERS, Resource.person(world.member)
    ) == {"beheerder"}
    assert await _allowed_subjects(world, Action.MANAGE_USERS, Resource.instance()) == {
        "beheerder"
    }
    assert await _allowed_subjects(
        world, Action.MANAGE_RATES, Resource.rate_card()
    ) == {"beheerder"}


async def test_month_close(world) -> None:
    own = Resource.assignment(world.own)
    assert await _allowed_subjects(world, Action.CLOSE_MONTH, own) == {
        "owner",
        "manager",
    }
    assert (
        await _allowed_subjects(
            world, Action.CLOSE_MONTH, Resource.assignment(world.other)
        )
        == set()
    )
    assert await _allowed_subjects(world, Action.REOPEN_MONTH, own) == {"beheerder"}


async def test_create_and_request_assignment(world) -> None:
    new = Resource.assignment(None)
    assert await _allowed_subjects(world, Action.CREATE_ASSIGNMENT, new) == {
        "beheerder",
        "planner",
        "owner",
        "manager",
    }
    assert await _allowed_subjects(world, Action.REQUEST_ASSIGNMENT, new) == {
        "aanvrager",
        "peer_client",
        "peer_contractor",
        "peer_stranger",
    }


async def test_issue_quote_and_deliver_report(world) -> None:
    own = Resource.quote(None, world.own)
    assert await _allowed_subjects(world, Action.ISSUE_QUOTE, own) == {
        "owner",
        "manager",
    }
    assert await _allowed_subjects(
        world, Action.DELIVER_REPORT, Resource.assignment(world.own)
    ) == {
        "owner",
        "manager",
    }
    # Incoming: only the contractor of that assignment pushes a quote or a report.
    commissioned = Resource.quote(None, world.commissioned)
    assert await _allowed_subjects(world, Action.ISSUE_QUOTE, commissioned) == {
        "peer_contractor"
    }
    assert await _allowed_subjects(
        world, Action.DELIVER_REPORT, Resource.assignment(world.commissioned)
    ) == {"peer_contractor"}
    # A quote on the contractor's initiative: any registered counterpart.
    unsolicited = Resource.quote(None, None)
    assert await _allowed_subjects(world, Action.ISSUE_QUOTE, unsolicited) == {
        "peer_client",
        "peer_contractor",
        "peer_stranger",
    }
    assert (
        await _allowed_subjects(world, Action.DELIVER_REPORT, Resource.assignment(None))
        == set()
    )


async def test_accept_quote(world) -> None:
    # A quote this instance issued: the client signs, as peer or as guest.
    issued = Resource.quote(world.quote, world.own)
    assert await _allowed_subjects(world, Action.ACCEPT_QUOTE, issued) == {
        "guest",
        "peer_client",
    }
    # A quote this instance received: its own tekenbevoegde signs.
    received = Resource.quote(world.commissioned_quote, world.commissioned)
    assert await _allowed_subjects(world, Action.ACCEPT_QUOTE, received) == {
        "tekenbevoegde"
    }
    # Without a quote there is nothing to accept.
    assert (
        await _allowed_subjects(
            world, Action.ACCEPT_QUOTE, Resource.assignment(world.commissioned)
        )
        == set()
    )


async def test_tekenbevoegde_reads_a_received_quote_in_full(world) -> None:
    received = Resource.quote(world.commissioned_quote, world.commissioned)
    assert await _read(world, "tekenbevoegde", received, DataClass.ASSIGNMENT_BASIC)
    assert await _read(world, "tekenbevoegde", received, DataClass.ASSIGNMENT_FINANCIAL)
    issued = Resource.quote(world.quote, world.own)
    assert not await _read(world, "tekenbevoegde", issued, DataClass.ASSIGNMENT_BASIC)
    assert not await _read(
        world,
        "tekenbevoegde",
        Resource.assignment(world.commissioned),
        DataClass.STAFFING,
    )


# --- guest -----------------------------------------------------------------


async def test_guest_sees_and_signs_exactly_one_quote(world) -> None:
    invited = Resource.quote(world.quote, world.own)
    for data_class in (DataClass.ASSIGNMENT_BASIC, DataClass.ASSIGNMENT_FINANCIAL):
        decision = await _read(world, "guest", invited, data_class)
        assert decision.allowed and decision.reason == "relation:guest_signer"
    for data_class in set(DataClass) - {
        DataClass.ASSIGNMENT_BASIC,
        DataClass.ASSIGNMENT_FINANCIAL,
    }:
        assert not await _read(world, "guest", invited, data_class), data_class

    other_quote = Resource.quote(uuid4(), world.own)
    assert not await _read(world, "guest", other_quote, DataClass.ASSIGNMENT_BASIC)
    assert not await decide(
        world.decider, world.subject("guest"), Action.ACCEPT_QUOTE, other_quote
    )
    assert not await _read(
        world, "guest", Resource.assignment(world.own), DataClass.ASSIGNMENT_BASIC
    )
    for action in set(Action) - {Action.READ, Action.ACCEPT_QUOTE}:
        assert not await decide(
            world.decider,
            world.subject("guest"),
            action,
            invited,
            DataClass.ASSIGNMENT_BASIC,
        ), action


async def test_guest_is_matched_on_invitation_or_email(world) -> None:
    invited = Resource.quote(world.quote, world.own)
    by_email = Subject.for_guest(email="SIGNER@client.example")
    by_invitation = Subject.for_guest(invitation_id=world.invitation)
    stranger = Subject.for_guest(email="signer@other.example", invitation_id=uuid4())
    assert await decide(world.decider, by_email, Action.ACCEPT_QUOTE, invited)
    assert await decide(world.decider, by_invitation, Action.ACCEPT_QUOTE, invited)
    assert not await decide(world.decider, stranger, Action.ACCEPT_QUOTE, invited)
    assert not await decide(
        world.decider, Subject.for_guest(), Action.ACCEPT_QUOTE, invited
    )


# --- peers -----------------------------------------------------------------

PERSONAL = [
    DataClass.STAFFING,
    DataClass.STAFFING_ROSTER,
    DataClass.STAFFING_COUNTS,
    DataClass.PERSON_RATE,
    DataClass.PERSON_COST,
    DataClass.PERSON_KPI,
    DataClass.RATE_MISMATCH_SIGNAL,
    DataClass.MASTER_DATA,
]


@pytest.mark.parametrize("data_class", PERSONAL)
async def test_counterparty_never_gets_classes_c_to_f(
    world, data_class: DataClass
) -> None:
    generous = Context(
        on_request=True, contract_allows_financial=True, parent_may_see_names=True
    )
    for resource in (
        Resource.assignment(world.own),
        Resource.allocation(world.own, world.member),
        Resource.person(world.member),
        Resource.quote(world.quote, world.own),
    ):
        assert not await _read(world, "peer_client", resource, data_class, generous)


async def test_counterparty_gets_financial_data_only_on_request(world) -> None:
    own = Resource.assignment(world.own)
    financial = DataClass.ASSIGNMENT_FINANCIAL

    default = await _read(world, "peer_client", own, financial)
    assert not default.allowed and default.reason == "not_on_request"

    no_contract = await _read(
        world, "peer_client", own, financial, Context(on_request=True)
    )
    assert (
        not no_contract.allowed and no_contract.reason == "contract_excludes_financial"
    )

    not_pulled = await _read(
        world, "peer_client", own, financial, Context(contract_allows_financial=True)
    )
    assert not not_pulled.allowed

    pulled = Context(on_request=True, contract_allows_financial=True)
    assert await _read(world, "peer_client", own, financial, pulled)
    # Only for assignments it is the client of.
    assert not await _read(
        world, "peer_client", Resource.assignment(world.other), financial, pulled
    )
    assert not await _read(
        world,
        "peer_client",
        Resource.assignment(world.other),
        DataClass.ASSIGNMENT_BASIC,
    )
    assert not await _read(
        world, "peer_stranger", own, DataClass.ASSIGNMENT_BASIC, pulled
    )


async def test_no_peer_can_edit(world) -> None:
    for peer in (
        "peer_client",
        "peer_parent",
        "peer_corpus",
        "peer_contractor",
        "peer_child",
    ):
        for data_class in DataClass:
            for resource in (
                Resource.assignment(world.own),
                Resource.allocation(world.own, world.member),
            ):
                assert not await decide(
                    world.decider,
                    world.subject(peer),
                    Action.EDIT,
                    resource,
                    data_class,
                )
        for action in (
            Action.MANAGE_RATES,
            Action.MANAGE_USERS,
            Action.CLOSE_MONTH,
            Action.CREATE_ASSIGNMENT,
        ):
            assert not await decide(
                world.decider,
                world.subject(peer),
                action,
                Resource.assignment(world.own),
            )


async def test_parent_gets_counts_by_default_and_names_only_when_switched_on(
    world,
) -> None:
    own = Resource.assignment(world.own)

    assert await _read(world, "peer_parent", own, DataClass.STAFFING_COUNTS)
    for data_class in (DataClass.STAFFING, DataClass.STAFFING_ROSTER):
        decision = await _read(world, "peer_parent", own, data_class)
        assert not decision.allowed and decision.reason == "names_not_shared"

    with_names = Context(parent_may_see_names=True)
    for data_class in (
        DataClass.STAFFING,
        DataClass.STAFFING_ROSTER,
        DataClass.STAFFING_COUNTS,
    ):
        assert await _read(world, "peer_parent", own, data_class, with_names)
    assert await _read(
        world,
        "peer_parent",
        Resource.allocation(world.own, world.member),
        DataClass.STAFFING,
        with_names,
    )


async def test_parent_reads_a_and_b_of_every_assignment_and_never_d_to_f(world) -> None:
    generous = Context(
        on_request=True, contract_allows_financial=True, parent_may_see_names=True
    )
    for assignment in (world.own, world.other):
        for data_class in (DataClass.ASSIGNMENT_BASIC, DataClass.ASSIGNMENT_FINANCIAL):
            assert await _read(
                world, "peer_parent", Resource.assignment(assignment), data_class
            )
    assert await _read(
        world,
        "peer_parent",
        Resource.cost_item(world.cost_item),
        DataClass.ASSIGNMENT_FINANCIAL,
    )
    assert await _read(
        world, "peer_parent", Resource.instance(), DataClass.STAFFING_COUNTS
    )
    for data_class in (
        DataClass.PERSON_RATE,
        DataClass.PERSON_COST,
        DataClass.PERSON_KPI,
        DataClass.RATE_MISMATCH_SIGNAL,
    ):
        for resource in (
            Resource.allocation(world.own, world.member),
            Resource.person(world.member),
        ):
            decision = await _read(world, "peer_parent", resource, data_class, generous)
            assert not decision.allowed and decision.reason == "class_never_shared"


async def test_child_and_unknown_peers_read_nothing(world) -> None:
    generous = Context(
        on_request=True, contract_allows_financial=True, parent_may_see_names=True
    )
    for peer in ("peer_child", "peer_unknown"):
        for data_class in DataClass:
            assert not await _read(
                world, peer, Resource.assignment(world.own), data_class, generous
            )
    unknown = await _read(
        world,
        "peer_unknown",
        Resource.assignment(world.own),
        DataClass.ASSIGNMENT_BASIC,
    )
    assert unknown.reason == "unknown_peer"


async def test_corpus_peer_reads_basics_of_assignments_that_reference_it(world) -> None:
    generous = Context(on_request=True, contract_allows_financial=True)
    assert await _read(
        world, "peer_corpus", Resource.assignment(world.own), DataClass.ASSIGNMENT_BASIC
    )
    assert not await _read(
        world,
        "peer_corpus",
        Resource.assignment(world.other),
        DataClass.ASSIGNMENT_BASIC,
    )
    assert not await _read(
        world,
        "peer_corpus",
        Resource.assignment(world.own),
        DataClass.ASSIGNMENT_FINANCIAL,
        generous,
    )


# --- shape -----------------------------------------------------------------


async def test_read_and_edit_need_a_data_class(world) -> None:
    for action in (Action.READ, Action.EDIT):
        decision = await decide(
            world.decider,
            world.subject("beheerder"),
            action,
            Resource.assignment(world.own),
        )
        assert not decision.allowed and decision.reason == "data_class_required"


async def test_permitted_classes(world) -> None:
    allocation = Resource.allocation(world.own, world.member)
    wanted = [
        DataClass.STAFFING_ROSTER,
        DataClass.STAFFING,
        DataClass.PERSON_RATE,
        DataClass.PERSON_COST,
        DataClass.PERSON_KPI,
        DataClass.RATE_MISMATCH_SIGNAL,
    ]
    planner = await permitted_classes(
        world.decider, world.subject("planner"), allocation, wanted, world.context
    )
    assert planner == {
        DataClass.STAFFING_ROSTER,
        DataClass.STAFFING,
        DataClass.RATE_MISMATCH_SIGNAL,
    }
    owner = await permitted_classes(
        world.decider, world.subject("owner"), allocation, wanted, world.context
    )
    assert owner == set(wanted) - {DataClass.PERSON_KPI}
    colleague = await permitted_classes(
        world.decider, world.subject("colleague"), allocation, wanted, world.context
    )
    assert colleague == {DataClass.STAFFING_ROSTER}
    editable = await permitted_classes(
        world.decider,
        world.subject("planner"),
        allocation,
        wanted,
        world.context,
        Action.EDIT,
    )
    assert editable == {DataClass.STAFFING}


def test_authzen_shape(world) -> None:
    request = AccessRequest(
        world.subject("planner"),
        Action.READ,
        Resource.allocation(world.own, world.member),
        DataClass.STAFFING,
        Context(
            on_request=True,
            period=(date(2026, 1, 1), date(2026, 12, 31)),
            today=date(2026, 10, 8),
        ),
    )
    body = request.to_authzen()
    assert set(body) == {"subject", "action", "resource", "context"}
    assert body["subject"] == {
        "type": "person",
        "id": str(world.subject("planner").person_id),
        "properties": {"functions": ["planner"]},
    }
    assert body["action"] == {"name": "read"}
    assert body["resource"]["type"] == "allocation"
    assert body["resource"]["properties"] == {
        "data_class": "staffing",
        "assignment_id": str(world.own),
        "person_id": str(world.member),
    }
    assert body["context"]["on_request"] is True
    assert body["context"]["period"] == ["2026-01-01", "2026-12-31"]

    peer = AccessRequest(
        world.subject("peer_client"), Action.READ, Resource.assignment(world.own)
    ).to_authzen()
    assert peer["subject"] == {"type": "peer", "id": "peer-client", "properties": {}}

    assert Decision(True, "relation:owner").to_authzen() == {
        "decision": True,
        "context": {"reason": "relation:owner"},
    }
    assert Decision.from_authzen({"decision": True}) == Decision(True, "external_allow")
    assert Decision.from_authzen(
        {"decision": False, "context": {"reason": "nope"}}
    ) == Decision(False, "nope")
    # Anything but an explicit true denies.
    assert not Decision.from_authzen({"decision": "true"}).allowed
    assert not Decision.from_authzen({}).allowed


async def test_an_external_decider_can_replace_the_local_one(world) -> None:
    class Refuser:
        def __init__(self) -> None:
            self.seen: list[dict] = []

        async def evaluate(self, request: AccessRequest) -> Decision:
            self.seen.append(request.to_authzen())
            return Decision.from_authzen(
                {"decision": False, "context": {"reason": "external"}}
            )

    external = Refuser()
    decision = await decide(
        external,
        world.subject("beheerder"),
        Action.READ,
        Resource.assignment(world.own),
        DataClass.ASSIGNMENT_BASIC,
    )
    assert not decision.allowed and decision.reason == "external"
    assert (
        external.seen[0]["resource"]["properties"]["data_class"] == "assignment_basic"
    )
