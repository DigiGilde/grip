"""What each reader gets from the start page, over HTTP.

Most tests read the whole body, so a word of a class the reader may not see
fails them wherever in the answer it turns up.
"""

import ast
import inspect
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends
from sqlalchemy import event, func, select

from grip.access import (
    Action,
    LocalDecider,
    field_classes,
    schema_classes,
    unclassified_fields,
)
from grip.access.deps import get_decider, get_relation_source
from grip.access.types import DataClass, deny
from grip.api.routes import start as start_route
from grip.core import clock
from grip.federation.bridge.organisations import own_organisation
from grip.federation.models import FederationOutbox, Peer
from grip.models.stream_event import StreamEvent
from grip.models.task import Task
from grip.schema.start import ConnectionsOut, StartOut
from grip.services import assignments, quotes, rates, read_cache
from grip.services import start as start_service
from grip.services.assignment_parts import BudgetFacts, PartsFacts
from grip.services.reports import investment, steering
from grip.tasks import engine as task_engine
from grip.tasks import service as task_service
from tests.api.reports import conftest as reports_world
from tests.lifecycle import accept

world = reports_world.world
as_person = reports_world.as_person
_no_event_handlers = reports_world._no_event_handlers

URL = "/api/start"
A = DataClass.ASSIGNMENT_BASIC
B = DataClass.ASSIGNMENT_FINANCIAL
C = DataClass.STAFFING


@pytest.fixture(autouse=True)
def _november():
    with clock.at(datetime(2026, 11, 15, 12, 0, tzinfo=UTC)):
        yield


async def _body(as_person, reader) -> dict:
    response = await as_person(reader).get(URL)
    assert response.status_code == 200, response.text
    return response.json()


def _deny(_test_app, refused):
    """Answer with the normal rules, except for what ``refused`` says."""

    class Refuses(LocalDecider):
        async def evaluate(self, request):
            if refused(request):
                return deny("test")
            return await super().evaluate(request)

    def decider(relations=Depends(get_relation_source)):
        return Refuses(relations)

    _test_app.dependency_overrides[get_decider] = decider


# -- the schema ---------------------------------------------------------------


def test_no_sensitive_class_can_be_on_the_start_page():
    classes = schema_classes(StartOut)
    assert not classes & {
        DataClass.PERSON_RATE,
        DataClass.PERSON_COST,
        DataClass.PERSON_KPI,
    }


def test_every_field_has_one_data_class():
    assert unclassified_fields(StartOut) == []


def test_a_number_of_messages_is_no_staffing():
    assert field_classes(ConnectionsOut)["problems"] is DataClass.MASTER_DATA


def test_the_start_route_imports_from_no_other_route():
    tree = ast.parse(inspect.getsource(start_route))
    modules = [
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ]
    assert not [module for module in modules if module.startswith("grip.api.routes")]


async def test_a_visit_writes_no_read_in_the_log(as_person, world, db_session):
    """A judgement about a colleague on Start would log a read on every visit."""

    async def reads() -> int:
        await db_session.flush()
        return await db_session.scalar(
            select(func.count())
            .select_from(StreamEvent)
            .where(StreamEvent.type == "data.read")
        )

    before = await reads()
    for reader in (
        world.leader,
        world.beheerder,
        world.lezer,
        world.planner,
        world.owner,
        world.member,
    ):
        await _body(as_person, reader)
        assert await reads() == before, reader.name


async def test_a_reader_with_nothing_gets_only_the_tasks(as_person, world):
    body = await _body(as_person, world.outsider)
    assert body == {"to_do": {"groups": [], "total": 0}}


# -- what is to do ------------------------------------------------------------


def _view(case_id, due_on=None, *, kind="assignment", subject=None, created=0):
    return SimpleNamespace(
        needs_me=True,
        overdue=due_on is not None and due_on < date(2026, 11, 15),
        task=SimpleNamespace(
            case_kind=kind,
            assignment_id=case_id if kind == "assignment" else None,
            vacancy_id=case_id if kind == "vacancy" else None,
            due_on=due_on,
            subject_kind=subject,
            created=created,
        ),
    )


def test_a_case_is_one_row_with_its_first_task():
    alfa, beta, vacancy = uuid4(), uuid4(), uuid4()
    views = [
        _view(alfa, date(2026, 4, 7)),
        _view(beta, date(2026, 5, 7)),
        _view(alfa),
        _view(vacancy, kind="vacancy"),
        _view(alfa),
    ]
    cases = start_service.cases_of(views)
    assert [case.head for case in cases] == [views[0], views[1], views[3]]
    assert [len(case.rest) for case in cases] == [2, 0, 0]


def test_what_only_looks_on_is_not_to_do():
    view = _view(uuid4())
    view.needs_me = False
    assert start_service.cases_of([view]) == []


def _cases(*dates):
    return start_service.cases_of([_view(uuid4(), due) for due in dates])


def test_the_last_place_goes_to_the_first_case_without_a_date():
    late = [date(2026, 3 + i, 7) for i in range(5)]
    cases = _cases(*late, None, None)
    top = start_service.top_five(cases)
    assert len(top) == 5
    assert [case.head.task.due_on for case in top] == [*late[:4], None]
    assert top[4] is cases[5]


def test_dated_cases_fill_the_top_when_nothing_is_without_a_date():
    late = [date(2026, 3 + i, 7) for i in range(7)]
    top = start_service.top_five(_cases(*late))
    assert [case.head.task.due_on for case in top] == late[:5]


def test_a_case_without_a_date_keeps_the_place_it_has():
    cases = _cases(date(2026, 3, 7), date(2026, 4, 7), None, None, None, None)
    top = start_service.top_five(cases)
    assert top == cases[:5]


@pytest.mark.parametrize(
    ("months", "others", "said"),
    [
        (0, 0, None),
        (7, 0, "daarna nog 7 maanden"),
        (1, 0, "daarna nog 1 maand"),
        (0, 2, "daarna nog 2 taken"),
        (0, 1, "daarna nog 1 taak"),
        (7, 1, "daarna nog 7 maanden en 1 taak"),
    ],
)
def test_the_words_of_what_comes_after(months, others, said):
    assert start_service.more_words(months, others) == said


