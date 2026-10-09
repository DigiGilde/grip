"""Reads for the costs screen: cost items with forecast, coverage and remainder.

Every amount comes from the calculation module (R6 to R8); this file only
loads the rows and puts names next to them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.models.assignment import Assignment, BudgetLine
from grip.models.cost import CostCoverage, CostItem, InvoiceLine
from grip.models.person import Person
from grip.models.stored_document import StoredDocument
from grip.services import stored_documents
from grip.services.errors import NotFoundError
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    to_calc_cost_item,
    to_calc_coverage,
    to_calc_invoice_line,
)


@dataclass(frozen=True)
class CoverageLine:
    # The coverage record itself and its version, for a save on top of it.
    id: UUID
    version: int
    budget_line_id: UUID
    budget_line_description: str
    assignment_id: UUID
    assignment_name: str
    pct: Decimal
    amount_cents: int


@dataclass(frozen=True)
class CostItemOverview:
    item: CostItem
    invoice_lines: tuple[InvoiceLine, ...]
    # The documents attached per invoice line id, without their content.
    attachments: dict[UUID, tuple[StoredDocument, ...]]
    # Name of whoever uploaded a document, per person id.
    uploader_names: dict[UUID, str]
    coverages: tuple[CoverageLine, ...]
    # R6: actual plus estimate lines (of the year, when a year is given).
    forecast_cents: int
    actual_cents: int
    estimate_cents: int
    # R8. ``None`` when the stored percentages add up to more than 100.
    covered_cents: int | None
    uncovered_cents: int | None
    pct_total: Decimal

    @property
    def variance_cents(self) -> int:
        """Budgeted minus the expected total; negative means over budget."""
        return self.item.budgeted_cents - self.forecast_cents

    @property
    def uncovered_pct(self) -> Decimal | None:
        """The share no budget line covers; ``None`` above 100 percent."""
        if self.pct_total > Decimal(100):
            return None
        return Decimal(100) - self.pct_total

    @property
    def assignment_ids(self) -> frozenset[UUID]:
        return frozenset(c.assignment_id for c in self.coverages)


@dataclass(frozen=True)
class BudgetLineOption:
    budget_line_id: UUID
    description: str
    kind: str
    assignment_id: UUID
    assignment_name: str


async def cost_item_overviews(
    session: AsyncSession,
    *,
    cost_item_id: UUID | None = None,
    year: int | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> list[CostItemOverview]:
    """All cost items, or one, with their lines and derived amounts.

    With a year only invoice lines whose period falls in that year count, in
    the forecast and therefore in the coverage amounts.
    """
    query = select(CostItem).order_by(func.lower(CostItem.description), CostItem.id)
    if cost_item_id is not None:
        query = query.where(CostItem.id == cost_item_id)
    items = list((await session.execute(query)).scalars())
    if cost_item_id is not None and not items:
        raise NotFoundError("Kostenpost", cost_item_id)
    if not items:
        return []
    ids = [item.id for item in items]

    invoices: dict[UUID, list[InvoiceLine]] = defaultdict(list)
    rows = await session.execute(
        select(InvoiceLine)
        .where(InvoiceLine.cost_item_id.in_(ids))
        .order_by(InvoiceLine.period.nulls_last(), InvoiceLine.created_at)
    )
    for line in rows.scalars():
        invoices[line.cost_item_id].append(line)

    coverage_rows = await session.execute(
        select(CostCoverage, BudgetLine, Assignment)
        .join(BudgetLine, BudgetLine.id == CostCoverage.budget_line_id)
        .join(Assignment, Assignment.id == BudgetLine.assignment_id)
        .where(CostCoverage.cost_item_id.in_(ids))
        .order_by(func.lower(Assignment.name), BudgetLine.position)
    )
    coverages: dict[UUID, list[tuple[CostCoverage, BudgetLine, Assignment]]] = (
        defaultdict(list)
    )
    for coverage, line, assignment in coverage_rows:
        coverages[coverage.cost_item_id].append((coverage, line, assignment))

    all_line_ids = [line.id for lines in invoices.values() for line in lines]
    documents = await stored_documents.documents_of(
        session, stored_documents.RECEIVED_INVOICE, all_line_ids
    )
    uploader_ids = {
        d.uploaded_by_id
        for docs in documents.values()
        for d in docs
        if d.uploaded_by_id is not None
    }
    uploader_names: dict[UUID, str] = {}
    if uploader_ids:
        people = await session.execute(
            select(Person.id, Person.name).where(Person.id.in_(uploader_ids))
        )
        uploader_names = {person_id: name for person_id, name in people}

    result: list[CostItemOverview] = []
    for item in items:
        calc_item = to_calc_cost_item(item)
        own_invoices = invoices.get(item.id, [])
        in_scope = [
            line
            for line in own_invoices
            if year is None or (line.period is not None and line.period.year == year)
        ]
        calc_invoices = tuple(to_calc_invoice_line(line) for line in in_scope)
        own_coverages = coverages.get(item.id, [])
        calc_coverages = tuple(to_calc_coverage(c) for c, _l, _a in own_coverages)

        covered: int | None
        uncovered: int | None
        try:
            totals = calc.cost_item_coverage(
                calc_item, calc_invoices, calc_coverages, basis=options.coverage_basis
            )
            covered, uncovered = totals.covered_cents, totals.uncovered_cents
        except calc.CoverageExceededError:
            covered = uncovered = None

        result.append(
            CostItemOverview(
                item=item,
                invoice_lines=tuple(in_scope),
                attachments={
                    line.id: tuple(documents.get(line.id, ())) for line in in_scope
                },
                uploader_names=uploader_names,
                coverages=tuple(
                    CoverageLine(
                        id=coverage.id,
                        version=coverage.version,
                        budget_line_id=line.id,
                        budget_line_description=line.description,
                        assignment_id=assignment.id,
                        assignment_name=assignment.name,
                        pct=coverage.pct,
                        amount_cents=calc.coverage_amount(
                            to_calc_coverage(coverage),
                            calc_item,
                            calc_invoices,
                            basis=options.coverage_basis,
                        ),
                    )
                    for coverage, line, assignment in own_coverages
                ),
                forecast_cents=calc.forecast(calc_item, calc_invoices),
                actual_cents=sum(
                    line.amount_cents for line in in_scope if line.kind == "actual"
                ),
                estimate_cents=sum(
                    line.amount_cents for line in in_scope if line.kind == "estimate"
                ),
                covered_cents=covered,
                uncovered_cents=uncovered,
                pct_total=sum((c.pct for c, _l, _a in own_coverages), Decimal(0)),
            )
        )
    return result


async def budget_line_options(session: AsyncSession) -> list[BudgetLineOption]:
    """Every budget line with its assignment, for choosing what covers a cost."""
    rows = await session.execute(
        select(BudgetLine, Assignment)
        .join(Assignment, Assignment.id == BudgetLine.assignment_id)
        .order_by(func.lower(Assignment.name), BudgetLine.position, BudgetLine.id)
    )
    return [
        BudgetLineOption(
            budget_line_id=line.id,
            description=line.description,
            kind=line.kind,
            assignment_id=assignment.id,
            assignment_name=assignment.name,
        )
        for line, assignment in rows
    ]


async def budget_line_assignment(session: AsyncSession, budget_line_id: UUID) -> UUID:
    """The assignment a budget line belongs to."""
    assignment_id = await session.scalar(
        select(BudgetLine.assignment_id).where(BudgetLine.id == budget_line_id)
    )
    if assignment_id is None:
        raise NotFoundError("Begrotingsregel", budget_line_id)
    return assignment_id
