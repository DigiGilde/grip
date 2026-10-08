"""Fixtures for the API tests of the assignment slice.

All names and amounts are fictional. Category D bills 18,000 per month in
2026, as in the worked examples of the domain description.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import DEV_PERSON_COOKIE
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.person import Person
from grip.services import assignments, events, rates

RATES_2026 = {"A": 900000, "B": 1200000, "C": 1500000, "D": 1800000, "E": 2100000}
SCALES = {8: "A", 9: "A", 10: "B", 11: "B", 12: "C", 13: "C", 14: "D", 15: "D"}


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@dataclass
class World:
    beheerder: Person
    lezer: Person
    planner: Person
    owner: Person
    member: Person
    colleague: Person
    outsider: Person
    assignment: Assignment
    other_assignment: Assignment
    line: BudgetLine
    fixed_line: BudgetLine
    member_allocation: Allocation
    colleague_allocation: Allocation


@pytest.fixture
def as_person(client: AsyncClient):
    """Make the following requests come from this person."""

    def _as(person: Person) -> AsyncClient:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return client

    return _as


@pytest.fixture
async def world(db_session: AsyncSession, create_person) -> World:
    """One assignment with an owner, a team of two, and people around it."""
    db = db_session
    beheerder = await create_person(
        "beheer@example.org", name="Bea Beheer", functions=["beheerder"]
    )
    lezer = await create_person(
        "lezer@example.org", name="Lex Lezer", functions=["lezer"]
    )
    planner = await create_person(
        "planner@example.org", name="Pim Planner", functions=["planner"]
    )
    owner = await create_person("eigenaar@example.org", name="Eva Eigenaar")
    member = await create_person("lid@example.org", name="Lot Lid")
    colleague = await create_person("collega@example.org", name="Cas Collega")
    outsider = await create_person("buiten@example.org", name="Bo Buiten")

    await rates.create_rate_card(db, 2026, actor=beheerder)
    for category, cents in RATES_2026.items():
        await rates.set_rate_band(db, 2026, category, cents, actor=beheerder)
    for scale, category in SCALES.items():
        await rates.set_scale_band(db, 2026, scale, category, actor=beheerder)
    await rates.set_rate_card_status(db, 2026, "active", actor=beheerder)
    # The member bills in category D, the colleague in C on a D line (R14).
    await rates.set_person_scale(db, member.id, date(2026, 1, 1), 14, actor=beheerder)
    await rates.set_person_scale(
        db, colleague.id, date(2026, 1, 1), 12, actor=beheerder
    )

    client_org = await assignments.upsert_organisation(db, name="Voorbeeldministerie")
    assignment = await assignments.create_assignment(
        db,
        name="Opdracht Alfa 2026",
        actor=owner,
        client_organisation_id=client_org.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        context_refs=["https://corpus.example/id/node/1"],
    )
    await assignments.update_assignment(
        db, assignment.id, actor=owner, quoted_amount_cents=40000000
    )
    other = await assignments.create_assignment(
        db, name="Opdracht Beta 2026", actor=beheerder
    )
    line = await assignments.add_budget_line(
        db,
        assignment.id,
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        actor=owner,
    )
    fixed = await assignments.add_budget_line(
        db,
        assignment.id,
        description="Hosting",
        kind="fixed",
        amount_cents=1500000,
        year=2026,
        actor=owner,
    )
    member_allocation = await assignments.add_allocation(
        db,
        line.id,
        member.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal("50"),
        actor=owner,
    )
    colleague_allocation = await assignments.add_allocation(
        db,
        line.id,
        colleague.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal("30"),
        actor=owner,
    )
    return World(
        beheerder=beheerder,
        lezer=lezer,
        planner=planner,
        owner=owner,
        member=member,
        colleague=colleague,
        outsider=outsider,
        assignment=assignment,
        other_assignment=other,
        line=line,
        fixed_line=fixed,
        member_allocation=member_allocation,
        colleague_allocation=colleague_allocation,
    )


def by_id(items: list[dict[str, Any]], key: str, value: Any) -> dict[str, Any]:
    return next(i for i in items if i[key] == str(value))
