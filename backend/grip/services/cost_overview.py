"""Reads for the costs screen: cost items with forecast, coverage and remainder.

Every amount comes from the calculation module (R6 to R8); this file only
loads the rows and puts names next to them. A cost item another organisation
keeps is read there (grip.services.cost_references) and counts with what was
read, or not at all.
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
from grip.models.organisation import Organisation
from grip.models.person import Person
from grip.models.stored_document import StoredDocument
from grip.services import cost_references, stored_documents
from grip.services.cost_references import FetchedLine, Reference
from grip.services.errors import NotFoundError
from grip.services.pricing import (
    DEFAULT_OPTIONS,
    PricingOptions,
    calc_costs,
    to_calc_coverage,
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
    # For a cost item another organisation keeps: what it stands for now,
    # and the invoice lines read there (of the year, when a year is given).
    reference: Reference | None = None
    fetched_lines: tuple[FetchedLine, ...] = ()
    # At the executor: the organisation that asked for the cost item.
    requester_name: str | None = None

    @property
    def counts(self) -> bool:
        """The amounts are known: an own item, or one read just now."""
        return self.reference is None or self.reference.counts

    @property
    def incomplete_by(self) -> tuple[str, ...]:
        """The executor, when this reference is spent but cannot be counted."""
        if self.reference is not None and self.reference.unknown:
            return (self.reference.executor_name,)
        return ()

    @property
    def description(self) -> str:
        if self.reference is not None and self.reference.content is not None:
            return self.reference.content.description
        return self.item.description or ""

    @property
    def budgeted_cents(self) -> int | None:
        """For a reference: what its executor has, or else what was asked."""
        if self.reference is not None and self.reference.content is not None:
            return self.reference.content.budgeted_cents
        return self.item.budgeted_cents

    @property
    def variance_cents(self) -> int:
        """Budgeted minus the expected total; negative means over budget."""
        return (self.budgeted_cents or 0) - self.forecast_cents

    @property
    def uncovered_pct(self) -> Decimal | None:
        """The share no budget line covers; ``None`` above 100 percent."""
        if self.pct_total > Decimal(100):
            return None
        return Decimal(100) - self.pct_total

    @property
    def attention_rank(self) -> int:
        """Where the item stands in a list that puts what needs attention
        first: money nobody pays for, then an overrun, then a received
        invoice without its document, then everything else."""
        if not self.counts:
            return 3
        if self.uncovered_cents is None or self.uncovered_cents > 0:
            return 0
        if self.variance_cents < 0:
            return 1
        if any(
            line.kind == "actual" and not self.attachments.get(line.id)
            for line in self.invoice_lines
        ):
            return 2
        return 3

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
    query = select(CostItem)
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

    references = await cost_references.read(session, items)
    requester_ids = {
        item.requester_organisation_id
        for item in items
        if item.requester_organisation_id is not None
    }
    requester_names: dict[UUID, str] = {}
    if requester_ids:
        organisations = await session.execute(
            select(Organisation.id, Organisation.label, Organisation.name).where(
                Organisation.id.in_(requester_ids)
            )
        )
        requester_names = {
            organisation_id: label or name
            for organisation_id, label, name in organisations
        }
    result: list[CostItemOverview] = []
    for item in items:
        own_invoices = invoices.get(item.id, [])
        in_scope = [
            line
            for line in own_invoices
            if year is None or (line.period is not None and line.period.year == year)
        ]
        calc_items, calc_invoices = calc_costs([item], in_scope, references, year=year)
        calc_item = calc_items[0]
        reference = references.get(item.id)
        fetched = tuple(
            line
            for line in (
                reference.content.lines
                if reference is not None and reference.content is not None
                else ()
            )
            if year is None or (line.period is not None and line.period.year == year)
        )
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
                    line.amount_cents
                    for line in calc_invoices
                    if line.kind.value == "actual"
                ),
                estimate_cents=sum(
                    line.amount_cents
                    for line in calc_invoices
                    if line.kind.value == "estimate"
                ),
                covered_cents=covered,
                uncovered_cents=uncovered,
                pct_total=sum((c.pct for c, _l, _a in own_coverages), Decimal(0)),
                reference=reference,
                fetched_lines=fetched,
                requester_name=requester_names.get(item.requester_organisation_id)
                if item.requester_organisation_id is not None
                else None,
            )
        )
    result.sort(
        key=lambda overview: (overview.description.casefold(), overview.item.id)
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
