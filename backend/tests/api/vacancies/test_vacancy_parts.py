"""The parts of a vacancy and where each one stands. All names are fictional."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from grip.models.task import Task
from grip.models.vacancy import Vacancy
from grip.services.vacancies import parts as vacancy_parts
from grip.tasks import telling
from tests.api.vacancies.test_vacancies_api import (
    BASE,
    _approve,
    _create,
    _decide,
    _motivate,
    _publish,
)

PART_KEYS = ["request", "decisions", "text", "fulfilment", "details", "history"]


async def _parts(client, vacancy_id: str) -> dict:
    response = await client.get(f"{BASE}/{vacancy_id}/parts")
    assert response.status_code == 200, response.text
    return response.json()


def _by_key(body: dict) -> dict[str, dict]:
    return {part["key"]: part for part in body["parts"]}


def _states(body: dict) -> dict[str, str | None]:
    return {part["key"]: part["state"] for part in body["parts"]}


async def _request(client, act_as, manager, budget_line, **extra) -> str:
    act_as(manager)
    vacancy = await _create(client, budget_line, **extra)
    await _motivate(client, vacancy["id"])
    response = await client.post(
        f"{BASE}/{vacancy['id']}/submit", json={"requested_on": "2026-09-28"}
    )
    assert response.status_code == 200, response.text
    return vacancy["id"]


async def _name_the_deciders(client, act_as, beheerder, vacancy_id: str) -> None:
    """Name who advises and approves, all outside grip."""
    act_as(beheerder)
    for kind, name in (
        ("hr_advice", "Fictieve Adviseur"),
        ("control_advice", "Fictieve Controller"),
        ("approval", "Fictieve Directeur"),
    ):
        response = await _decide(client, vacancy_id, kind, person_name=name)
        assert response.status_code == 200, response.text


# --- the row of a task -------------------------------------------------------


@pytest.mark.parametrize(
    ("template_key", "row"),
    [
        ("werving.aanvraag_voorbereiden", "request"),
        ("werving.formulier_maken", "request"),
        ("werving.getekend_formulier_vastleggen", "request"),
        ("werving.advies_hr", "decisions"),
        ("werving.advies_control", "decisions"),
        ("werving.akkoord", "decisions"),
        ("werving.openstellen", "text"),
        ("werving.link_vastleggen", "text"),
        ("teksten.schrijven", "text"),
        ("teksten.opmerkingen_verwerken", "text"),
        ("teksten.beoordelen", "text"),
        ("werving.vervullen", "fulfilment"),
        ("werving.collega_voorstellen", "fulfilment"),
        ("werving.account_aanvragen", "fulfilment"),
    ],
)
def test_every_task_of_a_vacancy_points_at_one_row(template_key, row) -> None:
    task = Task(template_key=template_key, vacancy_id=uuid4())
    assert vacancy_parts.row_of(task) == row


def test_a_text_that_is_written_points_at_the_text_row_in_every_situation() -> None:
    task = Task(template_key="teksten.schrijven", vacancy_id=uuid4())
    for situation in (None, "text_ready", "text_agreed"):
        task.situation = situation
        assert vacancy_parts.row_of(task) == "text"


def test_a_task_without_guidance_points_at_no_row() -> None:
    assert vacancy_parts.row_of(Task(title="Eigen taak")) is None


def test_no_task_of_the_plan_leads_to_a_destination_without_a_row() -> None:
    """A new destination for a vacancy must be given a row on purpose."""
    for key, guide in telling.guidance().templates.items():
        if not key.startswith(("werving.", "teksten.")):
            continue
        for situation in (None, *guide.situations):
            task = Task(template_key=key, vacancy_id=uuid4(), situation=situation)
            assert vacancy_parts.row_of(task) is not None, (key, situation)


# --- what a reader who runs the vacancy sees ---------------------------------


async def test_a_draft_vacancy_is_at_its_request(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line, addressee_name=None)
    body = await _parts(client, vacancy["id"])
    assert body["vacancy_id"] == vacancy["id"]
    assert [part["key"] for part in body["parts"]] == PART_KEYS
    request = _by_key(body)["request"]
    assert request["label"] == "Aanvraag"
    assert request["state"] == "current"
    assert request["notice"] == "Maak de aanvraag compleet"
    assert _by_key(body)["decisions"]["state"] == "future"
    assert _by_key(body)["decisions"]["notice"] is None
    assert body["tasks_link"] is True


async def test_the_parts_come_in_one_order_with_their_words(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    body = await _parts(client, vacancy["id"])
    assert [(part["key"], part["label"]) for part in body["parts"]] == [
        ("request", "Aanvraag"),
        ("decisions", "Advies en akkoord"),
        ("text", "Tekst en openstellen"),
        ("fulfilment", "Vervullen"),
        ("details", "Gegevens"),
        ("history", "Geschiedenis"),
    ]
    assert _by_key(body)["details"]["state"] is None
    assert _by_key(body)["history"]["state"] is None


async def test_a_vacancy_waits_on_its_advisers_for_the_one_who_runs_it(
    client, act_as, manager, beheerder, budget_line
) -> None:
    vid = await _request(client, act_as, manager, budget_line)
    await _name_the_deciders(client, act_as, beheerder, vid)
    act_as(manager)
    parts = _by_key(await _parts(client, vid))
    assert parts["request"]["state"] == "done"
    assert parts["decisions"]["state"] == "waiting"
    assert parts["decisions"]["notice"].startswith("Wacht op ")
    assert "Fictieve Adviseur" in parts["decisions"]["notice"]


async def test_the_one_who_must_still_name_the_advisers_is_at_the_move(
    client, act_as, manager, budget_line
) -> None:
    vid = await _request(client, act_as, manager, budget_line)
    act_as(manager)
    decisions = _by_key(await _parts(client, vid))["decisions"]
    assert decisions["state"] == "current"


async def test_the_adviser_with_an_account_has_the_advice_to_give(
    client, act_as, manager, beheerder, adviser, budget_line
) -> None:
    vid = await _request(client, act_as, manager, budget_line)
    act_as(beheerder)
    await _decide(
        client,
        vid,
        "hr_advice",
        person_name="Fictieve Adviseur",
        person_email="adviseur@example.org",
    )
    act_as(adviser)
    parts = _by_key(await _parts(client, vid))
    assert parts["decisions"]["state"] == "current"
    assert not parts["decisions"]["notice"].startswith("Wacht op")
    assert parts["request"]["state"] == "done"


async def test_two_parts_are_at_the_move_at_once(
    client, act_as, manager, beheerder, budget_line
) -> None:
    """A published vacancy: the link is recorded under the text, and who was
    hired is recorded under fulfilment."""
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    act_as(manager)
    body = await _parts(client, vacancy["id"])
    states = _states(body)
    assert states["request"] == "done"
    assert states["decisions"] == "done"
    assert states["text"] == "current"
    assert states["fulfilment"] == "current"
    assert (
        _by_key(body)["text"]["notice"]
        == "Leg de link naar de gepubliceerde vacature vast"
    )
    assert _by_key(body)["fulfilment"]["notice"] == "Leg vast wie is aangenomen"


async def test_a_part_whose_task_lies_with_someone_else_is_waited_on(
    client, act_as, manager, beheerder, planner, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    # The owner holds the tasks; a planner who also runs the vacancy sees
    # them as someone else's.
    act_as(planner)
    parts = _by_key(await _parts(client, vacancy["id"]))
    assert parts["text"]["state"] == "waiting"
    assert parts["text"]["notice"].startswith("Wacht op ")
    assert parts["fulfilment"]["state"] == "waiting"
    assert parts["decisions"]["state"] == "done"


async def test_a_filled_vacancy_is_done_in_every_step(
    client, act_as, manager, beheerder, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    act_as(manager)
    link = await client.put(
        f"{BASE}/{vacancy['id']}/publications",
        json={"place": "internal", "url": "https://intranet.example/v/1"},
    )
    assert link.status_code == 200, link.text
    response = await client.post(f"{BASE}/{vacancy['id']}/fill", json={})
    assert response.status_code == 200, response.text
    states = _states(await _parts(client, vacancy["id"]))
    assert [states[key] for key in ("request", "decisions", "text", "fulfilment")] == [
        "done"
    ] * 4


async def test_a_withdrawn_vacancy_says_so_where_it_was(
    client, act_as, manager, budget_line
) -> None:
    vid = await _request(client, act_as, manager, budget_line)
    response = await client.post(f"{BASE}/{vid}/withdraw", json={})
    assert response.status_code == 200, response.text
    parts = _by_key(await _parts(client, vid))
    assert parts["request"]["state"] is None
    assert parts["request"]["notice"] == "Ingetrokken"
    assert parts["decisions"]["state"] is None
    assert parts["decisions"]["notice"] is None


# --- a candidate who is ready ------------------------------------------------


async def test_a_ready_candidate_has_the_text_row_once_the_motivation_is_set(
    client, act_as, manager, beheerder, lezer, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(
        client,
        budget_line,
        vacancy_type="gerede",
        candidate_person_id=str(colleague.id),
    )
    await _approve(client, act_as, beheerder, vacancy["id"])
    for person in (manager, beheerder, lezer):
        act_as(person)
        body = await _parts(client, vacancy["id"])
        text = _by_key(body)["text"]
        assert text["label"] == "Tekst", person.name
        assert [part["key"] for part in body["parts"]][:3] == [
            "request",
            "decisions",
            "text",
        ], person.name


def test_who_has_nothing_under_the_text_gets_no_text_row() -> None:
    def matter(vacancy_type, can_edit, **had) -> bool:
        facts = {"has_texts": False, "has_vacancy_text": False, "has_steps": False}
        return vacancy_parts.has_text_matter(
            Vacancy(vacancy_type=vacancy_type),
            can_edit=can_edit,
            **(facts | had),
        )

    assert matter("gerede", False) is False
    # The one who edits may still choose to write a vacancy text.
    assert matter("gerede", True) is True
    # A vacancy that is opened needs its text anyway: nothing to choose.
    assert matter("regulier", True) is False
    assert matter("gerede", False, has_texts=True) is True
    assert matter("gerede", False, has_steps=True) is True


async def test_a_ready_candidate_still_reaches_the_motivation_to_write(
    client, act_as, manager, colleague, budget_line
) -> None:
    """The motivation is written under Tekst; a task must not lead nowhere."""
    act_as(manager)
    vacancy = await _create(
        client,
        budget_line,
        vacancy_type="gerede",
        candidate_person_id=str(colleague.id),
    )
    body = await _parts(client, vacancy["id"])
    text = _by_key(body).get("text")
    assert text is not None
    assert text["label"] == "Tekst"
    assert text["state"] == "current"


# --- fulfilment and details --------------------------------------------------


async def test_fulfilment_is_for_who_may_edit(
    client, act_as, manager, beheerder, lezer, adviser, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    for person, expected in ((manager, True), (beheerder, True), (lezer, False)):
        act_as(person)
        keys = [part["key"] for part in (await _parts(client, vacancy["id"]))["parts"]]
        assert ("fulfilment" in keys) is expected, person.name
    # Named for a decision: reads the vacancy, does not edit it.
    act_as(beheerder)
    await _decide(client, vacancy["id"], "hr_advice", person_id=str(adviser.id))
    act_as(adviser)
    keys = [part["key"] for part in (await _parts(client, vacancy["id"]))["parts"]]
    assert "fulfilment" not in keys


async def test_details_are_there_when_they_hold_more_than_the_head(
    client, act_as, manager, lezer, budget_line
) -> None:
    act_as(manager)
    with_contract = await _create(client, budget_line)
    act_as(lezer)
    assert "details" in _states(await _parts(client, with_contract["id"]))
    # A reader without edit rights and without anything extra to read.
    act_as(manager)
    bare = await _create(client, budget_line, contract_type=None)
    act_as(manager)
    assert "details" in _states(await _parts(client, bare["id"]))
    act_as(lezer)
    assert "details" not in _states(await _parts(client, bare["id"]))


# --- who reads what ----------------------------------------------------------


async def test_a_reader_of_the_published_text_gets_no_parts(
    client, act_as, manager, beheerder, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    act_as(colleague)
    response = await client.get(f"{BASE}/{vacancy['id']}/parts")
    assert response.status_code == 200
    assert response.json() == {
        "vacancy_id": vacancy["id"],
        "parts": [],
        "tasks_link": False,
    }
    assert "Fictie" not in response.text


async def test_the_text_part_is_not_offered_to_who_reads_only_the_published_vacancy(
    client, act_as, db_session, manager, beheerder, colleague, budget_line
) -> None:
    from grip.access import Subject
    from grip.access.deps import get_decider, get_relation_source
    from grip.core.config import get_settings
    from grip.tasks.access import TaskAccess
    from grip.tasks.cases import load_vacancy_cases

    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    vacancy_id = UUID(vacancy["id"])

    async def keys_for(person, functions: frozenset[str], can_edit: bool) -> set[str]:
        decider = get_decider(get_relation_source(db_session, get_settings()))
        access = TaskAccess(
            db_session, decider, Subject.for_person(person.id, functions)
        )
        found = await vacancy_parts.part_keys_of(
            db_session,
            access,
            await load_vacancy_cases(db_session, {vacancy_id}),
            {vacancy_id: can_edit},
        )
        return found[vacancy_id]

    assert "text" not in await keys_for(colleague, frozenset(), can_edit=True)
    assert "text" in await keys_for(beheerder, frozenset({"beheerder"}), can_edit=True)


async def test_a_draft_is_not_there_for_who_may_not_read_it(
    client, act_as, manager, colleague, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    act_as(colleague)
    hidden = await client.get(f"{BASE}/{vacancy['id']}/parts")
    unknown = await client.get(f"{BASE}/{uuid4()}/parts")
    assert hidden.status_code == 404
    assert hidden.json() == unknown.json()


async def test_a_lezer_gets_the_steps_without_a_name(
    client, act_as, manager, beheerder, lezer, budget_line
) -> None:
    vid = await _request(client, act_as, manager, budget_line)
    act_as(beheerder)
    await _decide(
        client,
        vid,
        "hr_advice",
        person_name="Fictieve Adviseur",
        person_email="adviseur@example.org",
    )
    act_as(lezer)
    response = await client.get(f"{BASE}/{vid}/parts")
    assert response.status_code == 200
    body = response.json()
    assert _by_key(body)["decisions"]["state"] == "waiting"
    assert _by_key(body)["decisions"]["notice"].startswith("Wacht op ")
    assert "Fictie" not in response.text
    assert "Fictieve" not in json.dumps(body)


async def test_a_lezer_hears_no_name_on_a_published_vacancy(
    client, act_as, manager, beheerder, lezer, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    act_as(lezer)
    response = await client.get(f"{BASE}/{vacancy['id']}/parts")
    assert response.status_code == 200
    body = response.json()
    assert _by_key(body)["text"]["state"] == "waiting"
    assert "Fictie" not in response.text
    assert "fulfilment" not in _by_key(body)
    # The same meaning as on an assignment: the reader may change the tasks.
    assert body["tasks_link"] is False


async def test_someone_named_for_a_decision_hears_no_name_of_the_owner(
    client, act_as, manager, beheerder, adviser, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    act_as(beheerder)
    await _decide(client, vacancy["id"], "hr_advice", person_id=str(adviser.id))
    act_as(adviser)
    response = await client.get(f"{BASE}/{vacancy['id']}/parts")
    assert response.status_code == 200
    assert "Fictieve Eigenaar" not in response.text
    assert "Fictieve Beheerder" not in response.text


async def test_the_one_who_runs_the_vacancy_may_hear_names(
    client, act_as, manager, beheerder, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _publish(client, act_as, beheerder, vacancy["id"])
    act_as(beheerder)
    # The tasks are the owner's; the beheerder may be told whose.
    text = _by_key(await _parts(client, vacancy["id"]))["text"]
    assert text["state"] == "waiting"
    assert "Fictieve Eigenaar" in text["notice"]


async def test_someone_asked_to_judge_a_text_sees_the_text_row_and_the_own_task(
    client, act_as, manager, adviser, budget_line
) -> None:
    from tests.api.vacancies.test_text_work import _save

    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    assert (await _save(client, vid, "## Dit ga je doen\n\nBouwen.")).status_code == 201
    offered = await client.post(
        f"{BASE}/{vid}/text-work/reviews",
        json={"kind": "vacancy_text", "reviewer_ids": [str(adviser.id)]},
    )
    assert offered.status_code == 201, offered.text

    act_as(adviser)
    response = await client.get(f"{BASE}/{vid}/parts")
    assert response.status_code == 200, response.text
    body = response.json()
    assert _by_key(body)["text"]["state"] == "current"
    assert "fulfilment" not in _by_key(body)
    assert "Fictieve Eigenaar" not in response.text
    assert body["tasks_link"] is False

    # The task is the reviewer's own: it is on the list, and the case of it
    # opens without a name.
    mine = (await client.get("/api/tasks/mine")).json()["items"]
    assert [item["title"] for item in mine if item["title"].startswith("Beoordeel")]
    case = await client.get(f"/api/tasks/cases/vacancy/{vid}")
    assert case.status_code == 200
    assert "Fictieve Eigenaar" not in case.text