MONTH = "month_to_close"


def test_the_first_month_is_not_counted_as_what_comes_after():
    alfa = uuid4()
    (case,) = start_service.cases_of(
        [_view(alfa, date(2026, 4, 7), subject=MONTH), _view(alfa)]
    )
    assert start_service.more_text(case, 8) == "daarna nog 7 maanden en 1 taak"


def test_every_month_comes_after_another_first_task():
    alfa = uuid4()
    (case,) = start_service.cases_of(
        [_view(alfa, date(2026, 4, 7)), _view(alfa, date(2026, 5, 7), subject=MONTH)]
    )
    assert start_service.more_text(case, 8) == "daarna nog 8 maanden"


def test_without_a_right_on_the_months_the_month_is_just_a_task():
    alfa = uuid4()
    (case,) = start_service.cases_of(
        [_view(alfa, date(2026, 4, 7)), _view(alfa, date(2026, 5, 7), subject=MONTH)]
    )
    assert start_service.more_text(case, None) == "daarna nog 1 taak"
    (only,) = start_service.cases_of([_view(alfa, date(2026, 4, 7), subject=MONTH)])
    assert start_service.more_text(only, None) is None


async def test_the_owner_hears_the_first_month_and_how_many_follow(
    as_person, world, db_session
):
    body = await _body(as_person, world.owner)
    (group,) = [
        g for g in body["to_do"]["groups"] if g["case_id"] == str(world.alfa.id)
    ]
    assert group["case_kind"] == "assignment"
    assert group["case_label"] == "Opdracht Alfa"
    assert group["headline"] == "Sluit augustus 2026 af"
    assert group["overdue"] is True
    assert group["due_on"] == "2026-09-07"
    # A task leads to the page; it does not open the month there.
    assert group["href"] == f"/opdrachten/{world.alfa.id}/afsluiten"
    assert group["more_text"].startswith("daarna nog 2 maanden")
    assert group["task_id"]


@pytest.mark.parametrize(
    "who", ["owner", "beheerder", "planner", "member", "lezer", "leader"]
)
async def test_the_total_is_the_number_in_the_bar(as_person, world, who):
    reader = getattr(world, who)
    body = await _body(as_person, reader)
    count = (await as_person(reader).get("/api/tasks/count")).json()
    assert body["to_do"]["total"] == count["to_do"]


async def test_five_late_cases_leave_room_for_one_without_a_date(
    as_person, world, db_session, create_person
):
    person = await create_person(
        "veel@example.org", name="Vera Veel", functions=["lezer"]
    )
    made = []
    for index in range(5):
        assignment = await assignments.create_assignment(
            db_session, name=f"Opdracht Laat {index}", actor=world.beheerder
        )
        await task_service.create_manual_task(
            db_session,
            case_kind="assignment",
            case_id=assignment.id,
            title=f"Te laat {index}",
            track=None,
            actor=world.beheerder,
            assignee_person_id=person.id,
            due_on=date(2026, 5, 1 + index),
        )
        made.append(assignment)
    undated = await assignments.create_assignment(
        db_session, name="Opdracht Zonder Datum", actor=world.beheerder
    )
    await task_service.create_manual_task(
        db_session,
        case_kind="assignment",
        case_id=undated.id,
        title="Geen haast",
        track=None,
        actor=world.beheerder,
        assignee_person_id=person.id,
    )
    await db_session.flush()
    to_do = (await _body(as_person, person))["to_do"]
    assert to_do["total"] == 6
    assert [g["headline"] for g in to_do["groups"]] == [
        "Te laat 0",
        "Te laat 1",
        "Te laat 2",
        "Te laat 3",
        "Geen haast",
    ]
    assert [g["overdue"] for g in to_do["groups"]] == [True] * 4 + [False]
    assert to_do["groups"][4]["due_on"] is None


async def test_a_member_with_a_handed_over_month_hears_no_count_and_no_page(
    as_person, world, db_session
):
    """Without B or C the number of months is not theirs, and neither is the
    page where a month is closed: the row leads to the assignment itself."""
    await _body(as_person, world.owner)
    task = await db_session.scalar(
        select(Task).where(
            Task.assignment_id == world.alfa.id, Task.subject_kind == MONTH
        )
    )
    await task_service.assign(db_session, task, world.member.id, actor=world.owner)
    await db_session.flush()

    body = await _body(as_person, world.member)
    (group,) = body["to_do"]["groups"]
    assert group["headline"] == "Sluit augustus 2026 af"
    assert group["more_text"] is None
    assert group["href"] == f"/opdrachten/{world.alfa.id}"
    assert "afsluiten" not in json.dumps(body["to_do"])
    assert "maanden" not in json.dumps(body["to_do"])


# -- my work ------------------------------------------------------------------


async def test_a_member_hears_the_own_inzet_and_nothing_else(as_person, world):
    body = await _body(as_person, world.member)
    assert body["my_work"] == {
        "person_id": str(world.member.id),
        "rows": [
            {
                "assignment_id": str(world.alfa.id),
                "name": "Opdracht Alfa",
                "line": "Productmanager, 100%, tot 30 jun 2027",
                "warning": None,
            }
        ],
        "total": 1,
    }
    for word in (
        "Cas Collega",
        "50%",
        "Developer",
        "my_assignments",
        "planning",
        "my_people",
        "figures",
        "connections",
        "cents",
        "verdict",
    ):
        assert word not in json.dumps(body), word


async def test_who_stops_soon_is_warned_on_the_row_that_ends_last(
    as_person, world, db_session
):
    with clock.at(datetime(2027, 4, 15, 12, 0, tzinfo=UTC)):
        body = await _body(as_person, world.member)
    (row,) = body["my_work"]["rows"]
    assert row["warning"] == "Geen inzet vanaf juli 2027"


