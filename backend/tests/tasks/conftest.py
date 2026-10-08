"""Fixtures for the task tests.

The world is built from rows, not through the services: the engine reads
facts from the domain tables, and a test of the engine should say exactly
which facts hold. All names and amounts are fictional.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from grip.core.auth import DEV_PERSON_COOKIE
from grip.models.assignment import Allocation, Assignment, AssignmentRole, BudgetLine
from grip.models.audit_log import AuditLog
from grip.models.month_close import MonthClose
from grip.models.organisation import Organisation
from grip.models.outgoing_invoice import OutgoingInvoice, OutgoingInvoiceDelivery
from grip.models.person import Person
from grip.models.quote import Quote, QuoteOffer
from grip.models.vacancy import Vacancy, VacancyDecision
from grip.models.vacancy_hire import VacancyHire
from grip.services import events
from grip.tasks import engine

INSTANCE = "http://localhost:8010"
TODAY = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _no_event_handlers():
    events.clear_handlers()
    yield
    events.clear_handlers()


@pytest.fixture
def as_person(client: AsyncClient):
    def _as(person: Person) -> AsyncClient:
        client.cookies.set(DEV_PERSON_COOKIE, str(person.id))
        return client

    return _as


class Builder:
    """Write the rows a fact is read from."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def assignment(
        self,
        name: str = "Opdracht Alfa 2026",
        *,
        status: str = "draft",
        kind: str = "external",
        owner: Person | None = None,
        managers: tuple[Person, ...] = (),
        client: Organisation | None = None,
        start: date | None = date(2026, 1, 1),
        end: date | None = date(2026, 12, 31),
    ) -> Assignment:
        assignment = Assignment(
            uri=f"{INSTANCE}/id/opdracht/{uuid.uuid4()}",
            name=name,
            kind=kind,
            status=status,
            client_organisation_id=client.id if client else None,
            start_date=start,
            end_date=end,
        )
        self.db.add(assignment)
        await self.db.flush()
        if owner is not None:
            self.db.add(
                AssignmentRole(
                    assignment_id=assignment.id, person_id=owner.id, role="owner"
                )
            )
        for manager in managers:
            self.db.add(
                AssignmentRole(
                    assignment_id=assignment.id, person_id=manager.id, role="manager"
                )
            )
        await self.db.flush()
        return assignment

    async def organisation(self, name: str, *, instance_uri: str | None = None):
        organisation = Organisation(name=name, instance_uri=instance_uri)
        self.db.add(organisation)
        await self.db.flush()
        return organisation

    async def line(
        self,
        assignment: Assignment,
        role: str = "Developer",
        *,
        fte: str = "1",
        start: date | None = None,
        end: date | None = None,
    ) -> BudgetLine:
        line = BudgetLine(
            assignment_id=assignment.id,
            kind="personnel",
            role=role,
            fte=Decimal(fte),
            rate_category="C",
            period_source="own",
            start_date=start or assignment.start_date,
            end_date=end or assignment.end_date,
        )
        self.db.add(line)
        await self.db.flush()
        return line

    async def allocation(
        self,
        line: BudgetLine,
        person: Person,
        *,
        pct: str = "100",
        start: date | None = None,
        end: date | None = None,
    ) -> Allocation:
        allocation = Allocation(
            budget_line_id=line.id,
            person_id=person.id,
            period_source="own",
            start_date=start or line.start_date,
            end_date=end or line.end_date,
            fte_pct=Decimal(pct),
        )
        self.db.add(allocation)
        await self.db.flush()
        return allocation

    async def quote(
        self,
        assignment: Assignment,
        *,
        status: str = "issued",
        issued_at: datetime = NOW,
        offered: bool = False,
    ) -> Quote:
        canonical = f'{{"id":"{uuid.uuid4()}"}}'.encode()
        quote = Quote(
            uri=f"{INSTANCE}/id/offerte/{uuid.uuid4()}",
            assignment_id=assignment.id,
            status=status,
            canonical=canonical,
            snapshot_hash=hashlib.sha256(canonical).hexdigest(),
            total_cents=1000000,
            issued_at=issued_at,
        )
        for name, value in _quote_extras().items():
            setattr(quote, name, value)
        self.db.add(quote)
        await self.db.flush()
        if offered:
            await self.offer(quote)
        return quote

    async def offer(self, quote: Quote) -> QuoteOffer:
        offer = QuoteOffer(quote_id=quote.id, channel="document", offered_at=NOW)
        self.db.add(offer)
        await self.db.flush()
        return offer

    async def close(self, assignment: Assignment, month: date) -> MonthClose:
        close = MonthClose(assignment_id=assignment.id, month=month, closed_at=NOW)
        self.db.add(close)
        await self.db.flush()
        return close

    async def export(self, close: MonthClose) -> SimpleNamespace:
        # Written as a row with only the columns every version of the table
        # has, so this fixture does not follow each change to the export.
        export_id = uuid.uuid4()
        await self.db.execute(
            text(
                "INSERT INTO billing_export"
                " (id, assignment_id, month, month_close_id, total_cents)"
                " VALUES (:id, :assignment_id, :month, :close_id, 100000)"
            ),
            {
                "id": export_id,
                "assignment_id": close.assignment_id,
                "month": close.month,
                "close_id": close.id,
            },
        )
        return SimpleNamespace(id=export_id, assignment_id=close.assignment_id)

    async def invoice(self, export: SimpleNamespace) -> OutgoingInvoice:
        invoice = OutgoingInvoice(
            assignment_id=export.assignment_id,
            invoice_number="F-2026-001",
            invoice_date=TODAY,
            amount_cents=100000,
            source="manual",
        )
        self.db.add(invoice)
        await self.db.flush()
        self.db.add(
            OutgoingInvoiceDelivery(
                outgoing_invoice_id=invoice.id, billing_export_id=export.id
            )
        )
        await self.db.flush()
        return invoice

    async def final_report(self, assignment: Assignment) -> None:
        self.db.add(
            AuditLog(
                action="create",
                entity="final_report",
                entity_id=str(assignment.id),
                new_value={},
            )
        )
        await self.db.flush()

    async def vacancy(
        self,
        *,
        status: str = "draft",
        vacancy_type: str = "regulier",
        requester: Person | None = None,
        line: BudgetLine | None = None,
        title: str = "Developer",
    ) -> Vacancy:
        vacancy = Vacancy(
            budget_line_id=line.id if line else None,
            function_title=title,
            fte=Decimal("1"),
            declarable=line is not None,
            vacancy_type=vacancy_type,
            status=status,
            requester_id=requester.id if requester else None,
            requested_on=date(2026, 10, 1) if status != "draft" else None,
        )
        self.db.add(vacancy)
        await self.db.flush()
        return vacancy

    async def decision(
        self,
        vacancy: Vacancy,
        kind: str,
        *,
        person: Person | None = None,
        agreed: bool | None = None,
    ) -> VacancyDecision:
        decision = VacancyDecision(
            vacancy_id=vacancy.id,
            kind=kind,
            person_id=person.id if person else None,
            person_name=person.name if person else "Iemand zonder account",
            agreed=agreed,
            decided_at=NOW if agreed is not None else None,
        )
        self.db.add(decision)
        await self.db.flush()
        await self.db.refresh(vacancy, ["decisions"])
        return decision

    async def hire(self, vacancy: Vacancy, person: Person) -> VacancyHire:
        hire = VacancyHire(
            vacancy_id=vacancy.id, person_id=person.id, start_date=date(2026, 11, 1)
        )
        self.db.add(hire)
        vacancy.status = "filled"
        await self.db.flush()
        return hire


def _quote_extras() -> dict[str, Any]:
    """Columns other work added to a quote and that have no default."""
    extras: dict[str, Any] = {}
    if "reference" in Quote.__table__.columns:
        extras["reference"] = f"T-2026-{uuid.uuid4().hex[:6]}"
    return extras


@pytest.fixture
def build(db_session: AsyncSession) -> Builder:
    return Builder(db_session)


@pytest.fixture
def evaluate(db_session: AsyncSession):
    """Run the engine for everything, on the day of the test."""

    async def _evaluate(today: date = TODAY, now: datetime = NOW) -> engine.Outcome:
        return await engine.evaluate_all(
            db_session, today=today, instance_base_uri=INSTANCE, now=now
        )

    return _evaluate
