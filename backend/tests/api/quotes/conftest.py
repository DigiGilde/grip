"""Fixtures for the quote, signing, monthly close and billing routes.

All names and amounts are fictional. Category D bills 18,000 per month in
2026 and 18,900 in 2027.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import DEV_PERSON_COOKIE
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.person import Person
from grip.services import assignments, events, rates

RATES = {
    2026: {"A": 900000, "B": 1200000, "C": 1500000, "D": 1800000, "E": 2100000},
    2027: {"A": 950000, "B": 1260000, "C": 1575000, "D": 1890000, "E": 2205000},
}
SCALES = {8: "A", 9: "A", 10: "B", 11: "B", 12: "C", 13: "C", 14: "D", 15: "D"}


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@dataclass
class World:
    beheerder: Person
    manager: Person
    lezer: Person
    planner: Person
    member: Person
    outsider: Person
    signer: Person
    assignment: Assignment
    line: BudgetLine
    allocation: Allocation


@pytest.fixture
async def world(db_session: AsyncSession, create_person) -> World:
    """One assignment with a personnel line, one person on it, and the cast."""
    beheerder = await create_person("beheerder@example.org", functions=["beheerder"])
    manager = await create_person("manager@example.org", name="Opdracht Manager")
    lezer = await create_person(
        "lezer@example.org", name="Lezer Voorbeeld", functions=["lezer"]
    )
    planner = await create_person(
        "planner@example.org", name="Planner Voorbeeld", functions=["planner"]
    )
    member = await create_person("teamlid@example.org", name="Teamlid Voorbeeld")
    outsider = await create_person("buiten@example.org", name="Buitenstaander")
    signer = await create_person(
        "tekenaar@opdrachtgever.example", name="Tekenaar Voorbeeld"
    )

    for year, bands in RATES.items():
        await rates.create_rate_card(db_session, year, actor=beheerder)
        for category, cents in bands.items():
            await rates.set_rate_band(
                db_session, year, category, cents, actor=beheerder
            )
        for scale, category in SCALES.items():
            await rates.set_scale_band(
                db_session, year, scale, category, actor=beheerder
            )
        await rates.set_rate_card_status(db_session, year, "active", actor=beheerder)
    await rates.set_person_scale(
        db_session, member.id, date(2026, 1, 1), 14, actor=beheerder
    )

    client_org = await assignments.upsert_organisation(
        db_session,
        name="Voorbeeldministerie",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
        unit_key="directie-voorbeeld",
    )
    assignment = await assignments.create_assignment(
        db_session,
        name="Opdracht Alfa",
        actor=manager,
        client_organisation_id=client_org.id,
        client_contact="Afdeling Voorbeeld",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    line = await assignments.add_budget_line(
        db_session,
        assignment.id,
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("0.8"),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        actor=manager,
    )
    allocation = await assignments.add_allocation(
        db_session,
        line.id,
        member.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal("80"),
        actor=manager,
    )
    await db_session.flush()
    return World(
        beheerder=beheerder,
        manager=manager,
        lezer=lezer,
        planner=planner,
        member=member,
        outsider=outsider,
        signer=signer,
        assignment=assignment,
        line=line,
        allocation=allocation,
    )


@pytest.fixture
def act_as(client: AsyncClient):
    """Make the next requests run as this person."""

    def _as(person: Person) -> AsyncClient:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return client

    return _as


PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def document_text(response) -> str:
    """The text of a quote document as served: one PDF, shown or downloaded."""
    import io

    from pypdf import PdfReader

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(response.content))
    pages = "\n".join(page.extract_text() for page in reader.pages)
    return pages.replace("\xa0", " ")