async def test_who_stops_after_the_coming_months_is_not_warned(as_person, world):
    with clock.at(datetime(2027, 2, 15, 12, 0, tzinfo=UTC)):
        body = await _body(as_person, world.member)
    assert body["my_work"]["rows"][0]["warning"] is None


async def test_ended_inzet_is_no_work(as_person, world, db_session):
    world.member_allocation.end_date = date(2026, 10, 31)
    await db_session.flush()
    assert "my_work" not in await _body(as_person, world.member)


@pytest.mark.parametrize("who", ["outsider", "lezer", "planner", "beheerder", "owner"])
async def test_without_own_inzet_there_is_no_work(as_person, world, who):
    assert "my_work" not in await _body(as_person, getattr(world, who))


async def test_my_work_needs_the_staffing_class_on_the_own_inzet(
    as_person, world, _test_app
):
    _deny(_test_app, lambda request: request.data_class is C)
    body = await _body(as_person, world.member)
    assert "my_work" not in body
    assert "100%" not in json.dumps(body)


# -- my assignments -----------------------------------------------------------


async def test_the_owner_gets_a_row_with_the_stand_and_what_it_asks(
    as_person, world, db_session
):
    world.member_allocation.end_date = date(2026, 12, 31)
    await db_session.flush()
    block = (await _body(as_person, world.owner))["my_assignments"]
    assert block["total"] == 1
    (row,) = block["rows"]
    assert row["assignment_id"] == str(world.alfa.id)
    assert row["name"] == "Opdracht Alfa"
    assert row["line"].startswith("Uitvoeren, 3 maanden af te sluiten")
    assert row["verdict"] == "room"


@pytest.mark.parametrize("who", ["member", "lezer", "planner", "leader", "outsider"])
async def test_who_runs_nothing_has_no_assignments_here(as_person, world, who):
    assert "my_assignments" not in await _body(as_person, getattr(world, who))


async def test_a_manager_also_has_the_assignment_here(
    as_person, world, db_session, create_person
):
    """The owner first: what is remembered of the stand must hold for the manager
    too, and ``READ_CACHE=verify`` checks that."""
    manager = await create_person("manager@example.org", name="Mo Manager")
    await assignments.set_assignment_role(
        db_session, world.alfa.id, manager.id, "manager", actor=world.owner
    )
    await db_session.flush()
    owners = (await _body(as_person, world.owner))["my_assignments"]
    block = (await _body(as_person, manager))["my_assignments"]
    assert [row["name"] for row in block["rows"]] == ["Opdracht Alfa"]
    assert block["rows"][0]["line"] == owners["rows"][0]["line"]


async def test_a_row_over_the_budget_says_so_and_comes_first(
    as_person, world, db_session
):
    for index in range(3):
        await assignments.create_assignment(
            db_session, name=f"Opdracht Aaa {index}", actor=world.owner
        )
    await db_session.flush()
    rows = (await _body(as_person, world.owner))["my_assignments"]["rows"]
    assert rows[0]["name"] == "Opdracht Alfa"
    assert rows[0]["verdict"] == "overrun"


async def test_a_potential_assignment_has_no_verdict_yet(as_person, world, db_session):
    await assignments.create_assignment(
        db_session, name="Opdracht Later", actor=world.owner
    )
    await db_session.flush()
    rows = (await _body(as_person, world.owner))["my_assignments"]["rows"]
    later = next(row for row in rows if row["name"] == "Opdracht Later")
    assert later["verdict"] is None


async def test_at_most_eight_rows_and_the_total_says_the_rest(
    as_person, world, db_session
):
    for index in range(9):
        await assignments.create_assignment(
            db_session, name=f"Opdracht Extra {index}", actor=world.owner
        )
    await db_session.flush()
    block = (await _body(as_person, world.owner))["my_assignments"]
    assert len(block["rows"]) == 8
    assert block["total"] == 10
    # What asks something comes first.
    assert block["rows"][0]["name"] == "Opdracht Alfa"


async def test_a_closed_assignment_with_nothing_to_report_is_left_out(
    as_person, world, db_session
):
    ended = await assignments.create_assignment(
        db_session, name="Opdracht Voorbij", actor=world.owner
    )
    await assignments.transition(db_session, ended.id, "cancelled", actor=world.owner)
    await db_session.flush()
    block = (await _body(as_person, world.owner))["my_assignments"]
    assert "Opdracht Voorbij" not in [row["name"] for row in block["rows"]]
    assert block["total"] == 1


async def test_without_the_money_class_a_row_has_no_verdict_and_no_money_sentence(
    as_person, world, _test_app
):
    _deny(
        _test_app,
        lambda request: request.data_class in (B, C, DataClass.STAFFING_COUNTS),
    )
    body = await _body(as_person, world.owner)
    (row,) = body["my_assignments"]["rows"]
    assert "verdict" not in row
    assert row["line"] == "Uitvoeren"


TEAM_ASKS = ", 1 rol open, 1 persoon in een andere schaal"


async def _team_asks(world, db_session):
    """Potential, so only the team asks something: half of a role is open, and
    Otto (scale 14, category D) is on a line of category C."""
    gamma = await assignments.create_assignment(
        db_session,
        name="Opdracht Gamma",
        actor=world.owner,
        start_date=date(2026, 12, 1),
        end_date=date(2027, 6, 30),
    )
    line = await assignments.add_budget_line(
        db_session,
        gamma.id,
        description="Ontwerper",
        kind="personnel",
        role="Ontwerper",
        fte=Decimal("1"),
        rate_category="C",
        start_date=date(2026, 12, 1),
        end_date=date(2027, 6, 30),
        actor=world.owner,
    )
    await assignments.add_allocation(
        db_session,
        line.id,
        world.other_person.id,
        start_date=date(2026, 12, 1),
        end_date=date(2027, 6, 30),
        fte_pct=Decimal("50"),
        actor=world.owner,
    )
    await db_session.flush()
    return gamma


