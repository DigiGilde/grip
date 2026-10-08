"""Queries for the domain tables. No business rules here."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from grip.models.assignment import Allocation, Assignment, AssignmentRole, BudgetLine
from grip.models.cost import CostCoverage, CostItem, InvoiceLine
from grip.models.month_close import MonthClose, MonthCloseLine
from grip.models.person_details import BillabilityTarget, Hire, PersonScale
from grip.models.quote import Quote, QuoteAcceptance, QuoteInvitation
from grip.models.rates import RateCard


class RateRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_card(self, year: int) -> RateCard | None:
        result = await self.db.execute(
            select(RateCard)
            .where(RateCard.year == year)
            .options(
                selectinload(RateCard.rate_bands), selectinload(RateCard.scale_bands)
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def all_cards(self) -> list[RateCard]:
        result = await self.db.execute(
            select(RateCard)
            .options(
                selectinload(RateCard.rate_bands), selectinload(RateCard.scale_bands)
            )
            .order_by(RateCard.year)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars())

    async def closed_years(self, years: Iterable[int]) -> list[int]:
        years = sorted(set(years))
        if not years:
            return []
        result = await self.db.execute(
            select(RateCard.year)
            .where(RateCard.year.in_(years), RateCard.status == "closed")
            .order_by(RateCard.year)
        )
        return list(result.scalars())


class PersonDetailRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def scales(
        self, person_ids: Iterable[UUID] | None = None
    ) -> list[PersonScale]:
        stmt = select(PersonScale).order_by(
            PersonScale.person_id, PersonScale.valid_from
        )
        if person_ids is not None:
            ids = list(set(person_ids))
            if not ids:
                return []
            stmt = stmt.where(PersonScale.person_id.in_(ids))
        return list((await self.db.execute(stmt)).scalars())

    async def target(self, person_id: UUID, year: int) -> BillabilityTarget | None:
        result = await self.db.execute(
            select(BillabilityTarget).where(
                BillabilityTarget.person_id == person_id,
                BillabilityTarget.year == year,
            )
        )
        return result.scalar_one_or_none()

    async def hires(self, person_id: UUID) -> list[Hire]:
        result = await self.db.execute(
            select(Hire).where(Hire.person_id == person_id).order_by(Hire.valid_from)
        )
        return list(result.scalars())


class AssignmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, assignment_id: UUID) -> Assignment | None:
        return await self.db.get(Assignment, assignment_id)

    async def get_by_uri(self, uri: str) -> Assignment | None:
        result = await self.db.execute(select(Assignment).where(Assignment.uri == uri))
        return result.scalar_one_or_none()

    async def list(
        self, *, status: str | None = None, node_uri: str | None = None
    ) -> list[Assignment]:
        stmt = select(Assignment).order_by(Assignment.name)
        if status is not None:
            stmt = stmt.where(Assignment.status == status)
        if node_uri is not None:
            stmt = stmt.where(Assignment.context_refs.contains([node_uri]))
        return list((await self.db.execute(stmt)).scalars())

    async def roles(self, assignment_id: UUID) -> list[AssignmentRole]:
        result = await self.db.execute(
            select(AssignmentRole).where(AssignmentRole.assignment_id == assignment_id)
        )
        return list(result.scalars())

    async def budget_lines(self, assignment_ids: Iterable[UUID]) -> list[BudgetLine]:
        ids = list(set(assignment_ids))
        if not ids:
            return []
        result = await self.db.execute(
            select(BudgetLine)
            .where(BudgetLine.assignment_id.in_(ids))
            .order_by(BudgetLine.assignment_id, BudgetLine.position)
        )
        return list(result.scalars())

    async def budget_lines_by_id(self, line_ids: Iterable[UUID]) -> list[BudgetLine]:
        ids = list(set(line_ids))
        if not ids:
            return []
        result = await self.db.execute(select(BudgetLine).where(BudgetLine.id.in_(ids)))
        return list(result.scalars())

    async def allocations_on_lines(self, line_ids: Iterable[UUID]) -> list[Allocation]:
        ids = list(set(line_ids))
        if not ids:
            return []
        result = await self.db.execute(
            select(Allocation)
            .where(Allocation.budget_line_id.in_(ids))
            .order_by(Allocation.start_date, Allocation.id)
        )
        return list(result.scalars())

    async def allocations_of_person(self, person_id: UUID) -> list[Allocation]:
        result = await self.db.execute(
            select(Allocation)
            .where(Allocation.person_id == person_id)
            .order_by(Allocation.start_date, Allocation.id)
        )
        return list(result.scalars())


class CostRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def coverages_on_lines(self, line_ids: Iterable[UUID]) -> list[CostCoverage]:
        ids = list(set(line_ids))
        if not ids:
            return []
        result = await self.db.execute(
            select(CostCoverage).where(CostCoverage.budget_line_id.in_(ids))
        )
        return list(result.scalars())

    async def coverages_of_item(self, cost_item_id: UUID) -> list[CostCoverage]:
        result = await self.db.execute(
            select(CostCoverage).where(CostCoverage.cost_item_id == cost_item_id)
        )
        return list(result.scalars())

    async def items(self, item_ids: Iterable[UUID]) -> list[CostItem]:
        ids = list(set(item_ids))
        if not ids:
            return []
        result = await self.db.execute(select(CostItem).where(CostItem.id.in_(ids)))
        return list(result.scalars())

    async def invoice_lines(self, item_ids: Iterable[UUID]) -> list[InvoiceLine]:
        ids = list(set(item_ids))
        if not ids:
            return []
        result = await self.db.execute(
            select(InvoiceLine).where(InvoiceLine.cost_item_id.in_(ids))
        )
        return list(result.scalars())


class MonthCloseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def in_force(self, assignment_id: UUID, month: date) -> MonthClose | None:
        result = await self.db.execute(
            select(MonthClose)
            .where(
                MonthClose.assignment_id == assignment_id,
                MonthClose.month == month,
                MonthClose.reopened_at.is_(None),
            )
            .options(selectinload(MonthClose.lines))
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def closed_months(self, assignment_id: UUID) -> list[date]:
        result = await self.db.execute(
            select(MonthClose.month)
            .where(
                MonthClose.assignment_id == assignment_id,
                MonthClose.reopened_at.is_(None),
            )
            .order_by(MonthClose.month)
        )
        return list(result.scalars())

    async def established(
        self, allocation_ids: Iterable[UUID]
    ) -> list[tuple[UUID, date, object]]:
        """(allocation id, month, established percentage) of closes in force."""
        ids = list(set(allocation_ids))
        if not ids:
            return []
        result = await self.db.execute(
            select(
                MonthCloseLine.allocation_id,
                MonthClose.month,
                MonthCloseLine.established_fte_pct,
            )
            .join(MonthClose, MonthClose.id == MonthCloseLine.month_close_id)
            .where(
                MonthCloseLine.allocation_id.in_(ids),
                MonthClose.reopened_at.is_(None),
            )
        )
        return [tuple(row) for row in result.all()]


class QuoteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, quote_id: UUID) -> Quote | None:
        return await self.db.get(Quote, quote_id)

    async def of_assignment(self, assignment_id: UUID) -> list[Quote]:
        result = await self.db.execute(
            select(Quote)
            .where(Quote.assignment_id == assignment_id)
            .order_by(Quote.issued_at)
        )
        return list(result.scalars())

    async def acceptance(self, quote_id: UUID) -> QuoteAcceptance | None:
        result = await self.db.execute(
            select(QuoteAcceptance).where(QuoteAcceptance.quote_id == quote_id)
        )
        return result.scalar_one_or_none()

    async def invitations(self, quote_id: UUID) -> list[QuoteInvitation]:
        result = await self.db.execute(
            select(QuoteInvitation).where(QuoteInvitation.quote_id == quote_id)
        )
        return list(result.scalars())
