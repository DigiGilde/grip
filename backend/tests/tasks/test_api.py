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
    assert titles(owner) == {"Zet de opdracht in uitvoering"}
    assert owner["counts"] == {"open": 1, "to_do": 1, "overdue": 0}
    task = owner["items"][0]
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
    }

    for person in (world.lezer, world.member, world.outsider):
        body = (await as_person(person).get("/api/tasks/mine")).json()
        assert body.get("items", []) == []


async def test_the_badge_counts_what_is_mine(as_person, world):
    response = await as_person(world.owner).get("/api/tasks/count")
    assert response.json() == {"open": 1, "to_do": 1, "overdue": 0}
    outsider = await as_person(world.outsider).get("/api/tasks/count")
    assert outsider.json()["open"] == 0


# --- the work on a case --------------------------------------------------------


async def test_a_case_shows_its_tracks_to_who_may_read_it(as_person, world):
    body = await case(as_person(world.owner), world)
    assert [track["label"] for track in body["tracks"]] == [
        "Offerte",
        "Bemensing",
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
    assert [track["label"] for track in body["tracks"]] == ["Werving"]
    task = body["tracks"][0]["tasks"][0]
    assert task["case_label"] == "Vacature Developer"
    assert task["link"] == f"/vacatures/{world.vacancy.id}"
    assert (await as_person(world.planner).get(path)).json()["can_add"] is True
    assert (await as_person(world.lezer).get(path)).json()["can_add"] is False
    assert (await as_person(world.outsider).get(path)).status_code == 404
    assert (await as_person(world.member).get(path)).status_code == 404