async def test_without_staffing_and_signal_the_team_asks_nothing_here(
    as_person, world, db_session, _test_app
):
    """First who has every class, so what is remembered is there for who has B
    and the list of the team, but not C and not the signal."""
    await _team_asks(world, db_session)

    def gamma_of(body):
        rows = body["my_assignments"]["rows"]
        return next(row for row in rows if row["name"] == "Opdracht Gamma")

    full = gamma_of(await _body(as_person, world.owner))
    _deny(
        _test_app,
        lambda request: (
            request.subject.person_id == world.owner.id
            and request.data_class in (C, DataClass.RATE_MISMATCH_SIGNAL)
        ),
    )
    body = await _body(as_person, world.owner)
    row = gamma_of(body)
    assert full["line"] == row["line"] + TEAM_ASKS
    text = json.dumps(body)
    assert "rol open" not in text
    assert "andere schaal" not in text


async def test_the_loader_reads_only_the_classes_it_is_given(world, db_session):
    gamma = await _team_asks(world, db_session)
    roster, signal = DataClass.STAFFING_ROSTER, DataClass.RATE_MISMATCH_SIGNAL

    async def facts(*classes):
        (read,) = await start_service.facts_of_many(
            db_session, {gamma.id: {A, *classes}}, date(2026, 11, 15)
        )
        return read.facts

    basic = await facts()
    assert basic == PartsFacts(kind=gamma.kind, status=gamma.status)
    money = await facts(B)
    assert money.budget is not None and money.months is not None
    assert money.has_personnel_line is False
    assert money.open_roles is None and money.other_scale is None
    team = await facts(B, roster)
    assert team.has_personnel_line is True
    assert team.open_roles is None and team.other_scale is None
    staffing = await facts(B, C)
    assert staffing.open_roles == 1 and staffing.other_scale is None
    scale = await facts(B, signal)
    assert scale.other_scale == 1 and scale.open_roles is None


def test_the_sentence_keeps_to_the_classes_whatever_the_facts_hold():
    facts = PartsFacts(
        kind="external",
        status="draft",
        has_personnel_line=True,
        open_roles=1,
        other_scale=1,
        budget=BudgetFacts(lines=1),
    )
    roster, signal = DataClass.STAFFING_ROSTER, DataClass.RATE_MISMATCH_SIGNAL
    assert start_service.notice_of(facts, {A, B, C, roster, signal}) == (
        "1 rol open, 1 persoon in een andere schaal"
    )
    assert start_service.notice_of(facts, {A, B, roster}) is None
    assert start_service.notice_of(facts, {A, B, C}) == "1 rol open"
    assert start_service.notice_of(facts, {A, B, roster, signal}) == (
        "1 persoon in een andere schaal"
    )


# -- planning -----------------------------------------------------------------


async def _open_role(world, db_session, **kwargs):
    return await assignments.add_budget_line(
        db_session,
        world.alfa.id,
        description=kwargs.pop("description", "Ontwerper"),
        kind="personnel",
        role="Ontwerper",
        fte=Decimal("0.6"),
        rate_category="C",
        start_date=kwargs.pop("start_date", date(2026, 12, 1)),
        end_date=kwargs.pop("end_date", date(2027, 6, 30)),
        actor=world.owner,
    )


async def test_the_planner_gets_counts_and_no_name(as_person, world, db_session):
    await _open_role(world, db_session)
    await db_session.flush()
    body = await _body(as_person, world.planner)
    assert body["planning"] == {
        "open_roles": 1,
        "open_fte": "0.6",
        "idle_people": 1,
        "idle_from": "2027-01-01",
    }


async def test_the_planning_is_the_number_on_the_board(as_person, world, db_session):
    await _open_role(world, db_session)
    await _open_role(
        world,
        db_session,
        description="Veel later",
        start_date=date(2028, 6, 1),
        end_date=date(2028, 12, 31),
    )
    await db_session.flush()
    body = await _body(as_person, world.planner)
    board = (await as_person(world.planner).get("/api/allocations/board")).json()
    assert body["planning"]["open_roles"] == len(board["open_roles"]) == 1


async def test_who_has_no_inzet_at_all_is_in_the_count(
    as_person, world, db_session, create_person
):
    idle = await create_person("vrij@example.org", name="Vic Vrij")
    await rates.set_person_scale(
        db_session, idle.id, date(2026, 1, 1), 14, actor=world.beheerder
    )
    await db_session.flush()
    planning = (await _body(as_person, world.planner))["planning"]
    assert planning["idle_people"] == 2
    assert planning["idle_from"] == "2027-01-01"


async def test_who_only_falls_idle_later_is_not_in_the_count(
    as_person, world, db_session
):
    """Mila and Cas stop in June 2027: months from now, and so no message."""
    await db_session.flush()
    planning = (await _body(as_person, world.planner))["planning"]
    assert planning["idle_people"] == 1


async def test_nothing_open_and_nobody_idle_is_no_block(as_person, world, db_session):
    with clock.at(datetime(2026, 7, 15, 12, 0, tzinfo=UTC)):
        body = await _body(as_person, world.planner)
    assert "planning" not in body


@pytest.mark.parametrize(
    "who", ["beheerder", "lezer", "owner", "member", "leader", "outsider"]
)
async def test_the_planning_is_only_for_the_planner(as_person, world, db_session, who):
    await _open_role(world, db_session)
    await db_session.flush()
    body = await _body(as_person, getattr(world, who))
    assert "planning" not in body
    assert "open_fte" not in json.dumps(body)


async def test_the_decision_says_who_plans_not_the_function(
    as_person, world, db_session, _test_app
):
    await _open_role(world, db_session)
    await db_session.flush()
    _deny(
        _test_app,
        lambda request: request.action is Action.EDIT and request.data_class is C,
    )
    assert "planning" not in await _body(as_person, world.planner)


async def test_planning_also_asks_whether_it_may_be_read(
    as_person, world, db_session, _test_app
):
    await _open_role(world, db_session)
    await db_session.flush()
    _deny(
        _test_app,
        lambda request: request.action is Action.READ and request.data_class is C,
    )
    assert "planning" not in await _body(as_person, world.planner)


