"""A small fictional instance for the API tests of rates, team, KPI and costs.

All names and amounts are made up. Category D bills 18,000 per month in
2026, as in the worked examples of the domain description.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import DEV_PERSON_COOKIE
from grip.models.person import Person
from grip.services import assignments, events, rates

RATES_2026 = {"A": 900000, "B": 1200000, "C": 1500000, "D": 1800000, "E": 2100000}
SCALES = {8: "A", 9: "A", 10: "B", 11: "B", 12: "C", 13: "C", 14: "D", 15: "D"}

# The period on screen in most tests: within the allocations below.
JUNE = {"period_start": "2026-06-01", "period_end": "2026-06-30"}


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@dataclass
class World:
    beheerder: Person
    planner: Person
    lezer: Person
    # Line manager of ``report``; holds no function and manages no assignment.
    lead: Person
    report: Person
    # Owner of assignment Alfa; holds no function.
    owner: Person
    # Hired, staffed on Alfa for all of 2026.
    hired: Person
    # Staffed nowhere, reports to nobody.
    outsider: Person
    alfa: Any
    alfa_line: Any
    beta: Any
    beta_line: Any


@pytest.fixture
def as_person(client):
    """Make the following requests run as the given person."""

    def _switch(person: Person) -> None:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))

    return _switch


@pytest.fixture
async def world(db_session: AsyncSession, create_person) -> World:
    db = db_session
    beheerder = await create_person(
        "beheerder@example.org", name="Bea Beheerder", functions=["beheerder"]
    )
    planner = await create_person(
        "planner@example.org", name="Piet Planner", functions=["planner"]
    )
    lezer = await create_person(
        "lezer@example.org", name="Lot Lezer", functions=["lezer"]
    )
    lead = await create_person("lead@example.org", name="Lies Leidinggevende")
    report = await create_person(
        "report@example.org", name="Rik Medewerker", manager_id=lead.id
    )
    owner = await create_person("owner@example.org", name="Olga Opdrachteigenaar")
    hired = await create_person("hired@example.org", name="Henk Inhuur")
    outsider = await create_person("outsider@example.org", name="Otto Overig")

    await rates.create_rate_card(db, 2026, actor=beheerder)
    for category, cents in RATES_2026.items():
        await rates.set_rate_band(db, 2026, category, cents, actor=beheerder)
    for scale, category in SCALES.items():
        await rates.set_scale_band(db, 2026, scale, category, actor=beheerder)
    await rates.set_rate_card_status(db, 2026, "active", actor=beheerder)

    for person in (report, hired, owner, outsider):
        await rates.set_person_scale(
            db, person.id, date(2026, 1, 1), 14, actor=beheerder
        )
    await rates.add_hire(
        db,
        hired.id,
        supplier="Voorbeeld Detachering",
        cost_monthly_rate_cents=1500000,
        valid_from=date(2026, 1, 1),
        actor=beheerder,
    )

    async def _assignment(name: str, owner_person: Person, staffed: Person):
        assignment = await assignments.create_assignment(
            db, name=name, actor=beheerder, owner_id=owner_person.id
        )
        line = await assignments.add_budget_line(
            db,
            assignment.id,
            description="Developer",
            kind="personnel",
            role="Developer",
            fte=Decimal("1"),
            rate_category="D",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            actor=beheerder,
        )
        await assignments.add_allocation(
            db,
            line.id,
            staffed.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            fte_pct=Decimal("100"),
            actor=beheerder,
        )
        return assignment, line

    alfa, alfa_line = await _assignment("Opdracht Alfa", owner, hired)
    beta, beta_line = await _assignment("Opdracht Beta", beheerder, report)
    await db.flush()
    return World(
        beheerder=beheerder,
        planner=planner,
        lezer=lezer,
        lead=lead,
        report=report,
        owner=owner,
        hired=hired,
        outsider=outsider,
        alfa=alfa,
        alfa_line=alfa_line,
        beta=beta,
        beta_line=beta_line,
    )


def by_id(items: list[dict[str, Any]], person: Person) -> dict[str, Any] | None:
    key = "id" if items and "id" in items[0] else "person_id"
    return next((i for i in items if i.get(key) == str(person.id)), None)
