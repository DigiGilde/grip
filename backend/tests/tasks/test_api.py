"""The task routes: who sees which task, and who may do what with it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from grip.access import unclassified_fields
from grip.models.assignment import Assignment
from grip.models.person import Person
from grip.models.vacancy import Vacancy
from grip.schema import tasks as schema


@dataclass
class World:
    beheerder: Person
    lezer: Person
    planner: Person
    owner: Person
    member: Person
    outsider: Person
    requester: Person
    assignment: Assignment
    other: Assignment
    vacancy: Vacancy


@pytest.fixture
async def world(build, create_person) -> World:
    beheerder = await create_person("beheer@example.org", functions=["beheerder"])
    lezer = await create_person("lezer@example.org", functions=["lezer"])
    planner = await create_person("planner@example.org", functions=["planner"])
    owner = await create_person("eigenaar@example.org", name="Eva Eigenaar")
    member = await create_person("lid@example.org", name="Lot Lid")
    outsider = await create_person("buiten@example.org")
    requester = await create_person(
        "vraag@example.org", name="Vera Vraag", functions=["planner"]
    )
    # Accepted, with one role staffed and one open: the owner must start the
    # work, the planner must fill a role. It starts this month, so no month
    # has ended yet and nothing waits to be closed.
    start = date.today().replace(day=1)
    assignment = await build.assignment(
        status="accepted", owner=owner, start=start, end=start + timedelta(days=200)
    )
    line = await build.line(assignment, "Developer")
    await build.allocation(line, member)
    await build.line(assignment, "Ontwerper")
    other = await build.assignment("Opdracht Beta 2026", owner=beheerder)
    vacancy = await build.vacancy(requester=requester)
    return World(
        beheerder=beheerder,
        lezer=lezer,
        planner=planner,
        owner=owner,
        member=member,
        outsider=outsider,
        requester=requester,
        assignment=assignment,
        other=other,
        vacancy=vacancy,
    )


def titles(body: dict) -> set[str]:
    return {item["title"] for item in body.get("items", [])}


async def case(client, world: World) -> dict:
    response = await client.get(f"/api/tasks/cases/assignment/{world.assignment.id}")
    assert response.status_code == 200, response.text
    return response.json()


def find(body: dict, title: str) -> dict:
    for track in body["tracks"]:
        for task in track.get("tasks", []):
            if task["title"] == title:
                return task
    raise AssertionError(f"{title} niet gevonden")


def test_every_field_has_a_data_class():
    for model in (schema.TaskOut, schema.TaskListOut, schema.CaseTasksOut):
        assert unclassified_fields(model) == []


# --- my tasks -------------------------------------------------------------------


async def test_my_tasks_are_the_ones_for_my_role(as_person, world):
    owner = (await as_person(world.owner).get("/api/tasks/mine")).json()
    # Staffing her own assignment is hers to do as well as a planner's.
    assert titles(owner) == {"Zet de opdracht in uitvoering", "Vul de rol Ontwerper in"}
    assert owner["counts"] == {"open": 2, "to_do": 2, "overdue": 0}
    task = next(
        item
        for item in owner["items"]
        if item["title"] == "Zet de opdracht in uitvoering"
    )
    assert task["is_mine"] is True
    assert task["case_label"] == "Opdracht Alfa 2026"
    assert task["assignee_label"] == "Eigenaar van de opdracht"
    assert task["closes_by_fact"] is True
    assert task["can_complete"] is False

    planner = (await as_person(world.planner).get("/api/tasks/mine")).json()
    assert titles(planner) == {"Vul de rol Ontwerper in"}

    # The requester of the vacancy is a planner too.
    requester = (await as_person(world.requester).get("/api/tasks/mine")).json()
    assert titles(requester) == {
        "Bereid de aanvraag voor en dien haar in",
        "Vul de rol Ontwerper in",
        "Schrijf de motivatie en stel haar vast",
        "Schrijf de vacaturetekst en stel haar vast",
    }

    for person in (world.lezer, world.member, world.outsider):
        body = (await as_person(person).get("/api/tasks/mine")).json()
        assert body.get("items", []) == []


async def test_the_badge_counts_what_is_mine(as_person, world):
    response = await as_person(world.owner).get("/api/tasks/count")
    assert response.json() == {"open": 2, "to_do": 2, "overdue": 0}
    outsider = await as_person(world.outsider).get("/api/tasks/count")
    assert outsider.json()["open"] == 0


# --- the work on a case --------------------------------------------------------


async def test_a_case_shows_its_tracks_to_who_may_read_it(as_person, world):
    body = await case(as_person(world.owner), world)
    assert [track["label"] for track in body["tracks"]] == [
        "Offerte",
        "Team",
        "Uitvoering",
        "Financiën",
    ]
    by_key = {track["key"]: track for track in body["tracks"]}
    assert by_key["bemensing"]["open_count"] == 1
    assert by_key["bemensing"]["standing"] == "Vul de rol Ontwerper in"
    assert by_key["offerte"]["standing"] == "Niets te doen"
    assert body["can_add"] is True


@pytest.mark.parametrize(
    ("who", "status", "can_add"),
    [
        # The beheerder reads everything and edits no assignment.
        ("beheerder", 200, False),
        ("lezer", 200, False),
        ("planner", 200, True),
        ("member", 200, False),
        ("outsider", 404, None),
    ],
)
async def test_who_reads_and_edits_a_case(as_person, world, who, status, can_add):
    client = as_person(getattr(world, who))
    response = await client.get(f"/api/tasks/cases/assignment/{world.assignment.id}")
    assert response.status_code == status
    if status == 200:
        assert response.json()["can_add"] is can_add


async def test_an_outsider_sees_no_task_of_the_case_anywhere(as_person, world):
    await case(as_person(world.owner), world)
    client = as_person(world.outsider)
    board = (await client.get("/api/tasks")).json()
    assert board.get("items", []) == []
    owner_board = (await as_person(world.owner).get("/api/tasks")).json()
    task_id = owner_board["items"][0]["id"]
    client = as_person(world.outsider)
    assert (await client.get(f"/api/tasks/{task_id}")).status_code == 404
    assert (
        await client.patch(f"/api/tasks/{task_id}", json={"status": "doing"})
    ).status_code == 404
    assert (
        await client.post(f"/api/tasks/{task_id}/notes", json={"body": "x"})
    ).status_code == 404


async def test_the_board_filters_on_case_track_and_mine(as_person, world):
    client = as_person(world.beheerder)
    everything = (await client.get("/api/tasks")).json()
    assert {"Zet de opdracht in uitvoering", "Vul de rol Ontwerper in"} <= titles(
        everything
    )
    one_case = (
        await client.get("/api/tasks", params={"assignment_id": str(world.other.id)})
    ).json()
    assert titles(one_case) == {"Werk de aanvraag uit: maak de begroting"}
    staffing = (await client.get("/api/tasks", params={"track": "bemensing"})).json()
    assert titles(staffing) == {"Vul de rol Ontwerper in"}
    mine = (await client.get("/api/tasks", params={"mine": "true"})).json()
    assert titles(mine) == {"Werk de aanvraag uit: maak de begroting"}


# --- changing a task ----------------------------------------------------------


async def test_a_task_a_fact_closes_cannot_be_ticked(as_person, world):
    client = as_person(world.owner)
    task = find(await case(client, world), "Zet de opdracht in uitvoering")
    response = await client.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    assert response.status_code == 422
    assert "sluit vanzelf zodra de opdracht is in uitvoering" in response.text
    moved = await client.patch(f"/api/tasks/{task['id']}", json={"status": "doing"})
    assert moved.status_code == 200
    assert moved.json()["status_label"] == "Bezig"
    # The engine leaves a status a person chose alone.
    assert find(await case(client, world), task["title"])["status"] == "doing"


async def test_only_the_assignee_or_an_editor_moves_a_task(as_person, world):
    owner = as_person(world.owner)
    task = find(await case(owner, world), "Zet de opdracht in uitvoering")
    for person in (world.lezer, world.member):
        response = await as_person(person).patch(
            f"/api/tasks/{task['id']}", json={"status": "doing"}
        )
        assert response.status_code == 403
    planner = await as_person(world.planner).patch(
        f"/api/tasks/{task['id']}", json={"status": "doing"}
    )
    assert planner.status_code == 200


async def test_a_manual_task_from_start_to_finish(as_person, world):
    owner = as_person(world.owner)
    created = await owner.post(
        "/api/tasks",
        json={
            "case_kind": "assignment",
            "case_id": str(world.assignment.id),
            "title": "Bel de opdrachtgever over de planning",
            "track": "uitvoering",
            "assignee_person_id": str(world.member.id),
            "due_on": "2026-10-20",
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["origin"] == "manual"
    assert task["assignee_label"] == "Lot Lid"
    assert task["closes_by_fact"] is False

    member = as_person(world.member)
    mine = (await member.get("/api/tasks/mine")).json()
    assert titles(mine) == {"Bel de opdrachtgever over de planning"}
    assert mine["items"][0]["can_complete"] is True
    noted = await member.post(
        f"/api/tasks/{task['id']}/notes", json={"body": "Gebeld, donderdag terug."}
    )
    assert noted.status_code == 201
    assert noted.json()["notes"][0]["author_name"] == "Lot Lid"
    done = await member.patch(f"/api/tasks/{task['id']}", json={"status": "done"})
    assert done.status_code == 200
    assert done.json()["completed_by_name"] == "Lot Lid"
    assert (await member.get("/api/tasks/mine")).json().get("items", []) == []


@pytest.mark.parametrize(
    ("who", "status"), [("lezer", 403), ("member", 403), ("outsider", 404)]
)
async def test_who_cannot_add_a_task(as_person, world, who, status):
    response = await as_person(getattr(world, who)).post(
        "/api/tasks",
        json={
            "case_kind": "assignment",
            "case_id": str(world.assignment.id),
            "title": "Iets",
        },
    )
    assert response.status_code == status


async def test_handing_a_plan_task_over_sticks(as_person, world):
    owner = as_person(world.owner)
    task = find(await case(owner, world), "Zet de opdracht in uitvoering")
    handed = await owner.patch(
        f"/api/tasks/{task['id']}", json={"assignee_person_id": str(world.member.id)}
    )
    assert handed.status_code == 200
    assert handed.json()["assignee_label"] == "Lot Lid"
    assert find(await case(owner, world), task["title"])["assignee_label"] == "Lot Lid"
    member = (await as_person(world.member).get("/api/tasks/mine")).json()
    assert titles(member) == {"Zet de opdracht in uitvoering"}
    back = await as_person(world.owner).patch(
        f"/api/tasks/{task['id']}", json={"assignee_person_id": None}
    )
    assert back.status_code == 200
    again = find(await case(as_person(world.owner), world), task["title"])
    assert again["assignee_label"] == "Eigenaar van de opdracht"


async def test_a_plan_task_cannot_be_renamed_or_dropped(as_person, world):
    owner = as_person(world.owner)
    task = find(await case(owner, world), "Zet de opdracht in uitvoering")
    renamed = await owner.patch(f"/api/tasks/{task['id']}", json={"title": "Anders"})
    assert renamed.status_code == 422
    dropped = await owner.patch(f"/api/tasks/{task['id']}", json={"status": "obsolete"})
    assert dropped.status_code == 422


# --- vacancies ---------------------------------------------------------------


async def test_the_tasks_of_a_vacancy_follow_the_vacancy_s_rights(as_person, world):
    path = f"/api/tasks/cases/vacancy/{world.vacancy.id}"
    requester = await as_person(world.requester).get(path)
    assert requester.status_code == 200
    body = requester.json()
    assert [track["label"] for track in body["tracks"]] == ["Werving", "Teksten"]
    task = body["tracks"][0]["tasks"][0]
    assert task["case_label"] == "Vacature Developer"
    assert task["link"] == f"/vacatures/{world.vacancy.id}/aanvraag"
    assert (await as_person(world.planner).get(path)).json()["can_add"] is True
    assert (await as_person(world.lezer).get(path)).json()["can_add"] is False
    assert (await as_person(world.outsider).get(path)).status_code == 404
    assert (await as_person(world.member).get(path)).status_code == 404


# --- internal approval ---------------------------------------------------------


async def test_an_approver_sees_the_request_and_nothing_else_of_the_case(
    as_person, world, build, create_person
):
    approver = await create_person(
        "goedkeurder@example.org", functions=["offertegoedkeurder"]
    )
    quote = await build.quote(world.other)
    await build.approval(quote, by=world.beheerder)
    mine = (await as_person(approver).get("/api/tasks/mine")).json()
    assert [item["title"].split(" ")[0] for item in mine["items"]] == ["Beoordeel"]
    assert mine["items"][0]["can_change"] is True
    assert mine["items"][0]["can_complete"] is False
    case = await as_person(approver).get(
        f"/api/tasks/cases/assignment/{world.other.id}"
    )
    assert case.status_code == 404
    outsider = (await as_person(world.outsider).get("/api/tasks/mine")).json()
    assert outsider.get("items", []) == []


# --- the address of the work: only to a page the reader may open ---------------


async def _plan_task(db_session, world, template_key, *, case="assignment", **extra):
    from grip.models.task import Task
    from grip.tasks.plan import current_plan

    task = Task(
        case_kind=case,
        assignment_id=world.assignment.id if case == "assignment" else None,
        vacancy_id=world.vacancy.id if case == "vacancy" else None,
        origin="plan",
        template_key=template_key,
        plan_version=current_plan().version,
        title="Werk",
        track="offerte",
        **extra,
    )
    db_session.add(task)
    await db_session.flush()
    return task


def _href_in_case(body: dict, task_id) -> str | None:
    for track in body["tracks"]:
        for task in track.get("tasks", []):
            if task["id"] == str(task_id):
                return task.get("work_href")
    raise AssertionError("taak niet gevonden")


async def test_a_team_member_gets_no_address_to_the_budget_or_the_quote(
    as_person, world, db_session
):
    base = f"/opdrachten/{world.assignment.id}"
    budget = await _plan_task(
        db_session,
        world,
        "offerte.aanvraag_uitwerken",
        assignee_person_id=world.member.id,
        link=f"{base}/begroting",
    )
    quote = await _plan_task(
        db_session,
        world,
        "offerte.opstellen",
        assignee_person_id=world.member.id,
        link=f"{base}/offerte",
    )
    mine = (await as_person(world.member).get("/api/tasks/mine")).json()["items"]
    by_id = {item["id"]: item for item in mine}
    assert str(budget.id) in by_id and str(quote.id) in by_id
    for task in (budget, quote):
        assert by_id[str(task.id)].get("work_href") is None
        assert by_id[str(task.id)].get("link") is None

    # Whoever reads the money of the assignment gets the address.
    for person in (world.owner, world.beheerder, world.lezer):
        body = await case(as_person(person), world)
        assert _href_in_case(body, budget.id) == (
            f"/opdrachten/{world.assignment.id}/begroting"
        ), person.name
        assert _href_in_case(body, quote.id) == (
            f"/opdrachten/{world.assignment.id}/offerte"
        ), person.name


async def test_the_address_to_staffing_follows_the_staffing_right(
    as_person, world, db_session
):
    task = await _plan_task(db_session, world, "bemensing.rol_invullen")
    expected = f"/opdrachten/{world.assignment.id}/team"
    for person in (world.owner, world.planner, world.beheerder, world.member):
        body = await case(as_person(person), world)
        assert _href_in_case(body, task.id) == expected, person.name
    # A reader of the money alone does not read the team.
    assert _href_in_case(await case(as_person(world.lezer), world), task.id) is None


async def test_the_address_to_fulfilment_is_for_who_may_edit_the_vacancy(
    as_person, world, db_session
):
    task = await _plan_task(db_session, world, "werving.vervullen", case="vacancy")
    expected = f"/vacatures/{world.vacancy.id}/vervulling"
    url = f"/api/tasks/cases/vacancy/{world.vacancy.id}"
    for person, address in (
        (world.requester, expected),
        (world.planner, expected),
        (world.beheerder, expected),
        (world.lezer, None),
    ):
        found = await as_person(person).get(url)
        assert found.status_code == 200, person.name
        assert _href_in_case(found.json(), task.id) == address, person.name


async def test_the_other_addresses_need_only_the_case(as_person, world, db_session):
    task = await _plan_task(db_session, world, "uitvoering.starten")
    for person in (world.owner, world.member, world.lezer):
        body = await case(as_person(person), world)
        assert _href_in_case(body, task.id) == f"/opdrachten/{world.assignment.id}", (
            person.name
        )


def _find_by_prefix(body: dict, prefix: str) -> dict:
    for track in body["tracks"]:
        for task in track.get("tasks", []):
            if task["title"].startswith(prefix):
                return task
    raise AssertionError(f"{prefix} niet gevonden")


async def test_the_address_to_a_decision_is_for_whoever_may_decide_it(
    as_person, world, build, create_person
):
    """The page of an internal approval asks the right to approve quotes, not
    only a reading of the case."""
    approver = await create_person(
        "goedkeurder@example.org", functions=["offertegoedkeurder"]
    )
    quote = await build.quote(world.assignment)
    await build.approval(quote, by=world.beheerder)

    mine = (await as_person(approver).get("/api/tasks/mine")).json()["items"]
    (task,) = [item for item in mine if item["title"].startswith("Beoordeel")]
    assert task["work_href"] == f"/goedkeuren/{quote.id}"
    assert task["link"] == f"/goedkeuren/{quote.id}"

    for person in (
        world.owner,
        world.planner,
        world.beheerder,
        world.member,
        world.lezer,
    ):
        found = _find_by_prefix(await case(as_person(person), world), "Beoordeel")
        assert found.get("work_href") is None, person.name
        assert found.get("link") is None, person.name


async def test_the_address_to_a_received_quote_follows_reading_that_quote(
    as_person, world, build, db_session
):
    from grip.access import Action, DataClass, LocalDecider, Resource, Subject, decide
    from grip.access.sql import SqlRelationSource
    from grip.core.config import get_settings

    quote = await build.quote(world.assignment)
    task = await _plan_task(
        db_session,
        world,
        "offerte.beoordelen_en_tekenen",
        subject_kind="quote",
        subject_id=str(quote.id),
        link=f"/aanvragen/offerte/{quote.id}",
    )
    decider = LocalDecider(
        SqlRelationSource(
            db_session, instance_base_uri=get_settings().INSTANCE_BASE_URI
        )
    )
    expected = f"/aanvragen/offerte/{quote.id}"
    seen = set()
    for person, functions in (
        (world.owner, ()),
        (world.planner, ("planner",)),
        (world.beheerder, ("beheerder",)),
        (world.member, ()),
        (world.lezer, ("lezer",)),
    ):
        # What the route decides: reading class A of the quote.
        allowed = (
            await decide(
                decider,
                Subject.for_person(person.id, frozenset(functions)),
                Action.READ,
                Resource.quote(quote.id, world.assignment.id),
                DataClass.ASSIGNMENT_BASIC,
            )
        ).allowed
        href = _href_in_case(await case(as_person(person), world), task.id)
        assert href == (expected if allowed else None), person.name
        seen.add(allowed)
    # The test sees both outcomes, so it cannot pass by being one-sided.
    assert seen == {True, False}


# --- names: only for who runs the case or does the work ------------------------

NAME = "Lot Lid"


def _no_name(response, who: str) -> None:
    assert response.status_code == 200, (who, response.text)
    assert NAME not in response.text, who
    named = {key for key, value in _walk(response.json()) if value not in (None, "")}
    assert "assignee_person_id" not in named, who


def _walk(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key, inner
            yield from _walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner)


async def _hand_over(as_person, world, case_kind, case_id, by, title=None):
    """The first open task of the case goes to the member, by hand."""
    client = as_person(by)
    found = await client.get(f"/api/tasks/cases/{case_kind}/{case_id}")
    task = next(
        task
        for track in found.json()["tracks"]
        for task in track["tasks"]
        if task["status"] in ("todo", "doing") and title in (None, task["title"])
    )
    handed = await client.patch(
        f"/api/tasks/{task['id']}",
        json={"assignee_person_id": str(world.member.id)},
    )
    assert handed.status_code == 200, handed.text
    return task["id"]


async def test_a_reader_gets_no_name_in_the_tasks_of_a_vacancy(as_person, world):
    await _hand_over(as_person, world, "vacancy", world.vacancy.id, world.requester)
    base = f"/api/tasks/cases/vacancy/{world.vacancy.id}"
    # The lezer reads the vacancy without names, so also its tasks.
    for url in (base, f"{base}/course", "/api/tasks"):
        _no_name(await as_person(world.lezer).get(url), f"lezer {url}")
    # Whoever runs the case keeps the name.
    assert NAME in (await as_person(world.requester).get(base)).text
    assert NAME in (await as_person(world.beheerder).get(base)).text


async def test_a_reader_gets_no_name_in_the_tasks_of_an_assignment(as_person, world):
    task_id = await _hand_over(
        as_person, world, "assignment", world.assignment.id, world.owner
    )
    noted = await as_person(world.member).post(
        f"/api/tasks/{task_id}/notes", json={"body": "Gebeld."}
    )
    assert noted.status_code == 201
    created = await as_person(world.owner).post(
        "/api/tasks",
        json={
            "case_kind": "assignment",
            "case_id": str(world.assignment.id),
            "title": "Bel de opdrachtgever",
            "track": "uitvoering",
            "assignee_person_id": str(world.member.id),
        },
    )
    assert created.status_code == 201, created.text
    done = await as_person(world.member).patch(
        f"/api/tasks/{created.json()['id']}", json={"status": "done"}
    )
    assert done.status_code == 200
    assert done.json()["completed_by_name"] == NAME

    base = f"/api/tasks/cases/assignment/{world.assignment.id}"
    for url in (base, f"{base}/course", "/api/tasks", f"/api/tasks/{task_id}"):
        _no_name(await as_person(world.lezer).get(url), f"lezer {url}")
    # The one who runs it, and the one who does the work, keep the name.
    assert NAME in (await as_person(world.owner).get(base)).text
    assert NAME in (await as_person(world.owner).get(f"/api/tasks/{task_id}")).text
    assert NAME in (await as_person(world.member).get("/api/tasks/mine")).text


async def test_a_take_over_leaves_no_name_in_the_note(as_person, world, db_session):
    from sqlalchemy import select

    from grip.models.audit_log import AuditLog

    # Staffing is the planner's step, which she may do for the member.
    task_id = await _hand_over(
        as_person,
        world,
        "assignment",
        world.assignment.id,
        world.owner,
        title="Vul de rol Ontwerper in",
    )
    taken = await as_person(world.planner).post(f"/api/tasks/{task_id}/takeover")
    assert taken.status_code == 200, taken.text
    assert [note["body"] for note in taken.json()["notes"]] == [
        "Overgenomen van een collega."
    ]
    assert NAME not in taken.text

    base = f"/api/tasks/cases/assignment/{world.assignment.id}"
    for url in (base, f"/api/tasks/{task_id}"):
        _no_name(await as_person(world.lezer).get(url), f"lezer {url}")

    # Who held it before is in the history, not in the note.
    await db_session.flush()
    changes = (
        await db_session.scalars(
            select(AuditLog).where(
                AuditLog.entity == "task", AuditLog.entity_id == str(task_id)
            )
        )
    ).all()
    assert any(
        (row.old_value or {}).get("assignee_person_id") == str(world.member.id)
        for row in changes
    )