async def test_the_function_alone_does_not_open_the_planning(
    as_person, world, db_session, _test_app
):
    await _open_role(world, db_session)
    await db_session.flush()
    _deny(_test_app, lambda request: request.data_class is C)
    assert "planning" not in await _body(as_person, world.planner)


# -- my people ----------------------------------------------------------------


async def test_a_leader_gets_inzet_and_free_from_and_no_judgement(as_person, world):
    body = await _body(as_person, world.leader)
    block = body["my_people"]
    assert block["total"] == 2
    assert [row["name"] for row in block["rows"]] == ["Cas Collega", "Mila Medewerker"]
    (cas, mila) = block["rows"]
    assert set(cas) == {"person_id", "name", "now_pct", "free_from"}
    assert cas["person_id"] == str(world.colleague.id)
    assert cas["now_pct"] == "50"
    assert mila["now_pct"] == "100"
    assert cas["free_from"] == "2027-07-01"
    for word in ("target", "realisation", "billing_scale", "cents", "Onder"):
        assert word not in json.dumps(block), word


@pytest.mark.parametrize(
    "who", ["beheerder", "planner", "lezer", "owner", "member", "outsider"]
)
async def test_who_leads_nobody_has_no_people_here(as_person, world, who):
    """A planner may read everybody's inzet; that does not make them hers."""
    assert "my_people" not in await _body(as_person, getattr(world, who))


async def test_who_falls_idle_first_comes_first(as_person, world, db_session):
    world.member_allocation.end_date = date(2026, 12, 31)
    await db_session.flush()
    rows = (await _body(as_person, world.leader))["my_people"]["rows"]
    assert [row["name"] for row in rows] == ["Mila Medewerker", "Cas Collega"]
    assert rows[0]["free_from"] == "2027-01-01"


async def test_at_most_eight_people_and_the_total_says_the_rest(
    as_person, world, create_person
):
    for index in range(9):
        await create_person(
            f"mens{index}@example.org",
            name=f"Mens {index}",
            manager_id=world.leader.id,
        )
    block = (await _body(as_person, world.leader))["my_people"]
    assert len(block["rows"]) == 8
    assert block["total"] == 11


async def test_who_left_is_not_among_my_people(as_person, world, db_session):
    world.colleague.is_active = False
    await db_session.flush()
    block = (await _body(as_person, world.leader))["my_people"]
    assert [row["name"] for row in block["rows"]] == ["Mila Medewerker"]


async def test_a_person_the_leader_may_not_read_is_not_counted(
    as_person, world, _test_app
):
    colleague = world.colleague.id
    _deny(
        _test_app,
        lambda request: request.resource.person_id == colleague,
    )
    block = (await _body(as_person, world.leader))["my_people"]
    assert [row["name"] for row in block["rows"]] == ["Mila Medewerker"]
    assert block["total"] == 1


async def test_the_team_list_alone_does_not_open_the_inzet_of_a_person(
    as_person, world, _test_app
):
    """Only C is refused for Cas: that he is in the team is no reason to show
    his inzet or when he is free."""
    colleague = world.colleague.id
    _deny(
        _test_app,
        lambda request: (
            request.resource.person_id == colleague and request.data_class is C
        ),
    )
    block = (await _body(as_person, world.leader))["my_people"]
    assert block["rows"] == [
        {
            "person_id": str(world.member.id),
            "name": "Mila Medewerker",
            "now_pct": "100",
            "free_from": "2027-07-01",
        }
    ]
    assert block["total"] == 1
    assert str(colleague) not in json.dumps(block)


async def test_start_and_the_board_say_the_same_of_everyone(
    as_person, world, db_session, create_person
):
    """Inzet past the window of the board, and a scale that only starts later."""
    far = await create_person(
        "ver@example.org", name="Vera Ver", manager_id=world.leader.id
    )
    late = await create_person(
        "laat@example.org", name="Lea Laat", manager_id=world.leader.id
    )
    await rates.set_person_scale(
        db_session, far.id, date(2026, 1, 1), 14, actor=world.beheerder
    )
    await rates.set_person_scale(
        db_session, late.id, date(2027, 1, 1), 14, actor=world.beheerder
    )
    line = await assignments.add_budget_line(
        db_session,
        world.beta.id,
        description="Later",
        kind="personnel",
        role="Later",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2027, 9, 1),
        end_date=date(2027, 12, 31),
        actor=world.beheerder,
    )
    await assignments.add_allocation(
        db_session,
        line.id,
        far.id,
        start_date=date(2027, 9, 1),
        end_date=date(2027, 12, 31),
        fte_pct=Decimal("100"),
        actor=world.beheerder,
    )
    await db_session.flush()
    board = (await as_person(world.planner).get("/api/allocations/board")).json()
    on_board = {person["person_id"]: person for person in board["persons"]}
    rows = (await _body(as_person, world.leader))["my_people"]["rows"]
    assert {row["name"] for row in rows} >= {"Vera Ver", "Lea Laat"}
    for row in rows:
        person = on_board[row["person_id"]]
        assert row["now_pct"] == person["now_pct"], row["name"]
        assert row["free_from"] == person["idle_from"], row["name"]
    planning = (await _body(as_person, world.planner))["planning"]
    assert planning["idle_people"] == sum(
        1
        for person in board["persons"]
        if person["idle_from"] and person["idle_from"] <= planning["idle_from"]
    )


# -- figures ------------------------------------------------------------------


async def _reports(as_person, reader) -> tuple[dict, dict]:
    client = as_person(reader)
    steering = (await client.get("/api/reports/steering")).json()
    investment = (await client.get("/api/reports/investment")).json()
    return steering, investment


