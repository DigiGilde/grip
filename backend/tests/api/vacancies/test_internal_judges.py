"""Who can be asked to advise, approve or review something internal.

Someone who is in grip for a client-side right only (asking for a quote,
signing one) is not offered and is refused. All names are fictional.
"""

from __future__ import annotations

import pytest

from tests.api.vacancies.test_text_work import _save
from tests.api.vacancies.test_vacancies_api import BASE, _create, _decide, _motivate


@pytest.fixture
async def signatory(create_person):
    return await create_person(
        "tekenaar@example.org", name="Fictieve Tekenaar", functions=["tekenbevoegde"]
    )


@pytest.fixture
async def requester_of_quotes(create_person):
    return await create_person(
        "vrager@example.org", name="Fictieve Vrager", functions=["aanvrager"]
    )


@pytest.fixture
async def signatory_and_reader(create_person):
    return await create_person(
        "beide@example.org",
        name="Fictieve Beide",
        functions=["tekenbevoegde", "lezer"],
    )


async def _requested(client, act_as, manager, budget_line) -> str:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    await _motivate(client, vacancy["id"])
    response = await client.post(
        f"{BASE}/{vacancy['id']}/submit", json={"requested_on": "2026-09-28"}
    )
    assert response.status_code == 200, response.text
    return vacancy["id"]


async def test_the_list_to_pick_from_leaves_out_client_side_only_people(
    client,
    act_as,
    beheerder,
    colleague,
    signatory,
    requester_of_quotes,
    signatory_and_reader,
) -> None:
    act_as(beheerder)
    everyone = {
        item["name"]
        for item in (await client.get("/api/person-options")).json()["items"]
    }
    judges = {
        item["name"]
        for item in (await client.get("/api/person-options?oordeel=true")).json()[
            "items"
        ]
    }
    assert {signatory.name, requester_of_quotes.name} <= everyone
    assert signatory.name not in judges
    assert requester_of_quotes.name not in judges
    # A colleague without any function, and someone with another function too.
    assert colleague.name in judges
    assert signatory_and_reader.name in judges


async def test_advice_and_approval_refuse_a_client_side_only_person(
    client, act_as, manager, beheerder, budget_line, signatory, colleague
) -> None:
    vid = await _requested(client, act_as, manager, budget_line)
    act_as(beheerder)
    for kind in ("hr_advice", "control_advice", "approval"):
        refused = await _decide(
            client, vid, kind, person_id=str(signatory.id), agreed=True
        )
        assert refused.status_code == 422, refused.text
        assert "namens een opdrachtgever" in refused.text
    accepted = await _decide(
        client, vid, "hr_advice", person_id=str(colleague.id), agreed=True
    )
    assert accepted.status_code == 200, accepted.text


async def test_a_request_is_not_addressed_to_a_client_side_only_person(
    client, act_as, manager, budget_line, signatory
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    refused = await client.patch(
        f"{BASE}/{vacancy['id']}", json={"addressee_id": str(signatory.id)}
    )
    assert refused.status_code == 422, refused.text
    assert "namens een opdrachtgever" in refused.text


async def test_a_text_is_not_reviewed_by_a_client_side_only_person(
    client, act_as, manager, budget_line, signatory, colleague
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid = vacancy["id"]
    await _save(client, vid, "## Dit ga je doen\n\nEerste versie.")
    work = (await client.get(f"{BASE}/{vid}/text-work")).json()
    offered = {option["name"] for option in work["reviewer_options"]}
    assert signatory.name not in offered and colleague.name in offered
    refused = await client.post(
        f"{BASE}/{vid}/text-work/reviews",
        json={"kind": "vacancy_text", "reviewer_ids": [str(signatory.id)]},
    )
    assert refused.status_code == 422, refused.text
    assert "namens een opdrachtgever" in refused.text
