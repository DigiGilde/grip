"""Fixtures for the vacancy API tests. All names and amounts are fictional."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import DEV_PERSON_COOKIE
from grip.services import assignments, events
from tests.vacancies.conftest import TEST_MAPPING, FakeChatClient, build_form_pdf


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@pytest.fixture
def act_as(client):
    """Make the following requests run as the given person."""

    def _act(person) -> None:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))

    return _act


@pytest.fixture
async def beheerder(create_person):
    return await create_person(
        "beheerder@example.org", name="Fictieve Beheerder", functions=["beheerder"]
    )


@pytest.fixture
async def planner(create_person):
    return await create_person(
        "planner@example.org", name="Fictieve Planner", functions=["planner"]
    )


@pytest.fixture
async def lezer(create_person):
    return await create_person(
        "lezer@example.org", name="Fictieve Lezer", functions=["lezer"]
    )


@pytest.fixture
async def manager(create_person):
    """Owner of the assignment the budget line belongs to; no function."""
    return await create_person("eigenaar@example.org", name="Fictieve Eigenaar")


@pytest.fixture
async def colleague(create_person):
    """A person of the instance without any function or role."""
    return await create_person("collega@example.org", name="Fictieve Collega")


@pytest.fixture
async def adviser(create_person):
    """Someone with an account who gets named as HR adviser."""
    return await create_person("adviseur@example.org", name="Fictieve Adviseur")


async def _line(db: AsyncSession, owner, name: str, role: str):
    assignment = await assignments.create_assignment(db, name=name, actor=owner)
    line = await assignments.add_budget_line(
        db,
        assignment.id,
        description=role,
        kind="personnel",
        actor=owner,
        role=role,
        fte=Decimal("0.8"),
        rate_category="C",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
    )
    return line


@pytest.fixture
async def budget_line(db_session, manager):
    return await _line(db_session, manager, "Opdracht Alfa", "Backend-ontwikkelaar")


@pytest.fixture
async def other_budget_line(db_session, beheerder):
    """A line on an assignment the manager has nothing to do with."""
    return await _line(db_session, beheerder, "Opdracht Beta", "Productmanager")


@pytest.fixture
def blank_form() -> bytes:
    text = [f["name"] for f in TEST_MAPPING["fields"] if f["type"] == "text"]
    boxes = [f["name"] for f in TEST_MAPPING["fields"] if f["type"] == "checkbox"]
    return build_form_pdf(text, boxes)


@pytest.fixture
def filled_form() -> bytes:
    text = [f["name"] for f in TEST_MAPPING["fields"] if f["type"] == "text"]
    boxes = [f["name"] for f in TEST_MAPPING["fields"] if f["type"] == "checkbox"]
    return build_form_pdf(
        text,
        boxes,
        text_values={"aanvrager": "Fictieve Aanvrager"},
        checked={"decl_ja"},
    )


@pytest.fixture
def test_mapping():
    return TEST_MAPPING


@pytest.fixture
def fake_model(monkeypatch) -> FakeChatClient:
    """Stand in for the language model in the service the route calls."""
    fake = FakeChatClient("Concepttekst van het model voor deze vacature.")
    monkeypatch.setattr(
        "grip.services.vacancies.service.get_chat_client", lambda *a, **k: fake
    )
    return fake
