"""Which roles a vacancy can be made for, and who a vacancy for a known
candidate is for."""

from decimal import Decimal

from grip.services import assignments

BASE = "/api/vacancies"


async def _fill(db_session, line, person, actor):
    await assignments.add_allocation(
        db_session, line.id, person.id, fte_pct=Decimal(80), actor=actor
    )


async def test_a_filled_role_is_offered_apart_with_who_fills_it(
    client, act_as, db_session, manager, colleague, lezer, budget_line
) -> None:
    await _fill(db_session, budget_line, colleague, manager)
    act_as(manager)
    # "Unfilled" keeps meaning what it says.
    assert (await client.get(f"{BASE}/unfilled-roles")).json() == []
    (role,) = (await client.get(f"{BASE}/filled-roles")).json()
    assert role["budget_line_id"] == str(budget_line.id)
    assert role["tentative"] is True  # the assignment is not agreed yet
    assert role["filled_by"] == [
        {"person_name": "Fictieve Collega", "until": "2027-12-31"}
    ]
    # Someone who may not open a vacancy there gets nothing.
    act_as(colleague)
    assert (await client.get(f"{BASE}/filled-roles")).json() == []


async def test_a_vacancy_can_be_made_for_a_filled_role(
    client, act_as, db_session, manager, colleague, budget_line
) -> None:
    await _fill(db_session, budget_line, colleague, manager)
    act_as(manager)
    response = await client.post(
        BASE, json={"budget_line_id": str(budget_line.id), "vacancy_type": "regulier"}
    )
    assert response.status_code == 201, response.text
    # With a vacancy running it is no longer offered.
    assert (await client.get(f"{BASE}/filled-roles")).json() == []


async def test_unfilled_roles_say_when_the_assignment_is_not_agreed(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    (role,) = (await client.get(f"{BASE}/unfilled-roles")).json()
    assert role["tentative"] is True


async def test_a_known_candidate_vacancy_needs_the_candidate(
    client, act_as, manager, budget_line
) -> None:
    act_as(manager)
    response = await client.post(
        BASE, json={"budget_line_id": str(budget_line.id), "vacancy_type": "beoogd"}
    )
    assert response.status_code == 422
    assert "heeft een kandidaat nodig" in response.json()["detail"]


async def test_the_candidate_is_the_intended_person_of_the_line(
    client, act_as, manager, colleague, lezer, budget_line
) -> None:
    act_as(manager)
    response = await client.post(
        BASE,
        json={
            "budget_line_id": str(budget_line.id),
            "vacancy_type": "beoogd",
            "candidate_person_id": str(colleague.id),
        },
    )
    assert response.status_code == 201, response.text
    vacancy = response.json()
    assert vacancy["candidate_name"] == "Fictieve Collega"
    # One fact: it is on the budget line, not copied onto the vacancy.
    budget = (
        await client.get(f"/api/assignments/{vacancy['assignment_id']}/budget")
    ).json()
    line = next(item for item in budget["lines"] if item["id"] == str(budget_line.id))
    assert line["intended_person_id"] == str(colleague.id)
    # Without the right to see staffing, no name.
    act_as(lezer)
    seen = (await client.get(f"{BASE}/{vacancy['id']}")).json()
    assert "candidate_name" not in seen and "candidate_person_id" not in seen
    assert "Fictieve Collega" not in str(seen)


async def test_a_regular_vacancy_takes_no_candidate(
    client, act_as, manager, colleague, budget_line
) -> None:
    act_as(manager)
    response = await client.post(
        BASE,
        json={
            "budget_line_id": str(budget_line.id),
            "vacancy_type": "regulier",
            "candidate_person_id": str(colleague.id),
        },
    )
    assert response.status_code == 422
