"""Fixtures for the API tests of the reports.

All names and amounts are fictional. Category D bills 18,000 per month in
2026 and 18,900 in 2027; category C 15,000 and 15,750.

Opdracht Alfa runs from July 2026 to June 2027, so every amount splits over
two rate years. July 2026 is closed with the member at 80 instead of 100
percent. Opdracht Beta is still a draft: its planned inzet is pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from grip.calc import Month
from grip.core.auth import DEV_PERSON_COOKIE
from grip.models.assignment import Allocation, Assignment, BudgetLine
from grip.models.cost import CostItem
from grip.models.month_close import BillingExport
from grip.models.person import Person
from grip.models.quote import Quote
from grip.services import assignments, costs, events, month_close, quotes, rates

RATES = {
    2026: {"A": 900000, "B": 1200000, "C": 1500000, "D": 1800000, "E": 2100000},
    2027: {"A": 950000, "B": 1260000, "C": 1575000, "D": 1890000, "E": 2205000},
}
SCALES = {8: "A", 9: "A", 10: "B", 11: "B", 12: "C", 13: "C", 14: "D", 15: "D"}

# Opdracht Alfa, in cents.
ALFA_BUDGET_2026 = 6 * 1800000 + 6 * 750000
ALFA_BUDGET_2027 = 6 * 1890000 + 6 * 787500
# July 2026 closed: the member at 80 percent, the colleague at 50 percent.
ALFA_REALISED_2026 = 1440000 + 750000
ALFA_FORECAST_2026 = 5 * 1800000 + 5 * 750000
ALFA_FORECAST_2027 = ALFA_BUDGET_2027
ALFA_COVERAGE_2026 = 450000
# Opdracht Beta: one person, the whole of 2026, not agreed yet.
BETA_PIPELINE_2026 = 12 * 1800000


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
    leader: Person
    member: Person
    colleague: Person
    other_person: Person
    outsider: Person
    alfa: Assignment
    beta: Assignment
    line: BudgetLine
    second_line: BudgetLine
    member_allocation: Allocation
    colleague_allocation: Allocation
    quote: Quote
    cost_item: CostItem
    export: BillingExport

    @property
    def staff_names(self) -> list[str]:
        return [self.member.name, self.colleague.name, self.other_person.name]


@pytest.fixture
def as_person(client: AsyncClient):
    """Make the following requests come from this person."""

    def _as(person: Person) -> AsyncClient:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return client

    return _as


@pytest.fixture
async def world(db_session: AsyncSession, create_person) -> World:
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
    leader = await create_person("leiding@example.org", name="Lot Leiding")
    member = await create_person(
        "lid@example.org", name="Mila Medewerker", manager_id=leader.id
    )
    colleague = await create_person(
        "collega@example.org", name="Cas Collega", manager_id=leader.id
    )
    other_person = await create_person("ander@example.org", name="Otto Ander")
    outsider = await create_person("buiten@example.org", name="Bo Buiten")

    for year, bands in RATES.items():
        await rates.create_rate_card(db, year, actor=beheerder)
        for category, cents in bands.items():
            await rates.set_rate_band(db, year, category, cents, actor=beheerder)
        for scale, category in SCALES.items():
            await rates.set_scale_band(db, year, scale, category, actor=beheerder)
        await rates.set_rate_card_status(db, year, "active", actor=beheerder)
    for person, scale in ((member, 14), (colleague, 12), (other_person, 14)):
        await rates.set_person_scale(
            db, person.id, date(2026, 1, 1), scale, actor=beheerder
        )
    await rates.set_billability_target(
        db, member.id, 2026, Decimal("90"), actor=beheerder
    )

    client_org = await assignments.upsert_organisation(db, name="Voorbeeldministerie")
    alfa = await assignments.create_assignment(
        db,
        name="Opdracht Alfa",
        actor=owner,
        client_organisation_id=client_org.id,
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        context_refs=["https://corpus.example/id/node/1"],
    )
    line = await assignments.add_budget_line(
        db,
        alfa.id,
        description="Productmanager",
        kind="personnel",
        role="Productmanager",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        actor=owner,
    )
    second_line = await assignments.add_budget_line(
        db,
        alfa.id,
        description="Developer",
        kind="personnel",
        role="Developer",
        fte=Decimal("0.5"),
        rate_category="C",
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        actor=owner,
    )
    member_allocation = await assignments.add_allocation(
        db,
        line.id,
        member.id,
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        fte_pct=Decimal("100"),
        actor=owner,
    )
    colleague_allocation = await assignments.add_allocation(
        db,
        second_line.id,
        colleague.id,
        start_date=date(2026, 7, 1),
        end_date=date(2027, 6, 30),
        fte_pct=Decimal("50"),
        actor=owner,
    )

    quote = await quotes.issue_quote(db, alfa.id, actor=owner)
    await quotes.accept_quote(
        db,
        quote.id,
        quote_hash=quote.snapshot_hash,
        signer_name="Tekenaar Voorbeeld",
        signer_email="tekenaar@opdrachtgever.example",
        organisation={"name": "Voorbeeldministerie"},
        form="uploaded_pdf",
        document_sha256="0" * 64,
        actor=owner,
    )
    await assignments.transition(db, alfa.id, "in_progress", actor=owner)

    await month_close.close_month(
        db,
        alfa.id,
        Month(2026, 7),
        actor=owner,
        established={
            member_allocation.id: Decimal("80"),
            colleague_allocation.id: Decimal("50"),
        },
    )
    export = await month_close.create_billing_export(
        db, alfa.id, Month(2026, 7), actor=owner
    )

    cost_item = await costs.create_cost_item(
        db, description="Hostingcontract", budgeted_cents=1500000, actor=owner
    )
    await costs.add_invoice_line(
        db,
        cost_item.id,
        kind="actual",
        amount_cents=1500000,
        period=date(2026, 8, 1),
        actor=owner,
    )
    await costs.set_coverage(db, cost_item.id, line.id, Decimal("30"), actor=owner)

    beta = await assignments.create_assignment(
        db,
        name="Opdracht Beta",
        actor=beheerder,
        client_organisation_id=client_org.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    beta_line = await assignments.add_budget_line(
        db,
        beta.id,
        description="Adviseur",
        kind="personnel",
        role="Adviseur",
        fte=Decimal("1"),
        rate_category="D",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        actor=beheerder,
    )
    await assignments.add_allocation(
        db,
        beta_line.id,
        other_person.id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        fte_pct=Decimal("100"),
        actor=beheerder,
    )
    await db.flush()
    return World(
        beheerder=beheerder,
        lezer=lezer,
        planner=planner,
        owner=owner,
        leader=leader,
        member=member,
        colleague=colleague,
        other_person=other_person,
        outsider=outsider,
        alfa=alfa,
        beta=beta,
        line=line,
        second_line=second_line,
        member_allocation=member_allocation,
        colleague_allocation=colleague_allocation,
        quote=quote,
        cost_item=cost_item,
        export=export,
    )