async def test_who_reads_everything_gets_the_same_figures_as_geld(as_person, world):
    body = await _body(as_person, world.beheerder)
    steering, investment = await _reports(as_person, world.beheerder)
    figures = steering["turnover"]["figures"]
    issued = next(
        s for s in steering["pipeline"]["statuses"] if s["status"] == "issued"
    )
    assert body["figures"] == {
        "year": 2026,
        "expected_cents": figures["expected_total_cents"],
        "budgeted_cents": figures["budgeted_cents"],
        "room_cents": investment["money"]["room_cents"],
        "shortfall": investment["money"]["shortfall"],
        "potential_cents": issued["total_cents"],
        "quotes_waiting": issued["count"],
        "incomplete_by": steering["turnover"]["incomplete_by"],
    }


async def test_with_few_targets_a_lezer_gets_no_room(as_person, world):
    """The room minus the other lines is the sum of the targets."""
    body = await _body(as_person, world.lezer)
    block = body["figures"]
    assert set(block) == {
        "year",
        "expected_cents",
        "budgeted_cents",
        "potential_cents",
        "quotes_waiting",
        "incomplete_by",
    }
    assert "room_cents" not in json.dumps(body)
    assert "shortfall" not in json.dumps(body)


async def test_with_enough_targets_a_lezer_gets_the_room(
    as_person, world, db_session, create_person
):
    for index in range(4):
        person = await create_person(f"extra{index}@example.org", name=f"Extra {index}")
        await rates.set_person_scale(
            db_session, person.id, date(2026, 1, 1), 14, actor=world.beheerder
        )
        await rates.set_billability_target(
            db_session, person.id, 2026, Decimal("50"), actor=world.beheerder
        )
    block = (await _body(as_person, world.lezer))["figures"]
    _, investment = await _reports(as_person, world.lezer)
    assert block["room_cents"] == investment["money"]["room_cents"]
    assert block["shortfall"] is investment["money"]["shortfall"]
    assert block["shortfall"] is (block["room_cents"] < 0)


async def test_one_target_short_a_lezer_gets_no_room(
    as_person, world, db_session, create_person
):
    for index in range(3):
        person = await create_person(f"extra{index}@example.org", name=f"Extra {index}")
        await rates.set_person_scale(
            db_session, person.id, date(2026, 1, 1), 14, actor=world.beheerder
        )
        await rates.set_billability_target(
            db_session, person.id, 2026, Decimal("50"), actor=world.beheerder
        )
    block = (await _body(as_person, world.lezer))["figures"]
    assert "room_cents" not in block
    assert "shortfall" not in block


@pytest.mark.parametrize(
    ("people", "sees_targets", "withheld"),
    [
        (0, False, False),
        (1, False, True),
        (4, False, True),
        (5, False, False),
        (1, True, False),
        (4, True, False),
    ],
)
def test_the_limit_of_the_sum_of_targets(people, sees_targets, withheld):
    assert investment.money_withheld(people, sees_targets=sees_targets) is withheld


async def test_a_withheld_room_does_not_keep_an_empty_block_alive(
    as_person, db_session, create_person
):
    """All that is left is zeros: the block has nothing to say to this reader."""
    boss = await create_person(
        "baas@example.org", name="Bo Baas", functions=["beheerder"]
    )
    lezer = await create_person(
        "leeg@example.org", name="Leo Leeg", functions=["lezer"]
    )
    person = await create_person("mens@example.org", name="Mo Mens")
    await rates.create_rate_card(db_session, 2026, actor=boss)
    for category, cents in reports_world.RATES[2026].items():
        await rates.set_rate_band(db_session, 2026, category, cents, actor=boss)
    for scale, category in reports_world.SCALES.items():
        await rates.set_scale_band(db_session, 2026, scale, category, actor=boss)
    await rates.set_rate_card_status(db_session, 2026, "active", actor=boss)
    await rates.set_person_scale(
        db_session, person.id, date(2026, 1, 1), 14, actor=boss
    )
    await rates.set_billability_target(
        db_session, person.id, 2026, Decimal("50"), actor=boss
    )
    await db_session.flush()
    assert "figures" not in await _body(as_person, lezer)
    # Who may read the room has something to read: a target and nothing against it.
    assert (await _body(as_person, boss))["figures"]["room_cents"] < 0


@pytest.mark.parametrize("who", ["owner", "planner", "member", "leader", "outsider"])
async def test_the_figures_are_for_who_reads_all_of_the_money(as_person, world, who):
    body = await _body(as_person, getattr(world, who))
    assert "figures" not in body
    assert "_cents" not in json.dumps(body)


async def test_a_waiting_quote_is_counted(as_person, world, db_session):
    await assignments.add_budget_line(
        db_session,
        world.beta.id,
        description="Hosting",
        kind="fixed",
        amount_cents=100000,
        year=2026,
        actor=world.beheerder,
    )
    quote = await quotes.issue_quote(db_session, world.beta.id, actor=world.beheerder)
    await db_session.flush()
    block = (await _body(as_person, world.lezer))["figures"]
    assert block["quotes_waiting"] == 1
    assert block["potential_cents"] == quote.total_cents


async def test_nothing_to_say_is_no_figures(as_person, db_session, create_person):
    lezer = await create_person(
        "leeg@example.org", name="Leo Leeg", functions=["lezer"]
    )
    assert "figures" not in await _body(as_person, lezer)


# -- my requests --------------------------------------------------------------


@pytest.fixture
async def asker(world, db_session, create_person):
    return await create_person(
        "aanvrager@example.org", name="Anne Aanvraag", functions=["aanvrager"]
    )


async def _ask(db_session, asker, name="Aanvraag Zeta 2026"):
    own = await own_organisation(db_session)
    contractor = await assignments.upsert_organisation(
        db_session, name="Voorbeeldleverancier"
    )
    assignment, _ = await assignments.create_assignment_request(
        db_session,
        name=name,
        contractor_organisation_id=contractor.id,
        client_organisation_id=own.id,
        actor=asker,
    )
    await db_session.flush()
    return assignment


