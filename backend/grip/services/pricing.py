"""Pricing bridge: database rows in, calculation module out.

This module loads what the rules need and calls ``grip.calc``. It implements
no rule itself. Where an overview needs a split or a year filter, it sums the
per-month amounts the calculation module returns.

Closed months count with the established inzet of the monthly close; open
months count with the planned inzet (docs/domein.md, Maandafsluiting).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from grip import calc
from grip.calc import AmountSource, CoverageBasis, Month, PartialMonths
from grip.models.assignment import Allocation, BudgetLine
from grip.models.cost import CostCoverage, CostItem, InvoiceLine
from grip.models.person_details import BillabilityTarget, PersonScale
from grip.models.rates import RateCard
from grip.repositories.domain import (
    AssignmentRepository,
    CostRepository,
    MonthCloseRepository,
    PersonDetailRepository,
    RateRepository,
)
from grip.services import read_cache
from grip.services.errors import NotFoundError
from grip.services.quote_content import QuoteLineSource


@dataclass(frozen=True)
class PricingOptions:
    """Choices the Grist formulas still have to confirm (docs/domein.md).

    One instance is passed down, so a change of default happens in one place.
    """

    partial_months: PartialMonths = PartialMonths.CALENDAR_DAYS
    coverage_basis: CoverageBasis = CoverageBasis.FORECAST
    # Price months of a draft rate card too, for budgeting a year ahead.
    include_draft: bool = False


DEFAULT_OPTIONS = PricingOptions()


@dataclass(frozen=True)
class CalcInputs:
    """Everything the calculation module needs for a set of budget lines."""

    rates: calc.RateBook
    scales: tuple[calc.PersonScale, ...]
    lines: tuple[calc.BudgetLine, ...]
    allocations: tuple[calc.Allocation, ...]
    cost_items: tuple[calc.CostItem, ...]
    invoice_lines: tuple[calc.InvoiceLine, ...]
    coverages: tuple[calc.CostCoverage, ...]
    # Established FTE percentage per (allocation id, month) of closed months.
    actuals: dict[tuple[str, Month], Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class LineOverview:
    budget_line_id: UUID
    budgeted_cents: int
    # Inzet of closed months, at the established percentage.
    realised_cents: int
    # Inzet of open months, at the planned percentage.
    forecast_cents: int
    # Coverage of cost items put on this line.
    coverage_cents: int

    @property
    def used_cents(self) -> int:
        return self.realised_cents + self.forecast_cents + self.coverage_cents

    @property
    def available_cents(self) -> int:
        return self.budgeted_cents - self.used_cents

    @property
    def overrun(self) -> bool:
        return self.available_cents < 0


@dataclass(frozen=True)
class AssignmentOverview:
    assignment_id: UUID
    # None means the whole period.
    year: int | None
    lines: tuple[LineOverview, ...]

    @property
    def budgeted_cents(self) -> int:
        return sum(line.budgeted_cents for line in self.lines)

    @property
    def realised_cents(self) -> int:
        return sum(line.realised_cents for line in self.lines)

    @property
    def forecast_cents(self) -> int:
        return sum(line.forecast_cents for line in self.lines)

    @property
    def coverage_cents(self) -> int:
        return sum(line.coverage_cents for line in self.lines)

    @property
    def used_cents(self) -> int:
        return sum(line.used_cents for line in self.lines)

    @property
    def available_cents(self) -> int:
        return self.budgeted_cents - self.used_cents

    @property
    def overrun(self) -> bool:
        return self.available_cents < 0


@dataclass(frozen=True)
class KpiOverview:
    person_id: UUID
    year: int
    realised_cents: int
    forecast_cents: int
    # None when the person has no target for the year.
    target_cents: int | None
    target_pct: Decimal | None

    @property
    def realisation_cents(self) -> int:
        return self.realised_cents + self.forecast_cents


# -- conversion ---------------------------------------------------------------


def to_calc_rate_card(card: RateCard) -> calc.RateCard:
    return calc.RateCard(
        id=str(card.id),
        name=card.name,
        valid_from=card.valid_from,
        valid_to=card.valid_to,
        status=calc.RateCardStatus(card.status),
        rate_bands=tuple(
            calc.RateBand(category=b.category, monthly_rate_cents=b.monthly_rate_cents)
            for b in card.rate_bands
        ),
        scale_bands=tuple(
            calc.ScaleBand(scale=b.scale, category=b.category) for b in card.scale_bands
        ),
    )


def to_calc_scale(scale: PersonScale) -> calc.PersonScale:
    return calc.PersonScale(
        person_id=str(scale.person_id),
        valid_from=scale.valid_from,
        valid_to=scale.valid_to,
        billing_scale=scale.billing_scale,
    )


# Raised by the calculation module for a line that waits for the period of
# its assignment; re-exported here for the callers of this module.
MissingPeriodError = calc.MissingPeriodError


def to_calc_line(line: BudgetLine | QuoteLineSource) -> calc.BudgetLine:
    return calc.BudgetLine(
        id=str(line.id),
        assignment_id=str(line.assignment_id),
        kind=calc.BudgetLineKind(line.kind),
        fte=line.fte,
        rate_category=line.rate_category,
        start_date=line.start_date,
        end_date=line.end_date,
        amount_cents=line.amount_cents,
        year=line.year,
    )


def to_calc_allocation(allocation: Allocation) -> calc.Allocation:
    return calc.Allocation(
        id=str(allocation.id),
        person_id=str(allocation.person_id),
        budget_line_id=str(allocation.budget_line_id),
        start_date=allocation.start_date,
        end_date=allocation.end_date,
        fte_pct=allocation.fte_pct,
    )


def to_calc_cost_item(item: CostItem) -> calc.CostItem:
    return calc.CostItem(id=str(item.id), budgeted_cents=item.budgeted_cents)


def to_calc_invoice_line(line: InvoiceLine) -> calc.InvoiceLine:
    return calc.InvoiceLine(
        id=str(line.id),
        cost_item_id=str(line.cost_item_id),
        kind=calc.InvoiceLineKind(line.kind),
        amount_cents=line.amount_cents,
        period=line.period,
    )


def to_calc_coverage(coverage: CostCoverage) -> calc.CostCoverage:
    return calc.CostCoverage(
        id=str(coverage.id),
        cost_item_id=str(coverage.cost_item_id),
        budget_line_id=str(coverage.budget_line_id),
        pct=coverage.pct,
    )


# -- loading ------------------------------------------------------------------


async def load_rate_book(
    session: AsyncSession, *, include_draft: bool = False
) -> calc.RateBook:
    cards = await RateRepository(session).all_cards()
    return calc.RateBook(
        cards=tuple(to_calc_rate_card(card) for card in cards),
        include_draft=include_draft,
    )


async def _load_actuals(
    session: AsyncSession, allocation_ids: Iterable[UUID]
) -> dict[tuple[str, Month], Decimal]:
    rows = await MonthCloseRepository(session).established(allocation_ids)
    return {
        (str(allocation_id), Month.of(month)): pct for allocation_id, month, pct in rows
    }


async def load_inputs_for_lines(
    session: AsyncSession,
    lines: Iterable[BudgetLine],
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> CalcInputs:
    """Load allocations, costs, scales and closed months for budget lines."""
    lines = list(lines)
    line_ids = [line.id for line in lines]
    assignments = AssignmentRepository(session)
    costs = CostRepository(session)

    allocations = await assignments.allocations_on_lines(line_ids)
    coverages = await costs.coverages_on_lines(line_ids)
    item_ids = {c.cost_item_id for c in coverages}
    cost_items = await costs.items(item_ids)
    invoice_lines = await costs.invoice_lines(item_ids)
    scales = await PersonDetailRepository(session).scales(
        {a.person_id for a in allocations}
    )
    return CalcInputs(
        rates=await load_rate_book(session, include_draft=options.include_draft),
        scales=tuple(to_calc_scale(s) for s in scales),
        lines=tuple(to_calc_line(line) for line in lines),
        allocations=tuple(to_calc_allocation(a) for a in allocations),
        cost_items=tuple(to_calc_cost_item(i) for i in cost_items),
        invoice_lines=tuple(to_calc_invoice_line(i) for i in invoice_lines),
        coverages=tuple(to_calc_coverage(c) for c in coverages),
        actuals=await _load_actuals(session, [a.id for a in allocations]),
    )


def split_by_assignment(inputs: CalcInputs) -> dict[str, CalcInputs]:
    """The inputs of several assignments, taken apart per assignment.

    Each part holds what ``load_inputs_for_lines`` gives for the lines of
    that one assignment, in the same order. The rate book is shared.
    """
    assignment_of_line = {line.id: line.assignment_id for line in inputs.lines}
    lines: dict[str, list[calc.BudgetLine]] = {}
    for line in inputs.lines:
        lines.setdefault(line.assignment_id, []).append(line)
    allocations: dict[str, list[calc.Allocation]] = {}
    for allocation in inputs.allocations:
        allocations.setdefault(
            assignment_of_line[allocation.budget_line_id], []
        ).append(allocation)
    coverages: dict[str, list[calc.CostCoverage]] = {}
    for coverage in inputs.coverages:
        coverages.setdefault(assignment_of_line[coverage.budget_line_id], []).append(
            coverage
        )
    assignment_of_allocation = {
        allocation.id: assignment_id
        for assignment_id, own in allocations.items()
        for allocation in own
    }
    actuals: dict[str, dict[tuple[str, Month], Decimal]] = {}
    for key, pct in inputs.actuals.items():
        actuals.setdefault(assignment_of_allocation[key[0]], {})[key] = pct

    parts: dict[str, CalcInputs] = {}
    for assignment_id, own_lines in lines.items():
        own_allocations = allocations.get(assignment_id, [])
        own_coverages = coverages.get(assignment_id, [])
        item_ids = {coverage.cost_item_id for coverage in own_coverages}
        person_ids = {allocation.person_id for allocation in own_allocations}
        parts[assignment_id] = CalcInputs(
            rates=inputs.rates,
            scales=tuple(s for s in inputs.scales if s.person_id in person_ids),
            lines=tuple(own_lines),
            allocations=tuple(own_allocations),
            cost_items=tuple(i for i in inputs.cost_items if i.id in item_ids),
            invoice_lines=tuple(
                i for i in inputs.invoice_lines if i.cost_item_id in item_ids
            ),
            coverages=tuple(own_coverages),
            actuals=actuals.get(assignment_id, {}),
        )
    return parts


def no_inputs(rates: calc.RateBook) -> CalcInputs:
    """The inputs of an assignment without budget lines."""
    return CalcInputs(
        rates=rates,
        scales=(),
        lines=(),
        allocations=(),
        cost_items=(),
        invoice_lines=(),
        coverages=(),
    )


async def load_inputs_by_assignment(
    session: AsyncSession,
    assignment_ids: Iterable[UUID],
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
    lines: Iterable[BudgetLine] | None = None,
) -> dict[UUID, CalcInputs]:
    """The inputs of several assignments, read together and given per assignment.

    ``lines`` are the budget lines of those assignments when the caller
    already has them.
    """
    ids = list(dict.fromkeys(assignment_ids))
    if lines is None:
        lines = await AssignmentRepository(session).budget_lines(ids)
    inputs = await load_inputs_for_lines(session, lines, options=options)
    parts = split_by_assignment(inputs)
    return {i: parts.get(str(i)) or no_inputs(inputs.rates) for i in ids}


async def load_inputs_for_assignment(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> CalcInputs:
    repo = AssignmentRepository(session)
    if await repo.get(assignment_id) is None:
        raise NotFoundError("Opdracht", assignment_id)
    lines = await repo.budget_lines([assignment_id])
    return await load_inputs_for_lines(session, lines, options=options)


# -- overviews ----------------------------------------------------------------


def _line_overview(
    line: calc.BudgetLine,
    inputs: CalcInputs,
    options: PricingOptions,
    year: int | None,
) -> LineOverview:
    realised = 0
    forecast = 0
    for allocation in inputs.allocations:
        if allocation.budget_line_id != line.id:
            continue
        for amount in calc.allocation_months(
            allocation,
            inputs.rates,
            inputs.scales,
            partial_months=options.partial_months,
            actuals=inputs.actuals,
        ):
            if year is not None and amount.month.year != year:
                continue
            if amount.source is AmountSource.ACTUAL:
                realised += amount.cents
            else:
                forecast += amount.cents

    items = {item.id: item for item in inputs.cost_items}
    coverage = 0
    for cov in inputs.coverages:
        if cov.budget_line_id != line.id:
            continue
        invoice_lines = inputs.invoice_lines
        if year is not None and options.coverage_basis is CoverageBasis.FORECAST:
            # A coverage amount follows the forecast of its cost item, so with
            # a year filter it follows the invoice lines of that year.
            invoice_lines = tuple(
                i
                for i in inputs.invoice_lines
                if i.period is not None and i.period.year == year
            )
        coverage += calc.coverage_amount(
            cov,
            items[cov.cost_item_id],
            invoice_lines,
            basis=options.coverage_basis,
        )

    return LineOverview(
        budget_line_id=UUID(line.id),
        budgeted_cents=calc.budgeted(
            line, inputs.rates, partial_months=options.partial_months, year=year
        ),
        realised_cents=realised,
        forecast_cents=forecast,
        coverage_cents=coverage,
    )


def overview_from_inputs(
    assignment_id: UUID,
    inputs: CalcInputs,
    *,
    year: int | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> AssignmentOverview:
    return AssignmentOverview(
        assignment_id=assignment_id,
        year=year,
        lines=tuple(
            _line_overview(line, inputs, options, year)
            for line in inputs.lines
            if line.assignment_id == str(assignment_id)
        ),
    )


async def assignment_overview(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    year: int | None = None,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> AssignmentOverview:
    """Budgeted, used and available of an assignment, per budget line.

    ``year=None`` covers the whole period. With a year, budgeted and inzet
    are the amounts of the months in that year; coverage follows the invoice
    lines of that year (forecast basis) or counts in full (budgeted basis).
    """
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    return overview_from_inputs(assignment_id, inputs, year=year, options=options)


async def assignment_totals(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> calc.AssignmentTotals:
    """R11 straight from the calculation module, for the whole period."""
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    return calc.assignment_totals(
        str(assignment_id),
        inputs.lines,
        allocations=inputs.allocations,
        coverages=inputs.coverages,
        cost_items=inputs.cost_items,
        invoice_lines=inputs.invoice_lines,
        rates=inputs.rates,
        scales=inputs.scales,
        partial_months=options.partial_months,
        coverage_basis=options.coverage_basis,
        actuals=inputs.actuals,
    )


async def budgeted_by_year(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> dict[int, int]:
    """Subtotal of the budget per calendar year, for the quote and the filter."""
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    totals: dict[int, int] = {}
    for line in inputs.lines:
        for year, cents in calc.budgeted_by_year(
            line, inputs.rates, partial_months=options.partial_months
        ).items():
            totals[year] = totals.get(year, 0) + cents
    return dict(sorted(totals.items()))


async def category_signals(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> tuple[calc.CategoryMismatch, ...]:
    """R14: people who bill in another category than their budget line assumes.

    The result names categories (class D). A caller that serves a planner must
    reduce it to the fact that a mismatch exists.
    """
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    signals: list[calc.CategoryMismatch] = []
    for line in inputs.lines:
        signals.extend(
            calc.category_mismatches(
                line, inputs.allocations, inputs.rates, inputs.scales
            )
        )
    return tuple(signals)


_MONTH_NAMES = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)

CAUSE_PROMOTION = "promotion"
CAUSE_SCALE_CHANGE = "scale_change"
CAUSE_RATE_CARD = "rate_card"
CAUSE_OTHER = "other"


@dataclass(frozen=True)
class RateDifference:
    """Why a budget line runs over or under: the R14 signal with its cause.

    A line is budgeted at one category. The person on it bills at the
    correct rate, whatever was budgeted or quoted; when that is another
    category the line runs over or under from a date. Grip shows that and
    names the cause; it does not block anything.
    """

    budget_line_id: UUID
    allocation_id: UUID
    person_id: UUID
    since: date
    line_category: str
    person_category: str
    direction: str
    cause: str
    # Names the categories: for who may see what a person bills (class D).
    text: str
    # Without the person and the categories: for who may see only that
    # something differs.
    generic_text: str


def _day_text(day: date) -> str:
    return f"{day.day} {_MONTH_NAMES[day.month - 1]} {day.year}"


def describe_rate_difference(
    mismatch: calc.CategoryMismatch,
    scales: Iterable[calc.PersonScale],
    rates: calc.RateBook,
) -> RateDifference:
    since = mismatch.since or mismatch.first_month.first_day
    own = sorted(
        (s for s in scales if s.person_id == mismatch.person_id),
        key=lambda s: s.valid_from,
    )
    new = next((s for s in own if s.valid_from == since), None)
    old = next(
        (
            s
            for s in own
            if s.valid_from < since
            and (s.valid_to or date.max) >= since - timedelta(days=1)
        ),
        None,
    )
    tail = (
        f"vanaf dan categorie {mismatch.person_category}, de regel is begroot op "
        f"{mismatch.line_category}"
    )
    when = _day_text(since)
    if new is not None and old is not None and new.billing_scale > old.billing_scale:
        cause, text = CAUSE_PROMOTION, f"gepromoveerd per {when}: {tail}"
    elif new is not None and old is not None:
        cause, text = CAUSE_SCALE_CHANGE, f"inzetschaal gewijzigd per {when}: {tail}"
    elif any(card.valid_from == since for card in rates.cards):
        cause = CAUSE_RATE_CARD
        text = (
            f"nieuwe tarievenkaart per {when}: de schaal valt vanaf dan in "
            f"categorie {mismatch.person_category}, de regel is begroot op "
            f"{mismatch.line_category}"
        )
    else:
        cause = CAUSE_OTHER
        text = (
            f"declareert in categorie {mismatch.person_category}; de regel is "
            f"begroot op {mismatch.line_category}"
        )
    generic = (
        "tarief wijkt af van de begroting"
        if cause == CAUSE_OTHER
        else f"tariefwijziging per {when}"
    )
    return RateDifference(
        budget_line_id=UUID(mismatch.budget_line_id),
        allocation_id=UUID(mismatch.allocation_id),
        person_id=UUID(mismatch.person_id),
        since=since,
        line_category=mismatch.line_category,
        person_category=mismatch.person_category,
        direction=mismatch.direction.value,
        cause=cause,
        text=text,
        generic_text=generic,
    )


async def rate_differences(
    session: AsyncSession,
    assignment_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> tuple[RateDifference, ...]:
    """Per budget line of an assignment why it runs over or under (R14),
    with the cause named: a promotion from a date, a new rate card, or a
    person who bills in another category than was budgeted."""
    inputs = await load_inputs_for_assignment(session, assignment_id, options=options)
    found: list[RateDifference] = []
    for line in inputs.lines:
        try:
            mismatches = calc.category_mismatches(
                line, inputs.allocations, inputs.rates, inputs.scales
            )
        except calc.CalcError:
            continue
        found.extend(
            describe_rate_difference(m, inputs.scales, inputs.rates) for m in mismatches
        )
    return tuple(found)


async def cost_item_coverage(
    session: AsyncSession,
    cost_item_id: UUID,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> calc.CostItemCoverage:
    """R6 to R8 for one cost item: basis, covered and uncovered remainder."""
    costs = CostRepository(session)
    items = await costs.items([cost_item_id])
    if not items:
        raise NotFoundError("Kostenpost", cost_item_id)
    invoice_lines = await costs.invoice_lines([cost_item_id])
    coverages = await costs.coverages_of_item(cost_item_id)
    return calc.cost_item_coverage(
        to_calc_cost_item(items[0]),
        tuple(to_calc_invoice_line(i) for i in invoice_lines),
        tuple(to_calc_coverage(c) for c in coverages),
        basis=options.coverage_basis,
    )


def _kpi_overview(
    person_id: UUID,
    year: int,
    allocations: Iterable[calc.Allocation],
    scales: tuple[calc.PersonScale, ...],
    rates: calc.RateBook,
    actuals: dict[tuple[str, Month], Decimal],
    target_pct: Decimal | None,
    options: PricingOptions,
) -> KpiOverview:
    realised = 0
    forecast = 0
    for allocation in allocations:
        for amount in calc.allocation_months(
            allocation,
            rates,
            scales,
            partial_months=options.partial_months,
            actuals=actuals,
        ):
            if amount.month.year != year:
                continue
            if amount.source is AmountSource.ACTUAL:
                realised += amount.cents
            else:
                forecast += amount.cents

    target_cents = None
    if target_pct is not None:
        target_cents = calc.kpi_target(
            calc.BillabilityTarget(
                person_id=str(person_id), year=year, target_pct=target_pct
            ),
            rates,
            scales,
        )
    return KpiOverview(
        person_id=person_id,
        year=year,
        realised_cents=realised,
        forecast_cents=forecast,
        target_cents=target_cents,
        target_pct=target_pct,
    )


async def kpi_overview(
    session: AsyncSession,
    person_id: UUID,
    year: int,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> KpiOverview:
    """R12 and R13 for one person and year (data class F)."""
    details = PersonDetailRepository(session)
    allocations = await AssignmentRepository(session).allocations_of_person(person_id)
    scales = tuple(to_calc_scale(s) for s in await details.scales([person_id]))
    rates = await load_rate_book(session, include_draft=options.include_draft)
    actuals = await _load_actuals(session, [a.id for a in allocations])
    target = await details.target(person_id, year)
    return _kpi_overview(
        person_id,
        year,
        tuple(to_calc_allocation(a) for a in allocations),
        scales,
        rates,
        actuals,
        target.target_pct if target is not None else None,
        options,
    )


async def kpi_overviews(
    session: AsyncSession,
    person_ids: Iterable[UUID],
    year: int,
    *,
    options: PricingOptions = DEFAULT_OPTIONS,
) -> dict[UUID, KpiOverview | None]:
    """``kpi_overview`` for several persons, from what they share read once.

    None for a person whose amounts cannot be derived (no billing scale, no
    rate card for a month).
    """
    ids = list(dict.fromkeys(person_ids))
    if not ids:
        return {}
    return await read_cache.remember_all(
        session,
        "kpi_overviews",
        (tuple(ids), year, options),
        lambda: _kpi_overviews(session, ids, year, options),
    )


async def _kpi_overviews(
    session: AsyncSession, ids: list[UUID], year: int, options: PricingOptions
) -> dict[UUID, KpiOverview | None]:
    rows = await session.execute(
        select(Allocation)
        .where(Allocation.person_id.in_(ids))
        .order_by(Allocation.start_date, Allocation.id)
    )
    allocations_of: dict[UUID, list[Allocation]] = {i: [] for i in ids}
    for allocation in rows.scalars():
        allocations_of[allocation.person_id].append(allocation)
    scales_of: dict[UUID, list[calc.PersonScale]] = {i: [] for i in ids}
    for scale in await PersonDetailRepository(session).scales(ids):
        scales_of[scale.person_id].append(to_calc_scale(scale))
    rates = await load_rate_book(session, include_draft=options.include_draft)
    actuals = await _load_actuals(
        session, [a.id for own in allocations_of.values() for a in own]
    )
    targets = {
        row[0]: row[1]
        for row in await session.execute(
            select(BillabilityTarget.person_id, BillabilityTarget.target_pct).where(
                BillabilityTarget.person_id.in_(ids), BillabilityTarget.year == year
            )
        )
    }
    found: dict[UUID, KpiOverview | None] = {}
    for person_id in ids:
        own = allocations_of[person_id]
        own_ids = {str(a.id) for a in own}
        try:
            found[person_id] = _kpi_overview(
                person_id,
                year,
                tuple(to_calc_allocation(a) for a in own),
                tuple(scales_of[person_id]),
                rates,
                {key: pct for key, pct in actuals.items() if key[0] in own_ids},
                targets.get(person_id),
                options,
            )
        except calc.CalcError:
            found[person_id] = None
    return found
