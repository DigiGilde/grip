"""Reading as an audit log: per event and per field, through the access model.

The first half states by hand what each kind of reader sees of a fixed set
of events. The second half walks the whole matrix: every reader against an
event of every kind of subject, and checks what the API shows against what
the decision point says, including that nothing can be counted.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from grip.access.decider import LocalDecider, decide
from grip.access.sql import SqlRelationSource
from grip.access.types import Action, DataClass, Resource, ResourceKind, Subject
from grip.core.config import get_settings
from grip.events import stream
from grip.events.classification import SPECS, class_from, spec_for
from grip.models.role import PersonRole
from grip.services import rates

FUNCTIONS = ("aanvrager", "tekenbevoegde", "offertegoedkeurder")


@pytest.fixture
async def cast(db_session, world, create_person):
    """The people of ``world`` plus a line manager and the other functions."""
    people = {
        "beheerder": world.beheerder,
        "planner": world.planner,
        "lezer": world.lezer,
        "owner": world.owner,
        "member": world.member,
        "colleague": world.colleague,
        "outsider": world.outsider,
    }
    chief = await create_person("leiding@example.org", name="Lin Leiding")
    world.member.manager_id = chief.id
    people["line_manager"] = chief
    for function in FUNCTIONS:
        people[function] = await create_person(
            f"{function}@example.org", name=function.title(), functions=[function]
        )
    await db_session.flush()
    return people


@pytest.fixture
async def history(db_session, world):
    """One event of each sort, about the assignment and about the member."""
    a, member = world.assignment.id, world.member.id
    made = {
        "assignment": stream.append(
            db_session,
            subject=("assignment", a),
            action="update",
            old={"name": "Alfa"},
            new={"name": "Alfa II"},
        ),
        "budget_line": stream.append(
            db_session,
            subject=("budget_line", world.line.id),
            action="update",
            old={"amount_cents": 100, "intended_person_id": None},
            new={"amount_cents": 200, "intended_person_id": str(member)},
        ),
        "allocation": stream.append(
            db_session,
            subject=("allocation", world.member_allocation.id),
            action="update",
            old={"fte_pct": "50", "rate_category": "C"},
            new={"fte_pct": "80", "rate_category": "D"},
        ),
        "person_scale": stream.append(
            db_session,
            subject=("person_scale", uuid.uuid4()),
            action="update",
            person_id=member,
            old={"billing_scale": 11},
            new={"billing_scale": 12, "valid_from": "2026-07-01"},
        ),
        "hire": stream.append(
            db_session,
            subject=("hire", uuid.uuid4()),
            action="update",
            person_id=member,
            new={"cost_rate_cents": 9000},
        ),
        "billability_target": stream.append(
            db_session,
            subject=("billability_target", uuid.uuid4()),
            action="update",
            person_id=member,
            new={"target": "80"},
        ),
        "rate_card": stream.append(
            db_session, subject=("rate_card", "2026"), action="update", new={"x": 1}
        ),
        "data.read": stream.append(
            db_session,
            "data.read",
            subject=("person", member),
            person_id=member,
            new={"classes": ["person_rate"]},
            existence_class="person_rate",
            field_classes={"*": "person_rate"},
        ),
        "quote.accepted": stream.append(
            db_session,
            "quote.accepted",
            payload={"quote_id": str(uuid.uuid4()), "assignment_id": str(a)},
        ),
    }
    await db_session.flush()
    return made


async def _read(client, as_person, person, history, **params) -> dict[str, dict]:
    """What this person gets of ``history``, by the key of the fixture."""
    by_seq = {event.seq: key for key, event in history.items()}
    answer = await as_person(person).get("/api/events", params={"limit": 200, **params})
    assert answer.status_code == 200, answer.text
    return {
        by_seq[item["seq"]]: item
        for item in answer.json()["items"]
        if item["seq"] in by_seq
    }


def _values(item: dict) -> dict[str, tuple]:
    return {
        change["field"]: (change["old"], change["new"])
        for change in item["changes"]
        if change["visible"]
    }


def _hidden(item: dict) -> set[str]:
    return {change["field"] for change in item["changes"] if not change["visible"]}


# -- what each reader sees, stated by hand --------------------------------------


async def test_the_beheerder_sees_everything(client, as_person, cast, history):
    seen = await _read(client, as_person, cast["beheerder"], history)
    assert set(seen) == set(history)
    assert all(not _hidden(item) and item["details_visible"] for item in seen.values())
    assert _values(seen["person_scale"])["billing_scale"] == (11, 12)
    assert seen["person_scale"]["person_name"] == "Lot Lid"
    assert seen["assignment"]["actor_kind"] == "system"


async def test_a_planner_knows_a_scale_changed_but_not_from_what_to_what(
    client, as_person, cast, history
):
    seen = await _read(client, as_person, cast["planner"], history)
    assert set(seen) == {
        "assignment",
        "budget_line",
        "allocation",
        "person_scale",
        "hire",
        "quote.accepted",
    }
    scale = seen["person_scale"]
    assert _hidden(scale) == {"billing_scale", "valid_from"} and not _values(scale)
    assert all(c["old"] is None and c["new"] is None for c in scale["changes"])
    assert scale["person_name"] == "Lot Lid"
    assert "11" not in str(scale["changes"]) and "12" not in str(scale["changes"])
    # Staffing yes, the rate on it no; the budget amount no, who is meant yes.
    assert _values(seen["allocation"]) == {"fte_pct": ("50", "80")}
    assert _hidden(seen["allocation"]) == {"rate_category"}
    assert _hidden(seen["budget_line"]) == {"amount_cents"}
    assert "intended_person_id" in _values(seen["budget_line"])
    assert seen["quote.accepted"]["payload"] is None
    assert not seen["hire"]["details_visible"] and _hidden(seen["hire"])


async def test_a_lezer_sees_the_money_and_no_people(client, as_person, cast, history):
    seen = await _read(client, as_person, cast["lezer"], history)
    assert set(seen) == {"assignment", "budget_line", "quote.accepted"}
    assert _values(seen["budget_line"]) == {"amount_cents": (100, 200)}
    assert _hidden(seen["budget_line"]) == {"intended_person_id"}
    assert seen["quote.accepted"]["payload"]["assignment_id"]


async def test_the_owner_sees_the_assignment_and_its_team(
    client, as_person, cast, history
):
    seen = await _read(client, as_person, cast["owner"], history)
    assert set(seen) == {"assignment", "budget_line", "allocation", "quote.accepted"}
    assert not _hidden(seen["budget_line"])
    # The rate of someone staffed on the own assignment.
    assert _values(seen["allocation"])["rate_category"] == ("C", "D")
    assert seen["allocation"]["person_name"] == "Lot Lid"


async def test_a_member_sees_the_own_data_and_little_of_the_assignment(
    client, as_person, cast, history
):
    seen = await _read(client, as_person, cast["member"], history)
    assert set(seen) == {
        "assignment",
        "budget_line",
        "allocation",
        "person_scale",
        "hire",
        "billability_target",
        "data.read",
        "quote.accepted",
    }
    assert _values(seen["person_scale"])["billing_scale"] == (11, 12)
    assert _values(seen["billability_target"]) == {"target": (None, "80")}
    # The own cost rate is not the member's to see.
    assert _hidden(seen["hire"]) == {"cost_rate_cents"}
    assert _hidden(seen["budget_line"]) == {"amount_cents", "intended_person_id"}
    assert seen["quote.accepted"]["payload"] is None
    # Who read my data, and what of it.
    assert _values(seen["data.read"]) == {"classes": (None, ["person_rate"])}


async def test_a_line_manager_sees_what_is_about_their_person(
    client, as_person, cast, history
):
    seen = await _read(client, as_person, cast["line_manager"], history)
    assert set(seen) == {
        "allocation",
        "person_scale",
        "hire",
        "billability_target",
        "data.read",
    }
    assert _values(seen["person_scale"])["billing_scale"] == (11, 12)
    assert _hidden(seen["hire"]) == {"cost_rate_cents"}


@pytest.mark.parametrize("who", ["outsider", "colleague", *FUNCTIONS])
async def test_others_see_nothing_of_it(client, as_person, cast, history, who):
    seen = await _read(client, as_person, cast[who], history)
    expected = (
        # A colleague on the same assignment is a member of it too.
        {"assignment", "budget_line", "quote.accepted"} if who == "colleague" else set()
    )
    assert set(seen) == expected


# -- the views ------------------------------------------------------------------


async def test_the_history_of_a_case(client, as_person, cast, history, world):
    params = {"case_kind": "assignment", "case_id": str(world.assignment.id)}
    seen = await _read(client, as_person, cast["beheerder"], history, **params)
    assert set(seen) == {"assignment", "budget_line", "allocation", "quote.accepted"}
    other = {"case_kind": "assignment", "case_id": str(world.other_assignment.id)}
    assert await _read(client, as_person, cast["beheerder"], history, **other) == {}


async def test_what_was_done_to_a_persons_data_and_by_a_person(
    client, as_person, cast, history, world, db_session
):
    about = {"person_id": str(world.member.id)}
    seen = await _read(client, as_person, cast["beheerder"], history, **about)
    assert set(seen) == {
        "allocation",
        "person_scale",
        "hire",
        "billability_target",
        "data.read",
    }
    # The same question from someone who may not know whose data it is.
    assert await _read(client, as_person, cast["lezer"], history, **about) == {}
    assert await _read(client, as_person, cast["outsider"], history, **about) == {}

    await rates.set_person_scale(
        db_session, world.colleague.id, date(2026, 6, 1), 13, actor=world.beheerder
    )
    await db_session.flush()
    answer = await as_person(cast["beheerder"]).get(
        "/api/events",
        params={"actor_id": str(world.beheerder.id), "type": "person_scale."},
    )
    items = answer.json()["items"]
    assert items and {item["actor_name"] for item in items} == {"Bea Beheer"}
    assert all(item["type"].startswith("person_scale.") for item in items)
    assert str(world.colleague.id) in {item["person_id"] for item in items}


async def test_filters_on_kind_period_and_type(client, as_person, cast, history):
    beheerder = cast["beheerder"]
    kinds = await _read(
        client, as_person, beheerder, history, subject_kind="budget_line"
    )
    assert set(kinds) == {"budget_line"}
    types = await _read(
        client, as_person, beheerder, history, type=["quote.", "rate_card.updated"]
    )
    assert set(types) == {"quote.accepted", "rate_card"}
    assert (
        await _read(client, as_person, beheerder, history, until="2000-01-01T00:00:00Z")
        == {}
    )
    assert set(
        await _read(client, as_person, beheerder, history, since="2000-01-01T00:00:00Z")
    ) == set(history)


async def test_paging_gives_no_total_and_no_trace_of_what_is_hidden(
    client, as_person, cast, history
):
    # Newest first, page by page, each event once.
    seqs: list[int] = []
    before = None
    for _ in range(50):
        params = {"limit": 2, "subject_kind": "rate_card"}
        if before:
            params["before"] = before
        body = (
            await as_person(cast["beheerder"]).get("/api/events", params=params)
        ).json()
        assert set(body) == {"items", "next_before"}
        seqs += [item["seq"] for item in body["items"]]
        before = body["next_before"]
        if before is None:
            break
    assert seqs == sorted(seqs, reverse=True) and len(seqs) == len(set(seqs))
    assert history["rate_card"].seq in seqs

    # A reader who may know of none of it gets exactly what an empty stream
    # gives, whatever is asked for.
    for params in (
        {},
        {"subject_kind": "rate_card"},
        {"person_id": str(history["person_scale"].person_id)},
        {"subject_kind": "person_scale", "limit": 1},
    ):
        answer = await as_person(cast["outsider"]).get("/api/events", params=params)
        assert answer.json() == {"items": [], "next_before": None}


async def test_an_id_that_names_the_person_is_hidden_with_the_person(
    client, as_person, cast, db_session, world
):
    """A budget line event that could tell who was meant: the lezer sees the
    event, not the person."""
    event = stream.append(
        db_session,
        subject=("budget_line", world.line.id),
        action="update",
        person_id=world.member.id,
        new={"intended_person_id": str(world.member.id)},
    )
    await db_session.flush()
    answer = await as_person(cast["lezer"]).get(
        "/api/events", params={"subject_kind": "budget_line", "limit": 200}
    )
    item = next(i for i in answer.json()["items"] if i["seq"] == event.seq)
    assert item["person_id"] is None and item["person_name"] is None
    assert str(world.member.id) not in str(item)


# -- the whole matrix -------------------------------------------------------------

_SENTINEL = "geheim-7f3a"


def _resource(kind: str, world, with_case: bool, with_person: bool) -> Resource:
    """What the model is asked, written out again here on purpose."""
    if kind.startswith("vacancy"):
        raise AssertionError("vacancies are walked in their own test")
    person = world.member.id if with_person else None
    if with_case:
        return Resource(
            ResourceKind.ASSIGNMENT,
            id=world.assignment.id,
            assignment_id=world.assignment.id,
            person_id=person,
        )
    if person is not None:
        return Resource.person(person)
    return {
        ResourceKind.ASSIGNMENT: Resource.assignment(None),
        ResourceKind.COST_ITEM: Resource.cost_item(None),
        ResourceKind.PERSON: Resource.person(None),
        ResourceKind.INSTANCE: Resource.instance(),
    }[spec_for(kind).resource]


async def _allowed(decider, subject, resource, data_class) -> bool:
    if data_class is None:
        answer = await decide(
            decider, subject, Action.MANAGE_USERS, Resource.instance()
        )
    else:
        answer = await decide(decider, subject, Action.READ, resource, data_class)
    return answer.allowed


async def test_every_reader_against_every_kind_of_event(
    client, as_person, cast, db_session, world
):
    kinds = [kind for kind in sorted(SPECS) if not kind.startswith("vacancy")]
    written = {}
    for kind in kinds:
        for with_case in (True, False):
            for with_person in (True, False):
                if (kind, with_case) == ("assignment", False) or (
                    kind,
                    with_person,
                ) == ("person", False):
                    # These are their own case or person: there is no such
                    # event without one.
                    continue
                fields = {
                    "plain": _SENTINEL,
                    **dict.fromkeys(SPECS[kind].fields, _SENTINEL),
                }
                written[kind, with_case, with_person] = stream.append(
                    db_session,
                    subject=(kind, uuid.uuid4()),
                    action="update",
                    assignment_id=world.assignment.id if with_case else None,
                    person_id=world.member.id if with_person else None,
                    new=fields,
                    note=_SENTINEL,
                )
    await db_session.flush()
    by_seq = {event.seq: key for key, event in written.items()}
    decider = LocalDecider(
        SqlRelationSource(
            db_session, instance_base_uri=get_settings().INSTANCE_BASE_URI
        )
    )

    checked = 0
    for who, person in cast.items():
        functions = set(
            await db_session.scalars(
                PersonRole.__table__.select()
                .with_only_columns(PersonRole.role_id)
                .where(PersonRole.person_id == person.id)
            )
        )
        subject = Subject.for_person(person.id, frozenset(functions))
        items: dict[tuple, dict] = {}
        before = None
        while True:
            params = {"limit": 200, **({"before": before} if before else {})}
            body = (await as_person(person).get("/api/events", params=params)).json()
            for item in body["items"]:
                if item["seq"] in by_seq:
                    items[by_seq[item["seq"]]] = item
            before = body["next_before"]
            if before is None or before < min(by_seq):
                break

        for key, event in written.items():
            kind, with_case, with_person = key
            resource = _resource(kind, world, with_case, with_person)
            may_know = await _allowed(
                decider, subject, resource, class_from(event.existence_class)
            )
            assert (key in items) == may_know, (who, key)
            checked += 1
            if not may_know:
                continue
            item = items[key]
            for change in item["changes"]:
                field_class = SPECS[kind].fields.get(
                    change["field"], SPECS[kind].values
                )
                may_see = await _allowed(decider, subject, resource, field_class)
                assert change["visible"] == may_see, (who, key, change["field"])
                assert (change["new"] == _SENTINEL) == may_see
            may_detail = await _allowed(decider, subject, resource, SPECS[kind].values)
            assert (item["note"] == _SENTINEL) == may_detail, (who, key)
            if with_person and person.id != world.member.id:
                may_name = await _allowed(
                    decider, subject, resource, DataClass.STAFFING_ROSTER
                )
                assert (item["person_id"] is not None) == may_name, (who, key)
            # Nothing of a value the reader may not see is anywhere in it.
            hidden_all = not may_detail and not any(
                change["visible"] for change in item["changes"]
            )
            if hidden_all:
                assert _SENTINEL not in str(item), (who, key)
    assert checked == len(cast) * len(written)


async def test_events_of_a_vacancy_follow_the_rules_for_vacancies(
    client, as_person, cast, db_session, world
):
    from grip.services.vacancies import service as vacancies

    vacancy = await vacancies.create_vacancy(
        db_session,
        actor=world.owner,
        function_title="Adviseur",
        fte=Decimal("1"),
        declarable=False,
    )
    await db_session.flush()
    seen = {}
    for who in ("beheerder", "planner", "owner", "lezer", "member", "outsider"):
        answer = await as_person(cast[who]).get(
            "/api/events",
            params={"case_kind": "vacancy", "case_id": str(vacancy.id)},
        )
        seen[who] = answer.json()["items"]
    assert seen["beheerder"]
    assert seen["outsider"] == [] and seen["member"] == []
    created = seen["beheerder"][-1]
    assert created["type"] == "vacancy.created" and created["details_visible"]
    # Without names: a lezer knows the vacancy was made, not what was filled in.
    if seen["lezer"]:
        assert all(not item["details_visible"] for item in seen["lezer"])
        assert all(not c["visible"] for item in seen["lezer"] for c in item["changes"])
