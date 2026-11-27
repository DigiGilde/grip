"""The proof on the test clients really fires."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from grip.models.assignment import Assignment
from grip.services import assignments


async def _a_case(client, create_person) -> str:
    await create_person("beheerder@example.org", functions=["beheerder"])
    response = await client.post("/api/assignments", json={"name": "Voorbeeldtraject"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_a_request_is_followed_and_its_case_compared(
    client, chronicle_proof, create_person
):
    await _a_case(client, create_person)
    assert chronicle_proof.requests >= 1
    assert chronicle_proof.cases_compared == 1
    assert chronicle_proof.problems == []


async def test_a_write_in_a_request_without_a_fact_is_a_problem(
    client, chronicle_proof, create_person, monkeypatch
):
    case = await _a_case(client, create_person)
    real_update = assignments.update_assignment

    async def around_the_chronicle(session, assignment_id, **changes):
        row = await session.get(Assignment, assignment_id)
        row.name = "Buiten de kroniek"
        return await real_update(session, assignment_id, **changes)

    monkeypatch.setattr(assignments, "update_assignment", around_the_chronicle)
    response = await client.patch(f"/api/assignments/{case}", json={"notes": "Iets"})
    assert response.status_code == 200, response.text
    assert any("changed assignment" in item for item in chronicle_proof.problems)
    assert any(".name:" in item for item in chronicle_proof.problems)
    chronicle_proof.problems.clear()


async def test_a_statement_in_a_request_without_a_fact_is_a_problem(
    client, chronicle_proof, create_person, monkeypatch
):
    case = await _a_case(client, create_person)
    real_update = assignments.update_assignment

    async def around_the_chronicle(session, assignment_id, **changes):
        await session.execute(
            text("UPDATE assignment SET name = 'Buiten de kroniek' WHERE id = :id"),
            {"id": assignment_id},
        )
        return await real_update(session, assignment_id, **changes)

    monkeypatch.setattr(assignments, "update_assignment", around_the_chronicle)
    response = await client.patch(f"/api/assignments/{case}", json={"notes": "Iets"})
    assert response.status_code == 200, response.text
    assert any("statement on assignment" in item for item in chronicle_proof.problems)
    chronicle_proof.problems.clear()


async def test_a_hand_edit_outside_a_request_only_stops_the_comparing(
    client, chronicle_proof, create_person, db_session
):
    case = await _a_case(client, create_person)
    row = await db_session.get(Assignment, UUID(case))
    row.name = "Klaargezet door de test"
    response = await client.patch(f"/api/assignments/{case}", json={"notes": "Iets"})
    assert response.status_code == 200, response.text
    assert chronicle_proof.problems == []
