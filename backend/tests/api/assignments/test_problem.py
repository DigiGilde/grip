"""Errors of the service layer become problem documents."""

from uuid import uuid4

from grip.core.problem import domain_error_status
from grip.services import errors


def test_status_per_kind_of_error():
    assert domain_error_status(errors.NotFoundError("Opdracht", "x")) == 404
    assert domain_error_status(errors.IllegalTransitionError("draft", "done")) == 409
    assert domain_error_status(errors.ClosedYearError(2025)) == 409
    assert domain_error_status(errors.MonthClosedError("2026-03")) == 409
    assert domain_error_status(errors.QuoteAlreadyDecidedError("accepted")) == 409
    assert domain_error_status(errors.DomainValidationError("x")) == 422
    assert domain_error_status(errors.QuoteHashMismatchError()) == 422


async def test_illegal_transition_is_a_conflict(world, as_person):
    client = as_person(world.owner)
    response = await client.post(
        f"/api/assignments/{world.assignment.id}/transition",
        json={"target": "completed"},
    )
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Statusovergang niet toegestaan"
    assert body["code"] == "IllegalTransitionError"
    assert "draft" in body["detail"]


async def test_invalid_input_from_the_service_is_422(world, as_person):
    client = as_person(world.owner)
    response = await client.post(
        f"/api/assignments/{world.assignment.id}/budget-lines",
        json={"description": "Zonder bedrag", "kind": "fixed"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "DomainValidationError"


async def test_unknown_assignment_is_404(world, as_person):
    client = as_person(world.beheerder)
    response = await client.get(f"/api/assignments/{uuid4()}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