async def test_an_asker_hears_where_the_request_stands(as_person, asker, db_session):
    asked = await _ask(db_session, asker)
    body = await _body(as_person, asker)
    assert body["my_requests"] == {
        "rows": [
            {
                "assignment_id": str(asked.id),
                "name": "Aanvraag Zeta 2026",
                "line": "Nog geen offerte",
            }
        ],
        "total": 1,
    }
    # It is hers once: not also among the assignments she runs.
    assert "my_assignments" not in body
    assert "cents" not in json.dumps(body)


async def test_a_request_that_did_not_arrive_says_so(as_person, asker, db_session):
    asked = await _ask(db_session, asker)
    peer = Peer(
        peer_id="urn:test:peer",
        base_uri="https://leverancier.example",
        role="counterpart",
        name="Voorbeeldleverancier",
    )
    db_session.add(peer)
    await db_session.flush()
    from grip.federation import terms

    db_session.add(
        FederationOutbox(
            message_id=uuid4(),
            peer_id=peer.id,
            service="grip-opdrachtverkeer",
            operation="sendAssignmentRequest",
            method="POST",
            path="/x",
            payload={terms.term("assignment_uri"): asked.uri},
            status="dead",
        )
    )
    await db_session.flush()
    (row,) = (await _body(as_person, asker))["my_requests"]["rows"]
    assert row["line"] == "De aanvraag is niet aangekomen"


async def test_only_who_may_ask_has_requests_here(
    as_person, world, asker, db_session, create_person
):
    await _ask(db_session, asker)
    other = await create_person(
        "ander@voorbeeld.example", name="Ada Ander", functions=["aanvrager"]
    )
    # Hers to read, but not an asker: a beheerder has this in the list.
    assert "my_requests" not in await _body(as_person, world.beheerder)
    assert "my_requests" not in await _body(as_person, world.lezer)
    # An asker, but not hers to read.
    assert "my_requests" not in await _body(as_person, other)


async def test_a_request_of_someone_else_is_not_mine(
    as_person, asker, db_session, create_person
):
    """She may read it, and she may ask herself. It is still not hers."""
    lea = await create_person(
        "lea@example.org", name="Lea Lezer", functions=["aanvrager", "lezer"]
    )
    await _ask(db_session, asker)
    assert "my_requests" not in await _body(as_person, lea)


async def test_a_manager_of_a_request_has_it_too(
    as_person, asker, db_session, create_person
):
    mo = await create_person("mo@example.org", name="Mo Mede", functions=["aanvrager"])
    asked = await _ask(db_session, asker)
    await assignments.set_assignment_role(
        db_session, asked.id, mo.id, "manager", actor=asker
    )
    await db_session.flush()
    body = await _body(as_person, mo)
    assert [row["name"] for row in body["my_requests"]["rows"]] == [asked.name]
    assert "my_assignments" not in body


async def _with_a_quote(db_session, asker, asked):
    await assignments.add_budget_line(
        db_session,
        asked.id,
        description="Regel",
        kind="fixed",
        amount_cents=100000,
        year=2026,
        actor=asker,
    )
    await quotes.issue_quote(db_session, asked.id, actor=asker)
    await db_session.flush()


async def test_an_asker_without_the_money_class_hears_only_the_status(
    as_person, asker, db_session, create_person, _test_app
):
    """First who has B, so the remembered value is there for who has not."""
    mo = await create_person("mo@example.org", name="Mo Mede", functions=["aanvrager"])
    asked = await _ask(db_session, asker)
    await assignments.set_assignment_role(
        db_session, asked.id, mo.id, "manager", actor=asker
    )
    await _with_a_quote(db_session, asker, asked)
    (hers,) = (await _body(as_person, asker))["my_requests"]["rows"]
    assert hers["line"].startswith("Ontvangen op")
    _deny(
        _test_app,
        lambda request: request.subject.person_id == mo.id and request.data_class is B,
    )
    (row,) = (await _body(as_person, mo))["my_requests"]["rows"]
    assert row["line"] == "Offerte gemaakt"


async def test_a_request_of_a_beheerder_reports_no_work_of_the_contractor(
    as_person, world, db_session
):
    """She is no asker, so it stays among her assignments. The months, the team
    and the report are in the other instance, so a finished one asks nothing."""
    asked = await _ask(db_session, world.beheerder)
    asked.status = "completed"
    await db_session.flush()
    body = await _body(as_person, world.beheerder)
    assert asked.name not in json.dumps(body.get("my_assignments", {}))


async def test_a_received_quote_is_no_potential(as_person, world, asker, db_session):
    """It is money this instance would pay. Start and Geld say the same."""
    asked = await _ask(db_session, asker)
    await _with_a_quote(db_session, asker, asked)
    figures = (await _body(as_person, world.lezer))["figures"]
    steering_body = (await as_person(world.lezer).get("/api/reports/steering")).json()
    assert figures["quotes_waiting"] == 0
    assert figures["potential_cents"] == 0
    issued = next(
        s for s in steering_body["pipeline"]["statuses"] if s["status"] == "issued"
    )
    assert issued["count"] == 0
    assert asked.name not in json.dumps(steering_body["pipeline"])


async def test_a_quote_on_a_request_of_this_instance_stays_out_of_the_year(
    world, asker, db_session
):
    asked = await _ask(db_session, asker)
    await _with_a_quote(db_session, asker, asked)
    found = await steering.quotes_of_year(db_session, 2026)
    assert asked.id not in [quote.assignment_id for quote in found]
    # A quote to another client is still ours, and so is an assignment without one.
    assert world.alfa.id in [quote.assignment_id for quote in found]
    world.alfa.client_organisation_id = None
    await db_session.flush()
    found = await steering.quotes_of_year(db_session, 2026)
    assert world.alfa.id in [quote.assignment_id for quote in found]


async def test_at_most_eight_requests(as_person, asker, db_session):
    for index in range(9):
        await _ask(db_session, asker, name=f"Aanvraag {index}")
    block = (await _body(as_person, asker))["my_requests"]
    assert len(block["rows"]) == 8
    assert block["total"] == 9


# -- connections --------------------------------------------------------------


