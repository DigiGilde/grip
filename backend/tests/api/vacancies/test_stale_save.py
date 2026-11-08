"""A save on top of someone else's change of a vacancy or a role is refused.
All names are fictional."""

from __future__ import annotations

from tests.api.vacancies.test_vacancies_api import BASE, _create, _motivate


def _if_match(record_id: str, version: int) -> dict[str, str]:
    return {"If-Match": f'"{record_id}:{version}"'}


async def test_a_vacancy_changed_meanwhile_refuses_the_older_save(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    vacancy = await _create(client, budget_line)
    vid, opened = vacancy["id"], vacancy["version"]

    first = await client.patch(
        f"{BASE}/{vid}", json={"scale": 12}, headers=_if_match(vid, opened)
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] > opened

    stale = await client.patch(
        f"{BASE}/{vid}", json={"scale": 13}, headers=_if_match(vid, opened)
    )
    assert stale.status_code == 409, stale.text
    problem = stale.json()
    assert problem["code"] == "StaleWriteError"
    assert "intussen gewijzigd" in problem["detail"]
    assert problem["changed_by"] == manager.name
    assert (await client.get(f"{BASE}/{vid}")).json()["scale"] == 12

    # Without the header nothing is checked: older screens keep working.
    plain = await client.patch(f"{BASE}/{vid}", json={"scale": 13})
    assert plain.status_code == 200, plain.text


async def test_a_role_changed_meanwhile_refuses_the_older_save(
    client, act_as, beheerder
) -> None:
    act_as(beheerder)
    made = await client.post("/api/catalogue-roles", json={"name": "Fictieve rol"})
    assert made.status_code == 201, made.text
    role = made.json()
    rid, opened = role["id"], role["version"]
    url = f"/api/catalogue-roles/{rid}"
    first = await client.patch(
        url, json={"description": "Eerste"}, headers=_if_match(rid, opened)
    )
    assert first.status_code == 200, first.text
    stale = await client.patch(
        url, json={"description": "Tweede"}, headers=_if_match(rid, opened)
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "StaleWriteError"


async def _submitted(client, act_as, beheerder, budget_line) -> str:
    act_as(beheerder)
    vid = (await _create(client, budget_line))["id"]
    await _motivate(client, vid)
    sent = await client.post(
        f"{BASE}/{vid}/submit", json={"requested_on": "2026-09-28"}
    )
    assert sent.status_code == 200, sent.text
    return vid


async def test_recording_a_decision_from_the_current_version_is_accepted(
    client, act_as, beheerder, budget_line
) -> None:
    vid = await _submitted(client, act_as, beheerder, budget_line)
    opened = (await client.get(f"{BASE}/{vid}")).json()["version"]
    response = await client.put(
        f"{BASE}/{vid}/decisions/control_advice",
        json={
            "person_name": "Fictieve Controller",
            "agreed": True,
            "note": "Akkoord",
            "decided_on": "2026-09-30",
        },
        headers=_if_match(vid, opened),
    )
    assert response.status_code == 200, response.text


async def test_recording_a_decision_on_top_of_a_change_is_refused(
    client, act_as, beheerder, budget_line
) -> None:
    vid = await _submitted(client, act_as, beheerder, budget_line)
    opened = (await client.get(f"{BASE}/{vid}")).json()["version"]
    changed = await client.patch(
        f"{BASE}/{vid}", json={"scale": 12}, headers=_if_match(vid, opened)
    )
    assert changed.status_code == 200, changed.text
    response = await client.put(
        f"{BASE}/{vid}/decisions/control_advice",
        json={"person_name": "Fictieve Controller", "agreed": True},
        headers=_if_match(vid, opened),
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "StaleWriteError"
