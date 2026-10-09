"""The tasks keep working around a kept request form. All names are fictional.

A vacancy with a stored form and named advisers once took the task list and
the head of every vacancy down for everyone. The state is built here exactly:
a stored form, three people named for advice and approval, one of them with
an account and one outside grip, read as three different people.
"""

from __future__ import annotations

import pytest

from grip.services import stored_documents
from grip.tasks import cases
from tests.api.vacancies.test_request_forms_api import _template, _vacancy
from tests.api.vacancies.test_vacancies_api import BASE, _decide


async def _named(client, act_as, beheerder, vid: str) -> None:
    """Name who advises and approves: one with an account, two outside grip."""
    act_as(beheerder)
    for kind, body in (
        (
            "hr_advice",
            {
                "person_name": "Fictieve Adviseur",
                "person_email": "adviseur@example.org",
            },
        ),
        ("control_advice", {"person_name": "Fictieve Controller"}),
        ("approval", {"person_name": "Fictieve Directeur"}),
    ):
        response = await _decide(client, vid, kind, **body)
        assert response.status_code == 200, response.text


async def _read_as(client, act_as, person, vid: str) -> tuple[dict, dict | None]:
    act_as(person)
    mine = await client.get("/api/tasks/mine")
    assert mine.status_code == 200, mine.text
    course = await client.get(f"/api/tasks/cases/vacancy/{vid}/course")
    assert course.status_code in (200, 404), course.text
    return mine.json(), course.json() if course.status_code == 200 else None


async def test_a_kept_form_and_named_advisers_leave_the_tasks_working_for_everyone(
    client,
    act_as,
    manager,
    beheerder,
    adviser,
    budget_line,
    blank_form,
    test_mapping,
    db_session,
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    vid = await _vacancy(client, act_as, manager, budget_line)
    act_as(manager)
    assert (await client.post(f"{BASE}/{vid}/request-forms")).status_code == 201
    await _named(client, act_as, beheerder, vid)
    # As in a request of its own: nothing is in the session yet, so a value
    # that is loaded lazily would have to be fetched in the middle of reading.
    people = [(p.id, p) for p in (manager, adviser, beheerder)]
    db_session.expunge_all()

    for _, person in people:
        mine, course = await _read_as(client, act_as, person, vid)
        assert mine["failed_cases"] == 0
        if course is not None:
            assert course["course"]["current_label"] == "Advies en akkoord"

    # The requester hears that the form no longer fits: names were added.
    mine, _ = await _read_as(client, act_as, manager, vid)
    assert "Maak het aanvraagformulier" in " ".join(
        t["headline"] for t in mine["items"]
    )
    # The adviser with an account has her advice to give.
    mine, _ = await _read_as(client, act_as, adviser, vid)
    assert any("advies" in t["headline"].lower() for t in mine["items"])


async def test_whether_the_form_still_fits_is_known_without_opening_the_file(
    client,
    act_as,
    manager,
    beheerder,
    adviser,
    budget_line,
    blank_form,
    test_mapping,
    monkeypatch,
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    vid = await _vacancy(client, act_as, manager, budget_line)
    act_as(manager)
    url = f"{BASE}/{vid}/request-forms"
    assert (await client.post(url)).status_code == 201

    async def never(*args, **kwargs):
        raise AssertionError("the kept file was opened to answer a question")

    monkeypatch.setattr(stored_documents, "owned_document", never)

    # Fits: no new form is asked for.
    mine, _ = await _read_as(client, act_as, manager, vid)
    assert "Maak het aanvraagformulier" not in " ".join(
        t["headline"] for t in mine["items"]
    )
    assert (await client.get(url)).json()["changed"] == []

    # Changed: known from what was kept with the form, still without the file.
    await _named(client, act_as, beheerder, vid)
    act_as(manager)
    changed = (await client.get(url)).json()["changed"]
    assert "Naam van de HR-adviseur" in changed
    mine, _ = await _read_as(client, act_as, manager, vid)
    assert "Maak het aanvraagformulier" in " ".join(
        t["headline"] for t in mine["items"]
    )


async def test_one_case_with_failing_facts_does_not_take_the_others_down(
    client,
    act_as,
    manager,
    beheerder,
    budget_line,
    blank_form,
    test_mapping,
    monkeypatch,
    caplog,
) -> None:
    await _template(client, act_as, beheerder, blank_form, test_mapping)
    broken = await _vacancy(client, act_as, manager, budget_line)
    act_as(manager)
    # The owner has other work too: the budget of her assignment.
    before = (await client.get("/api/tasks/mine")).json()
    assert before["items"], "the requester has tasks to compare with"

    real = cases._request_form_facts

    async def failing(db, vacancy):
        if str(vacancy.id) == broken:
            raise RuntimeError("the facts of this vacancy cannot be read")
        return await real(db, vacancy)

    monkeypatch.setattr(cases, "_request_form_facts", failing)

    mine, course = await _read_as(client, act_as, manager, broken)
    # Everyone keeps their list; the tasks of the broken case stay as they were.
    assert [t["id"] for t in mine["items"]] == [t["id"] for t in before["items"]]
    assert mine["failed_cases"] == 0
    # Its head falls back to no course instead of an error.
    assert course is not None and course["course"] is None
    assert "could not be read" in caplog.text

    # Who keeps the instance is told that it happened.
    mine, _ = await _read_as(client, act_as, beheerder, broken)
    assert mine["failed_cases"] == 1


@pytest.fixture(autouse=True)
def _quiet(caplog):
    caplog.set_level("ERROR")