async def _message(db_session, status):
    peer = Peer(
        peer_id=f"urn:test:{uuid4()}",
        base_uri=f"https://{uuid4()}.example",
        role="counterpart",
        name="Voorbeeldpartij",
    )
    db_session.add(peer)
    await db_session.flush()
    db_session.add(
        FederationOutbox(
            message_id=uuid4(),
            peer_id=peer.id,
            service="grip-opdrachtverkeer",
            operation="sendQuote",
            method="POST",
            path="/x",
            payload={},
            status=status,
        )
    )
    await db_session.flush()


async def test_the_beheerder_hears_only_of_messages_that_did_not_arrive(
    as_person, world, db_session
):
    await _message(db_session, "sent")
    await _message(db_session, "pending")
    assert "connections" not in await _body(as_person, world.beheerder)
    await _message(db_session, "dead")
    await _message(db_session, "dead")
    body = await _body(as_person, world.beheerder)
    assert body["connections"] == {"problems": 2}


@pytest.mark.parametrize(
    "who", ["lezer", "planner", "owner", "leader", "member", "outsider"]
)
async def test_the_connections_are_only_for_the_beheerder(
    as_person, world, db_session, who
):
    await _message(db_session, "dead")
    assert "connections" not in await _body(as_person, getattr(world, who))


# -- the budget ---------------------------------------------------------------


async def _statements_of_a_visit(client, reader, db_session) -> int:
    engine = db_session.bind.sync_engine
    count = 0

    def _count(*_):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _count)
    try:
        response = await client(reader).get(URL)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    assert response.status_code == 200, response.text
    return count


async def _statements_of_a_warm_visit(client, reader, db_session) -> int:
    await client(reader).get(URL)
    return await _statements_of_a_visit(client, reader, db_session)


async def _statements_after_a_change_elsewhere(client, reader, db_session, world):
    """What is remembered until the next event is gone; what is remembered per
    assignment stays for every assignment but the one that changed."""
    await client(reader).get(URL)
    await task_service.create_manual_task(
        db_session,
        case_kind="assignment",
        case_id=world.beta.id,
        title="Iets anders",
        track=None,
        actor=world.beheerder,
        assignee_person_id=world.beheerder.id,
    )
    await db_session.flush()
    return await _statements_of_a_visit(client, reader, db_session)


async def _statements_of_a_first_visit(client, reader, db_session) -> int:
    """Nothing is remembered, as after a start of the process. The task engine
    then reads the facts of every case for whoever asks first; here the count in
    the bar asks first, so that reading is not in the count of the start page."""
    read_cache.clear()
    task_engine.forget_evaluation()
    await client(reader).get("/api/tasks/count")
    return await _statements_of_a_visit(client, reader, db_session)


async def _more_assignments(world, db_session, count):
    """Half wait for an answer to their quote, half run with months behind
    them: what a row and a task of the start page read per assignment."""
    for index in range(count):
        assignment = await assignments.create_assignment(
            db_session,
            name=f"Opdracht Druk {index}",
            actor=world.owner,
            client_organisation_id=world.alfa.client_organisation_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        line = await assignments.add_budget_line(
            db_session,
            assignment.id,
            description="Adviseur",
            kind="personnel",
            role="Adviseur",
            fte=Decimal("1"),
            rate_category="D",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            actor=world.owner,
        )
        await assignments.add_allocation(
            db_session,
            line.id,
            world.other_person.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            fte_pct=Decimal("10"),
            actor=world.owner,
        )
        if index % 2:
            await quotes.issue_quote(db_session, assignment.id, actor=world.owner)
            continue
        await accept(db_session, assignment.id)
        await assignments.transition(
            db_session,
            assignment.id,
            "in_progress",
            actor=world.owner,
            enforce_readiness=False,
        )
    await db_session.flush()


@pytest.mark.parametrize("after", ["a change elsewhere", "a start of the process"])
async def test_a_cold_visit_does_not_grow_with_the_assignments(
    as_person, world, db_session, monkeypatch, after
):
    """The owner reads as much for one assignment as for thirteen, of which
    eight rows and five tasks show."""
    monkeypatch.setenv("READ_CACHE", "on")

    async def cold() -> int:
        if after == "a change elsewhere":
            return await _statements_after_a_change_elsewhere(
                as_person, world.owner, db_session, world
            )
        return await _statements_of_a_first_visit(as_person, world.owner, db_session)

    first = await cold()
    await _more_assignments(world, db_session, 12)
    body = await _body(as_person, world.owner)
    assert len(body["my_assignments"]["rows"]) == 8
    assert len(body["to_do"]["groups"]) == 5
    assert await cold() <= first + 5


async def test_a_warm_visit_stays_within_the_budget_however_much_there_is(
    as_person, world, db_session, monkeypatch, create_person
):
    """Docs: at most 50 statements in a request (docs/snelheid.md)."""
    monkeypatch.setenv("READ_CACHE", "on")
    first = await _statements_of_a_warm_visit(as_person, world.owner, db_session)
    for index in range(12):
        assignment = await assignments.create_assignment(
            db_session, name=f"Opdracht Veel {index}", actor=world.owner
        )
        line = await assignments.add_budget_line(
            db_session,
            assignment.id,
            description="Adviseur",
            kind="personnel",
            role="Adviseur",
            fte=Decimal("1"),
            rate_category="D",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            actor=world.owner,
        )
        await assignments.add_allocation(
            db_session,
            line.id,
            world.other_person.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            fte_pct=Decimal("10"),
            actor=world.owner,
        )
    await db_session.flush()
    many = await _statements_of_a_warm_visit(as_person, world.owner, db_session)
    assert many <= 50
    assert many <= first + 5


async def test_a_warm_visit_of_an_asker_stays_within_the_budget(
    as_person, asker, db_session, monkeypatch
):
    monkeypatch.setenv("READ_CACHE", "on")
    for index in range(10):
        await _ask(db_session, asker, name=f"Aanvraag {index}")
    assert await _statements_of_a_warm_visit(as_person, asker, db_session) <= 50
