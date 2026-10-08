"""Fixtures for the domain and service layer tests.

All amounts are fictional. Category D bills 18,000 per month in 2026, as in
the worked examples of the domain description.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from grip.models.organisation import Organisation
from grip.services import assignments, events, rates

RATES_2026 = {"A": 900000, "B": 1200000, "C": 1500000, "D": 1800000, "E": 2100000}
RATES_2027 = {"A": 950000, "B": 1260000, "C": 1575000, "D": 1890000, "E": 2205000}
# Every category covers two scales.
SCALES = {
    8: "A",
    9: "A",
    10: "B",
    11: "B",
    12: "C",
    13: "C",
    14: "D",
    15: "D",
    16: "E",
    17: "E",
}


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@pytest.fixture
async def beheerder(create_person):
    return await create_person("beheerder@example.org", functions=["beheerder"])


async def _make_card(db: AsyncSession, year: int, bands: dict[str, int], actor) -> None:
    await rates.create_rate_card(db, year, actor=actor)
    for category, cents in bands.items():
        await rates.set_rate_band(db, year, category, cents, actor=actor)
    for scale, category in SCALES.items():
        await rates.set_scale_band(db, year, scale, category, actor=actor)
    await rates.set_rate_card_status(db, year, "active", actor=actor)


@pytest.fixture
async def rate_cards(db_session: AsyncSession, beheerder):
    """Active rate cards for 2026 and 2027."""
    await _make_card(db_session, 2026, RATES_2026, beheerder)
    await _make_card(db_session, 2027, RATES_2027, beheerder)


@pytest.fixture
def make_person(db_session: AsyncSession, create_person, beheerder):
    """A person with a billing scale from 2026-01-01 on."""
    counter = {"n": 0}

    async def _make(scale: int = 14, *, valid_from: date = date(2026, 1, 1)):
        counter["n"] += 1
        person = await create_person(
            f"medewerker{counter['n']}@example.org", name=f"Medewerker {counter['n']}"
        )
        await rates.set_person_scale(
            db_session, person.id, valid_from, scale, actor=beheerder
        )
        return person

    return _make


@pytest.fixture
async def client_org(db_session: AsyncSession) -> Organisation:
    return await assignments.upsert_organisation(
        db_session,
        name="Voorbeeldministerie",
        tooi_uri="https://identifier.overheid.nl/tooi/id/ministerie/mnre0000",
        unit_key="directie-voorbeeld",
    )


@pytest.fixture
def make_assignment(db_session: AsyncSession, beheerder, client_org):
    async def _make(name: str = "Opdracht Alfa", **kwargs):
        kwargs.setdefault("client_organisation_id", client_org.id)
        kwargs.setdefault("start_date", date(2026, 1, 1))
        return await assignments.create_assignment(
            db_session, name=name, actor=beheerder, **kwargs
        )

    return _make


@pytest.fixture
def add_personnel_line(db_session: AsyncSession, beheerder):
    async def _add(
        assignment,
        *,
        description: str = "Productmanager",
        fte: str = "0.8",
        category: str = "D",
        start: date = date(2026, 1, 1),
        end: date = date(2026, 12, 31),
        **kwargs,
    ):
        return await assignments.add_budget_line(
            db_session,
            assignment.id,
            description=description,
            kind="personnel",
            role=description,
            fte=Decimal(fte),
            rate_category=category,
            start_date=start,
            end_date=end,
            actor=beheerder,
            **kwargs,
        )

    return _add


@pytest.fixture
def accept(db_session: AsyncSession, beheerder):
    """Move a draft assignment to accepted, so its months can be closed."""

    async def _accept(assignment):
        for step in ("quoted", "accepted"):
            await assignments.transition(
                db_session, assignment.id, step, actor=beheerder
            )
        return assignment

    return _accept
